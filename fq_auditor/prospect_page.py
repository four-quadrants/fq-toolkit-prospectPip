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
import intake_form as _ic
import production as _prod                                     # noqa: E402

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

PROD_SRC = '<span class="src">Practice Analysis</span>'

# The template's metric names against the figures the Practice Analysis
# actually prints. Only rows the report can answer are mapped; the rest stay
# NEEDS A HUMAN rather than being derived from something that nearly means the
# same thing. "Gross production" is charges before adjustments; "Net" is after.
PROD_MAP = {
    'Gross production': lambda v: v.get('charges_uninsured', 0)
                                 + v.get('charges_insured', 0)
    if {'charges_uninsured', 'charges_insured'} <= set(v) else None,
    'Production adjustments': lambda v: v.get('adjustments_add'),
    'Net production': lambda v: v.get('total_charges'),
    'Gross collections': lambda v: abs(v['patient_payments'])
    + v.get('insurance_payments', 0)
    if 'patient_payments' in v and 'insurance_payments' in v else None,
    'Collection adjustments': lambda v: v.get('adjustments_less'),
    'Net collections': lambda v: v.get('total_credits'),
}


def production_rows(folder):
    """{year: {metric: value}} from the scanned reports, agreed figures only."""
    rows = {}
    try:
        got = _prod.gather(folder)
    except Exception:
        return rows
    for year, rec in got.items():
        vals = rec.get('values') or {}
        chk = rec.get('check')
        if chk and not chk['agrees']:
            continue          # the report does not add up; report nothing
        rows[year] = {name: fn(vals) for name, fn in PROD_MAP.items()
                      if fn(vals) is not None}
    return rows


def notes_from_form(f):
    """The Initial Notes sentences, written from the client's own answers.

    Each line is composed only from fields the form actually carries. A note
    with nothing behind it comes back None and prints as a gap, so the page
    never pads itself out with a sentence that says nothing.
    """
    def g(*keys):
        return [f[k] for k in keys if f.get(k)]

    def money(k):
        v = _ic.money(f.get(k))
        return '${:,.0f}'.format(v) if v is not None else None

    practice, personal = [], []

    own = []
    if f.get('ownership'):
        own.append(f['ownership'].lower())
    if f.get('years_owned'):
        own.append('%s years' % f['years_owned'])
    if f.get('building'):
        b = 'owns the building' if f['building'].lower().startswith('own') else 'rents'
        if f.get('building_sqft'):
            b += ', %s sq ft' % '{:,}'.format(int(_ic.money('building_sqft') or 0)) \
                 if False else ', %s sq ft' % f['building_sqft']
        if money('building_payment'):
            b += ' at %s/mo' % money('building_payment')
        own.append(b)
    practice.append(('Ownership', ', '.join(own) or None))

    growth = []
    if money('collections_last'):
        growth.append('%s collected last year' % money('collections_last'))
    if money('collections_proj'):
        growth.append('%s projected this year' % money('collections_proj'))
        a, b = _ic.money(f.get('collections_last')), _ic.money(f.get('collections_proj'))
        if a and b:
            growth.append('%+.0f%% on the client\u2019s own forecast' % (100.0 * (b - a) / a))
    practice.append(('Growth', ', '.join(growth) or None))

    team = []
    if f.get('chairs_total'):
        team.append('%s chairs (%s operative, %s hygiene, %s overflow)'
                    % (f['chairs_total'], f.get('chairs_operative', '?'),
                       f.get('chairs_hygiene', '?'), f.get('chairs_overflow', '?')))
    if f.get('has_associates'):
        t = 'associates: %s' % f['has_associates'].lower()
        if f.get('associate_comp'):
            t += ' \u2014 %s' % f['associate_comp']
        team.append(t)
    practice.append(('Team', '; '.join(team) or None))

    prod = []
    for label, key in (('doctor days/wk', 'doctor_days'),
                       ('hygiene days/wk', 'hygiene_days'),
                       ('new patients/mo', 'new_patients_mo')):
        if f.get(key):
            prod.append('%s %s' % (f[key], label))
    if f.get('new_patient_wait'):
        prod.append('next new-patient opening %s' % f['new_patient_wait'])
    practice.append(('Productivity', ', '.join(prod) or None))

    payer = []
    if f.get('in_network'):
        payer.append('in-network: %s' % f['in_network'].lower())
    if f.get('pms'):
        payer.append('runs %s' % f['pms'])
    practice.append(('Payer mix', ', '.join(payer) or None))

    practice.append(('Costs',
                     ('client states overhead at %s' % f['overhead_stated'])
                     if f.get('overhead_stated') else None))
    practice.append(('Transition', None))

    hh = []
    for k, lab in (('age', 'age %s'), ('marital_status', '%s'),
                   ('dependents', '%s dependents')):
        if f.get(k):
            hh.append(lab % f[k])
    personal.append(('Household', ', '.join(hh) or None))
    personal.append(('Spending', None))

    ret = []
    if f.get('retire_age'):
        ret.append('target age %s' % f['retire_age'])
    if f.get('retire_target'):
        ret.append('believes %s is needed' % f['retire_target'])
    if f.get('retire_basis'):
        ret.append('basis: %s' % f['retire_basis'].lower())
    if f.get('saved_last_year'):
        ret.append('saved last year: %s' % f['saved_last_year'].lower())
    personal.append(('Retirement', ', '.join(ret) or None))

    personal.append(('Liquidity',
                     ('liquid at retirement today: %s' % f['saved_liquid'])
                     if f.get('saved_liquid') else None))
    personal.append(('Protection', None))
    struct = []
    if money('take_home'):
        struct.append('take-home %s' % money('take_home'))
    if f.get('cpa_rating'):
        struct.append('rates the CPA \u201c%s\u201d' % f['cpa_rating'].lower())
    if f.get('tax_surprise'):
        struct.append('tax surprise: %s' % f['tax_surprise'][:120])
    personal.append(('Structure', '; '.join(struct) or None))
    personal.append(('Stated goal', None))
    return practice, personal


