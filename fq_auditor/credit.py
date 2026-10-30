#!/usr/bin/env python3
"""Credit reports: every account the bureaus know about, as debt rows.

    python3 credit.py "<client folder>"          # print what was found

A credit report is where most of a household's debt shows up in one place:
mortgages, HELOCs, car loans, student loans, cards, and practice loans the
owner has guaranteed. Statements and the Debt Sheet only show what the client
chose to send.

HOW IT READS THEM
    Equifax's own PDF is text with labelled fields ("Balance: $165,136",
    "Scheduled Payment Amount: $2,419"), so it is parsed in code, exactly.
    Everything else (Experian and TransUnion PDFs that are pictures of pages,
    phone photos of a report) goes to Claude on the team seat, which reads
    the pages and returns the same fields. Each figure Claude returns must
    appear in the document's own text when there is text to check against.

ONE ROW PER ACCOUNT
    The same mortgage appears on three bureaus and on both spouses' reports.
    Rows are merged on lender and the last four digits of the account (or,
    without those, lender, type and the month it was opened), keeping the
    most recent balance and noting every report it appeared on.

WHAT COUNTS AS DEBT
    Open accounts with a balance above zero. Closed and paid accounts, and
    cards at a zero balance, are listed separately as "seen, nothing owed" so
    the reviewer can see the report was read in full.

The result is saved to _Audit/credit_report.json, keyed on the reports' own
fingerprints, so it is read once and reused by every later step.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SAVED = os.path.join('_Audit', 'credit_report.json')
NAME = re.compile(r'credit\s*report|equifax|experian|transunion|annual\s*credit',
                  re.I)
TIMEOUT = 900
VERSION = 3      # bump when the merging or naming changes, to re-merge


def _num(s):
    if s in (None, ''):
        return None
    m = re.search(r'-?[\d,]+\.?\d*', str(s).replace('$', ''))
    if not m:
        return None
    try:
        return float(m.group(0).replace(',', ''))
    except ValueError:
        return None


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def find_reports(folder):
    """The credit report files, one per distinct document (the same report
    is often both in Original_sourcedocs and in the filed tree)."""
    seen, out = set(), []
    roots = [os.path.join(folder, 'Original_sourcedocs'),
             os.path.join(folder, 'Documents')]
    for root in roots:
        for path in sorted(glob.glob(os.path.join(root, '**', '*'), recursive=True)):
            if not os.path.isfile(path) or '/.fq_cache' in path:
                continue
            here = path[len(folder):]
            if not NAME.search(here):
                continue
            if not path.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.heic')):
                continue
            try:
                d = _sha(path)
            except OSError:
                continue
            if d in seen:
                continue
            seen.add(d)
            out.append({'path': path, 'sha': d, 'name': os.path.basename(path)})
    return out


def _thin(text, pages):
    """A browser 'print to PDF' of a report saved as pictures: every page
    carries the URL and '1/50' and nothing else."""
    body = re.sub(r'https?://\S+|\d+/\d+|annual credit report|experian|'
                  r'\d{1,2}/\d{1,2}/\d{2},? \d{1,2}:\d{2} [ap]m', '', text or '', flags=re.I)
    return len(re.sub(r'\s', '', body)) < 150 * max(1, pages)


def _ocr(folder, rep):
    """Read a pictures-only PDF with the toolkit's own OCR, once, and keep
    the text beside the other extracts. Claude cannot render PDF pages on a
    Mac without poppler, so it gets this text instead (Kelly Spaulding's
    50-page Experian report came back empty before this)."""
    out = os.path.join(folder, 'Original_sourcedocs', '.fq_cache', rep['sha'] + '.ocr.txt')
    if os.path.exists(out):
        return open(out, errors='replace').read()
    try:
        import extract
        doc = extract.open_pdf(rep['path'])
        if doc is None:
            return ''
        pages = []
        for page in doc:
            try:
                t = extract._ocr_with_rescue(page, extract.OCR_DPI)
                pages.append(t[0] if isinstance(t, tuple) else t)
            except Exception:  # noqa: BLE001
                pages.append('')
        doc.close()
        text = '\n\n'.join(pages)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w') as fh:
            fh.write(text)
        return text
    except Exception:  # noqa: BLE001
        return ''


def _text(folder, rep):
    """The toolkit's own text extract of a report, if one exists, else the
    PDF's text layer, else OCR of its pages."""
    for cache in (os.path.join(folder, '.fq_cache'),
                  os.path.join(folder, 'Original_sourcedocs', '.fq_cache')):
        hits = sorted(h for h in glob.glob(os.path.join(cache, rep['sha'] + '*.txt'))
                      if not h.endswith(('.credit.txt', '.ocr.txt')))
        if hits:
            try:
                text = open(hits[-1], errors='replace').read()
            except OSError:
                text = ''
            if text and not _thin(text, text.count('\f') + text.count('/50') or 1):
                return text
    if rep['path'].lower().endswith('.pdf'):
        try:
            import fitz
            doc = fitz.open(rep['path'])
            if not doc.needs_pass:
                text = '\n'.join(p.get_text() for p in doc)
                if not _thin(text, doc.page_count):
                    return text
                return _ocr(folder, rep)
        except Exception:  # noqa: BLE001
            pass
    return ''


