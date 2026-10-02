"""Single-file interactive HTML review for the FQ intake auditor.

    build_html(res, client, checklist_source, path, decisions=None)

Same inputs as render_docx.build_docx, plus any decisions carried over from a
previous review.

WHY HTML AS WELL AS DOCX
The Word report is a deliverable you read. Reviewing an audit is different work:
filtering, searching, and making a call on the documents the classifier would not
guess at. That needs an interface. Python keeps doing OCR, classification and the
file moves; this is only the review surface.

HOW THE ROUND TRIP WORKS
A page opened from file:// cannot write to disk. So decisions are held in the page
and exported as one small JSON file:

    review the page  ->  "Download decisions"  ->  decisions.json
    next run:  audit.py ... --decisions decisions.json

Decisions are keyed by SHA-256 of the file's contents, not by filename, so they
survive renames and re-runs and cannot attach to the wrong document.

The page is entirely self-contained — no CDN, no fonts, nothing fetched. Its CSP
forbids network access outright, because the internal section contains client PII.
"""

import os, re, io, json, html, base64, datetime

# ---------------------------------------------------------------- filing plan

# Everything the auditor files sits under one folder, so the client folder keeps
# its own shape: Original_sourcedocs, _Audit and the analysis work stay visible
# beside Documents rather than being crowded out by two big trees.
#
#   2026/Spaulding, Kelly/Documents/Personal/...
#   2026/Spaulding, Kelly/Documents/Business/...
DOCS_DIR = 'Documents'
SIDE_DIR = {'Personal': 'Personal', 'Practice': 'Business'}
REVIEW_DIR = os.path.join(DOCS_DIR, '_Needs Review')

TYPE_MAP = {
    'bank_statement':        (None,       'Banking'),
    'cc_statement':          ('Practice', 'Credit Cards'),
    'brokerage_statement':   ('Personal', 'Investments'),
    'credit_report':         ('Personal', 'Credit Reports'),
    'w2':                    ('Personal', 'Pay Info:W2s'),
    'paystub':               ('Personal', 'Pay Info:W2s'),
    'payroll_summary':       ('Practice', 'Payroll Summaries'),
    'pnl':                   ('Practice', 'Financials'),
    'balance_sheet':         ('Practice', 'Financials'),
    'personal_tax_return':   ('Personal', 'Taxes'),
    'business_tax_return':   ('Practice', 'Taxes'),
    'day_sheet':             ('Practice', 'Production/Monthly Production'),
    'provider_productivity': ('Practice', 'Production/Monthly Production'),
    'fee_schedule':          ('Practice', 'Fees'),
    'employment_contract':   ('Practice', 'Associate Info'),
    'building_value':        ('Practice', ''),
    'debt_schedule':         (None,       'Debt'),
    # A line of credit is debt, and it can sit on either side of the house — so
    # it takes the debt_schedule treatment: no forced side, the classifier's
    # read decides. A practice LOC files to Business/Debt, a personal one to
    # Personal/Debt, and an unreadable one goes to a human.
    'line_of_credit':        (None,       'Debt'),
    'disability_insurance':  ('Personal', 'Insurance'),
    'life_insurance':        ('Personal', 'Insurance'),
    # The classifier emits 'property_insurance' and 'overhead_insurance'. The two
    # longer names below were never emitted by anything, so those mappings had
    # never fired once and both kinds of policy went to review instead. Kept as
    # aliases in case an older decisions.json refers to them.
    'property_insurance':    ('Personal', 'Insurance'),
    'homeowners_insurance':  ('Personal', 'Insurance'),
    'overhead_insurance':    ('Practice', 'Insurance'),
    'business_overhead_insurance': ('Practice', 'Insurance'),
    'insurance_policy':      (None,       'Insurance'),

    # Anything describing how the practice performed — what was produced,
    # collected, how many days were worked, how many patients came through.
    'production_report':     ('Practice', 'Production'),
    'dr_days_worked':        ('Practice', 'Production'),
    'total_patients':        ('Practice', 'Production'),
    'new_patients':          ('Practice', 'Production'),

    'hsa_statement':         ('Personal', 'Investments'),

    # Tax paperwork follows the return it belongs to.
    'form_1099':             ('Personal', 'Pay Info:W2s'),
    'k1':                    ('Personal', 'Taxes'),
    'schedule_e':            ('Personal', 'Taxes'),
    'partnership_tax_return': ('Practice', 'Taxes'),

    'quickbooks_file':       ('Practice', 'Financials'),
    'provider_schedule':     ('Practice', 'Logistics'),

    # --- judgement calls, not rules handed down. Easy to move if wrong. ---
    # Payer mix drives the fee analysis, so it sits with the fee schedule.
    'ffs_percentage':        ('Practice', 'Fees'),
    'insurance_carriers':    ('Practice', 'Fees'),
    # The service agreement with their CPA firm covers practice and personal
    # both; filed practice-side because that is where the entity work lives.
    'engagement_letter':     ('Practice', 'Logistics'),
    'financial_plan':        ('Personal', 'Misc'),
    # Practice admin — the paperwork that runs the office rather than reports on it.
    'staff_roster':     ('Practice', 'Logistics'),
    'bonus_structure':  ('Practice', 'Logistics'),
    'practice_hours':   ('Practice', 'Logistics'),
    # A signed lease is a property document; the checklist files it under Personal.
    'rental_lease':     ('Personal', 'Assets'),
    # Still deliberately unmapped: if the classifier does not know what it is, a
    # human should look rather than have it dropped into Misc unseen.
    'client_note':      ('Personal', 'Misc'),
    # Birthdates are never really a document — they arrive typed in a portal
    # comment or an email. When one does turn up as a file, it is a personal
    # scrap, not a statement.
    'birthdates':       ('Personal', 'Misc'),
    'unknown':          (None, None),
}

# Offered in the destination dropdown. Account-level folders are appended live
# from whatever the classifier actually read off the statements.
BASE_DESTS = [DOCS_DIR + '/' + d for d in [
    'Personal/Assets', 'Personal/Banking', 'Personal/Credit Reports', 'Personal/Debt',
    'Personal/Insurance', 'Personal/Investments', 'Personal/Pay Info:W2s', 'Personal/Taxes',
    'Personal/Misc',
    'Business/Banking', 'Business/Credit Cards', 'Business/Debt', 'Business/Fees',
    'Business/Financials', 'Business/Insurance', 'Business/Payroll Summaries',
    'Business/Production', 'Business/Production/Monthly Production', 'Business/Taxes',
    'Business/Logistics', 'Business/Misc',
]]

# Misc was in the original filing-tree sketch in RESUME_HERE.md for both sides.
# It is offered in the dropdown even though the folders do not exist on disk yet —
# filing creates what it needs.
PREVIEW_MAX_W = 560      # thumbnail width in px
PREVIEW_SNIPPET = 700    # characters of extracted text shown under the thumbnail


def build_redacted_index(redacted_dir):
    """lowercased stem -> redacted file path.

    Cena names its output "<original stem> (redacted).pdf". Indexed by stem with
    the extension dropped, so a .docx source redacted to .pdf still matches, as
    does a file whose extension differs only in case.
    """
    idx = {}
    if not redacted_dir or not os.path.isdir(redacted_dir):
        return idx
    for name in os.listdir(redacted_dir):
        stem = os.path.splitext(name)[0]
        stem = stem.replace(' (redacted)', '').replace('(redacted)', '').strip()
        idx.setdefault(stem.lower(), os.path.join(redacted_dir, name))
    return idx


def mask_digits(s):
    """Digits to '#', letters untouched.

    A reviewer deciding "personal or practice?" needs the issuer name, the
    document title, the city — never the numbers. Masking keeps every word that
    carries classification signal and removes every account, routing and ID
    number from the page as text. Doing this matters as much as redacting the
    images: text is searchable.
    """
    return ''.join('#' if c.isdigit() else c for c in (s or ''))


def _thumb_data_uri(path, max_w=PREVIEW_MAX_W):
    """First page of a document as an inlined JPEG data URI, or None.

    Inlined rather than linked: a page opened from file:// cannot reliably
    navigate to sibling file:// documents in Chrome, and an embedded image always
    renders. Non-PDF inputs (docx, xlsx) have no page to render — those fall back
    to the text snippet.
    """
    try:
        import fitz
    except Exception:
        return None
    if not path or not str(path).lower().endswith('.pdf'):
        return None
    try:
        import base64
        d = fitz.open(path)
        if not len(d):
            return None
        pg = d[0]
        scale = min(1.0, float(max_w) / max(1.0, pg.rect.width))
        pix = pg.get_pixmap(matrix=fitz.Matrix(scale * 2, scale * 2))
        try:
            raw = pix.tobytes('jpeg', jpg_quality=62)
            mime = 'image/jpeg'
        except Exception:
            raw = pix.tobytes('png')
            mime = 'image/png'
        d.close()
        return 'data:%s;base64,%s' % (mime, base64.b64encode(raw).decode('ascii'))
    except Exception:
        return None


def _snippet(cache_dir, sha, n=PREVIEW_SNIPPET):
    """Start of the already-extracted text from the OCR cache, digits masked."""
    if not cache_dir or not sha:
        return None
    p = os.path.join(cache_dir, sha + '.txt')
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding='utf-8', errors='replace') as fh:
            t = fh.read(n * 3)
        return mask_digits(' '.join(t.split())[:n])
    except Exception:
        return None


def under_documents(dest):
    """Bring a saved decision into the Documents/ tree.

    Decisions are keyed by content hash and outlive the code. Ones chosen before
    filing moved under Documents/ say "Business/Debt", and were still being
    honoured literally — so a document the operator had explicitly placed ended
    up as the one thing outside the tree, which looks exactly like a bug in the
    filing rather than an old choice being respected.
    """
    d = (dest or '').strip().strip('/')
    if not d or d.startswith(DOCS_DIR + '/') or d == DOCS_DIR:
        return d
    first = d.split('/')[0]
    if first in set(SIDE_DIR.values()) | {'_Needs Review'}:
        return DOCS_DIR + '/' + d
    return d


def plan_destination(doc):
    """Where this document should go, and whether a human must decide.

    Returns (path, reason, needs_review). Nothing is guessed: no confident side,
    no confident classification, or no folder in the tree all route to review
    with the reason stated.
    """
    dtype = doc.get('doc_type') or 'unknown'
    side = doc.get('owner_side')
    conf = doc.get('confidence')

    mapped = TYPE_MAP.get(dtype)
    if not mapped or mapped[1] is None:
        return (REVIEW_DIR, 'no folder in the tree for "%s" yet' % dtype, True)

    forced_side, sub = mapped
    use_side = forced_side or side
    if not use_side:
        return (REVIEW_DIR, 'personal vs practice unclear — needs a human call', True)
    if conf == 'low':
        return (REVIEW_DIR, 'classified with low confidence', True)

    parts = [DOCS_DIR, SIDE_DIR.get(use_side, use_side), sub]
    if dtype in ('bank_statement', 'cc_statement', 'brokerage_statement'):
        tail, issuer = doc.get('account_tail'), doc.get('issuer')
        if tail:
            parts.append('x%s' % str(tail).lstrip('xX'))
        elif issuer:
            parts.append(str(issuer))
        else:
            return ('/'.join(parts), 'no account number or issuer read — filed at folder level', True)
    return ('/'.join(parts), 'classified %s' % dtype.replace('_', ' '), False)


def account_key(doc):
    """Stable key for the ACCOUNT a statement belongs to, not the statement.

    Whether Arvest x9299 is personal or the practice's is a fact about the
    account, true for every month of it. Keying a decision to the account means
    answering once, not once per statement and again next quarter.
    """
    if (doc.get('doc_type') or '') not in ('bank_statement', 'cc_statement', 'brokerage_statement'):
        return None
    issuer = (doc.get('issuer') or '').strip().lower()
    tail = str(doc.get('account_tail') or '').strip().lstrip('xX').lower()
    if not issuer and not tail:
        return None
    # Issuer AND tail. Keying on the tail alone would have merged two unrelated
    # accounts — Cap 1 HYSA and Arvest Platinum both end 5502 in this corpus.
    # The fragmentation that made the tail tempting (the same account keying as
    # "capital one|2284" one month and "|2284" the next) is fixed upstream by
    # propagate_issuer_within_series, which backfills the missing issuer.
    return '%s|%s' % (issuer, tail)


def split_decisions(decisions):
    """Accept {'files':{}, 'accounts':{}} or a legacy flat {sha: …} map."""
    decisions = decisions or {}
    if 'files' in decisions or 'accounts' in decisions:
        return decisions.get('files') or {}, decisions.get('accounts') or {}
    return decisions, {}


def item_decisions(decisions):
    """The reviewer's verdicts on checklist items, keyed by item id.

    Kept out of split_decisions so its two-value signature stays as it is —
    several callers unpack it, and widening the tuple would break them
    silently at the point where filing decisions are read.
    """
    return ((decisions or {}).get('items') or {}) if isinstance(decisions, dict) else {}


def build_plan(docs, decisions=None, mislabeled=()):
    """Filing plan — destination AND proposed name — with human decisions applied.

    An account-level decision wins over a per-file one only where no per-file
    decision exists: a specific call about one statement should not be overridden
    by a general rule about its account.

    One function produces both the destination and the name so the review page,
    the writeup and the rename log cannot disagree with each other.
    """
    by_file, by_account = split_decisions(decisions)
    mislabeled = set(mislabeled or ())
    rows = []
    for d in sorted(docs, key=lambda x: (x.get('doc_type') or '', x.get('file') or '')):
        dest, why, review = plan_destination(d)
        sha = d.get('sha256') or ''
        akey = account_key(d)
        decided = by_file.get(sha)
        if not (decided and decided.get('dest')) and akey:
            acct = by_account.get(akey)
            if acct and acct.get('dest'):
                decided = dict(acct)
                decided['note'] = ('account rule' +
                                   (': ' + acct['note'] if acct.get('note') else ''))
        if decided and decided.get('dest'):
            rows.append({
                'sha': sha, 'file': d.get('file'), 'dest': under_documents(decided['dest']),
                'why': 'your decision' + (' — ' + decided['note'] if decided.get('note') else ''),
                'review': False, 'decided': True,
                'doc_type': d.get('doc_type'), 'side': d.get('owner_side'),
                'year': d.get('year'), 'month': d.get('month'),
                'issuer': d.get('issuer'), 'tail': d.get('account_tail'),
                'conf': d.get('confidence'), 'pages': d.get('n_pages'), 'path': d.get('path'),
                'akey': akey,
            })
            continue
        rows.append({
            'sha': sha, 'file': d.get('file'), 'dest': dest, 'why': why,
            'review': review, 'decided': False,
            'doc_type': d.get('doc_type'), 'side': d.get('owner_side'),
            'year': d.get('year'), 'month': d.get('month'),
            'issuer': d.get('issuer'), 'tail': d.get('account_tail'),
            'conf': d.get('confidence'), 'pages': d.get('n_pages'), 'path': d.get('path'),
            'akey': akey,
        })

    # Names, then collisions — collisions can only be judged once every proposed
    # name exists, and a decided destination changes which names share a folder.
    by_sha = {d.get('sha256'): d for d in docs}
    for r in rows:
        doc = by_sha.get(r['sha']) or {}
        new, why, confirm = plan_rename(doc, mislabeled, doc.get('person'))
        r['new_name'] = new
        r['rename_why'] = why
        r['needs_confirmation'] = confirm
    resolve_collisions(rows)
    return rows


