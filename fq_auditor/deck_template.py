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
import json
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

SKIP_THEMES = ('Fee range', 'Timeline', 'Comprehensive plan', 'Objections',
               'Competition', 'Fees')


def pain_concerns(bundle, limit=5):
    """[(heading, body)] from the initial notes' pain points block: the
    dentist's own words first, then the themes with the figure behind each."""
    rows = []
    for block in bundle.blocks:
        if not block.title.lower().startswith('pain points'):
            continue
        for fact in block.facts:
            if not fact.value or fact.label.startswith(SKIP_THEMES):
                continue
            if fact.label.startswith('Dentist pain'):
                continue
            head = re.sub(r',.*$', '', fact.label)
            rows.append((client_head(head), client_voice(head, str(fact.value))))
    return [_fit_card(i, r) for i, r in enumerate(rows[:limit])]


def _fit_card(i, row):
    """The fourth concern card's text box shrinks anything past one short
    line to fit (the firm, 29 Oct: the Debt line went tiny). Keep it to the
    first clause there."""
    head, body = row
    if i == 3 and len(body) > 70:
        body = body.split(';')[0].rstrip('.') + '.'
    return (head, body)


def _short(text):
    """'$720,061' -> '$720k'."""
    v = float(re.sub(r'[^\d.]', '', text) or 0)
    return '$%.1fM' % (v / 1e6) if v >= 1e6 else '$%dk' % round(v / 1000)


HEADS = {'oh improvements': 'Overhead', 'qb improvements': 'Books and taxes',
         'debt structuring': 'Debt', 'retirement planning': 'Retirement',
         'tax management / cpa': 'Tax surprises'}


def client_head(head):
    return HEADS.get((head or '').strip().lower(), head)


def client_voice(head, body):
    """The analyst’s evidence line, said to the client for the slide.

    The pain points block is written for the team ("liquid if walking away
    today: 'Not enough'"); the concerns slide is read by the dentist."""
    h = head.lower()
    bits = []
    if h.startswith('retirement'):
        m = re.search(r'target ([^;]+?) was a guess', body)
        if m:
            bits.append('Your %s retirement target was a guess' % (m.group(1).strip() if m.group(1).strip().startswith('$') else '$' + m.group(1).strip()))
        if 'no plan connecting' in body:
            bits.append('nothing ties the practice to retirement')
        if 'not saving enough' in body:
            bits.append('you are not saving enough today')
        if re.search(r'walking away today: "?not enough', body, re.I):
            bits.append('there is not enough set aside to walk away')
    elif h.startswith('oh'):
        pnl = re.search(r'([\d.]+)% on the (\d{4}) P&L', body)
        said = re.search(r'client thinks ([\d.]+%)', body)
        if pnl:
            bits.append('Overhead runs %s%% on the books' % round(float(pnl.group(1))))
            if said:
                bits[-1] += ' against the %s you estimated' % said.group(1)
    elif h.startswith('practice efficiencies'):
        m = re.search(r'new patients ([\d,]+) to ([\d,]+)', body)
        if m:
            bits.append('New patients fell from %s to %s last year' % m.groups())
        m = re.search(r'collect % ([\d.]+%)', body)
        if m:
            bits.append('collections are at %s' % m.group(1))
    elif h.startswith('debt'):
        m = re.search(r'(\$[\d,]+) across (\d+) obligations\. (\$[\d,]+)/mo', body)
        if m:
            bits.append('%s of practice debt costing %s a month' % (_short(m.group(1)), _short(m.group(3))))
        m = re.search(r'LOC drawn to (\$[\d,]+) of (\$[\d,]+)', body)
        if m:
            bits.append('the line of credit is drawn to %s of %s' % (_short(m.group(1)), _short(m.group(2))))
    elif h.startswith('qb'):
        if 'not' in body or 'apart' in body:
            bits.append('The books do not tie to the tax return')
        if 'depreciation' in body:
            bits.append('depreciation is not being booked')
    elif h.startswith('tax'):
        bits.append('Surprises at tax time and a CPA relationship that is not proactive')
    elif h.startswith('fee'):
        m = re.search(r'([\d.]+)% below', body)
        bits.append('Fees sit %s%% below the market' % m.group(1) if m else body)
    if not bits:
        return body
    # The cards hold about 110 characters at their font; past that the line
    # runs off the card (the firm, 29 Oct, the Debt card). Keep whole clauses.
    text = bits[0]
    for b in bits[1:]:
        if len(text) + 2 + len(b) > 105:
            break
        text += '; ' + b
    return text[0].upper() + text[1:] + '.'


