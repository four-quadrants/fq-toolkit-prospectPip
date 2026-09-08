"""Text extraction for the FQ Intake Auditor.

Reads EVERY page of every document. Redacted PDFs are image-only (the redactor
flattens pages to destroy the text layer), so any page without a usable text
layer is rendered with pymupdf and OCR'd with tesseract.

Results are cached on disk keyed by content hash, so re-running an audit on the
same folder is near-instant. Runs fully offline.
"""
import os, io, re, json, hashlib, multiprocessing

import pymupdf
import pytesseract
from PIL import Image

# One OCR thread per worker: we parallelise across files instead, which is much
# faster than letting each tesseract call fight for the same cores.
os.environ.setdefault('OMP_THREAD_LIMIT', '1')

OCR_DPI = 150
# A page with fewer than this many characters in its text layer is treated as
# image-only and sent to OCR. Redacted pages sometimes carry a few stray glyphs.
MIN_TEXT_LAYER_CHARS = 40


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


# Telling tesseract the real resolution matters — it guesses, and guesses badly on
# a rendered page. But the page-segmentation mode is NOT a free win: PSM 6 ("one
# uniform block") reads ruled form boxes the default drops, and simultaneously
# breaks documents the default handled. Measured here: PSM 6 took Sara W2 2024
# from 401 characters to 836 and made it classify correctly, while taking Daniel
# Term Life Policy Summary from 2490 to 2168 and losing the W-2 markers that
# exposed it as a mislabeled file.
#
# So the default stays primary, and PSM 6 is only a rescue attempt on pages that
# came back too thin to be plausible — keeping whichever result reads longer. Same
# shape as the redactor's escalation: try the alternative, keep it only if better.
OCR_CFG_DEFAULT = '-c user_defined_dpi=%d'
OCR_CFG_BLOCK = '--psm 6 -c user_defined_dpi=%d'

RETRY_UNDER_CHARS = 600       # a whole page thinner than this is usually a failure
RETRY_DPI = 300
PIXEL_BUDGET = 80_000_000     # stay inside Pillow's decompression guard


def _ocr(page, dpi, cfg=OCR_CFG_DEFAULT):
    """One OCR pass at a given resolution, within the pixel budget."""
    rect = page.rect
    est = (rect.width / 72.0 * dpi) * (rect.height / 72.0 * dpi)
    if est > PIXEL_BUDGET:
        dpi = max(100, int(dpi * (PIXEL_BUDGET / est) ** 0.5))
    pix = page.get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(img, config=cfg % dpi)


def _ocr_with_rescue(page, dpi):
    """Default segmentation first; rescue a thin page with PSM 6 at higher dpi."""
    out = _ocr(page, dpi)
    if len(out.strip()) >= RETRY_UNDER_CHARS:
        return out
    better = _ocr(page, max(dpi, RETRY_DPI), OCR_CFG_BLOCK)
    return better if len(better.strip()) > len(out.strip()) else out


# A page can carry a full text layer that is not text. A PDF whose fonts ship no
# ToUnicode map extracts as a substitution cipher: Prather's Memphis lease came
# back as 82,000 characters beginning `!"##$%!&'()($'*$)'+%$$#$,-`, which is
# "COMMERCIAL LEASE AGREEMENT" shifted. It passed the length gate, classified as
# unknown, and landed in "unexpected" while two lease items read as missing —
# the client had sent the document and the audit said she had not.
#
# Legible text is mostly letters and digits; a cipher is mostly punctuation.
# Measured across 532 documents from three completed clients, the lowest ratio
# on a genuinely readable page was 0.473, and the mojibake lease sits at 0.237.
# 0.40 sits in that gap with room on both sides.
MIN_LEGIBLE_ALNUM = 0.40
# Short pages swing wildly — a two-word page of "$1,204.55 —" proves nothing —
# so only judge legibility where there is enough text to judge.
MIN_CHARS_TO_JUDGE = 200


def alnum_ratio(text):
    """Share of non-space characters that are letters or digits."""
    solid = [c for c in text if not c.isspace()]
    if not solid:
        return 0.0
    return sum(1 for c in solid if c.isalnum()) / len(solid)


