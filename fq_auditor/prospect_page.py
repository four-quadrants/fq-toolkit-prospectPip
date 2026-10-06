#!/usr/bin/env python3
"""Render the two-page Prospect Summary from whatever has been established.

    python3 prospect_page.py "<client folder>"      # writes _Audit/<client> - Prospect Summary.html

WHY EVERY FIELD CARRIES A SOURCE
Rendering the page is the easy half — it is a layout. The hard half is knowing
which numbers are safe to print, and this document is read by an advisor sitting
in front of a prospect. A figure with no source is worse than a gap: a gap gets
chased, a wrong number gets quoted.

So each field is one of three things, and says which:

    a value, with the document it came from
    NOT YET SENT      - the client has not provided what it needs
    NEEDS A HUMAN     - we hold the document but cannot read it safely

The last one matters. Oyler's production reports are scans whose OCR returns
"2.733.136.00" for 2,733,136 and "0,00" for zero. The documents are here; the
figures are not trustworthy. Printing them because they exist is exactly the
failure this layout is built to prevent.
"""
import os
import re
import sys
import json
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import summary as _summary                                    # noqa: E402

GAP = 'NOT YET SENT'
HUMAN = 'NEEDS A HUMAN'


def _e(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def money(v):
    return '{:,.0f}'.format(v) if isinstance(v, (int, float)) else None


def cell(value, source=None, why=None):
    """One field: what it is, and where it came from."""
    if value is None:
        tag = why or GAP
        klass = 'gap' if tag == GAP else 'human'
        return '<span class="%s">%s</span>' % (klass, _e(tag))
    src = ('<span class="src">%s</span>' % _e(source)) if source else ''
    return '%s%s' % (_e(value), src)


ANALYSIS_ROWS = [
    ('Gross production', 'bold0'), ('Production adjustments', ''),
    ('Net production', 'b'), ('Gross collections', ''),
    ('Collection adjustments', ''), ('Net collections', 'b'),
    ('Production \u2014 owner', ''), ('Production \u2014 associate', ''),
    ('Hygiene production', ''), ('Doctor % of production', ''),
    ('Hygiene % of production', ''), ('Total patients', ''),
    ('New patients', ''), ('Days worked', ''),
    ('Gross production / patient', ''), ('Net production / patient', ''),
    ('Gross production / day', ''), ('Net production / day', ''),
    ('Patients / day', ''), ('New patients % of total', ''),
    ('Production adjustment %', 'b'),
]

PRACTICE_NOTES = ['Ownership', 'Growth', 'Team', 'Productivity', 'Payer mix',
                  'Costs', 'Transition']
PERSONAL_NOTES = ['Household', 'Spending', 'Retirement', 'Liquidity',
                  'Protection', 'Structure', 'Stated goal']


def build(folder, client=None):
    client = client or os.path.basename(folder.rstrip('/'))
    pnl = _summary.gather(folder)
    by_year = {p['year']: p for p in pnl if p.get('year')}
    years = sorted(by_year)[-3:]

    L = []
    a = L.append
    a('<!doctype html><meta charset="utf-8"><title>Prospect summary \u2014 %s</title>' % _e(client))
    a('<style>%s</style>' % CSS)

    # ---------------------------------------------------------------- page 1
    a('<div class="pg">')
    a('<div class="hd"><div>')
    a('<div class="kick">PROSPECT SUMMARY &nbsp;\u00b7&nbsp; ONBOARDING &amp; DATA INTAKE</div>')
    a('<h1>%s</h1>' % _e(client))
    a('<div class="sub">%s</div>' % cell(None, why=HUMAN))
    a('</div><div class="meta">PREPARED %s<br>ADVISOR %s<br>ANALYST %s<br>'
      '<span class="stage">STAGE &nbsp;DATA RECEIVED</span></div></div>'
      % (datetime.date.today().strftime('%d.%m.%Y'), cell(None, why=HUMAN),
         cell(None, why=HUMAN)))

    latest = by_year.get(years[-1]) if years else None
    a('<div class="kpis">')
    for label, val, src, why in (
        ("NET COLLECTIONS '%s" % (years[-1][-2:] if years else '--'),
         ('$' + money(latest['income'])) if latest else None,
         'P&L' if latest else None, None),
        ('OVERHEAD', ('%.1f%%' % latest['overhead_pct']) if latest else None,
         'P&L' if latest else None, None),
        ('OWNER COMP', None, None, HUMAN),
        ('TOTAL DEBT', None, None, None),
        ('OBSERVED ASSETS', None, None, None)):
        a('<div class="kpi"><div class="kl">%s</div><div class="kv">%s</div></div>'
          % (label, cell(val, src, why)))
    a('</div>')

    a('<div class="cols">')

    # ---- left: initial notes --------------------------------------------
    a('<div class="colL">')
    a('<h2>Initial notes</h2>')
    for head, items in (('PRACTICE', PRACTICE_NOTES), ('PERSONAL', PERSONAL_NOTES)):
        a('<div class="tag %s">%s</div><ul class="notes">'
          % ('tp' if head == 'PRACTICE' else 'tn', head))
        for n in items:
            a('<li><b>%s</b> \u2014 %s</li>' % (_e(n), cell(None, why=HUMAN)))
        a('</ul>')
    a('</div>')

    # ---- right: the numbers ---------------------------------------------
    a('<div class="colR">')
    a('<h2>Practice analysis<span class="src2">SOURCE: PMS + PRACTICE FINANCIALS</span></h2>')
    a('<table class="an"><tr><th>METRIC</th>')
    for n, y in enumerate(years):
        a('<th>%s</th>' % y)
        if n:
            a('<th class="d">\u0394</th>')
    a('</tr>')
    for name, cls in ANALYSIS_ROWS:
        a('<tr class="%s"><td>%s</td>' % ('b' if cls == 'b' else '', _e(name)))
        for n, y in enumerate(years):
            a('<td>%s</td>' % cell(None, why=HUMAN))
            if n:
                a('<td class="d"></td>')
        a('</tr>')
    a('</table>')

    a('<h2>Overhead<span class="src2">TAX RETURNS VS. PRACTICE FINANCIALS</span></h2>')
    a('<table class="an"><tr><th>BASIS</th>%s<th>3-YR MOVE</th><th>TARGET</th></tr>'
      % ''.join('<th>%s</th>' % y for y in years))
    a('<tr><td>Tax returns (1120-S)</td>')
    for y in years:
        a('<td>%s</td>' % cell(None, why=HUMAN))
    a('<td></td><td>&le;60%</td></tr>')
    a('<tr><td>Practice financials (P&amp;L)</td>')
    for y in years:
        p = by_year.get(y)
        a('<td>%s</td>' % (('%.1f%%' % p['overhead_pct']) if p else cell(None)))
    if len(years) > 1 and by_year.get(years[0]) and by_year.get(years[-1]):
        a('<td class="mv">%+.1fpt</td>'
          % (by_year[years[-1]]['overhead_pct'] - by_year[years[0]]['overhead_pct']))
    else:
        a('<td></td>')
    a('<td>&le;60%</td></tr>')
    a('<tr class="b"><td>Basis difference</td>')
    for y in years:
        a('<td>%s</td>' % cell(None, why=HUMAN))
    a('<td></td><td></td></tr>')
    a('</table>')
    a('<p class="note"><b>Reconciliation:</b> %s</p>' % cell(None, why=HUMAN))

    a('<div class="two">')
    a('<div><h3>Fee positioning</h3><p class="small">%s</p></div>'
      % cell(None, why=HUMAN))
    a('<div><h3>Risk flags</h3><p class="small">%s</p></div>'
      % cell(None, why=HUMAN))
    a('</div>')
    a('</div>')      # colR
    a('</div>')      # cols

    a('<div class="markup">ADVISOR NOTES / MEETING MARKUP<div class="ruled">'
      '<div></div><div></div><div></div></div></div>')
    a('<div class="ft"><span>FOUR QUADRANTS ADVISORY \u00b7 PROSPECT SUMMARY</span>'
      '<span>CONFIDENTIAL \u2014 INTERNAL USE ONLY</span><span>PAGE 1 OF 2</span></div>')
    a('</div>')

    # ---------------------------------------------------------------- page 2
    a('<div class="pg">')
    a('<div class="hd2"><h2 class="p2">Debt, cashflow &amp; assets</h2>'
      '<div class="meta">%s</div></div>' % _e(client))
    a('<h2>Debt schedule</h2>')
    a('<table class="an"><tr><th>OBLIGATION</th><th>TYPE</th><th>ORIGINAL</th>'
      '<th>BALANCE</th><th>RATE</th><th>PAYMENT</th><th>MATURITY</th></tr>')
    for side in ('PRACTICE', 'PERSONAL'):
        a('<tr><td colspan="7" class="side">%s</td></tr>' % side)
        a('<tr><td colspan="7">%s</td></tr>'
          % cell(None, why=(HUMAN if side == 'PRACTICE' else GAP)))
    a('</table>')
    a('<p class="note">The practice debt schedule is in the folder but is a '
      'spreadsheet of free text, so the rows need reading by a person. The '
      'personal half has not been sent.</p>')

    a('<h2>Cashflow analysis<span class="src2">MONTHLY SURPLUS / (DEFICIT) BY ACCOUNT</span></h2>')
    a('<p class="small">%s \u2014 needs the personal and HSA statements.</p>' % cell(None))
    a('<h2>Assets observed</h2>')
    a('<p class="small">%s \u2014 needs the remaining investment statements.</p>' % cell(None))
    a('<div class="two">')
    a('<div><h3>Entities &amp; ownership</h3><p class="small">%s</p></div>' % cell(None, why=HUMAN))
    a('<div><h3>Insurance &amp; retirement</h3><p class="small">%s</p></div>' % cell(None, why=HUMAN))
    a('</div>')
    a('<div class="markup">ADVISOR NOTES / MEETING MARKUP<div class="ruled">'
      '<div></div><div></div><div></div><div></div></div></div>')
    a('<div class="ft"><span>FOUR QUADRANTS ADVISORY \u00b7 PROSPECT SUMMARY</span>'
      '<span>CONFIDENTIAL \u2014 INTERNAL USE ONLY</span><span>PAGE 2 OF 2</span></div>')
    a('</div>')
    return '\n'.join(L)


CSS = """
body{background:#F3F1EC;margin:0;padding:26px;
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#1B2A41}
.pg{max-width:900px;margin:0 auto;background:#fff;padding:30px 34px 24px;
  box-shadow:0 1px 3px rgba(0,0,0,.12)}
.hd{display:flex;justify-content:space-between;align-items:flex-start;
  border-bottom:2px solid #16324F;padding-bottom:12px}
.kick{font-size:10px;letter-spacing:1.3px;color:#F08418;font-weight:600}
h1{margin:4px 0 0;font-size:26px;color:#16324F}
.meta{font-size:10px;letter-spacing:1px;color:#8A9099;text-align:right}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0 4px}
.kpi{border:1px solid #E4E0D8;border-radius:6px;padding:9px 11px}
.kl{font-size:9.5px;letter-spacing:.9px;color:#8A9099}
.kv{font-size:19px;font-weight:600;color:#16324F;margin-top:2px}
h2{font-size:12px;letter-spacing:1.1px;text-transform:uppercase;color:#16324F;
  border-left:3px solid #F08418;padding-left:8px;margin:22px 0 8px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:right;font-size:10px;letter-spacing:.6px;color:#8A9099;
  border-bottom:1px solid #E4E0D8;padding:5px 7px}
th:first-child{text-align:left}
td{padding:5px 7px;border-bottom:1px solid #F2EFE9;text-align:right}
td:first-child{text-align:left}
table.todo td{text-align:left}
.gap{font-size:10px;letter-spacing:.6px;color:#8A9099;background:#F2F0EB;
  border-radius:4px;padding:1px 6px;white-space:nowrap}
.human{font-size:10px;letter-spacing:.6px;color:#8A5A12;background:#FDF3E4;
  border-radius:4px;padding:1px 6px;white-space:nowrap}
.src{font-size:9.5px;color:#8A9099;margin-left:6px}
.why{font-size:11.5px;color:#6C7480}
.note{font-size:11.5px;color:#6C7480;margin:6px 0 0}
.ft{margin-top:20px;border-top:1px solid #E4E0D8;padding-top:8px;
  font-size:9.5px;letter-spacing:.8px;color:#8A9099}
"""


def main():
    ap = argparse.ArgumentParser(description="Render the Prospect Summary")
    ap.add_argument('folder')
    ap.add_argument('--client', default=None)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    html = build(args.folder, args.client)
    out = args.out or os.path.join(args.folder, '_Audit', 'Prospect Summary.html')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w') as fh:
        fh.write(html)
    print(out)


if __name__ == '__main__':
    main()
