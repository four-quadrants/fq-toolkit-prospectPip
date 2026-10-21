#!/usr/bin/env python3
"""The consultation deck, built from the firm's own redesigned deck.

    python3 deck_template.py "<client folder>" --client "Dr. Brian Oyler" \
            --out "Consult deck - Oyler.pptx"

WHY A TEMPLATE AND NOT A DRAWING
The first generator drew every slide from nothing on PowerPoint's blank
theme. The numbers were right, but in Keynote each slide opened as loose boxes
on a blank page, in fonts and colours nobody on the team could match, and the
sales team could not edit it without fighting it.

This one opens the firm's own deck, `assets/consult_template.pptx` (Keynote's
PowerPoint export of "Oyler Consultation-ah version", the format every consult
uses from October 2026), and changes only the words. Every shape, colour,
Barlow and Barlow Condensed run, position and slide stays exactly where the
designer put it, so the result edits in Keynote the same way the original does.

WHAT HAPPENS TO EACH PIECE OF TEXT
Every text shape on every slide gets one of four treatments, set in SPEC:
    keep      firm boilerplate, left alone (the 4Q results, the team, tax 101)
    name      boilerplate that names the client: Brian/Oyler swapped
    fill      a figure we compute, written in the shape's own formatting
    advisor   the advisor's own words or decisions: replaced with a visible
              [ADVISOR: ...] prompt in the same font, so nothing from Oyler's
              deck can survive into another client's and an unfinished slide
              is obvious
A shape the SPEC does not mention takes its slide's default. Presenter notes
are rewritten for every slide that carries client figures.

SLIDES THAT COME AND GO
Corporate debt (no practice loans), the tax example (no 1040 figures yet) and
the larger-practice-value scenario (none entered) are dropped when there is
nothing to put on them.
"""
import os
import re
import sys
import copy
import math
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pptx import Presentation                                # noqa: E402

import plan as _plan                                         # noqa: E402
import deck as _deck                                         # noqa: E402
import savings as _sav                                       # noqa: E402
import levers as _lev                                        # noqa: E402
import facts as _facts                                       # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'assets', 'consult_template.pptx')
# The template in git is the firm's deck with its client scrubbed out by
# _spec/build_template.py: names became these tokens. The source deck was
# Oyler's; build_template needs to know that to scrub it.
TEMPLATE_FIRST, TEMPLATE_SURNAME = '{FIRST}', '{SURNAME}'
TEMPLATE_FIRST_SOURCE, TEMPLATE_SURNAME_SOURCE = 'Brian', 'Oyler'

# The firm's 3-year averages, applied to the client on the results slide:
# +25% income, overhead x 0.891 (74.00% to 65.93%), savings x 6.67.
RESULT_INCOME, RESULT_OH, RESULT_SAVE = 1.25, 0.891, 6.67

M = _deck._m
N = _deck._num
WORDS = {1: 'ONE', 2: 'TWO', 3: 'THREE', 4: 'FOUR', 5: 'FIVE', 6: 'SIX',
         7: 'SEVEN', 8: 'EIGHT'}


def _k(v):
    """$148k, $47.5k, $1.1M as the redesign writes them."""
    if v is None:
        return None
    a = abs(v)
    s = '-' if v < 0 else ''
    if a >= 1e6:
        return '%s$%.1fM' % (s, a / 1e6)
    if a >= 1e5:
        # Truncated, as the redesign writes it: $148,800 is "$148k".
        return '%s$%dk' % (s, int(a / 1e3))
    return '%s$%.1fk' % (s, a / 1e3)


def _pct(v, d=1):
    return None if v is None else ('%.' + str(d) + 'f%%') % (100 * v)


def _signed(v):
    if v is None:
        return None
    return '%s%.0f%%' % ('+' if v >= 0 else '−', abs(100 * v))


# --------------------------------------------------------------------------
# The figures
# --------------------------------------------------------------------------