def _page_text(page, dpi=OCR_DPI):
    t = page.get_text() or ''
    if len(t.strip()) >= MIN_TEXT_LAYER_CHARS:
        if (len(t.strip()) < MIN_CHARS_TO_JUDGE
                or alnum_ratio(t) >= MIN_LEGIBLE_ALNUM):
            return t, False
        # Same escalation the PSM 6 rescue uses above: try the alternative and
        # keep it only if it genuinely reads better. If OCR does no better, the
        # original is returned unchanged — a bad guess must not make things
        # worse than leaving them alone.
        alt = _ocr_with_rescue(page, dpi)
        if alt and alnum_ratio(alt) > alnum_ratio(t):
            return alt, True
        return t, False
    return _ocr_with_rescue(page, dpi), True


PASSWORD_FILE = '_PASSWORDS.txt'


def passwords_near(path, limit=40):
    """Passwords the client sent, read from the notes file beside the documents.

    Clients protect their tax returns and post the password in a portal comment;
    the pull skill writes those comments verbatim into _PASSWORDS.txt. Without
    this, an encrypted return reads as an empty document and the checklist calls
    it missing — which is what happened to a 91-page 1040 that had arrived
    perfectly intact.

    Every whitespace-separated token in that file is tried. Guessing which word
    IS the password from a sentence like "481920365 should be the password for
    the returns" is not worth the risk of guessing wrong; trying them all costs
    microseconds and cannot be fooled by phrasing.
    """
    here = os.path.dirname(os.path.abspath(path))
    for folder in (here, os.path.dirname(here)):
        note = os.path.join(folder, PASSWORD_FILE)
        if not os.path.exists(note):
            continue
        try:
            text = open(note, errors='ignore').read()
        except OSError:
            continue
        seen, out = set(), []
        for tok in re.findall(r'[^\s]{4,40}', text):
            tok = tok.strip('.,;:"\'()[]')
            if tok and tok.lower() not in seen:
                seen.add(tok.lower())
                out.append(tok)
        return out[:limit]
    return []


def open_pdf(path):
    """Open a PDF, unlocking it if the client sent us the password.

    Every route into a PDF must come through here. Four separate places called
    pymupdf.open directly; adding password handling to only the obvious one left
    a 91-page return reading as empty through the parallel path the audit
    actually uses — the same shape of bug as three places each deciding for
    themselves what counted as a PDF. Returns None when it cannot be unlocked.
    """
    doc = pymupdf.open(path)
    if not doc.needs_pass:
        return doc
    for pw in passwords_near(path):
        if doc.authenticate(pw):
            return doc
    doc.close()
    return None


def extract_pdf(path, dpi=OCR_DPI):
    """Return (full_text, page_texts, n_ocr_pages). Reads all pages."""
    doc = open_pdf(path)
    if doc is None:
        return ("[password protected: no password for this file in %s]"
                % PASSWORD_FILE), [], 0
    pages, ocr_count = [], 0
    for page in doc:
        t, was_ocr = _page_text(page, dpi)
        ocr_count += int(was_ocr)
        pages.append(t)
    doc.close()
    return "\n\n".join(pages), pages, ocr_count