# ---- Equifax, in code ------------------------------------------------------

EQ_FIELDS = {
    'balance': r'Balance:\s*\$?([\d,]+)',
    'account': r'Account Number:\s*\*?(\w+)',
    'owner': r'Owner:\s*([A-Za-z ]+?Account)',
    'limit': r'Credit Limit:\s*\$?([\d,]*)',
    'high': r'High Credit:\s*\$?([\d,]*)',
    'type': r'Loan/Account Type:\s*([^|\n]+?)\s*\|',
    'status': r'Status:\s*([^\n]+)',
    'opened': r'Date Opened:\s*([\d/]+)',
    'reported': r'Date Reported:\s*([\d/]+)',
    'payment': r'Scheduled Payment Amount:\s*\$?([\d,]*)',
    'closed': r'Date Closed:\s*([\d/]*)',
    'term': r'Term Duration:\s*([^\n]*)',
}


def parse_equifax(text):
    """Every account block in an Equifax report's text."""
    if 'EQUIFAX' not in text.upper() or 'Loan/Account Type' not in text:
        return None
    who = re.search(r'Prepared for:\s*\n\s*([^\n]+)', text)
    who = who.group(1).strip() if who else None
    rows = []
    # Each block starts at the lender's name line, two lines above
    # "Date Reported"; the block runs to the next one.
    starts = [m.start() for m in re.finditer(r'Date Reported:', text)]
    for i, s in enumerate(starts):
        block = text[s:starts[i + 1] if i + 1 < len(starts) else len(text)]
        head = text[max(0, s - 400):s].rstrip().split('\n')
        lender = None
        for line in reversed(head[-4:]):
            line = line.strip()
            if line and '|' not in line and not re.search(r'\d{5}', line):
                lender = line
                break
        if lender is None:
            # "10750 W Ih 10 ... | (800) 531-2265 Date Reported" on one line:
            # the lender is the line before the address
            lender = head[-2].strip() if len(head) > 1 else None
        rec = {'bureau': 'Equifax', 'person': who, 'lender': lender}
        for k, pat in EQ_FIELDS.items():
            m = re.search(pat, block)
            rec[k] = m.group(1).strip() if m else None
        for k in ('balance', 'limit', 'high', 'payment'):
            rec[k] = _num(rec[k])
        if not rec.get('type'):
            continue
        rows.append(rec)
    return rows


# ---- Claude, for everything else -------------------------------------------

PROMPT = """Read this credit report for {who} and list every account on it.

FILE: {path}
{how}

For each account (tradeline) return:
  lender, account (last 4 digits shown, or null), type (Mortgage, HELOC,
  Auto, Student loan, Credit card, Installment, Business, Other, as the report
  calls it), owner (Individual, Joint, Authorized user), status (as the report
  says: Open / Pays as agreed / Closed / Paid / Past due ...), balance,
  payment (the scheduled monthly payment), limit (credit limit, or high
  credit / original amount for a loan), opened (MM/YYYY), reported (MM/YYYY),
  closed (MM/YYYY or null).
Copy figures exactly as printed. Use null for anything not shown. Do not
estimate. Include closed and zero-balance accounts too; they are filtered
later.

Return JSON only:
{{"bureau": "Experian", "person": "name on the report", "accounts": [{{...}}]}}"""