def figures(folder, client):
    """Everything the slides print, from the documents, the models and the
    advisor's entry. Missing values are None and the slide says so."""
    b = _facts.gather(folder, client)
    f = {x.label: x.value for x in b.all_facts()}
    adv = _deck._advisor(folder)
    D = {'adv': adv, 'facts': f, 'first': b.forename or 'the client',
         'surname': b.surname or ''}
    D['names'] = adv.get('names') or client or b.client
    D['date'] = adv.get('consult_date_text') or \
        datetime.date.today().strftime('%B %-d, %Y')

    cash = None
    if _deck._cash:
        try:
            cash = _deck._cash.for_assumptions(folder)
        except Exception:                                    # noqa: BLE001
            cash = None
    read = cash and any(a['entity'] == 'Personal' and a['readable']
                        for a in cash['accounts'])
    spend = (cash['monthly_including'] * 12) if read else None
    if adv.get('current_expenses'):
        spend = N(adv['current_expenses'])
    D['cash'] = cash if read else None
    D['spend'] = spend

    start, parts = _deck._start_portfolio(folder)
    D['start'] = N(adv.get('start_portfolio')) or start
    D['start_parts'] = parts
    D['age'] = N(f.get('Age')) or N(adv.get('age'))
    D['retire_age'] = N(adv.get('retire_age')) or N(f.get('Retirement age goal'))
    D['current_savings'] = N(adv.get('current_savings'))
    D['income'] = N(adv.get('target_income'))
    D['schedule'] = [tuple(x) for x in (adv.get('savings_schedule') or [])]
    D['take_home'] = N(adv.get('current_income')) or N(f.get('Take-home, stated'))
    D['overhead'] = N(f.get('Overhead, tax basis')) or \
        N(f.get('Overhead, P&L basis'))
    D['revenue'] = N(f.get('Income base (overhead denominator)'))
    D['overhead_dollars'] = N(f.get('Total expenses (overhead numerator)'))
    D['debt_total'] = N(f.get('Practice total'))
    D['debt_service'] = N(f.get('Practice debt service'))

    # ---- what the plan works out instead of asking for -------------------
    # (_spec/savings/WORKSHEET.md; the advisor's entry wins wherever given)
    other = N(f.get('Other income')) or 0
    D['collections'] = (D['revenue'] - other) if D['revenue'] else None
    D['owns_building'] = 'owns the building' in str(f.get('Office location')
                                                     or '').lower()
    D['building'] = N(adv.get('building_value')) if (
        D['owns_building'] or adv.get('building_value')) else None
    years_to = (D['retire_age'] - D['age']) if (D['age'] and
                                                 D['retire_age']) else None
    gross, net = _plan.sale(D['collections'], years_to, D['building'],
                            N(adv.get('debt_at_sale')) or 0)
    D['sale_gross'], D['sale_derived'] = gross, net
    D['sale_needs_building'] = D['owns_building'] and not D['building']
    bal = N(adv.get('ideal_bank_balance'))
    if not bal and D.get('overhead_dollars'):
        bal = math.ceil(D['overhead_dollars'] / 12.0 / 10000.0) * 10000
    D['ideal_balance'] = bal

    # Practice opportunities, needed by the gains.
    lx = {'overhead': D['overhead'], 'net_collections': D['revenue'],
          'target_overhead': N(adv.get('target_overhead'))}
    lx.update(_deck._production_inputs(folder))
    lx.update(adv.get('levers') or {})
    D['lever_inputs'] = lx
    D['levers'] = _lev.compute(lx)

    excl = (cash['monthly_excluding'] if read else None)
    D['gains_proposed'] = _plan.gains(
        collections=D['collections'], current_savings=D['current_savings'],
        cash=D['cash'], ideal_balance=bal, spend_excl_monthly=excl,
        levers={k: v for k, v in D['levers'].items() if k != 'overhead'},
        extra=adv.get('gains'))
    # The table as the advisor left it in the app replaces the proposal
    # outright: rows they deleted stay deleted.
    if adv.get('gains_table'):
        D['gains'] = [dict(g, gain=N(g.get('gain')) or 0,
                           kind=g.get('kind') or 'cash',
                           invested=[N(x) or 0 for x in
                                     (g.get('invested') or [0, 0, 0])])
                      for g in adv['gains_table'] if g.get('label')]
    else:
        D['gains'] = D['gains_proposed']
    consult = adv.get('consult_date') or datetime.date.today().isoformat()
    f0 = _sav.first_year_fraction(datetime.date.fromisoformat(consult))
    first_plan_year = int(consult[:4]) + (1 if f0 == 0 else 0)
    # A table edited on the Consult plan card is the advisor's newest word,
    # so it rebuilds the schedule even over an older typed one.
    if adv.get('gains_table'):
        D['schedule'] = []
    D['schedule_derived'] = not D['schedule']
    if not D['schedule'] and D['current_savings']:
        D['schedule'] = _plan.schedule(D['gains'], first_plan_year)

    # ---- the two retirement paths -----------------------------------------
    D['proj'] = D['proj2'] = None
    need = [n for n, v in (('age', D['age']), ('retirement age',
            D['retire_age']), ('investable accounts', D['start']),
            ('current savings', D['current_savings']),
            ('personal spending', spend),
            ('savings schedule', D['schedule'])) if not v]
    D['need_proj'] = need
    if not need:
        kw = dict(start=D['start'], consult_date=consult,
                  age_now=int(D['age']), retire_age=int(D['retire_age']),
                  current_savings=D['current_savings'],
                  current_expenses=spend, fq_schedule=D['schedule'],
                  horizon_age=int(N(adv.get('horizon_age')) or
                                  _sav.HORIZON_AGE),
                  r1=N(adv.get('fq_first_year_rate')))
        sale = N(adv.get('sale_net'))
        if sale is None:
            sale = net or 0
        sale_fq = N(adv.get('sale_net_fq'))
        sale_fq = sale if sale_fq is None else sale_fq

        def run(income, sale_net):
            return _sav.project(fq_income=income, sale_net=sale_net, **kw)

        # Retirement income: the advisor's, or what the schedule pays.
        D['income_derived'] = not D['income']
        if not D['income']:
            p = run(1.0, sale_fq)
            D['income'] = _sav.solve_income(
                D['start'], p['f'], p['fq_deposits'], p['retire_year'],
                p['first_year'], p['end_year'],
                r1=N(adv.get('fq_first_year_rate')))
        D['proj'] = run(D['income'], sale)
        if sale_fq != sale:
            fq = run(D['income'], sale_fq)
            for k in ('fq', 'fq_deposits', 'fq_at_retirement'):
                D['proj'][k] = fq[k]
        if adv.get('sale_net_current') is not None:
            cur = run(D['income'], N(adv['sale_net_current']))
            for k in ('current', 'current_deposits', 'runout_year',
                      'years_before_runout', 'on_pace_for', 'on_pace_share',
                      'current_at_retirement'):
                D['proj'][k] = cur[k]
        D['sale'] = sale_fq
        big = adv.get('larger_scenario') or {}
        if big.get('sale_net'):
            p2 = run(1.0, N(big['sale_net']))
            inc2 = N(big.get('target_income')) or _sav.solve_income(
                D['start'], p2['f'], p2['fq_deposits'], p2['retire_year'],
                p2['first_year'], p2['end_year'],
                r1=N(adv.get('fq_first_year_rate')))
            D['proj2'] = run(inc2, N(big['sale_net']))
            D['income2'] = inc2
            D['sale2'] = N(big['sale_net'])
    return D




