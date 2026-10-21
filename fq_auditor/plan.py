#!/usr/bin/env python3
"""The proposed plan's inputs, worked out rather than typed.

What Brogan types into his savings worksheet turns out to be mostly arithmetic
on figures the toolkit already reads (`_spec/savings/WORKSHEET.md`). This file
does that arithmetic, so the advisor reviews a prefilled plan instead of
building one:

    sale()          the practice (and building, when the client owns one) at
                    retirement, net
    gains()         the cashflow gains the plan is built from, each with its
                    source
    invested()      how much of each gain is saved, year by year: a proposed
                    ramp the advisor adjusts
    schedule()      the yearly savings, summed from the above
    savings.solve_income() then gives the retirement income the schedule pays.

Everything the advisor enters in the deck entry of plan_inputs.json still wins:
a figure here is a proposal, never an override.
"""
import math

PRACTICE_MULTIPLE = 0.65     # of collections, as in every worksheet read
PRACTICE_GROWTH = 0.03       # his K column
BUILDING_GROWTH = 0.02       # his L column
SALE_NET = 0.70              # after taxes, on every deck and worksheet read
OVERHEAD_STEP = 0.03         # "3% lower overhead = 122.4k"
PERSONAL_CUSHION_MONTHS = 2  # personal cash kept back before a surplus

# The proposed ramp. His invested amounts phase recurring gains in over three
# years and take a share of one-time items once:
#   3% lower overhead   Oyler 6k, 18k, 36k; Kinsler 9k, 15k, 21k;
#                       Meier 12k, 24k, 36k
#   bank surplus (once) Oyler 20k of 65.7k; Kinsler 100k of 203k;
#                       Meier 550k of 707k
# No single rule reproduces all three, so this is a middle line, and the
# advisor's figures replace it.
RAMP_PRACTICE = (0.10, 0.20, 0.30)   # practice improvements, by plan year
RAMP_CASH = (0.50, 0.50, 0.50)       # cash the household already has coming
ONCE_SHARE = 0.50                    # one-time items, year 1 only
ROUND_TO = 3000


def _round(v, step=ROUND_TO):
    return int(round((v or 0) / float(step))) * step


def practice_value(collections):
    """65% of collections: Oyler 0.65 x $4,103,930 = $2,667,000, his figure."""
    return collections * PRACTICE_MULTIPLE if collections else None


def sale(collections, years, building=None, debt_at_sale=0.0,
         growth=PRACTICE_GROWTH):
    """Gross and net proceeds at retirement.

    The building only when the client owns it and a value has been entered:
    many rent, and an owned building with no value is a gap the Assumptions
    already prints, not a zero to assume.
    """
    pv = practice_value(collections)
    if pv is None or years is None:
        return None, None
    gross = pv * (1 + growth) ** years
    if building:
        gross += building * (1 + BUILDING_GROWTH) ** years
    net = gross * SALE_NET - (debt_at_sale or 0)
    return gross, net


def gains(collections=None, current_savings=None, cash=None,
          ideal_balance=None, spend_excl_monthly=None, levers=None,
          extra=None):
    """The list the savings projection slide is built from.

    Each entry: key, label, gain (a year's cashflow), kind ('base', 'practice',
    'cash' or 'once'), basis. Only what can be supported is listed; the
    advisor adds the rest (a refinance, a policy cash-out, better tax
    management) in the deck entry under 'gains'.
    """
    out = []
    if current_savings:
        out.append(dict(key='current', label='Current savings',
                        gain=current_savings, kind='base',
                        basis='What is saved today, all of it kept.'))
    if collections:
        out.append(dict(key='overhead', label='−3% overhead',
                        gain=collections * OVERHEAD_STEP, kind='practice',
                        basis='3%% of collections of $%s.'
                              % '{:,.0f}'.format(collections)))
    for key, label in (('adjustment', 'Lower adjustment %'),
                       ('new_patients', 'New patient %'),
                       ('per_patient', 'Net production per patient'),
                       ('fees', 'Fee increase'),
                       ('collections', 'Collection % to 99.5%')):
        v = ((levers or {}).get(key) or {}).get('value')
        if v:
            out.append(dict(key=key, label=label, gain=v, kind='practice',
                            basis='levers.py, to the owner.'))
    if cash:
        practice_bal = sum(a['balance'] or 0 for a in cash['accounts']
                           if a['entity'] != 'Personal')
        personal_bal = sum(a['balance'] or 0 for a in cash['accounts']
                           if a['entity'] == 'Personal')
        if ideal_balance and practice_bal > ideal_balance:
            out.append(dict(
                key='practice_surplus', label='Practice bank surplus **',
                gain=practice_bal - ideal_balance, kind='once',
                basis='Practice balances of $%s above the ideal balance of '
                      '$%s.' % ('{:,.0f}'.format(practice_bal),
                                '{:,.0f}'.format(ideal_balance))))
        cushion = (spend_excl_monthly or 0) * PERSONAL_CUSHION_MONTHS
        if personal_bal > cushion:
            out.append(dict(
                key='personal_surplus', label='Personal bank surplus **',
                gain=personal_bal - cushion, kind='once',
                basis='Personal balances of $%s less two months of spending.'
                      % '{:,.0f}'.format(personal_bal)))
        monthly = sum((a.get('surplus') or 0) for a in cash['accounts']
                      if a['entity'] == 'Personal' and a.get('readable'))
        if monthly > 0:
            out.append(dict(
                key='personal_monthly', label='Personal monthly surplus',
                gain=monthly * 12, kind='cash',
                basis='Average personal surplus of $%s a month.'
                      % '{:,.0f}'.format(monthly)))
    for g in (extra or []):
        out.append(dict(key=g.get('key') or g.get('label'), label=g['label'],
                        gain=g.get('gain') or 0,
                        kind=g.get('kind') or 'cash',
                        basis=g.get('basis') or 'Entered by the advisor.',
                        invested=g.get('invested')))
    return out


def invested(g, year_index):
    """The proposed amount saved from one gain in plan year 1, 2, 3..."""
    if g.get('invested'):
        given = g['invested']
        return given[min(year_index, len(given) - 1)]
    k = g['kind']
    i = min(year_index, 2)
    if k == 'base':
        return g['gain']
    if k == 'once':
        return _round(g['gain'] * ONCE_SHARE, 5000) if year_index == 0 else 0
    ramp = RAMP_PRACTICE if k == 'practice' else RAMP_CASH
    return _round(g['gain'] * ramp[i])


def schedule(glist, first_year, years=3):
    """[(year, amount), ...]: each of the first `years` plan years summed,
    then held, as his brokerage rows hold from year 3."""
    return [(first_year + i, sum(invested(g, i) for g in glist))
            for i in range(years)]