def _answered(cdir, rep):
    """An answer already given for this same report, on any machine (the
    share mounts at a different path on each Mac, so the cached question
    differs only in the path)."""
    for path in sorted(glob.glob(os.path.join(cdir, '*.json'))):
        try:
            hit = json.load(open(path))
        except (OSError, ValueError):
            continue
        if rep['sha'] in (hit.get('prompt') or '') or \
                ('/' + rep['name'] + '\n') in (hit.get('prompt') or ''):
            m = re.search(r'\{.*\}', hit.get('answer') or '', re.S)
            try:
                got = json.loads(m.group(0)) if m else None
            except ValueError:
                got = None
            if got and got.get('accounts') and not got.get('error'):
                return got
            # an answer that read nothing is not an answer: ask again
    return None


def read_with_claude(folder, rep, who):
    import ask_claude
    text = _text(folder, rep)
    if text and len(re.sub(r'\s', '', text)) > 500:
        cache = os.path.join(folder, 'Original_sourcedocs', '.fq_cache')
        tmp = os.path.join(cache, rep['sha'] + '.credit.txt')
        try:
            os.makedirs(cache, exist_ok=True)
            with open(tmp, 'w') as fh:
                fh.write(text)
        except OSError:
            tmp = None
        # The text's own fingerprint in the question, so new text (OCR of a
        # pictures-only report) is a new question, not the old cached answer.
        import hashlib
        tag = hashlib.sha1(text.encode('utf-8', 'replace')).hexdigest()[:10]
        how = ('Its text has been extracted to %s (%d characters, version %s); '
               'read that.' % (tmp, len(text), tag)) if tmp \
            else 'Read the file itself.'
    else:
        how = ('It is a picture of the pages; read the file itself, every '
               'page (PDFs: in groups of up to 20 pages).')
    prompt = PROMPT.format(who=who or 'the client', path=rep['path'], how=how)
    dirs = sorted({os.path.dirname(rep['path']),
                   os.path.join(folder, 'Original_sourcedocs', '.fq_cache')})
    cdir = os.path.join(folder, '.fq_cache', 'credit')
    got = _answered(cdir, rep)
    if got is None:
        got = ask_claude.ask_json(prompt, cache_dir=cdir, timeout=TIMEOUT,
                                  allow=('Read',), add_dirs=dirs)
    if not got or got.get('error') or not got.get('accounts'):
        return None              # not read, so it is listed as unread
    rows = []
    for a in got.get('accounts') or []:
        rec = {'bureau': got.get('bureau'), 'person': got.get('person'),
               'lender': a.get('lender'), 'account': a.get('account'),
               'type': a.get('type'), 'owner': a.get('owner'),
               'status': a.get('status'), 'opened': a.get('opened'),
               'reported': a.get('reported'), 'closed': a.get('closed')}
        for k in ('balance', 'payment', 'limit'):
            rec[k] = _num(a.get(k))
        rows.append(rec)
    # Figures checked against the text when there is text: a balance not in
    # the document is dropped to None rather than trusted.
    if text:
        flat = text.replace(',', '')
        for r in rows:
            for k in ('balance', 'payment', 'limit'):
                v = r.get(k)
                if v and str(int(v)) not in flat:
                    r[k + '_unchecked'] = v
                    r[k] = None
    return rows


# ---- one row per account ---------------------------------------------------

ALIASES = (('wfb', 'wells'), ('wells', 'wells'), ('jpm', 'chase'),
           ('chase', 'chase'), ('amex', 'american'), ('boa', 'bankofamerica'),
           ('bank of america', 'bankofamerica'), ('us bank', 'usbank'),
           ('u s bank', 'usbank'), ('usbank', 'usbank'))


def _lender_key(s):
    low = (s or '').lower().strip()
    for start, key in ALIASES:
        if low.startswith(start):
            return key
    s = re.sub(r'[^a-z ]', ' ', low)
    words = [w for w in s.split() if w not in ('bank', 'the', 'na', 'n', 'a',
                                               'of', 'card', 'cards', 'services',
                                               'financial', 'home', 'mtg')]
    return words[0] if words else s.strip()[:6]


def _month(d):
    m = re.search(r'(\d{1,2})/(?:\d{1,2}/)?(\d{2,4})', d or '')
    if not m:
        return None
    y = int(m.group(2))
    return '%02d/%d' % (int(m.group(1)), y + 2000 if y < 100 else y)