# --------------------------------------------------------------------------
# Writing into a shape without losing its formatting
# --------------------------------------------------------------------------

def set_text(shape, text):
    """Replace a shape's words, keeping the first run's formatting.

    Lines split on '\\n' become paragraphs cloned from the first, so a
    two-line label keeps its spacing. Extra paragraphs are removed.
    """
    tf = shape.text_frame
    paras = list(tf.paragraphs)
    lines = str(text).split('\n')
    p0 = paras[0]
    runs = list(p0.runs)
    if not runs:
        p0.text = lines[0]
        runs = list(p0.runs)
    runs[0].text = lines[0]
    for r in runs[1:]:
        r._r.getparent().remove(r._r)
    for p in paras[1:]:
        p._p.getparent().remove(p._p)
    for line in lines[1:]:
        new = copy.deepcopy(p0._p)
        p0._p.addnext(new)
        p0 = type(p0)(new, p0._parent)
        p0.runs[0].text = line


def swap_names(shape, first, surname):
    """{FIRST} and {SURNAME}, run by run."""
    pairs = [(TEMPLATE_FIRST, first), (TEMPLATE_SURNAME, surname)]
    for p in shape.text_frame.paragraphs:
        for r in p.runs:
            t = r.text
            for a, b in pairs:
                if b:
                    t = t.replace(a, b)
            r.text = t


def ask(label):
    return '[ADVISOR: %s]' % label


# --------------------------------------------------------------------------
# The slides: template slide number, default treatment, and the shapes
# --------------------------------------------------------------------------

def _row(D, y, which):
    p = D[which]
    return p and p['fq'].get(y)