def extract_other(path, ext=None):
    """Best-effort text for the non-PDF files clients send.

    `ext` may be supplied by the caller when the filename has none and the
    type was determined from the file's contents instead.
    """
    ext = (ext or os.path.splitext(path)[1]).lower()
    try:
        if ext in ('.txt', '.md', '.csv'):
            return open(path, errors='ignore').read()
        if ext == '.docx':
            from docx import Document
            d = Document(path)
            parts = [p.text for p in d.paragraphs]
            for tbl in d.tables:
                for row in tbl.rows:
                    parts.append(" | ".join(c.text for c in row.cells))
            return "\n".join(parts)
        if ext in ('.xlsx', '.xlsm'):
            from openpyxl import load_workbook
            wb = load_workbook(path, read_only=True, data_only=True)
            parts = []
            for ws in wb.worksheets:
                parts.append(f"[sheet: {ws.title}]")
                for row in ws.iter_rows(values_only=True):
                    parts.append(" | ".join('' if v is None else str(v) for v in row))
            return "\n".join(parts)
        if ext in ('.png', '.jpg', '.jpeg', '.tif', '.tiff'):
            # A photographed or scanned statement. Same OCR the PDF pages get.
            import pytesseract
            from PIL import Image
            return pytesseract.image_to_string(Image.open(path), config=OCR_CFG_DEFAULT)
        if ext in ('.qbb', '.qbw', '.qbm'):
            # A QuickBooks backup is a proprietary binary with no extractable
            # text. It is listed as supported anyway so that it reaches the
            # classifier, which recognises it by extension — the one document
            # type where the filename is the only honest evidence there is.
            # Left out of SUPPORTED, these were skipped silently and the
            # "QuickBooks backup" checklist item read missing with the file
            # sitting right there.
            return ''
        if ext == '.eml':
            import email
            msg = email.message_from_file(open(path, errors='ignore'))
            parts = [f"{k}: {v}" for k, v in msg.items()]
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    parts.append(part.get_payload(decode=True).decode(errors='ignore'))
            return "\n".join(parts)
    except Exception as e:                       # never let one odd file kill a run
        return f"[unreadable: {e}]"
    return ''


SUPPORTED = ('.pdf', '.docx', '.xlsx', '.xlsm', '.txt', '.md', '.csv', '.eml',
             '.qbb', '.qbw', '.qbm', '.png', '.jpg', '.jpeg', '.tif', '.tiff')


# Bump whenever the OCR settings change. The cache is keyed by file CONTENTS, so
# without this a settings improvement is invisible: every document would keep
# serving the text produced by the old settings. Old entries are left on disk
# rather than deleted, so a bump is reversible.
#   v2 (2026-08-21): explicit user_defined_dpi, plus a PSM 6 rescue pass for
#                    pages that come back implausibly thin.
#   v3 (2026-08-28): files whose names have no real extension are now read at
#                    all, so their empty cache entries must not be reused.
#   v5 (2026-08-28): password-protected PDFs are now opened, so their
#                    empty cache entries must not be reused.
#   v7 (2026-09-04): pages whose text layer is a substitution cipher (a PDF with
#                    no ToUnicode map) are now OCR'd. Their cached gibberish
#                    would otherwise be served forever.
OCR_VERSION = 7


def _cache_paths(cache_dir, digest):
    suffix = '' if OCR_VERSION <= 1 else '.v%d' % OCR_VERSION
    return (os.path.join(cache_dir, digest + suffix + '.txt'),
            os.path.join(cache_dir, digest + suffix + '.json'))


def _extract_one(args):
    path, cache_dir, dpi = args
    name = os.path.basename(path)
    digest = file_hash(path)
    txt_p, meta_p = _cache_paths(cache_dir, digest)
    if os.path.exists(txt_p) and os.path.exists(meta_p):
        meta = json.load(open(meta_p))
        meta.update(file=name, path=path, sha256=digest, cached=True)
        return meta, open(txt_p, errors='ignore').read()

    # Trust the extension only when it is one we know. Client filenames are full
    # of dots — "1.1.26 - 3.31.26 Huntington Savings" splits to an 'extension' of
    # '.26 huntington savings', which is not empty, so an `ext or sniff()` test
    # never sniffed and read eight real bank statements as nothing at all.
    kind = resolve_kind(path)
    if kind == '.pdf':
        text, pages, ocr_count = extract_pdf(path, dpi)
        meta = dict(n_pages=len(pages), n_ocr_pages=ocr_count)
    else:
        text = extract_other(path, kind)
        meta = dict(n_pages=1, n_ocr_pages=0)

    os.makedirs(cache_dir, exist_ok=True)
    with open(txt_p, 'w') as fh:
        fh.write(text)
    with open(meta_p, 'w') as fh:
        json.dump(meta, fh)
    meta.update(file=name, path=path, sha256=digest, cached=False)
    return meta, text