# ------------------------------------------------------------------- renaming

TYPE_NAME = {
    'w2': 'W-2', 'paystub': 'Paystub', 'payroll_summary': 'Payroll summary',
    'pnl': 'P&L', 'balance_sheet': 'Balance sheet', 'day_sheet': 'Day sheet',
    'provider_productivity': 'Provider productivity', 'fee_schedule': 'Fee schedule',
    'debt_schedule': 'Debt schedule', 'credit_report': 'Credit report',
    'personal_tax_return': 'Personal tax return', 'business_tax_return': 'Business tax return',
    'life_insurance': 'Life insurance', 'disability_insurance': 'Disability insurance',
    'homeowners_insurance': 'Homeowners insurance', 'rental_lease': 'Lease',
    'staff_roster': 'Staff roster', 'bonus_structure': 'Bonus structure',
    'practice_hours': 'Practice hours', 'client_note': 'Note',
}
STATEMENTS = ('bank_statement', 'cc_statement', 'brokerage_statement')

# A name is "ambiguous" when it tells a human nothing: all digits, a bare person
# name, a duplicate marker, or no type word at all.
_TYPE_WORDS = re.compile(
    r'stmt|statement|w-?2|paystub|pay\s?stub|payroll|p\s?&\s?l|profit|loss|balance|'
    r'tax|return|1040|1120|lease|roster|bonus|hours|fee|debt|credit\s?report|'
    r'insur\w*|\bins\b|policy|day\s?sheet|productivity|brokerage|ira|roth|529|hsa|'
    r'\bcc\b|\bcard\b', re.I)


def is_ambiguous_name(fname):
    stem = os.path.splitext(fname or '')[0]
    if not stem:
        return True
    if re.fullmatch(r'[\d\W_]+', stem):            # "74074"
        return True
    if re.search(r'\(\d+\)\s*$', stem):            # "Avery Roth (1)"
        return True
    return not _TYPE_WORDS.search(stem)            # "Erin Roth", "College"


# Product and institution words a human put in the filename that the classifier
# cannot read back. "Cap 1 HYSA March" became "Daniel Chk (Capital One) x5502" —
# the rename would have thrown away the fact that it is a high-yield savings
# account and replaced it with a wrong guess. If the old name carries something
# the new one does not, the old name wins.
_PRODUCT_HINTS = re.compile(
    r'hysa|high[- ]?yield|free\s*blue|platinum|money\s*market|\bmm\b|\bhsa\b|\b529\b|'
    r'roth|\bira\b|rollover|\b401\s?k\b|\b457\b|\b403\s?b\b|savings|checking|'
    r'\bchk\b|\bsav\b|\bcd\b|joint|rental|escrow|sweep', re.I)


def name_loses_information(old_name, new_name):
    """True when the old filename says something the proposed one does not."""
    old_stem = os.path.splitext(old_name or '')[0]
    new_low = (new_name or '').lower()
    for word in set(m.group(0).lower() for m in _PRODUCT_HINTS.finditer(old_stem)):
        if word.strip() and word not in new_low:
            return True

    # A bare number in a client's filename is nearly always a fact they wanted
    # kept: "2024 144 Total Dr Days" is a year's day count, "ADA Life Ins 381824"
    # is a policy number. Renaming that to "Day sheet 2024-01" dropped the 144 AND
    # asserted a January the file never claimed. Years are ignored (the new name
    # carries those), and an account tail already echoed in the new name counts as
    # kept, so statements still get renamed.
    # Dates are stripped first, or the "30" in "2026-06-30" reads as a fact worth
    # keeping and blocks a perfectly good rename.
    stripped = re.sub(r'\d{1,4}[./-]\d{1,2}[./-]\d{2,4}|\b(19|20)\d{2}[-/]\d{1,2}\b',
                      ' ', old_stem)
    for num in set(re.findall(r'\b\d{2,7}\b', stripped)):
        if re.fullmatch(r'(19|20)\d{2}', num):
            continue                       # a year — the new name keeps it
        if num in new_low:
            continue                       # preserved, e.g. an account tail
        return True
    return False


# Only these types name a person. A joint tax return has two, an S-corp return has
# none, and a practice document belongs to the practice — attaching whoever
# happened to be mentioned produced "Sara Business tax return 2023".
PERSONAL_TITLED = ('w2', 'paystub', 'brokerage_statement',
                   'life_insurance', 'disability_insurance', 'credit_report')


def _clean(s):
    """Filename-safe, without mangling the parts a human reads."""
    s = re.sub(r'[/\\:*?"<>|]', '-', str(s))
    return re.sub(r'\s+', ' ', s).strip(' .')


def proposed_name(doc, person=None):
    """Name from what the CONTENT says, following the firm's convention.

    Statements:  "Nadia Chk (BancFirst) x4108 2026-01.pdf"
    Everything:  "Daniel W-2 2024.pdf"  /  "Payroll summary 2026-02.pdf"

    Returns None when there is not enough to beat the existing name — a rename
    that loses information is worse than no rename.
    """
    dtype = doc.get('doc_type')
    if not dtype or dtype == 'unknown':
        return None
    ext = os.path.splitext(doc.get('file') or '')[1].lower()
    parts = []
    if person:
        parts.append(str(person))

    if dtype in STATEMENTS:
        kind = doc.get('account_kind') or _KIND_FALLBACK.get(dtype)
        if kind:
            parts.append(kind)
        if doc.get('issuer'):
            parts.append('(%s)' % doc['issuer'])
        if doc.get('account_tail'):
            parts.append('x%s' % str(doc['account_tail']).lstrip('xX'))
        if not doc.get('issuer') and not doc.get('account_tail'):
            return None            # nothing to distinguish it from its siblings
    else:
        parts.append(TYPE_NAME.get(dtype, dtype.replace('_', ' ').capitalize()))

    y, m = doc.get('year'), doc.get('month')
    # A month is only meaningful on a monthly document. An annual production
    # report contains twelve monthly ROWS, and the first of them was being read
    # as the document's own month — so "2024 AnnualP&I.csv" filed as
    # "Production report 2024-01", which any reader takes for January.
    # Requires 'monthly' explicitly rather than defaulting to it: on this corpus
    # every document carrying a month it should not have — the annual P&I files,
    # a life policy, a debt sheet, three credit reports — had no granularity at
    # all, while every genuinely monthly one was tagged.
    if m and doc.get('granularity') != 'monthly':
        m = None
    if y and m:
        parts.append('%s-%02d' % (y, int(m)))
    elif y:
        parts.append(str(y))
    elif dtype in PERIOD_REQUIRED:
        # Say WHAT it is even when the period cannot be read. A file sitting there
        # called "Term Life Policy Summary" when its contents are a W-2 is actively
        # misleading; "Daniel W-2 (year TBD)" is merely incomplete. The marker is
        # in the name rather than only in the report because three W-2s would
        # otherwise all become "Daniel W-2.pdf", and because the folder itself
        # should show what still needs a human.
        parts.append(PERIOD_TBD)
    return _clean(' '.join(parts)) + ext


PERIOD_TBD = '(year TBD)'


# A period is REQUIRED only where the document is one of a run — a statement for
# a month, a return for a year, production data for a month. Those names collide
# with their own siblings without it ("Daniel W-2.pdf" three years running), and
# the checklist asks for them by period, so a name without one cannot be checked
# off against it.
#
# Derived from the classifier's own PERIODIC set so the two cannot drift apart,
# plus the year-scoped forms. Everything else — a lease, a staff roster, a fee
# schedule, an insurance policy — takes a year when one is known and is named
# perfectly well without one.
try:
    from classify import PERIODIC as _PERIODIC
except Exception:
    _PERIODIC = set(STATEMENTS) | {'payroll_summary', 'provider_productivity',
                                   'day_sheet', 'pnl', 'balance_sheet'}
PERIOD_REQUIRED = set(_PERIODIC) | {
    'w2', 'paystub', 'personal_tax_return', 'business_tax_return',
}


# Used when the product could not be read. "Bank stmt (BancFirst) x2274 2025-12"
# is recognisable at a glance; "Acct (BancFirst) …" is not.
_KIND_FALLBACK = {'cc_statement': 'CC', 'brokerage_statement': 'Brok', 'bank_statement': 'Bank stmt'}


def plan_rename(doc, mislabeled_files, person=None):
    """(new_name, reason, needs_confirmation).

    Only renames where the name is WRONG or says nothing. A name the client chose
    that already describes the contents is left alone — churn for its own sake
    makes the tree harder to recognise, not easier.

    needs_confirmation is True when the new name is right about the TYPE but
    incomplete: the period could not be read. Those get renamed anyway and are
    surfaced for a human, because the old name was worse than incomplete.
    """
    fname = doc.get('file') or ''
    # Person only where the document is genuinely one person's.
    if doc.get('doc_type') not in PERSONAL_TITLED:
        person = None
    proposed = proposed_name(doc, person)
    if not proposed:
        return None, 'not enough read from the contents to name it safely', False
    if proposed.lower() == fname.lower():
        return None, 'already named correctly', False

    tbd = PERIOD_TBD in proposed
    mislabeled = fname in mislabeled_files

    if name_loses_information(fname, proposed):
        if mislabeled:
            return proposed, 'filename contradicts the contents (old name held extra detail)', True
        return None, 'existing name carries detail the classifier cannot read', False
    if mislabeled:
        why = 'filename contradicts the contents'
        if tbd:
            why += ' — type is confirmed, period is not'
        return proposed, why, tbd
    if is_ambiguous_name(fname):
        why = 'existing name says nothing about the contents'
        if tbd:
            why += ' — period could not be read'
        return proposed, why, tbd
    return None, 'existing name is accurate enough — left alone', False


# Words that appear in half of all client filenames and distinguish nothing.
_DULL = {'the', 'and', 'for', 'copy', 'final', 'scan', 'scanned', 'new', 'doc',
         'document', 'file', 'statement', 'statements', 'report', 'reports',
         'pdf', 'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep',
         'sept', 'oct', 'nov', 'dec', 'ytd', 'annual'}


def _distinguisher(row, others):
    """A word from this file's ORIGINAL name that its rivals do not have.

    "2024 AnnualP&I.csv" and "2024 DOCTOR ONLY AnnualP&I.csv" both propose
    "Production report 2024". The difference matters to whoever opens the folder,
    and it is sitting in the name the client already gave it — so use that rather
    than a number. Returns None when nothing sets this file apart.
    """
    def words(name):
        return re.findall(r"[A-Za-z]{3,}", os.path.splitext(name or '')[0])

    theirs = set()
    for o in others:
        theirs |= {w.lower() for w in words(o.get('file'))}

    picked = []
    for w in words(row.get('file')):
        lw = w.lower()
        if lw in theirs or lw in _DULL or lw in {p.lower() for p in picked}:
            continue
        picked.append(w.title())
        if len(picked) == 2:
            break
    return ' '.join(picked) or None


def resolve_collisions(rows):
    """Two documents must never propose the same name in the same folder.

    Found immediately on the real corpus: "2024 individual Bassett main.pdf" and
    "Cash_App_January_2026_Account_Statement.pdf" both proposed
    "Personal tax return 2024.pdf" — the second is a mislabeled copy of the same
    return. Renaming both would have destroyed one. Collisions are numbered AND
    flagged, because a collision usually means two documents that need comparing,
    not just a naming clash.
    """
    seen = {}
    for r in rows:
        if not r.get('new_name'):
            continue
        key = ((r.get('dest') or '').lower(), r['new_name'].lower())
        seen.setdefault(key, []).append(r)
    for key, group in seen.items():
        if len(group) < 2:
            continue
        # Prefer a word from the client's OWN filename over a counter. Her two
        # 2024 production files differ only in that one is doctor only;
        # numbering them (1) and (2) put a distinction the analyst needs behind
        # a coin toss. Tags are worked out first, because once the doctor-only
        # file is tagged the plain one needs no suffix at all.
        tags = {id(r): _distinguisher(r, [o for o in group if o is not r])
                for r in group}
        untagged = [r for r in group if not tags[id(r)]]
        for i, r in enumerate(group, 1):
            stem, ext = os.path.splitext(r['new_name'])
            tag = tags[id(r)]
            if tag:
                r['new_name'] = '%s (%s)%s' % (stem, tag, ext)
            elif len(untagged) > 1:
                r['new_name'] = '%s (%d)%s' % (stem, i, ext)
            r['collision'] = True
            r['rename_why'] = (r.get('rename_why') or '') + \
                ' — COLLISION: %d documents proposed this same name, compare them' % len(group)
            # NOT review=True. A collision is about the NAME, and the numbering
            # above has already made it safe to file. Marking it as needing a
            # filing decision put it back in "Decide these", where choosing a
            # destination could never clear it — the operator picked a folder,
            # saved, and watched the same two documents reappear every time.
            # Collisions get their own callout instead.
    return rows


def build_rename_log(rows, client):
    """CSV: every rename, plus the content hash that ties it to the original."""
    out = ['old_name,new_name,sha256,reason,destination']
    for r in rows:
        if not r.get('new_name'):
            continue
        out.append(','.join('"%s"' % str(x or '').replace('"', "'") for x in
                            [r['file'], r['new_name'], r.get('sha'),
                             r.get('rename_why'), r.get('dest')]))
    return '\n'.join(out) + '\n'


def account_label(rows):
    """Human label for an account key, from the rows that belong to it."""
    if not rows:
        return 'this account'
    r = rows[0]
    bits = [x for x in [r.get('issuer'), ('x%s' % r['tail']) if r.get('tail') else None] if x]
    return ' · '.join(str(b) for b in bits) or 'account with no number read'


# ------------------------------------------------- internal clarification memo

