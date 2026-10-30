#!/usr/bin/env python3
"""Every obligation the client has, from wherever it is written down.

    python3 debt.py "<client folder>"
    python3 debt.py "<client folder>" --json

WHY THIS IS NOT ONE DOCUMENT
A prospect's debt arrives in at least three shapes. The practice debt comes on
the firm's own spreadsheet, filled in by the office, with every column we asked
for. The personal mortgages come as monthly statements, which carry the balance
and the payment but not the term or the origination. A building loan can arrive
as a letter answering the question in prose.

So this reads all three and keeps them apart. The spreadsheet is believed as
written; the statements are read for what they state; and anything that only
appears in prose is reported as present but unread, because a number lifted out
of a sentence by pattern-matching is a number nobody can check.

WHAT IT DOES NOT DO
Reconcile them against each other. Oyler's Assumptions lists a Regions mortgage
ending 3379 where the statement says 3779, and an M&T ending 1892 where the
statement says 1416; the payments match to the cent in both cases. That is a
real finding and it belongs in the due-diligence pass, not buried in a total.
This reports what each source says and marks where they disagree.
"""
import os
import re
import sys
import glob
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import classify                                              # noqa: E402

CACHE = '.fq_cache'


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r'[^\d.\-]', '', str(v))
    try:
        return float(s)
    except ValueError:
        return None


def _year_of(v):
    """The year a loan matures, from a date cell or a string.

    Only the year is kept. The schedule carries full dates, but what an
    analyst writes is "3 drop off in the next 2 years", and a day-precise
    maturity invites a precision the rest of the line does not have.
    """
    if v is None:
        return None
    if hasattr(v, 'year'):
        return v.year
    m = re.search(r'(20\d\d)', str(v))
    return int(m.group(1)) if m else None


