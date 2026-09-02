"""Content-based document classifier.

Rules of the road:

  * Classification is driven by the OCR'd CONTENT of the document. The filename
    is never a deciding factor -- clients mislabel files constantly (a
    "statement.pdf" that is really a W-2). The filename is recorded only so the
    auditor can REPORT a contradiction between name and content.

  * Identifying phrases are matched against the document HEAD, not the whole
    text. This matters more than it sounds: a 137-page credit report contains a
    legend line reading "PPL: Paid profit and loss", and a paystub itemises "EE
    Disability Pretax" as a deduction. Searching the full text for a title turns
    those into a P&L and a disability policy respectively. Only rules that are
    genuinely about bulk content (counting procedure codes, say) read everything.

  * Every classified document carries scope hints -- primary form year, period,
    granularity, month, issuer, account tail -- because the reconciler has to
    tell "right document, wrong scope" from "right document".

  * `owner_side` (Personal / Practice) is emitted for every document so the
    later filing-tree stage is a thin layer on top of this module.

Add a document type by appending a Rule. Rules are evaluated in order and the
first match wins, so specific rules go above general ones.
"""
import re
import unicodedata
from collections import namedtuple

# how much of the document counts as the "head" for title matching
HEAD_CHARS = 3500

MONTHS = {m: i for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
     'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], start=1)}
MONTH_NAMES = ['', 'January', 'February', 'March', 'April', 'May', 'June',
               'July', 'August', 'September', 'October', 'November', 'December']
MONTH_RE = (r'(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
            r'Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)')
NUM_DATE = r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})'


def normalise(text):
    """Google Docs exports are full of zero-width joiners, which silently break
    every regex you try to run against them."""
    if not text:
        return ''
    t = unicodedata.normalize('NFKC', text)
    return t.replace('​', '').replace('‌', '').replace('﻿', '')


def has(t, *pats):
    return any(re.search(p, t, re.I) for p in pats)


def count(t, *pats):
    return sum(len(re.findall(p, t, re.I)) for p in pats)


# --------------------------------------------------------------------------
# dates and periods
# --------------------------------------------------------------------------

def _norm_year(y):
    y = str(y)
    return '20' + y if len(y) == 2 else y


def _pdate(m, d, y):
    mi, yr = int(m), int(_norm_year(y))
    return (mi, yr) if 1 <= mi <= 12 and 2000 <= yr <= 2035 else None


# The trailing "(?: Date)?" matters more than it looks. Fifth Third heads its
# statements "Statement Period Date: 4/1/2026 - 4/30/2026". Without it the label
# match failed on that word and the search ran on to a bare "Period: 03/01/26 -
# 03/31/26" printed further down the page, dating every one of these statements
# a month early — which then invented a gap in the month that was actually there.
RANGE_LABEL = (r'(Statement\s*Dates?|Billing\s*Period|Statement\s*Period|Check\s*Dates?'
               r'|Activity\s*Period|Pay\s*Period|Period)(?:\s+Dates?)?')
DATE_LABEL = r'(Statement\s*Date|Closing\s*Date|Statement\s*Closing|As\s*of)'


def _closing_month(end, start=None):
    """Which month a statement 'belongs to', given its closing date.

    Statements are named by their closing date, but cycles that close on the 1st
    or 2nd of the following month would otherwise shift a whole statement
    forward: RRFD's January statement runs 1/01/26 thru 2/01/26 and must be
    January, not February. If it closes in the first couple of days of a month
    and the period started earlier, roll back.
    """
    em, ey, ed = end
    if ed <= 3 and start is not None:
        sm, sy, _ = start
        if (sm, sy) != (em, ey):
            return sm, sy
    return em, ey


def _fulldate(m, d, y):
    got = _pdate(m, d, y)
    return None if got is None else (got[0], got[1], int(d))


def statement_period(text):
    """(month, year, raw) for a periodic document."""
    head = text[:6000]

    # 1. labelled range -> closing month
    m = re.search(RANGE_LABEL + r'\s*[:\-]?\s*' + NUM_DATE
                  + r'\s*(?:thru|through|to|-|–)\s*' + NUM_DATE, head, re.I)
    if m:
        start = _fulldate(m.group(2), m.group(3), m.group(4))
        end = _fulldate(m.group(5), m.group(6), m.group(7))
        if end:
            mi, yr = _closing_month(end, start)
            return mi, str(yr), m.group(0).strip()

    # 2. "From EOM: Jan 30, 26 To EOM: ..." -- EagleSoft reports. This must beat
    #    the generic date label below, because those reports also print the date
    #    they were RUN ("DATE 5/13/2026"), which is not the reporting period.
    m = re.search(r'From\s*(?:EOM|EOD)\s*:?\s*' + MONTH_RE + r'\w*\.?\s*\d{1,2},?\s*\'?(\d{2,4})',
                  head, re.I)
    if m:
        mi = MONTHS.get(m.group(1)[:3].lower())
        if mi:
            return mi, _norm_year(m.group(2)), m.group(0).strip()

    # 3. label, then dates further along (tables put label and value on
    #    separate lines, so the value can be a hundred characters away)
    m = re.search(RANGE_LABEL + r'\b', head, re.I)
    if m:
        window = head[m.end():m.end() + 300]
        dates = [d for d in (_fulldate(*g) for g in re.findall(NUM_DATE, window)) if d]
        if dates:
            mi, yr = _closing_month(dates[-1], dates[0] if len(dates) > 1 else None)
            return mi, str(yr), f"{m.group(1)} {' '.join(window.split())[:40]}"

    # 4. explicitly labelled single date (never a bare "Date:")
    m = re.search(DATE_LABEL + r'\s*[:\-]?\s*' + NUM_DATE, head, re.I)
    if m:
        got = _pdate(m.group(2), m.group(3), m.group(4))
        if got:
            return got[0], str(got[1]), m.group(0).strip()
    m = re.search(DATE_LABEL + r'\b', head, re.I)
    if m:
        window = head[m.end():m.end() + 200]
        dates = [d for d in (_pdate(*g) for g in re.findall(NUM_DATE, window)) if d]
        if dates:
            return dates[0][0], str(dates[0][1]), f"{m.group(1)} {' '.join(window.split())[:40]}"

    # 5. month-name forms
    for p in (r'(?:Statement|Billing|Activity)\s*(?:Period|Date)?\s*[:\-]?\s*'
              + MONTH_RE + r'\w*\.?\s+\d{1,2},?\s*(20\d\d)',
              r'For the (?:month|period) (?:of|ending|ended)\s*' + MONTH_RE + r'\w*\.?,?\s*(20\d\d)',
              MONTH_RE + r'\s+\d{1,2},?\s*(20\d\d)\s*(?:through|-|to|–)\s*' + MONTH_RE):
        m = re.search(p, head, re.I)
        if m:
            mi = MONTHS.get(m.group(1)[:3].lower())
            if mi:
                return mi, _norm_year(m.group(2)), m.group(0).strip()

    # 5b. A FULL date ("Jul 31, 2026") before a bare one ("Aug 2021").
    #
    # Edward Jones prints a five-year performance graph whose x-axis reads
    # "Aug 2021 | Feb | Aug 2022 | Feb | Aug 2023 ...", and that axis sits
    # ABOVE the statement's own date on the page. The bare month-and-year
    # pattern below matched the first axis label and dated every one of those
    # statements to 2021 — five years out. A bare month and year is as likely to
    # be a chart axis as a date; a full date with a day in it is not. Taking the
    # most frequent one also beats taking the first, since the real date is
    # repeated in headers and footers while an axis label appears once.
    full = [(MONTHS.get(mo[:3].lower()), _norm_year(yr)) for mo, yr in
            re.findall(MONTH_RE + r'\s+\d{1,2},\s*(20\d\d)', head, re.I)]
    full = [f for f in full if f[0]]
    if full:
        mode = max(set(full), key=full.count)
        if full.count(mode) >= 2:
            return mode[0], mode[1], 'most frequent full date (%s/%s)' % mode

    m = re.search(MONTH_RE + r'\s*(20\d\d)', head, re.I)
    if m:
        mi = MONTHS.get(m.group(1)[:3].lower())
        if mi:
            return mi, _norm_year(m.group(2)), m.group(0).strip()

    # 6. last resort: some banks print only a transaction table. Use the most
    #    common month among the dates in it.
    dates = [d for d in (_pdate(*g) for g in re.findall(NUM_DATE, head)) if d]
    if len(dates) >= 3:
        mode = max(set(dates), key=dates.count)
        if dates.count(mode) >= 3:
            return mode[0], str(mode[1]), f"inferred from transaction dates ({mode[0]}/{mode[1]})"
    return None, None, None


