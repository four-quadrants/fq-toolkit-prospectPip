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
import store as _store  # noqa: E402
import re
import sys
import copy
import math
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pptx import Presentation                                # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402

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

    def last_two(name, ytd=False):
        vals = ser.get(name) or {}
        ys = [y for y in sorted(vals) if vals.get(y) is not None and y < this_year]
        # A rate the year to date has slipped on (patients a day, production
        # per patient, new patients): the lever is getting it back to last
        # year's, as the lead advisor sized Tanksley ("patients a day back
        # to 10.7", 2025, from 10.2 in 2026 so far).
        if ytd and ys and vals.get(this_year) is not None and vals[this_year] < vals[ys[-1]]:
            return [vals[ys[-1]], vals[this_year]]
        return [vals[y] for y in ys[-2:]] if len(ys) >= 2 else None
    pats = ser.get('patient visits') or {}
    full = [y for y in sorted(pats) if pats.get(y) and y < this_year]
    if full:
        out['patients'] = pats[full[-1]]
    np2 = last_two('new patients % of total', ytd=True)
    if np2:
        out['np_pct_prior'], out['np_pct'] = np2
    pp2 = last_two('net production / patient', ytd=True)
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
    # Patients per doctor day, last year against the year before (the lead
    # advisor's "pat/day" block), with the days and gross per patient that
    # size it.
    ppd = last_two('patients / doctor day', ytd=True)
    if ppd:
        out['pats_per_day_prior'], out['pats_per_day'] = ppd
    for key, name in (('doctor_days_year', 'days worked, all doctors'),
                      ('gross_per_patient', 'gross production / patient')):
        two = last_two(name)
        if two:
            out[key] = two[-1]
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
    # Without the advisor's own wording: "Dr. First Surname" from the
    # documents, never the folder name (which can carry "- TEST" or a due date).
    D['names'] = adv.get('names') or (
        'Dr. %s %s' % (b.forename, b.surname) if b.forename and b.surname else (b.client or client))
    _cd = None
    try:
        _cd = datetime.date.fromisoformat(str(adv.get('consult_date'))[:10]) if adv.get('consult_date') else None
    except ValueError:
        _cd = None
    D['date'] = adv.get('consult_date_text') or \
        (_cd or datetime.date.today()).strftime('%B %-d, %Y')

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
        # Teams write household spending as a month ($27,645) as often as a
        # year; no practice owner's household spends under $60,000 a year.
        if spend and spend < 60000:
            spend = spend * 12
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
    if not D['retire_age']:
        # "ASAP" on the form: the age agreed on the call, as the analyst wrote
        # it in the summary's projection.
        try:
            import json as _json
            import store as _store
            with open(_store.json_path(folder, 'summary.json')) as fh:
                D['retire_age'] = N((_json.load(fh).get('projection') or {}).get('retire_age'))
        except (OSError, ValueError):
            pass
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
    # The checked readings win, as they do on the initial notes: a debt
    # schedule the template reader cannot parse left one deck saying "0
    # loans" against eight on the notes.
    try:
        import doc_readings as _dr
        got = (_dr.check(folder)[0].get('debts') or {}).get('practice')
        if got:
            D['practice_debts'] = [dict(r, description=r.get('what') or r.get('description'))
                                   for r in got]
    except Exception:                                        # noqa: BLE001
        pass
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
    # When the production reader found nothing (a practice whose reports were
    # read by Claude, not a Dentrix export), the by-year figures on the notes
    # still hold collections, production and adjustments for the last full
    # year. They fill only what is missing, so the levers can compute.
    ser = {name: vals for name, vals, _f in b.series}
    this_year = str(datetime.date.today().year)

    def last_full(name):
        vals = ser.get(name) or {}
        ys = [y for y in sorted(vals) if vals.get(y) is not None and y < this_year]
        return vals[ys[-1]] if ys else None
    for key, name, fn in (('collection_pct', 'collection %', None),
                          ('net_production', 'net production', None),
                          ('gross_production', 'gross production', None),
                          ('adjust_pct', 'production adjustment %', abs)):
        v = last_full(name)
        if lx.get(key) is None and v is not None:
            lx[key] = fn(v) if fn else v
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
        D['gains'] = [dict(g, label=g['label'][:1].upper() + g['label'][1:],
                           gain=N(g.get('gain')) or 0,
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
    # A schedule he typed year by year (savings_schedule) still wins: the
    # review page only keeps one when he typed savings years himself.
    if adv.get('gains_table') and not adv.get('savings_schedule'):
        D['schedule'] = []
    D['schedule_derived'] = not D['schedule']
    if not D['schedule'] and D['current_savings']:
        D['schedule'] = _plan.schedule(D['gains'], first_plan_year)
    # Steps the lead advisor typed for particular years (the 401(k) starting
    # in 2030, a profit share in 2039) go on top of the schedule the
    # recommendations build: his Spaulding plan kept rising after year two,
    # and without these the path stayed flat and ran out at 75.
    steps = adv.get('savings_steps') or []
    if steps and D['schedule']:
        merged = dict((int(y), v) for y, v in D['schedule'])
        for y, v in steps:
            if N(v) is not None:
                merged[int(y)] = N(v)
        D['schedule'] = sorted(merged.items())

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
            # When today's path cannot fund today's lifestyle (it runs out),
            # the lead advisor measures against what that path is on pace
            # for instead (Tanksley: $517,000 over $228,000 = +127%).
            'income_up': (_signed(D['income'] / pace - 1)
                          if pace and D.get('spend') and pace < D['spend'] else
                          _signed(D['income'] / D['spend'] - 1) if D.get('spend')
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
    # The accountant's review (carried onto the consult review as tax_flags,
    # tax_deductions and tax_pattern) comes first: those are the findings the
    # tax side presents. The computed flags fill any slot left.
    adv7 = D['adv']
    mine = [str(x) for x in (adv7.get('tax_flags') or []) if str(x).strip()]
    for name, text in zip(('Text 8', 'Text 10', 'Text 12', 'Text 14', 'Text 16'),
                          (mine + [f for f in flags if f not in mine])[:5]):
        out[7][name] = text
    for name, text in zip(('Text 21', 'Text 23', 'Text 25'),
                          [str(x) for x in (adv7.get('tax_deductions') or []) if str(x).strip()]):
        out[7][name] = text
    if adv7.get('tax_pattern'):
        out[7]['Text 30'] = str(adv7['tax_pattern'])
    # Fees, as quoted (the deck entry on the consult review).
    fees = {'Text 25': adv7.get('fee_planning_y1'), 'Text 26': adv7.get('fee_planning_note'),
            'Text 29': adv7.get('fee_planning_y2'), 'Text 36': adv7.get('fee_tax_y1'),
            'Text 37': adv7.get('fee_tax_note'), 'Text 40': adv7.get('fee_tax_y2')}
    fees = {k: str(v) for k, v in fees.items() if v}
    if fees:
        out.setdefault(19, {}).update(fees)

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
        adj_goal = _lev.ADJ_IDEAL_HIGH if lx['adjust_pct'] >= _lev.ADJ_THRESHOLD \
            else lx['adjust_pct'] - 0.10
        rows.append(('Production adjustment %', _pct(lx['adjust_pct']),
                     _pct(adj_goal), lv['adjustment']['value'] / owner,
                     lv['adjustment']['value']))
    if lv['collections'].get('value'):
        rows.append(('Collection %', _pct(lx['collection_pct']), '99.5%',
                     lv['collections']['value'] / owner,
                     lv['collections']['value']))
    now_goal = {
        'new_patients': (_pct(lx.get('np_pct')), _pct(lx.get('np_pct_prior'))),
        'per_patient': (M(lx.get('net_per_patient')), M(lx.get('net_per_patient_prior'))),
        'hygiene': ('%g days' % lx['hygiene_days'] if lx.get('hygiene_days') else 'TBD',
                    (lambda m: ('%s days' % m.group(1)) if m else 'TBD')(
                        re.search(r'to ([\d.]+) chair-days', str((D.get('levers') or {}).get('hygiene', {}).get('basis') or '')))),
        'fees': ('%.1f%% below' % (100 * lx['fees_off']) if lx.get('fees_off') else 'TBD',
                 'benchmark'),
        'pats_per_day': ('%.1f' % lx['pats_per_day'] if lx.get('pats_per_day') else 'TBD',
                         '%.1f' % lx['pats_per_day_prior'] if lx.get('pats_per_day_prior') else 'TBD'),
    }
    for key, label in (('new_patients', 'New patient % of total patients'),
                       ('per_patient', 'Net production/patient'),
                       ('pats_per_day', 'Patients per doctor day'),
                       ('hygiene', 'Hygiene chair-days'),
                       ('fees', 'Increase fees')):
        v = lv[key].get('value')
        if v:
            cur, goal = now_goal.get(key, ('TBD', 'TBD'))
            rows.append((label, cur or 'TBD', goal or 'TBD', v / owner, v))
    # Practice items the lead advisor added on the review page that no lever
    # computes ("current growth trend continues", more hygiene days, an
    # associate change): his figure, with no current/goal to show.
    computed = {'overhead', 'adjustment', 'new_patients', 'fees', 'collections',
                'per_patient', 'hygiene'}
    for g in adv.get('gains_table') or ():
        k = g.get('key') or ''
        if k in computed or k in ('current', 's_corp', 'five_k_rule'):
            continue
        if k not in ('growth_trend', 'per_day', 'associate_change', 'hygiene') \
                and g.get('kind') != 'practice':
            continue
        v = N(g.get('gain'))
        if v:
            lab = g.get('label') or k
            rows.append((lab[:1].upper() + lab[1:], '\u2013', '\u2013', v / owner, v))
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
            # advisor then has no cell to type another lever into. A dash keeps
            # the box without reading as something still to do.
            vals = ['\u2013'] * 5
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
        # The payments on the loans themselves (cards paid in full are not
        # loans), and what they would be after the candidates are combined.
        pay = rf['all_payments'] or D['debt_service']
        after = max(0.0, pay - rf['freed'])

        def rng(v):
            lo, hi = max(0, int(v // 1000)), int(v // 1000) + 2
            return '$%d\u2013%dk/mo' % (lo, hi)

        def name(r):
            # "Patterson Dental (Solea Laser)", not the lender four times.
            cred = re.sub(r'\s*/.*$', '', str(r.get('creditor') or '')).strip()
            what = re.sub(r'\s*\(\d+\)\s*$', '', str(r.get('description') or '')).strip(' )')
            same = sum(1 for x in rf['candidates']
                       if re.sub(r'\s*/.*$', '', str(x.get('creditor') or '')).strip() == cred)
            return '%s (%s)' % (cred, what) if same > 1 and what and what != cred else cred
        recent = 0
        for r in rf['candidates'] + rf['kept']:
            st = r.get('started')
            try:
                d = st if hasattr(st, 'year') else datetime.date.fromisoformat(str(st)[:10])
                if hasattr(d, 'date'):
                    d = d.date()
                if (datetime.date.today() - d).days <= 14 * 31:
                    recent += 1
            except (TypeError, ValueError):
                pass
        out[10] = {'Text 3': '%s/mo in payments today' % M(pay),
                   'Text 28': '%s/mo' % M(pay),
                   'Text 4': 'across the %s practice loans' % (WORDS.get(n, str(n)).lower())}
        if c:
            out[10].update({
                'Text 2': '%s LOANS, %s TO REFINANCE' % (WORDS.get(n, str(n)),
                                                        WORDS.get(c, str(c))),
                'Text 6': 'There are %d practice loans today%s, and %d of them look '
                          'like candidates for a refinance: %s.'
                          % (n, (', %d added in the last 14 months' % recent)
                             if recent >= 2 else '', c,
                             ', '.join(name(r) for r in rf['candidates'])),
                'Text 8': 'Freed-up income is reallocated to build the practice bank '
                          'account first, then savings.',
                'Text 25': '%d refinance candidate%s of %d' % (c, '' if c == 1 else 's', n),
                'Text 30': rng(after),
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
                   'and obtains a fresh line of credit of %s+.' % (
                       _k(N(D['adv'].get('loc_amount'))).replace('.0k', 'k')
                       if D['adv'].get('loc_amount') else b_txt),
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
        k1 = lambda v: '$%.1fk' % (abs(v) / 1000.0)       # noqa: E731
        sg = lambda v: '+' if v >= 0 else '\u2212'         # noqa: E731
        out[11].update({
            'Text 3': '%s%s/mo business cashflow' % (sg(inc['gain']), k1(inc['gain'])),
            'Text 4': 'with a new 401(k) in %d' % inc['plan_year'],
            'Text 6': 'Decrease %s\u2019s W-2 (\u2212%s/yr) and take %s, '
                      'consistent distributions (%s%s/yr) to have fewer '
                      'tax surprises and smoother cashflow.'
                      % (D['first'], _k(inc['w2_cut'] * 12),
                         'lower' if inc['dist_cut'] >= 0 else 'higher',
                         '\u2212' if inc['dist_cut'] >= 0 else '+',
                         _k(abs(inc['dist_cut']) * 12)),
            'Text 10': 'Increase the 401(k) to max with the same match, saving '
                       '%s/yr more. All changes lower taxes over %s/yr.'
                       % (k1(inc['more_saved']), k1(inc['tax_saved'])),
            'Text 12': 'Begin paying distributions to cover custom quarterly '
                       'tax estimates (example on the next slide).',
            'Text 15': 'Personal cashflow stays identical while business '
                       'cashflow grows by %s%s/mo.' % (sg(inc['gain']), k1(inc['gain'])),
            'Text 23': neg(inc['def']), 'Text 24': 'Taxes (%d%%)' % round(100 * inc['pct']),
            'Text 25': neg(inc['tax']), 'Text 28': M(inc['net']),
            'Text 31': '%s/mo' % M(inc['dist']),
            'Text 35': '%s/mo' % M(inc['p_w2']),
            'Text 36': '%s per year' % _k(inc['p_w2'] * 12),
            'Text 39': neg(inc['p_def']),
            'Text 40': 'Taxes (%d%%)' % round(100 * inc['p_rate']),
            'Text 41': neg(inc['p_tax']), 'Text 44': M(inc['p_net']),
            'Text 47': '%s/mo' % M(inc['p_dist'])})

    # 11, with two earners: the lead advisor's Tanksley slide. When the plan
    # sets the spouse's W-2 (income_w2_spouse_proposed), the slide shows the
    # owner's proposed pay on the left and the spouse's on the right, with
    # distributions under the owner and rent taken home under the spouse.
    two = two_earner(D, inc)
    if two:
        def neg2(v):
            return '(%s)' % M(v)
        k2 = lambda v: '$%.1fk' % (abs(v) / 1000.0)        # noqa: E731
        sg2 = lambda v: '+' if v >= 0 else '\u2212'        # noqa: E731
        bullets = [
            'Decrease %s\u2019s W-2 (%s%s/yr), %s %s\u2019s W-2 (%s%s/yr) and raise the tax '
            'withholding: fewer tax surprises and lower quarterlies, if any.'
            % (D['first'], sg2(-two['o_cut']), _k(abs(two['o_cut']) * 12),
               'increase' if two['s_up'] >= 0 else 'decrease', two['spouse'],
               sg2(two['s_up']), _k(abs(two['s_up']) * 12)),
            'Consistent %s/mo distributions%s.' % (_k(two['dist']),
                ('; take %s/mo of the rent home' % _k(two['rent'])) if two['rent'] else ''),
            ('Flip contributions from Roth to traditional 401(k) to maximize tax savings now; '
             'revisit each year with the financial plan.') if two['roth_flip'] else
            'Increase the 401(k) to max with the same match.',
            'Evaluate the 401(k) for a better structure with a new TPA.']
        out[11].update({
            'Text 3': '%s%s/mo personal cashflow' % (sg2(two['gain']), k2(two['gain'])),
            'Text 4': 'with a new 401(k) in %d' % two['plan_year'],
            'Text 6': bullets[0], 'Text 8': bullets[1], 'Text 10': bullets[2], 'Text 12': bullets[3],
            'Text 14': 'MORE AT HOME, SAME IN THE PRACTICE' if two['gain'] >= 0 else 'LESS AT HOME, MORE IN THE PRACTICE',
            'Text 15': 'Personal cashflow %s%s/mo; business cashflow unchanged.%s'
                       % (sg2(two['gain']), k2(two['gain']),
                          (' Save %s/mo of the increase.' % _k(two['save_more']))
                          if two['save_more'] and two['gain'] > 0 else ''),
            'Text 18': '%s GROSS W-2' % D['first'].upper(),
            'Text 19': '%s/mo' % M(two['o_w2']), 'Text 20': '%s per year' % _k(two['o_w2'] * 12),
            'Text 23': neg2(two['o_def']), 'Text 24': 'Taxes (%d%%)' % round(100 * two['rate']),
            'Text 25': neg2(two['o_tax']), 'Text 28': M(two['o_net']),
            'Text 30': 'Distributions', 'Text 31': '%s/mo' % M(two['dist']),
            'Text 34': '%s GROSS W-2' % two['spouse'].upper(),
            'Text 35': '%s/mo' % M(two['s_w2']), 'Text 36': '%s per year' % _k(two['s_w2'] * 12),
            'Text 39': neg2(two['s_def']), 'Text 40': 'Taxes (%d%%)' % round(100 * two['rate']),
            'Text 41': neg2(two['s_tax']), 'Text 44': M(two['s_net']),
            'Text 46': 'Rent taken home' if two['rent'] else ' ',
            'Text 47': ('%s/mo' % M(two['rent'])) if two['rent'] else ' '})

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
        early = sorted(set([y0, y0 + 1, y0 + 2, y0 + 3] + changes))
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


def _rent_home(D):
    """What the building's rent could send home a month: the rent the
    practice pays the owner's building entity, less the building loans, less
    a cushion of a tenth of the rent, rounded down to $1,000 (the lead
    advisor's Tanksley slide: $8,500 rent, about $5,040 of building loans,
    $2,000 taken home). 0 without both figures."""
    f = D.get('facts') or {}
    rent = None
    for key in ('Entity structure', 'Office location'):
        m = re.search(r'\$([\d,]{4,})\s*(?:a month|/mo)', str(f.get(key) or ''))
        if m:
            rent = float(m.group(1).replace(',', ''))
            break
    if not rent:
        return 0, None, None
    pay = 0.0
    try:
        with open(_store.json_path(D['folder'], 'doc_readings.json')) as fh:
            dr = json.load(fh)
        bld = ((dr.get('debts') or {}).get('building')) or []
        got = [N(b.get('payment')) for b in bld if N(b.get('payment'))]
        if got:
            pay = sum(got)
        else:
            for b in bld:
                m = re.findall(r'\$([\d,]+\.\d{2})', str(b.get('description') or ''))
                if m and re.search(r'a month', str(b.get('description') or '')):
                    pay = sum(float(x.replace(',', '')) for x in m)
                    break
    except (OSError, ValueError):
        pass
    if not pay:
        return 0, rent, None
    home = math.floor(max(0.0, rent - pay - 0.1 * rent) / 1000.0) * 1000
    return home, rent, pay


def two_earner(D, inc):
    """The pay slide for a household where both spouses draw a W-2 from the
    practice, worked out from the documents: the spouse's W-2 and deferral
    from the W-2s (income_facts), a proposed spouse W-2 just large enough to
    max the 401(k) after payroll tax (rounded up to $5,000), contributions
    flipped from Roth to traditional when they are Roth today, the rent the
    building can send home, and distributions set so the household takes
    home what it does today before the rent. Every figure can be overridden
    in the deck entry (income_w2_spouse_proposed, income_w2_spouse,
    income_deferral_spouse_proposed, income_distributions_proposed, rent_home,
    roth_to_traditional, savings_increase, spouse_name). None without a
    spouse W-2 or the owner's pay."""
    adv, f = D['adv'], D.get('income_facts') or {}
    s_now_y = N(adv.get('income_w2_spouse')) or N(f.get('spouse_w2'))
    sw = N(adv.get('income_w2_spouse_proposed'))
    if not inc or not (sw or s_now_y):
        return None
    rate = inc['p_rate']
    age = (D.get('age') or 0) + 1
    cap = K401_BASE + (K401_CATCHUP_60 if 60 <= age <= 63 else K401_CATCHUP if age >= 50 else 0)
    if not sw:
        sw = math.ceil(cap * 1.0765 / 5000.0) * 5000 if s_now_y < cap * 1.0765 else s_now_y
    s_w2 = sw / 12.0
    s_def = (N(adv.get('income_deferral_spouse_proposed')) or min(cap, sw)) / 12.0
    s_tax = max(0.0, s_w2 - s_def) * rate
    s_net = s_w2 - s_def - s_tax
    s_now = (s_now_y or 0) / 12.0
    s_now_def = (N(f.get('spouse_deferral')) or 0) / 12.0
    s_now_net = s_now - s_now_def - max(0.0, s_now - s_now_def) * rate
    rent = N(adv.get('rent_home'))
    rent_src = 'entered'
    if rent is None:
        rent, _r, _p = _rent_home(D)
        rent_src = 'derived'
    rent = rent / 12.0 if rent and rent > 60000 else (rent or 0)
    now = inc['net'] + inc['dist'] + s_now_net
    dist = N(adv.get('income_distributions_proposed'))
    if dist:
        dist = dist / 12.0 if dist > 60000 else dist
    else:
        # the household keeps what it takes home today; only the rent is new
        dist = math.ceil(max(0.0, now - inc['p_net'] - s_net) / 500.0) * 500
    new = inc['p_net'] + dist + s_net + rent
    spouse = adv.get('spouse_name') or f.get('spouse_name') or ''
    if not spouse:
        m = re.search(r'&\s*([A-Z][a-z]+)', str(adv.get('names') or ''))
        spouse = m.group(1) if m else 'Spouse'
    flip = adv.get('roth_to_traditional')
    flip = (str(flip).lower() in ('yes', 'true', '1', 'y')) if flip is not None else \
        (str(f.get('deferral_kind') or '').lower() == 'roth')
    return dict(spouse=spouse, rate=rate, o_w2=inc['p_w2'], o_def=inc['p_def'],
                o_tax=inc['p_tax'], o_net=inc['p_net'], o_cut=inc['w2'] - inc['p_w2'],
                s_w2=s_w2, s_def=s_def, s_tax=s_tax, s_net=s_net, s_up=s_w2 - s_now,
                dist=dist, rent=rent, rent_src=rent_src, gain=new - now, roth_flip=flip,
                save_more=N(adv.get('savings_increase')) or 0, plan_year=inc['plan_year'])


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
    # A spouse on the practice payroll shares the household's tax bill: the
    # owner's part is the owner's share of the two W-2s, so neither is
    # charged the whole return.
    sw_y = N(adv.get('income_w2_spouse')) or N(f.get('spouse_w2'))
    if sw_y:
        own_t = max(0.0, f['w2'] - (f.get('deferral') or 0) if str(f.get('deferral_kind') or '').lower() == 'roth'
                    else f['w2'])
        sp_t = max(0.0, sw_y)
        tax = tax * own_t / (own_t + sp_t) if (own_t + sp_t) else tax
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
    # The proposed tax rate: the advisor's, else the rate this household
    # actually pays now (its return) when that is lower, else the firm's 40%. A flat 40% on a
    # household whose rental losses bring it to 18% made the new structure
    # look like it cost $5,500 a month.
    # The lower of the two: total tax over W-2 runs far above 40% when the
    # return also carries distributions (Oyler, 72%), and there the firm's
    # 40% stands.
    cur = tax / (w2 - dfr) if (w2 - dfr) > 0 else None
    rate = N(adv.get('income_tax_rate_proposed')) or (
        min(cur, PROPOSED_TAX_RATE) if cur else PROPOSED_TAX_RATE)
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
    # How you get paid: a sole proprietor (Schedule C) has no W-2 and no
    # distributions to restructure, so the slide has nothing to say.
    if not income_structure(D) and not (D.get('income_facts') or {}).get('w2') \
            and not (D.get('facts') or {}).get('Doctor wages'):
        drop.append(11)
    # Account by account needs the investment statements (holdings and a
    # return per account). With only balances on file the slide would be
    # sixteen blanks; it comes back by itself once statements are read, or
    # the lead advisor can force it on the consult review.
    if not any((v or {}).get('return_pct') is not None
               for v in (D.get('returns') or {}).values()):
        drop.append(15)
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
        with open(_store.json_path(folder, 'review_decisions.json')) as fh:
            rev = json.load(fh)
    except (OSError, ValueError):
        rev = {}
    reviewed = rev.get('slides') if 'slides' in rev else None
    if reviewed:
        # What he approved or rewrote wins; a box he cleared stays empty;
        # the boxes he never touched keep the draft rather than a blank.
        drafted = {}
        if not os.environ.get('FQ_NO_DRAFTS'):
            try:
                import deck_drafts
                drafted = deck_drafts.draft(folder, D, holes(D, prs, fills, drop))
            except ImportError:
                drafted = {}
        out = dict(drafted)
        for k, v in reviewed.items():
            if v:
                out[k] = v
            else:
                out.pop(k, None)
        return out
    if os.environ.get('FQ_NO_DRAFTS'):
        return {}
    try:
        import deck_drafts
    except ImportError:
        return {}
    return deck_drafts.draft(folder, D, holes(D, prs, fills, drop))


# The concern cards on slide 3: (card, bar, heading, body) by shape name.
_CARDS = [('Shape 5', 'Shape 6', 'Text 7', 'Text 8'),
          ('Shape 9', 'Shape 10', 'Text 11', 'Text 12'),
          ('Shape 13', 'Shape 14', 'Text 15', 'Text 16'),
          ('Shape 17', 'Shape 18', 'Text 19', 'Text 20'),
          ('Shape 21', 'Shape 22', 'Text 23', 'Text 24')]


def _layout_concerns(slide, n):
    """Lay the concern cards out for how many there are, and stop the text
    shrinking to fit.

    The template is three cards over two. With four concerns the fifth card
    sat empty with its placeholders showing, and PowerPoint's shrink-to-fit
    gave every card a different text size (Spaulding, 2 Nov: a heading
    running past its card, one body at half the size of the others). Four
    become a two-by-two grid, three one tall row; every heading and body
    keeps the template's size and the boxes are sized to their card.
    """
    from pptx.util import Pt
    from lxml import etree
    A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
    by = {sh.name: sh for sh in slide.shapes}
    if n >= 5 or n < 3:
        boxes = [(48, 122, 438, 269), (501, 122, 438, 269), (954, 122, 438, 269),
                 (48, 404, 664, 269), (728, 404, 664, 269)]
    elif n == 4:
        boxes = [(48, 122, 664, 269), (728, 122, 664, 269),
                 (48, 404, 664, 269), (728, 404, 664, 269)]
    else:
        boxes = [(48, 122, 438, 551), (501, 122, 438, 551), (954, 122, 438, 551)]
    for i, names in enumerate(_CARDS):
        shapes = [by.get(x) for x in names]
        if i >= len(boxes):
            for sh in shapes:
                if sh is not None:
                    sh._element.getparent().remove(sh._element)
            continue
        x, y, w, h = boxes[i]
        card, bar, head, body = shapes
        if card is not None:
            card.left, card.top, card.width, card.height = Pt(x), Pt(y), Pt(w), Pt(h)
        if bar is not None:
            bar.left, bar.top, bar.width = Pt(x), Pt(y), Pt(w)
            # One accent colour across the cards once they are re-laid out
            # (the template's bottom row is blue, its top row orange).
            first = by.get(_CARDS[0][1])
            if n in (3, 4) and first is not None and bar is not first:
                try:
                    bar.fill.solid()
                    bar.fill.fore_color.rgb = first.fill.fore_color.rgb
                except Exception:                            # noqa: BLE001
                    pass
        long_head = head is not None and len(head.text_frame.text) * 12.5 > (w - 44)
        if head is not None:
            head.left, head.top = Pt(x + 22), Pt(y + 25)
            head.width, head.height = Pt(w - 44), Pt(66 if long_head else 36)
        if body is not None:
            top = y + (100 if long_head else 68)
            body.left, body.top = Pt(x + 22), Pt(top)
            body.width, body.height = Pt(w - 44), Pt(y + h - top - 18)
        for sh in (head, body):
            if sh is None:
                continue
            sh.text_frame.word_wrap = True
            bp = sh.text_frame._txBody.find(A + 'bodyPr')
            for old in list(bp):
                if old.tag in (A + 'normAutofit', A + 'spAutoFit', A + 'noAutofit'):
                    bp.remove(old)
            etree.SubElement(bp, A + 'noAutofit')


# ---- slides the lead advisor removed or added on the consult review --------

# Layouts a new slide can take, each built from a template slide so it keeps
# the deck's look: (template slide, shapes kept for the layout).
_POINT_CARDS = [('Shape 5', 'Shape 6', 'Text 7', 'Text 8'),
                ('Shape 9', 'Shape 10', 'Text 11', 'Text 12'),
                ('Shape 13', 'Shape 14', 'Text 15', 'Text 16'),
                ('Shape 17', 'Shape 18', 'Text 19', 'Text 20'),
                ('Shape 21', None, 'Text 22', 'Text 23'),
                ('Shape 24', 'Shape 25', 'Text 26', 'Text 27'),
                ('Shape 28', 'Shape 29', 'Text 30', 'Text 31')]
_FIG_TILES = [('Shape 4', 'Shape 5', 'Text 6', 'Text 7'),
              ('Shape 8', 'Shape 9', 'Text 10', 'Text 11'),
              ('Shape 12', None, 'Text 13', 'Text 14')]
LAYOUTS = {'points': 13, 'statement': 13, 'figures': 4, 'columns': 4,
           'compare': 4, 'steps': 6, 'two': 13, 'statement_points': 13, 'accounts': 15}
# Names and one-line descriptions, for the review page's layout picker.
LAYOUT_INFO = [
    ('points', 'Numbered points', 'Two to six points in numbered cards that fill the slide'),
    ('statement', 'Statement', 'One or two sentences, large, on a dark card'),
    ('statement_points', 'Statement and three points', 'A headline on the dark card, three numbered points under it'),
    ('figures', 'Three figures', 'Three big numbers, each with a label and a line of explanation'),
    ('columns', 'Three columns', 'Three tall cards, each a heading and a few lines'),
    ('two', 'Today and with 4Q', 'Two tall cards side by side, a few lines each'),
    ('compare', 'Side-by-side table', 'Up to three rows: what it is, today, with Four Quadrants'),
    ('steps', 'Steps', 'Up to five steps across a dark band, each a heading and a short line'),
    ('accounts', 'Detailed table', 'Three rows by five columns (like the account-by-account slide), with a takeaway band'),
]
# The account-by-account slide's table: per row (name, sub-line, then the
# four columns, the last one's sub-line).
_ACC_ROWS = [('Text 24', 'Text 25', 'Text 27', 'Text 29', 'Text 31', 'Text 34', 'Text 35'),
             ('Text 38', 'Text 39', 'Text 41', 'Text 43', 'Text 45', 'Text 48', 'Text 49'),
             ('Text 51', 'Text 52', 'Text 53', 'Text 54', 'Text 55', 'Text 57', None)]
_ACC_HEADS = ('Text 17', 'Text 18', 'Text 19', 'Text 20', 'Text 21')
_CMP_ROWS = [('Text 21', 'Text 23', 'Text 26'), ('Text 28', 'Text 30', 'Text 33'),
             ('Text 34', 'Text 35', 'Text 37')]
_CMP_SHAPES = ['Shape %d' % i for i in (15, 16, 20, 22, 24, 25, 27, 29, 31, 32, 36, 38, 39)] + \
    ['Text %d' % i for i in (17, 18, 19, 21, 23, 26, 28, 30, 33, 34, 35, 37, 40, 41)]
_STEP_COLS = [('Shape 68', 'Text 69', 'Text 70'), ('Shape 71', 'Text 72', 'Text 73'),
              ('Shape 74', 'Text 75', 'Text 76'), ('Shape 77', 'Text 78', 'Text 79'),
              ('Shape 80', 'Text 81', 'Text 82')]
# The content area every layout fills, in points: below the header rule.
TOP, BOTTOM, LEFT, WIDTH, GAP = 121, 786, 48, 1344, 16


def deck_edits(folder):
    """{'removed': [template slide numbers], 'added': [new slides]} from
    the consult review, or empty."""
    try:
        with open(_store.json_path(folder, 'review_decisions.json')) as fh:
            got = json.load(fh).get('deck_slides') or {}
    except (OSError, ValueError):
        got = {}
    return {'removed': [int(n) for n in got.get('removed') or ()],
            'forced': [int(n) for n in got.get('forced') or ()],
            'added': [a for a in got.get('added') or () if a.get('title') or a.get('items') or a.get('body')]}


def _clone(prs, src):
    """A copy of slide `src` at the end of the deck, shapes, background and
    pictures included."""
    new = prs.slides.add_slide(src.slide_layout)
    for sh in list(new.shapes):
        sh._element.getparent().remove(sh._element)
    rid_map = {}
    for rid, rel in src.part.rels.items():
        if rel.is_external or 'notesSlide' in rel.reltype or 'slideLayout' in rel.reltype:
            continue
        rid_map[rid] = new.part.relate_to(rel._target, rel.reltype)
    tree = new.shapes._spTree
    for el in src.shapes._spTree.iterchildren():
        if el.tag.endswith('}nvGrpSpPr') or el.tag.endswith('}grpSpPr'):
            continue
        c = copy.deepcopy(el)
        for node in c.iter():
            for k, v in list(node.attrib.items()):
                if k.endswith('}embed') or k.endswith('}link') or k.endswith('}id'):
                    if v in rid_map:
                        node.set(k, rid_map[v])
        tree.append(c)
    bg = src._element.cSld.bg
    if bg is not None:
        new._element.cSld.insert(0, copy.deepcopy(bg))
    return new


def _shape(slide, name):
    for sh in slide.shapes:
        if sh.name == name:
            return sh
    return None


def _remove(slide, *names):
    for n in names:
        sh = _shape(slide, n) if n else None
        if sh is not None:
            sh._element.getparent().remove(sh._element)


def _font(shape, size=None, bold=None):
    for para in shape.text_frame.paragraphs:
        for r in para.runs:
            if size:
                r.font.size = size
            if bold is not None:
                r.font.bold = bold


def _box(shape, left, top, width, height):
    from pptx.util import Pt
    shape.left, shape.top, shape.width, shape.height = Pt(left), Pt(top), Pt(width), Pt(height)


def _anchor(shape, how='middle'):
    from pptx.enum.text import MSO_ANCHOR
    shape.text_frame.word_wrap = True
    shape.text_frame.vertical_anchor = {'middle': MSO_ANCHOR.MIDDLE, 'top': MSO_ANCHOR.TOP}[how]


def _lines(text_or_list):
    if isinstance(text_or_list, (list, tuple)):
        return [x.strip() for x in text_or_list if x and str(x).strip()]
    return [x.strip() for x in str(text_or_list or '').split('\n') if x.strip()]


def _dup(slide, shape):
    """A copy of a shape on the same slide (for a text line a layout needs
    more of than the template slide has)."""
    el = copy.deepcopy(shape._element)
    shape._element.addnext(el)
    return [sh for sh in slide.shapes if sh._element is el][0]


def _point_cards(s, items, top, bottom):
    """Numbered cards, two to a row, filling top..bottom; an odd last card
    runs the full width. Uses the barred cards of the cashflow slide."""
    from pptx.util import Pt
    groups = [g for g in _POINT_CARDS if g[1]]          # the cards with an accent bar
    items = items[:len(groups)]
    n = len(items)
    rows = (n + 1) // 2 if n > 1 else 1
    h = (bottom - top - GAP * (rows - 1)) / float(rows)
    half = (WIDTH - GAP) / 2.0
    size = Pt(36 if n <= 2 else 30 if n <= 4 else 26)
    for i, (card, bar, num, txt) in enumerate(groups):
        if i >= n:
            _remove(s, card, bar, num, txt)
            continue
        r, c = divmod(i, 2)
        full = (n == 1) or (i == n - 1 and n % 2 == 1)
        x = LEFT if (full or c == 0) else LEFT + half + GAP
        w = WIDTH if full else half
        y = top + r * (h + GAP)
        _box(_shape(s, card), x, y, w, h)
        _box(_shape(s, bar), x, y, 5, h)
        set_text(_shape(s, num), '%02d' % (i + 1))
        _box(_shape(s, num), x + 24, y, 80, h)
        _anchor(_shape(s, num))
        _font(_shape(s, num), Pt(34))
        set_text(_shape(s, txt), items[i])
        _box(_shape(s, txt), x + 110, y + 10, w - 134, h - 20)
        _anchor(_shape(s, txt))
        _font(_shape(s, txt), size)


DD_ORANGE, DD_BLUE, DD_DARK, DD_TEXT, DD_MUTED = 'E8730C', '1F6FB2', '3A3F45', '4A5056', '8A9098'
DD_GREY, DD_GREY2, DD_GREY3, DD_LINE = 'A8AEB4', 'C9CDD1', 'DCDCDC', 'E3E1DE'


def _dd_rect(s, x, y, w, h, fill, line=None):
    from pptx.util import Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    r = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Pt(x), Pt(y), Pt(max(w, 0.5)), Pt(max(h, 0.5)))
    r.fill.solid()
    r.fill.fore_color.rgb = RGBColor.from_string(fill)
    if line:
        r.line.color.rgb = RGBColor.from_string(line)
        r.line.width = Pt(0.75)
    else:
        r.line.fill.background()
    r.shadow.inherit = False
    return r


def _dd_text(s, x, y, w, h, runs, size=16, align='l', anchor='top', font='Barlow', spacing=None, lines=None):
    """A text box. runs: [(text, colour, bold)] for one paragraph, or a list
    of such lists for several paragraphs."""
    from pptx.util import Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    tb = s.shapes.add_textbox(Pt(x), Pt(y), Pt(w), Pt(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = {'top': MSO_ANCHOR.TOP, 'middle': MSO_ANCHOR.MIDDLE, 'bottom': MSO_ANCHOR.BOTTOM}[anchor]
    paras = runs if runs and isinstance(runs[0], list) else [runs]
    for i, pr in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = {'l': PP_ALIGN.LEFT, 'r': PP_ALIGN.RIGHT, 'c': PP_ALIGN.CENTER}[align]
        if lines:
            p.space_after = Pt(lines)
        for text, col, bold in pr:
            r = p.add_run()
            r.text = text
            r.font.size = Pt(size)
            r.font.bold = bool(bold)
            r.font.name = font
            r.font.color.rgb = RGBColor.from_string(col)
            if spacing:
                r.font._element.set('spc', str(int(spacing * 100)))
    return tb


def _dd_head(s, x, y, w, text, col=DD_ORANGE, size=24):
    return _dd_text(s, x, y, w, 30, [((text or '').upper(), col, True)], size=size,
                    font='Barlow Condensed', spacing=1.5)


def _dd_pct(v):
    try:
        return float(re.sub(r'[^0-9.]', '', str(v)) or 0)
    except ValueError:
        return 0.0


def _bold_split(text, col, boldcol=None):
    """**bold** inside a line of text, as runs."""
    out = []
    for i, part in enumerate(re.split(r'\*\*', text or '')):
        if part:
            out.append((part, (boldcol or DD_DARK) if i % 2 else col, bool(i % 2)))
    return out or [(' ', col, False)]


def current_path_data(D):
    """The current-path slide, as the lead advisor added it to Tanksley
    (and 15 of the 34 decks the team made in 2024 to 2026): today's savings
    and spending carried forward, when the money runs out, and how much of
    retirement rests on the practice sale. None without a projection."""
    p = D.get('proj')
    if not p or not D.get('spend'):
        return None
    cur, dep = p['current'], p['current_deposits']
    y0, ry, ey = p['first_year'], p['retire_year'], p['end_year']
    run = p.get('runout_year')
    cy = int(str(D['adv'].get('consult_date') or datetime.date.today().isoformat())[:4])
    age = (lambda y: int(D['age']) + (y - cy)) if D.get('age') else (lambda y: '')
    spend = D['spend']
    exp = lambda y: spend * (1 + _sav.INFLATION) ** (y - y0)    # noqa: E731
    last = run if run else ey
    sale = D.get('sale') or 0
    share = p.get('sale_share_of_portfolio')
    rows = [[str(age(y0)), str(y0), M(dep.get(y0, 0)), M(cur[y0]), M(exp(y0)), ''],
            [str(age(ry)), str(ry), M(dep.get(ry, 0)), M(cur[ry]), M(exp(ry)),
             ('*practice%s sell %s net%s' % (' & bldg' if D.get('building') else '', _k(sale),
                                             (' (%d%% of the portfolio)' % round(share * 100)) if share else ''))
             if sale else ''],
            [str(age(last)), str(last), '$0', M(cur.get(last, 0)), M(exp(last)), '']]
    pace, first = p.get('on_pace_for'), D['first']
    if run:
        band = 'Funds run out at %s (%d) at today’s lifestyle%s' % (
            age(run), run, (': on pace for %s/yr, %d%% of today.' % (M(pace), round(100 * pace / spend)))
            if pace else '.')
    else:
        band = 'Today’s path lasts to %s at today’s lifestyle.' % age(ey)
    keys = ['Current portfolio %s, investing %s/yr until retirement at %s'
            % (M(D.get('start')), M(D.get('current_savings')),
               int(D['retire_age']) if D.get('retire_age') else 'retirement'),
            ('Practice%s sale in %d: %s net after taxes and debt payoff%s'
             % (' and building' if D.get('building') else '', ry, _k(sale),
                (' (%d%% of the portfolio then)' % round(share * 100)) if share else '')) if sale else None,
            'Retirement expenses held at today’s lifestyle (%s/yr), grown with inflation' % M(spend),
            ('At %s, %d years before the funds run out at the current lifestyle' % (age(ry), run - ry))
            if run else None]
    return {'layout': 'current_path', 'after': 15, 'id': 'current_path',
            'eyebrow': 'Current retirement strategy', 'title': 'Where today’s path leads',
            'note': '%s/yr' % M(spend), 'sub': 'today’s expenses, saving %s/yr' % M(D.get('current_savings')),
            'who': '%s AGE' % first.upper(), 'rows': rows, 'keys': [k for k in keys if k], 'band': band}


def _current_path(prs, a):
    """Built from the savings-future slide: three rows (now, retirement, when
    the money runs out), a key factors panel, the band."""
    from pptx.util import Pt
    src = prs.slides[17 - 1]
    s = _clone(prs, src)
    by = {sh.name: sh for sh in s.shapes}
    E = 12700
    set_text(by['Text 1'], a['eyebrow'].upper())
    set_text(by['Text 2'], a['title'].upper())
    if 'Text 3' in by:
        set_text(by['Text 3'], a['note'])
    if 'Text 4' in by:
        set_text(by['Text 4'], a['sub'])
    set_text(by['Text 7'], a['who'])
    if 'Text 10' in by:
        set_text(by['Text 10'], 'YEAR-END PORTFOLIO (%s NET)' % ('8.5%'))
    if 'Text 11' in by:
        set_text(by['Text 11'], 'RETIREMENT EXPENSES')
    # rows: the first grid row, the retirement row, the last row
    r0 = ('Text 14', 'Text 16', 'Text 18', 'Text 20', 'Text 22')
    r1 = ('Text 59', 'Text 62', 'Text 65', 'Text 68', 'Text 71')
    r2 = ('Text 75', 'Text 76', 'Text 77', 'Text 78', 'Text 79')
    for names, vals in zip((r0, r1, r2), a['rows']):
        for n, v in zip(names, vals):
            if n in by:
                set_text(by[n], v)
    if 'Text 74' in by:
        set_text(by['Text 74'], a['rows'][1][5] or ' ')
    for n in [f'Shape {i}' for i in range(24, 57)] + [f'Text {i}' for i in range(24, 57)] + ['Text 82']:
        if n in by:
            by[n]._element.getparent().remove(by[n]._element)
    for i in list(range(57, 80)):
        for pre in ('Shape ', 'Text '):
            sh = by.get(pre + str(i))
            if sh is not None:
                sh.top = sh.top - Pt(270)
    by['Shape 5'].height = Pt(433 - 118)
    if 'Text 81' in by:
        by['Text 81'].width = Pt(1300)
        set_text(by['Text 81'], a['band'])
    # key factors panel
    els = [copy.deepcopy(by[n]._element) for n in ('Shape 5', 'Shape 6', 'Text 7', 'Text 74')]
    for el in els:
        s.shapes._spTree.append(el)
    fr, bd, hd, bo = list(s.shapes)[-4:]
    fr.top, fr.height = Pt(448), Pt(708 - 448)
    bd.top = Pt(448)
    hd.top, hd.width = Pt(459), Pt(600)
    set_text(hd, 'KEY FACTORS')
    bo.left, bo.top, bo.width, bo.height = Pt(63), Pt(502), Pt(1310), Pt(200)
    set_text(bo, '\n'.join('•  ' + k for k in a['keys']))
    bp = bo.text_frame._txBody.bodyPr
    for el in list(bp):
        if el.tag.endswith('normAutofit'):
            bp.remove(el)
    bp.set('anchor', 't')
    from pptx.dml.color import RGBColor
    for para in bo.text_frame.paragraphs:
        para.space_after = Pt(10)
        for r in para.runs:
            r.font.size = Pt(20)
            r.font.color.rgb = RGBColor.from_string('4A5056')
    return s


def _deep_dive(prs, a):
    """The deeper investments slide: what the money is actually in. Left: the
    invested equity by sector (bars) and how the steerable sleeve splits
    (cash, equity, bonds). Right: the concentration callout, the holdings
    that recur across funds, and the share nobody can see into. A dark band
    with the one-line takeaway."""
    s = _clone(prs, prs.slides[LAYOUTS['points'] - 1])
    header = {'Shape 0', 'Text 1', 'Text 2'}
    _remove(s, *[sh.name for sh in list(s.shapes) if sh.name not in header])
    set_text(_shape(s, 'Text 1'), (a.get('eyebrow') or 'Investments').upper())
    title, accent = (a.get('title') or 'A deeper look').upper(), (a.get('title_accent') or '').upper()
    t = _shape(s, 'Text 2')
    set_text(t, title)
    if accent and title.endswith(accent):
        from pptx.dml.color import RGBColor
        para = t.text_frame.paragraphs[0]
        r0 = para.runs[0]
        r0.text = title[:-len(accent)]
        r1 = copy.deepcopy(r0._r)
        r0._r.addnext(r1)
        para.runs[1].text = accent
        para.runs[1].font.color.rgb = RGBColor.from_string(DD_ORANGE)
    t.width = _shape(s, 'Text 1').width = __import__('pptx.util', fromlist=['Pt']).Pt(860)
    if a.get('note'):
        _dd_text(s, 930, 38, 462, 30, [(a['note'], DD_DARK, True)], size=26, align='r', font='Barlow Condensed')
    if a.get('sub'):
        _dd_text(s, 830, 70, 562, 22, [(a['sub'], DD_MUTED, False)], size=15, align='r')

    L, LW, R, RW = 48, 760, 838, 554
    # Left: sector bars
    _dd_head(s, L, 126, 520, a.get('bars_head') or 'Where the invested equity sits')
    if a.get('bars_note'):
        _dd_text(s, L + 540, 130, LW - 540, 40, [(a['bars_note'], DD_MUTED, False)], size=16)
    bars = [b for b in (a.get('bars') or []) if b and b[0]][:8]
    top = 176
    rowh = min(52, (548 - top) / float(max(len(bars), 1)))
    mx = max([_dd_pct(b[1]) for b in bars] + [1])
    cols = [DD_ORANGE, DD_BLUE, DD_GREY, DD_GREY, DD_GREY2, DD_GREY2, DD_GREY2, DD_GREY3]
    for i, b in enumerate(bars):
        y = top + i * rowh
        last = i == len(bars) - 1 and len(bars) == 8
        _dd_text(s, L, y, 560, 22, [(b[0], DD_MUTED if last else DD_DARK, not last)], size=19)
        _dd_rect(s, L, y + 25, 560 * _dd_pct(b[1]) / mx, 18, cols[i])
        vc = DD_ORANGE if i == 0 else DD_BLUE if i == 1 else DD_MUTED
        _dd_text(s, L + 580, y + 12, LW - 580, 32, [(b[1], vc, i < 2)], size=30 if i < 2 else 24,
                 align='r', font='Barlow Condensed', anchor='middle')
    # Left bottom: how the sleeve splits
    cy = 572
    _dd_rect(s, L, cy, LW, 214, 'FFFFFF')
    _dd_rect(s, L, cy, 5, 214, DD_ORANGE)
    _dd_head(s, L + 26, cy + 22, LW - 50, a.get('mix_head') or 'How the sleeve splits')
    mix = [m for m in (a.get('mix') or []) if m and m[0]][:4]
    tot = sum(_dd_pct(m[1]) for m in mix) or 1
    x, mcol = L + 26, [(DD_ORANGE, 'FFFFFF'), (DD_BLUE, 'FFFFFF'), (DD_GREY2, DD_DARK), (DD_GREY3, DD_DARK)]
    for i, m in enumerate(mix):
        w = (LW - 52) * _dd_pct(m[1]) / tot
        _dd_rect(s, x, cy + 72, w, 38, mcol[i][0])
        _dd_text(s, x, cy + 72, w, 38, [(('%s %s' % (m[0], m[1])).upper(), mcol[i][1], True)], size=21,
                 align='c', anchor='middle', font='Barlow Condensed', spacing=1)
        x += w
    if a.get('mix_note'):
        _dd_text(s, L + 26, cy + 128, LW - 52, 70, _bold_split(a['mix_note'], DD_TEXT), size=20)

    # Right: the concentration callout
    y = 126
    _dd_rect(s, R, y, RW, 124, 'FFFFFF')
    _dd_rect(s, R, y, RW, 4, DD_BLUE)
    _dd_text(s, R + 22, y + 18, RW - 44, 30, [((a.get('card_head') or '').upper(), DD_DARK, True)], size=26,
             font='Barlow Condensed')
    _dd_text(s, R + 22, y + 54, RW - 44, 64, _bold_split(a.get('card_body') or '', DD_TEXT), size=19)
    # Right: the holdings that recur
    y = 264
    rows = [r for r in (a.get('recur_rows') or []) if r and r[0]][:6]
    hgt = 82 + 27 * len(rows) + (30 if a.get('recur_note') else 0)
    _dd_rect(s, R, y, RW, hgt, 'FFFFFF', DD_LINE)
    _dd_text(s, R + 22, y + 16, RW - 44, 26, [((a.get('recur_head') or '').upper(), DD_ORANGE, True)],
             size=24, font='Barlow Condensed')
    if a.get('recur_sub'):
        _dd_text(s, R + 22, y + 44, RW - 44, 20, [(a['recur_sub'], DD_MUTED, False)], size=16)
    for i, r in enumerate(rows):
        _dd_text(s, R + 22, y + 70 + 27 * i, 90, 26, [(r[0], DD_DARK, True)], size=19)
        _dd_text(s, R + 112, y + 70 + 27 * i, RW - 134, 26, [(r[1] if len(r) > 1 else '', DD_MUTED, False)], size=19)
    if a.get('recur_note'):
        _dd_text(s, R + 22, y + hgt - 34, RW - 44, 26, [(a['recur_note'], DD_GREY, False)], size=17)
    # Right: what nobody can see
    y = y + hgt + 22
    _dd_head(s, R, y, RW, a.get('zoom_head') or '')
    z = [p for p in (a.get('zoom') or []) if p and p[0]][:2]
    ztot = sum(_dd_pct(p[1]) for p in z) or 1
    x = R
    for i, p in enumerate(z):
        w = RW * _dd_pct(p[1]) / ztot
        _dd_rect(s, x, y + 40, w, 40, DD_BLUE if i == 0 else DD_GREY)
        _dd_text(s, x, y + 40, w, 40, [(p[0].upper(), 'FFFFFF', True)], size=20, align='c', anchor='middle',
                 font='Barlow Condensed', spacing=1)
        x += w
    if a.get('zoom_body'):
        _dd_text(s, R, y + 92, RW, 110, _bold_split(a['zoom_body'], DD_TEXT), size=17)
    # The takeaway band
    band = a.get('band') or ['', '']
    _dd_rect(s, R, 730, RW, 56, DD_DARK)
    _dd_text(s, R + 18, 730, RW - 36, 56, [(band[0] + ' ', 'FFFFFF', True), (band[1] if len(band) > 1 else '', 'F5A25D', True)],
             size=24, anchor='middle', font='Barlow Condensed')
    return s


def _added_slide(prs, a):
    """Build one added slide from its layout. Returns the new slide. Every
    layout fills the content area; nothing is left as empty page."""
    from pptx.util import Pt
    if a.get('layout') == 'deep_dive':
        return _deep_dive(prs, a)
    if a.get('layout') == 'current_path':
        return _current_path(prs, a)
    layout = a.get('layout') if a.get('layout') in LAYOUTS else 'points'
    s = _clone(prs, prs.slides[LAYOUTS[layout] - 1])
    eyebrow = (a.get('eyebrow') or '').strip().upper()
    title = (a.get('title') or '').strip().upper() or 'TITLE'
    cap = (a.get('note') or '').strip()
    set_text(_shape(s, 'Text 1'), eyebrow or ' ')
    set_text(_shape(s, 'Text 2'), title)
    for nm in ('Text 1', 'Text 2'):
        _shape(s, nm).width = Pt(900 if cap else 1340)
    header = {'Shape 0', 'Text 1', 'Text 2'}

    def caption(name):
        # The small line at the top right, when he gives one.
        sh = _shape(s, name)
        if cap and sh is not None:
            set_text(sh, cap)
            _box(sh, 1000, 58, 392, 26)
            return {name}
        return set()

    if layout in ('figures', 'columns'):
        keep = header | caption('Text 3')
        tiles = _FIG_TILES
        data = (a.get('figures') if layout == 'figures' else a.get('columns')) or []
        data = [list(d) + ['', '', ''] for d in data if any((x or '').strip() for x in d)][:3]
        n = max(1, len(data))
        w = (WIDTH - GAP * (n - 1)) / float(n)
        for i, (card, bar, big, small) in enumerate(tiles):
            if i >= len(data):
                _remove(s, card, bar, big, small)
                continue
            keep |= {card, bar, big, small} - {None}
            x = LEFT + i * (w + GAP)
            _box(_shape(s, card), x, TOP, w, BOTTOM - TOP)
            if bar:
                _box(_shape(s, bar), x, TOP, w, 4)
            hd, lab = _shape(s, big), _shape(s, small)
            if layout == 'figures':
                set_text(hd, data[i][0] or ' ')
                _box(hd, x + 32, TOP + 60, w - 64, 140)
                _font(hd, Pt(96))
                set_text(lab, data[i][1] or ' ')
                _box(lab, x + 32, TOP + 215, w - 64, 60)
                _font(lab, Pt(32), True)
                det = _dup(s, lab)
                set_text(det, data[i][2] or ' ')
                _box(det, x + 32, TOP + 300, w - 64, BOTTOM - TOP - 330)
                _anchor(det, 'top')
                _font(det, Pt(26), False)
                keep.add(det.name)
            else:
                set_text(hd, (data[i][0] or ' ').upper())
                _box(hd, x + 32, TOP + 40, w - 64, 60)
                _font(hd, Pt(32))
                body = _lines(data[i][1])
                set_text(lab, '\n'.join(body) or ' ')
                _box(lab, x + 32, TOP + 130, w - 64, BOTTOM - TOP - 160)
                _anchor(lab, 'top')
                _font(lab, Pt(28))
                for para in lab.text_frame.paragraphs:
                    para.space_after = Pt(18)
        _remove(s, *[sh.name for sh in list(s.shapes) if sh.name not in keep])
        return s

    if layout == 'accounts':
        drop = {'Text 4', 'Text 5', 'Text 6'} | {'Shape %d' % i for i in (7, 10, 13)} | \
            {'Text %d' % i for i in (8, 9, 11, 12, 14)}
        _remove(s, *drop)
        keep = header | caption('Text 3')
        if not keep - header:
            _remove(s, 'Text 3')
        # The table and its takeaway band, stretched to fill the slide.
        k = (BOTTOM - TOP) / float(783 - 214)
        for sh in s.shapes:
            if sh.name in keep:
                continue
            t, h = sh.top / 12700.0, sh.height / 12700.0
            sh.top, sh.height = Pt(TOP + (t - 214) * k), Pt(max(1, h * k))
        heads = list(a.get('heads') or []) + [''] * 5
        for nm, d, h in zip(_ACC_HEADS, ('ACCOUNT', 'VALUE', "WHAT'S INSIDE", 'LIQUIDITY', 'VS. 4Q'), heads):
            set_text(_shape(s, nm), (h or d).upper())
        rows = [list(r) + [''] * 7 for r in (a.get('rows') or [])][:3]
        for i, names in enumerate(_ACC_ROWS):
            r = rows[i] if i < len(rows) else [''] * 7
            vals = [r[0], r[1], r[2], r[3], r[4], r[5], r[6]]
            for nm, v in zip(names, vals):
                if nm:
                    set_text(_shape(s, nm), v or ' ')
        for nm, dx in (('Shape 60', 48), ('Text 61', 48)):
            sh = _shape(s, nm)
            sh.left = sh.left + Pt(dx)
            if nm == 'Text 61':
                sh.width = sh.width - Pt(dx)
        _shape(s, 'Text 59').width = _shape(s, 'Text 59').width + Pt(40)
        set_text(_shape(s, 'Text 59'), (a.get('figure') or '').strip() or ' ')
        set_text(_shape(s, 'Text 61'), (a.get('body') or '').strip() or ' ')
        _anchor(_shape(s, 'Text 61'))
        return s

    if layout == 'compare':
        keep = header | set(_CMP_SHAPES)
        _remove(s, *[sh.name for sh in list(s.shapes) if sh.name not in keep])
        # The results slide's table, stretched to fill the slide.
        k = (BOTTOM - TOP) / float(779 - 257)
        for sh in s.shapes:
            if sh.name in _CMP_SHAPES:
                t, h = sh.top / 12700.0, sh.height / 12700.0
                sh.top, sh.height = Pt(TOP + (t - 257) * k), Pt(max(1, h * k))
        heads = (a.get('heads') or ['', 'TODAY', 'WITH FOUR QUADRANTS'])
        for nm, h in zip(('Text 17', 'Text 18', 'Text 19'), heads):
            set_text(_shape(s, nm), (h or ' ').upper())
        rows = (a.get('rows') or [])[:3]
        for i, names in enumerate(_CMP_ROWS):
            r = list(rows[i]) if i < len(rows) else []
            for nm, v in zip(names, r + ['', '', '']):
                set_text(_shape(s, nm), v or ' ')
                _anchor(_shape(s, nm))
                _font(_shape(s, nm), Pt(40) if nm != names[0] else Pt(30))
        side = _lines(a.get('body'))
        if side:
            set_text(_shape(s, 'Text 40'), side[0].upper())
            set_text(_shape(s, 'Text 41'), '\n'.join(side[1:]) or ' ')
            _font(_shape(s, 'Text 41'), Pt(24))
            _font(_shape(s, 'Text 40'), Pt(26))
        else:
            _remove(s, 'Shape 38', 'Shape 39', 'Text 40', 'Text 41')
            for nm in ('Shape 15', 'Shape 16'):
                _shape(s, nm).width = Pt(WIDTH)
        return s

    if layout == 'steps':
        steps = [list(x) + ['', ''] for x in (a.get('steps') or []) if any((y or '').strip() for y in x)][:5]
        keep = header | {'Shape 66', 'Text 67'}
        band, sub = _shape(s, 'Shape 66'), _shape(s, 'Text 67')
        _box(band, LEFT, TOP, WIDTH, BOTTOM - TOP)
        subtitle = (a.get('body') or '').strip()
        set_text(sub, subtitle.upper() or ' ')
        _box(sub, LEFT + 28, TOP + 30, WIDTH - 56, 40)
        _font(sub, Pt(28))
        n = max(1, len(steps))
        w = (WIDTH - 56 - GAP * (n - 1)) / float(n)
        for i, (line, hd, bd) in enumerate(_STEP_COLS):
            if i >= len(steps):
                _remove(s, line, hd, bd)
                continue
            keep |= {line, hd, bd}
            x = LEFT + 28 + i * (w + GAP)
            _box(_shape(s, line), x, TOP + 110, w, 4)
            set_text(_shape(s, hd), (steps[i][0] or ' ').upper())
            _box(_shape(s, hd), x, TOP + 130, w, 70)
            _font(_shape(s, hd), Pt(28))
            set_text(_shape(s, bd), steps[i][1] or ' ')
            _box(_shape(s, bd), x, TOP + 220, w, BOTTOM - TOP - 250)
            _anchor(_shape(s, bd), 'top')
            _font(_shape(s, bd), Pt(28))
        _remove(s, *[sh.name for sh in list(s.shapes) if sh.name not in keep])
        return s

    # The cashflow slide's cards: points, two columns, statement.
    _remove(s, 'Text 4')
    keep_cap = caption('Text 3')
    if not keep_cap:
        _remove(s, 'Text 3')
    if layout == 'two':
        cols = [list(c) + ['', ''] for c in (a.get('columns') or [])][:2]
        while len(cols) < 2:
            cols.append(['', ''])
        half = (WIDTH - GAP) / 2.0
        keep = header | keep_cap
        for i, (card, bar, num, txt) in enumerate(_POINT_CARDS[:2]):
            keep |= {card, bar, num, txt}
            x = LEFT + i * (half + GAP)
            _box(_shape(s, card), x, TOP, half, BOTTOM - TOP)
            _box(_shape(s, bar), x, TOP, 5, BOTTOM - TOP)
            set_text(_shape(s, num), (cols[i][0] or ('TODAY' if i == 0 else 'WITH FOUR QUADRANTS')).upper())
            _box(_shape(s, num), x + 32, TOP + 30, half - 64, 60)
            _font(_shape(s, num), Pt(34), True)
            for r in [r for para in _shape(s, num).text_frame.paragraphs for r in para.runs]:
                r.font.color.rgb = RGBColor(0x3A, 0x3F, 0x45) if i == 0 else RGBColor(0xE8, 0x73, 0x0C)
            body = _lines(cols[i][1])
            set_text(_shape(s, txt), '\n'.join(body) or ' ')
            _box(_shape(s, txt), x + 32, TOP + 110, half - 64, BOTTOM - TOP - 140)
            _anchor(_shape(s, txt), 'top')
            _font(_shape(s, txt), Pt(30))
            for para in _shape(s, txt).text_frame.paragraphs:
                para.space_after = Pt(20)
        _remove(s, *[sh.name for sh in list(s.shapes) if sh.name not in keep])
        return s
    if layout in ('statement', 'statement_points'):
        pts = _lines(a.get('items'))[:3] if layout == 'statement_points' else []
        band_bottom = BOTTOM if not pts else TOP + 300
        card, txt = _shape(s, 'Shape 21'), _shape(s, 'Text 23')
        keep = header | keep_cap | {'Shape 21', 'Text 23'}
        _box(card, LEFT, TOP, WIDTH, band_bottom - TOP)
        _box(txt, LEFT + 48, TOP + 20, WIDTH - 96, band_bottom - TOP - 40)
        set_text(txt, '\n'.join(_lines(a.get('body'))) or ' ')
        _anchor(txt)
        _font(txt, Pt(52 if not pts else 40))
        for para in txt.text_frame.paragraphs:
            para.space_after = Pt(16)
        if pts:
            groups = [g for g in _POINT_CARDS if g[1]][:3]
            w = (WIDTH - GAP * 2) / 3.0
            y, h = band_bottom + GAP, BOTTOM - band_bottom - GAP
            for i, (c, b, num, t) in enumerate(groups):
                if i >= len(pts):
                    continue
                keep |= {c, b, num, t}
                x = LEFT + i * (w + GAP)
                _box(_shape(s, c), x, y, w, h)
                _box(_shape(s, b), x, y, 5, h)
                set_text(_shape(s, num), '%02d' % (i + 1))
                _box(_shape(s, num), x + 28, y + 24, 90, 56)
                _font(_shape(s, num), Pt(34))
                set_text(_shape(s, t), pts[i])
                _box(_shape(s, t), x + 28, y + 90, w - 56, h - 110)
                _anchor(_shape(s, t), 'top')
                _font(_shape(s, t), Pt(28))
        _remove(s, *[sh.name for sh in list(s.shapes) if sh.name not in keep])
        return s
    _point_cards(s, _lines(a.get('items')), TOP, BOTTOM)
    keep = header | keep_cap | {x for g in _POINT_CARDS if g[1] for x in g}
    _remove(s, *[sh.name for sh in list(s.shapes) if sh.name not in keep])
    return s


def apply_deck_edits(prs, edits, auto_drop):
    """Add the new slides where he put them and remove the slides he took
    out (and the ones left out for this client). Template numbering is used
    throughout, so it runs on the template-sized deck, last."""
    lst = prs.slides._sldIdLst
    orig = list(lst)                     # template slides, in order
    added = {}
    for a in edits.get('added') or ():
        s = _added_slide(prs, a)
        try:
            s.notes_slide.notes_text_frame.text = (
                'Today\u2019s path carried forward: what they save and spend now, when it runs out, '
                'and how much rides on the practice sale.' if a.get('id') == 'current_path'
                else 'Added on the consult review.')
        except Exception:                                    # noqa: BLE001
            pass
        added.setdefault(int(a.get('after') or len(orig)), []).append(lst[-1])
    gone = (set(auto_drop) - set(edits.get('forced') or ())) | set(edits.get('removed') or ())
    order = []
    for n, el in enumerate(orig, 1):
        if n not in gone:
            order.append(el)
        order.extend(added.get(n, []))
    for n in sorted(added):
        if n > len(orig) or n < 1:
            order.extend(added[n])
    for el in list(lst):
        lst.remove(el)
    for n, el in enumerate(orig, 1):
        if n in gone:
            prs.part.drop_rel(el.rId)
    for el in order:
        lst.append(el)
    return sorted(gone)


def _house_style(prs):
    """The lead advisor's styling, applied to every deck. The tax red flags
    page: every finding bold, dollar figures in the deck's orange, and the
    words "IRS Red Flag n" in red. The savings future: the last year-end
    portfolio in the same blue as the rest, red only when it runs short."""
    import copy as _copy
    from pptx.dml.color import RGBColor
    tok = re.compile(r"(IRS [Rr]ed [Ff]lag \d|\$[\d,]+(?:\.\d+)?[kKM]?\+?)")
    for slide in prs.slides:
        names = {sh.name: sh for sh in slide.shapes if sh.has_text_frame}
        title = ' '.join(names[n].text_frame.text for n in ('Text 1', 'Text 2') if n in names).upper()
        if 'RED FLAGS' in title and 'TAX RETURN' in title:
            for n in ('Text 8', 'Text 10', 'Text 12', 'Text 14', 'Text 16', 'Text 21', 'Text 23', 'Text 25'):
                sh = names.get(n)
                if sh is None:
                    continue
                text = sh.text_frame.text.strip()
                if not text or text.startswith('['):
                    continue                      # a placeholder keeps its look
                text = re.sub(r'IRS red flag (\d)', r'IRS Red Flag \1', text, flags=re.I)
                para = sh.text_frame.paragraphs[0]
                for q in sh.text_frame.paragraphs[1:]:
                    q._p.getparent().remove(q._p)
                base = para.runs[0]._r
                for r in para.runs[1:]:
                    r._r.getparent().remove(r._r)
                parts = [x for x in tok.split(text) if x]
                prev = None
                for i, part in enumerate(parts):
                    r = base if i == 0 else _copy.deepcopy(base)
                    if i:
                        prev.addnext(r)
                    prev = r
                    r.find('{http://schemas.openxmlformats.org/drawingml/2006/main}t').text = part
                # one size for every finding: no box shrinks its own text
                bp = sh.text_frame._txBody.bodyPr
                for el in list(bp):
                    if el.tag.endswith('normAutofit'):
                        bp.remove(el)
                if n == 'Text 25':
                    from pptx.util import Pt as _Pt
                    sh.height = _Pt(130)
                for run, part in zip(para.runs, parts):
                    run.font.bold = True
                    run.font.color.rgb = RGBColor.from_string(
                        'B03A1A' if part.upper().startswith('IRS RED FLAG') else
                        'E8730C' if part.startswith('$') else '3A3F45')
        if 'GET PAID' in title and 'Text 19' in names:
            # As the lead advisor fixed it on Tanksley: the four points one
            # size, the take-home figure beside its label in the middle of its
            # band, and the bottom rows one size, nothing shrinking itself.
            from pptx.util import Pt as _P
            E = 12700

            def _size(sh, pt):
                bp = sh.text_frame._txBody.bodyPr
                for el in list(bp):
                    if el.tag.endswith('normAutofit'):
                        bp.remove(el)
                for para in sh.text_frame.paragraphs:
                    for r in para.runs:
                        r.font.size = _P(pt)
            for n in ('Text 6', 'Text 8', 'Text 10', 'Text 12'):
                if n in names and not names[n].text_frame.text.startswith('['):
                    _size(names[n], 18)
                    names[n].width = _P(555)
            byn = {sh.name: sh for sh in slide.shapes}
            for lab, val, band in (('Text 27', 'Text 28', 'Shape 26'), ('Text 43', 'Text 44', 'Shape 42')):
                if lab in byn and val in byn and band in byn:
                    b = byn[band]
                    for sh in (byn[lab], byn[val]):
                        sh.top, sh.height = b.top, b.height
                        sh.text_frame._txBody.bodyPr.set('anchor', 'ctr')
                    byn[lab].left, byn[lab].width = b.left + _P(19), _P(192)
                    byn[val].left, byn[val].width = b.left + _P(201), _P(116)
            for lab, val in (('Text 30', 'Text 31'), ('Text 46', 'Text 47')):
                if lab in byn and val in byn:
                    for sh in (byn[lab], byn[val]):
                        sh.top, sh.height = _P(700), _P(64)
                        sh.text_frame._txBody.bodyPr.set('anchor', 'ctr')
                    _size(byn[lab], 16)
                    _size(byn[val], 20)
                    x = byn[lab].left
                    byn[lab].width = _P(175)
                    byn[val].left, byn[val].width = x + _P(160), _P(152)
        if 'SAVINGS FUTURE' in title and 'Text 78' in names:
            sh = names['Text 78']
            v = sh.text_frame.text.strip()
            col = 'B03A1A' if v.startswith(('-', '−', '(')) else '1F6FB2'
            for para in sh.text_frame.paragraphs:
                for r in para.runs:
                    r.font.color.rgb = RGBColor.from_string(col)


def _tidy(prs):
    """Small things that look wrong once a client's words are in: a space left
    before a full stop where a run ended, and a one-line figure longer than
    its box (widened toward its alignment, so Keynote and PowerPoint show it
    on one line), and text boxes that run off the slide."""
    from pptx.util import Pt
    W = prs.slide_width
    for slide in prs.slides:
        for sh in slide.shapes:
            if not sh.has_text_frame:
                continue
            # A text box running past the slide's edge (left-aligned headings
            # in the template): keep it on the slide, so it is easy to select
            # and edit in Keynote.
            if sh.left is not None and sh.left + sh.width > W and sh.left < W - Pt(200):
                sh.width = W - sh.left - Pt(48)
            for para in sh.text_frame.paragraphs:
                runs = para.runs
                for r0, r1 in zip(runs, runs[1:]):
                    if r0.text.endswith(' ') and r1.text[:1] in '.,;:)':
                        r0.text = r0.text.rstrip()
            bp = sh.text_frame._txBody.bodyPr
            text = sh.text_frame.text.strip()
            if bp.get('wrap') != 'none' or not text or '\n' in text:
                continue
            size = None
            for para in sh.text_frame.paragraphs:
                for r in para.runs:
                    if r.font.size:
                        size = r.font.size.pt
                if size is None:
                    d = para._p.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}defRPr')
                    if d is None:
                        d = sh.text_frame._txBody.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}defRPr')
                    if d is not None and d.get('sz'):
                        size = int(d.get('sz')) / 100.0
            if not size:
                continue
            need = len(text) * size * 0.55 + 6
            have = sh.width / 12700.0
            if need > have:
                extra = need - have
                algn = None
                for tag in ('pPr', 'lvl1pPr'):
                    el = sh.text_frame._txBody.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}' + tag)
                    if el is not None and el.get('algn'):
                        algn = el.get('algn')
                        break
                if algn == 'r':
                    sh.left = sh.left - Pt(extra)
                sh.width = sh.width + Pt(extra)


def render(folder, client, out, template=TEMPLATE, edits=True):
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
        if n not in drop:
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

    try:
        _layout_concerns(prs.slides[2], len(adv.get('concerns') or []))
    except Exception as exc:                                 # noqa: BLE001
        print('   concerns layout left as the template: %s' % exc)
    ed = deck_edits(folder) if edits else {}
    # The current path, before the annual savings: standard since Tanksley.
    try:
        cp = current_path_data(D)
    except Exception as exc:                                 # noqa: BLE001
        cp = None
        print('   current-path slide skipped: %s' % exc)
    if cp and 'current_path' not in {x.get('id') for x in (ed.get('added') or ())} \
            and not (D['adv'].get('no_current_path')):
        ed = dict(ed or {})
        ed['added'] = [cp] + list(ed.get('added') or [])
    if ed.get('removed') or ed.get('added') or ed.get('forced'):
        drop = apply_deck_edits(prs, ed, drop)
    else:
        for n in sorted(drop, reverse=True):
            _drop(prs, n - 1)
    _house_style(prs)
    _tidy(prs)
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
