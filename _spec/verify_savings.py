#!/usr/bin/env python3
"""Rerun savings.py against Brogan's worksheet for every signed client.

    python3 _spec/verify_savings.py [<Signed folder>]

Reads each client's `savings worksheet.pdf` (his Numbers sheet printed to PDF)
and the consult deck beside it. Takes his deposits and first-year expenses as
given, because those are his inputs, and checks that savings.py produces his
year-end values on both paths from the first year to retirement. It also checks
the run-out year. Nothing here is typed in from a client: every figure is read
from the two PDFs.

The PDF is a Numbers sheet tiled across pages, so the columns are recovered by
pattern rather than by position: the age-year-deposit rows give the deposit
columns in sheet order (current, current run-out, Four Quadrants), and the
"Year-end portfolio Value (8.5% / 9.0%)" headers start each value column.
"""
import os
import re
import sys
import glob
import datetime
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'fq_auditor'))
import savings as S                                          # noqa: E402

DEFAULT = '/Volumes/Analysis/Brogan/Prospects/2026/_TEST/_Converted/2.) Signed'


def _text(pdf):
    return subprocess.run(['pdftotext', '-layout', pdf, '-'],
                          capture_output=True, text=True).stdout


def deposit_blocks(t):
    rows = re.findall(r'^\s*(\d\d)\s+(20\d\d)\s+(-?\d*)USD', t, re.M)
    out, cur = [], []
    for age, y, v in rows:
        y = int(y)
        if cur and y <= cur[-1][1]:
            out.append(cur)
            cur = []
        cur.append((int(age), y, int(v) if v else 0))
    if cur:
        out.append(cur)
    return out


def value_columns(t):
    out, cur = [], None
    for line in t.splitlines():
        if re.search(r'Value \((8\.5|9\.0)% Ret', line):
            cur = []
            out.append(cur)
            continue
        m = re.match(r'^\s*(-?\d+)USD\s+(\d+)USD', line)
        if cur is not None and m:
            cur.append((int(m.group(1)), int(m.group(2))))
    return out


def deck_facts(deck):
    t = re.sub(r'\s+', ' ', _text(deck))
    m = re.search(r'portfolio value \$([\d,]+)', t)
    start = int(m.group(1).replace(',', '')) if m else None
    d = re.search(r'(January|February|March|April|May|June|July|August|'
                  r'September|October|November|December) \d{1,2}, 20\d\d', t)
    date = datetime.datetime.strptime(d.group(0), '%B %d, %Y').date()
    return start, date


def check(folder):
    ws = glob.glob(os.path.join(folder, 'savings worksheet*.pdf'))[0]
    decks = [p for p in glob.glob(os.path.join(folder, '*.pdf'))
             if 'savings' not in p.lower()]
    decks.sort(key=lambda p: ('final' not in p.lower(), 'Consultation' in p))
    start, date = deck_facts(decks[0])
    t = _text(ws)
    blocks, cols = deposit_blocks(t), value_columns(t)
    cur_b, fq_b = blocks[0], blocks[2]
    y0 = cur_b[0][1]
    base = cur_b[0][2]
    retire = max(y for _, y, v in cur_b if v > 2 * base)
    cur_d = {y: v for _, y, v in cur_b}
    fq_d = {y: v for _, y, v in fq_b}
    f = S.first_year_fraction(date)
    note = []
    if start is None:
        start = round(cols[0][0][0] / (1 + S.CURRENT_RETURN * f))
        note.append('start derived')

    def score(path, col):
        n = ok = 0
        for i, (v, _) in enumerate(col):
            y = y0 + i
            if y > retire:
                break
            n += 1
            # Five dollars, or a hundred-thousandth of the value: two of his
            # sheets carry a rounded cell that drifts a few dollars over
            # twenty-five years of compounding (McDonald $13 on $1.9m).
            ok += abs(path[y] - v) <= max(5, abs(v) * 1e-5)
        return ok, n

    best = None
    for ff in (f, 1.0):
        for r1 in (S.FIRST_YEAR_FQ_RETURN, S.FQ_RETURN):
            c = S.current_path(start, ff, cur_d, retire, cols[0][0][1], y0, retire + 40)
            q = S.fq_path(start, ff, fq_d, retire, cols[2][0][1], y0, retire + 40, r1=r1)
            sc, sq = score(c, cols[0]), score(q, cols[2])
            key = sc[0] + sq[0]
            if best is None or key > best[0]:
                best = (key, sc, sq, ff, r1, c)
    _, sc, sq, ff, r1, c = best
    firm_ro = next((y0 + i for i, (v, _) in enumerate(cols[0]) if v < 0), None)
    if ff != f:
        note.append('whole first year')
    if r1 != S.FIRST_YEAR_FQ_RETURN:
        note.append('9% first year')
    return sc, sq, firm_ro, S.runout_year(c), note


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    folders = sorted(set(os.path.dirname(p) for p in
                         glob.glob(os.path.join(root, '**', 'savings worksheet*.pdf'),
                                   recursive=True)))
    full = 0
    for d in folders:
        name = os.path.relpath(d, root).split('/Consult')[0]
        try:
            sc, sq, fro, oro, note = check(d)
        except Exception as e:                               # noqa: BLE001
            print('%-32s could not read: %s' % (name, e))
            continue
        exact = sc[0] == sc[1] and sq[0] == sq[1]
        full += exact
        print('%-32s current %2d/%-2d  FQ %2d/%-2d  run-out %s/%s  %s%s' % (
            name, sc[0], sc[1], sq[0], sq[1], fro, oro,
            'EXACT ' if exact else '', ', '.join(note)))
    print('\n%d of %d reproduced row for row to retirement.' % (full, len(folders)))


if __name__ == '__main__':
    main()