def build_clarification(res, plan, client):
    """Internal writeup: what is missing, what is wrong, what needs a decision.

    Distinct from the client email. The email asks the client for documents; this
    tells the firm what a human has to resolve before the file can be finished.
    Contains no account digits and no PII.
    """
    results, cross = res['results'], res['cross']
    L = []
    L.append('NEEDS CLARIFICATION — %s' % client)
    L.append(datetime.date.today().isoformat())
    # Internal only. Last-four account references are allowed here because they
    # are how a human tells three Arvest series apart; a full account number is
    # never included. The CLIENT email is held to a stricter rule and is scanned
    # after generation to keep even last-fours out of it.
    L.append('Internal. Not for the client. May cite account last-four; never a full number.')
    L.append('')

    missing = [r for r in results if r['status'] == 'missing']
    mismatched = [r for r in results if r['status'] == 'mismatched']
    # Half-answered is still owed. Listing these only on screen and leaving them
    # out of the chase list is how a client ends up never being asked for the
    # personal half of something.
    partial = [r for r in results if r['status'] == 'partly satisfied']
    review = [p for p in plan if p['review']]

    # On a second or later pass, what CHANGED comes first. Restating the whole
    # position every week is how a chase list stops being read.
    led = res.get('ledger')
    if led and len(led.get('runs') or []) >= 1:
        try:
            import ledger as _l
            ns, out, since = _l.update_checklist(dict(led), results)
            lines = _l.summarise(led, res.get('new_hashes') or [], ns, out, since)
            if lines and 'First pass' not in lines[0]:
                L.append('SINCE LAST TIME')
                for line in lines:
                    L.append('  ' + line)
                L.append('')
        except Exception:
            pass

    # Only what is actually true of this client. The block used to print eight
    # counters unconditionally, so a clean run read as a wall of zeroes and the
    # two lines that mattered were lost among six that said nothing. A count of
    # none is not information; it is padding that trains people to skim.
    counts = [
        (len(missing),    'checklist item(s) still missing'),
        (len(partial),    'item(s) only half answered'),
        (len(mismatched), 'item(s) arrived but need your call'),
        (len(cross['gaps']), 'statement series with missing months'),
        (len(review),     'document(s) need a filing decision'),
        (len([p for p in plan if p.get('needs_confirmation')]),
                          'rename(s) need the period confirmed'),
        (len(cross.get('mislabeled') or []),
                          'filename(s) contradict their contents'),
    ]
    live = [(n, what) for n, what in counts if n]
    if live:
        L.append('WHAT NEEDS A HUMAN')
        for n, what in live:
            L.append('  %d %s' % (n, what))
    else:
        L.append('Nothing outstanding — every item is answered and every '
                 'document has a home.')
    L.append('')

    if partial:
        L.append('PARTLY PROVIDED — ask the client for the rest')
        for r in partial:
            L.append('  - [%s] %s' % (r['item'].get('section'), r['item'].get('label')))
            if r.get('note'):
                L.append('      %s' % r['note'])
        L.append('')

    if missing:
        L.append('NOT PROVIDED — ask the client')
        for r in missing:
            opt = ' (optional)' if r['item'].get('optional') else ''
            L.append('  - [%s] %s%s' % (r['item'].get('section'), r['item'].get('label'), opt))
            # A note written against a missing item is the most useful sentence
            # on the page — "she is sending this Monday" — and this section
            # printed labels only, so it reached the screen and nothing else.
            if r.get('note'):
                L.append('      %s' % r['note'])
        L.append('')

    if mismatched:
        L.append('WRONG SCOPE — arrived, but not usable as sent')
        for r in mismatched:
            L.append('  - [%s] %s' % (r['item'].get('section'), r['item'].get('label')))
            if r.get('note'):
                L.append('      %s' % r['note'])
        L.append('')

    if cross['gaps']:
        L.append('MISSING MONTHS')
        for g in cross['gaps']:
            # Label alone is not enough: three separate Arvest series all read as
            # "Bank statement", which left three identical, unactionable lines.
            who = [g.get('label')]
            if g.get('issuer'):
                who.append(str(g['issuer']))
            if g.get('account_tail'):
                who.append('x%s' % str(g['account_tail']).lstrip('xX'))
            if g.get('side'):
                who.append('(%s)' % g['side'])
            L.append('  - %s: missing %s' % (' · '.join(who), ', '.join(g.get('missing') or [])))
        L.append('')

    if cross.get('gap_fillers'):
        L.append('POSSIBLY ALREADY HERE UNDER A WRONG NAME — check before asking')
        for f in cross['gap_fillers']:
            L.append('  - %s of %s may be the file named like a %s'
                      % (f.get('month'), f.get('actual'), f.get('claimed')))
        L.append('')

    renamed = [p for p in plan if p.get('new_name')]
    if renamed:
        L.append('RENAMED BECAUSE THE NAME DID NOT MATCH THE CONTENTS')
        for p in sorted(renamed, key=lambda x: x['file']):
            L.append('  - %s' % p['file'])
            L.append('      now: %s' % p['new_name'])
            L.append('      why: %s' % p.get('rename_why'))
        L.append('')

    unconfirmed = [p for p in plan if p.get('needs_confirmation')]
    if unconfirmed:
        L.append('RENAMED BUT NEEDS CONFIRMING — the type is read from the contents,')
        L.append('the period is not. Open each one, confirm the year, and rename the')
        L.append('"(year TBD)" part.')
        for p in sorted(unconfirmed, key=lambda x: x['file']):
            L.append('  - %s  ->  %s' % (p['file'], p['new_name']))
        L.append('')

    collided = [p for p in plan if p.get('collision')]
    if collided:
        L.append('TWO OR MORE DOCUMENTS WANTED THE SAME NAME — compare them, they may')
        L.append('be duplicates or one may be misread.')
        for p in sorted(collided, key=lambda x: x['new_name'] or ''):
            L.append('  - %s  ->  %s' % (p['file'], p['new_name']))
        L.append('')

    if review:
        L.append('FILING DECISIONS NEEDED')
        grouped = {}
        for p in review:
            grouped.setdefault(p['why'], []).append(p['file'])
        for why, files in sorted(grouped.items(), key=lambda x: -len(x[1])):
            L.append('  %s (%d)' % (why, len(files)))
            for f in sorted(files):
                L.append('      - %s' % f)
        L.append('')

    # This used to tell the reader to "export decisions.json and re-run with
    # --decisions", which was true of the command-line tool and has not been
    # true since the app grew a Save button. Instructions that describe a
    # workflow nobody uses are worse than none: they send someone looking for a
    # flag that isn't there.
    L.append('This writeup is a snapshot of the run above. Decisions you save on '
             'the Review page')
    L.append('do not change it until the audit runs again — press Run the audit, '
             'or Build File Tree,')
    L.append('which re-runs it for you.')
    return '\n'.join(L)


