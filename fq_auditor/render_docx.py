"""Render the internal audit report as a Word .docx (opens cleanly in Pages)."""
import datetime

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from classify import describe

NAVY = RGBColor(0x14, 0x20, 0x2E)
ORANGE = RGBColor(0xE8, 0x79, 0x2B)
RED = RGBColor(0xC0, 0x39, 0x2B)
GREEN = RGBColor(0x1F, 0x8A, 0x5B)
GREY = RGBColor(0x5B, 0x6B, 0x7A)


def _h(doc, text, size=13, color=NAVY, before=12):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(size)
    r.font.color.rgb = color
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(4)
    return p


def _p(doc, text, color=None, bullet=True, bold=False, size=10.5, italic=False):
    p = doc.add_paragraph(style='List Bullet' if bullet else None)
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.bold = bold
    r.italic = italic
    if color:
        r.font.color.rgb = color
    p.paragraph_format.space_after = Pt(2)
    return p


def _rich(doc, parts, bullet=True):
    """parts = [(text, bold, color), ...] on a single bullet line."""
    p = doc.add_paragraph(style='List Bullet' if bullet else None)
    for text, bold, color in parts:
        r = p.add_run(text)
        r.font.size = Pt(10.5)
        r.bold = bold
        if color:
            r.font.color.rgb = color
    p.paragraph_format.space_after = Pt(2)
    return p