def merge(rows):
    """One account per real account, newest balance kept, every report noted."""
    out = {}
    for r in rows:
        last4 = re.sub(r'\D', '', str(r.get('account') or ''))[-4:]
        key = (_lender_key(r.get('lender')), last4) if last4 else \
            (_lender_key(r.get('lender')), (r.get('type') or '').lower()[:6],
             _month(r.get('opened')))
        seen_on = '%s (%s)' % (r.get('bureau') or '?', (r.get('person') or '?').title())
        have = out.get(key)
        if not have:
            r = dict(r, seen_on=[seen_on])
            out[key] = r
            continue
        if seen_on not in have['seen_on']:
            have['seen_on'].append(seen_on)
        newer = (_month(r.get('reported')) or '') > (_month(have.get('reported')) or '')
        for k in ('balance', 'payment', 'limit', 'status', 'reported', 'closed',
                  'owner', 'type', 'opened'):
            if r.get(k) is not None and (have.get(k) is None or newer):
                have[k] = r[k]
    # Each bureau masks the account number differently (Equifax *7127,
    # TransUnion 0068, Experian none at all) and spells the lender its own
    # way ("USAA FED SVG BK- SAN AN"). The same loan still reports the same
    # balance and payment, so an open account with an identical balance and
    # payment is one account, whatever its name.
    final = {}
    for r in out.values():
        if (r.get('balance') or 0) > 0:
            k2 = ('owed', round(r['balance']), round(r.get('payment') or 0))
        else:
            k2 = ('none', id(r))
        have = final.get(k2)
        if not have:
            final[k2] = r
            continue
        for x in r.get('seen_on') or []:
            if x not in have['seen_on']:
                have['seen_on'].append(x)
        for k in ('account', 'owner', 'opened', 'limit', 'type'):
            if not have.get(k) and r.get(k):
                have[k] = r[k]
    return list(final.values())


NAMES = (('usaa', 'USAA'), ('wfbna', 'Wells Fargo'), ('wells', 'Wells Fargo'),
         ('us bank', 'US Bank'), ('u s bank', 'US Bank'), ('jpmcb', 'Chase'),
         ('chase', 'Chase'), ('amex', 'American Express'),
         ('american express', 'American Express'), ('bank of america', 'Bank of America'),
         ('bk of amer', 'Bank of America'), ('capital one', 'Capital One'),
         ('citi', 'Citi'), ('discover', 'Discover'), ('navient', 'Navient'),
         ('nelnet', 'Nelnet'), ('mohela', 'MOHELA'), ('sallie', 'Sallie Mae'),
         ('toyota', 'Toyota Financial'), ('honda', 'Honda Financial'),
         ('ally', 'Ally'), ('pnc', 'PNC'), ('truist', 'Truist'), ('regions', 'Regions'),
         ('huntington', 'Huntington'), ('fifth third', 'Fifth Third'),
         ('rocket', 'Rocket Mortgage'), ('mr cooper', 'Mr. Cooper'))


def tidy_lender(name):
    """'USAA FED SVG BK- SAN AN' -> 'USAA', the way the plan names lenders."""
    low = (name or '').lower()
    for k, v in NAMES:
        if re.match(re.escape(k) + r'\b', low):
            return v
    t = re.sub(r'\b(federal savings|fed svg|savings bank|bank|bk|na|n\.a\.|'
               r'home mtg|mtg|mortgage|financial|services)\b', '', name or '', flags=re.I)
    return ' '.join(t.split()).title() or (name or '').title()


CLOSED = re.compile(r'closed|paid|transferred|refinanced|charge', re.I)