def covered_months(text):
    """Every month a statement actually covers.

    Some statements bundle two months ("Cap 1 HYSA Jan-Feb"). Crediting only one
    of them makes the other look missing, so gap detection needs the full span.
    """
    head = text[:6000]
    m = re.search(RANGE_LABEL + r'\s*[:\-]?\s*' + NUM_DATE
                  + r'\s*(?:thru|through|to|-|–)\s*' + NUM_DATE, head, re.I)
    if not m:
        return None
    start = _fulldate(m.group(2), m.group(3), m.group(4))
    end = _fulldate(m.group(5), m.group(6), m.group(7))
    if not (start and end):
        return None
    sm, sy, sd = start
    em, ey = _closing_month(end, start)
    ed = end[2]
    # An ordinary billing cycle crosses a month boundary (Citi runs 12/04-01/05)
    # but is still ONE monthly statement. Only a genuinely long period covers
    # multiple months, so require appreciably more than a single cycle.
    days = ((ey - sy) * 12 + (em - sm)) * 30 + (ed - sd)
    if days <= 45:
        return None
    span = (ey - sy) * 12 + (em - sm)
    if span <= 0 or span > 11:
        return None
    out, y, mo = [], sy, sm
    for _ in range(span + 1):
        out.append((y, mo))
        mo += 1
        if mo > 12:
            mo, y = 1, y + 1
    return out


def primary_year(text, doc_type=None):
    """The year the document is ABOUT, not every year it mentions."""
    head = text[:4000]
    for p in (r'For the year Jan\.?\s*1[^\n]{0,40}?(20\d\d)',
              r'for calendar year (20\d\d)',
              r'[Tt]ax [Yy]ear\s*:?\s*(20\d\d)',
              r'beginning[^\n]{0,30}(20\d\d)[^\n]{0,30}ending',
              r'Form\s*1040[^\n]{0,40}?(20\d\d)',
              r'Form\s*1120-?S[^\n]{0,40}?(20\d\d)',
              r'\bW-?2\b[^\n]{0,40}?(20\d\d)',
              r'(20\d\d)\s*W-?2\b'):
        m = re.search(p, head, re.I)
        if m:
            return m.group(1)

    mon, yr, _ = statement_period(text)
    if yr:
        return yr

    # Wage forms print the tax year as a bare number, often the only year on the
    # page, and OCR frequently mangles the words around it ("ignmoekonen 2024").
    # So for these types accept a bare plausible year — but never one glued to a
    # longer digit run, which is how a ZIP (73105) or a suite number (Ste 2059)
    # gets mistaken for a tax year.
    if doc_type in ('w2', 'paystub'):
        cands = [m.group(1) for m in re.finditer(r'(?<![\d-])(20[12]\d)(?![\d-])', text)]
        cands = [c for c in cands if 2015 <= int(c) <= 2030]
        if cands:
            from collections import Counter
            return Counter(cands).most_common(1)[0][0]

    def plausible(ys):
        return [y for y in ys if 2015 <= int(y) <= 2035]
    for scope in (head, text):
        years = plausible(re.findall(r'\b(20[0-3]\d)\b', scope))
        if years:
            return max(set(years), key=years.count)
    return None


