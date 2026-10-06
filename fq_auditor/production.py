#!/usr/bin/env python3
"""Read a scanned Practice Analysis, and only believe the figures twice.

    python3 production.py "<client folder>"
    python3 production.py "<client folder>" --json

WHY THIS IS NOT IN summary.py
A Profit & Loss arrives as a spreadsheet, so its numbers are already numbers.
A Practice Analysis arrives as a scan of a Dentrix printout, so its numbers are
whatever the OCR thought it saw. The first attempt read 2,733,136.00 as
"2.733.136.00" and 0.00 as "0,00", and a figure that might be a thousand times
wrong is worse in front of a prospect than an honest blank.

THE GATE
What actually goes wrong in these scans is the separators — the commas and
periods between digits — not the digits. So each page is read twice, at two
resolutions, and both readings are stripped to their digits alone and divided
by a hundred for the cents. A label's figure is accepted only when the two
passes land on the same number. Where they disagree, the figure is reported as
needing a human, with both readings shown so the analyst can settle it in one
glance rather than opening the scan and hunting.

Measured on Oyler's 2024 Practice Analysis: 9 of 11 labels agreed. The point is
not that two passes are right — it is that two passes that disagree are visibly
wrong, which one pass never is.
"""
import os
import re
import sys
import glob
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS_DPI = (300, 400)

# The labels the Prospect Summary's practice table asks for, each matched on a
# distinctive fragment rather than the full printed line, because Dentrix wraps
# and abbreviates them differently between report versions.
LABELS = [
    ('charges_uninsured',  r'non-?insured charges'),
    ('charges_insured',    r'^\s*insured charges'),
    ('adjustments_add',    r'adjustments:?\s*additions'),
    ('total_charges',      r'total charges'),
    ('patient_payments',   r'patient payments'),
    ('insurance_payments', r'insurance payments'),
    ('adjustments_less',   r'adjustments:?\s*reductions'),
    ('total_credits',      r'total credits'),
    ('receivables',        r'total receivables'),
    ('credit_balances',    r'credit balances'),
    ('new_patients',       r'^\s*new patients'),
    ('referred_patients',  r'referred patients'),
    ('active_patients',    r'^\s*active patients'),
]


def digits_value(token):
    """A money token as a number, reading only its digits.

    "2.733.136.00", "2,733,136.00" and "2 733 136 00" are the same scan of the
    same figure; the separators are the part OCR gets wrong. Strip to digits,
    take the last two as cents. Returns None for a token with no digits.
    """
    neg = token.strip().startswith('(') or token.strip().startswith('-')
    d = re.sub(r'\D', '', token)
    if not d:
        return None
    v = int(d) / 100.0
    return -v if neg else v


def whole_value(token):
    """A count (new patients, visits) as an integer — no implied cents."""
    d = re.sub(r'\D', '', token)
    return int(d) if d else None


COUNT_FIELDS = {'new_patients', 'referred_patients', 'active_patients'}
MONEY_FIELDS = {k for k, _ in LABELS} - COUNT_FIELDS

# One figure, never two. An earlier version let a token span whitespace, so a
# row of columns read as a single 27-digit number.
TOKEN = re.compile(r'[\(\-]?\d[\d,.]*\d[\)]?|(?<!\d)\d(?!\d)')


def read_pass(text):
    """{field: value} from one OCR pass of a Practice Analysis."""
    out = {}
    for line in (text or '').split('\n'):
        # OCR drops a space inside a figure — "1,404, 103.00" for 1,404,103.00,
        # "4,467 ,838.40" for 4,467,838.40 — which splits one number into two
        # and reads a practice's year as $14.04. A space touching a separator
        # is never a column break, so close it before tokenising.
        line = re.sub(r'\s+([,.])', r'\1', line)
        line = re.sub(r'([,.])\s+(?=\d)', r'\1', line)
        low = line.lower()
        for key, pat in LABELS:
            if key in out or not re.search(pat, low, re.I):
                continue
            # The figure is the FIRST number on the line. These reports print
            # the period total first and the month-to-date columns after it;
            # taking the last column read a year's charges as one month's.
            toks = TOKEN.findall(line)
            if not toks:
                continue
            tok = toks[0]
            # Counts are not read. On these reports the first column carries
            # the period's money total but reads 0 for every patient count, so
            # the count columns mean something else and guessing which would be
            # a confident wrong number in front of a prospect.
            if key not in MONEY_FIELDS:
                break
            v = digits_value(tok)
            if v is not None:
                out[key] = v
            break
    return out


