#!/usr/bin/env python3
"""Pull the figures the Prospect Summary needs out of documents already read.

    python3 summary.py "<client folder>"            # print what it found
    python3 summary.py "<client folder>" --json     # the structured sheet

WHERE THIS SITS
The auditor answers "did they send it". This answers "what does it say". It
reads nothing from disk itself beyond the text the auditor already extracted and
cached, so it costs seconds and can never disagree with the audit about which
document is which.

WHAT IT WILL AND WILL NOT READ
A Profit & Loss arrives as a spreadsheet: labelled rows, one number each,
totals the practice's own accountant already struck. Those figures are safe to
read and safe to add up.

Production reports are the opposite. Oyler's are scans of Dentrix printouts, and
the OCR returns "2.733.136.00" for 2,733,136.00, "0,00" for 0.00 and
"01/014/2024" for a date. A number that might be a thousand times wrong is worse
than no number, so production is NOT read here. It needs either a cleaner export
from the practice or a figure typed in by a human.

That division is the whole design: compute only what the source can carry, and
say plainly what it cannot.
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

# A P&L's own section totals, as the accountant grouped them. Read rather than
# re-derived: adding up the rows ourselves would silently disagree with the
# client's books the moment a row is classified differently.
# A row is "Label | col | col | ... | Total". The workbook carries a column per
# month as well as the total, so the value is the LAST number on the line and
# the label is everything before the first bar. Matching "label | number" alone
# read a twelve-column row as a label containing bars and a number that was
# January — and produced an overhead of 1998%.
def split_row(line):
    if '|' not in line:
        return None, None
    parts = [c.strip() for c in line.split('|')]
    name = parts[0].strip()
    for cell in reversed(parts[1:]):
        v = _num(cell)
        if v is not None:
            return name, v
    return name, None

# Which section totals are overhead. Everything the practice spends to produce
# the dentistry, excluding what the owner takes home — owner comp is a
# distribution decision, not a cost of running the chair, and including it is
# how two overhead numbers for one practice come to disagree.
OWNER_WORDS = re.compile(r"owner|doctor comp|dr\.? comp|shareholder|"
                         r"officer|distribution|draw", re.I)
INCOME_WORDS = re.compile(r"\bincome\b|\brevenue\b|gross profit", re.I)
OTHER_WORDS = re.compile(r"^other\b", re.I)


def _num(s):
    """A P&L cell as a float, or None. Tolerant of 1,234.56 and (123)."""
    if s is None:
        return None
    s = str(s).strip().replace(',', '')
    neg = s.startswith('(') and s.endswith(')')
    s = s.strip('()')
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def read_pnl(text):
    """Income, expense sections and overhead from one Profit & Loss.

    Returns None when the text does not look like a P&L with usable totals,
    rather than guessing — a half-read P&L produces an overhead percentage that
    looks ordinary and is wrong.
    """
    income = None
    sections, rows = {}, {}
    # One sheet only. A workbook holds the summary and a month-by-month tab
    # carrying the same sections again; reading both counted every section twice.
    body = text or ''
    sheets = re.split(r'^\[sheet: ', body, flags=re.M)
    body = sheets[1] if len(sheets) > 1 else body

    for line in body.split('\n'):
        name, val = split_row(line)
        if not name or val is None:
            continue
        m = re.match(r'^Total for (.+)$', name, re.I)
        if m:
            label = m.group(1).strip()
            if re.fullmatch(r'income', label, re.I):
                income = val
            else:
                sections[label] = val
        elif not name.lower().startswith('total'):
            rows[name] = val

    if income is None:
        income = rows.get('Gross Profit') or rows.get('Total for Income')
    if not income:
        return None

    # Section totals nest: "Total for Salaries" sits inside "Total for EMPLOYEE
    # COSTS". Counting both double-counts the wages. Keep only the outermost by
    # dropping any section whose value is contained in a larger one that also
    # appears — the P&L's own hierarchy, read off its own arithmetic.
    top = {}
    for name, val in sections.items():
        if any(name != other and abs(val) < abs(oval)
               and _nested(name, other, text) for other, oval in sections.items()):
            continue
        top[name] = val

    # An income section is not an expense. "Total for INCOME FROM SERVICES" was
    # being added to the cost side, which put overhead near 190%.
    top = {k: v for k, v in top.items() if not INCOME_WORDS.search(k)}

    # "Other Expenses" is below the operating line — interest, depreciation,
    # one-offs. Reported, never folded in: overhead is what it costs to run the
    # chairs, and burying financing inside it is how one practice ends up with
    # two different overhead numbers.
    other = {k: v for k, v in top.items() if OTHER_WORDS.search(k)}
    owner = {k: v for k, v in top.items()
             if OWNER_WORDS.search(k) and k not in other}
    overhead_total = sum(v for k, v in top.items()
                         if k not in owner and k not in other)
    return {
        'income': round(income, 2),
        'sections': {k: round(v, 2) for k, v in sorted(top.items())},
        'owner_comp': {k: round(v, 2) for k, v in owner.items()},
        'other_expenses': {k: round(v, 2) for k, v in other.items()},
        'overhead': round(overhead_total, 2),
        'overhead_pct': round(100.0 * overhead_total / income, 1) if income else None,
    }


def _nested(inner, outer, text):
    """Does the 'Total for <inner>' line appear before 'Total for <outer>'?

    A P&L prints a subtotal before the total that contains it, so order is the
    nesting. Crude, and deliberately so: the alternative is a chart-of-accounts
    model per client, and every practice names its sections differently.
    """
    i = text.find('Total for %s' % inner)
    o = text.find('Total for %s' % outer)
    return 0 <= i < o


def gather(folder):
    """Every P&L the auditor has already read, newest year first."""
    cache = os.path.join(folder, CACHE)
    if not os.path.isdir(cache):
        cache = os.path.join(folder, 'Original_sourcedocs', CACHE)
    out = []
    for p in glob.glob(os.path.join(cache, '*.txt')):
        text = open(p, errors='replace').read()
        if len(text.strip()) < 40:
            continue
        doc = classify.classify(text)
        if doc['doc_type'] != 'pnl':
            continue
        got = read_pnl(text)
        if got:
            got['year'] = doc.get('year')
            got['period'] = doc.get('period') or doc.get('granularity')
            out.append(got)
    out.sort(key=lambda d: (d.get('year') or ''), reverse=True)
    return out


def main():
    ap = argparse.ArgumentParser(description="Figures for the Prospect Summary")
    ap.add_argument('folder')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    found = gather(a.folder)
    if a.json:
        print(json.dumps({'profit_and_loss': found}, indent=1))
        return
    if not found:
        print("No readable Profit & Loss in this client's cache. Run the audit first.")
        return
    for p in found:
        print("\n%s  (%s)" % (p.get('year') or 'year unknown', p.get('period') or ''))
        print("  income            %15s" % '{:,.2f}'.format(p['income']))
        for k, v in p['sections'].items():
            print("    %-30s %13s" % (k[:30], '{:,.2f}'.format(v)))
        if p['other_expenses']:
            print("  below the line (not in overhead)")
            for k, v in p['other_expenses'].items():
                print("    %-30s %13s" % (k[:30], '{:,.2f}'.format(v)))
        if p['owner_comp']:
            print("  owner comp (excluded from overhead)")
            for k, v in p['owner_comp'].items():
                print("    %-30s %13s" % (k[:30], '{:,.2f}'.format(v)))
        print("  OVERHEAD          %15s   %s%%"
              % ('{:,.2f}'.format(p['overhead']), p['overhead_pct']))


if __name__ == '__main__':
    main()