def granularity(text):
    """monthly / annual / quarterly / ytd / period."""
    head = text[:6000]
    m = re.search(r'From\s*(?:EOM|EOD):?\s*' + MONTH_RE + r'[^\n]{0,30}?To\s*(?:EOM|EOD):?\s*'
                  + MONTH_RE, head, re.I)
    if m:
        a, b = MONTHS.get(m.group(1)[:3].lower()), MONTHS.get(m.group(2)[:3].lower())
        if a and b:
            span = (b - a) % 12
            return 'monthly' if span == 0 else ('annual' if span >= 10 else 'period')

    # a full year, even though a month is named
    if has(head, r'Jan(?:uary)?\s*\d{0,2}\s*[-–]\s*Dec(?:ember)?\s*\d{0,2},?\s*20\d\d',
           r'Jan(?:uary)?\s*\d{0,2},?\s*20\d\d[^\n]{0,25}Dec(?:ember)?\s*\d{0,2},?\s*20\d\d',
           r'for the year end', r'annual (?:summary|report|statement)'):
        return 'annual'
    if has(head, r'\bquarterly statement\b', r'\bquarter-to-date\b', r'\bQ[1-4]\s*20\d\d'):
        return 'quarterly'
    if has(head, r'\bYTD\b', r'year to date', r'January\s+1[^\n]{0,30}(through|to|-)'):
        return 'ytd'
    if has(head, r'Statement Period', r'Statement Dates?', r'Billing Period',
           r'for the month', r'monthly (?:statement|summary|report)'):
        return 'monthly'
    return None


ISSUERS = [
    ('Arvest', r'\bArvest\b'), ('BancFirst', r'\bBanc\s?First\b|\bBNCF\b'),
    ('Capital One', r'\bCapital\s?One\b|\bCap\s?1\b'),
    ('Eastman CU', r'\bEastman\b'),
    ('Cash App', r'\bCash\s?App\b|\bBlock,?\s*Inc\b'),
    ('Citibank', r'\bCiti(?:bank|business)?\b|CITI®'),
    ('Chase', r'\bChase\b|JPMorgan'), ('Bank of America', r'Bank of America'),
    ('Wells Fargo', r'Wells Fargo'), ('American Express', r'American Express|\bAmex\b'),
    ('Fidelity', r'\bFidelity\b'), ('Vanguard', r'\bVanguard\b'), ('Schwab', r'\bSchwab\b'),
    ('SoonerSave', r'\bSoonerSave\b'), ('LPL Financial', r'\bLPL\s*FINANCIAL\b'),
    ('Mass Mutual', r'Mass\s?Mutual'), ('Farmers', r"\bFarmer'?s?\b"),
    ('Principal', r'\bPrincipal\b'), ('Guardian', r'\bGuardian\b'),
    ('The Standard', r'\bThe Standard\b|Standard Insurance'),
    ('TransUnion', r'\bTransUnion\b'), ('Equifax', r'\bEquifax\b'),
    ('Experian', r'\bExperian\b'),
    # An institution missing from this list is worse than it sounds: with no
    # match on the letterhead, the earliest-wins rule below falls through to
    # whatever bank is namechecked in the transaction table. Every Fifth Third
    # statement in the Spaulding file came back as Chase or Citibank that way,
    # which split one account across three series.
    ('Fifth Third', r'\bFifth\s*Third\b|www\.53\.com'),
    ('Huntington', r'\bHuntington\s*(?:National\s*)?Bank\b|\bHuntington\b'),
    ('Edward Jones', r'Edward\s*Jones|\bEDWARDJONES\b'),
    ('T. Rowe Price', r'T\.?\s*Rowe\s*Price'),
    ('Coinbase', r'\bCoinbase\b'),
    ('Optum', r'\bOptum\s*(?:Bank|Financial)?\b'),
    # Reads its own name plainly on the letterhead — it just was not on this
    # list, so the earliest-wins rule fell through to a bank named in the
    # transaction table and every HSA statement came back as someone else's.
    ('HSA Bank', r'\bHSA\s*Bank\b'),
    # The investment side of an HSA. Its statements carry a disclosure reading
    # "Custodial services provided by DriveWealth, LLC, Citibank, N.A., RBC..."
    # — three institutions in one sentence, none of which issued the statement.
    # DriveWealth's own name appears just before it, so earliest-wins picks the
    # right one once it is on this list.
    ('DriveWealth', r'\bDriveWealth\b'),
    ('Health Equity', r'\bHealth\s*Equity\b'),
    ('Fidelity HSA', r'\bFidelity\s*HSA\b'),
    ('Ameriprise', r'\bAmeriprise\b'),
    ('Merrill', r'\bMerrill\s*(?:Lynch|Edge)?\b'),
    ('Morgan Stanley', r'Morgan\s*Stanley|\bE\*?TRADE\b'),
    ('PNC', r'\bPNC\s*Bank\b'), ('Truist', r'\bTruist\b'),
    ('US Bank', r'\bU\.?S\.?\s*Bank\b'), ('Regions', r'\bRegions\s*Bank\b'),
    ('KeyBank', r'\bKeyBank\b'), ('Citizens', r'\bCitizens\s*Bank\b'),
    ('First Merchants', r'\bFirst\s*Merchants\b'),
    ('Old National', r'\bOld\s*National\b'),
]


def issuer(text):
    """Whoever appears EARLIEST wins, not whoever is first in our list.

    A Capital One statement can mention "Preauthorized Deposit from ARVEST BANK"
    in its transaction table; scanning in list order made that statement Arvest's.
    The institution that issued the document is the one on the letterhead.
    """
    head = text[:6000]
    best, best_pos = None, len(head) + 1
    for name, pat in ISSUERS:
        m = re.search(pat, head, re.I)
        if m and m.start() < best_pos:
            best, best_pos = name, m.start()
    return best


def account_tail(text):
    """Last 4 of the account number.

    Deliberately strict: it must be explicitly labelled or masked. A loose
    "any four digits" rule happily returns a ZIP code or a phone fragment, and a
    wrong account number silently splits one statement series into two and
    invents a missing month.

    Whichever candidate appears EARLIEST wins, not whichever pattern is listed
    first — the same lesson `issuer` above already learned. Fifth Third prints
    "Account Number: 5550142398" on the letterhead and then, pages later, a
    transaction reading "5/3 COMMRCL LN #XXXXXXXXXXX0026". Trying the masked
    pattern first gave every one of those statements the loan's last four, which
    split one account into several series and invented missing months.
    """
    head = text[:6000]
    best, best_pos = None, len(head) + 1
    for p in (r'[Xx*#]{3,}[\- ]?(\d{4})\b',
              r'(?:ending in|ending with|ending)\s*[:#*]?\s*(\d{4})\b',
              r'acc(?:oun)?t\.?\s*(?:number|no\.?|#)\s*[:#]?\s*(?:[Xx*#\- ]*)(\d{4,17})\b',
              r'(?:Primary|Member)\s*Account\s*[:#]?\s*(?:[Xx*#\- ]*)(\d{4,17})\b'):
        m = re.search(p, head, re.I)
        if m and m.start() < best_pos:
            digits = re.sub(r'\D', '', m.group(1))
            if len(digits) >= 4:
                best, best_pos = digits[-4:], m.start()
    if best:
        return best

    # label and value on separate lines (common in bank statement tables):
    # "ACCOUNT NUMBER" ... then "009-5550142" further down
    m = re.search(r'acc(?:oun)?t\s*number\b', head, re.I)
    if m:
        window = head[m.end():m.end() + 200]
        m2 = re.search(r'\b(\d{3}-\d{7}|\d{8,17})\b', window)
        if m2:
            return re.sub(r'\D', '', m2.group(1))[-4:]
    return None


