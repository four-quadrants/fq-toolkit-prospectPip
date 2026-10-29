#!/usr/bin/env python3
"""The retirement projections on the consultation deck.

Three slides come out of this: CURRENT RETIREMENT STRATEGY, the "on pace for
$X/yr" line under it, and YOUR FOUR QUADRANTS SAVINGS FUTURE. The lead advisor builds them
by hand in `savings worksheet.numbers`, one per client.

HOW THIS WAS ESTABLISHED
By reproducing his worksheet for every signed client that has one, read from
the PDFs in `_TEST/_Converted/2.) Signed`. With the conventions below, twelve of
thirteen match row for row from the first year to retirement, on both paths.
`_spec/verify_savings.py` reruns that check.

THE ARITHMETIC, AS HIS SHEET DOES IT
Current path, at 8.5%:
    first year   start x (1 + 8.5% x f); this year's savings are already in it
    to retire    (value + deposit) x 1.085      deposit goes in at the start
    after        (value - expenses) x 1.085 + pension
Four Quadrants path, at 9%:
    first year   start x (1 + r1 x f) + this year's savings
    to retire    value x 1.09 + deposit         deposit lands at the end
    after        (value - expenses) x 1.09 + pension
Expenses inflate 3.2% a year from the first year. The sale of the practice and
building is a deposit in the retirement year, as his sheet enters it.

The two paths really do place the deposit differently. That is his sheet, not
a transcription slip here: changing either one breaks the match on every client.

CONVENTIONS THAT VARY, AND WHAT IS DEFAULTED
f, the part of the first year still to run. Since May 2026 it is the time left
    after the consult date, rounded down to a quarter: 6 May gives 0.5,
    11 August and 9 September give 0.25. Consults before May used a whole year.
r1, the first-year rate on the Four Quadrants path. 8.5% on every consult
    since August (Kinsler, Meier, Spaulding, Wright), 9% on some earlier ones.
    8.5% is the default, and it is also the defensible one: in the first
    partial year the money has not moved yet.
Once the money runs out. Rebol and Spaulding stop compounding a negative
    balance; Bassett keeps compounding it. Only the run-out year is printed, and
    it comes out the same either way, so the default is to stop compounding.

FAULTS IN THE ANSWER KEYS, NOT REPRODUCED
Kinsler's current path starts taking expenses in 2041 but puts the sale in 2042,
    and the deck says the sale is in 2040. Three different years.
Kinsler's deck shows $383,088 of first-year expenses, which is Rebol's figure;
    her own sheet has $248,796.
Kinsler's deck and her worksheet differ by $2,000 on the first-year savings.
Spaulding's sheet stops compounding two years before her money runs out.
"""
import datetime

INFLATION = 0.032
CURRENT_RETURN = 0.085
FQ_RETURN = 0.09
FIRST_YEAR_FQ_RETURN = 0.085
HORIZON_AGE = 90


def first_year_fraction(consult_date):
    """The part of the first year left after the consult, rounded down to a quarter."""
    if isinstance(consult_date, str):
        consult_date = datetime.datetime.strptime(consult_date, '%Y-%m-%d').date()
    end = datetime.date(consult_date.year, 12, 31)
    left = (end - consult_date).days / 365.0
    return int(left * 4) / 4.0


def _expense(exp0, y, y0):
    return exp0 * (1 + INFLATION) ** (y - y0)


def current_path(start, f, deposits, retire_year, expenses, y0, end,
                 r=None, compound_negative=False):
    """Year-end values on the current path. deposits is {year: amount}, with the
    sale in the retirement year and any pension in the years after it."""
    r = CURRENT_RETURN if r is None else r
    out = {}
    v = start * (1 + r * f)
    out[y0] = v
    for y in range(y0 + 1, end + 1):
        d = deposits.get(y, 0)
        if y <= retire_year:
            v = (v + d) * (1 + r)
        else:
            x = v - _expense(expenses, y, y0)
            v = (x * (1 + r) if (x > 0 or compound_negative) else x) + d
        out[y] = v
    return out


def fq_path(start, f, deposits, retire_year, expenses, y0, end,
            r=None, r1=None, compound_negative=False):
    """Year-end values on the Four Quadrants path. deposits as above, from the
    advisor's savings schedule. Rates are read when called, so the advisor's
    own figures (set by deck_template.apply_assumptions) are used."""
    r = FQ_RETURN if r is None else r
    r1 = FIRST_YEAR_FQ_RETURN if r1 is None else r1
    out = {}
    v = start * (1 + r1 * f) + deposits.get(y0, 0)
    out[y0] = v
    for y in range(y0 + 1, end + 1):
        d = deposits.get(y, 0)
        if y <= retire_year:
            v = v * (1 + r) + d
        else:
            x = v - _expense(expenses, y, y0)
            v = (x * (1 + r) if (x > 0 or compound_negative) else x) + d
        out[y] = v
    return out


def runout_year(path):
    """First year the balance is below zero, or None if it never is."""
    for y in sorted(path):
        if path[y] < 0:
            return y
    return None


