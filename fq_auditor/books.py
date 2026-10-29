#!/usr/bin/env python3
"""What the books say that their totals do not.

    python3 books.py "<client folder>"

WHY THE DETAIL ROWS
Overhead is a ratio of two totals and says nothing about what is inside them.
The analyst’s notes on this client are mostly about what is inside:

    Spends 72k and 115k on "consulting" in 2024 and 2025 -- what is this for?
    Net income on the 2024 and 2025 books does not match the returns.
    Has a 476k loan to shareholder, has had it since at least pre-2024.

None of that is visible from the P&L's section totals. All of it is one layer
down, in the individual rows, and each one is a question for the client rather
than a figure for the plan.

WHAT IT LOOKS FOR
Three things, each of which is a question rather than a number:

  - A line that moved a lot, or that is large and unexplained. Consulting at
    72k then 116k is not a line anyone budgeted; it is a line someone decided.
  - The books disagreeing with the return about the same year's profit. On
    Oyler the 2024 gap is 96,935.
  - An obligation on the balance sheet that is not on the debt schedule. The
    schedule is what the office filled in; the balance sheet is what the
    bookkeeper recorded, and the difference is usually a loan nobody mentioned.

It does not judge. Every finding is reported with both figures and left for a
person, because "the books do not match the return" has a dozen innocent
explanations and the useful thing is to ask which one applies.
"""
import os
import re
import sys
import glob
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import classify                                              # noqa: E402
import summary as _summary                                   # noqa: E402
import tax_basis as _tax                                     # noqa: E402

CACHE = '.fq_cache'

# Rows that are structure rather than spending, and would otherwise dominate
# any "largest lines" list.
STRUCTURAL = re.compile(
    r'^(total|gross profit|net (operating )?income|professional income|'
    r'income from services|liabilities and equity|equity)', re.I)

# What the firm expects to see on a dental P&L. A large line that is none of
# these is the interesting kind.
EXPECTED = re.compile(
    r'wage|salar|payroll|rent|lab(oratory)? fee|dental suppl|depreciat|'
    r'insurance|tax|utilit|interest|associate|benefit|pension|401', re.I)


def _rows(text, biggest=False):
    """Every labelled figure on the first sheet of a workbook.

    With biggest=True the largest column wins rather than the last. A balance
    sheet carries a column per year, and taking the last one reports whatever
    is true now: an Amex loan of $104,250 in 2024 and nil since reads as nil,
    which is exactly the borrowing worth asking about.
    """
    body = re.split(r'^\[sheet: ', text or '', flags=re.M)
    body = body[1] if len(body) > 1 else (text or '')
    out = {}
    for line in body.split('\n'):
        name, value = _summary.split_row(line)
        if not name or value is None or STRUCTURAL.match(name.strip()):
            continue
        if biggest:
            cells = [_summary._num(c) for c in line.split('|')[1:]]
            cells = [c for c in cells if c is not None]
            if cells:
                value = max(cells, key=abs)
        out.setdefault(name.strip(), value)
    return out


def _documents(folder, marker):
    found = {}
    for path in sorted(glob.glob(os.path.join(folder, CACHE, '*.txt'))):
        text = open(path, errors='replace').read()
        if marker not in text[:300]:
            continue
        year = classify.classify(text).get('year')
        if year:
            found[year] = text
    return found


def unexplained_lines(folder, floor=25000):
    """Large spending lines that are not the usual dental cost centres."""
    pnls = _documents(folder, 'Profit and Loss')
    by_line = {}
    for year, text in pnls.items():
        for name, value in _rows(text).items():
            if value is None or abs(value) < floor:
                continue
            if EXPECTED.search(name):
                continue
            by_line.setdefault(name, {})[year] = value
    out = []
    for name, years in sorted(by_line.items()):
        if not years:
            continue
        out.append({'line': name, 'by_year': years,
                    'largest': max(years.values())})
    return sorted(out, key=lambda r: -r['largest'])


def profit_against_return(folder):
    """What the books call profit, against what the return calls it."""
    pnl = {p['year']: p for p in _summary.gather(folder) if p.get('year')}
    tax = _tax.gather(folder)
    out = []
    for year in sorted(set(pnl) & set(tax), reverse=True):
        p, t = pnl[year], tax[year]
        books = p['income_base'] - (p['expenses'] + p['other_expenses'])
        ret = t['income_base'] - t['total_deductions']
        out.append({'year': year, 'books': round(books, 2),
                    'return': round(ret, 2), 'gap': round(books - ret, 2)})
    return out