# --------------------------------------------------------------------------
# rules: test(head, full)
# --------------------------------------------------------------------------
Rule = namedtuple('Rule', 'doc_type label side test')


def _r(doc_type, label, side, test):
    return Rule(doc_type, label, side, test)


# Labels that can honestly describe the same document. Kept deliberately small:
# every pair here is one a practice actually prints together.
COUNTS_FAMILY = {'day_sheet', 'provider_productivity', 'production_report',
                 'total_patients', 'new_patients', 'dr_days_worked'}

RULES = [
    # credit reports first: they are long and quote every financial term there is
    # Tested on the FULL text, not the head. Daniel's 51-page report says "credit
    # report" 11 times and "Experian" 9 times, none of it inside the first 3500
    # characters, so a head-only test called it "unknown" while Sara's — same kind
    # of document — classified fine. A repetition threshold keeps a passing
    # mention on some other document from matching.
    # Early, because an engagement letter names every service the firm performs
    # — bookkeeping, tax returns, QuickBooks — and later rules would grab it on
    # those words. Spaulding's is filed as "Service Agreement.pdf" and calls
    # itself both names in its own second paragraph.
    _r('engagement_letter', 'Engagement letter', None,
       lambda h, t: has(h, r'engagement letter', r'\bservice agreement\b',
                        r'terms and objectives of our engagement',
                        r'scope of services to be provided',
                        r'this letter is to confirm our understanding')),
    # Dentrix practice-analysis reports. Three different layouts, all production
    # data, and all previously wrong: the production summary read as a fee
    # schedule (it lists procedure codes with totals, which is what a fee
    # schedule looks like from a distance), the provider summary read as
    # unknown, and the practice analysis read as new_patients. Ahead of those
    # rules because the report titles are unambiguous where the contents are not.
    _r('production_report', 'Practice analysis (production)', 'Practice',
       lambda h, t: has(h, r'practice analysis\s*-\s*production summary',
                        r'analysis summary\s*\(\s*provider\s*\)',
                        r'\bpractice analysis\b')),

    # A payer-mix export: carriers down one column, patient or plan counts down
    # the next. Before the generic insurance rules, which look for policy
    # language — this is a spreadsheet ABOUT insurers, not a policy.
    _r('insurance_carriers', 'Insurance carrier list / plan mix', 'Practice',
       lambda h, t: has(h, r'insurance carrier', r'insurance (?:plan )?mix',
                        r'carrier counts?', r'in-?network carriers?')
                    and has(h, r'\bcounts?\b', r'%\s*of\s*total', r'\brank\b',
                            r'plan count')),
    _r('credit_report', 'Credit report', 'Personal',
       lambda h, t: has(h, r'credit report\b', r'\bTransUnion\b', r'\bEquifax\b',
                        r'\bExperian\b', r'\bFICO\b')
                    or count(t, r'credit report\b') >= 3
                    or count(t, r'\bTransUnion\b', r'\bEquifax\b', r'\bExperian\b') >= 3),

    # ---- practice production ------------------------------------------
    # Written against real Open Dental exports. Both files carry the same column
    # vocabulary — "Tot Prod", "Pt Income", "Ins Income" — and differ only in
    # whether rows are months or days, so the date column decides which is which.
    _r('day_sheet', 'Daily production (day sheet)', 'Practice',
       lambda h, t: has(h, r'\bTot\s*Prod\b') and has(h, r'\bPt\s*Income\b|\bIns\s*Income\b')
                    and has(h, r'^\s*Date\b|\|\s*Date\s*\||\bDate\s*\|\s*Day\b')),
    _r('production_report', 'Production and income report', 'Practice',
       lambda h, t: has(h, r'\bTot\s*Prod\b')
                    and has(h, r'\bPt\s*Income\b|\bIns\s*Income\b|Unearned\s*Pt')),

    # ---- tax ----------------------------------------------------------
    # 1099s arrive as consolidated broker/payer statements that rarely say
    # "1099" in a heading — "Tax Statement for Forms 1099" is the giveaway.
    # The form number itself is often the first thing OCR loses — Jon's came
    # through as noise on a 663-character read. The surrounding boilerplate
    # survives, and "Tax Statement for Forms ... for Tax Year" is only ever a
    # consolidated 1099.
    # A filed personal return is delivered as a packet whose cover sheet is Form
    # 8879, the IRS e-file authorisation. Inside are the 1099s that fed it — so
    # the 1099 rule below fired first and called a 91-page 1040 a 1099. Form 8879
    # exists only to authorise the e-filing of a personal return, which makes it
    # a safe thing to lead on.
    _r('personal_tax_return', 'Personal tax return (e-file packet)', 'Personal',
       lambda h, t: has(h, r'form\s*8879')
                    and has(h, r'e-?file signature authorization', r'1545-0074')),

    _r('form_1099', '1099 income statement', 'Personal',
       lambda h, t: has(h, r'\b1099\b')
                    or (has(h, r'tax statement for forms')
                        and has(h, r'for tax year|omb'))),

    _r('personal_tax_return', 'Personal tax return (Form 1040)', 'Personal',
       lambda h, t: has(h, r'Form\s*1\s*040\b', r'U\.?S\.?\s*Individual Income Tax Return')),

    # A preparer's packet opens with a cover letter and a carryover summary, so
    # "Form 1040" may not appear for several pages — only a bare "1040" as a form
    # number. Meanwhile the carryover page lists "Traditional IRA Basis" and
    # "Roth IRA Conversion Basis", which is enough for the brokerage rule below.
    # Spaulding's 2024 and 2025 returns were filed as investment statements that
    # way, and the tax-return checklist item was satisfied by their daughter's
    # returns instead. Needs the form number AND language no statement carries.
    _r('personal_tax_return', 'Personal tax return (preparer packet)', 'Personal',
       lambda h, t: has(h, r'\b1\s?040\b')
                    and has(h, r'return carryover summary', r'two year comparison',
                            r'taxpayer identification number',
                            r'overpayment applied', r'qualified business income deduction')),

    # A preparer's packet whose cover pages carry no form number at all.
    # Katherine Rebol's 2023 return opens with the accountant's letterhead and a
    # two-year income comparison; "1040" does not appear anywhere in the first
    # 3500 characters. With no form number the rules above cannot fire, and the
    # phrase "HEALTH SAVINGS ACCOUNT DEDUCTION" in its income summary was enough
    # to file it as a bank statement.
    #
    # No single phrase here is decisive, so it takes four. "Adjusted gross
    # income" beside "married filing jointly" beside "taxable income" is a tax
    # return; nothing else in a client folder talks that way.
    _r('personal_tax_return', 'Personal tax return (preparer packet, no form number)', 'Personal',
       lambda h, t: sum(bool(re.search(p_, h, re.I)) for p_ in (
           r'married filing (?:jointly|separately)', r'adjusted gross income',
           r'taxable income', r'total income', r'overpayment applied',
           r'itemi[sz]ed deductions?', r'standard deduction',
           r'filing status', r'refund')) >= 4),

    # State returns never say 1040. Indiana files an IT-40, Oklahoma a 511, and
    # each state has its own number, so match the shape rather than the digits.
    _r('personal_tax_return', 'Personal tax return (state)', 'Personal',
       lambda h, t: has(h, r'\bIT-?\s*40\b', r'\b5\s*11\b', r'state form',
                        r'declaration of electronic filing')
                    and has(h, r'individual income tax')),
    _r('business_tax_return', 'Practice tax return (Form 1120-S)', 'Practice',
       lambda h, t: has(h, r'Form\s*1120-?\s?S\b', r'Income Tax Return for an S Corporation',
                        r'Small Business Corporation Income Tax')),
    _r('partnership_tax_return', 'Partnership tax return (Form 1065)', 'Practice',
       lambda h, t: has(h, r'Form\s*1065\b', r'Return of Partnership Income')),
    _r('k1', 'Schedule K-1', 'Practice',
       lambda h, t: has(h, r'Schedule\s*K-?1\b', r"Partner'?s Share of Income",
                        r"Shareholder'?s Share of Income")),
    _r('schedule_e', 'Schedule E (rental income)', 'Personal',
       lambda h, t: has(h, r'Schedule\s*E\b[^\n]{0,60}Supplemental Income',
                        r'Supplemental Income and Loss')),
    _r('w2', 'W-2 wage statement', 'Personal',
       lambda h, t: has(h, r'\bW-?2\s*(?:Wage|and Tax Statement)', r'Wage and Tax Statement')),
    # Widened after Sara's paystub came back "unknown". Its OCR reads
    # "Pers Earn Stmt-SHUGO", "Period Begin", "Check Type", "Earnings Summary",
    # "Total Gross Pay", "Net Pay" — so the old rule failed on every branch:
    # "earnings statement" was abbreviated, "Pay Period Begin" was "Period Begin",
    # and "Check Date" was "Check Type". The pairing requirement is what keeps a
    # payroll summary or a W-2 from matching.
    _r('paystub', 'Paystub / earnings statement', 'Personal',
       lambda h, t: has(h, r'earnings statement', r'\bpay\s?stub\b',
                        r'earn(?:ings)?\.?\s*stmt', r'earnings summary')
                    or (has(h, r'(?:pay\s+)?period\s+(?:begin|end)', r'\bcheck\s+(?:date|type)\b',
                              r'\bvoucher\b', r'\bhire\s+date\b')
                        and has(h, r'\b(?:total\s+)?gross\s+pay\b', r'\bnet\s+pay\b',
                                  r'\bdir\s+dep\b'))),
    _r('payroll_summary', 'Payroll summary', 'Practice',
       lambda h, t: has(h, r'payroll summary', r'payroll (?:register|journal)',
                        r'total (?:employer )?payroll (?:taxes|cost)')),

    # ---- practice production / financials ------------------------------
    _r('provider_productivity', 'EagleSoft Provider Productivity report', 'Practice',
       lambda h, t: has(h, r'PROVIDER\s+PRODUCTIVITY')),
    _r('day_sheet', 'EagleSoft Day Sheet report', 'Practice',
       lambda h, t: has(h, r'\bDay\s*Sheet\b', r'DAYSHEET')),
    _r('balance_sheet', 'Balance sheet', 'Practice',
       lambda h, t: has(h, r'\bBalance\s*Sheet\b')),
    # "Total for Income" is QuickBooks' wording; a bare "Total Income" test
    # silently missed every P&L this practice sends
    _r('pnl', 'Profit & loss / income statement', 'Practice',
       lambda h, t: has(h, r'Profit\s*(?:and|&)\s*Loss', r'\bIncome Statement\b')
                    or (has(h, r'Net (?:Ordinary )?Income')
                        and has(h, r'Total\s+(?:for\s+)?(?:Income|Revenue|Expenses?)'))),
    _r('fee_schedule', 'Fee schedule', 'Practice',
       lambda h, t: has(h, r'fee schedule') or count(t, r'\bD[0-9]{4}\b') >= 8),
    _r('new_patients', 'New patient counts', 'Practice',
       lambda h, t: has(h, r'new patient(?:s)? (?:count|report|by month)', r'\bNew Patients\b')),
    # What a building is thought to be worth. The request asks for a
    # guesstimate, so this is nearly always a two-line spreadsheet or a typed
    # figure rather than an appraisal — Rebol's read "Aproximate Value of
    # Office Buildings" (the client's spelling) over two addresses. Matching
    # "approx" strictly would have missed it, which is the whole reason this
    # reads content loosely and requires a value word plus a building word.
    _r('building_value', 'Building value estimate', 'Practice',
       lambda h, t: (has(h, r'value') and has(h, r'building|propert|real estate'))
                    and not has(h, r'balance sheet|profit\s*(?:and|&)\s*loss')),

    # Clients answer these three by typing a handful of numbers into a Word
    # document — "Total Patients: 2024- 3164 patients". Both were on the filing
    # map and in the vocabulary, but nothing ever RECOGNISED them, so they came
    # out unknown and the checklist reported them missing with the file sitting
    # in the folder. New patients worked only because that rule already existed.
    #
    # After new_patients on purpose: "Total New Patients" must not be read as a
    # total patient count, which is the same distinction the vocabulary makes.
    _r('total_patients', 'Total patient counts', 'Practice',
       lambda h, t: has(h, r'total\s+patients?\b', r'patients?\s+seen\b')
                    and has(h, r'\d')),
    _r('dr_days_worked', 'Doctor days worked', 'Practice',
       lambda h, t: has(h, r'(?:doctor|dr\.?)\s+days\s+worked',
                        r'total\s+(?:doctor|dr\.?)\s+days',
                        r'days\s+worked\b')
                    and has(h, r'\bdays?\b')),

    # ---- statements -----------------------------------------------------
    _r('cc_statement', 'Credit card statement', None,
       lambda h, t: has(h, r'minimum payment (?:due|amount)', r'payment due date',
                        r'credit (?:line|limit)', r'available credit', r'\bAADVANTAGE\b')
                    and has(h, r'statement|transactions|new balance|billing')),
    _r('brokerage_statement', 'Investment / brokerage statement', 'Personal',
       lambda h, t: has(h, r'\bbrokerage\b', r'\bIRA\b', r'\b401\s?\(?k\)?\b', r'\b457\b',
                        r'\b529\b', r'\bRoth\b', r'portfolio (?:value|summary)',
                        r'\bmutual fund\b', r'market value', r'\bshares\b')),
    # Two tiers, because one weak phrase is not a bank statement.
    #
    # "savings account" alone used to be enough, and a 1040 carrying the line
    # "HEALTH SAVINGS ACCOUNT DEDUCTION" in its income summary was filed as a
    # Citizens bank statement into Business/Banking. The word "citizens"
    # elsewhere on the return supplied a plausible issuer and the direct-deposit
    # section supplied an account number, so nothing downstream looked wrong.
    #
    # The strong phrases below only ever appear on a real statement, so they
    # still stand alone. The weak ones — an account TYPE, which any document can
    # mention — now need a statement-shaped signal beside them.
    _r('bank_statement', 'Bank statement', None,
       lambda h, t: has(h, r'beginning balance', r'ending balance',
                        r'deposits and (?:other )?credits',
                        r'withdrawals and (?:other )?debits',
                        r'summary of accounts', r'account statement')
                    or (has(h, r'(?<!health )(?<!flexible )checking account',
                            r'(?<!health )savings account', r'money market')
                        and has(h, r'statement period', r'statement date',
                                r'\bbalance\b', r'\bdeposits?\b', r'\bwithdrawals?\b',
                                r'transactions?'))),

    # ---- insurance ------------------------------------------------------
    _r('disability_insurance', 'Disability insurance policy', 'Personal',
       lambda h, t: has(h, r'disability') and has(h, r'policy|insurance|benefit')),
    _r('overhead_insurance', 'Business overhead expense insurance', 'Practice',
       lambda h, t: has(h, r'business overhead', r'overhead expense')
                    and has(h, r'policy|insurance|premium|payment')),
    # "Dependent Life - HealthChoice Standard Option ... Benefit Election Details"
    # came back unknown: employer benefit elections say "dependent life" or
    # "spouse life", never "life insurance", and show a coverage amount rather
    # than a policy or premium.
    # An HSA custodian statement reads like a bank statement but belongs with the
    # health accounts, and the bank rules were not catching it at all.
    _r('hsa_statement', 'HSA statement', 'Personal',
       lambda h, t: has(h, r'\bHSA\b', r'health savings')
                    and has(h, r'participant|account id|statement|contributions|custodian')),

    # A screenshot of the insurer's customer portal, which is how clients often
    # send this rather than the policy document. Kelly's says "Face Amount",
    # "Base $63,010.00", "Individual Term" and "Annuity Rider" — and never once
    # says "life insurance", so every rule below missed it and it landed on the
    # reviewer's desk as an unknown. "Face amount" is life-insurance vocabulary
    # and almost nothing else uses it.
    _r('life_insurance', 'Life insurance (portal summary)', 'Personal',
       lambda h, t: has(h, r'face amount')
                    and has(h, r'\bpremium\b', r'annuity rider', r'\bterm\b',
                            r'\bpolicy\b', r'\bbenefits?\b')),
    _r('life_insurance', 'Life insurance policy', 'Personal',
       lambda h, t: (has(h, r'life insurance', r'term life', r'whole life', r'\bAD&D\b',
                         r'dependent life', r'spouse life', r'basic life',
                         r'supplemental life', r'member life')
                     # "Member Life 10 Year Term" splits the phrase apart, so
                     # accept life AND term appearing separately as well.
                     or (has(h, r'\blife\b') and has(h, r'\b\d+\s*year\s*term\b|\bterm\b')))
                    and has(h, r'policy|coverage|premium|face amount|benefit election')),
    _r('property_insurance', 'Property / homeowners insurance', 'Personal',
       lambda h, t: has(h, r'homeowners?', r'dwelling coverage', r'property insurance')
                    and has(h, r'declaration|policy|premium')),
    _r('insurance_policy', 'Insurance policy (other)', None,
       lambda h, t: has(h, r'declarations? page', r'policy number')
                    and has(h, r'premium|coverage')),

    # ---- leases / debts / practice admin --------------------------------
    _r('rental_lease', 'Rental property lease', 'Personal',
       lambda h, t: has(h, r'lease agreement', r'residential lease', r'rental agreement',
                        r'\blessor\b[^\n]{0,80}\blessee\b',
                        r'\blandlord\b[^\n]{0,80}\btenant\b')),
    _r('staff_roster', 'Staff roster', 'Practice',
       lambda h, t: has(h, r'staff roster')
                    or (has(h, r'\bhygiene\b', r'\bhygienist\b')
                        and has(h, r'office manager|front office|assistants')
                        and has(h, r'hours\s*/\s*week|hours/week|hours per week|average \d+ hours'))),
    _r('practice_hours', 'Practice hours', 'Practice',
       lambda h, t: has(h, r'office hours', r'practice hours', r'hours of operation')),
    _r('bonus_structure', 'Bonus structure', 'Practice',
       lambda h, t: has(h, r'bonus (?:structure|plan|program)', r'\bbonus\b')),
    _r('provider_schedule', 'Provider schedule', 'Practice',
       lambda h, t: has(h, r'provider schedule', r'doctor schedule', r'hygiene schedule')),
    _r('debt_schedule', 'Debt schedule', None,
       lambda h, t: has(h, r'\bdebts?\b')
                    and has(h, r'balance|interest rate|payoff|monthly payment')),
    # After debt_schedule on purpose: a debt sheet that happens to LIST a line of
    # credit is still a debt sheet. This is for the LOC's own paperwork — the
    # bank's statement or agreement for the facility itself. No forced side; a
    # practice and a household can each hold one.
    _r('line_of_credit', 'Line of credit', None,
       lambda h, t: has(h, r'line of credit', r'\bLOC\b', r'revolving credit')
                    and has(h, r'credit limit|available credit|draw|advance|'
                               r'outstanding balance|interest rate|apr')),
]


