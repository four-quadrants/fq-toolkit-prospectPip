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
#
# Two more layouts, found on the second and third clients:
#   QuickBooks Desktop to Excel (Spaulding) indents by leading empty cells,
#   " |  | Total Income |  |  | 58368.99 | ... | 575874.2", so the label is the
#   first cell with words in it, not the first cell.
#   QuickBooks Online to PDF (Rebol) has no bars at all,
#   "Total for Income $2,678,845.79", so the figure is the money at the end.
TRAILING_MONEY = re.compile(
    r'^(.*?[A-Za-z].*?)\s+(\(?-?\$?\s*[\d,]+\.\d{2}\)?)\s*$')


def split_row(line):
    if '|' not in line:
        m = TRAILING_MONEY.match(line.strip())
        if not m:
            return None, None
        return m.group(1).strip(), _num(m.group(2).replace('$', ''))
    parts = [c.strip() for c in line.split('|')]
    lead = 0
    while lead < len(parts) - 1 and not parts[lead]:
        lead += 1
    name = parts[lead].strip()
    for cell in reversed(parts[lead + 1:]):
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


MONTHS = ('january february march april may june july august september '
          'october november december').split()


def period_months(text):
    """How many months a P&L covers, read off its own heading.

    Every one of these sheets prints its period under the practice name:
    "January-December, 2024" or just "July 2026". That line is the only honest
    statement of what the figures below it add up to — column counts do not
    survive a summary tab. Returns None when the heading says nothing, because
    a guessed span turns one month's income into a year's collections.
    """
    head = '\n'.join((text or '').split('\n')[:12]).lower()
    # "January-December, 2024", and QuickBooks Online's
    # "January 1-December 31, 2024", with a day after each month.
    m = re.search(r'(%s)(?:\s+\d{1,2})?\s*(?:-|–|—|\s+through\s+|\s+to\s+)\s*(%s)'
                  % ('|'.join(MONTHS), '|'.join(MONTHS)), head)
    if m:
        a, b = MONTHS.index(m.group(1)), MONTHS.index(m.group(2))
        return (b - a) % 12 + 1
    for mon in MONTHS:
        if re.search(r'\b%s\b[,\s]+20\d\d' % mon, head):
            return 1
    return None


def spans_years(text):
    """True when the heading covers more than one calendar year."""
    head = '\n'.join((text or '').split('\n')[:12]).lower()
    m = re.search(r'(?:%s)\w*\.?\s*(?:\d{1,2},?\s*)?,?\s*(20\d\d)\s*(?:-|–|—|\s+through\s+|\s+to\s+)\s*'
                  r'(?:%s)\w*\.?\s*(?:\d{1,2},?\s*)?,?\s*(20\d\d)'
                  % ('|'.join(MONTHS), '|'.join(MONTHS)), head)
    return bool(m and m.group(1) != m.group(2))


def _find_total(rows, *names):
    """A 'Total for X' figure by name, matched exactly then by prefix."""
    norm = {re.sub(r'\s+', ' ', k).strip().lower(): v for k, v in rows.items()}
    for n in names:
        if n.lower() in norm:
            return norm[n.lower()]
    for n in names:
        for k, v in norm.items():
            if k.startswith(n.lower()):
                return v
    return None


def _widest_sheet(text):
    """The sheet of a workbook that covers the most months."""
    sheets = re.split(r'^\[sheet: ', text, flags=re.M)
    if len(sheets) < 2:
        return text
    best, best_months = sheets[1], -1
    for chunk in sheets[1:]:
        months = period_months(chunk) or 0
        # A tie goes to the earlier sheet, which is the one the bookkeeper put
        # first and usually the one a person would open.
        if months > best_months:
            best, best_months = chunk, months
    return best


