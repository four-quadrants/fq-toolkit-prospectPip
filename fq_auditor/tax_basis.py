#!/usr/bin/env python3
"""Overhead on a tax basis, read from the practice's 1120-S.

    python3 tax_basis.py "<client folder>"
    python3 tax_basis.py "<client folder>" --json

WHY A SECOND BASIS AT ALL
The P&L is the bookkeeper's account of the year; the return is the account the
practice swore to. They are built from the same money and they rarely agree,
because the return follows tax rules about what is deductible and when. The
gap between them is not an error to be reconciled away -- it is the thing the
first meeting is about, and a prospect summary that shows only one basis
invites an argument it cannot settle.

So this computes the same ratio the firm computes off the P&L, using the
return's own lines:

    income base = Total income (loss)
    overhead    = Total deductions
                  - Compensation of officers        (the owner's own pay)
                  - Depreciation / amortisation     (not a cash cost of a chair)
    overhead %  = overhead / income base

Officer compensation is held out for exactly the reason doctor salary is held
out of the P&L figure: what the owner pays themselves is a distribution
decision, not the cost of running the practice, and leaving it in makes two
practices with identical economics look different.

WHAT IT READS
Tax software prints a two-year comparative on the return's summary page, so a
single current-year return usually yields both years. Labels are matched on a
fragment, and the figures are the numbers that follow on their own lines --
which is how these PDFs lay out, with the label's leader dots on one line and
each year's figure beneath.
"""
import os
import re
import sys
import glob
import json
import argparse

# The lines this needs, matched on a distinctive fragment of the printed label.
WANT = [
    ('gross_receipts',   r'gross receipts less returns'),
    ('total_income',     r'total income \(loss\)'),
    ('officer_comp',     r'compensation of officers'),
    ('salaries',         r'salaries/wages'),
    ('depreciation',     r'^\s*depreciation\b'),
    ('amortization',     r'^\s*amortization\b'),
    ('total_deductions', r'total deductions'),
    ('ordinary_income',  r'ordinary business income'),
]

NUM = re.compile(r'^\(?-?[\d,]+\)?$')


def _num(s):
    s = s.strip().replace(',', '')
    neg = s.startswith('(') and s.endswith(')')
    s = s.strip('()')
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def parse(text):
    """{field: [year1, year2, ...]} from a return's comparative summary page.

    The figures follow the label on their own lines, newest year first, with a
    difference column last on a two-year comparative. The difference is dropped
    by taking at most two figures and checking the third equals their spread --
    reading it as a third year produced a year with a $229,658 income.
    """
    lines = [l.strip() for l in (text or '').split('\n')]
    out = {}
    for i, line in enumerate(lines):
        low = re.sub(r'[.…]{2,}', ' ', line).strip().lower()
        for key, pat in WANT:
            if key in out or not re.search(pat, low, re.I):
                continue
            vals = []
            for nxt in lines[i + 1:i + 5]:
                if not NUM.match(nxt):
                    break
                v = _num(nxt)
                if v is None:
                    break
                vals.append(v)
            if not vals:
                continue
            # Drop a trailing difference column when it is one.
            if len(vals) >= 3 and abs((vals[0] - vals[1]) - vals[2]) < 1.5:
                vals = vals[:2]
            out[key] = vals[:2]
            break
    return out


def overhead(fields, idx=0):
    """Tax-basis overhead for one year of a parsed return."""
    def g(key):
        v = fields.get(key)
        return v[idx] if v and len(v) > idx else None

    base = g('total_income')
    deductions = g('total_deductions')
    if base in (None, 0) or deductions is None:
        return None
    officers = g('officer_comp') or 0.0
    da = (g('depreciation') or 0.0) + (g('amortization') or 0.0)
    oh = deductions - officers - da
    return {
        'income_base': round(base, 2),
        'total_deductions': round(deductions, 2),
        'officer_comp': round(officers, 2),
        'depreciation_amort': round(da, 2),
        'overhead': round(oh, 2),
        'overhead_pct': round(100.0 * oh / base, 1),
    }


def find_returns(folder):
    """The practice's S-corporation returns, newest first.

    Only the client copy: a preparer file copy of the same year is the same
    return and reading both just produces the same year twice.
    """
    hits = []
    for root, _dirs, files in os.walk(folder):
        if os.path.basename(root).startswith('.'):
            continue
        for name in files:
            low = name.lower()
            if not low.endswith('.pdf') or 's-corporation' not in low:
                continue
            if 'clientcopy' not in low.replace(' ', ''):
                continue
            if '_k1_' in low or 'k1' in low.split('_')[-1]:
                continue
            m = re.search(r'(20\d\d)', name)
            hits.append((m.group(1) if m else '', os.path.join(root, name)))
    seen, out = set(), []
    for year, path in sorted(hits, reverse=True):
        if year in seen:
            continue
        seen.add(year)
        out.append((year, path))
    return out


def read_return(path, pages=6):
    """The comparative summary page of a return, as text."""
    import fitz
    doc = fitz.open(path)
    try:
        for i in range(min(pages, doc.page_count)):
            text = doc[i].get_text()
            if 'Total deductions' in text:
                return text
    finally:
        doc.close()
    return ''


def gather(folder):
    """{year: tax-basis overhead} across the returns in a client folder.

    A current return carries the prior year beside it, so the newest filing
    usually answers two years on its own. Where two returns both speak to a
    year, the newer filing wins -- it is the one that reflects any amendment.
    """
    out = {}
    for filed_year, path in find_returns(folder):
        fields = parse(read_return(path))
        if not fields:
            continue
        years = [filed_year]
        if filed_year.isdigit():
            years.append(str(int(filed_year) - 1))
        for idx, year in enumerate(years):
            got = overhead(fields, idx)
            if got and year not in out:
                got['source'] = os.path.basename(path)
                out[year] = got
    return out


def main():
    ap = argparse.ArgumentParser(description='Tax-basis overhead from 1120-S')
    ap.add_argument('folder')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    got = gather(a.folder)
    if a.json:
        print(json.dumps(got, indent=1))
        return
    if not got:
        print('No S-corporation return with a deductions summary in %s' % a.folder)
        return
    for year in sorted(got, reverse=True):
        g = got[year]
        print('\n%s' % year)
        print('  income base        %15s' % '{:,.0f}'.format(g['income_base']))
        print('  total deductions   %15s' % '{:,.0f}'.format(g['total_deductions']))
        print('  less officer comp  %15s' % '{:,.0f}'.format(g['officer_comp']))
        print('  less dep/amort     %15s' % '{:,.0f}'.format(g['depreciation_amort']))
        print('  OVERHEAD           %15s   %s%%'
              % ('{:,.0f}'.format(g['overhead']), g['overhead_pct']))


if __name__ == '__main__':
    main()