PERSONAL_HINTS = [r'\bpersonal\b', r'\bindividual\b', r'\bjoint\b']
PRACTICE_HINTS = [r'\bPLLC\b', r'\bLLC\b', r'\bP\.?C\.?\b', r'Family Dentistry',
                  r'\bpractice\b', r'\bemployer\b', r'\bbusiness\b', r'\bDDS\b', r'\bDMD\b']


# Short account-kind tags for filenames: "Sara Chk (BancFirst) x4108".
# Ordered most specific first — "Roth IRA" must read as Roth, not IRA.
ACCOUNT_KINDS = [
    ('HSA',  r'\bh\.?s\.?a\.?\b|health\s+savings'),
    ('529',  r'\b529\b|college\s+savings'),
    ('457',  r'\b457\b'),
    ('401k', r'401\s?\(?k\)?'),
    ('403b', r'403\s?\(?b\)?'),
    ('Roth', r'\broth\b'),
    ('IRA',  r'\bira\b'),
    ('HYSA', r'high[- ]?yield|\bhysa\b'),
    ('MM',   r'money\s*market|\bmmkt\b|\bmma\b'),
    ('CD',   r'certificate\s+of\s+deposit'),
    ('Chk',  r'\bchecking\b|\bchk\b|free\s+blue|total\s+checking'),
    ('Sav',  r'\bsavings\b'),
    ('Brok', r'brokerage|investment\s+account|securities'),
    ('CC',   r'credit\s*card|\bvisa\b|mastercard|amex|minimum\s+payment'),
]
_KIND_DEFAULT = {'cc_statement': 'CC', 'brokerage_statement': 'Brok', 'bank_statement': 'Bank stmt'}