def slide_fills(D):
    """{template slide number: {shape name: text}} for every fill, plus the
    advisor prompts. Built in one place so the SPEC below stays readable."""
    adv, first = D['adv'], D['first']
    FIRST = first.upper()
    out = {}
    proj = D['proj']
    ra = int(D['retire_age']) if D['retire_age'] else None
    # Counted from the first year the projection shows, as the deck counts
    # it: Oyler's runs 2027 to 2036 and says "in 9 years".
    years = (proj['retire_year'] - proj['first_year']) if proj else (
        (ra - int(D['age'])) if (ra and D['age']) else None)

    # 1 title
    out[1] = {'Text 1': D['names'].upper(), 'Text 4': D['date']}

    # 2 and 20 the difference
    if proj:
        sch = sorted(D['schedule'])
        y2 = N(sch[min(1, len(sch) - 1)][1]) if sch else None
        cur = D['current_savings']
        fq_w, cur_w = proj['fq_at_retirement'], proj['current_at_retirement']
        pace = proj['on_pace_for']
        diff = {
            'income': '%s/yr' % M(D['income']),
            'income_line': 'Retirement income with %s retiring at age %d'
                           % (first, ra),
            'income_up': _signed(D['income'] / pace - 1) if pace else ask('%'),
            'save2': '%s/yr' % _k(y2),
            'save_up': _signed(y2 / cur - 1) if cur else ask('%'),
            'wealth': _k(fq_w),
            'wealth_vs': '$%.1f million' % (cur_w / 1e6),
            'wealth_up': _signed(fq_w / cur_w - 1) if cur_w > 0 else ask('%'),
        }
        out[2] = {
            'Text 5': diff['income'], 'Text 7': diff['income_line'],
            'Text 8': diff['income_up'], 'Text 11': diff['save2'],
            'Text 13': 'Saved per year by year 2, a %s increase against '
                       'today’s %s' % (diff['save_up'].lstrip('+'),
                                            _k(cur)),
            'Text 16': diff['wealth'],
            'Text 18': 'Retirement wealth in %d years, against' % years,
            'Text 19': diff['wealth_vs'], 'Text 20': diff['wealth_up'],
            'Text 23': ask('change in reliance on the sale'),
        }
        out[20] = {
            'Text 3': diff['income'], 'Text 4': diff['income_line'],
            'Text 5': diff['income_up'], 'Text 7': diff['save2'],
            'Text 8': 'Saved by year 2, against today’s %s' % _k(cur),
            'Text 9': diff['save_up'], 'Text 11': diff['wealth'],
            'Text 12': 'Retirement wealth in %d years, against %s'
                       % (years, diff['wealth_vs']),
            'Text 13': diff['wealth_up'],
            'Text 15': D['names'].upper(),
            'Text 16': 'Consultation · %s' % D['date'],
        }
    else:
        miss = ask('needs ' + ', '.join(D['need_proj']))
        out[2] = {k: miss if k == 'Text 5' else ask('from the projection')
                  for k in ('Text 5', 'Text 7', 'Text 8', 'Text 11',
                            'Text 13', 'Text 16', 'Text 18', 'Text 19',
                            'Text 20', 'Text 23')}
        out[20] = {k: ask('from the projection') for k in
                   ('Text 3', 'Text 4', 'Text 5', 'Text 7', 'Text 8',
                    'Text 9', 'Text 11', 'Text 12', 'Text 13')}
        out[20].update({'Text 15': D['names'].upper(),
                        'Text 16': 'Consultation · %s' % D['date']})

    # 3 concerns
    con = adv.get('concerns') or []
    out[3] = {'Text 2': '%s’S BIGGEST CONCERNS' % FIRST}
    if years:
        out[3]['Text 3'] = 'Financial freedom in %d years' % years
        out[3]['Text 28'] = ('Blend business, financial and transition '
                             'strategies across the practice and the personal '
                             'situation to achieve financial freedom in %d '
                             'years.' % years)
    for i, (h, b) in enumerate([('Text 7', 'Text 8'), ('Text 11', 'Text 12'),
                                ('Text 15', 'Text 16'), ('Text 19', 'Text 20'),
                                ('Text 23', 'Text 24')]):
        if i < len(con):
            item = con[i]
            head, body = (item if isinstance(item, (list, tuple))
                          else (item, ''))
            out[3][h], out[3][b] = head.upper(), body
        else:
            out[3][h] = ask('concern %d' % (i + 1))
            out[3][b] = ask('in the client’s words')

    # 4 results applied to the practice
    th, oh, sv = D['take_home'], D['overhead'], D['current_savings']
    out[4] = {
        'Text 23': M(th) or ask('income'),
        'Text 26': M(th * RESULT_INCOME) if th else ask('income'),
        'Text 30': _pct(oh, 2) or ask('overhead'),
        'Text 33': _pct(oh * RESULT_OH, 2) if oh else ask('overhead'),
        'Text 35': M(sv) or ask('savings'),
        'Text 37': M(sv * RESULT_SAVE) if sv else ask('savings'),
    }

    # 9 practice opportunities: five rows in the template
    lv = D['levers']
    lx = D['lever_inputs']
    target = lx.get('target_overhead') or _lev.TARGET_OH
    owner = 1 - target
    rows = []
    if lv['overhead'].get('value') is not None:
        rows.append(('Overhead', _pct(lx['overhead']), _pct(target), 0.0,
                     lv['overhead']['value']))
    if lv['adjustment'].get('value'):
        rows.append(('Production adjustment %', _pct(lx['adjust_pct']),
                     ask('goal'), lv['adjustment']['value'] / owner,
                     lv['adjustment']['value']))
    if lv['collections'].get('value'):
        rows.append(('Collection %', _pct(lx['collection_pct']), '99.5%',
                     lv['collections']['value'] / owner,
                     lv['collections']['value']))
    for key, label in (('new_patients', 'New patient % of total patients'),
                       ('per_patient', 'Net production/patient'),
                       ('hygiene', 'Hygiene chair-days'),
                       ('fees', 'Increase fees')):
        v = lv[key].get('value')
        if v:
            rows.append((label, ask('current'), ask('goal'), v / owner, v))
    rows = rows[:5]
    cells = [('Text 13', 'Text 15', 'Text 17', 'Text 19', 'Text 22'),
             ('Text 24', 'Text 26', 'Text 28', 'Text 30', 'Text 33'),
             ('Text 35', 'Text 37', 'Text 39', 'Text 41', 'Text 44'),
             ('Text 46', 'Text 48', 'Text 50', 'Text 52', 'Text 55'),
             ('Text 57', 'Text 59', 'Text 61', 'Text 63', 'Text 66')]
    out[9] = {}
    for i, names in enumerate(cells):
        if i < len(rows):
            r = rows[i]
            vals = [r[0], r[1], r[2], M(r[3]), M(r[4])]
        else:
            # Never blank: Keynote deletes an empty text box on save, and the
            # advisor then has no cell to type a sixth lever into.
            vals = [ask('lever'), '[TBD]', '[TBD]', '[TBD]', '[TBD]']
        for n, v in zip(names, vals):
            out[9][n] = v
    rev = sum(r[3] for r in rows)
    own = sum(r[4] for r in rows)
    out[9].update({
        'Text 2': '%s LEVER%s, ONE PRACTICE' % (WORDS.get(len(rows), str(len(rows))),
                                              '' if len(rows) == 1 else 'S'),
        'Text 3': '%s extra to owner%s' % (M(own), 's' if
                                           adv.get('owners_plural') else ''),
        'Text 4': 'on %s of additional revenue' % M(rev),
        'Text 72': M(rev), 'Text 74': M(own),
    })

    # 10 corporate debt
    if D['debt_service']:
        out[10] = {'Text 3': '%s/mo in payments today' % M(D['debt_service']),
                   'Text 28': '%s/mo' % M(D['debt_service']),
                   'Text 4': 'across the practice loans'}

    # 13 cash flow process: the ideal balance, wherever it appears
    # One month of practice expenses on the most recent reliable overhead,
    # which is the firm's rule (Austin, 21 October): the overhead numerator
    # of the newest full-year P&L over twelve, rounded up to the next $10k.
    # Rebol: $2,098,078 / 12 = $174,840, so $180k, as on his deck.
    bal = D.get('ideal_balance')
    b_txt = _k(bal).replace('.0k', 'k') if bal else ask('ideal balance')
    out[13] = {
        'Text 3': b_txt,
        'Text 8': 'Establish an ideal practice bank balance of %s.' % b_txt,
        'Text 20': 'Four Quadrants consolidates and refinances practice debt, '
                   'and obtains a fresh line of credit of %s+.' % b_txt,
        'Text 31': 'Once accounts reach %s, devise income, debt and savings '
                   'strategies to maximize the financial plan.' % b_txt,
    }

    # 15 investments current
    if D['start']:
        out[15] = {'Text 5': 'WHERE THE %s SITS' % _k(D['start']),
                   'Text 6': '%s total retirement savings' % M(D['start'])}
        acct_rows = [('Text 24', 'Text 27'), ('Text 38', 'Text 41'),
                     ('Text 51', 'Text 53')]
        for i, (lab, val) in enumerate(acct_rows):
            if i < len(D['start_parts']):
                l, a = D['start_parts'][i]
                short = re.sub(r'\s*\[.*?\]', '', l).split(',')[0]
                out[15][lab] = short.upper()[:24]
                out[15][val] = _k(a)
            else:
                out[15][lab], out[15][val] = '[TBD]', '[TBD]'

    # 16 savings projection: the advisor's sources; totals from the schedule
    # 16 the savings projection, from the gains: what each is worth a year
    # and the proposed share of it invested. Rows the gains do not fill stay
    # [TBD] for the advisor, and the totals are only printed when every row
    # behind them is filled (Austin's test edit: a total beside [TBD] rows
    # reads as a figure nobody can account for).
    sch = sorted(D['schedule'])
    # Only when the schedule came from these gains: beside an advisor's own
    # schedule they would describe a plan nobody chose.
    gl = [g for g in D['gains']] if D.get('schedule_derived') else []
    if gl:
        y1 = [('Text 10', 'Text 12', 'Text 14'), ('Text 16', 'Text 18', 'Text 20'),
              ('Text 22', 'Text 24', 'Text 26'), ('Text 28', 'Text 30', 'Text 32'),
              ('Text 34', 'Text 36', 'Text 38'), ('Text 40', 'Text 42', 'Text 44')]
        out[16] = {}
        for i, cells in enumerate(y1):
            if i < len(gl):
                g = gl[i]
                vals = [g['label'], M(g['gain']), M(_plan.invested(g, 0))]
            else:
                vals = [ask('another source'), '[TBD]', '[TBD]']
            for n, v in zip(cells, vals):
                out[16][n] = v
        full = len(gl) <= len(y1)
        out[16]['Text 54'] = M(sum(g['gain'] for g in gl)) if full else '[TBD]'
        out[16]['Text 56'] = M(sum(_plan.invested(g, 0) for g in gl)) \
            if full else '[TBD]'
        rec = [g for g in gl if g['kind'] != 'once']
        y2 = [('Text 63', 'Text 65', 'Text 67'), ('Text 69', 'Text 71', 'Text 73'),
              ('Text 75', 'Text 77', 'Text 79'), ('Text 81', 'Text 83', 'Text 85')]
        same = sum(_plan.invested(g, 0) for g in rec)
        step = sum(_plan.invested(g, 1) - _plan.invested(g, 0) for g in rec)
        rows2 = [('Same as year 1 (minus one-timers **)',
                  M(sum(g['gain'] for g in rec)), M(same)),
                 ('Practice improvements, second year', '\u2013', M(step))]
        for i, cells in enumerate(y2):
            vals = rows2[i] if i < len(rows2) else (
                ask('another source'), '[TBD]', '[TBD]')
            for n, v in zip(cells, vals):
                out[16][n] = v
        out[16]['Text 89'] = M(sum(g['gain'] for g in rec)) if full else '[TBD]'
        out[16]['Text 91'] = M(same + step) if full else '[TBD]'

    # 17 and 18 the Four Quadrants future
    for slide, which, inc_key in ((17, 'proj', 'income'), (18, 'proj2',
                                                           'income2')):
        p = D.get(which)
        if not p:
            continue
        inc = D[inc_key]
        q, y0, ry, ey = p['fq'], p['first_year'], p['retire_year'], \
            p['end_year']
        changes, last = [], None
        for y, a in sch:
            if N(a) != last:
                changes.append(int(y))
                last = N(a)
        early = sorted(set([y0, y0 + 1, y0 + 2] + changes))
        early = [y for y in early if y < ry][:4]
        cy = int((adv.get('consult_date') or
                  datetime.date.today().isoformat())[:4])

        def age_at(y, cy=cy):
            # Age is the IC form's, in the consult year.
            return int(D['age']) + (y - cy)

        def exp_at(y):
            return inc * (1 + _sav.INFLATION) ** (y - y0)
        fill = {'Text 3': '%s/yr' % M(inc), 'Text 7': '%s AGE' % FIRST}
        if slide == 17 and not D.get('proj2'):
            fill['Text 4'] = 'retirement income'
        grid = [('Text 14', 'Text 16', 'Text 18', 'Text 20', 'Text 22'),
                ('Text 25', 'Text 27', 'Text 29', 'Text 31', 'Text 33'),
                ('Text 36', 'Text 38', 'Text 40', 'Text 42', 'Text 44'),
                ('Text 47', 'Text 49', 'Text 51', 'Text 53', 'Text 55')]
        for i, names in enumerate(grid):
            if i < len(early):
                y = early[i]
                vals = [str(age_at(y)), str(y),
                        M(p['fq_deposits'].get(y, 0)), M(q[y]), M(exp_at(y))]
            else:
                vals = ['[TBD]'] * 5
            for n, v in zip(names, vals):
                fill[n] = v
        sale = D['sale'] if slide == 17 else D['sale2']
        fill.update({
            'Text 59': str(age_at(ry)), 'Text 62': str(ry),
            'Text 65': M(p['fq_deposits'].get(ry, 0)), 'Text 68': M(q[ry]),
            'Text 71': M(exp_at(ry)),
            'Text 74': ('*practice%s sell, %s net' % (
                ' & bldg' if D.get('building') else '', _k(sale))) +
            (' (building not valued)' if D.get('sale_needs_building')
             else ''),
            'Text 75': str(age_at(ey)), 'Text 76': str(ey), 'Text 77': '$0',
            'Text 78': M(q[ey]), 'Text 79': M(exp_at(ey)),
            'Text 81': ('Funded to %d at %s/yr.' % (age_at(ey), M(inc)))
            if q[ey] > -1000 else
            ('Runs short in %s at %s/yr.' % (_sav.runout_year(
                {k: v for k, v in q.items() if k > ry}) or ey, M(inc))),
            'Text 82': ('Retire at %d, practice%s sell%s in %d.'
                        % (ra, ' and building' if D.get('building') else '',
                           '' if D.get('building') else 's', ry))
            if slide == 17 else
                       'Same savings path, a higher sale price.',
        })
        out[slide] = fill
    return out