PRACTICE_NOTES = ['Ownership', 'Growth', 'Team', 'Productivity', 'Payer mix',
                  'Costs', 'Transition']
PERSONAL_NOTES = ['Household', 'Spending', 'Retirement', 'Liquidity',
                  'Protection', 'Structure', 'Stated goal']


def build(folder, client=None):
    client = client or os.path.basename(folder.rstrip('/'))
    form = {}
    src = _ic.find_form(folder) or _ic.find_form(os.path.dirname(folder.rstrip('/')))
    if src:
        form = _ic.parse(src)
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
    bits = [x for x in (form.get('pms') and 'Dentrix' or None,
                        form.get('ownership'),
                        form.get('years_owned') and '%s years' % form['years_owned'],
                        form.get('age') and 'Age %s' % form['age'],
                        form.get('marital_status'),
                        form.get('dependents') is not None and
                        '%s dependents' % form.get('dependents')) if x]
    a('<div class="sub">%s</div>'
      % (' \u00b7 '.join(_e(b) for b in bits) if bits else cell(None, why=HUMAN)))
    a('</div><div class="meta">PREPARED %s<br>ADVISOR %s<br>ANALYST %s<br>'
      '<span class="stage">STAGE &nbsp;DATA RECEIVED</span></div></div>'
      % (datetime.date.today().strftime('%d.%m.%Y'), cell(None, why=HUMAN),
         cell(None, why=HUMAN)))

    prod_rows = production_rows(folder)
    latest = by_year.get(years[-1]) if years else None
    # The headline is the newest P&L that covers a whole year. The newest sheet
    # of all may be a single month — Oyler's July 2026 — and a month's income
    # under a yearly label is a wrong number that reads like an ordinary one.
    full = [y for y in years if (by_year[y].get('months') or 0) >= 12]
    head_year = full[-1] if full else (years[-1] if years else None)
    headline = by_year.get(head_year) if head_year else None
    n = (headline or {}).get('months') or 0
    inc_label = "NET COLLECTIONS '%s" % (head_year[-2:] if head_year else '--')
    inc_src = 'P&L'
    if headline and n and n < 12:
        inc_label = "COLLECTIONS, %d MONTH%s '%s" % (n, '' if n == 1 else 'S',
                                                     head_year[-2:])
        inc_src = 'P&L, part year'
    latest = headline or latest
    a('<div class="kpis">')
    for label, val, src, why in (
        (inc_label,
         ('$' + money(latest['income'])) if latest else None,
         inc_src if latest else None, None),
        ('OVERHEAD', ('%.1f%%' % latest['overhead_pct']) if latest else None,
         'P&L' if latest else None, None),
        ('OWNER COMP',
         ('$' + money(_ic.money(form.get('take_home')))) if form.get('take_home') else None,
         'IC form' if form.get('take_home') else None, HUMAN),
        ('TOTAL DEBT', None, None, None),
        ('OBSERVED ASSETS', None, None, None)):
        a('<div class="kpi"><div class="kl">%s</div><div class="kv">%s</div></div>'
          % (label, cell(val, src, why)))
    a('</div>')

    a('<div class="cols">')

    # ---- left: initial notes --------------------------------------------
    a('<div class="colL">')
    a('<h2>Initial notes</h2>')
    prac_notes, pers_notes = notes_from_form(form)
    for head, items in (('PRACTICE', prac_notes), ('PERSONAL', pers_notes)):
        a('<div class="tag %s">%s</div><ul class="notes">'
          % ('tp' if head == 'PRACTICE' else 'tn', head))
        for name, body in items:
            a('<li><b>%s</b> \u2014 %s</li>'
              % (_e(name), _e(body) if body else cell(None, why=HUMAN)))
        a('</ul>')
    a('</div>')

    # ---- right: the numbers ---------------------------------------------
    a('<div class="colR">')
    a('<h2>Practice analysis<span class="src2">SOURCE: PMS + PRACTICE FINANCIALS</span></h2>')
    a('<table class="an"><tr><th>METRIC</th>')
    # A part-year column says so in its heading. Without it the year-to-date
    # column sat beside two full years and its change column read -42%, which
    # is the arithmetic of a half-finished year, not a falling practice.
    partial = {y for y in years
               if 0 < (by_year.get(y, {}).get('months') or 12) < 12}
    for n, y in enumerate(years):
        a('<th>%s%s</th>' % (y, ' YTD' if y in partial else ''))
        if n:
            a('<th class="d">\u0394</th>')
    a('</tr>')
    for name, cls in ANALYSIS_ROWS:
        a('<tr class="%s"><td>%s</td>' % ('b' if cls == 'b' else '', _e(name)))
        prev = None
        for n, y in enumerate(years):
            v = prod_rows.get(y, {}).get(name)
            a('<td>%s</td>' % (('$' + money(v)) + PROD_SRC if v is not None
                               else cell(None, why=HUMAN)))
            if n:
                # The change column only where both years were actually read.
                d = ''
                if v is not None and prev and y not in partial \
                        and years[n - 1] not in partial:
                    d = '%+.0f%%' % (100.0 * (v - prev) / abs(prev))
                a('<td class="d">%s</td>' % d)
            prev = v
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
    a('<tr><td>Client\u2019s own estimate</td>')
    for y in years:
        a('<td>%s</td>' % (cell(form['overhead_stated'], 'IC form')
                           if (form.get('overhead_stated') and y == years[-1])
                           else '<span class="gap">\u2014</span>'))
    a('<td></td><td></td></tr>')
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