def account_kind(text, doc_type, account_tail=None):
    """Checking / savings / Roth / IRA and so on, for the filename.

    Searched in a NARROW window around the account number, not across the header.
    Scanning the first few thousand characters put every Arvest account down as a
    money market (a rate-disclosure table lists every product the bank offers) and
    every Vanguard account as a 529 (mentioned in the footer). The product name
    that matters is the one printed beside the account number.
    """
    if doc_type not in ('bank_statement', 'cc_statement', 'brokerage_statement'):
        return None
    windows = []
    tail = str(account_tail or '')
    if tail:
        for m in re.finditer(re.escape(tail), text):
            windows.append(text[max(0, m.start() - 140):m.start() + 60])
    windows.append(text[:400])              # statement header, as a fallback
    for w in windows:
        for name, pat in ACCOUNT_KINDS:
            if re.search(pat, w, re.I):
                return name
    return _KIND_DEFAULT.get(doc_type)


def infer_side(head, doc_type, practice_names=(), full=None, home_tokens=()):
    """Personal vs Practice for types that can be either (bank / CC statements).

    The practice's own entity name is searched across the WHOLE document, not just
    the head: on a bank statement the practice is usually named in a transfer or
    deposit line in the transaction body, not on the cover. Restricting this to the
    head found nothing on statements that plainly say "Rose Rock Family Dentistry"
    twenty lines down.

    The looser keyword hints stay on the head only. Counting words like "business"
    or "practice" across a whole statement is noise.
    """
    hay = full or head
    for pn in practice_names:
        if pn and re.search(re.escape(pn), hay, re.I):
            return 'Practice'
        # Also try the distinctive leading words, since OCR mangles suffixes
        # ("PLLC" -> "PLLG") far more often than it mangles a proper name.
        lead = ' '.join(str(pn).split()[:2])
        if len(lead) >= 6 and re.search(re.escape(lead), hay, re.I):
            return 'Practice'

    # No business entity named, but the statement is addressed to the family home:
    # that is a personal account. This is what finally resolved the savings and
    # money-market statements — they carry almost no transactions, so there was
    # nothing else to go on, but every one of them is mailed to the house.
    # Matched on the street NAME rather than a full address, because OCR renders
    # "2624 S Black Oak Dr" as "2624 § Black Oak Dr" and a strict address pattern
    # misses it entirely.
    for tok in (home_tokens or ()):
        if tok and re.search(re.escape(tok), hay, re.I):
            return 'Personal'
    p = count(head, *PRACTICE_HINTS)
    q = count(head, *PERSONAL_HINTS)
    if p > q and p >= 2:
        return 'Practice'
    if q > p:
        return 'Personal'
    return None