# Template slide number -> (default treatment, {shape: treatment})
# 'fill' shapes are written from slide_fills(); anything a fill provides wins
# over the treatment named here.
SPEC = {
    1: ('keep', {}),
    2: ('keep', {'Text 25': 'name'}),
    3: ('advisor', {'Text 1': 'keep', 'Text 4': 'keep', 'Text 26': 'keep'}),
    4: ('keep', {}),
    5: ('keep', {}),
    6: ('keep', {}),
    7: ('advisor', {'Text 1': 'keep', 'Text 2': 'keep', 'Text 3': 'keep',
                    'Text 6': 'keep', 'Text 19': 'keep', 'Text 27': 'keep',
                    'Text 28': 'keep'}),
    8: ('advisor', {'Text 1': 'keep', 'Text 2': 'keep', 'Text 6': 'keep',
                    'Text 10': 'keep', 'Text 14': 'keep', 'Text 18': 'keep',
                    'Text 22': 'keep', 'Text 26': 'keep', 'Text 27': 'keep',
                    'Text 29': 'keep', 'Text 31': 'keep'}),
    9: ('keep', {'Text 78': 'keep', 'Text 79': 'keep', 'Text 80': 'name',
                 'Text 81': 'keep'}),
    10: ('advisor', {'Text 1': 'keep', 'Text 10': 'keep', 'Text 12': 'name',
                     'Text 14': 'keep', 'Text 15': 'keep', 'Text 18': 'keep',
                     'Text 27': 'keep', 'Text 29': 'keep', 'Text 32': 'keep'}),
    11: ('advisor', {'Text 1': 'keep', 'Text 2': 'keep', 'Text 8': 'keep',
                     'Text 14': 'keep', 'Text 18': 'keep', 'Text 22': 'keep',
                     'Text 27': 'keep', 'Text 30': 'keep', 'Text 34': 'keep',
                     'Text 38': 'keep', 'Text 43': 'keep', 'Text 46': 'keep'}),
    12: ('advisor', {'Text 1': 'keep', 'Text 2': 'keep', 'Text 4': 'keep',
                     'Text 7': 'keep', 'Text 8': 'keep', 'Text 10': 'keep',
                     'Text 12': 'keep', 'Text 19': 'keep', 'Text 26': 'keep',
                     'Text 33': 'keep', 'Text 41': 'keep'}),
    13: ('keep', {}),
    14: ('keep', {'Text 20': 'advisor', 'Text 21': 'advisor',
                  'Text 25': 'advisor', 'Text 28': 'advisor',
                  'Text 34': 'advisor'}),
    15: ('advisor', {'Text 1': 'keep', 'Text 2': 'keep', 'Text 4': 'keep',
                     'Text 17': 'keep', 'Text 18': 'keep', 'Text 19': 'keep',
                     'Text 20': 'keep', 'Text 21': 'keep', 'Text 35': 'keep'}),
    16: ('advisor', {'Text 1': 'keep', 'Text 2': 'keep', 'Text 3': 'keep',
                     'Text 5': 'keep', 'Text 6': 'keep', 'Text 7': 'keep',
                     'Text 46': 'keep', 'Text 48': 'keep', 'Text 50': 'keep',
                     'Text 52': 'keep', 'Text 58': 'keep', 'Text 59': 'keep',
                     'Text 60': 'keep', 'Text 87': 'keep', 'Text 92': 'keep'}),
    17: ('keep', {}),
    18: ('keep', {}),
    19: ('keep', {'Text 25': 'advisor', 'Text 26': 'advisor',
                  'Text 29': 'advisor', 'Text 36': 'advisor',
                  'Text 37': 'advisor', 'Text 40': 'advisor'}),
    20: ('keep', {}),
}