def read_pdf(path, dpis=PASS_DPI):
    """Two independent OCR passes of one scan, as {field: {dpi: value}}."""
    import fitz
    import extract
    doc = fitz.open(path)
    passes = {}
    for dpi in dpis:
        text = []
        for page in doc:
            text.append(extract._ocr(page, dpi, extract.OCR_CFG_BLOCK))
        passes[dpi] = read_pass('\n'.join(text))
    doc.close()
    return passes


def agree(passes):
    """Split two passes into what they agree on and what they do not.

    Returns (values, disputed). A field only one pass saw is disputed, not
    accepted: a figure the other resolution could not find at all is exactly
    the kind the scan is too poor to carry.
    """
    keys = set()
    for got in passes.values():
        keys |= set(got)
    values, disputed = {}, {}
    for k in keys:
        seen = [got.get(k) for got in passes.values()]
        if None not in seen and len(set(seen)) == 1:
            values[k] = seen[0]
        else:
            disputed[k] = {str(d): got.get(k) for d, got in passes.items()}
    return values, disputed


def arithmetic_check(values):
    """Does the report add up, using only figures both passes agreed on?

    The scan prints its own subtotal: uninsured + insured + additions = total
    charges. When the accepted figures reproduce it, two passes agreeing was
    not two passes making the same mistake. Returns None when a piece of the
    sum was not accepted, because an unchecked figure is not a failed one.
    """
    parts = ('charges_uninsured', 'charges_insured', 'adjustments_add')
    if not all(k in values for k in parts) or 'total_charges' not in values:
        return None
    want = values['total_charges']
    got = sum(values[k] for k in parts)
    return {'expected': round(want, 2), 'from_parts': round(got, 2),
            'agrees': abs(got - want) < 1.0}


def find_reports(folder):
    """The Practice Analysis scans in a client folder, newest year first."""
    hits = []
    for root, _dirs, files in os.walk(folder):
        if os.path.basename(root).startswith('.'):
            continue
        for name in files:
            if not name.lower().endswith('.pdf'):
                continue
            low = name.lower()
            if 'practice analysis' not in low and 'analysis summary' not in low:
                continue
            m = re.search(r'(20\d\d)', name)
            hits.append((m.group(1) if m else '', os.path.join(root, name)))
    hits.sort(reverse=True)
    # One report per year: the folder holds both the filed copy and the
    # original, and reading the same scan twice doubles the slowest step here.
    seen, out = set(), []
    for year, path in hits:
        if year in seen:
            continue
        seen.add(year)
        out.append((year, path))
    return out


def gather(folder, dpis=PASS_DPI):
    """Every Practice Analysis read twice, keyed by year."""
    out = {}
    for year, path in find_reports(folder):
        passes = read_pdf(path, dpis)
        values, disputed = agree(passes)
        out[year] = {'source': os.path.basename(path),
                     'values': values, 'disputed': disputed,
                     'check': arithmetic_check(values)}
    return out


def main():
    ap = argparse.ArgumentParser(description='Read scanned production reports')
    ap.add_argument('folder')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--year')
    a = ap.parse_args()
    got = gather(a.folder)
    if a.year:
        got = {k: v for k, v in got.items() if k == a.year}
    if a.json:
        print(json.dumps(got, indent=1))
        return
    for year in sorted(got, reverse=True):
        rec = got[year]
        print('\n%s  (%s)' % (year or 'year unknown', rec['source']))
        for k, v in sorted(rec['values'].items()):
            print('   %-20s %15s' % (k, '{:,.2f}'.format(v)
                                     if isinstance(v, float) else v))
        chk = rec.get('check')
        if chk:
            print('   %-20s %s' % ('adds up?',
                  'yes' if chk['agrees'] else
                  'NO — parts %s vs total %s'
                  % (chk['from_parts'], chk['expected'])))
        for k, v in sorted(rec['disputed'].items()):
            print('   %-20s NEEDS A HUMAN  %s' % (k, v))


if __name__ == '__main__':
    main()