STATEMENT_TYPES = ('bank_statement', 'cc_statement', 'brokerage_statement')
INSURANCE_TYPES = ('disability_insurance', 'life_insurance', 'overhead_insurance',
                   'property_insurance', 'insurance_policy')
PERIODIC = set(STATEMENT_TYPES) | {'payroll_summary', 'provider_productivity',
                                   'day_sheet', 'pnl', 'balance_sheet'}


_FINANCIAL_MARKERS = (r'account\s*(?:number|no\.?)', r'statement', r'balance', r'\binvoice\b',
                      r'\bpolicy\b', r'\bpremium\b', r'gross pay', r'\bpayroll\b',
                      r'tax return', r'\bform\s*\d', r'total\s+(?:income|expense)')


def looks_like_client_note(t, household=()):
    """A short piece of prose about the family, not a financial document.

    "College.docx" reads: "Avery Bassett graduates May 2027 from Oklahoma State
    University, Accounting degree..." — plainly a planning note, but it matched no
    document rule and came back unknown. Kept deliberately narrow: short, names a
    household member, and carries none of the structure a real financial document
    has.
    """
    if not household or len(t) > 4000:
        return False
    if has(t, *_FINANCIAL_MARKERS):
        return False
    return any(re.search(r'\b' + re.escape(p) + r'\b', t, re.I) for p in household)


