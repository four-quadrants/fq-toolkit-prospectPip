#!/usr/bin/env python3
"""What the client owns, as each statement reports it.

    python3 assets.py "<client folder>"
    python3 assets.py "<client folder>" --json

ONE BALANCE PER ACCOUNT, THE NEWEST
A client sends four months of statements for the same account. Adding up what
each one says would report their checking account four times over. So the
statements are grouped by account and only the latest is kept, which is also
the only one that answers "what do they have now".

WHY THE COUNT TRAVELS WITH THE TOTAL
The same reason it does for debt: a bare figure reads as the whole picture. The
accounts without a statement are invisible in a total and obvious in a count,
and on this page the gap is the more useful half -- Oyler's Assumptions lists
six accounts and four of them have no statement here at all.

NOTHING IS INFERRED
A statement whose balance cannot be read is reported as unreadable rather than
estimated from the transactions. The transactions are what the cashflow work is
for, and a balance assembled from them would look like a statement figure
without being one.
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

KINDS = {'bank_statement': 'Cash', 'brokerage_statement': 'Investments',
         'retirement_statement': 'Investments',
         'investment_statement': 'Investments',
         'unknown': None}

SCHEMA = """{
  "is_account_statement": true or false,
  "kind": "Cash or Investments",
  "institution": "who holds it, as printed",
  "account_last4": "four digits, or null",
  "owner": "whose account, or null",
  "side": "Personal or Practice",
  "balance": "the closing balance as a number, no commas or currency sign",
  "as_of": "YYYY-MM the balance is stated as of",
  "evidence": "the line on the page you read the balance from, quoted",
  "confidence": "high, medium or low"
}"""


def _money(s):
    """A figure as a number, however it was written.

    Claude is asked for a bare number and usually gives one, but "109,433.61"
    and "$109,433.61" both turn up, and a string that is not a number at all
    has to come back as None rather than raise in the middle of a run.
    """
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    cleaned = re.sub(r'[^\d.\-]', '', str(s))
    try:
        return float(cleaned)
    except ValueError:
        return None


def _period_key(doc, text):
    """Something sortable, so "latest" means latest and not last-read."""
    m = re.search(r'\b(20\d\d)[-/](\d{1,2})\b', text[:400])
    if m:
        return '%s-%02d' % (m.group(1), int(m.group(2)))
    m = re.search(r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b', text[:400])
    if m:
        year = m.group(3)
        year = ('20' + year) if len(year) == 2 else year
        return '%s-%02d' % (year, int(m.group(1)))
    return str(doc.get('year') or '')


def ask_about(path, text, folder):
    """What this statement says the account holds.

    Patterns could not do this. "Balance" appears a dozen times on a statement
    meaning a dozen things -- the previous balance, the balance of one holding,
    the minimum payment balance -- and the closing figure is laid out
    differently by every custodian. Reading the x4728 bank statement, the
    pattern version reported its PREVIOUS balance as an investment account, and
    missed a $629,591 IRA entirely. Two right out of eight.

    So the figure is read by something that understands the page, and the tool
    keeps the jobs patterns are good at: one account per statement, newest
    wins, and the arithmetic.
    """
    import ask_claude
    hint = ' '.join(text.split())[:2500]
    prompt = ("""Read this account statement and report what the account holds.

DOCUMENT: %s

Our text extraction reads:
\"\"\"%s\"\"\"

Read the file itself as well if you can open it.

Reply with only JSON:
%s

Rules:
- balance is the CLOSING balance for the whole account, not a previous
  balance, not one holding within it, not an amount due.
- If this is not an account statement at all (a mortgage statement, a tax
  return, an invoice), set is_account_statement false and leave balance null.
- A loan or mortgage statement is NOT an asset. It is a debt and belongs
  elsewhere.
- Quote the line you read the balance from. If you cannot find a clear closing
  balance, say so with confidence low rather than picking the nearest number.