def _series_inputs(bundle, folder):
    """The lever inputs the initial notes already hold: patients, new patient
    share and net production per patient for the last two FULL years (the
    current year is a year to date), hygiene share, the IC form's days, and
    the fee study. Without them the deck showed two levers where the lead advisor
    shows five."""
    out = {}
    this_year = str(datetime.date.today().year)
    ser = {name: vals for name, vals, _f in bundle.series}

    def last_two(name):
        vals = ser.get(name) or {}
        ys = [y for y in sorted(vals) if vals.get(y) is not None and y < this_year]
        return [vals[y] for y in ys[-2:]] if len(ys) >= 2 else None
    pats = ser.get('patients (procedures)') or {}
    full = [y for y in sorted(pats) if pats.get(y) and y < this_year]
    if full:
        out['patients'] = pats[full[-1]]
    np2 = last_two('new patients % of total')
    if np2:
        out['np_pct_prior'], out['np_pct'] = np2
    pp2 = last_two('net production / patient')
    if pp2:
        out['net_per_patient_prior'], out['net_per_patient'] = pp2
    else:
        # From the practice's own production export, over the patients seen
        try:
            pi = _deck.annual_pi(folder)
            ys = [y for y in sorted(pi) if not pi[y]['partial'] and pats.get(y)]
            if len(ys) >= 2:
                out['net_per_patient_prior'] = pi[ys[-2]]['net'] / pats[ys[-2]]
                out['net_per_patient'] = pi[ys[-1]]['net'] / pats[ys[-1]]
        except Exception:                                    # noqa: BLE001
            pass
    hyg = last_two('hygiene % of production')
    if hyg:
        out['hygiene_share'] = hyg[-1]
    try:
        import intake_form as _ic
        f = _ic.find_form_near(folder)
        form = _ic.parse(f) if f else {}
        if _ic.money(form.get('hygiene_days')):
            out['hygiene_days'] = _ic.money(form.get('hygiene_days'))
        if _ic.money(form.get('doctor_days')):
            out['doctor_days'] = _ic.money(form.get('doctor_days'))
        if str(form.get('in_network') or '').strip().lower().startswith('no'):
            out['ffs_share'] = 1.0
    except Exception:                                        # noqa: BLE001
        pass
    try:
        import compose as _compose
        pct, _txt = _compose.fee_study(folder)
        if pct is not None:
            out['fees_off'] = max(0.0, -pct / 100.0)
    except Exception:                                        # noqa: BLE001
        pass
    return out


# Every assumption the lead advisor can change on the review page: deck
# entry key -> (module, constant, what it is, as a percent?). The default is
# the module's own value; the review page shows it and takes his figure.
ASSUMPTIONS = (
    ('a_current_return', _sav, 'CURRENT_RETURN', 'Return on the current path', True),
    ('a_fq_return', _sav, 'FQ_RETURN', 'Return with Four Quadrants', True),
    ('a_first_year_return', _sav, 'FIRST_YEAR_FQ_RETURN',
     'Return with Four Quadrants, first year', True),
    ('a_inflation', _sav, 'INFLATION', 'Inflation on retirement spending', True),
    ('a_horizon_age', _sav, 'HORIZON_AGE', 'Plan to age', False),
    ('a_practice_multiple', _plan, 'PRACTICE_MULTIPLE',
     'Practice value, as a share of collections', True),
    ('a_practice_growth', _plan, 'PRACTICE_GROWTH', 'Practice value growth a year', True),
    ('a_building_growth', _plan, 'BUILDING_GROWTH', 'Building value growth a year', True),
    ('a_sale_net', _plan, 'SALE_NET', 'Sale kept after tax', True),
    ('a_refi_rate', _plan, 'REFI_RATE', 'Refinance rate', True),
    ('a_refi_years', _plan, 'REFI_YEARS', 'Refinance term, years', False),
    ('a_refi_share', _plan, 'REFI_SHARE', 'Share of the refinance savings invested', True),
    ('a_once_share', _plan, 'ONCE_SHARE', 'Share of one-time cash invested', True),
)
_ASSUMPTION_DEFAULTS = {k: getattr(m, c) for k, m, c, _l, _p in ASSUMPTIONS}


def apply_assumptions(adv):
    """Set the models' constants from the deck entry, back to the firm's
    defaults first so one client's figures never carry to the next."""
    for key, mod, const, _label, pct in ASSUMPTIONS:
        v = N(adv.get(key)) if adv.get(key) not in (None, '') else None
        if v is not None and pct and v > 1:
            v = v / 100.0
        setattr(mod, const, v if v is not None else _ASSUMPTION_DEFAULTS[key])


_FIGURES = {}


def figures(folder, client):
    """Once per run: the review page asks for the same figures four times
    (the plan, the wording, the pictures, the workings), at 40 seconds each."""
    key = (os.path.abspath(folder), client)
    if key not in _FIGURES:
        _FIGURES[key] = _figures(folder, client)
    D = _FIGURES[key]
    apply_assumptions(D['adv'])
    return copy.deepcopy(D)