def classify(text, filename='', practice_names=(), home_tokens=(), household=()):
    t = normalise(text)
    h = t[:HEAD_CHARS]

    doc = dict(doc_type='unknown', label='Unrecognised document', owner_side=None,
               year=None, month=None, period=None, granularity=None,
               issuer=None, account_tail=None, confidence='low', notes=[],
               also_types=[])

    # The one place the extension is allowed to decide. Everything else in this
    # module reads content on purpose, because filenames lie — but a QuickBooks
    # backup is a proprietary binary with no extractable text at all, so there is
    # nothing to read and the extension is the only honest signal there is.
    is_qb_backup = (re.search(r'\.(qbb|qbw|qbm)$', filename or '', re.I)
                    and len(t.strip()) < 200)
    if is_qb_backup:
        doc.update(doc_type='quickbooks_file', label='QuickBooks backup file',
                   owner_side='Practice', confidence='high',
                   notes=['identified by file type — a QuickBooks backup holds no readable text'])

    # First match wins the document's identity, but it is not always the only
    # true thing about it. Rebol's client put doctor days, total patients and
    # new patients in one table and said so in the portal — "I combined Dr.
    # Days, Patients, and New Patients into one word doc". The classifier
    # picked one label, so that document answered one checklist item and the
    # other two were chased from a client who had already sent them.
    #
    # So a document may carry extra labels — but ONLY within a declared family.
    # The first version of this recorded every rule that matched, on the theory
    # that a secondary label held to the same test as the primary was equally
    # safe. That was wrong, and measurably so: the rules are ordered and later
    # ones are written assuming earlier ones already claimed the document, so
    # collecting them all made a 1040 "also a brokerage statement" and a balance
    # sheet "also a line of credit". On Rebol it marked the investment
    # statements satisfied by a tax return — an item the client genuinely had
    # not answered, which would then never have been chased.
    #
    # Only these travel together, because they are genuinely one report in
    # practice: a day sheet or productivity report is where patient counts and
    # doctor days come from, and practices routinely put all of them on one
    # page. Everything else stays single-label.
    for rule in (() if is_qb_backup else RULES):
        try:
            hit = rule.test(h, t)
        except Exception:
            hit = False
        if not hit:
            continue
        if doc['doc_type'] == 'unknown':
            doc.update(doc_type=rule.doc_type, label=rule.label, owner_side=rule.side,
                       confidence='high')
        elif (rule.doc_type != doc['doc_type']
              and rule.doc_type not in doc['also_types']
              and doc['doc_type'] in COUNTS_FAMILY
              and rule.doc_type in COUNTS_FAMILY):
            doc['also_types'].append(rule.doc_type)

    if doc['doc_type'] == 'unknown' and looks_like_client_note(t, household):
        doc.update(doc_type='client_note', label='Client note', owner_side='Personal',
                   confidence='medium')

    doc['granularity'] = granularity(t)
    doc['year'] = primary_year(t, doc['doc_type'])

    mon, yr, raw = statement_period(t)
    is_statement = doc['doc_type'] in PERIODIC
    # A bank statement mentioning "interest paid year-to-date" is still a
    # monthly statement. But a report that IS year-to-date -- a YTD P&L, a YTD
    # Day Sheet -- must not be pinned to a single month, or it collides with
    # that month's real report and looks like a duplicate.
    suppress = doc['granularity'] in ('annual', 'quarterly') or (
        doc['granularity'] == 'ytd' and doc['doc_type'] not in STATEMENT_TYPES)
    if mon and not suppress:
        doc['month'], doc['period'] = mon, raw
        if yr:
            doc['year'] = yr if is_statement else (doc['year'] or yr)
        if is_statement and doc['granularity'] in (None, 'ytd'):
            doc['granularity'] = 'monthly'
    elif raw:
        doc['period'] = raw

    # issuer and account number only mean something on a statement or a policy;
    # read off a tax return they just pick up whichever bank is mentioned inside
    if doc['doc_type'] in STATEMENT_TYPES + INSURANCE_TYPES:
        doc['issuer'] = issuer(t)
        doc['account_tail'] = account_tail(t)

    if doc['month'] and is_statement:
        cov = covered_months(t)
        if cov and len(cov) > 1:
            doc['covers'] = cov
            doc['notes'].append(
                "covers " + ", ".join(f"{MONTH_NAMES[m]} {y}" for y, m in cov))

    if doc['owner_side'] is None:
        doc['owner_side'] = infer_side(h, doc['doc_type'], practice_names, full=t,
                                       home_tokens=home_tokens)
    doc['account_kind'] = account_kind(t, doc['doc_type'], doc.get('account_tail'))
    if doc['doc_type'] != 'unknown' and doc['owner_side'] is None:
        doc['notes'].append('personal vs practice unclear - needs a human call')
    if doc['doc_type'] == 'unknown' and len(t.strip()) < 100:
        doc['notes'].append('little or no extractable text - may be a scan that failed OCR')

    doc['series_key'] = series_key(doc)
    return doc


def series_key(doc):
    """Identity of the recurring series a document belongs to, so the reconciler
    can spot a missing month. None for one-off documents."""
    if doc['doc_type'] not in PERIODIC:
        return None
    if doc.get('granularity') in ('annual', 'quarterly'):
        return None
    return '|'.join([doc['doc_type'], doc.get('issuer') or '',
                     doc.get('account_tail') or '', doc.get('owner_side') or ''])


def describe(doc):
    bits = [doc['label']]
    if doc.get('issuer'):
        bits.append(doc['issuer'])
    if doc.get('account_tail'):
        bits.append('x' + doc['account_tail'])
    if doc.get('month') and doc.get('year'):
        bits.append(f"{MONTH_NAMES[doc['month']]} {doc['year']}")
    elif doc.get('year'):
        bits.append(str(doc['year']))
    return ' · '.join(bits)