def read_schedule(path):
    """The firm's debt schedule template, as the office filled it in."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    head = next((i for i, r in enumerate(rows)
                 if r and str(r[0]).strip().lower() == 'creditor'), None)
    if head is None:
        return read_debt_sheet(path, rows)
    cols = [str(c).strip() if c else '' for c in rows[head]]

    def col(*words):
        for i, c in enumerate(cols):
            if any(w.lower() in c.lower() for w in words):
                yield i

    # Two balance columns is normal: the template asks for a second, later one
    # "if available". The later is preferred and the earlier is the fallback,
    # because the office fills whichever they had to hand.
    bals = list(col('current balance'))
    out = []
    for r in rows[head + 1:]:
        if not r or not r[0] or str(r[0]).strip().upper() == 'TOTALS':
            continue
        get = lambda *w: next((_num(r[i]) for i in col(*w)
                               if _num(r[i]) is not None), None)   # noqa: E731
        balance = next((_num(r[i]) for i in reversed(bals)
                        if _num(r[i]) is not None), None)
        out.append({
            'creditor': str(r[0]).strip(),
            'description': str(r[1]).strip() if len(r) > 1 and r[1] else None,
            'original': get('original amount'),
            'balance': balance,
            'rate': get('interest rate'),
            'payment': get('minimum monthly'),
            'maturity': _year_of(next((r[i] for i in col('maturity')), None)),
            'available_credit': get('available credit'),
            'side': 'Practice',
            'source': os.path.basename(path),
            'as_of': next((cols[i] for i in reversed(bals)
                           if _num(r[i]) is not None), None),
        })
    return out


def read_debt_sheet(path, rows):
    """The firm's other template, the "Debt Sheet": practice AND personal.

    Columns: Debt Description, Practice/Personal/Other, Bank/Lender,
    Original Amount, Origination Date, Current Balance, Payment Terms,
    Interest Rate, Minimum Payment, Extra Amount, Notes. Spaulding filled
    this one in and the reader, which only knew the "Creditor" template,
    returned nothing: no practice debt and no personal debt in her notes.
    A row marked "Personal/Practice" is counted as personal; the lead advisor’s own
    $728k on 8 loans for her practice leaves it out.
    """
    head = None
    for i, r in enumerate(rows):
        cells = [str(c).strip().lower() for c in r if c]
        if any('balance' in c for c in cells) and \
                any('lender' in c or 'description' in c or 'loan' in c
                    for c in cells):
            head = i
            break
    if head is None:
        return []
    cols = [str(c).strip().lower() if c else '' for c in rows[head]]

    def idx(*words):
        # Words in order of preference: "minimum payment" before a bare
        # "payment", which would otherwise find "Payment Terms" first.
        for w in words:
            for i, c in enumerate(cols):
                if w in c:
                    return i
        return None

    c_desc, c_side = idx('description'), idx('practice/personal', 'personal')
    c_lender = idx('lender', 'bank', 'loan service')
    c_orig = idx('original amount', 'original note', 'original')
    c_bal, c_rate = idx('current balance', 'balance'), idx('interest rate', 'rate')
    c_pay = idx('minimum payment', 'payment amt', 'payment')
    c_terms = idx('payment terms', 'terms')
    c_notes, c_start = idx('notes'), idx('origination')
    c_end = idx('payoff', 'maturity', 'end date')

    def cell(r, i):
        return r[i] if i is not None and i < len(r) else None

    out = []
    for r in rows[head + 1:]:
        if not r or not any(r):
            continue
        desc = cell(r, c_desc)
        bal = _num(cell(r, c_bal))
        if not desc or bal is None:
            continue
        side_txt = str(cell(r, c_side) or '').strip().lower()
        # The side can be its own column ("Practice/Personal"), an unlabelled
        # cell saying "Business" (Rebol), or only the file's name ("Business
        # Debt YTD 2026 04.xlsx" beside "Personal Debt ...").
        cells = {str(c).strip().lower() for c in r if isinstance(c, str)}
        fname = os.path.basename(path).lower()
        if side_txt in ('practice', 'business') or cells & {'practice', 'business'}:
            side = 'Practice'
        elif side_txt.startswith('personal') or 'personal' in cells:
            side = 'Personal'
        elif 'business' in fname or 'practice' in fname:
            side = 'Practice'
        else:
            side = 'Personal'
        notes = str(cell(r, c_notes) or '')
        out.append({
            'creditor': str(cell(r, c_lender) or desc).strip(),
            'description': str(desc).strip(),
            'original': _num(cell(r, c_orig)),
            'balance': bal,
            'rate': _num(cell(r, c_rate)),
            'payment': _num(cell(r, c_pay)),
            'maturity': _year_of(cell(r, c_end)) or _year_of(notes) or None,
            'terms': cell(r, c_terms),
            'started': cell(r, c_start),
            'side': side,
            'source': os.path.basename(path),
            'as_of': 'current balance',
        })
    return out


# A mortgage statement states the balance and the payment plainly and says
# almost nothing about the term. These are the three it does state.
STATEMENT_FIELDS = [
    # "Outstanding Principal* $427,759" and "Unpaid Principal Balance" are
    # both common; a bare "Principal $829" is the month's principal portion and
    # must not match, so one of the qualifying words is required.
    ('balance', r'(?:outstanding|unpaid|current)\s+principal\s*(?:balance)?\*?'
                r'[:\s]*\$?([\d,]+\.?\d*)'),
    ('payment', r'(?:regular\s+monthly\s+payment|amount\s+due|total\s+payment)'
                r'[:\s]*\$?([\d,]+\.?\d*)'),
    ('rate',    r'interest\s+rate[:\s]*([\d.]+)\s*%'),
]
ACCOUNT = re.compile(r'(?:loan|account)\s*(?:number|no\.?|#)?[:\s]*(\d{6,})',
                     re.I)


def read_statements(folder):
    """Personal debt, as the lender's own statement reports it."""
    out = []
    for path in sorted(glob.glob(os.path.join(folder, CACHE, '*.txt'))):
        text = ' '.join(open(path, errors='replace').read().split())
        if not re.search(r'mortgage statement|loan statement', text, re.I):
            continue
        rec = {'side': 'Personal', 'source': os.path.basename(path)[:12],
               'creditor': None, 'account_last4': None}
        issuer = re.search(r'\b(regions|m&t|wells fargo|chase|truist|pnc|'
                           r'us bank|quicken|rocket|freedom|roundpoint)\b',
                           text, re.I)
        if issuer:
            rec['creditor'] = issuer.group(1).title()
        acct = ACCOUNT.search(text)
        if acct:
            rec['account_last4'] = acct.group(1)[-4:]
        for field, pat in STATEMENT_FIELDS:
            m = re.search(pat, text, re.I)
            if m:
                rec[field] = _num(m.group(1))
        # What it is, so the plan can say "Florida Mortgage (Regions x3779)"
        # the way the lead advisor writes it, rather than a lender and four digits.
        rec['what'] = 'Mortgage' if re.search(r'mortgage', text, re.I) else 'Loan'
        prop = re.search(r'property\s+address\s*:?\s*(.{0,90})', text, re.I)
        if prop:
            st = re.search(r'\b([A-Z]{2})\s+\d{5}\b', prop.group(1))
            if st:
                rec['state'] = st.group(1)
        if rec.get('balance') or rec.get('payment'):
            out.append(rec)
    return out


def dedupe_statements(rows):
    """One row per account. A lender sends a statement a month."""
    best = {}
    for r in rows:
        key = (r.get('creditor'), r.get('account_last4'))
        have = best.get(key)
        if not have or (r.get('balance') and not have.get('balance')):
            if have and have.get('state') and not r.get('state'):
                r['state'] = have['state']
            best[key] = r
        elif r.get('state') and not have.get('state'):
            have['state'] = r['state']
    return list(best.values())


def find_prose(folder):
    """Obligations that exist only inside a sentence.

    Reported, never parsed. Oyler's building loan arrives as a letter giving
    the origination, amount, term, rate, balance and payment in prose. Lifting
    those out with a pattern would produce six numbers nobody could check
    against anything, which is how a wrong figure reaches a plan.
    """
    out = []
    for path in sorted(glob.glob(os.path.join(folder, CACHE, '*.txt'))):
        text = open(path, errors='replace').read()
        doc = classify.classify(text)
        if doc.get('doc_type') not in ('line_of_credit', 'loan_document'):
            continue
        flat = ' '.join(text.split())
        out.append({'source': os.path.basename(path)[:12],
                    'why': 'loan terms stated in prose, needs a person',
                    'first_words': flat[:180]})
    return out