def _figures(folder, client):
    """Everything the slides print, from the documents, the models and the
    advisor's entry. Missing values are None and the slide says so."""
    b = _facts.gather(folder, client)
    f = {x.label: x.value for x in b.all_facts()}
    adv = _deck._advisor(folder)
    apply_assumptions(adv)
    # The concerns are the pain points from the initial notes, settled
    # weeks earlier, not something to invent at the deck. Used unless the
    # advisor has written their own.
    if not adv.get('concerns'):
        adv = dict(adv)
        adv['concerns'] = pain_concerns(b)
        adv['concerns_from'] = 'initial notes'
    else:
        # Concerns carried from the review page are still the team's wording
        # unless the lead advisor rewrote them; say them to the client.
        adv = dict(adv)
        adv['concerns'] = [_fit_card(i, (client_head(c[0]),
                            client_voice(c[0], c[1] if len(c) > 1 else '')))
                           for i, c in enumerate(adv['concerns'])]
    D = {'adv': adv, 'facts': f, 'folder': folder,
         'first': b.forename or 'the client',
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
    # The account table on the investments slide has three rows: the three
    # largest accounts, in the order the plan lists them (Rebol has six, and
    # his two Schwab IRAs hold most of the money).
    top = sorted(range(len(parts)), key=lambda i: -parts[i][1])[:3]
    D['slide_parts'] = [parts[i] for i in sorted(top)]
    D['age'] = N(f.get('Age')) or N(adv.get('age'))
    D['retire_age'] = N(adv.get('retire_age')) or _deck.retire_age_of(f.get('Retirement age goal'))
    D['current_savings'] = N(adv.get('current_savings'))
    D['income'] = N(adv.get('target_income'))
    D['schedule'] = [tuple(x) for x in (adv.get('savings_schedule') or [])]
    D['take_home'] = N(adv.get('current_income')) or N(f.get('Take-home, stated'))
    D['overhead'] = N(f.get('Overhead, tax basis')) or \
        N(f.get('Overhead, P&L basis'))
    D['revenue'] = N(f.get('Income base (overhead denominator)'))
    D['overhead_dollars'] = N(f.get('Total expenses (overhead numerator)'))
    D['debt_total'] = N(f.get('Practice total'))
    try:
        import debt as _debt
        D['practice_debts'] = _debt.gather(folder).get('practice') or []
    except Exception:                                        # noqa: BLE001
        D['practice_debts'] = []
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
    lx.update(_series_inputs(b, folder))
    lx.update(adv.get('levers') or {})
    D['lever_inputs'] = lx
    D['levers'] = _lev.compute(lx)

    excl = (cash['monthly_excluding'] if read else None)
    D['income_facts'] = {}
    if not os.environ.get('FQ_NO_DRAFTS'):
        try:
            import deck_drafts
            D['income_facts'] = deck_drafts.income_facts(folder, D['first'] or '')
        except Exception:  # noqa: BLE001
            pass
    D['returns'] = {}
    if not os.environ.get('FQ_NO_DRAFTS'):
        try:
            import deck_drafts
            D['returns'] = deck_drafts.account_returns(
                folder, [l for l, _a in D.get('start_parts') or []],
                D['first'] or '')
        except Exception:  # noqa: BLE001
            pass
    # 4Q's return over each account's period, and any corrected account
    # return, from the review page
    for l, v in ((adv.get('returns') or {}).items()):
        D['returns'].setdefault(l, {}).update(
            {k: x for k, x in v.items() if x is not None})
    D.setdefault('schedule', D.get('schedule') or [])
    _inc = income_structure(D)
    D['gains_proposed'] = _plan.gains(
        collections=D['collections'], current_savings=D['current_savings'],
        cash=D['cash'], ideal_balance=bal, spend_excl_monthly=excl,
        levers={k: v for k, v in D['levers'].items() if k != 'overhead'},
        extra=adv.get('gains'),
        refi_freed=None if str(adv.get('refinance', '')).lower() in ('no', 'n', 'false', '0')
        else (_plan.refinance(D.get('practice_debts')) or {}).get('freed'),
        added_deferral=_inc['more_saved'] if _inc else None)
    # The table as the advisor left it in the app replaces the proposal
    # outright: rows they deleted stay deleted.
    if adv.get('gains_table'):
        D['gains'] = [dict(g, gain=N(g.get('gain')) or 0,
                           key=g.get('key') or g.get('label'),
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

PLACEHOLDER_GREY = 'A0A8B1'


def placeholder_style(shape, short):
    """Quiet the marker: grey, small, never wrapping.

    "[TBD]" in a 28pt orange figure cell read as a headline and wrapped to
    "[TB D]" (the firm, 29 Oct). A figure cell now shows a small grey TBD; a
    text box keeps its [ADVISOR: ...] note, grey and at body size, so the
    slide still says what to write without shouting it.
    """
    from pptx.util import Pt
    from pptx.dml.color import RGBColor
    tf = shape.text_frame
    tf.word_wrap = not short
    for para in tf.paragraphs:
        for run in para.runs:
            run.font.color.rgb = RGBColor.from_string(PLACEHOLDER_GREY)
            size = run.font.size.pt if run.font.size else 12
            run.font.size = Pt(min(size, 11 if short else 12))
            run.font.bold = False
            run.font.italic = not short


def _split_label(shape, force=False):
    """The lead advisor’s red flags read "Label: detail" with only the label bold.
    set_text clones the first (bold) run for the whole line; split it."""
    import copy as _copy
    p = shape.text_frame.paragraphs[0]
    runs = list(p.runs)
    if len(runs) != 1 or not (force or runs[0].font.bold):
        return
    t = runs[0].text
    m = re.match(r'^([^:]{3,60}:)(\s.+)$', t)
    if not m:
        return
    runs[0].text = m.group(1)
    new = _copy.deepcopy(runs[0]._r)
    runs[0]._r.addnext(new)
    r2 = p.runs[1]
    r2.text = m.group(2)
    runs[0].font.bold = True
    r2.font.bold = False


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
        # How much of retirement rests on the sale: its share of the
        # portfolio at retirement, current path against 4Q's.
        sale_c = D.get('sale') or 0
        sale_q = N(D['adv'].get('sale_net_fq')) or sale_c
        share_c = sale_c / cur_w if cur_w else None
        share_q = sale_q / fq_w if fq_w else None
        reliance = (_signed(share_q / share_c - 1) if share_c and share_q
                    else ask('change in reliance on the sale'))
        diff = {
            'income': '%s/yr' % M(D['income']),
            'income_line': 'Retirement income with %s retiring at age %d'
                           % (first, ra),
            # Against what the household spends today, as the lead advisor computes
            # it (Oyler: $599,000 over $404,592 = +48%), not against the
            # income the current path could sustain.
            'income_up': (_signed(D['income'] / D['spend'] - 1) if D.get('spend')
                          else (_signed(D['income'] / pace - 1) if pace else ask('%'))),
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
            'Text 23': reliance,
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

    # 7 and 8 tax and accounting. Page 8 is the firm's standing language:
    # The lead advisor’s Oyler, Meier and Kinsler decks say the same five things with
    # the name changed. Page 7's red flags are the client's own, but three
    # lines recur on every deck, and the toolkit's findings supply the books
    # line and the tax-surprise line.
    out[8] = {
        'Text 6': 'CLEAN UP THE PAST',
        'Text 7': 'Review prior years and amend returns if needed, then correct '
                  'those problems going forward.',
        'Text 10': 'ELIMINATE THE RED FLAGS',
        'Text 11': 'Correct the QuickBooks and financial problems and reconcile '
                   'them to the tax returns.',
        'Text 14': 'PAY YOURSELF CORRECTLY',
        'Text 15': 'Adjust %s\u2019s W-2 and distributions to minimize taxes and '
                   'maximize retirement.' % first,
        'Text 18': 'BEST PRACTICES, IMPLEMENTED',
        'Text 19': 'Advise on accounting best practices and implement additional '
                   'tax savings strategies and deductions.',
        'Text 22': 'BOOKS THAT STAY CLOSED',
        'Text 23': 'Improve practice accounting, update financials, and record '
                   'adjustments and reconcile monthly, reducing audit exposure.',
    }
    f7 = D.get('facts') or {}
    flags = []
    pnl, tax = N(f7.get('Overhead, P&L basis')), N(f7.get('Overhead, tax basis'))
    dep = f7.get('Depreciation / amortisation')
    books = []
    if pnl and tax and abs(pnl - tax) >= 0.02:
        books.append('overhead reads %.0f%% on the books and %.0f%% on the return'
                     % (100 * pnl, 100 * tax))
    if dep in (0, 0.0):
        books.append('no depreciation is booked')
    if books:
        flags.append('QuickBooks and financials don\u2019t tie to the returns: %s. '
                     'An audit flag.' % '; '.join(books))
    # A surprise is a red flag only when it cost money: a big refund (Oyler's
    # equipment and cost segregation) is not one.
    surprise = str(f7.get('Tax surprises') or '')
    if surprise.lower().startswith('yes') and re.search(
            r'\bow(e|ed)\b|penalt|underpa|interest|balance due', surprise, re.I) \
            and not re.search(r'refund', surprise, re.I):
        flags.append('Tax surprises at filing: money owed that was not planned for.')
    out[7] = {'Text 25': 'Opportunity to maximize deductions: meals, travel, '
                         'meetings, the \u201cAugusta Rule\u201d and more.',
              'Text 28': 'A lack of proactive tax advice and planning, so taxes are '
                         'reacted to after the fact instead of managed.'}
    for name, text in zip(('Text 8', 'Text 10', 'Text 12'), flags):
        out[7][name] = text

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
    now_goal = {
        'new_patients': (_pct(lx.get('np_pct')), _pct(lx.get('np_pct_prior'))),
        'per_patient': (M(lx.get('net_per_patient')), M(lx.get('net_per_patient_prior'))),
        'hygiene': ('%g days' % lx['hygiene_days'] if lx.get('hygiene_days') else 'TBD', 'TBD'),
        'fees': ('%.1f%% below' % (100 * lx['fees_off']) if lx.get('fees_off') else 'TBD',
                 'benchmark'),
    }
    for key, label in (('new_patients', 'New patient % of total patients'),
                       ('per_patient', 'Net production/patient'),
                       ('hygiene', 'Hygiene chair-days'),
                       ('fees', 'Increase fees')):
        v = lv[key].get('value')
        if v:
            cur, goal = now_goal.get(key, ('TBD', 'TBD'))
            rows.append((label, cur or 'TBD', goal or 'TBD', v / owner, v))
    rows.sort(key=lambda r: -r[4])
    # Five rows, as the lead advisor shows them. A lever already at goal is still a
    # finding worth a row ("adjustments 5.3%, below where dropping carriers
    # pays"; "fees already above the market"), and it beats an empty line.
    extra = []
    if lx.get('adjust_pct') is not None:
        extra.append(('Production adjustment %', _pct(lx['adjust_pct']),
                      'At goal', 0.0, 0.0))
    try:
        import compose as _compose
        fpct, _t = _compose.fee_study(D.get('folder'))
    except Exception:                                        # noqa: BLE001
        fpct = None
    if fpct is not None and fpct >= 0:
        extra.append(('Fees vs market', '%+.1f%%' % fpct, 'Hold', 0.0, 0.0))
    if lx.get('net_per_patient') and lx.get('net_per_patient_prior') \
            and lx['net_per_patient'] >= lx['net_per_patient_prior']:
        extra.append(('Net production/patient', M(lx['net_per_patient']),
                      'Holding', 0.0, 0.0))
    have = {r[0] for r in rows}
    for r in extra:
        if len(rows) >= 5:
            break
        if r[0] not in have:
            rows.append(r)
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
        rf = _plan.refinance(D.get('practice_debts'))
        n, c = rf['loans'], len(rf['candidates'])

        def rng(v):
            lo, hi = max(0, int(v // 1000)), int(v // 1000) + 2
            return '$%d\u2013%dk/mo' % (lo, hi)
        out[10] = {'Text 3': '%s/mo in payments today' % M(D['debt_service']),
                   'Text 28': '%s/mo' % M(D['debt_service']),
                   'Text 4': 'across the %s practice loans' % (WORDS.get(n, str(n)).lower())}
        if c:
            out[10].update({
                'Text 2': '%s LOANS, %s TO REFINANCE' % (WORDS.get(n, str(n)),
                                                        WORDS.get(c, str(c))),
                'Text 6': 'There are %d practice loans today, and %d of them look '
                          'like candidates for a refinance: %s.'
                          % (n, c, ', '.join(re.sub(r'\s*/.*$', '', str(r.get('creditor')))
                                             for r in rf['candidates'])),
                'Text 8': 'Freed-up income is reallocated to build the practice bank '
                          'account first, then savings.',
                'Text 25': '%d refinance candidate%s of %d' % (c, '' if c == 1 else 's', n),
                'Text 30': rng(rf['payment_new']),
                'Text 33': rng(rf['freed']),
            })
        else:
            out[10]['Text 2'] = '%s LOANS, NONE TO REFINANCE' % WORDS.get(n, str(n))

    # 13 cash flow process: the ideal balance, wherever it appears
    # One month of practice expenses on the most recent reliable overhead,
    # which is the firm's rule (the firm, 21 October): the overhead numerator
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

    # 11 income structure: today's W-2 from the P&L's doctor wages, and the
    # proposed structure worked the way the lead advisor works it
    w2 = N((D.get('facts') or {}).get('Doctor wages'))
    inc = income_structure(D)
    if inc:
        w2 = inc['w2'] * 12
    if w2:
        out.setdefault(11, {})
        out[11].update({'Text 19': '%s/mo' % M(w2 / 12.0),
                        'Text 20': '%s per year' % _k(w2)})
    if inc:
        def neg(v):
            return '(%s)' % M(v)
        k1 = lambda v: '$%.1fk' % (v / 1000.0)            # noqa: E731
        out[11].update({
            'Text 3': '+%s/mo business cashflow' % k1(inc['gain']),
            'Text 4': 'with a new 401(k) in %d' % inc['plan_year'],
            'Text 6': 'Decrease %s\u2019s W-2 (\u2212%s/yr ) and take lower, '
                      'consistent distributions ( \u2212%s/yr ) to have fewer '
                      'tax surprises and smoother cashflow.'
                      % (D['first'], _k(inc['w2_cut'] * 12),
                         _k(inc['dist_cut'] * 12)),
            'Text 10': 'Increase the 401(k) to max with the same match, saving '
                       '%s/yr more. All changes lower taxes over %s/yr.'
                       % (k1(inc['more_saved']), k1(inc['tax_saved'])),
            'Text 12': 'Begin paying distributions to cover custom quarterly '
                       'tax estimates (example on the next slide).',
            'Text 15': 'Personal cashflow stays identical while business '
                       'cashflow grows by +%s/mo.' % k1(inc['gain']),
            'Text 23': neg(inc['def']), 'Text 24': 'Taxes (%d%%)' % round(100 * inc['pct']),
            'Text 25': neg(inc['tax']), 'Text 28': M(inc['net']),
            'Text 31': '%s/mo' % M(inc['dist']),
            'Text 35': '%s/mo' % M(inc['p_w2']),
            'Text 36': '%s per year' % _k(inc['p_w2'] * 12),
            'Text 39': neg(inc['p_def']),
            'Text 40': 'Taxes (%d%%)' % round(100 * inc['p_rate']),
            'Text 41': neg(inc['p_tax']), 'Text 44': M(inc['p_net']),
            'Text 47': '%s/mo' % M(inc['p_dist'])})

    # 14 and 15 investments: how much is locked up, and in what. The lead advisor’s
    # Oyler slides: "94% of retirement savings sits in relatively illiquid
    # private placements"; a bar of Reef IRA 57%, Reef non-qualified 37%,
    # the rest 6%; "7 mutual funds" under the 401(k).
    parts = D.get('start_parts') or []
    tot = sum(a for _l, a in parts) or 0
    binfo = {}
    for key in ('qualified_accounts', 'nonqualified_accounts'):
        for r in (_deck._inputs.value(D.get('folder'), key) or []):
            binfo[str(r.get('label') or '')] = str(r.get('basis') or '')
    ILL = re.compile(r'llc|private|placement|secured note|reef|units', re.I)
    illiquid = [(l, a) for l, a in parts if ILL.search(l + ' ' + binfo.get(l, ''))]
    if tot and parts:
        share = sum(a for _l, a in illiquid) / tot
        out[14] = {'Text 34': 'Readily priced holdings, with full transparency into '
                              'every position.'}
        if share >= 0.3:
            out[14].update({'Text 20': '%d%%' % round(100 * share),
                            'Text 21': 'Of retirement savings sits in relatively '
                                       'illiquid private placements.',
                            'Text 28': 'Limited information on statements. A more '
                                       'fundamental approach brings visibility and '
                                       'control.'})
        funds = [l for l, _a in parts if re.search(r'fund', binfo.get(l, ''), re.I)]
        if funds:
            out[14]['Text 25'] = ('The %s holds mutual funds only. Upgrade to options '
                                  'with lower internal expense and better '
                                  'performance.' % re.sub(r'\s*\[.*?\]', '', funds[0]))
        # the bar on 15: the two largest holdings and the rest
        big = sorted(parts, key=lambda x: -x[1])
        out.setdefault(15, {})
        for (lab, val), (l, a) in zip((('Text 8', 'Text 9'), ('Text 11', 'Text 12')), big[:2]):
            nm = re.sub(r'\s*\[.*?\]', '', l).upper()
            if len(nm) > 22:
                nm = nm[:22].rsplit(' ', 1)[0]
            out[15][lab] = nm.rstrip(' ,;-')
            out[15][val] = '%d%%' % round(100 * a / tot)
        rest = sum(a for _l, a in big[2:])
        out[15]['Text 14'] = '%d%%' % round(100 * rest / tot) if rest else '0%'
        subs = (('Text 25'), ('Text 39'), ('Text 52'))
        for name, (l, _a) in zip(subs, parts):
            b = binfo.get(l, '')
            m = re.search(r'(\w+) funds', b)
            words = {'seven': 7, 'six': 6, 'five': 5, 'four': 4, 'three': 3, 'eight': 8}
            if m:
                n = words.get(m.group(1).lower(), m.group(1))
                out[15][name] = '%s mutual funds' % n
            elif ILL.search(l + ' ' + b):
                out[15][name] = 'private placements'

    # 15 investments current
    if D['start']:
        out.setdefault(15, {}).update({'Text 5': 'WHERE THE %s SITS' % _k(D['start']),
                   'Text 6': '%s total retirement savings' % M(D['start'])})
        acct_rows = [('Text 24', 'Text 27'), ('Text 38', 'Text 41'),
                     ('Text 51', 'Text 53')]
        # What is inside and how liquid, from the Assumptions' own account
        # notes (Oyler: "held across seven funds, 61.5% equities"; "$500,000
        # in LLC interests") rather than left for the advisor to retype.
        basis = {}
        for key in ('qualified_accounts', 'nonqualified_accounts'):
            for r in (_deck._inputs.value(D.get('folder'), key) or []):
                basis[str(r.get('label') or '')] = str(r.get('basis') or '')
        inside = [('Text 29', 'Text 31'), ('Text 43', 'Text 45'),
                  ('Text 54', 'Text 55')]
        for i, (lab, val) in enumerate(acct_rows):
            if i < len(D['slide_parts']):
                l, a = D['slide_parts'][i]
                short = re.sub(r'\s*\[.*?\]', '', l).split(',')[0]
                out[15][lab] = short.upper()[:24]
                out[15][val] = _k(a)
                note = basis.get(l, '')
                note = re.sub(r'^per the most recent \[[^\]]*\] \w+;\s*', '', note)
                if note:
                    out[15][inside[i][0]] = note[0].upper() + note[1:]
                    illiquid = re.search(r'llc|private|placement|note|reef|units',
                                         note + ' ' + l, re.I)
                    out[15][inside[i][1]] = ('Limited liquidity' if illiquid
                                             else 'Daily')
            else:
                out[15][lab], out[15][val] = '[TBD]', '[TBD]'
        # Against 4Q: each account's annualized return (from its statements)
        # less 4Q's over the same dates (asked for on the review page), and
        # what the gap cost: value x gap, summed. The lead advisor's Oyler
        # slide: $69k x 15.64% + ($628k + $408k) x 19.35% = $211.3k, which is
        # +19.11% of the $1.1M.
        rets = D.get('returns') or {}
        vs_cells = [('Text 34', 'Text 35'), ('Text 48', 'Text 49'),
                    (None, 'Text 57')]
        lost, any_gap = 0.0, False
        for i, (cell, sub) in enumerate(vs_cells):
            if i >= len(D['slide_parts']):
                break
            l, a = D['slide_parts'][i]
            r = rets.get(l) or {}
            if r.get('measured_with'):
                r = dict(rets.get(r['measured_with']) or {}, **{
                    k: v for k, v in r.items() if v is not None})
            gap = None
            if r.get('return_pct') is not None and r.get('fq_pct') is not None:
                gap = float(r['return_pct']) - float(r['fq_pct'])
                lost += a * max(0.0, -gap) / 100.0
                any_gap = True
            if cell:
                out[15][cell] = ('%+.2f%%' % gap).replace('-', '\u2212') \
                    if gap is not None else '[TBD]'
            if sub and r.get('period'):
                out[15][sub] = ('measured with the %s, %s'
                                % (re.sub(r'\s*\[.*?\]', '', r['measured_with']).split(',')[0],
                                   r['period'])
                                if (rets.get(l) or {}).get('measured_with')
                                else 'annualized, %s' % r['period'])
        if any_gap:
            pct = 100.0 * lost / D['start']
            out[15].update({
                'Text 3': '$%.1fk left on the table' % (lost / 1000.0),
                'Text 59': '$%.1fk' % (lost / 1000.0),
                'Text 61': 'More %s would have had achieving 4Q\u2019s returns on '
                           'an annualized basis, +%.2f%% more money.'
                           % (D['first'], pct)})

    # 16 savings projection: the advisor's sources; totals from the schedule
    # 16 the savings projection, from the gains: what each is worth a year
    # and the proposed share of it invested. Rows the gains do not fill stay
    # [TBD] for the advisor, and the totals are only printed when every row
    # behind them is filled (the firm's test edit: a total beside [TBD] rows
    # reads as a figure nobody can account for).
    sch = sorted(D['schedule'])
    # Only when the schedule came from these gains: beside an advisor's own
    # schedule they would describe a plan nobody chose.
    later = [g for g in D['gains'] if g.get('year') == 2]
    gl = _slide16_rows([g for g in D['gains'] if g.get('year') != 2])
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
                vals = ['', '', '']
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
                  M(sum(g['gain'] for g in rec)), M(same))]
        if later:
            # The lead advisor's year-two recommendations, as he chose them
            for g in later[:3]:
                rows2.append((g['label'], M(g['gain']) if g['gain'] else '\u2013',
                              M(_plan.invested(g, 1))))
            step = sum(_plan.invested(g, 1) for g in later) + step
        else:
            rows2.append(('Practice improvements, second year', '\u2013', M(step)))
        for i, cells in enumerate(y2):
            vals = rows2[i] if i < len(rows2) else ('', '', '')
            for n, v in zip(cells, vals):
                out[16][n] = v
        out[16]['Text 89'] = M(sum(g['gain'] for g in rec) +
                               sum(g['gain'] or 0 for g in later)) if full else '[TBD]'
        out[16]['Text 91'] = M(same + step) if full else '[TBD]'

    # 17 and 18 the Four Quadrants future
    for slide, which, inc_key in ((17, 'proj', 'income'), (18, 'proj2',
                                                           'income2')):
        p = D.get(which)
        if not p:
            continue
        out.setdefault(slide, {})['Text 4'] = (
            'retirement income' if not D.get('proj2') else
            'retirement income \u00b7 %s practice value'
            % ('smaller' if slide == 17 else 'larger'))
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
            'Text 81': ('Funded to %d at %s/yr.%s' % (
                age_at(ey), M(inc),
                ' Even at the smaller practice value.'
                if slide == 17 and D.get('proj2') else ''))
            if q[ey] > -1000 else
            ('Runs short in %s at %s/yr.' % (_sav.runout_year(
                {k: v for k, v in q.items() if k > ry}) or ey, M(inc))),
            'Text 82': ('Retire at %d, practice%s sell%s in %d.'
                        % (ra, ' and building' if D.get('building') else '',
                           '' if D.get('building') else 's', ry))
            if slide == 17 else
                       'Same savings path, a higher sale price.',
        })
        out[slide].update(fill)
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
    9: 'The overhead goal is 50% (the analyst’s model) unless the advisor sets one. '
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


# The fee slide is set by the lead advisor for each client: left as TBD.
NOT_DRAFTED = {7, 9, 19}   # 7: accounting writes the tax red flags; 9: levers are figures, never drafted


# 401(k) employee limits (2026): base, catch-up at 50, the larger catch-up
# at 60 to 63. The plan year's own limits replace these when published.
K401_BASE, K401_CATCHUP, K401_CATCHUP_60 = 24500, 8000, 11250
PROPOSED_TAX_RATE = 0.40      # the lead advisor's Oyler slide: "Taxes (40%)"
EXTRA_DEFERRAL_TAX = 0.30     # tax saved on the added deferral, his 30%


def income_structure(D):
    """Today's pay and the proposed pay, a month at a time, as on the lead
    advisor's Oyler slide: W-2 down to the next $5,000 a month, the 401(k) to
    the maximum, taxes at 40% of W-2 less the deferral, and distributions set
    so the household takes home exactly what it does today. Every input can
    be overridden in the deck entry (review page). None when a figure is
    missing, and the slide keeps its placeholders."""
    adv = D['adv']
    f = dict(D.get('income_facts') or {})
    for k in ('w2', 'deferral', 'total_tax', 'distributions'):
        if adv.get('income_' + k) is not None:
            f[k] = N(adv['income_' + k])
    if not f.get('w2'):
        f['w2'] = N((D.get('facts') or {}).get('Doctor wages'))
    if not (f.get('w2') and f.get('total_tax') and f.get('distributions')):
        return None
    w2, dfr = f['w2'] / 12.0, (f.get('deferral') or 0) / 12.0
    tax, dist = f['total_tax'] / 12.0, f['distributions'] / 12.0
    net = w2 - dfr - tax
    p_w2 = N(adv.get('income_w2_proposed'))
    p_w2 = p_w2 / 12.0 if p_w2 else None
    if not p_w2:
        p_w2 = (w2 // 5000) * 5000
        if p_w2 >= w2:
            p_w2 = w2 - 2500
    age = (D.get('age') or 0) + 1
    cap = K401_BASE + (K401_CATCHUP_60 if 60 <= age <= 63 else
                       K401_CATCHUP if age >= 50 else 0)
    p_def = max(dfr, N(adv.get('income_deferral_proposed')) or cap) / 12.0 \
        if not adv.get('income_deferral_proposed') else \
        N(adv['income_deferral_proposed']) / 12.0
    rate = N(adv.get('income_tax_rate_proposed')) or PROPOSED_TAX_RATE
    rate = rate / 100.0 if rate > 1 else rate
    p_tax = (p_w2 - p_def) * rate
    p_net = p_w2 - p_def - p_tax
    p_dist = net + dist - p_net
    if p_dist < 0:
        return None
    sch = D.get('schedule') or []
    return dict(w2=w2, **{'def': dfr}, tax=tax, pct=tax / (w2 - dfr),
                net=net, dist=dist, p_w2=p_w2, p_def=p_def, p_rate=rate,
                p_tax=p_tax, p_net=p_net, p_dist=p_dist,
                w2_cut=w2 - p_w2, dist_cut=dist - p_dist,
                gain=(w2 - p_w2) + (dist - p_dist),
                more_saved=(p_def - dfr) * 12,
                tax_saved=(p_def - dfr) * 12 * EXTRA_DEFERRAL_TAX,
                plan_year=sch[0][0] if sch else datetime.date.today().year + 1,
                year=f.get('year'))


def _slide16_rows(gains, slots=6):
    """The year-one rows of the savings slide, at most six, in the order the
    lead advisor lays them out: what is saved today, one-time cash, the
    refinance, the practice levers (folded into one row, as on his slides),
    overhead, then the household's monthly surplus."""
    gl = [g for g in gains or [] if (g.get('gain') or 0) > 0]
    lev = [g for g in gl if g['kind'] == 'practice' and g['key'] != 'overhead']
    if len(lev) > 1:
        folded = dict(key='levers', kind='practice',
                      label=', '.join(g['label'] for g in lev),
                      gain=sum(g['gain'] for g in lev),
                      basis='The practice levers together.')
        folded['invested'] = [sum(_plan.invested(g, i) for g in lev)
                              for i in range(3)]
        gl = [g for g in gl if g not in lev] + [folded]
    order = {'current': 0, 'practice_surplus': 1, 'personal_surplus': 2,
             'refinance': 3, 'levers': 4, 'overhead': 5, 'personal_monthly': 6}
    gl.sort(key=lambda g: order.get(g['key'], 4.5))
    return gl[:slots]


def holes(D, prs, fills, drop):
    """Every box that would otherwise go out as a placeholder, with the slide
    heading and, from the examples file, what that box held in a past deck."""
    try:
        with open(os.path.join(os.path.dirname(TEMPLATE),
                               'deck_examples.json')) as fh:
            examples = json.load(fh)
    except (OSError, ValueError):
        examples = {}
    out = []
    for n, slide in enumerate(prs.slides, 1):
        if n in drop or n in NOT_DRAFTED:
            continue
        default, shapes = SPEC.get(n, ('keep', {}))
        mine = fills.get(n, {})
        texts = [sh.text_frame.text.strip() for sh in slide.shapes
                 if sh.has_text_frame and sh.text_frame.text.strip()]
        heading = ' / '.join(t for t in texts[:2])[:80]
        for sh in slide.shapes:
            if not sh.has_text_frame or not sh.text_frame.text.strip():
                continue
            if sh.name in mine:
                hole = str(mine[sh.name]).startswith(('[ADVISOR', '[TBD'))
            else:
                hole = shapes.get(sh.name, default) == 'advisor'
            if hole:
                out.append({'id': '%d.%s' % (n, sh.name), 'slide': n,
                            'heading': heading.replace('"', "'"),
                            'example': examples.get(
                                '%d.%s' % (n, sh.name)) or '(none)'})
    return out


def dropped(D):
    """Template slides left out for this client."""
    drop = []
    if not D['debt_service']:
        drop.append(10)
    adv = D['adv']
    if not (adv.get('tax_current') and adv.get('tax_split')):
        drop.append(12)
    if not D.get('proj2'):
        drop.append(18)
    return drop


def proposed_wording(folder, D):
    """Claude's drafts for the empty boxes: [{id, slide, heading, example,
    text}]. Used by the review page, where the lead advisor approves them."""
    prs = Presentation(TEMPLATE)
    hs = holes(D, prs, slide_fills(D), dropped(D))
    import deck_drafts
    got = deck_drafts.draft(folder, D, hs)
    return [dict(h, text=got[h['id']]) for h in hs if h['id'] in got]


def _drafts(folder, D, prs, fills, drop):
    """The wording for the empty boxes. Once the lead advisor has reviewed it,
    what he approved (and nothing he dropped); before that, Claude's drafts,
    marked in the notes as not yet reviewed."""
    try:
        with open(os.path.join(folder, '_Audit', 'review_decisions.json')) as fh:
            rev = json.load(fh)
    except (OSError, ValueError):
        rev = {}
    if 'slides' in rev:
        return {k: v for k, v in (rev['slides'] or {}).items() if v}
    if os.environ.get('FQ_NO_DRAFTS'):
        return {}
    try:
        import deck_drafts
    except ImportError:
        return {}
    return deck_drafts.draft(folder, D, holes(D, prs, fills, drop))


def render(folder, client, out, template=TEMPLATE):
    D = figures(folder, client)
    fills = slide_fills(D)
    prs = Presentation(template)
    prompts = 0
    drop = dropped(D)
    adv = D['adv']

    drafts = _drafts(folder, D, prs, fills, drop)

    for n, slide in enumerate(prs.slides, 1):
        default, shapes = SPEC.get(n, ('keep', {}))
        mine = fills.get(n, {})
        asked = []
        drafted = 0
        for sh in slide.shapes:
            if not sh.has_text_frame or not sh.text_frame.text.strip():
                continue
            name = sh.name
            mark = '%d.%s' % (n, name)
            if mark in drafts:
                set_text(sh, drafts[mark].replace('\u2019', "'"))
                _split_label(sh, force=(n == 7))
                drafted += 1
                continue
            if name in mine:
                # The redesign's minus sign and straight apostrophe.
                text = str(mine[name]).replace('-$', '\u2212$').replace(
                    '\u2019', "'")
                if text == '[TBD]':
                    text = 'TBD'
                set_text(sh, text)
                _split_label(sh, force=(n == 7))
                if str(mine[name]).startswith(('[ADVISOR', '[TBD')):
                    placeholder_style(sh, text == 'TBD')
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
                label = 'TBD' if len(was) <= 18 else ask('write this')
                set_text(sh, label)
                placeholder_style(sh, label == 'TBD')
                asked.append(label)
        prompts += len(asked)
        if slide.has_notes_slide and n not in KEEP_NOTES:
            note = NOTES.get(n, '')
            if drafted:
                note += ('\n\nDrafted by Claude from the documents, read '
                         'before the meeting: %d box%s on this slide.'
                         % (drafted, '' if drafted == 1 else 'es'))
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