def owed(rows):
    """Open with a balance, as debt rows debt.py and the plan understand."""
    debts, nothing = [], []
    for r in rows:
        if re.search(r'card|revolving|charge', r.get('type') or '', re.I) and \
                not re.search(r'equity|line of credit', r.get('type') or '', re.I):
            # Cards are listed, not counted: most are paid off each month,
            # and the plan's liabilities are loans (the lead advisor's
            # Assumptions list loans only).
            if (r.get('balance') or 0) > 0 and not r.get('closed'):
                r = dict(r, card=True)
            nothing.append(r)
            continue
        if (r.get('balance') or 0) <= 0 or r.get('closed') or \
                CLOSED.search(r.get('status') or ''):
            nothing.append(r)
            continue
        t = (r.get('type') or '').lower()
        what = ('Mortgage' if 'mortgage' in t else 'HELOC' if 'equity' in t or
                'heloc' in t else 'Auto loan' if 'auto' in t else 'Student loan'
                if 'student' in t or 'education' in t else 'Credit card'
                if 'card' in t or 'revolving' in t or 'charge' in t else
                'Loan')
        debts.append({
            'side': 'Business' if 'business' in t or 'commercial' in t
            else 'Personal',
            'creditor': tidy_lender(r.get('lender')),
            'what': what, 'account_last4': re.sub(r'\D', '', str(r.get('account') or ''))[-4:] or None,
            'balance': r.get('balance'), 'payment': r.get('payment'),
            'rate': None, 'owner': r.get('owner'), 'opened': r.get('opened'),
            'source': 'credit report: ' + ', '.join(r.get('seen_on') or []),
        })
    return debts, nothing


def read(folder, log=print, use_claude=True):
    """{'debts': [...], 'nothing_owed': [...], 'reports': [...], 'unread':
    [...]}, saved and reused while the reports are unchanged."""
    reps = find_reports(folder)
    saved_path = os.path.join(folder, SAVED)
    try:
        with open(saved_path) as fh:
            saved = json.load(fh)
    except (OSError, ValueError):
        saved = {}
    key = sorted(r['sha'] for r in reps)
    if saved.get('reports_key') == key and not saved.get('unread') and \
            saved.get('v') == VERSION:
        return saved
    if not reps:
        return {'debts': [], 'nothing_owed': [], 'reports': [], 'unread': [],
                'reports_key': key}
    who = None
    rows, unread, done = [], [], []
    for rep in reps:
        text = _text(folder, rep)
        got = parse_equifax(text) if text else None
        how = 'parsed'
        if got is None and use_claude:
            try:
                got = read_with_claude(folder, rep, who)
                how = 'Claude'
            except Exception as exc:  # noqa: BLE001
                log('  credit report not read (%s): %s' % (rep['name'], exc))
                got = None
        if got is None:
            unread.append(rep['name'])
            continue
        rows += got
        done.append({'file': rep['name'], 'accounts': len(got), 'read_by': how})
    accounts = merge(rows)
    debts, nothing = owed(accounts)
    out = {'v': VERSION, 'reports_key': key, 'reports': done, 'unread': unread,
           'debts': debts,
           'cards': [{k: r.get(k) for k in ('lender', 'account', 'balance', 'limit',
                                            'payment', 'seen_on')}
                     for r in nothing if r.get('card')],
           'nothing_owed': [
               {k: r.get(k) for k in ('lender', 'type', 'status', 'balance',
                                      'seen_on')} for r in nothing if not r.get('card')]}
    if done:
        try:
            with open(saved_path, 'w') as fh:
                json.dump(out, fh, indent=1)
        except OSError:
            pass
    return out


def main():
    ap = argparse.ArgumentParser(description='Debts on the credit reports')
    ap.add_argument('folder')
    ap.add_argument('--no-claude', action='store_true')
    a = ap.parse_args()
    got = read(a.folder, use_claude=not a.no_claude)
    for r in got['reports']:
        print('read  %-55s %3d accounts (%s)' % (r['file'][:55], r['accounts'], r['read_by']))
    for n in got['unread']:
        print('NOT READ  %s' % n)
    print('\nOWED (%d):' % len(got['debts']))
    for d in got['debts']:
        print('  %-28s %-12s %-6s bal %10s  pay %8s  %s' % (
            d['creditor'][:28], d['what'], d['account_last4'] or '',
            '{:,.0f}'.format(d['balance']) if d['balance'] else '-',
            '{:,.0f}'.format(d['payment']) if d['payment'] else '-', d['source']))
    print('\ncards with a balance (listed, not counted): %d' % len(got.get('cards') or []))
    for c in got.get('cards') or []:
        print('  %-28s bal %10s' % ((c['lender'] or '')[:28], '{:,.0f}'.format(c['balance'] or 0)))
    print('seen, nothing owed: %d' % len(got['nothing_owed']))


if __name__ == '__main__':
    main()