def write_clarification_docx(memo, client, path):
    """The writeup as a Word file. Plain .txt opens in a bare editor on a Mac and
    looks like a log file; this is something you can hand to someone."""
    from docx import Document
    from docx.shared import Pt, RGBColor
    NAVY = RGBColor(0x1B, 0x2A, 0x41)
    ORANGE = RGBColor(0xE8, 0x79, 0x2B)

    d = Document()
    lines = memo.split('\n')
    title = d.add_paragraph()
    r = title.add_run('Needs Clarification — %s' % client)
    r.bold = True; r.font.size = Pt(19); r.font.color.rgb = NAVY
    title.paragraph_format.space_after = Pt(2)

    for raw in lines[1:]:
        line = raw.rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        # ALL-CAPS lines are section headings in the memo
        letters = [c for c in stripped if c.isalpha()]
        is_head = letters and all(c.isupper() for c in letters) and not line.startswith('  ')
        p = d.add_paragraph()
        if is_head:
            run = p.add_run(stripped)
            run.bold = True; run.font.size = Pt(12); run.font.color.rgb = ORANGE
            p.paragraph_format.space_before = Pt(13); p.paragraph_format.space_after = Pt(3)
        else:
            indent = len(line) - len(line.lstrip())
            run = p.add_run(stripped.lstrip('- '))
            run.font.size = Pt(10.5)
            if stripped.startswith('-'):
                p.style = d.styles['List Bullet']
            p.paragraph_format.left_indent = Pt(11 * max(0, indent // 2))
            p.paragraph_format.space_after = Pt(1)
    d.save(path)
    return path


# ------------------------------------------------------------------ rendering


# --------------------------------------------------------------------------
# brand
# --------------------------------------------------------------------------
# The real Four Quadrants mark, vendored into the repo rather than read off the
# Analysis share. The share is not always mounted — on the coworker's machine it
# may never be — and a header whose logo silently vanishes looks like a broken
# page. Inlined as a data URI because the page has to survive being saved to
# disk and emailed, where a relative <img src> points at nothing, and because
# the page's own CSP allows data: images but no network of any kind.
LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'assets', 'fq_logo.png')
LOGO_H = 34                      # rendered height in the header, in px
_LOGO_CACHE = {}


def logo_data_uri(height=LOGO_H):
    """The mark as a small data: URI, or None if it cannot be produced.

    Downscaled first. The source art is 4819px wide — inlining it whole would
    add roughly 280KB of base64 to every review page for something displayed at
    34px tall.
    """
    if height in _LOGO_CACHE:
        return _LOGO_CACHE[height]
    uri = None
    try:
        from PIL import Image
        im = Image.open(LOGO_PATH).convert('RGBA')
        w = max(1, int(im.width * (height * 2.0) / im.height))     # 2x for retina
        im = im.resize((w, height * 2), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format='PNG', optimize=True)
        uri = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
    except Exception:
        uri = None               # a missing logo must never break the audit
    _LOGO_CACHE[height] = uri
    return uri


CSS = """
/* Four Quadrants palette. The orange and slate are sampled straight off the
   firm's logo artwork rather than eyeballed, so the header art and the chrome
   around it are the same colours rather than nearly the same. Navy and the two
   blues are the supporting range. */
:root{
  --fq-orange:#F08418;  --fq-orange-dk:#CE6E0D;
  --fq-slate:#607884;   --fq-slate-lt:#909CA8;
  --fq-navy:#16324F;    --fq-navy-lt:#22456A;
  --fq-baby:#A9CFE5;    --fq-baby-pale:#EAF3F9;
  --fq-ink:#1B2A41;     --fq-line:#E4E0D8;
}
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
     color:#1B2A41;background:#F7F6F3}
header{background:var(--fq-navy);color:#fff;padding:20px 30px;position:sticky;top:0;z-index:20}
header h1{margin:0;font-size:20px}
header .sub{opacity:.72;font-size:13px;margin-top:3px}
.bar{display:flex;align-items:center;gap:10px;margin-top:12px;flex-wrap:wrap}
button{font:inherit;font-size:13px;padding:7px 13px;border-radius:7px;border:1px solid #3A4A62;
       background:#2A3A52;color:#fff;cursor:pointer}
button:hover{background:#35486380}
button.primary{background:var(--fq-orange);border-color:var(--fq-orange)}
button.primary:hover{background:var(--fq-orange-dk)}
button:disabled{opacity:.45;cursor:default}
#undecided{font-size:13px;opacity:.85}
.wrap{max-width:1240px;margin:0 auto;padding:0 30px 80px}
.tiles{display:flex;flex-wrap:wrap;gap:11px;margin:20px 0 6px}
.tile{flex:1 1 122px;background:#fff;border:1px solid #E4E0D8;border-radius:9px;padding:12px 14px}
.tile b{display:block;font-size:24px;line-height:1.1}
.tile span{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:#6C7480}
.tile.warn b{color:#C0392B} .tile.ok b{color:#1E8449}
h2{font-size:16px;margin:32px 0 4px;padding-bottom:7px;border-bottom:2px solid var(--fq-orange)}
h2 .n{color:#6C7480;font-weight:400;font-size:13px;margin-left:7px}
.hint{color:#6C7480;font-size:13px;margin:6px 0 12px}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #E4E0D8;border-radius:9px}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:#6C7480;
   padding:9px 10px;border-bottom:1px solid #E4E0D8;background:#FBFAF8}
td{padding:7px 10px;border-bottom:1px solid #F0EDE7;vertical-align:top;font-size:13.5px}
tr:last-child td{border-bottom:none}
tr.review{background:#FFF8F2} tr.done{background:#F2FAF4}
code{font:12.5px ui-monospace,Menlo,monospace;background:#F2F0EB;padding:1px 5px;border-radius:4px}
.pill{display:inline-block;font-size:11px;padding:2px 8px;border-radius:20px;font-weight:600}
.p-sat{background:#E4F5E9;color:#1E6B38} .p-mis{background:#FDECEA;color:#A5342A}
.p-mism{background:#FFF3E0;color:#8A5218} .p-rev{background:#FFE9DC;color:#9C4A16}
/* Answered, not outstanding — grey so it never reads as a chase. */
.p-na{background:#ECEFF1;color:#546E7A}
/* Half-answered. Amber rather than green: something arrived, but the
   client is still owed a chase for the rest. */
.p-part{background:#FFF3E0;color:#8A5218;font-weight:600}
select,input[type=text]{font:inherit;font-size:13px;padding:5px 7px;border:1px solid #D8D4CA;
       border-radius:6px;background:#fff;max-width:100%}
select{min-width:210px}
.filter{width:100%;max-width:340px;padding:8px 11px;border:1px solid #D8D4CA;border-radius:7px;
        font:inherit;font-size:13.5px;margin-bottom:11px}
ul{margin:8px 0 0;padding-left:20px} li{margin:3px 0}
details.pii{margin-top:14px;border:2px solid #C0392B;border-radius:9px;background:#fff;overflow:hidden}
details.pii>summary{cursor:pointer;padding:13px 16px;font-weight:700;color:#C0392B;background:#FDECEA}
.piibody{padding:4px 16px 16px}
.leakfile{margin-top:16px;font-weight:700;font-size:14px}
.ctx{font:12px ui-monospace,Menlo,monospace;color:#5A6270;background:#F7F6F3;padding:5px 8px;
     border-radius:5px;margin-top:3px;word-break:break-all}
.banner{background:#EAF3EC;border:1px solid #BEDCC6;border-left:4px solid #1E8449;
     border-radius:8px;padding:11px 14px;margin:18px 0 0;font-size:13px;color:#274B33}
.banner.bad{background:#FDECEA;border-color:#EFC3BC;border-left-color:#C0392B;color:#7E2A20}
.warnsrc{font-size:11.5px;color:#9C4A16;background:#FFF3E0;padding:4px 8px;
     border-radius:5px;margin-top:6px;display:inline-block}
details.prev{margin-top:5px}
details.prev>summary{cursor:pointer;font-size:12px;color:#8A5218;font-weight:600;
     background:#FFF3E0;display:inline-block;padding:2px 9px;border-radius:12px}
details.prev img{display:block;margin-top:8px;max-width:100%;border:1px solid #D8D4CA;
     border-radius:6px;background:#fff}
details.prev .snip{font:11.5px/1.5 ui-monospace,Menlo,monospace;color:#5A6270;
     background:#F7F6F3;padding:7px 9px;border-radius:6px;margin-top:7px;max-height:150px;overflow:auto}

.alldone{background:#EAF3EC;border:1px solid #BEDCC6;border-left:4px solid #1E8449;
  border-radius:10px;padding:18px 20px;font-size:15px;color:#274B33;margin-top:22px}
.shortcut{background:#FFF8F2;border:1px solid #F0D9B5;border-radius:10px;padding:16px 18px;margin:16px 0 22px}
.acctrow{display:flex;align-items:center;gap:12px;padding:7px 0;border-top:1px solid #F3E6D6}
.acctrow:first-of-type{border-top:0}
.acctrow .who{font-weight:600;min-width:190px}
.acctrow .cnt{color:#9C4A16;font-size:12.5px;min-width:66px}
.qcard{display:flex;gap:16px;background:#fff;border:1px solid #E4E0D8;border-radius:12px;
  padding:18px 20px;margin-bottom:14px}
.qcard.done{border-color:#BEDCC6;background:#FBFEFC}
#plantable{table-layout:fixed;width:100%}
#plantable td{word-break:break-word;vertical-align:top}
#plantable td:nth-child(5){font-size:12px;color:#6b7280}
button.openfile{margin-top:8px;font-size:13px;padding:5px 11px;border-radius:7px;
      border:1px solid #C9C3B6;background:#fff;color:#1B2A41;cursor:pointer}
button.openfile:hover{background:#F4F1EA;color:#1B2A41}
/* Preview overlay. The image is fetched live from the app and never
   written into this file, so the page stays safe to save or send. */
#pvwrap{position:fixed;inset:0;background:rgba(20,24,31,.82);z-index:9999;
      display:none;align-items:center;justify-content:center;padding:28px}
#pvwrap.on{display:flex}
#pvbox{background:#fff;border-radius:12px;max-width:94vw;max-height:94vh;
      display:flex;flex-direction:column;overflow:hidden}
#pvhead{display:flex;gap:14px;align-items:center;padding:11px 16px;
      border-bottom:1px solid #E4E0D8;font-size:14px;font-weight:600;color:#1B2A41}
#pvhead button{margin-left:auto;border:1px solid #C9C3B6;background:#fff;
      color:#1B2A41;border-radius:7px;padding:4px 12px;cursor:pointer}
#pvimg{max-width:90vw;max-height:78vh;object-fit:contain;display:block}
#pvmsg{padding:26px;color:#6b7280;font-size:14px}
/* A workbook, shown as a workbook. Sticky header row and first column so the
   labels stay put while you scroll a wide schedule — the whole reason for
   showing a grid rather than a paragraph is being able to tell which number
   sits under which heading. */
#pvsheet{padding:0 0 6px;max-width:92vw;max-height:78vh;overflow:auto}
#pvtabs{display:flex;gap:6px;padding:9px 14px 0;flex-wrap:wrap;
      position:sticky;top:0;background:#fff;z-index:3}
#pvtabs button{font:inherit;font-size:12px;padding:4px 11px;border-radius:14px;
      border:1px solid #D8D4CA;background:#fff;color:#5A6270;cursor:pointer}
#pvtabs button.on{background:var(--fq-navy);border-color:var(--fq-navy);color:#fff;font-weight:600}
table.xlsheet{border-collapse:separate;border-spacing:0;font-size:12.5px;margin:10px 14px 0;
      background:#fff;border:1px solid #C9D2DA;width:auto}
table.xlsheet td{border-right:1px solid #E9EDF1;border-bottom:1px solid #E9EDF1;padding:3px 8px;
      white-space:nowrap;max-width:210px;overflow:hidden;text-overflow:ellipsis;vertical-align:top}
table.xlsheet td.num{text-align:right;font-variant-numeric:tabular-nums}
/* Column letters and row numbers, greyed like a spreadsheet's own gutters. */
table.xlsheet td.addr{background:#EDF1F4;color:#6C7480;font-size:11px;text-align:center;
      font-weight:600;padding:2px 7px;position:sticky;left:0;z-index:2}
table.xlsheet tr.addr td{position:sticky;top:0;left:auto;z-index:3}
table.xlsheet tr.addr td.corner{left:0;z-index:5}
/* The real heading row, wherever it turned out to be. Client workbooks open
   with a title and a line of instructions far more often than not. */
table.xlsheet tr.hdr td{background:#DCE7EF;color:var(--fq-navy);font-weight:600;
      position:sticky;top:22px;z-index:1}
table.xlsheet tr.hdr td.addr{z-index:4}
.pvtrunc{margin:8px 14px 0;font-size:12px;color:#9C4A16;background:#FFF3E0;
      padding:4px 9px;border-radius:5px;display:inline-block}
#pvtext{margin:0;padding:18px 20px;max-width:88vw;max-height:78vh;overflow:auto;
      font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;color:#2b3442;
      white-space:pre-wrap;word-break:break-word}
.qnum{flex:0 0 30px;height:30px;border-radius:50%;background:var(--fq-slate);color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600}
.qcard.done .qnum{background:#1E8449}
.qbody{flex:1;min-width:0}
.qname{font-size:16px;font-weight:600;word-break:break-word}
.qmeta{color:#6C7480;font-size:13px;margin-top:2px}
.qwhy{color:#9C4A16;background:#FFF3E0;display:inline-block;font-size:12px;
  padding:2px 9px;border-radius:12px;margin-top:8px}
.qpick{display:flex;gap:10px;align-items:center;margin-top:14px;flex-wrap:wrap}
.qpick label{margin:0;flex:0 0 auto}
.qpick select{flex:1;min-width:230px;font-size:14px;padding:9px 10px}
.qpick input{flex:1;min-width:170px}
details.panel{background:#fff;border:1px solid #E4E0D8;border-radius:10px;margin:14px 0;overflow:hidden}
details.panel>summary{cursor:pointer;padding:15px 18px;font-weight:600;font-size:15px;
  list-style:none;display:flex;align-items:center}
details.panel>summary::-webkit-details-marker{display:none}
details.panel>summary:before{content:'▸';margin-right:10px;color:#9aa2ad}
details.panel[open]>summary:before{content:'▾'}
details.panel>summary .n{margin-left:auto;font-weight:400;color:#6C7480;font-size:13px}
.pbody{padding:4px 18px 18px}

/* ---- logo ----------------------------------------------------------- */
.hlogo{height:34px;width:auto;display:block;flex-shrink:0}
.hbrand{display:flex;align-items:center;gap:16px;min-width:0}
.hrule{width:1px;height:30px;background:rgba(169,207,229,.35);flex-shrink:0}

/* ---- checklist summary ---------------------------------------------- */
/* The first thing on the page. What the client owes us, whether it turned up,
   and which document answered it — readable without opening anything. */
.sum{background:#fff;border:1px solid var(--fq-line);border-left:4px solid var(--fq-slate);
  border-radius:11px;padding:18px 20px;margin:20px 0 6px}
.sum h3{margin:0 0 3px;font-size:15.5px;color:var(--fq-navy)}
.sumsub{color:#6C7480;font-size:12.5px;margin-bottom:14px}
.sumgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:9px}
.ck{display:flex;gap:10px;padding:9px 11px;border-radius:9px;background:var(--fq-baby-pale);
  border:1px solid #DCE9F2;align-items:flex-start}
.ck.bad{background:#FDECEA;border-color:#F3CFC9}
.ck.part{background:#FFF6EA;border-color:#F5DCB8}
.ck.na{background:#F2F4F5;border-color:#E2E6E8}
.ckmark{flex:0 0 19px;height:19px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-size:12px;font-weight:700;color:#fff;margin-top:1px}
.ck .ckmark{background:#2E8B57}
.ck.bad .ckmark{background:#C0392B}
.ck.part .ckmark{background:var(--fq-orange)}
.ck.na .ckmark{background:var(--fq-slate-lt)}
.ckbody{min-width:0;flex:1}
.cklab{font-size:13px;font-weight:600;line-height:1.35;color:var(--fq-ink)}
.cknote{font-size:12px;color:#9C4A16;margin-top:3px}
.ck.bad .cknote{color:#A5342A}
.ckdocs{margin-top:5px;display:flex;flex-wrap:wrap;gap:5px}
button.ckdoc{font-size:11.5px;margin-top:0;background:#fff;border:1px solid #CFDEE9;color:var(--fq-navy);
  border-radius:12px;padding:2px 9px;cursor:pointer;max-width:100%;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;font-family:inherit}
button.ckdoc:hover{background:var(--fq-baby);border-color:var(--fq-slate)}
.ckmore{font-size:11.5px;color:#6C7480;align-self:center}
.ckover{margin-top:6px}
.ckover>summary{cursor:pointer;font-size:11px;color:#8A94A0;list-style:none;
  display:inline-block;padding:1px 0;border-bottom:1px dotted #C7CDD4}
.ckover>summary::-webkit-details-marker{display:none}
.ckover>summary:hover{color:var(--fq-navy)}
/* ckbar, not bar. A `.bar` rule already exists in this stylesheet — dead, but
   still matching — and its align-items:center stopped the segments stretching,
   so they had no height and the whole thing rendered as an empty grey track.
   Same failure as the preview table that inherited the page's own .grid and
   collapsed into two columns. Prefix anything added to a shared stylesheet. */
.ckbar{display:flex;align-items:stretch;gap:0;height:11px;border-radius:6px;
       overflow:hidden;margin:10px 0 7px;background:var(--fq-line)}
.ckbar span{display:block;height:100%}
.bok{background:#1D9E75} .bcall{background:var(--fq-orange)} .bmiss{background:#C8CDD3}
.ckbarkey{display:flex;gap:16px;font-size:12px;color:var(--fq-slate);margin-bottom:10px}
.ckbarkey i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px}
.kok{background:#1D9E75} .kcall{background:var(--fq-orange)} .kmiss{background:#C8CDD3}
/* A group heading inside the checklist, so the three jobs read as three jobs. */
.ckgroup{margin-top:14px}
.ckgroup:first-of-type{margin-top:4px}
.ckgrp{font-size:13px;font-weight:700;letter-spacing:.3px;color:var(--fq-navy);
       padding:7px 0 6px;border-bottom:2px solid var(--fq-baby);cursor:pointer;
       list-style:none;display:flex;align-items:center;gap:8px;user-select:none}
.ckgrp::-webkit-details-marker{display:none}
/* A caret drawn in CSS, so the heading reads as something you can open before
   anyone clicks it. Rotates when the group opens. */
.ckgrp::before{content:'';width:0;height:0;border-left:5px solid var(--fq-slate);
       border-top:4px solid transparent;border-bottom:4px solid transparent;
       transition:transform .12s}
.ckgroup[open]>.ckgrp::before{transform:rotate(90deg)}
.ckgn{margin-left:auto;font-weight:600;font-size:12px;color:var(--fq-slate);
      background:var(--fq-baby-pale);border-radius:9px;padding:1px 9px}
.ckgroup>.sumgrid{margin-top:9px}
.sumhead{font-size:19px;font-weight:600;color:var(--fq-navy)}
.donutrow{display:flex;align-items:center;gap:18px;margin:14px 0 8px;flex-wrap:wrap}
.donut{width:92px;height:92px;border-radius:50%;flex:0 0 auto;position:relative;
  background:conic-gradient(#1D9E75 calc(var(--pct)*1%),#E4E0D8 0)}
.donutmid{position:absolute;inset:11px;border-radius:50%;background:#fff;
  display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1.1}
.donutmid b{font-size:21px;color:var(--fq-navy)}
.donutmid span{font-size:10px;color:var(--fq-slate);text-transform:uppercase;letter-spacing:.5px}
.tiles{display:flex;flex-wrap:wrap;gap:4px;flex:1 1 240px;align-content:center}
.tiles i{width:17px;height:17px;border-radius:4px;display:block;cursor:default}
.tok{background:#1D9E75} .tcall{background:var(--fq-orange)} .tmiss{background:#D5D9DE}
.tiles i:hover{outline:2px solid var(--fq-navy);outline-offset:1px}
.md{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.2fr);gap:14px;margin-top:14px}
.mdlist{max-height:430px;overflow:auto;border:1px solid #EFEBE3;border-radius:10px;
  background:#fff;padding:4px}
button.mdrow{display:flex;align-items:flex-start;gap:9px;width:100%;text-align:left;
  background:none;border:0;border-radius:7px;padding:7px 9px;font-size:13px;
  color:var(--fq-ink);cursor:pointer;margin:0;line-height:1.35}
button.mdrow:hover{background:var(--fq-baby-pale)}
button.mdrow.on{background:var(--fq-baby-pale);box-shadow:inset 3px 0 0 var(--fq-orange);
  font-weight:600;color:var(--fq-navy)}
button.mdrow i{flex:0 0 auto;width:9px;height:9px;border-radius:3px;margin-top:5px}
.mddetail{background:var(--fq-navy);border-radius:10px;padding:15px 17px;
  align-self:start;color:#E8EEF4}
.mddetail .cklab{color:#fff;font-size:14px;line-height:1.4}
.mddetail .ckwhy{color:#AFC4D6}
.mddetail button.ckdoc{background:#20406180;border-color:#3C5F82;color:#DCE8F2}
.mddetail button.ckdoc:hover{background:#2B527A;border-color:#6E93B5}
.mddetail .ckdt{color:#9DB4C9}
.mddetail button.ckmore{background:#20406180;border-color:#3C5F82;color:#DCE8F2}
.mddetail select,.mddetail input{background:#fff;border-color:#3C5F82}
.mddetail .ckstale{background:var(--fq-orange)}
.mdwhat{font-size:10.5px;letter-spacing:.7px;text-transform:uppercase;
  color:#7E9CB8;margin-bottom:8px}
.mdpane.hide{display:none}
.mdpane .ckline{background:none;padding:0;margin:0}
@media (max-width:620px){.md{grid-template-columns:1fr}.mdlist{max-height:220px}}
.block{border-radius:12px;padding:14px 16px;margin:12px 0}
.block.judge{background:#FDF3E4;border:1px solid #F3D9AE}
.block.gone{background:#F7F5F0;border:1px solid #E7E2D8}
.block.ok{background:#EAF5EE;border:1px solid #BFE0CC}
.blocktitle{font-weight:600;font-size:15px;color:var(--fq-ink)}
.block.judge .blocktitle{color:#8A5A12}
.blocksub{font-size:13px;color:var(--fq-slate);margin:2px 0 12px}
.ckline{background:#fff;border-radius:9px;padding:10px 12px;margin-bottom:8px}
.ckline:last-child{margin-bottom:0}
.ckline.quiet{background:transparent;padding:5px 2px;margin-bottom:0;
  border-bottom:1px solid #F1EDE5}
.ckline.quiet .cklab{font-size:13.5px;color:var(--fq-slate)}
.ckwhy{font-size:12.5px;color:var(--fq-slate);margin-top:3px}
.ckdt{margin-left:6px;color:#8A9099;font-weight:400}
.ckx{display:none}
button.ckmore{font-size:11.5px;margin-top:0;background:var(--fq-baby-pale);border:1px dashed #9FC2DA;color:var(--fq-navy);border-radius:7px;padding:3px 9px;cursor:pointer}
button.ckmore:hover{background:var(--fq-baby)}
.morerow{border-top:1px solid #EDE8DF;padding:11px 2px;font-size:13.5px;
  color:var(--fq-slate);cursor:pointer}
.morerow:hover{color:var(--fq-navy)}
.morerow>summary{list-style:none;cursor:pointer}
.morerow>summary::-webkit-details-marker{display:none}
.chev{display:inline-block;width:0;height:0;margin-right:8px;
  border-left:5px solid currentColor;border-top:4px solid transparent;
  border-bottom:4px solid transparent}
details.morerow[open] .chev{transform:rotate(90deg)}
.settledlist{margin-top:8px}
.ckpick{margin-top:7px;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.ckpick select{font-size:12px;padding:3px 6px;min-width:0;max-width:210px}
.ckpick input{font-size:12px;padding:3px 7px;flex:1;min-width:130px}
.ckpick label{font-size:11px;color:#6C7480;text-transform:uppercase;letter-spacing:.5px}
.cksaid{font-size:11.5px;line-height:1.45;color:#37506B;background:#fff;
  border-left:3px solid var(--fq-baby);border-radius:0;padding:5px 9px;margin-top:5px}
.cksaid b{color:var(--fq-navy)}
.saidrow{display:flex;gap:10px;padding:9px 0;border-top:1px solid #F0EDE7}
.saidrow:first-of-type{border-top:0}
.saidwho{flex:0 0 130px;font-weight:600;font-size:12.5px;color:var(--fq-navy)}
.saidwho span{display:block;font-weight:400;font-size:11px;color:#8A94A0}
.saidtext{flex:1;min-width:0;font-size:13px;white-space:pre-wrap;word-break:break-word}
.ckstale{font-size:11px;background:var(--fq-orange);color:#fff;border-radius:10px;
  padding:1px 8px;margin-left:6px;vertical-align:1px;font-weight:600}
.ckhuman{font-size:11px;background:var(--fq-navy);color:#fff;border-radius:10px;
  padding:1px 8px;margin-left:6px;vertical-align:1px}

/* ---- shell ---------------------------------------------------------- */
body{background:#FAF8F5}
header{background:linear-gradient(180deg,var(--fq-navy) 0%,var(--fq-navy-lt) 100%);color:#fff;
  padding:0;position:sticky;top:0;z-index:30;box-shadow:0 1px 0 rgba(0,0,0,.15)}
.hrow{max-width:1180px;margin:0 auto;padding:16px 26px;display:flex;align-items:center;gap:20px}
.hleft{min-width:0}
header h1{margin:0;font-size:20px;font-weight:600;letter-spacing:-.2px}
header .sub{opacity:.65;font-size:12.5px;margin-top:2px}
.hright{margin-left:auto;display:flex;align-items:center;gap:9px;flex-shrink:0}
#undecided{font-size:13px;opacity:.85;margin-right:4px;white-space:nowrap}
header button{background:#2A4C74;border:1px solid #3B628E;color:#e8eef6;font:inherit;
  font-size:13px;padding:8px 14px;border-radius:8px;cursor:pointer}
header button:hover{background:#35618F}
header button.primary{background:#E8792B;border-color:#E8792B;color:#fff;font-weight:600;
  font-size:14px;padding:9px 18px}
header button.primary:hover{background:#d06a22}
header button.primary:disabled{opacity:.45;cursor:default}
.progwrap{height:3px;background:rgba(255,255,255,.14)}
.prog{height:100%;background:#E8792B;width:0;transition:width .3s}

/* ---- two columns ----------------------------------------------------- */
.wrap{max-width:1180px;margin:0 auto;padding:24px 26px 70px}
.grid{display:grid;grid-template-columns:minmax(0,1fr) 250px;gap:26px;align-items:start}
.main{min-width:0}
.rail{position:sticky;top:96px;display:flex;flex-direction:column;gap:14px}
.railcard{background:#fff;border:1px solid #EAE5DC;border-radius:12px;padding:14px 16px;
  overflow:visible}
/* A count you can interrogate. Hovering names what it is counting, to the left
   so the panel opens over the page rather than off the edge of the window. */
.stat[data-tip]{position:relative;cursor:help}
.stat[data-tip] b{border-bottom:1px dotted #B9C2CC}
.stat[data-tip]:hover::after{
  content:attr(data-tip);white-space:pre-wrap;position:absolute;right:calc(100% + 12px);
  top:-6px;width:290px;background:var(--fq-navy);color:#fff;font-size:12px;line-height:1.45;
  padding:9px 11px;border-radius:8px;z-index:60;box-shadow:0 6px 18px rgba(20,30,45,.25);
  pointer-events:none}
@media(max-width:1100px){
  /* The rail sits inline on a narrow window, so a tooltip to its left would
     hang off the page. Drop it underneath instead. */
  .stat[data-tip]:hover::after{right:auto;left:0;top:calc(100% + 6px)}
}
.railcard h3{margin:0 0 10px;font-size:11px;text-transform:uppercase;letter-spacing:.7px;
  color:#8A94A0;font-weight:600}
.stat{display:flex;align-items:baseline;gap:9px;padding:6px 0;border-top:1px solid #F4F1EB}
.stat:first-of-type{border-top:0}
.stat b{font-size:19px;line-height:1;min-width:30px;font-variant-numeric:tabular-nums}
.stat span{font-size:13px;color:#6C7480}
.stat.warn b{color:#C0392B}
.stat.ok b{color:#1E8449}
.tips{background:#FFF8F2;border-color:#F0D9B5}
.tips h3{color:#9C4A16}
.tips ol{margin:0;padding-left:18px;font-size:13px;line-height:1.7;color:#5C4630}
@media (max-width:900px){
  .grid{grid-template-columns:1fr}
  .rail{position:static;flex-direction:row;flex-wrap:wrap}
  .railcard{flex:1 1 240px}
}
h2{font-size:18px;margin:26px 0 4px;padding-bottom:0;border-bottom:0;font-weight:600}
h2 .n{color:#8A94A0;font-weight:400;font-size:13px;margin-left:8px}

.built{font-size:11.5px;color:#8C93A1;background:#F2F4F7;border-radius:8px;
  padding:7px 12px;margin:0 0 16px;display:inline-block}
.collide{background:#FFF6E8;border:1px solid #F0DCC0;border-radius:10px;
  padding:14px 16px;margin:18px 0 4px;font-size:13.5px;color:#6B4A22}
.collide code{background:#F7EEDF;color:#6B4A22}
.collide li{margin:4px 0}
pre.memo{background:#fff;border:1px solid #E4E0D8;border-radius:9px;padding:15px;
     font:12.5px/1.6 ui-monospace,Menlo,monospace;white-space:pre-wrap;max-height:420px;overflow:auto}
footer{color:#6C7480;font-size:12px;padding:24px 30px;text-align:center}
.grp{background:#FBFAF8;font-weight:600;font-size:12.5px}
"""

JS = r"""
// Two registers. FILES is a call about one document; ACCTS is a standing rule
// about an account, which is what stops you answering the same question every
// quarter. Exported together as {files, accounts}.
var __c = window.__CARRIED__ || {};
var DEC   = (__c.files || (__c.accounts ? {} : __c)) || {};
var ACCTS = __c.accounts || {};
var ITEMS = __c.items || {};

function settled(row){
  var d = DEC[row.dataset.sha];
  if(d && d.dest) return true;
  var ak = row.dataset.akey;
  return !!(ak && ACCTS[ak] && ACCTS[ak].dest);
}

function setUndecided(){
  var rows = document.querySelectorAll('[data-sha][data-review="1"]');
  var n = 0;
  rows.forEach(function(r){
    var ok = settled(r);
    r.classList.toggle('done', ok);
    if(!ok) n++;
  });
  var el = document.getElementById('undecided');
  var total = rows.length, done = total - n;
  if(el) el.textContent = total ? (n ? (done + ' of ' + total + ' decided') : 'all ' + total + ' decided') : '';
  var bar = document.getElementById('prog');
  if(bar) bar.style.width = total ? (100 * done / total) + '%' : '0';
  var btn = document.getElementById('dlDec');
  if(btn) btn.disabled = Object.keys(DEC).length === 0 && Object.keys(ACCTS).length === 0
                         && Object.keys(ITEMS).length === 0;
}

function record(sha, dest, note, row){
  setTimeout(autosave, 0);
  if(!dest){ delete DEC[sha]; }
  else { DEC[sha] = {dest:dest, note:note||''}; }
  if(row){
    row.classList.toggle('done', !!dest);
    var c = row.querySelector('.destnow');
    if(c) c.textContent = dest || row.dataset.suggested;
  }
  setUndecided();
}

function wire(){
  document.querySelectorAll('[data-sha]').forEach(function(row){
    var sel = row.querySelector('select.dest');
    var note = row.querySelector('input.note');
    if(!sel) return;
    var carried = DEC[row.dataset.sha];
    if(carried){
      // put the carried value in the list if it is not already there
      if(!Array.prototype.some.call(sel.options, function(o){return o.value===carried.dest;})){
        var o=document.createElement('option'); o.value=carried.dest; o.textContent=carried.dest; sel.appendChild(o);
      }
      sel.value = carried.dest;
      if(note) note.value = carried.note || '';
      row.classList.add('done');
    }
    sel.addEventListener('change', function(){ record(row.dataset.sha, sel.value, note?note.value:'', row); });
    if(note) note.addEventListener('input', function(){
      if(sel.value) record(row.dataset.sha, sel.value, note.value, row);
    });
  });

  // Bulk: apply one destination to every undecided row sharing a reason.
  // Open the original in whatever app the Mac uses for it. Served by the local
  // app, so this only ever reaches files inside the chosen root.
  // Preview in place. Opening the document in another app took you out of the
  // review entirely, which is the wrong shape for "glance at this, then keep
  // going down the list".
  var pv = document.createElement('div');
  pv.id = 'pvwrap';
  pv.innerHTML = '<div id="pvbox"><div id="pvhead"><span id="pvname"></span>'
               + '<button id="pvclose">Close</button></div>'
               + '<div id="pvbody"><div id="pvmsg">Loading…</div></div></div>';
  document.body.appendChild(pv);

  function hide(){ pv.classList.remove('on');
                   document.getElementById('pvbody').innerHTML='<div id="pvmsg">Loading…</div>'; }
  pv.addEventListener('click', function(e){ if(e.target===pv) hide(); });
  document.getElementById('pvclose').addEventListener('click', hide);
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') hide(); });


  function textFallback(body, b){
    fetch('/api/preview?path=' + encodeURIComponent(b.dataset.path)
          + '&folder=' + encodeURIComponent(window.__FQ_FOLDER__||''))
      .then(function(r){ return (r.status === 423 || r.status === 415) ? r.json() : null; })
      .then(function(d){
        if(d && d.final){ body.innerHTML = '<div id="pvmsg">' + d.error + '</div>'; return; }
        plainText(body, b);
      })
      .catch(function(){ plainText(body, b); });
  }

  function plainText(body, b){
    fetch('/api/previewtext?path=' + encodeURIComponent(b.dataset.path)
          + '&folder=' + encodeURIComponent(window.__FQ_FOLDER__||''))
      .then(function(r){ return r.json(); })
      .then(function(d){
        var pre = document.createElement('pre');
        pre.id = 'pvtext';
        pre.textContent = d.text || d.error || 'Nothing to show.';
        body.innerHTML=''; body.appendChild(pre);
      })
      .catch(function(){ body.innerHTML='<div id="pvmsg">Nothing to show for this file.</div>'; });
  }

  var NUMRE = /^[-+(]?[$]?[\d,]+(\.\d+)?[)%]?$/;
  function showSheets(body, sheets){
    body.innerHTML = '';
    var tabs = document.createElement('div'); tabs.id='pvtabs';
    var host = document.createElement('div'); host.id='pvsheet';
    if(sheets.length > 1) body.appendChild(tabs);
    body.appendChild(host);

    function draw(i){
      var sh = sheets[i];
      host.innerHTML = '';
      var t = document.createElement('table'); t.className='xlsheet';

      // Column letters across the top, row numbers down the side — the same
      // reference the file uses. Without them a reviewer comparing the panel
      // against the real workbook has nothing to line the two up by.
      var head = document.createElement('tr'); head.className='addr';
      head.appendChild(cell('td', '', 'corner'));
      (sh.cols || []).forEach(function(L){ head.appendChild(cell('td', L, 'addr')); });
      t.appendChild(head);

      sh.rows.forEach(function(row, ri){
        var tr = document.createElement('tr');
        if(ri === sh.header) tr.className = 'hdr';
        tr.appendChild(cell('td', String(ri+1), 'addr'));
        row.forEach(function(c){
          var td = cell('td', c, (c && NUMRE.test(c.trim())) ? 'num' : '');
          if(c && c.length > 22) td.title = c;
          tr.appendChild(td);
        });
        t.appendChild(tr);
      });
      host.appendChild(t);
      if(sh.truncated){
        var w = document.createElement('div'); w.className='pvtrunc';
        w.textContent = 'Showing the first ' + sh.rows.length + ' rows — open the file for the rest.';
        host.appendChild(w);
      }
      Array.prototype.forEach.call(tabs.children, function(btn, j){
        btn.classList.toggle('on', j===i);
      });
    }
    function cell(tag, text, cls){
      var e = document.createElement(tag);
      e.textContent = text;
      if(cls) e.className = cls;
      return e;
    }
    sheets.forEach(function(sh, i){
      var btn = document.createElement('button');
      btn.textContent = sh.name;
      btn.addEventListener('click', function(){ draw(i); });
      tabs.appendChild(btn);
    });
    draw(0);
  }

  document.querySelectorAll('button.openfile').forEach(function(b){
    b.addEventListener('click', function(){
      current = b.dataset.path;
      document.getElementById('pvname').textContent = b.dataset.name || '';
      pv.classList.add('on');
      var body = document.getElementById('pvbody');
      var img = new Image();
      img.id = 'pvimg';
      img.onload  = function(){ body.innerHTML=''; body.appendChild(img); };
      // A spreadsheet or CSV has no page to photograph. Rather than pushing the
      // reviewer into Numbers — which loses their place in the list — show the
      // text the auditor already read out of it. That text is also exactly what
      // the classifier judged the document on, so it explains the verdict.
      img.onerror = function(){
        // A spreadsheet gets a grid, not a paragraph. Tried first, and only
        // falling through to the flat text if the workbook cannot be read —
        // a .xls saved by an old version, say, which openpyxl will not open.
        var low = (b.dataset.path||'').toLowerCase();
        if(/\.(xlsx|xlsm|xltx|csv|tsv|docx)$/.test(low)){
          fetch('/api/sheet?path=' + encodeURIComponent(b.dataset.path)
                + '&folder=' + encodeURIComponent(window.__FQ_FOLDER__||''))
            .then(function(r){
              if(r.status === 404){
                body.innerHTML = '<div id="pvmsg">This copy of the app is older than '
                  + 'the page and has no spreadsheet viewer. Quit it and start it '
                  + 'again, then reopen this preview.</div>';
                return null;
              }
              return r.json();
            })
            .then(function(d){
              if(d === null) return;
              if(!d.sheets || !d.sheets.length) throw new Error(d.error||'no sheets');
              showSheets(body, d.sheets);
            })
            .catch(function(){ textFallback(body, b); });
          return;
        }
        textFallback(body, b);
      };
      img.src = '/api/preview?path=' + encodeURIComponent(b.dataset.path)
              + '&folder=' + encodeURIComponent(window.__FQ_FOLDER__||'')
              + '&t=' + Date.now();
    });
  });

  // Checklist verdicts. Stored the moment they change, like every other
  // decision on this page, so nothing is lost by scrolling away; they still
  // only take effect when Save is pressed.
  // What a verdict means for the page, mirroring reconcile's VERDICTS table.
  // The server decides this for real on the next run; this is the same mapping
  // applied straight away, so the dot and the counts move when you do.
  var VERDICT_TO = {satisfied:'ok', not_applicable:'ok', practice:'call',
                    personal:'call', missing:'miss'};

  function recordItem(id){
    var sel  = document.querySelector('select.ckv[data-item="'+CSS.escape(id)+'"]');
    var note = document.querySelector('input.cknote[data-item="'+CSS.escape(id)+'"]');
    var v = sel ? sel.value : '';
    var n = note ? note.value.trim() : '';
    if(!v && !n) delete ITEMS[id];
    else ITEMS[id] = {verdict: v, note: n};
    setUndecided();
    if(v) restat(id, VERDICT_TO[v]);
    autosave();
  }

  // Move the item's dot and redraw the counts. Without this, marking something
  // satisfied changed nothing on screen until the next audit run — which reads
  // exactly like the click not working, so people click again.
  function restat(id, kind){
    if(!kind) return;
    var pane = document.querySelector('.mdpane select.ckv[data-item="'
                                      + CSS.escape(id) + '"]');
    if(!pane) return;
    var i = pane.closest('.mdpane').dataset.i;
    var row = document.querySelector('.mdrow[data-i="' + i + '"] i');
    if(row) row.className = ({ok:'tok', call:'tcall', miss:'tmiss'})[kind];
    var tile = document.querySelectorAll('.tiles i')[parseInt(i, 10)];
    recount();
  }

  function recount(){
    var dots = document.querySelectorAll('.mdlist .mdrow i');
    var ok = 0, call = 0, miss = 0;
    dots.forEach(function(d){
      if(d.classList.contains('tok')) ok++;
      else if(d.classList.contains('tcall')) call++;
      else miss++;
    });
    var total = ok + call + miss || 1;
    var tiles = document.querySelectorAll('.tiles i');
    dots.forEach(function(d, n){ if(tiles[n]) tiles[n].className = d.className; });
    var pct = Math.round(100 * ok / total);
    var donut = document.querySelector('.donut');
    if(donut){
      donut.style.setProperty('--pct', pct);
      var b = donut.querySelector('.donutmid b');
      if(b) b.textContent = pct + '%';
    }
    var key = document.querySelector('.ckbarkey');
    if(key) key.innerHTML = '<span><i class="kok"></i>' + ok + ' answered</span>'
      + '<span><i class="kcall"></i>' + call + ' need you</span>'
      + '<span><i class="kmiss"></i>' + miss + ' not sent yet</span>';
  }

  // Saved as you work. The Save button was a step people forgot, and forgetting
  // it lost everything with no warning — the page looked identical either way.
  var saveTimer = null;
  function autosave(){
    if(!window.__FQ_SAVE__) return;          // standalone file: no server to save to
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function(){
      window.__FQ_SAVE__({files: DEC, accounts: ACCTS, items: ITEMS});
    }, 600);
  }
  document.querySelectorAll('select.ckv').forEach(function(sel){
    sel.addEventListener('change', function(){ recordItem(sel.dataset.item); });
  });
  document.querySelectorAll('input.cknote').forEach(function(inp){
    inp.addEventListener('input', function(){ recordItem(inp.dataset.item); });
  });

  document.querySelectorAll('button.bulk').forEach(function(b){
    b.addEventListener('click', function(){
      var reason = b.dataset.reason;
      var pick = document.querySelector('select[data-bulkfor="'+CSS.escape(reason)+'"]');
      if(!pick || !pick.value) return;
      document.querySelectorAll('[data-sha][data-reason="'+CSS.escape(reason)+'"]').forEach(function(row){
        var sel = row.querySelector('select.dest');
        if(!sel) return;
        if(!Array.prototype.some.call(sel.options, function(o){return o.value===pick.value;})){
          var o=document.createElement('option'); o.value=pick.value; o.textContent=pick.value; sel.appendChild(o);
        }
        sel.value = pick.value;
        var note = row.querySelector('input.note');
        record(row.dataset.sha, pick.value, note?note.value:'', row);
      });
    });
  });
  // Standing rules per account.
  document.querySelectorAll('select.acct').forEach(function(sel){
    var ak = sel.dataset.akey;
    if(ACCTS[ak]){
      if(!Array.prototype.some.call(sel.options, function(o){return o.value===ACCTS[ak].dest;})){
        var o=document.createElement('option'); o.value=ACCTS[ak].dest; o.textContent=ACCTS[ak].dest; sel.appendChild(o);
      }
      sel.value = ACCTS[ak].dest;
    }
    sel.addEventListener('change', function(){
      if(sel.value) ACCTS[ak] = {dest: sel.value, note: ''};
      else delete ACCTS[ak];
      // Reflect the rule on every row of that account.
      document.querySelectorAll('[data-akey="'+CSS.escape(ak)+'"]').forEach(function(row){
        var c = row.querySelector('.destnow');
        if(c) c.textContent = sel.value || row.dataset.suggested;
      });
      setUndecided();
    });
  });
  setUndecided();
}

function save(name, text, type){
  var b = new Blob([text], {type: type || 'text/plain'});
  var u = URL.createObjectURL(b);
  var a = document.createElement('a');
  a.href = u; a.download = name;
  document.body.appendChild(a); a.click();
  setTimeout(function(){ URL.revokeObjectURL(u); a.remove(); }, 800);
}

function wireButtons(){
  var d = document.getElementById('dlDec');
  if(d) d.addEventListener('click', function(){
    save('decisions.json', JSON.stringify({files:DEC, accounts:ACCTS, items:ITEMS}, null, 1), 'application/json');
  });
  // Downloaded as HTML, not .txt or .md — those open in a plain editor on a Mac
  // and look terrible. This opens formatted in any browser and prints to PDF.
  var m = document.getElementById('dlMemo');
  if(m) m.addEventListener('click', function(){
    var body = document.getElementById('memo').textContent;
    var esc = body.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    var doc = '<!DOCTYPE html><html><head><meta charset="utf-8">'
      + '<title>Needs Clarification</title><style>'
      + 'body{font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#1B2A41;'
      + 'max-width:760px;margin:40px auto;padding:0 24px}'
      + 'pre{white-space:pre-wrap;font:inherit;margin:0}'
      + '@media print{body{margin:0}}'
      + '</style></head><body><pre>' + esc + '</pre></body></html>';
    save('Needs Clarification.html', doc, 'text/html');
  });
  var c = document.getElementById('cpMemo');
  if(c) c.addEventListener('click', function(){
    var t = document.getElementById('memo').textContent;
    if(navigator.clipboard) navigator.clipboard.writeText(t).then(function(){ c.textContent='Copied'; setTimeout(function(){c.textContent='Copy writeup';},1400); });
  });
  ['planfilter|plantable','unexpfilter|unexptable'].forEach(function(p){
    var a=p.split('|'), i=document.getElementById(a[0]), t=document.getElementById(a[1]);
    if(!i||!t) return;
    i.addEventListener('input', function(){
      var q=i.value.toLowerCase();
      Array.prototype.forEach.call(t.tBodies[0].rows, function(r){
        if(r.classList.contains('grp')) return;
        r.style.display = r.textContent.toLowerCase().indexOf(q)>=0 ? '' : 'none';
      });
    });
  });
}
wire(); wireButtons();
"""


def _e(s):
    return html.escape('' if s is None else str(s))


def _pill(status):
    cls = {'satisfied': 'p-sat', 'missing': 'p-mis', 'mismatched': 'p-mism',
           'not_applicable': 'p-na', 'partly satisfied': 'p-part'}.get(status, 'p-rev')
    return '<span class="pill %s">%s</span>' % (cls, _e(status.replace('_', ' ')))


# Where each kind of document could plausibly go. An ECU statement is a bank
# statement — it belongs in one of the two Banking folders, not in any of the
# twenty-one places the full list offers. Narrowing the choice is most of what
# makes this quick to work through.
LIKELY_FOR = {
    'bank_statement':        ['Personal/Banking', 'Business/Banking'],
    'cc_statement':          ['Business/Credit Cards', 'Personal/Banking'],
    'brokerage_statement':   ['Personal/Investments'],
    'credit_report':         ['Personal/Credit Reports'],
    'w2':                    ['Personal/Pay Info:W2s'],
    'paystub':               ['Personal/Pay Info:W2s'],
    'payroll_summary':       ['Business/Payroll Summaries'],
    'pnl':                   ['Business/Financials'],
    'balance_sheet':         ['Business/Financials'],
    'personal_tax_return':   ['Personal/Taxes'],
    'business_tax_return':   ['Business/Taxes'],
    'day_sheet':             ['Business/Production/Monthly Production', 'Business/Production'],
    'provider_productivity': ['Business/Production/Monthly Production', 'Business/Production'],
    'fee_schedule':          ['Business/Fees'],
    'employment_contract':   ['Business/Associate Info'],
    'building_value':        ['Business'],
    'debt_schedule':         ['Personal/Debt', 'Business/Debt'],
    'disability_insurance':  ['Personal/Insurance'],
    'life_insurance':        ['Personal/Insurance'],
    'homeowners_insurance':  ['Personal/Insurance'],
    'business_overhead_insurance': ['Business/Insurance'],
    'rental_lease':          ['Personal/Assets'],
    'staff_roster':          ['Business/Logistics'],
    'bonus_structure':       ['Business/Logistics'],
    'practice_hours':        ['Business/Logistics'],
    'client_note':           ['Personal/Misc'],
}
# Always offered, whatever the document is: somewhere to put the odd one out, and
# a way to leave it for later.
ALWAYS = ['Personal/Misc', 'Business/Misc', REVIEW_DIR]


def _dest_options_for(doc, plan, selected=None):
    """A short list of likely destinations, with everything else still reachable.

    Two groups rather than a filtered list: an unrecognised document, or one the
    classifier got wrong, still needs somewhere to go — hiding the rest would
    trade one kind of stuck for another.
    """
    all_dests = set(BASE_DESTS)
    for p in plan:
        if p.get('dest') and p['dest'] != REVIEW_DIR:
            all_dests.add(p['dest'])

    # The parent folders only — NOT every account subfolder beneath them. Listing
    # siblings turned a 2-option choice into 14: an ECU statement with no account
    # number read has no business being offered Business/Banking/x9700. Its own
    # account folder is added below when the classifier managed to read one.
    likely = list(LIKELY_FOR.get(doc.get('doc_type') or '', []))
    # the document's own account folder, if the classifier read one
    if doc.get('dest') and doc['dest'] != REVIEW_DIR and doc['dest'] not in likely:
        likely.insert(0, doc['dest'])
    for d in ALWAYS:
        if d not in likely:
            likely.append(d)

    out = ['<option value="">— choose —</option>']
    if likely:
        out.append('<optgroup label="Likely">')
        for d in likely:
            sel = ' selected' if d == selected else ''
            out.append('<option value="%s"%s>%s</option>' % (_e(d), sel, _e(d)))
        out.append('</optgroup>')
    rest = [d for d in sorted(all_dests) if d not in likely]
    if rest:
        out.append('<optgroup label="Anywhere else">')
        for d in rest:
            sel = ' selected' if d == selected else ''
            out.append('<option value="%s"%s>%s</option>' % (_e(d), sel, _e(d)))
        out.append('</optgroup>')
    return ''.join(out)


def _dest_options(plan, selected=None):
    seen = set(BASE_DESTS)
    for p in plan:
        if p['dest'] and p['dest'] != REVIEW_DIR:
            seen.add(p['dest'])
    opts = ['<option value="">— choose —</option>']
    for d in sorted(seen):
        sel = ' selected' if d == selected else ''
        opts.append('<option value="%s"%s>%s</option>' % (_e(d), sel, _e(d)))
    opts.append('<option value="%s">%s (leave for later)</option>' % (_e(REVIEW_DIR), _e(REVIEW_DIR)))
    return ''.join(opts)



CK_MARK = {'satisfied': ('', '\u2713'), 'not_applicable': ('na', '\u2013'),
           'partly satisfied': ('part', '\u00bd'), 'missing': ('bad', '!'),
           'mismatched': ('bad', '!')}
CK_ORDER = {'missing': 0, 'mismatched': 1, 'partly satisfied': 2,
            'satisfied': 3, 'not_applicable': 4}


# The classifier's own wording, so a chip and the filing log cannot disagree
# about what a document is. Built from its rules rather than retyped.
def _doc_labels():
    try:
        from classify import RULES
        return {r.doc_type: r.label for r in RULES}
    except Exception:
        return {}


DOC_LABELS = _doc_labels()
DOC_LABELS.setdefault('unknown', 'unrecognised')
DOC_LABELS.setdefault('client_note', 'client note')


def render_checklist_summary(a, results, client, verdicts=None, n_review=0):
    """The whole point of the page, answering two questions and nothing else.

    What needs YOU, and what the client has not sent. Everything that used to
    sit here — nine counters in a rail, eleven headed sections, a dropdown on
    every one of thirty items — answered questions nobody had asked, and buried
    the two that matter.

    An item needing judgement states WHY on its own line ("what arrived is for
    x4782"), so the reason is readable without opening anything. A missing item
    needs no reason: nothing came.
    """
    if not results:
        return
    for r in results:
        v = (verdicts or {}).get(str(r['item'].get('id'))) or {}
        r['_verdict'], r['_vnote'] = v.get('verdict') or '', v.get('note') or ''

    def needs_you(r):
        return (r['status'] in ('mismatched', 'partly satisfied')
                or bool(r.get('verdict_stale')))

    judge   = [r for r in results if needs_you(r)]
    absent  = [r for r in results if r['status'] == 'missing' and not needs_you(r)]
    settled = [r for r in results if r not in judge and r not in absent]

    a('<div class="sum">')
    a('<div class="sumhead">%s</div>' % _e(client))

    # Where the client stands, first and as a picture. Collapsing this to one
    # line of prose and pushing the answered list to the bottom of the page made
    # the single most-asked question — how much of this have they sent? — the
    # hardest thing on the screen to find.
    # One tile per item, in the order they were asked for. A bar shows the
    # proportion; tiles show the proportion AND the count AND which specific
    # items are where, because every tile carries the item's name on hover.
    # Thirty things asked for is a shape you can take in at a glance; "61%" is
    # a number you have to think about.
    pct = int(round(100.0 * len(settled) / (len(results) or 1)))
    a('<div class="donutrow">')
    a('<div class="donut" style="--pct:%d">'
      '<div class="donutmid"><b>%d%%</b><span>complete</span></div></div>' % (pct, pct))
    # Same order and index as the rows below, so a tile and a row are the same
    # item. They were drawn in two different orders, which meant updating one
    # recoloured the wrong square in the other.
    order = judge + absent + settled
    a('<div class="tiles">')
    for n, r in enumerate(order):
        if r in judge:
            cls, what = 'tcall', 'needs you'
        elif r in absent:
            cls, what = 'tmiss', 'not sent yet'
        else:
            cls, what = 'tok', 'answered'
        a('<i class="%s" data-i="%d" title="%s — %s"></i>'
          % (cls, n, _e(r['item'].get('label') or ''), what))
    a('</div></div>')
    a('<div class="ckbarkey"><span><i class="kok"></i>%d answered</span>'
      '<span><i class="kcall"></i>%d need you</span>'
      '<span><i class="kmiss"></i>%d not sent yet</span></div>'
      % (len(settled), len(judge), len(absent)))

    # List on the left, the selected item opened on the right. Every item is in
    # the list, in the order it was asked for, so "what have they sent" is the
    # same glance as "what is left" — and only one item's detail is on screen at
    # a time, which is what stopped this page being a wall.
    shorts = short_labels([(r['item'].get('label') or r['item'].get('id') or '',
                            r['item'].get('satisfied_by') or ())
                           for r in order])
    a('<div class="md">')
    a('<div class="mdlist">')
    for n, r in enumerate(order):
        dot = 'tcall' if r in judge else ('tmiss' if r in absent else 'tok')
        full = r['item'].get('label') or r['item'].get('id') or ''
        a('<button class="mdrow%s" data-i="%d" title="%s"><i class="%s"></i>'
          '<span>%s</span></button>'
          % (' on' if n == 0 else '', n, _e(full), dot, _e(shorts[n])))
    a('</div>')
    a('<div class="mddetail">')
    for n, r in enumerate(order):
        a('<div class="mdpane%s" data-i="%d">' % ('' if n == 0 else ' hide', n))
        a('<div class="mdwhat">What we asked for</div>')
        _render_item(a, r, show_why=True)
        a('</div>')
    a('</div></div>')

    if n_review:
        a('<div class="morerow" onclick="document.getElementById(\'decidethese\')'
          '.scrollIntoView({behavior:\'smooth\'})">'
          '<span class="chev"></span>%d document(s) could not be placed '
          '\u2014 tell it where they go</div>' % n_review)
    a('</div>')
    a('''<script>
(function(){
  var rows = document.querySelectorAll('.mdrow');
  var panes = document.querySelectorAll('.mdpane');
  function open(i){
    rows.forEach(function(x){ x.classList.toggle('on', x.dataset.i === i); });
    panes.forEach(function(p){ p.classList.toggle('hide', p.dataset.i !== i); });
    var row = document.querySelector('.mdrow[data-i="' + i + '"]');
    if(row && row.scrollIntoView) row.scrollIntoView({block:'nearest'});
  }
  rows.forEach(function(b){
    b.addEventListener('click', function(){ open(b.dataset.i); });
  });
  // A tile is the same item as a row. Clicking one opens it, which turns the
  // chart from a picture into a way in.
  document.querySelectorAll('.tiles i').forEach(function(t){
    t.style.cursor = 'pointer';
    t.addEventListener('click', function(){ open(t.dataset.i); });
  });
  window.__FQ_OPEN__ = open;
})();
</script>''')


# A LIST of years at the front is noise — nearly every ask opens '2024,
# 2025, & 2026 YTD'. A single year is the opposite: '2025 business taxes'
# and '2025 personal taxes' are told apart by nothing else.
# A checklist row should read like a label, not like the sentence we sent the
# client. Built from WHAT IS ASKED FOR rather than by truncating the wording:
# "QuickBooks Online login information or a QuickBooks backup file for the
# dental building entity (Moonridge), if available (reach out if you need
# guidance...)" is "QuickBooks · building", and thirty of those is a list you
# can read down in one pass.
SHORT_BY_TYPE = {
    'debt_schedule': 'Debt schedule', 'bank_statement': 'Bank statements',
    'personal_tax_return': 'Personal taxes', 'business_tax_return': 'Business taxes',
    'partnership_tax_return': 'Entity taxes', 'pnl': 'Profit & loss',
    'balance_sheet': 'Balance sheet', 'production_report': 'Production reports',
    'day_sheet': 'Production reports', 'provider_productivity': 'Production reports',
    'fee_schedule': 'Fee schedule', 'w2': 'W-2s', 'form_1099': '1099s',
    'credit_report': 'Credit report', 'birthdates': 'Birth date',
    'quickbooks_file': 'QuickBooks', 'rental_lease': 'Lease',
    'life_insurance': 'Life insurance', 'disability_insurance': 'Disability cover',
    'brokerage_statement': 'Investment statements', 'hsa_statement': 'HSA statements',
    'financial_plan': 'Financial plan', 'employment_contract': 'Associate contracts',
    'dr_days_worked': 'Doctor days', 'total_patients': 'Total patients',
    'new_patients': 'New patients', 'paystub': 'Pay stubs',
    'line_of_credit': 'Line of credit', 'building_value': 'Building value',
    'cc_statement': 'Card statements', 'payroll_summary': 'Payroll',
    'staff_roster': 'Staff roster', 'client_note': 'Note from the client',
}

_ACCT = re.compile(r'(?:ending(?:\s+in)?\s*#?\s*x?|\bx)(\d{4,})\b', re.I)
_ONE_YEAR = re.compile(r'^\s*(20\d\d)\b(?!\s*[,&]\s*20)')
_ENTITY_WORD = re.compile(
    r'\b(practice|building|personal|wellness clinic|memphis|rental|moonridge|'
    r'home|hsa)\b', re.I)


def short_label(label, satisfied_by=()):
    """One short line naming what the item asks for."""
    text = (label or '').strip()
    base = None
    for t in (satisfied_by or ()):
        if t in SHORT_BY_TYPE:
            base = SHORT_BY_TYPE[t]
            break
    if not base:
        base = re.split(r'\s*[\u2014\u2013(]|,\s*if\b', text)[0].strip(' ,;')
        base = base[:34] + ('\u2026' if len(base) > 34 else '')

    bits = []
    y = _ONE_YEAR.search(text)
    if y:
        bits.append(y.group(1))
    acct = _ACCT.search(text)
    if acct:
        bits.append('x' + acct.group(1))
    else:
        ent = _ENTITY_WORD.search(text)
        if ent and ent.group(1).lower() not in base.lower():
            bits.append(ent.group(1).lower())
    return (' '.join([bits[0], base]) if bits and bits[0].isdigit()
            else base) + (' \u00b7 ' + ' \u00b7 '.join(
                b for b in bits if not b.isdigit()) if any(
                    not b.isdigit() for b in bits) else '')


def short_labels(items):
    """Short labels for a whole list, disambiguated where two collide.

    Oyler asks for QuickBooks twice — practice and building entity. Two rows
    reading "QuickBooks" is worse than two long ones: you cannot tell which one
    you are answering.
    """
    out = [short_label(lbl, sb) for lbl, sb in items]
    seen = {}
    for i, s in enumerate(out):
        seen.setdefault(s, []).append(i)
    for s, idx in seen.items():
        if len(idx) < 2:
            continue
        for i in idx:
            extra = _ENTITY_WORD.findall(items[i][0] or '')
            extra = [e.lower() for e in extra if e.lower() not in s.lower()]
            if extra:
                out[i] = s + ' \u00b7 ' + extra[0]
    return out


def _render_item(a, r, show_why=True, quiet=False):
    """One checklist line: what was asked, why it is here, what you can say."""
    item = r['item']
    a('<div class="ckline%s">' % (' quiet' if quiet else ''))
    a('<div class="cklab">%s</div>' % _e(item.get('label') or item.get('id')))
    if r.get('verdict_stale'):
        a('<span class="ckstale">your answer predates the evidence</span>')

    why = []
    if show_why and r.get('note'):
        why.append(_e(r['note']))
    if why:
        a('<div class="ckwhy">%s</div>' % ' \u00b7 '.join(why))

    docs = r.get('docs') or []
    if docs and not quiet:
        a('<div class="ckdocs">')
        for n, d in enumerate(docs):
            # openfile as well as ckdoc: the preview binds to .openfile, and
            # renaming the chip silently killed every preview on the page.
            #
            # The classification is shown only here — on an item you are being
            # asked about. A chip reading "tax extension.pdf" says nothing about
            # WHY it is attached to a birthdate item; "· client note" says it all.
            lab = DOC_LABELS.get(d.get('doc_type'), d.get('doc_type') or 'unrecognised')
            a('<button class="ckdoc openfile%s" data-path="%s" data-name="%s" '
              'title="classified as %s">%s<span class="ckdt">%s</span></button>'
              % (' ckx' if n >= 4 else '', _e(d.get('path') or ''),
                 _e(d.get('file') or ''), _e(lab),
                 _e(d.get('file') or ''), _e(lab)))
        if len(docs) > 4:
            # "+8 more" used to be a dead label, so the eight documents it stood
            # for could not be looked at — on exactly the items where you most
            # need to know which ones arrived.
            a('<button class="ckmore" onclick="this.parentNode.querySelectorAll'
              '(\'.ckx\').forEach(function(e){e.classList.remove(\'ckx\')});'
              'this.remove()">show %d more</button>' % (len(docs) - 4))
        a('</div>')

    if not quiet:
        cur = (r.get('_verdict') or '')
        _said = {'satisfied': 'satisfied', 'missing': 'nothing arrived',
                 'mismatched': 'needs your call', 'partly satisfied': 'half answered',
                 'not_applicable': 'not applicable'}.get(r['status'], r['status'])
        opts = [('', 'Auditor says: %s' % _said),
                ('satisfied', 'Satisfied \u2014 all here'),
                ('practice', 'Practice side only'), ('personal', 'Personal side only'),
                ('not_applicable', 'Not applicable \u2014 they do not have one'),
                ('missing', 'Still missing \u2014 chase it')]
        a('<div class="ckpick">')
        a('<select class="ckv" data-item="%s">' % _e(str(item.get('id'))))
        for val, txt in opts:
            a('<option value="%s"%s>%s</option>'
              % (_e(val), ' selected' if val == cur else '', _e(txt)))
        a('</select>')
        a('<input class="cknote" data-item="%s" placeholder="note (optional)" value="%s">'
          % (_e(str(item.get('id'))), _e(r.get('_vnote') or '')))
        a('</div>')
    a('</div>')


def _tip(names, cap=7):
    """A hover list for a count, so a number is never just a number.

    "1 needs a decision" is a fact you cannot act on without hunting for which
    one. Capped, because a client with thirty missing items would produce a
    tooltip taller than the window.
    """
    names = [n for n in (names or []) if n]
    if not names:
        return 'nothing in this group'
    out = names[:cap]
    if len(names) > cap:
        out.append('\u2026and %d more' % (len(names) - cap))
    return '\n'.join('\u2022 ' + str(n)[:78] for n in out)


def build_html(res, client, checklist_source, path, decisions=None, cache_dir=None,
               redacted_dir=None, previews='redacted', comments=None):
    docs, results = res['docs'], res['results']
    cross, leaks = res['cross'], res['leaks']
    unexpected = res.get('unexpected', [])
    decisions = decisions or {}

    # A person's verdict lands before anything is counted, written or emailed.
    # Applied here rather than in the page markup so the chase list, the tiles
    # and the client email all see the same answer.
    import reconcile as _rec
    _rec.apply_item_verdicts(results, item_decisions(decisions), who='you')

    plan = build_plan(docs, decisions, res.get('mislabeled') or ())
    review = [p for p in plan if p['review']]
    memo = build_clarification(res, plan, client)
    red_idx = build_redacted_index(redacted_dir) if previews == 'redacted' else {}

    counts = {}
    for r in results:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    n_pages = sum(d.get('n_pages') or 0 for d in docs)
    stamp = datetime.date.today().isoformat()

    o = []
    a = o.append
    a('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">')
    a('<meta name="viewport" content="width=device-width,initial-scale=1">')
    a('<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
      'style-src \'unsafe-inline\'; script-src \'unsafe-inline\'; connect-src \'none\'; '
      'img-src data:; form-action \'none\'; base-uri \'none\'">')
    a('<meta name="referrer" content="no-referrer">')
    a('<title>Intake Review — %s</title>' % _e(client))
    a('<style>%s</style></head><body>' % CSS)

    a('<header><div class="hrow">')
    # No logo here. The app already shows one in its own header directly above,
    # so this page was stacking a second Four Quadrants mark on top of the first
    # and pushing the client's name — the one thing that identifies which file
    # you are looking at — into third place.
    a('<div class="hbrand">')
    a('<div class="hleft">')
    a('<h1>%s</h1>' % _e(client))
    a('<div class="sub">Intake review &middot; %s &middot; %d documents, %d pages</div>'
      % (stamp, len(docs), n_pages))
    a('</div></div>')
    a('<div class="hright">')
    a('<span id="undecided"></span>')
    a('<button class="primary" id="dlDec" disabled>Save decisions</button>')
    a('<button id="dlMemo" title="Download this writeup as a file">Download</button>')
    a('<button id="cpMemo" title="Copy this writeup, ready to paste into an email">Copy writeup</button>')
    a('</div>')
    a('</div>')
    a('<div class="progwrap"><div class="prog" id="prog"></div></div>')
    a('</header><div class="wrap"><div class="grid"><div class="main">')

    # Say, on the page itself, what this build was given. Without it the only way
    # to tell a stale page from decisions that never arrived is to read the
    # terminal, and the two failures look identical from here.
    _cf, _ca = split_decisions(decisions)
    if _cf or _ca:
        # Carried is not the same as applied. A decision can arrive and still do
        # nothing: saved with no destination chosen, or keyed to a document that
        # is not in this run. Counting all three separately is the difference
        # between knowing and guessing.
        _shas = {d.get('sha256') for d in docs}
        _blank = sum(1 for v in _cf.values() if not (v or {}).get('dest'))
        _unmatched = sum(1 for k, v in _cf.items() if (v or {}).get('dest') and k not in _shas)
        _applied = sum(1 for p in plan if p.get('decided'))
        bits = ['carried %d document decision(s), %d applied' % (len(_cf), _applied)]
        if _blank:
            bits.append('%d had no destination chosen' % _blank)
        if _unmatched:
            bits.append('%d did not match any document here' % _unmatched)
        if _ca:
            bits.append('%d account rule(s)' % len(_ca))
        msg = ' · '.join(bits)
    else:
        msg = 'no saved decisions were carried in'
    a('<div class="built">Built %s · %s</div>'
      % (datetime.datetime.now().strftime('%H:%M:%S'), msg))

    # State plainly what this file does and does not contain. Overclaiming
    # "no PII" would be false — filenames alone carry client names.
    if previews == 'originals':
        a('<div class="banner bad"><b>This page embeds unredacted originals.</b> '
          'It contains full identifiers. Treat it exactly like the source documents: '
          'do not forward it, do not upload it. Re-run without '
          '<code>--previews originals</code> to produce a shareable version.</div>')
    # The reassurance banner that used to sit here is gone at the operator's
    # request: it appeared on every page, said the same thing every time, and
    # pushed the actual work below the fold. The properties it described still
    # hold — digits are masked in snippets, the saved file has no network access
    # — they just no longer need restating on every client.


    render_checklist_summary(a, results, client, item_decisions(decisions),
                             n_review=len([p for p in plan if p['review']]))

    collided = [p for p in plan if p.get('collision')]

    # ---- the only thing that needs a person -------------------------------
    # One job, at the top, as cards rather than a table. A table asks you to read
    # across columns; a card asks one question at a time, which is what this is.
    if not review:
        a('<div class="alldone"><b>Nothing to decide.</b> Every document was placed '
          'confidently. Have a look at <i>Filed automatically</i> below if you want '
          'to check, otherwise you are done here.</div>')
    else:
        a('<h2 id="decidethese">Decide these<span class="n">%d of %d documents</span></h2>'
              % (len(review), len(plan)))
        a('<p class="hint">Everything else has been placed already. Work down this list, '
          'then press <b>Save decisions</b> at the top. Nothing moves until you do.</p>')

        # Account-level shortcuts first: one answer can settle a whole run of
        # statements, so offering it before the individual cards saves the
        # operator from answering the same question four times.
        accts = {}
        for p in review:
            if p.get('akey'):
                accts.setdefault(p['akey'], []).append(p)
        multi = {k: v for k, v in accts.items() if len(v) > 1}
        if multi:
            a('<div class="shortcut"><b>Shortcut — decide a whole account at once</b>'
              '<p class="hint" style="margin:6px 0 10px">These are several statements for '
              'the same account. Answering here settles all of them, and every future '
              'statement for that account.</p>')
            for ak, arows in sorted(multi.items(), key=lambda x: -len(x[1])):
                a('<div class="acctrow"><span class="who">%s</span>'
                  '<span class="cnt">%d files</span>'
                  '<select class="acct" data-akey="%s">%s</select></div>'
                  % (_e(account_label(arows)), len(arows), _e(ak),
                     _dest_options_for(arows[0], plan)))
            a('</div>')

        for i, p in enumerate(review, 1):
            bits = [x for x in [(p['doc_type'] or '').replace('_', ' '), p['side'],
                                p['issuer'], ('x%s' % p['tail']) if p['tail'] else None,
                                p['year']] if x]
            thumb, tsrc = None, None
            if previews == 'redacted':
                rp = red_idx.get(os.path.splitext(p['file'] or '')[0].strip().lower())
                if rp:
                    thumb = _thumb_data_uri(rp)
            elif previews == 'originals':
                thumb = _thumb_data_uri(p.get('path'))
            snip = _snippet(cache_dir, p.get('sha'))

            a('<div class="qcard" data-sha="%s" data-review="1" data-reason="%s" '
              'data-suggested="%s" data-akey="%s">'
              % (_e(p['sha']), _e(p['why']), _e(p['dest']), _e(p.get('akey') or '')))
            a('<div class="qnum">%d</div>' % i)
            a('<div class="qbody">')
            a('<div class="qname">%s</div>' % _e(p['file']))
            a('<div class="qmeta">%s</div>' % _e(' · '.join(str(b) for b in bits) or 'not recognised'))
            a('<div class="qwhy">%s</div>' % _e(p['why']))
            # Open the real file. A thumbnail is only embedded when a REDACTED
            # copy exists, so that this page can be shared without carrying a
            # client's statements inside it. That left a scanned image with no
            # preview at all — and "decide where this goes" with nothing to look
            # at is not a decision anyone can make. Opening the original in
            # Preview costs one click and puts nothing in the file.
            if p.get('path'):
                a('<button class="openfile" data-path="%s">Open this file</button>'
                  % _e(p['path']))
            if thumb or snip:
                a('<details class="prev"><summary>See the document</summary>')
                if thumb:
                    a('<img src="%s" alt="first page">' % thumb)
                if snip:
                    a('<div class="snip">%s…</div>' % _e(snip))
                a('</details>')
            a('<div class="qpick"><label>File it into</label>'
              '<select class="dest">%s</select>'
              '<input class="note" type="text" placeholder="note (optional)"></div>'
              % _dest_options_for(p, plan))
            a('</div></div>')

    # ---- full plan ---------------------------------------------------------
    a('<h2>Full filing plan<span class="n">%d documents</span></h2>' % len(plan))
    a('<input class="filter" id="planfilter" placeholder="Filter by file, type or destination…">')
    a('<details class="panel"><summary>Filed automatically'
      '<span class="n">%d documents</span></summary><div class="pbody">' % (len(plan) - len(review)))
    n_ren = len([p for p in plan if p.get('new_name')])
    n_tbd = len([p for p in plan if p.get('needs_confirmation')])
    a('<p class="hint">%d file(s) would be renamed from their contents%s. '
      'A name is only changed when it contradicts the contents or says nothing; '
      'anything already accurate is left alone.</p>'
      % (n_ren, (', %d still needing the period confirmed' % n_tbd) if n_tbd else ''))
    a('<table id="plantable"><thead><tr><th>File</th><th>New name</th><th>Type</th>'
      '<th>Destination</th><th>Why</th></tr></thead><tbody>')
    for p in plan:
        cls = 'done' if p['decided'] else ('review' if p['review'] else '')
        if p.get('needs_confirmation') or p.get('collision'):
            cls = 'review'
        newname = ('<b>%s</b>' % _e(p['new_name'])) if p.get('new_name') else \
                  '<span style="color:#9aa2ad">unchanged</span>'
        why = p['why']
        if p.get('new_name'):
            why = '%s<br><span style="color:#8A5218">rename: %s</span>' % (_e(why), _e(p.get('rename_why')))
        else:
            why = _e(why)
        # Every row can be opened. Previously only a document flagged for a
        # decision could be looked at, which is backwards: the ones filed
        # automatically are exactly the ones you want to spot-check.
        namecell = _e(p['file'])
        if p.get('path'):
            namecell += ('<br><button class="openfile" data-path="%s" data-name="%s">'
                         'Preview</button>' % (_e(p['path']), _e(p['file'])))
        a('<tr class="%s"><td>%s</td><td>%s</td><td>%s</td>'
          '<td><code class="destnow">%s</code></td><td>%s</td></tr>'
          % (cls, namecell, newname, _e((p['doc_type'] or '').replace('_', ' ')),
             _e(p['dest']), why))
    a('</tbody></table>')

    a('</div></details>')

    # ---- the writeup -------------------------------------------------------
    a('<details class="panel"><summary>What to chase'
      '<span class="n">the client still owes you things</span></summary><div class="pbody">')
    a('<p class="hint">Internal. No account numbers, no PII. Copy it into an email '
      'or hand it to whoever chases the client.</p>')
    a('<pre class="memo" id="memo">%s</pre>' % _e(memo))

    # ---- checklist ---------------------------------------------------------
    a('</div></details>')


    if collided:
        a('<div class="collide" style="margin-top:26px"><b>Two documents wanted the same name</b>'
          '<p class="hint" style="margin:6px 0 8px">Already handled — they have been numbered '
          'so nothing is overwritten, and they file normally. Worth opening both, though: '
          'usually it means the same document arrived twice.</p><ul style="margin:0">')
        for p in collided:
            a('<li><code>%s</code> &rarr; <b>%s</b></li>' % (_e(p['file']), _e(p['new_name'])))
        a('</ul></div>')

    if comments:
        a('<details class="panel"><summary>What was said in the portal'
          '<span class="n">%d message(s)</span></summary><div class="pbody">' % len(comments))
        a('<p class="hint">The whole thread, oldest first. Worth a look before '
          'chasing anything — half of what looks missing has usually been '
          'discussed already.</p>')
        for c in comments:
            a('<div class="saidrow"><div class="saidwho">%s<span>%s</span></div>'
              '<div class="saidtext">%s</div></div>'
              % (_e(c.get('who') or 'someone'),
                 'client' if c.get('from_client') else 'our team',
                 _e(c.get('text') or '')))
        a('</div></details>')

    a('<details class="panel"><summary>Detail'
      '<span class="n">checklist, missing months, duplicates</span></summary><div class="pbody">')
    a('<h2>Checklist<span class="n">%d items</span></h2>' % len(results))
    a('<table><thead><tr><th>Status</th><th>Section</th><th>Item</th><th>Note</th></tr></thead><tbody>')
    order = {'missing': 0, 'partly satisfied': 1, 'mismatched': 2,
             'satisfied': 3, 'not_applicable': 4}
    for r in sorted(results, key=lambda x: order.get(x['status'], 3)):
        a('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
          % (_pill(r['status']), _e(r['item'].get('section')),
             _e(r['item'].get('label')), _e(r.get('note'))))
    a('</tbody></table>')

    if cross['gaps']:
        a('<h2>Statement series with missing months<span class="n">%d</span></h2>' % len(cross['gaps']))
        a('<table><thead><tr><th>Series</th><th>Have</th><th>Missing</th></tr></thead><tbody>')
        for g in cross['gaps']:
            a('<tr><td>%s</td><td>%s</td><td><b>%s</b></td></tr>'
              % (_e(g.get('label')), _e(', '.join(g.get('present') or [])),
                 _e(', '.join(g.get('missing') or []))))
        a('</tbody></table>')

    if cross.get('gap_fillers'):
        a('<h2>A missing month may be here under a wrong name<span class="n">%d</span></h2>'
          % len(cross['gap_fillers']))
        a('<ul>')
        for f in cross['gap_fillers']:
            a('<li><code>%s</code> is named like a %s but its contents are a %s for %s</li>'
              % (_e(f.get('file')), _e(f.get('claimed')), _e(f.get('actual')), _e(f.get('month'))))
        a('</ul>')

    if cross.get('mislabeled'):
        a('<h2>Content does not match the filename<span class="n">%d</span></h2>' % len(cross['mislabeled']))
        a('<ul>')
        for m in cross['mislabeled']:
            a('<li><code>%s</code> — filename suggests %s, contents are <b>%s</b></li>'
              % (_e(m.get('file')), _e(m.get('claimed')), _e(m.get('actual'))))
        a('</ul>')

    if cross.get('duplicates'):
        a('<h2>Duplicates<span class="n">%d</span></h2>' % len(cross['duplicates']))
        a('<ul>')
        for d in cross['duplicates']:
            a('<li>%s: %s</li>' % (_e(d.get('kind')),
                                   ', '.join('<code>%s</code>' % _e(f) for f in d.get('files') or [])))
        a('</ul>')

    if unexpected:
        a('<h2>Provided but not on the checklist<span class="n">%d</span></h2>' % len(unexpected))
        a('<input class="filter" id="unexpfilter" placeholder="Filter…">')
        a('<table id="unexptable"><thead><tr><th>File</th><th>Read as</th></tr></thead><tbody>')
        for u in unexpected:
            bits = [x for x in [u.get('label'), u.get('issuer'),
                                ('x%s' % u['account_tail']) if u.get('account_tail') else None,
                                u.get('period') or u.get('year')] if x]
            a('<tr><td>%s</td><td>%s</td></tr>' % (_e(u.get('file')), _e(' · '.join(str(b) for b in bits))))
        a('</tbody></table>')

    a('</div></details>')

    a('<details class="pii"><summary>Residual PII — INTERNAL ONLY — %d file(s). '
      'Never send this section, or anything derived from it, to a client.</summary>'
      '<div class="piibody">' % len(leaks))
    a('<p class="hint">Values are masked to the last four digits. A finding only fires on six '
      'or more digits, so it always means the document holds more than a last-four. This is '
      'the gate on anything leaving the machine.</p>')
    for fname in sorted(leaks.keys()):
        findings = [f for f in leaks[fname] if f.get('confidence') == 'high']
        lower = len(leaks[fname]) - len(findings)
        if not findings and not lower:
            continue
        a('<div class="leakfile">%s</div><ul>' % _e(fname))
        for f in findings:
            pages = f.get('pages') or ([f['page']] if f.get('page') else [])
            where = ('pages %s of %s' % (', '.join(str(p) for p in pages), f.get('n_pages'))) \
                    if pages else 'page not recorded'
            a('<li><b>%s</b> <code>%s</code> (%s digits) — %s <span class="pill p-rev">%s</span>'
              % (_e(f.get('kind')), _e(f.get('masked')), _e(f.get('digits_seen')),
                 _e(f.get('why')), _e(where)))
            if f.get('context'):
                a('<div class="ctx">%s</div>' % _e(f['context']))
            a('</li>')
        if lower:
            a('<li>%d lower-confidence match(es) not listed</li>' % lower)
        a('</ul>')
    a('</div></details>')

    a('</div>')                                    # .main

    # The rail is gone. Nine counters — partly satisfied, series gaps, files
    # with residual PII — answered nine questions nobody had asked, and the
    # two that matter (what needs me, what never arrived) were competing with
    # them for the same glance. Those two now ARE the page; the rest is one
    # collapsed line each, or lives in the internal report where it belongs.
    a('</div>')                                    # .grid

    a('</div><footer>Generated locally by the FQ intake auditor. '
      'No network access; this page cannot transmit anything.</footer>')
    _f, _a = split_decisions(decisions)
    a('<script>window.__CARRIED__=%s;</script>'
      % json.dumps({'files': _f, 'accounts': _a, 'items': item_decisions(decisions)}))
    a('<script>%s</script></body></html>' % JS)

    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(o))
    return path