def _ocr_page_task(args):
    """OCR a single page. The unit of parallel work is one PAGE, not one file."""
    path, pageno, dpi = args
    doc = open_pdf(path)
    if doc is None:
        return path, pageno, ''
    try:
        # Same settings and thin-page retry as the serial path — this is the one
        # that actually runs for most documents, so a fix applied only to
        # _page_text would have had no effect on a real folder.
        return path, pageno, _ocr_with_rescue(doc[pageno], dpi)
    finally:
        doc.close()


def _survey(path):
    """Cheaply work out which pages have a usable text layer and which need OCR.
    Returns (page_texts, [indices needing OCR])."""
    doc = open_pdf(path)
    if doc is None:
        return [], []
    texts, todo = [], []
    for i, page in enumerate(doc):
        t = page.get_text() or ''
        if len(t.strip()) >= MIN_TEXT_LAYER_CHARS:
            texts.append(t)
        else:
            texts.append(None)
            todo.append(i)
    doc.close()
    return texts, todo


# The auditor writes its deliverables next to the documents it just read, so the
# SECOND run finds them sitting in the folder and treats them as client uploads —
# reporting six new documents that the client never sent, and grading the client's
# own audit report as an unexpected file. Named by suffix rather than by a
# recorded hash so that a copy, a rename, or last quarter's report is caught too.
OWN_OUTPUT_SUFFIXES = (
    ' - intake review.html',
    ' - needs clarification.docx',
    ' - rename log.csv',
    ' - filing log.csv',
    ' - internal audit.docx',
    ' - internal audit.md',
    ' - client email.txt',
    ' - redacted index.html',
)


# Files the toolkit writes INTO the documents folder for the operator to read.
# They are not client documents and must not be audited, classified or filed —
# _PASSWORDS.txt in particular would otherwise be copied into the tree and
# reported as an unexpected document.
OWN_NOTES = {'_passwords.txt'}


def is_own_output(name):
    """Is this a file the auditor itself wrote on an earlier run?"""
    low = (name or '').lower()
    if low in OWN_NOTES:
        return True
    # A zip has already been unpacked into this folder, so auditing the archive
    # as well would report it as an unrecognised document sitting alongside the
    # sixteen real ones it contains.
    if low.endswith('.zip'):
        return True
    return any(low.endswith(s) for s in OWN_OUTPUT_SUFFIXES)


# What the file actually IS, read from its first few bytes.
#
# LaunchBay stores plenty of uploads with no extension at all — Kelly Spaulding
# sent eight Huntington bank statements, an HSA statement and a 401k statement,
# every one of them named without a suffix. Selecting files by extension skipped
# all of them, and because the auditor only counts what it read, it then reported
# "0 unexpected" while eleven real documents sat unopened. Silence like that is
# worse than an error: the client email that follows asks for nothing.
_MAGIC = [
    (b'%PDF', '.pdf'),
    (b'PK\x03\x04', '.xlsx'),      # any OOXML: xlsx/docx are both zips
    (b'\x89PNG\r\n\x1a\n', '.png'),
    (b'\xff\xd8\xff', '.jpg'),
    (b'II*\x00', '.tif'),
    (b'MM\x00*', '.tif'),
    (b'\xd0\xcf\x11\xe0', '.doc'),  # legacy Office
]


def sniff_type(path):
    """Extension this file deserves, judged by content. None if unreadable."""
    try:
        with open(path, 'rb') as fh:
            head = fh.read(8)
    except OSError:
        return None
    for magic, ext in _MAGIC:
        if head.startswith(magic):
            return ext
    return None