def sustainable_expense(start, f, deposits, retire_year, y0, end, step=1000):
    """The "currently on pace for $X/yr" figure: the largest first-year expense,
    in steps of $1,000, that the current path carries to the horizon without
    going below zero. Matches Rebol ($191,000), Bassett ($169,000) and
    Spaulding ($158,000, whose sheet runs to 94 rather than 90)."""
    lo, hi = 0, step
    while current_path(start, f, deposits, retire_year, hi, y0, end)[end] >= 0:
        lo, hi = hi, hi * 2
    while hi - lo > step:
        mid = (lo + hi) // 2 // step * step
        if mid in (lo, hi):
            break
        if current_path(start, f, deposits, retire_year, mid, y0, end)[end] >= 0:
            lo = mid
        else:
            hi = mid
    return lo


def solve_income(start, f, deposits, retire_year, y0, end, r1=None,
                 step=1000):
    """The retirement income the Four Quadrants path pays to the horizon: the
    largest first-year figure, in $1,000s, that leaves the portfolio at or
    above zero. Not typed by the advisor: this reproduces the lead advisor’s target on
    Rebol ($466,000), Spaulding ($571,000), Kinsler ($564,000) and Bassett
    ($324,000) exactly."""
    r1 = FIRST_YEAR_FQ_RETURN if r1 is None else r1

    def ok(inc):
        return fq_path(start, f, deposits, retire_year, inc, y0, end,
                       r1=r1)[end] >= 0
    lo, hi = 0, step
    while ok(hi):
        lo, hi = hi, hi * 2
    while hi - lo > step:
        mid = (lo + hi) // 2 // step * step
        if mid in (lo, hi):
            break
        if ok(mid):
            lo = mid
        else:
            hi = mid
    return lo


def step_schedule(steps, first, last):
    """{year: amount} from a step list like [(2026, 73900), (2028, 101900)],
    each amount holding until the next step. The advisor's savings schedule is
    written this way."""
    steps = sorted(steps)
    out = {}
    for y in range(first, last + 1):
        live = [a for s, a in steps if s <= y]
        if live:
            out[y] = live[-1]
    return out


def project(start, consult_date, age_now, retire_age, current_savings,
            current_expenses, fq_schedule, fq_income, sale_net=0, pension=0,
            pension_from=None, horizon_age=None, f=None, r1=None):
    """Both paths and the headline figures, for the deck.

    start             today's portfolio, from the Assumptions sections 4 and 5
    current_savings   what is being saved per year now
    current_expenses  personal spending including liabilities, x12
    fq_schedule       advisor: [(year, amount), ...] savings steps
    fq_income         advisor: target retirement income, first-year dollars
    sale_net          advisor: practice and building sale, net, at retirement
    """
    if isinstance(consult_date, str):
        consult_date = datetime.datetime.strptime(consult_date, '%Y-%m-%d').date()
    y0 = consult_date.year
    if f is None:
        f = first_year_fraction(consult_date)
    # A consult late enough that no quarter of the year is left starts the
    # projection on 1 January, a whole year at the full rate, with expenses
    # inflating from that year. Oyler's redesigned deck (16 October) opens on
    # 2027: $1,105,645 x 1.09 + $120,800 = $1,325,953, against $599,000 of
    # expenses in 2027 and $618,168 in 2028.
    if f == 0:
        y0, f = y0 + 1, 1.0
        r1 = FQ_RETURN if r1 is None else r1
    horizon_age = horizon_age or HORIZON_AGE
    retire = consult_date.year + (retire_age - age_now)
    end = consult_date.year + (horizon_age - age_now)
    pension_from = pension_from or retire + 1

    cur = step_schedule([(y0, current_savings)], y0, retire)
    cur[retire] = cur.get(retire, 0) + sale_net
    fqd = step_schedule(fq_schedule, y0, retire)
    fqd[retire] = fqd.get(retire, 0) + sale_net
    for y in range(max(pension_from, retire + 1), end + 1):
        cur[y] = cur.get(y, 0) + pension
        fqd[y] = fqd.get(y, 0) + pension

    c = current_path(start, f, cur, retire, current_expenses, y0, end)
    q = fq_path(start, f, fqd, retire, fq_income, y0, end,
                r1=FIRST_YEAR_FQ_RETURN if r1 is None else r1)
    ro = runout_year(c)
    pace = sustainable_expense(start, f, cur, retire, y0, end)
    out = {
        'first_year': y0, 'retire_year': retire, 'end_year': end, 'f': f,
        'current': c, 'fq': q,
        'current_deposits': cur, 'fq_deposits': fqd,
        'runout_year': ro,
        'years_before_runout': (ro - retire) if ro else None,
        'on_pace_for': pace,
        'current_at_retirement': c[retire],
        'fq_at_retirement': q[retire],
        # "accounts for 66% of retirement portfolio at that time": the net
        # sale over the year-end value, as the deck computes it (Rebol 66%,
        # Spaulding 16%, Kinsler 27%).
        'sale_share_of_portfolio': (sale_net / c[retire]
                                    if c[retire] > 0 and sale_net else None),
        # "(50% of current lifestyle)": on-pace-for over today's expenses.
        'on_pace_share': pace / current_expenses if current_expenses else None,
    }
    return out