def build_docx(res, client, checklist_source, path):
    docs, results = res['docs'], res['results']
    cross, leaks = res['cross'], res['leaks']

    d = Document()
    t = d.add_paragraph()
    r = t.add_run(f"Intake Audit — {client}")
    r.bold = True
    r.font.size = Pt(20)
    r.font.color.rgb = NAVY
    t.paragraph_format.space_after = Pt(2)

    sub = d.add_paragraph()
    rs = sub.add_run(
        f"{datetime.date.today().strftime('%B %d, %Y')}   ·   {len(docs)} documents, "
        f"{sum(x['n_pages'] for x in docs)} pages "
        f"({sum(x['n_ocr_pages'] for x in docs)} read by OCR)   ·   "
        f"checklist: {checklist_source}")
    rs.italic = True
    rs.font.size = Pt(9)
    rs.font.color.rgb = GREY

    counts = {}
    for x in results:
        counts[x['status']] = counts.get(x['status'], 0) + 1

    _h(d, "Summary", 12)
    _rich(d, [(f"{counts.get('satisfied', 0)} satisfied", True, GREEN), ("   ·   ", False, GREY),
              (f"{counts.get('mismatched', 0)} mismatched", True, ORANGE), ("   ·   ", False, GREY),
              (f"{counts.get('missing', 0)} missing", True, RED), ("   ·   ", False, GREY),
              (f"{len(res['unexpected'])} unexpected", True, GREY)], bullet=False)
    _rich(d, [(f"{len(cross['gaps'])} statement series with missing months", True, ORANGE),
              ("   ·   ", False, GREY),
              (f"{len(cross['mislabeled'])} files whose contents contradict the filename", True, ORANGE),
              ("   ·   ", False, GREY),
              (f"{len(leaks)} files with residual PII", True, RED)], bullet=False)

    def bucket(title, statuses, color):
        _h(d, title, 12, color)
        rows = [x for x in results if x['status'] in statuses]
        if not rows:
            _p(d, "(none)", GREY)
            return
        for sec in ('Personal', 'Practice'):
            srows = [x for x in rows if x['item']['section'] == sec]
            if not srows:
                continue
            _p(d, sec, NAVY, bullet=False, bold=True, size=10.5)
            for x in srows:
                parts = [(x['item']['label'], False, None)]
                if x['note']:
                    parts.append((f"  —  {x['note']}", False, color))
                if x['docs']:
                    parts.append(("   [" + ", ".join(y['file'] for y in x['docs']) + "]",
                                  False, GREY))
                _rich(d, parts)

    bucket("Satisfied", ['satisfied'], GREEN)
    bucket("Mismatched — arrived, but wrong scope", ['mismatched'], ORANGE)
    bucket("Missing", ['missing'], RED)

    _h(d, "Statement series with missing months", 12, ORANGE)
    if cross['gaps']:
        for g in cross['gaps']:
            head = g['label'] + (f" · {g['issuer']}" if g['issuer'] else '')
            head += f" · x{g['account_tail']}" if g['account_tail'] else ''
            _rich(d, [(head, True, None),
                      (f"  —  have {', '.join(g['present'])}; ", False, None),
                      (f"missing {', '.join(g['missing'])}", True, RED)])
    else:
        _p(d, "(none)", GREY)

    if cross['gap_fillers']:
        _h(d, "A missing month may already be in the folder under a wrong name", 11, ORANGE, 8)
        for h in cross['gap_fillers']:
            _rich(d, [(f"{h['month']} of {h['gap']['label']}", True, None),
                      (f"  —  {h['file']} is named like a "
                       f"{h['claimed'].replace('_', ' ')}, but its contents are a "
                       f"{h['actual'].replace('_', ' ')} for that month", False, None)])

    _h(d, "Content does not match the filename", 12, ORANGE)
    if cross['mislabeled']:
        for m in cross['mislabeled']:
            _rich(d, [(m['file'], True, None),
                      (f"  —  named like a {m['claimed'].replace('_', ' ')}, "
                       f"contents are ", False, None),
                      (m['actual'].replace('_', ' '), True, ORANGE)])
    else:
        _p(d, "(none)", GREY)

    _h(d, "Duplicates", 12, GREY)
    if cross['duplicates']:
        for x in cross['duplicates']:
            _rich(d, [(x['kind'], True, None),
                      (": " + ", ".join(x['files'])
                       + (f"  —  {x['detail']}" if x.get('detail') else ''), False, None)])
    else:
        _p(d, "(none)", GREY)

    _h(d, "Unexpected — provided but not on the checklist", 12, GREY)
    if res['unexpected']:
        for x in sorted(res['unexpected'], key=lambda y: (y['doc_type'], y['file'])):
            _rich(d, [(x['file'], False, None), ("  —  " + describe(x), False, GREY)])
    else:
        _p(d, "(none)", GREY)

    if res['facts'].get('rental_property_count'):
        _h(d, "Cross-checks", 12, NAVY)
        _p(d, f"{res['facts']['rental_property_source']} shows "
              f"{res['facts']['rental_property_count']} rental properties, so that many signed "
              f"leases are genuinely expected.")

    _h(d, "Residual PII — INTERNAL ONLY", 12, RED)
    _p(d, "Never send this section, or anything derived from it, to a client. Re-redact any "
          "file listed below before it leaves the firm.", RED, bullet=False, italic=True, size=9.5)
    _p(d, "Values are masked to the last four digits. A finding only fires on six or more "
          "digits, so it always means the document contains more than a last-four. "
          "Low-confidence matches (OCR artifacts from numeric tables) are counted, not listed.",
       GREY, bullet=False, italic=True, size=9)

    n_high = sum(1 for v in leaks.values() for f in v if f['confidence'] == 'high')
    hi_files = sum(1 for v in leaks.values() if any(f['confidence'] == 'high' for f in v))
    noise = sum(x.get('pii_noise', 0) for x in docs)
    _rich(d, [(f"{n_high} high-confidence finding(s) in {hi_files} file(s)", True, RED),
              (" — start here. "
               f"A further {len(leaks) - hi_files} file(s) have lower-confidence matches "
               f"only; {noise} likely OCR artifact(s) suppressed.", False, GREY)], bullet=False)

    if leaks:
        for fname, findings in sorted(leaks.items()):
            hi = [f for f in findings if f['confidence'] == 'high']
            med = [f for f in findings if f['confidence'] == 'medium']
            _p(d, fname, NAVY, bullet=False, bold=True, size=10.5)
            for f in hi:
                from audit import page_list
                pages = f.get('pages') or ([f['page']] if f.get('page') else [])
                where = (f"page{'s' if len(pages) > 1 else ''} "
                         f"{page_list(pages)} of {f['n_pages']}"
                         if pages else "page not recorded")
                _rich(d, [(f"{where}  ", True, NAVY),
                          (f"{f['kind']} ", True, RED),
                          (f"{f['masked']} ", True, None),
                          (f"({f['digits_seen']} digits present) — {f['why']}", False, None)])
                _p(d, f"context: {f['context']}", GREY, size=8.5)
            if med:
                _p(d, f"{len(med)} lower-confidence match(es): "
                      + ", ".join(f"{f['kind']} {f['masked']}" for f in med[:6])
                      + (" ..." if len(med) > 6 else ""), GREY)
    else:
        _p(d, "None detected.", GREY)

    d.save(path)
    return path
