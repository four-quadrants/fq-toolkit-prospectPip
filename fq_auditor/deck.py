#!/usr/bin/env python3
"""The consultation deck's content: every slide, every number, and its source.

    python3 deck.py "<client folder>" --client "Dr. Brian Oyler"     # print it

Rendered by deck_pptx.py. Laid out from `_spec/cashflow/DECK.md` and from the
firm's own consult decks for Rebol, Spaulding, Kinsler and Bassett: every slide
is an eyebrow, a headline, one hero figure with a line under it, a body, and a
presenter note. The note carries where each figure came from, so whoever
presents can answer "where's that from" without leaving the slide.

WHERE THE NUMBERS COME FROM
    documents    the facts bundle, the cash flow build, the Assumptions store
    models       savings.py (both retirement paths), levers.py (opportunities)
    the advisor  the 'deck' entry in _Audit/plan_inputs.json, four decisions
                 that are the advisor's and always will be:
                   target_income      retirement income, today's dollars
                   savings_schedule   [[year, amount], ...] brokerage steps
                   sale_net           practice and building sale, net
                   tax_split          {"withholding": .., "estimates": ..}
                 plus what the documents cannot know yet: retire_age if the
                 IC form is missing, current_savings, target_overhead,
                 concerns, income structure, fees.

A slide whose input is missing prints what is missing, in amber, on the slide.
Nothing is filled in from another client and nothing is guessed.
"""
import os
import glob
import re
import sys
import json
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import facts as _facts                                       # noqa: E402
import inputs as _inputs                                     # noqa: E402
import savings as _sav                                       # noqa: E402
import levers as _lev                                        # noqa: E402

try:
    import cashflow as _cash                                 # noqa: E402
except Exception:                                            # pragma: no cover
    _cash = None

PRACTICE_MULTIPLE = 0.65     # assumptions.FIRM['practice_value_multiple']
PRACTICE_GROWTH_CURRENT = 0.03
PRACTICE_GROWTH_FQ = 0.04
BUILDING_GROWTH = 0.02
SALE_NET_SHARE = 0.70        # net after taxes, on every deck read: Rebol
                             # 4.481 to 3.136, Spaulding 1.340 to 0.937,
                             # Kinsler 2.195 to 1.536, Bassett 1.239 to 0.867
BANKISH = re.compile(r'checking|savings|money market|\bcd\b', re.I)


def _m(v, k=False):
    if v is None:
        return None
    sign = '-' if v < 0 else ''
    a = abs(v)
    if k and a >= 1e6:
        return '%s$%.2fm' % (sign, a / 1e6)
    if k and a >= 1e4:
        return '%s$%.1fk' % (sign, a / 1e3)
    return '%s${:,.0f}'.format(a) % sign


def _num(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r'-?[\d,]+(?:\.\d+)?', str(s).replace('$', ''))
    return float(m.group(0).replace(',', '')) if m else None