def read_pnl(text):
    """Overhead from one Profit & Loss, on Four Quadrants' own definition.

        income base = Total Income + Total Other Income
        overhead    = Total Expense + Total Other Expense
                      - doctor salary - (depreciation + amortisation + s179)
        overhead %  = overhead / income base

    WHY THIS IS SPELLED OUT
    An earlier version dropped "Other Expenses" wholesale, on the reasoning
    that a section called "other" sits below the operating line. On this firm's
    P&Ls it does not: Other Expenses is where ASSOCIATE EXPENSES and DOCTOR
    EXPENSES live, and on Oyler that was $1.23m of real cost on a $4.1m
    practice. Excluding it printed 59.4% against a true 77.0% -- a number that
    looked healthy, sat conveniently just under the firm's 60% target, and was
    wrong by eighteen points.

    Each of depreciation, amortisation and section 179 is looked up on its own
    and contributes zero when absent, because a cash-basis P&L often carries
    none of them and that is not a mapping failure.

    Returns None when the sheet does not carry the totals this needs, rather
    than computing a percentage from half a P&L.
    """
    sections, rows, lines = {}, {}, {}
    # One sheet, but the RIGHT one. A workbook holds a summary tab and a
    # month-by-month tab carrying the same sections again, and reading both
    # counts everything twice -- but reading the first blindly was worse. On
    # Oyler's 2026 file the Summary tab is July alone at $312,810 while the By
    # Month tab totals $2,169,371 for January to July, and the file is named
    # "YtD". So the sheet covering the longest period wins.
    body = _widest_sheet(text or '')

    pending = None
    for line in body.split('\n'):
        name, val = split_row(line)
        # A PDF page can break a total from its figure: "Total for Expenses"
        # on one line and "$1,931,224.10" on the next (Rebol 2024).
        if name is None and pending and re.match(
                r'^\(?-?\$?\s*[\d,]+\.\d{2}\)?$', line.strip()):
            name, val = pending, _num(line.strip().replace('$', ''))
        if not line.strip():
            continue                     # a blank line does not end the wait
        pending = None
        if name is None and re.match(r'^Total (?:for )?\S', line.strip(), re.I):
            pending = line.strip()
            continue
        if not name or val is None:
            continue
        # QuickBooks Online numbers its accounts: "71100 Depreciation
        # Expense", "70055 Owner Wages". The number is not part of the name.
        name = re.sub(r'^(Total (?:for )?)?\d{3,6}\s+', r'\1', name,
                      flags=re.I)
        # "Total for Income" (QuickBooks Online), "Total Income" (Desktop).
        m = re.match(r'^Total (?:for )?(.+)$', name, re.I)
        if m:
            sections[m.group(1).strip()] = val
        elif not name.lower().startswith('total'):
            lines.setdefault(name.strip(), val)
        rows[name] = val

    income = _find_total(sections, 'income')
    if income is None:
        return None
    other_income = _find_total(sections, 'other income') or 0.0
    expenses = _find_total(sections, 'expenses', 'expense')
    other_exp = _find_total(sections, 'other expenses', 'other expense') or 0.0
    if expenses is None:
        return None

    # Rebol's books call it "Owner Wages", under an Owner section that also
    # holds his auto, health insurance and payroll taxes. Only the wages come
    # out: that reproduces the 78.3% on his consult deck, and taking the
    # whole Owner section out would print 76.0%.
    doctor_salary = _find_total(lines, 'doctor wages', 'dr salary',
                                'doctor salary', 'owner wages') or 0.0
    # Three independent lookups; a missing one contributes zero.
    da_found, da_total = [], 0.0
    for label, *aliases in (('Depreciation', 'depreciation expense',
                             'depreciation'),
                            ('Amortization', 'amortization expense',
                             'amortization'),
                            ('Section 179', 'section 179 expense',
                             'section 179 depreciation')):
        hit = None
        for key, v in lines.items():
            k = key.strip().lower()
            if any(k.startswith(a) for a in aliases):
                hit = v
                break
        if hit:
            da_found.append(label)
            da_total += hit

    base = income + other_income
    overhead = expenses + other_exp - doctor_salary - da_total
    return {
        'income': round(income, 2),
        'other_income': round(other_income, 2),
        'income_base': round(base, 2),
        'expenses': round(expenses, 2),
        'other_expenses': round(other_exp, 2),
        'doctor_salary': round(doctor_salary, 2),
        'depreciation_amort': round(da_total, 2),
        'da_found': da_found,
        'sections': {k: round(v, 2) for k, v in sorted(sections.items())},
        'overhead': round(overhead, 2),
        'overhead_pct': round(100.0 * overhead / base, 1) if base else None,
        # Measured on the sheet actually read, not on the file. Reading it
        # from the whole text picked up the Summary tab's 'July 2026' and
        # called a seven-month year-to-date a single month.
        'months': period_months(body),
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
        if spans_years(text):
            # A comparative P&L with a column per year ("January,
            # 2021-June, 2025") cannot be read as one period: its totals
            # column adds five years together. Leave it to Claude's readings.
            continue
        got = read_pnl(text)
        if got:
            got['year'] = doc.get('year')
            got['period'] = doc.get('period') or doc.get('granularity')
            out.append(got)
    # Newest year first, and within a year the largest income LAST. Every
    # reader builds {year: pnl} from this list, so the last one of a year is
    # the one kept, and it has to be the practice. Rebol's folder also holds
    # the P&L of his building LLC ($113,000 of rent against the practice's
    # $2.68m), and in file order the LLC was the one kept.
    # Two copies of the same P&L (the client's spreadsheet and a PDF print of
    # it) have the same income; keep the one with more lines read. A PDF puts
    # the labels and figures in separate columns, so Oyler's 2025 PDF gave no
    # Doctor Wages and overhead came out 86% instead of 77%.
    def detail(d):
        return sum(1 for v in d.values()
                   if isinstance(v, (int, float)) and not isinstance(v, bool) and v)
    out.sort(key=lambda d: ((d.get('year') or ''),
                            -round(d.get('income_base') or 0, -2),
                            -detail(d)),
             reverse=True)
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