# Notes that hold for any client are kept; the rest are rewritten.
KEEP_NOTES = {5, 6}

NOTES = {
    4: 'Our traditional-program clients become top one percent practices. '
       'Three-year averages: net income up over 25 percent, overhead down '
       'nearly 11 percent, retirement savings up over 675 percent, all net of '
       'our fees. The right-hand column applies those averages to this '
       'practice\u2019s own figures.',
    2: 'The destination first. Retirement income, savings by year two and '
       'retirement wealth are from savings.py: the current path at 8.5% on '
       'today’s savings, the Four Quadrants path at 9% on the advisor’s '
       'schedule.',
    9: 'The overhead goal is 50% (Bryan’s model) unless the advisor sets one. '
       'The firm has not settled the long-term goal, so check it before '
       'presenting. Levers from levers.py. Overhead to the goal is '
       'savings, not revenue, so it adds nothing to the revenue column. The '
       'levers overlap; the total is not strictly additive.',
    15: 'Account values from the Assumptions, sections 4 and 5. What is inside '
        'each account and how it compares to 4Q is the advisor’s read.',
    17: 'savings.py, Four Quadrants path. Expenses inflate 3.2% a year from '
        'the first year shown.',
    18: 'Same savings path at the larger practice value the advisor entered.',
    20: 'Same three figures as slide 2.',
}