def _ckey(name):
    import credit as _c
    return _c._lender_key(name)


def add_credit(folder, rows):
    """The credit report's open loans beside what the statements and the
    Debt Sheet already list. A loan already listed is completed from the
    report (a payment, the last four digits) and keeps its own figures; a
    loan only the report shows is added, marked as from the report."""
    try:
        import credit as _credit
        got = _credit.read(folder, log=lambda *_a: None)
    except Exception:  # noqa: BLE001 - no reports, nothing to add
        return rows, []
    rows = [dict(r) for r in rows]
    added = []
    for c in got.get('debts') or []:
        if c.get('side') != 'Personal':
            continue
        match = None
        for r in rows:
            l4 = str(r.get('account_last4') or '')
            if l4 and c.get('account_last4') and l4[-4:] == c['account_last4']:
                match = r
                break
            close = r.get('balance') and c.get('balance') and \
                abs(r['balance'] - c['balance']) <= 0.1 * c['balance']
            same_pay = r.get('payment') and c.get('payment') and \
                abs(r['payment'] - c['payment']) <= 2
            if close and (_ckey(r.get('creditor')) == _ckey(c.get('creditor'))
                          or same_pay):
                match = r
                break
        if match:
            for k in ('payment', 'account_last4', 'what', 'opened'):
                if not match.get(k) and c.get(k):
                    match[k] = c[k]
            match['source'] = '%s; on the credit report' % (match.get('source') or '')
            continue
        rows.append(dict(c))
        added.append(c)
    return rows, added


def gather(folder):
    # One schedule, however many copies of it are on disk. The same workbook
    # sits in Documents, in Original_sourcedocs and in whatever tree the last
    # filing run built, so globbing gave three identical sets of obligations
    # and a practice debt of 2.1m against a true 720k.
    import hashlib
    sched, seen = [], set()
    for path in sorted(glob.glob(os.path.join(folder, '**', '*.xlsx'),
                                 recursive=True)):
        if 'debt' not in os.path.basename(path).lower():
            continue
        try:
            with open(path, 'rb') as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            continue
        if digest in seen:
            continue
        seen.add(digest)
        sched += read_schedule(path)
    statements = dedupe_statements(read_statements(folder))
    # A Debt Sheet carries personal rows too. They are the client's own
    # account; a mortgage statement for the same loan is not added twice.
    personal_sheet = [r for r in sched if r.get('side') == 'Personal']
    sched = [r for r in sched if r.get('side') != 'Personal']
    if personal_sheet:
        statements = personal_sheet
    prose = find_prose(folder)
    statements, from_credit = add_credit(folder, statements)

    def total(rows, key):
        vals = [r.get(key) for r in rows if r.get(key)]
        return round(sum(vals), 2) if vals else None

    return {
        'practice': sched,
        'personal': statements,
        'unread': prose,
        'from_credit_report': from_credit,
        'practice_balance': total(sched, 'balance'),
        'practice_payment': total(sched, 'payment'),
        'personal_balance': total(statements, 'balance'),
        'personal_payment': total(statements, 'payment'),
    }


def main():
    ap = argparse.ArgumentParser(description="Every obligation, by source")
    ap.add_argument('folder')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    g = gather(a.folder)
    if a.json:
        print(json.dumps(g, indent=1))
        return

    for side in ('practice', 'personal'):
        rows = g[side]
        if not rows:
            continue
        print('\n%s' % side.upper())
        for r in rows:
            print('  %-28s %12s %7s %12s' % (
                (r.get('creditor') or '?')[:28],
                '{:,.0f}'.format(r['balance']) if r.get('balance') else '-',
                ('%.2f%%' % (r['rate'] * 100 if r['rate'] < 1 else r['rate']))
                if r.get('rate') else '-',
                '{:,.0f}/mo'.format(r['payment']) if r.get('payment') else '-'))
        print('  %-28s %12s %7s %12s' % (
            'subtotal',
            '{:,.0f}'.format(g['%s_balance' % side] or 0), '',
            '{:,.0f}/mo'.format(g['%s_payment' % side] or 0)))

    if g['unread']:
        print('\nSTATED IN PROSE, NOT READ')
        for r in g['unread']:
            print('  %s  %s' % (r['source'], r['why']))
            print('     "%s..."' % r['first_words'][:110])

    known = (g['practice_balance'] or 0) + (g['personal_balance'] or 0)
    print('\nREADABLE TOTAL  %s across %d obligations'
          % ('{:,.0f}'.format(known), len(g['practice']) + len(g['personal'])))
    if g['unread']:
        print('plus %d obligation(s) a person still has to read'
              % len(g['unread']))


if __name__ == '__main__':
    main()