""" % (path, hint, SCHEMA))
    return ask_claude.ask_json(
        prompt, cache_dir=os.path.join(folder, CACHE, 'assets'),
        add_dirs=[os.path.abspath(folder)])


def candidates(folder):
    """Documents that might be an account statement. Deliberately wide: the
    classifier is what got this wrong last time, so it narrows the field and
    does not decide."""
    out = []
    for path in sorted(glob.glob(os.path.join(folder, CACHE, '*.txt'))):
        raw = open(path, errors='replace').read()
        doc = classify.classify(raw)
        if doc.get('doc_type') in KINDS:
            out.append((path, raw, doc))
    return out


def gather(folder, sources=None):
    found, unreadable, rejected = {}, [], []
    for path, raw, doc in candidates(folder):
        src = (sources or {}).get(os.path.basename(path).split('.')[0]) or path
        ans = ask_about(src, raw, folder)
        if not ans:
            unreadable.append({'source': os.path.basename(path)[:12],
                               'why': 'no usable answer'})
            continue
        if not ans.get('is_account_statement') or ans.get('balance') in (None, ''):
            rejected.append({'source': os.path.basename(path)[:12],
                             'why': ans.get('evidence') or 'not an account statement'})
            continue
        balance = _money(ans['balance'])
        if balance is None:
            unreadable.append({'source': os.path.basename(path)[:12],
                               'why': 'balance not a number'})
            continue
        kind = 'Investments' if str(ans.get('kind', '')).lower().startswith('inv') \
            else 'Cash'
        issuer = (ans.get('institution') or '').strip() or None
        tail = (ans.get('account_last4') or doc.get('account_tail') or None)
        when = ans.get('as_of') or _period_key(doc, ' '.join(raw.split()))
        key = (kind, issuer, tail)
        # Latest statement wins. Four months of one account is one account.
        if key not in found or str(when) > str(found[key]['as_of']):
            found[key] = {'kind': kind, 'issuer': issuer, 'account': tail,
                          'balance': balance, 'as_of': when,
                          'side': ans.get('side') or doc.get('owner_side'),
                          'owner': ans.get('owner'),
                          'confidence': ans.get('confidence'),
                          'evidence': ans.get('evidence'),
                          'source': os.path.basename(path)[:12]}

    rows = sorted(found.values(), key=lambda r: (r['kind'], -r['balance']))
    by_kind = {}
    for r in rows:
        by_kind[r['kind']] = round(by_kind.get(r['kind'], 0) + r['balance'], 2)
    return {'accounts': rows, 'by_kind': by_kind,
            'total': round(sum(by_kind.values()), 2) if by_kind else None,
            'unreadable': unreadable, 'not_accounts': rejected}


def main():
    ap = argparse.ArgumentParser(description='What the statements say is there')
    ap.add_argument('folder')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    from classify_claude import source_index
    g = gather(a.folder, sources=source_index(a.folder))
    if a.json:
        print(json.dumps(g, indent=1))
        return
    for r in g['accounts']:
        print('  %-13s %-16s %-7s %14s   as of %s'
              % (r['kind'], (r['issuer'] or '?')[:16],
                 ('x%s' % r['account']) if r['account'] else '-',
                 '{:,.2f}'.format(r['balance']), r['as_of']))
    print()
    for kind, total in sorted(g['by_kind'].items()):
        print('  %-13s %14s' % (kind, '{:,.0f}'.format(total)))
    print('  %-13s %14s   across %d account(s)'
          % ('TOTAL', '{:,.0f}'.format(g['total'] or 0), len(g['accounts'])))
    if g.get('not_accounts'):
        print('\n  %d document(s) looked like a statement and were not:'
              % len(g['not_accounts']))
        for r in g['not_accounts'][:6]:
            print('     %s  %s' % (r['source'], str(r['why'])[:72]))
    if g['unreadable']:
        print('\n  %d statement(s) with no readable balance:' % len(g['unreadable']))
        for r in g['unreadable'][:6]:
            print('     %s  %s' % (r['source'], r.get('why', '')))


if __name__ == '__main__':
    main()