def _drop(prs, index):
    sld = prs.slides._sldIdLst[index]
    prs.part.drop_rel(sld.rId)
    prs.slides._sldIdLst.remove(sld)


def render(folder, client, out, template=TEMPLATE):
    D = figures(folder, client)
    fills = slide_fills(D)
    prs = Presentation(template)
    prompts = 0
    drop = []
    if not D['debt_service']:
        drop.append(10)
    adv = D['adv']
    if not (adv.get('tax_current') and adv.get('tax_split')):
        drop.append(12)
    if not D.get('proj2'):
        drop.append(18)

    for n, slide in enumerate(prs.slides, 1):
        default, shapes = SPEC.get(n, ('keep', {}))
        mine = fills.get(n, {})
        asked = []
        for sh in slide.shapes:
            if not sh.has_text_frame or not sh.text_frame.text.strip():
                continue
            name = sh.name
            if name in mine:
                # The redesign's minus sign and straight apostrophe.
                text = str(mine[name]).replace('-$', '\u2212$').replace(
                    '\u2019', "'")
                set_text(sh, text)
                if str(mine[name]).startswith(('[ADVISOR', '[TBD')):
                    asked.append(mine[name])
                continue
            how = shapes.get(name, default)
            if how == 'keep':
                continue
            if how == 'name':
                swap_names(sh, D['first'], D['surname'])
                continue
            if how == 'advisor':
                # Never echo the template's own words: they are Oyler's
                # ("the $476.7k shareholder loan", "Reef"), and an echo would
                # carry them into the next client's deck. Short cells (a
                # figure, a rate) get [TBD] so the layout holds.
                was = sh.text_frame.text.strip()
                label = '[TBD]' if len(was) <= 18 else ask('write this')
                set_text(sh, label)
                asked.append(label)
        prompts += len(asked)
        if slide.has_notes_slide and n not in KEEP_NOTES:
            note = NOTES.get(n, '')
            if asked:
                note += ('\n\nStill to write on this slide: %d item%s marked '
                         '[ADVISOR] or [TBD].'
                         % (len(asked), '' if len(asked) == 1 else 's'))
            slide.notes_slide.notes_text_frame.text = note.strip()

    for n in sorted(drop, reverse=True):
        _drop(prs, n - 1)
    prs.save(out)
    return out, len(prs.slides._sldIdLst), prompts, drop


def main():
    ap = argparse.ArgumentParser(description='Consult deck from the template')
    ap.add_argument('folder')
    ap.add_argument('--client', default=None)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    out, n, prompts, drop = render(a.folder, a.client, a.out)
    print('%s: %d slides, %d advisor prompts, dropped %s'
          % (out, n, prompts, drop or 'none'))


if __name__ == '__main__':
    main()