def resolve_kind(path):
    """The extension this file should be treated as.

    Every route into extraction has to ask this the SAME way. Three separate
    places tested `path.endswith('.pdf')` on their own, so a PDF uploaded with
    no extension was read correctly by one of them and as an empty string by
    the other two — which is how eight bank statements came out blank.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in SUPPORTED:
        return ext
    return sniff_type(path) or ext


def readable(path):
    """Should the auditor try to read this file?

    Extension first because it is cheap and usually right; content sniffing for
    the rest, so a bank statement saved without a suffix is still read.
    """
    name = os.path.basename(path)
    if name.startswith('.') or is_own_output(name):
        return False
    if name.lower().endswith(SUPPORTED):
        return True
    return sniff_type(path) is not None


ZIP_MARK = ' (from zip) '


def expand_zips(folder, quiet=True):
    """Unpack any zip in the folder so its contents can be audited.

    Clients bundle a year of returns into one archive; the auditor could not see
    inside, so "last two years of completed tax returns" read as missing while
    sixteen documents sat in the zip.

    Extracted files land in the SAME folder, flat, named

        Client Returns (3) (from zip) 2024_OYLER_1040.pdf

    Flat because everything downstream — reading, filing, previews — works on a
    flat folder, and a nested tree would need all of it taught to recurse. The
    marker keeps the origin visible in the filing plan and the rename log, so
    nobody wonders where a file came from.

    The zip itself is left alone. Re-running is free: anything already extracted
    is skipped by name.
    """
    import zipfile
    made = []
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith('.zip'):
            continue
        stem = os.path.splitext(name)[0]
        try:
            zf = zipfile.ZipFile(os.path.join(folder, name))
        except Exception as e:
            if not quiet:
                print("   could not open %s: %s" % (name, e))
            continue
        with zf:
            for info in zf.infolist():
                if info.is_dir() or info.file_size == 0:
                    continue
                inner = os.path.basename(info.filename)
                if not inner or inner.startswith('.') or inner.startswith('__MACOSX'):
                    continue
                out = os.path.join(folder, stem + ZIP_MARK + inner)
                if os.path.exists(out):
                    continue
                try:
                    with zf.open(info) as src, open(out + '.part', 'wb') as dst:
                        while True:
                            chunk = src.read(1 << 20)
                            if not chunk:
                                break
                            dst.write(chunk)
                    os.replace(out + '.part', out)
                    made.append(os.path.basename(out))
                except Exception as e:
                    if not quiet:
                        print("   could not extract %s: %s" % (inner, e))
    if made and not quiet:
        print("  unpacked %d file(s) from zip archives" % len(made))
    return made


def extract_folder(folder, cache_dir=None, dpi=OCR_DPI, workers=None, progress=True):
    """Extract text for every supported file in a folder (non-recursive).

    Returns a list of dicts: file, path, sha256, n_pages, n_ocr_pages, text.

    Work is parallelised across PAGES rather than files. Client folders are
    lopsided -- ninety small statements and one 137-page credit report -- so
    per-file parallelism leaves most cores idle at the end of a run while one
    worker chews through the big document alone.
    """
    cache_dir = cache_dir or os.path.join(folder, '.fq_cache')
    os.makedirs(cache_dir, exist_ok=True)
    expand_zips(folder, quiet=not progress)
    files = [os.path.join(folder, f) for f in sorted(os.listdir(folder))
             if readable(os.path.join(folder, f))]
    workers = workers or max(1, (os.cpu_count() or 2))

    out, pending, tasks = [], {}, []

    for path in files:
        name = os.path.basename(path)
        digest = file_hash(path)
        txt_p, meta_p = _cache_paths(cache_dir, digest)
        if os.path.exists(txt_p) and os.path.exists(meta_p):
            meta = json.load(open(meta_p))
            meta.update(file=name, path=path, sha256=digest, cached=True,
                        text=open(txt_p, errors='ignore').read())
            out.append(meta)
            continue

        kind = resolve_kind(path)
        if kind != '.pdf':
            text = extract_other(path, kind)
            with open(txt_p, 'w') as fh:
                fh.write(text)
            with open(meta_p, 'w') as fh:
                json.dump(dict(n_pages=1, n_ocr_pages=0), fh)
            out.append(dict(file=name, path=path, sha256=digest, n_pages=1,
                            n_ocr_pages=0, cached=False, text=text))
            continue

        texts, todo = _survey(path)
        pending[path] = dict(name=name, digest=digest, texts=texts, todo=set(todo),
                             n_ocr=len(todo))
        tasks += [(path, i, dpi) for i in todo]

    if progress:
        print(f"  {len(out)} of {len(files)} already cached; "
              f"{len(tasks)} pages need OCR across {len(pending)} document(s)", flush=True)

    done = 0
    if tasks:
        if workers > 1 and len(tasks) > 1:
            with multiprocessing.Pool(workers) as pool:
                for path, pageno, text in pool.imap_unordered(_ocr_page_task, tasks):
                    _absorb(pending, path, pageno, text, cache_dir, out)
                    done += 1
                    if progress and (done % 10 == 0 or done == len(tasks)):
                        print(f"    OCR {done}/{len(tasks)} pages", flush=True)
        else:
            for t in tasks:
                path, pageno, text = _ocr_page_task(t)
                _absorb(pending, path, pageno, text, cache_dir, out)

    # anything with no OCR needed at all still has to be written out
    for path, st in list(pending.items()):
        if not st['todo']:
            _finish(pending, path, cache_dir, out)

    order = {os.path.basename(p): i for i, p in enumerate(files)}
    out.sort(key=lambda d: order.get(d['file'], 0))
    return out


def add_page_index(path, cache_dir, dpi=OCR_DPI):
    """Backfill page offsets for a file cached before we recorded them.

    Only called for files that actually have PII findings, so nobody pays to
    re-read a whole folder just to learn page numbers.
    """
    if resolve_kind(path) != '.pdf':
        return None
    digest = file_hash(path)
    txt_p, meta_p = _cache_paths(cache_dir, digest)
    texts, todo = _survey(path)
    for i in todo:
        doc = open_pdf(path)
        if doc is None:
            return None
        try:
            texts[i] = _ocr_with_rescue(doc[i], dpi)   # same path as everywhere else
        finally:
            doc.close()
    pages = [t if t is not None else '' for t in texts]
    text = SEP.join(pages)
    starts = page_starts(pages)
    with open(txt_p, 'w') as fh:
        fh.write(text)
    with open(meta_p, 'w') as fh:
        json.dump(dict(n_pages=len(pages), n_ocr_pages=len(todo), page_starts=starts), fh)
    return dict(text=text, page_starts=starts, n_pages=len(pages), n_ocr_pages=len(todo))


def _absorb(pending, path, pageno, text, cache_dir, out):
    st = pending.get(path)
    if st is None:
        return
    st['texts'][pageno] = text
    st['todo'].discard(pageno)
    if not st['todo']:
        _finish(pending, path, cache_dir, out)


SEP = "\n\n"


def page_starts(pages):
    """Character offset where each page begins in the joined text, so a finding
    at offset N can be reported as "page 26 of 29" instead of leaving someone to
    search a 29-page return by hand."""
    starts, pos = [], 0
    for p in pages:
        starts.append(pos)
        pos += len(p) + len(SEP)
    return starts


def page_of(offset, starts):
    if not starts:
        return None
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def _finish(pending, path, cache_dir, out):
    st = pending.pop(path)
    pages = [t if t is not None else '' for t in st['texts']]
    text = SEP.join(pages)
    txt_p, meta_p = _cache_paths(cache_dir, st['digest'])
    with open(txt_p, 'w') as fh:
        fh.write(text)
    meta = dict(n_pages=len(pages), n_ocr_pages=st['n_ocr'],
                page_starts=page_starts(pages))
    with open(meta_p, 'w') as fh:
        json.dump(meta, fh)
    out.append(dict(file=st['name'], path=path, sha256=st['digest'],
                    n_pages=len(pages), n_ocr_pages=meta['n_ocr_pages'],
                    page_starts=meta['page_starts'],
                    cached=False, text=text))


if __name__ == '__main__':
    import sys
    folder = sys.argv[1]
    cache = sys.argv[2] if len(sys.argv) > 2 else None
    docs = extract_folder(folder, cache)
    print("DONE", len(docs), "files,",
          sum(d['n_pages'] for d in docs), "pages,",
          sum(d['n_ocr_pages'] for d in docs), "OCR'd")