NOISE = re.compile(r'^(note payable|loan)\s*[-:]?\s*|\s*[-:]\s*\d+$', re.I)


def _creditor_words(name):
    """The words that identify a lender, with the bookkeeping stripped off.

    "Note Payable - GM Financial" and "GM Financial" are one obligation; so are
    "EIDL Grant/Loan" and "EDL Grant/Loan", where somebody dropped an I. Crude
    substring matching reported both as debts the schedule had missed, which is
    the kind of false alarm that teaches people to ignore the list.
    """
    cleaned = NOISE.sub('', name).lower()
    words = re.findall(r'[a-z]{3,}', cleaned)
    drop = {'loan', 'note', 'payable', 'grant', 'bank', 'the', 'and', 'line',
            'credit', 'com'}
    return {w for w in words if w not in drop}


def _near(a, b):
    """One word against another with a character out of place.

    The schedule says "EDL Grant/Loan" and the balance sheet says "EIDL" -- the
    same loan with a letter dropped. Reporting it as debt the schedule missed
    is the sort of false alarm that trains people to skip the list.
    """
    for x in a:
        for y in b:
            if abs(len(x) - len(y)) > 1:
                continue
            if x in y or y in x:
                return True
            if len(x) == len(y) and sum(
                    1 for p, q in zip(x, y) if p != q) == 1:
                return True
            # One character inserted or dropped: EDL against EIDL.
            short, long_ = (x, y) if len(x) < len(y) else (y, x)
            for i in range(len(long_)):
                if long_[:i] + long_[i + 1:] == short:
                    return True
    return False


def debt_not_on_schedule(folder, scheduled_names, floor=10000):
    """Obligations the balance sheet records and the schedule does not.

    Every year is looked at, not just the newest. An Amex loan of $104,250 sat
    on Oyler's 2024 balance sheet and nowhere else; by 2026 it is zero and
    invisible, and it is exactly the kind of borrowing worth asking about.
    """
    sheets = _documents(folder, 'Balance Sheet')
    known = [_creditor_words(n) for n in scheduled_names if n]
    seen, out = set(), []
    for year, text in sorted(sheets.items(), reverse=True):
        for name, value in _rows(text, biggest=True).items():
            if not re.search(r'loan|note payable|line of credit|mortgage',
                             name, re.I):
                continue
            if value is None or abs(value) < floor:
                continue
            words = _creditor_words(name)
            if any(words & k for k in known) or any(
                    _near(words, k) for k in known):
                continue
            key = tuple(sorted(words))
            if key in seen:
                continue
            seen.add(key)
            out.append({'line': name, 'balance': value,
                        'year': 'peak of the years on this sheet'})
    return out


def gather(folder, scheduled_names=()):
    return {'unexplained': unexplained_lines(folder),
            'profit_gap': profit_against_return(folder),
            'unscheduled_debt': debt_not_on_schedule(folder, scheduled_names)}


def main():
    ap = argparse.ArgumentParser(description='What the detail rows say')
    ap.add_argument('folder')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    import debt as _debt
    names = [r.get('creditor') or '' for r in
             (_debt.gather(a.folder).get('practice') or ())]
    g = gather(a.folder, names)
    if a.json:
        print(json.dumps(g, indent=1))
        return

    print('LINES THAT ARE NOT THE USUAL COST CENTRES')
    for row in g['unexplained'][:8]:
        years = '  '.join('%s %s' % (y, '{:,.0f}'.format(v))
                          for y, v in sorted(row['by_year'].items()))
        print('  %-34s %s' % (row['line'][:34], years))

    print('\nTHE BOOKS AGAINST THE RETURN')
    for row in g['profit_gap']:
        print('  %-6s books %13s   return %13s   apart %12s'
              % (row['year'], '{:,.0f}'.format(row['books']),
                 '{:,.0f}'.format(row['return']), '{:,.0f}'.format(row['gap'])))

    if g['unscheduled_debt']:
        print('\nON THE BALANCE SHEET, NOT ON THE DEBT SCHEDULE')
        for row in g['unscheduled_debt']:
            print('  %-34s %13s   %s' % (row['line'][:34],
                                         '{:,.0f}'.format(row['balance']),
                                         row['year']))


if __name__ == '__main__':
    main()