def retire_age_of(v):
    """The retirement age in the IC form's answer: a number, or the last
    and largest age named in a sentence ("down to 3 days a week by 55 and
    able to walk away by 65" is 65, not 3)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    ages = [float(x) for x in re.findall(r'\b([4-8]\d)\b', str(v))]
    return max(ages) if ages else None


class Slide(object):
    def __init__(self, key, eyebrow, headline, hero=None, sub=None,
                 body=None, table=None, note='', needs=None, kind='content'):
        self.key, self.eyebrow, self.headline = key, eyebrow, headline
        self.hero, self.sub = hero, sub
        self.body = body or []           # bullet lines
        self.table = table               # {'head': [...], 'rows': [[...]]}
        self.note = note
        self.needs = needs or []         # what the advisor still has to supply
        self.kind = kind

    def as_dict(self):
        return dict(self.__dict__)


def _advisor(folder):
    got = _inputs.get(folder, 'deck') or {}
    return got.get('value') or {}


def _start_portfolio(folder):
    """Today's investable portfolio: the qualified accounts, plus non-qualified
    holdings that are investments rather than bank balances.

    Oyler: Vestwell 401k $69,120 + Provident IRA $628,000 + Reef $408,526,
    which is the lead advisor’s `(69120+628000+408525)` to within the dollar he rounded.
    Bank cash is left out, as on every firm deck read ("Current portfolio
    value $289,545 (excl. HSA)").
    """
    try:
        import accounts as _accounts
        _accounts.ensure(folder, log=lambda *_a: None)
    except Exception:                                        # noqa: BLE001
        pass
    parts, total = [], 0.0
    for key in ('qualified_accounts', 'nonqualified_accounts'):
        for r in (_inputs.value(folder, key) or []):
            label = r.get('label') or ''
            amt = _num(r.get('amount') or r.get('value'))
            if not amt or r.get('excluded') or BANKISH.search(label) or \
                    re.search(r'\bhsa\b|529', label, re.I):
                continue
            parts.append((label, amt))
            total += amt
    return (total or None), parts


def annual_pi(folder):
    """{year: {gross, adjustments, net, income}} from Dentrix "Annual P&I"
    exports (one CSV a year, a row a month: Production, Adjustments,
    Write-off, Tot Prod, ... Total Income). Doctor-only and year-to-date
    files are left out; a year with fewer than 12 months is marked partial."""
    import csv
    out = {}
    for path in glob.glob(os.path.join(folder, '**', '*P&I*.csv'), recursive=True):
        name = os.path.basename(path).lower()
        if 'doctor' in name or '/.' in path:
            continue
        try:
            # Dentrix leads with a blank line before the header
            lines = [ln for ln in open(path, errors='replace').read().splitlines()
                     if ln.strip()]
            rows = list(csv.DictReader(lines))
        except (OSError, csv.Error):
            continue
        by = {}
        for r in rows:
            m = re.match(r'\s*[A-Za-z]{3}\s+(\d{4})', r.get('Month') or '')
            if not m:
                continue
            y = m.group(1)
            t = by.setdefault(y, {'gross': 0.0, 'adjustments': 0.0, 'net': 0.0,
                                  'income': 0.0, 'months': 0})
            t['gross'] += _num(r.get('Production')) or 0
            t['adjustments'] += -((_num(r.get('Adjustments')) or 0) +
                                  (_num(r.get('Write-off')) or 0))
            t['net'] += _num(r.get('Tot Prod')) or 0
            t['income'] += _num(r.get('Total Income')) or 0
            t['months'] += 1
        for y, t in by.items():
            t['partial'] = t['months'] < 12
            if y not in out or (out[y]['partial'] and not t['partial']):
                out[y] = t
    return out


def _production_inputs(folder):
    """Adjustment %, net production and collection % from the newest full
    year of the Practice Analysis, where the practice sent one.

        adjustments   adjustments less, net of adjustments add
        net           total charges less adjustments
        collections   patient plus insurance payments, over net
    """
    try:
        import production as _prod
        got = _prod.gather(folder)
    except Exception:                                        # noqa: BLE001
        got = {}
    if not got:
        pi = annual_pi(folder)
        # The current year once it has six months in it, annualised: the
        # lead advisor's Spaulding deck used 2026 to June (adjustments 40.5%,
        # collections 91.3%, on the year annualised), not 2025, whose
        # collections read 103% against production.
        for year in sorted(pi, reverse=True):
            t = pi[year]
            m = t.get('months') or 0
            if t['partial'] and m >= 6 and t['gross'] and t['net']:
                k = 12.0 / m
                return {'gross_production': t['gross'] * k,
                        'adjust_pct': t['adjustments'] / t['gross'],
                        'net_production': t['net'] * k,
                        'collection_pct': t['income'] / t['net'],
                        'production_year': '%s, %d months annualised' % (year, m)}
            break
        for year in sorted(pi, reverse=True):
            t = pi[year]
            if t['partial'] or not t['gross']:
                continue
            return {'gross_production': t['gross'],
                    'adjust_pct': t['adjustments'] / t['gross'],
                    'net_production': t['net'],
                    'collection_pct': t['income'] / t['net'] if t['net'] else None,
                    'production_year': year}
        return {}
    for year in sorted(got, reverse=True):
        r = got[year]
        if 'ytd' in (r.get('source') or '').lower():
            continue
        v = r['values']
        gross = v.get('total_charges')
        if not gross:
            continue
        adj = (v.get('adjustments_less') or 0) - (v.get('adjustments_add') or 0)
        net = gross - adj
        paid = abs(v.get('patient_payments') or 0) + \
            abs(v.get('insurance_payments') or 0)
        return {'gross_production': gross, 'adjust_pct': adj / gross,
                'net_production': net,
                'collection_pct': (paid / net) if net and paid else None,
                'production_year': year}
    return {}


def gather(folder, client=None, today=None):
    today = today or datetime.date.today()
    b = _facts.gather(folder, client)
    f = {x.label: x.value for x in b.all_facts()}
    adv = _advisor(folder)
    first = b.forename or 'the client'
    slides = []

    # ---- shared figures -------------------------------------------------
    cash = None
    if _cash:
        try:
            cash = _cash.for_assumptions(folder)
        except Exception:                                    # noqa: BLE001
            cash = None
    spend_m = cash['monthly_including'] if cash and cash['accounts'] else None
    personal_read = cash and any(a['entity'] == 'Personal' and a['readable']
                                 for a in cash['accounts'])
    if not personal_read:
        spend_m = None
    start, start_parts = _start_portfolio(folder)
    start = _num(adv.get('start_portfolio')) or start

    age = _num(f.get('Age')) or _num(adv.get('age'))
    retire_age = _num(adv.get('retire_age')) or retire_age_of(f.get('Retirement age goal'))
    revenue = _num(f.get('Income base (overhead denominator)'))
    building = _num(adv.get('building_value'))
    years_to = (retire_age - age) if (age and retire_age) else None

    def sale(growth, key='sale_net'):
        if adv.get(key) is not None:
            return _num(adv[key]), None
        if key != 'sale_net' and adv.get('sale_net') is not None:
            return _num(adv['sale_net']), None
        if not (revenue and years_to):
            return None, None
        gross = revenue * PRACTICE_MULTIPLE * (1 + growth) ** years_to
        if building:
            gross += building * (1 + BUILDING_GROWTH) ** years_to
        return gross * SALE_NET_SHARE, gross

    sale_cur, gross_cur = sale(PRACTICE_GROWTH_CURRENT)
    sale_fq, gross_fq = sale(PRACTICE_GROWTH_FQ, 'sale_net_fq')
    # The advisor can overrule the measured spending, and the deck says so in
    # the note. Rebol's deck ran on $383,088 a year where his own
    # Assumptions published $198,058.
    if adv.get('current_expenses'):
        spend_m = _num(adv['current_expenses']) / 12.0

    proj = None
    need_proj = [n for n, v in (
        ('client age (IC form)', age), ('retirement age (IC form)', retire_age),
        ('investable accounts (Assumptions 4 and 5)', start),
        ('current annual savings', _num(adv.get('current_savings'))),
        ('personal spending (cash flow)', spend_m)) if not v]
    sched = adv.get('savings_schedule')
    income = _num(adv.get('target_income'))
    if not need_proj:
        consult = adv.get('consult_date') or today.isoformat()
        proj = _sav.project(
            start=start, consult_date=consult, age_now=int(age),
            retire_age=int(retire_age),
            current_savings=_num(adv['current_savings']),
            current_expenses=spend_m * 12,
            fq_schedule=[tuple(x) for x in sched] if sched else
            [(int(consult[:4]), _num(adv['current_savings']))],
            fq_income=income or spend_m * 12,
            sale_net=sale_cur or 0,
            # 90 by firm standard; Spaulding's sheet ran to 94.
            horizon_age=int(_num(adv.get('horizon_age')) or _sav.HORIZON_AGE),
            # 8.5% unless the advisor says otherwise; consults before
            # August used 9% (Rebol, Bassett, Desai).
            r1=_num(adv.get('fq_first_year_rate')))
        if sale_fq and sale_fq != sale_cur:
            fqd = dict(proj['fq_deposits'])
            fqd[proj['retire_year']] += (sale_fq - (sale_cur or 0))
            proj['fq'] = _sav.fq_path(start, proj['f'], fqd,
                                      proj['retire_year'],
                                      income or spend_m * 12,
                                      proj['first_year'], proj['end_year'],
                                      r1=_num(adv.get('fq_first_year_rate'))
                                      or _sav.FIRST_YEAR_FQ_RETURN)
            proj['fq_deposits'] = fqd
            proj['fq_at_retirement'] = proj['fq'][proj['retire_year']]

    # ---- 1 title ----------------------------------------------------------
    names = adv.get('names') or (client or b.client)
    slides.append(Slide('title', 'CONSULTATION', names,
                        sub=adv.get('consult_date_text')
                        or today.strftime('%B %-d, %Y'),
                        kind='title',
                        note='Four Quadrants. The Multimillion Dollar Secret '
                             'for Dentists.'))

    # ---- 2 the difference -------------------------------------------------
    if proj and income and sched:
        cur_w, fq_w = proj['current_at_retirement'], proj['fq_at_retirement']
        slides.append(Slide(
            'difference', 'THE FOUR QUADRANTS DIFFERENCE',
            'Retirement wealth of %s vs. %s' % (_m(fq_w, True), _m(cur_w, True)),
            hero=_m(fq_w, True),
            sub='at retirement in %d, against %s on the current path'
                % (proj['retire_year'], _m(cur_w, True)),
            body=['Retirement income of %s a year, %s retiring at %d'
                  % (_m(income), first, int(retire_age)),
                  'Saving %s a year by year 2, against %s now'
                  % (_m(_num(sched[min(1, len(sched) - 1)][1])),
                     _m(_num(adv.get('current_savings')))),
                  'Current path: funds run out %s'
                  % ('in %d' % proj['runout_year'] if proj['runout_year']
                     else 'not before %d' % proj['end_year'])],
            note='Both figures from savings.py: the current path at 8.5% with '
                 'today\'s savings, the Four Quadrants path at 9% on the '
                 'advisor\'s schedule. Same start, same expenses, same sale.'))
    else:
        slides.append(Slide('difference', 'THE FOUR QUADRANTS DIFFERENCE',
                            'The Four Quadrants difference',
                            needs=need_proj + [n for n, v in (
                                ('target retirement income', income),
                                ('savings schedule', sched)) if not v],
                            note='Filled from the two retirement paths once '
                                 'their inputs are in.'))

    # ---- 3 concerns -------------------------------------------------------
    concerns = adv.get('concerns') or []
    slides.append(Slide(
        'concerns', 'BIGGEST CONCERNS',
        '%s’s biggest concerns' % (b.surname or first),
        body=concerns,
        needs=[] if concerns else ['the client’s concerns, from the '
                                   'IC form and the consult offer call'],
        note='In the client’s own order where the IC form gives one.'))

    # ---- 4 results (boilerplate) ------------------------------------------
    slides.append(Slide(
        'results', 'FOUR QUADRANTS RESULTS',
        'Clients in the traditional program, on average, in 3 years',
        hero='+25%', sub='net income',
        body=['Increase their net income by over 25%',
              'Lower their overhead by nearly 11%',
              'Increase retirement savings',
              'Become a top 1% DDS'],
        note='Firm standard slide.', kind='boilerplate'))

    # ---- 5 practice opportunities ----------------------------------------
    oh = _num(f.get('Overhead, P&L basis')) or _num(f.get('Overhead, tax basis'))
    target_oh = _num(adv.get('target_overhead'))
    lx = {'overhead': oh, 'net_collections': revenue,
          'target_overhead': target_oh}
    lx.update(_production_inputs(folder))
    lx.update({k: v for k, v in (adv.get('levers') or {}).items()})
    lv = _lev.ranked(_lev.compute(lx))
    rows = [[label, _m(v)] for _k, label, v, _basis in lv['rows']]
    slides.append(Slide(
        'opportunities', 'PRACTICE OPPORTUNITIES',
        'Extra income to %s' % first,
        hero=_m(lv['top_subtotal'], True) if lv['rows'] else None,
        sub=('top %d levers; %s at worst-case attrition'
             % (min(5, len(lv['rows'])), _m(lv['worst_case'], True)))
            if lv['rows'] else None,
        table={'head': ['Lever', 'To the owner'], 'rows': rows},
        body=[lv['caveat']] if rows else [],
        needs=['%s: needs %s' % (_lev.LABELS[k], ', '.join(n))
               for k, n in lv['waiting']],
        note='levers.py, the analyst\'s model, at a %.0f%% goal overhead. Current '
             'overhead %s on the P&L. Revenue %s.'
             % (100 * (target_oh or _lev.TARGET_OH),
                ('%.1f%%' % (100 * oh)) if oh else 'not read',
                _m(revenue) or 'not read')))

    # ---- 6 debt -----------------------------------------------------------
    pd_total = _num(f.get('Practice total'))
    pd_service = _num(f.get('Practice debt service'))
    slides.append(Slide(
        'debt', 'CORPORATE DEBT STRUCTURING',
        'Practice debt of %s' % _m(pd_total) if pd_total else
        'Practice debt',
        hero=_m(pd_service) + '/mo' if pd_service else None,
        sub=('a month across the practice’s loans. %s'
             % (f.get('Practice debt') or '')) if pd_total else None,
        needs=[] if pd_total else ['practice loan statements'],
        note='From the debt schedule read off the loan statements.'))

    # ---- 7 income structure -----------------------------------------------
    inc = adv.get('income_structure') or {}
    if inc:
        cur_def, new_def = _num(inc.get('deferrals_current')), \
            _num(inc.get('deferrals_proposed'))
        diff = (new_def - cur_def) if None not in (cur_def, new_def) else None
        slides.append(Slide(
            'income', 'NEW INCOME / SAVINGS',
            'A pay structure that saves more',
            hero=('%s/yr more' % _m(diff, True)) if diff else None,
            sub=('saved into plans, and over %s a year of tax'
                 % _m(diff * 0.3, True)) if diff else None,
            table={'head': ['', 'Amount'], 'rows': [
                ['Proposed W-2', _m(_num(inc.get('w2')))],
                ['Proposed distributions', _m(_num(inc.get('distributions')))],
                ['Deferrals + match, current', _m(cur_def)],
                ['Deferrals + match, proposed', _m(new_def)]]},
            note='Tax saving at 30% of the added deferral, as the lead advisor\'s '
                 'worksheet computes it (=C210*0.3).'))
    else:
        slides.append(Slide('income', 'NEW INCOME / SAVINGS',
                            'A pay structure that saves more',
                            needs=['proposed W-2, distributions and '
                                   'deferrals (advisor)'],
                            note='Rows 200 to 212 of the savings worksheet.'))

    # ---- 8 cash flow ------------------------------------------------------
    if spend_m and cash and personal_read:
        rows = [[a['name'], _m(a['deposit']), _m(a['expense']),
                 _m(a['surplus'])] for a in cash['accounts']
                if a['entity'] == 'Personal' and a['readable']]
        slides.append(Slide(
            'cashflow', 'CASH FLOW MANAGEMENT',
            'Where the money goes each month',
            hero=_m(spend_m) + '/mo',
            sub=('personal spending including liabilities; %s without them'
                 % _m(cash['monthly_excluding'])) if not
                adv.get('current_expenses') else
                ('the advisor\u2019s figure. Measured from the statements: '
                 '%s including liabilities, %s without them'
                 % (_m(cash['monthly_including']),
                    _m(cash['monthly_excluding']))),
            table={'head': ['Account', 'Deposits', 'Expenses', 'Surplus'],
                   'rows': rows},
            note='The cash flow workbook, four statement periods per '
                 'account, transfers between his own accounts removed.'))
    else:
        slides.append(Slide('cashflow', 'CASH FLOW MANAGEMENT',
                            'Where the money goes each month',
                            needs=['personal bank statements'],
                            note='Built from the cash flow workbook.'))

    # ---- 9 tax and accounting 101 (boilerplate) ---------------------------
    slides.append(Slide(
        'tax101', '4Q TAX & ACCOUNTING 101',
        'Monthly dental accounting, not just a tax return',
        table={'head': ['Service', 'Basic', 'Standard', 'Four Quadrants'],
               'rows': [['Prepare and file annual tax returns', 'x', 'x', 'x'],
                        ['Quarterly tax estimates', '', 'x', 'x'],
                        ['Clouded QuickBooks, real-time accuracy', '', '', 'x'],
                        ['Customized dental chart of accounts', '', '', 'x'],
                        ['Monthly P&L and balance sheet review', '', '', 'x']]},
        note='Firm standard slide.', kind='boilerplate'))

    # ---- 10 tax review: withholding against estimates ---------------------
    tax = adv.get('tax_current') or {}
    split = adv.get('tax_split') or {}
    owed = _num(tax.get('total_tax'))
    wh, est = _num(tax.get('withholding')), _num(tax.get('estimates'))
    if None not in (owed, wh):
        cur_bal = (wh + (est or 0)) - owed
        rows = [['Withholding', _m(wh), _m(_num(split.get('withholding')))],
                ['Estimates', _m(est or 0), _m(_num(split.get('estimates')))],
                ['Total tax owed', _m(owed), _m(owed)],
                ['Refund / (balance due)', _m(cur_bal),
                 _m((_num(split.get('withholding')) or 0)
                    + (_num(split.get('estimates')) or 0) - owed)
                 if split else None]]
        slides.append(Slide(
            'tax', 'HIGH LEVEL TAX REVIEW',
            'The same tax bill, paid on time instead of in advance',
            hero=_m(cur_bal, True) + ' refund' if cur_bal > 0 else None,
            sub='an interest-free loan to the IRS each year'
                if cur_bal > 0 else None,
            table={'head': ['', 'Current', 'Proposed'], 'rows': rows},
            needs=[] if split else ['withholding against estimates split '
                                    '(advisor)'],
            note='Current from the 1040: line 24 total tax, 25d withholding, '
                 '26 estimates. Proposed is one decision about how to split '
                 'the same bill. Nobody models anything.'))
    else:
        slides.append(Slide('tax', 'HIGH LEVEL TAX REVIEW',
                            'The same tax bill, paid on time',
                            needs=['1040 lines 24, 25d and 26', 'withholding '
                                   'against estimates split (advisor)'],
                            note='Three figures off the personal return and '
                                 'one decision.'))

    # ---- 11 how we invest (boilerplate) -----------------------------------
    slides.append(Slide(
        'invest', 'INVESTMENTS', 'Four Quadrants investment philosophy',
        body=['Capital preservation', 'Primary focus is saving more with '
              'less risk', 'Secondary focus is returns', 'Four Quadrants to '
              'manage all investments'],
        note='Firm standard slide.', kind='boilerplate'))

    # ---- 12 investments current -------------------------------------------
    slides.append(Slide(
        'investments', 'INVESTMENTS – CURRENT',
        'What is saved today',
        hero=_m(start, True) if start else None,
        sub='investable, excluding bank cash' if start else None,
        table={'head': ['Account', 'Value'],
               'rows': [[l, _m(a)] for l, a in start_parts]}
        if start_parts else None,
        needs=[] if start else ['retirement and investment statements'],
        note='Sections 4 and 5 of the Assumptions.'))

    # ---- 13 current retirement strategy -----------------------------------
    if proj:
        c, ry, ey = proj['current'], proj['retire_year'], proj['end_year']
        y0 = proj['first_year']
        mid = proj['runout_year'] or (ry + ey) // 2
        pick = [y0, ry, mid, ey]
        rows = [[str(int(age) + (y - y0)), str(y),
                 _m(proj['current_deposits'].get(y, 0), True),
                 _m(c[y], True),
                 _m(spend_m * 12 * (1 + _sav.INFLATION) ** (y - y0), True)]
                for y in pick]
        ro = proj['years_before_runout']
        slides.append(Slide(
            'current_path', 'CURRENT RETIREMENT STRATEGY',
            ('Less than %d years before funds run out' % ro) if ro else
            'Funds last to age %d' % _sav.HORIZON_AGE,
            hero=_m(proj['on_pace_for']) + '/yr',
            sub='of retirement spending the current path supports (%.0f%% '
                'of today’s lifestyle)' % (100 * proj['on_pace_share']),
            table={'head': ['Age', 'Year', 'Invests', 'Portfolio (8.5%)',
                            'Expenses'], 'rows': rows},
            body=['Current portfolio %s, investing %s a year until retirement'
                  % (_m(start), _m(_num(adv['current_savings']))),
                  ('Assumes practice%s sale in %d (%s gross; %s net after '
                   'taxes)' % (' & building' if building else '', ry,
                               _m(gross_cur, True), _m(sale_cur, True)))
                  if gross_cur else
                  'Sale at retirement: %s net' % _m(sale_cur, True)],
            note='savings.py current path. First year grows for the part of '
                 'the year after the consult (%.2f).' % proj['f']))
    else:
        slides.append(Slide('current_path', 'CURRENT RETIREMENT STRATEGY',
                            'Where the current path leads', needs=need_proj,
                            note='savings.py current path.'))

    # ---- 14 annual savings projection -------------------------------------
    if sched:
        # The steps only: a row per change, not a row per year. The lead advisor’s
        # schedule for Rebol is fourteen years in six amounts.
        steps, last = [], None
        for y, a in sorted(sched):
            if _num(a) != last:
                steps.append((y, a))
                last = _num(a)
        rows = [[str(int(y)), _m(_num(a))] for y, a in steps]
        slides.append(Slide(
            'schedule', 'ANNUAL SAVINGS PROJECTION',
            'What gets saved, and where it comes from',
            hero=_m(_num(sched[0][1]), True), sub='invested in year 1',
            table={'head': ['From', 'Invested per year'], 'rows': rows},
            body=adv.get('schedule_sources') or [],
            note='The advisor\'s schedule; the sources under it are the '
                 'advisor\'s too.'))
    else:
        slides.append(Slide('schedule', 'ANNUAL SAVINGS PROJECTION',
                            'What gets saved, and where it comes from',
                            needs=['savings schedule (advisor)'],
                            note='Advisor decision.'))

    # ---- 15 FQ savings future ---------------------------------------------
    if proj and sched and income:
        q, ry, y0 = proj['fq'], proj['retire_year'], proj['first_year']
        # As his slide picks them: the first three years, each year the
        # amount steps, retirement, and the end. Never more than eight rows.
        changes, last = [], None
        for y, a in sorted(sched):
            if _num(a) != last:
                changes.append(int(y))
                last = _num(a)
        steps = sorted(set([y0, y0 + 1, y0 + 2] + changes))[:6]
        steps = sorted(set(steps + [ry, proj['end_year']]))
        rows = [[str(int(age) + (y - y0)), str(y),
                 _m(proj['fq_deposits'].get(y, 0), True), _m(q[y], True),
                 _m(income * (1 + _sav.INFLATION) ** (y - y0), True)]
                for y in steps if y in q]
        slides.append(Slide(
            'fq_path', 'YOUR FOUR QUADRANTS SAVINGS FUTURE',
            'Retirement income of %s a year' % _m(income),
            hero=_m(q[ry], True), sub='at retirement in %d' % ry,
            table={'head': ['Age', 'Year', 'Annual savings',
                            'Portfolio (9%)', 'Retirement expenses'],
                   'rows': rows},
            note='savings.py Four Quadrants path on the advisor\'s schedule.'))
    else:
        slides.append(Slide('fq_path', 'YOUR FOUR QUADRANTS SAVINGS FUTURE',
                            'Retirement on the Four Quadrants path',
                            needs=need_proj + [n for n, v in (
                                ('target retirement income', income),
                                ('savings schedule', sched)) if not v],
                            note='savings.py Four Quadrants path.'))

    # ---- 16 client process (boilerplate) ----------------------------------
    slides.append(Slide(
        'process', 'FOUR QUADRANTS CLIENT PROCESS', 'How the year runs',
        body=['Annual planning meeting', 'Pre-review',
              'Mid-year review', 'Monthly accounting and quarterly reports'],
        note='Firm standard slide.', kind='boilerplate'))

    # ---- 17 agreement -----------------------------------------------------
    fees = adv.get('fees') or []
    slides.append(Slide(
        'agreement', '2-YEAR AGREEMENT', 'The engagement',
        table={'head': ['', 'Year 1', 'Year 2'], 'rows': fees} if fees else None,
        needs=[] if fees else ['planning, tax and investment fees (advisor)'],
        note='Paid by the practice.'))

    # ---- 18 close ---------------------------------------------------------
    slides.append(Slide('close', 'FOUR QUADRANTS', names,
                        sub='The Multimillion Dollar Secret for Dentists',
                        kind='title'))
    return {'client': client or b.client, 'slides': slides,
            'projection': proj}


def main():
    ap = argparse.ArgumentParser(description='Consult deck content')
    ap.add_argument('folder')
    ap.add_argument('--client', default=None)
    a = ap.parse_args()
    d = gather(a.folder, a.client)
    for i, s in enumerate(d['slides'], 1):
        print('%2d  %-34s %s  %s' % (i, s.eyebrow[:34], s.hero or '',
                                     ('NEEDS: ' + '; '.join(s.needs))
                                     if s.needs else ''))


if __name__ == '__main__':
    main()
