#!/usr/bin/env python3
"""Draft the base plan of the Assumptions, from the documents.

    python3 assumptions.py "<client folder>" --client "Dr. Brian Oyler"

WHAT THIS IS
The Assumptions is the firm's financial plan for a prospect: fifteen numbered
sections in a fixed order, each stating what the plan assumes and where the
figure came from. It is the hub of the whole pipeline. The Prospect Summary
feeds it, the due diligence comes out of it, and the consult deck is built from
it.

The base plan only. The proposed plan is written after the consultation and is
not generated here; what survives in old files under that heading is leftover
text from a previous client.

WHY GENERATE IT AT ALL
Because it is currently built by copying last client's document and editing.
Oyler's own plan still names a previous client in four places -- "Louisa's
W-2s", "her student debt" -- and carries two account numbers that contradict
the statements in his folder. Generating it from the facts cannot make those
mistakes, and it takes the hours out of the part that is transcription rather
than judgement.

WHAT IT WILL NOT DO
Fill a section it cannot support. A section with no documents behind it is
printed with what is needed and why, in the body of the plan where the analyst
will see it, rather than silently omitted or quietly carried over from someone
else.
"""
import os
import sys
import json
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import facts as _facts                                       # noqa: E402
import compose as _compose                                   # noqa: E402
import inputs as _inputs                                     # noqa: E402

try:
    import cashflow as _cashflow                             # noqa: E402
except Exception:                                            # pragma: no cover
    _cashflow = None

try:
    from urllib.parse import quote
except ImportError:                                          # pragma: no cover
    from urllib import quote


def _zillow_link(street, town, state):
    """A link straight to the property, so the lookup is one click.

    Zillow's /homes/<slug>_rb/ form resolves an address without needing its
    internal property id, which we have no way of knowing.
    """
    slug = '%s %s %s' % (street, town, state)
    return 'https://www.zillow.com/homes/%s_rb/' % quote(
        slug.replace(' ', '-'), safe='-')

# The firm's standing assumptions. These do not come from the client and should
# not be re-derived per client; where one changes, it changes here once.
FIRM = {
    'inflation': 3.2,
    'life_expectancy': 90,
    'property_growth': (3.0, 0.5),
    # Measured across the 44 plans, not inferred from one. Nine percent with
    # an eight point deviation covers retirement plans, IRAs and brokerage
    # (8 of 10 occurrences). Twelve is not the general case: it appears only
    # against 529s and a single concentrated stock holding, which is a
    # different risk and gets its own constant below. Carrying 12.0 as the
    # default would have widened the deviation on every diversified account
    # in every plan.
    'retirement_return': (9.0, 8.0),
    # The wider deviation, for anything self-directed or concentrated rather
    # than managed and diversified: 529s, crypto (Rice's Coinbase holding),
    # a single stock position, and an unmanaged 403b. Rice's plan states the
    # distinction outright, giving the Redlands 403b 12.0 and "the managed
    # retirement accounts" 8.0 in the same sentence.
    'unmanaged_return': (9.0, 12.0),
    'cash_return': (0.0, 0.0),
    'practice_growth': (4.0, 1.0),
    'social_security_pct': 40,
    'social_security_age': 65,
    'social_security_index': 2.0,
    'practice_value_multiple': 0.65,
}


class Section(object):
    """One numbered item of the plan."""

    def __init__(self, number, text=None, needed=None, why=None, source=None,
                 link=None, flag=None, rows=None):
        self.number = number
        self.text = text
        # A section that is really a list gets one. The old documents ran
        # eight accounts together in a single sentence separated by
        # semicolons, which is unreadable and is also why nobody noticed the
        # same IRA being counted twice. A label, an amount, and the basis
        # underneath: {label, amount, detail}.
        self.rows = rows or []
        self.needed = needed
        self.why = why
        self.source = source
        # Where to go and do the thing the section is waiting on. A needed
        # block that says "look up the Zillow estimate" and makes the reader
        # find the property themselves is most of the work left undone.
        self.link = link
        # A note about the figure that is printed rather than the figure
        # itself: stale, contradicted, or carried over.
        self.flag = flag
        # For a section whose headline figure is in its prose rather than in
        # a row, so the closing summary can reach it without re-deriving it.
        self.value = None
        # Column headings, when the section renders as a table. Unlabelled
        # columns are most of what makes a block of figures hard to read.
        self.heads = None

    @property
    def complete(self):
        return bool(self.text)


def _money(v, pence=False):
    if v is None:
        return None
    return ('${:,.2f}' if pence else '${:,.0f}').format(v)


def _get(bundle, label):
    for fact in bundle.all_facts():
        if fact.label == label:
            return fact
    return None


def _value(bundle, label):
    fact = _get(bundle, label)
    return fact.value if fact else None


def _series(bundle, name, year=None):
    for label, by_year, _fmt in bundle.series:
        if label != name:
            continue
        if year:
            return by_year.get(year)
        got = {y: v for y, v in by_year.items() if v is not None}
        return got
    return None


def _flag(folder, number):
    """An analyst-recorded caveat for one section, if there is one.

    Section flags live in the input store under 'section_flags', keyed by
    section number as a string. This exists so a known problem with a
    section can be printed without the section's own reader having to learn
    about it: the Hearthside loan is missing from the debt schedule because
    the statement has not arrived, which is a fact about the client's file
    rather than something the debt reader can discover.
    """
    got = (_inputs.get(folder, 'section_flags') or {}).get('value') or {}
    return got.get(str(number))


def build(bundle, folder):
    years = bundle.years
    latest = years[-1] if years else None
    # Full years only. Valuing a practice at 65% of a seven-month year reads
    # as a figure rather than as a mistake: Oyler's came out at $1.41m against
    # a true $2.67m, and nothing on the page said the year was short.
    full = [y for y in years if (bundle.months_by_year or {}).get(y, 0) >= 12]
    if not full:
        full = years[:-1] or years
    out = []

    # 1 ---------------------------------------------------------------------
    this_year = datetime.date.today().year
    age = _value(bundle, 'Age')
    end = (this_year + int(FIRM['life_expectancy'] - age)) if age else None
    out.append(Section(1,
        'We have employed an inflation rate of %.1f%% annually over the life '
        'of the plan (%d-%s).' % (FIRM['inflation'], this_year, end or '----'),
        source='firm standard'))

    # 2 ---------------------------------------------------------------------
    retire_at = _value(bundle, 'Retirement age goal')
    if age and retire_at:
        year_of = this_year + int(retire_at - age)
        # The corpus wording, unchanged in all 44 plans: given name, the year,
        # the age, then the life expectancy in brackets. Year only, because
        # the firm's plans assume a year-end exit and the IC form carries an
        # age rather than a birth date.
        out.append(Section(2,
            'We assume that %s is set to retire in %d, at an age of %d. Life '
            'expectancy used for this plan is age %d (%s).'
            % (bundle.forename or 'the client', year_of, retire_at,
               FIRM['life_expectancy'], end),
            source='IC form: age %d, retirement age goal %d.'
                   % (age, retire_at)))
    else:
        out.append(Section(2, needed='the client’s target retirement age',
                           why='every projection in the plan runs to it'))

    # 3 ---------------------------------------------------------------------
    # Two separate questions, and conflating them cost us a round trip. The
    # address is in the documents. The market value is not in any document and
    # never will be, because it is a Zillow estimate and Zillow blocks
    # automated requests. So the address is read and the value is typed, and
    # the section says which of the two is actually missing.
    # One household, several properties. The first version assumed one home
    # and printed a single sentence, which on this client hid three of the
    # four properties the decree awards him. Properties live in the input
    # store under 'properties', each {label, amount, basis, needed}, and the
    # section renders them as a table with the growth assumption stated once
    # underneath rather than repeated per property.
    props = (_inputs.get(folder, 'properties') or {}).get('value') or []
    if not props:
        home = _compose.residence_full(folder)
        val = _inputs.get(folder, 'residence_value')
        if home and val and val.get('value'):
            street, town, state = home
            props = [{'label': '%s, %s' % (town, state),
                      'amount': _money(val['value']),
                      'basis': '%s. %s' % (street,
                                           _inputs.cite(val, 'Zillow.com'))}]
    if props:
        rows = [{'label': p.get('label'),
                 'amount': p.get('amount') or 'not valued',
                 'detail': p.get('basis')} for p in props]
        missing = [p for p in props if not p.get('amount')]
        out.append(Section(3,
            'From a personal asset standpoint, we show the following '
            'properties. Each has been given a growth rate of %.1f%% and a '
            '%.1f%% standard deviation for purposes of Monte Carlo '
            'Simulation.'
            % (FIRM['property_growth'][0], FIRM['property_growth'][1]),
            rows=rows,
            source=(_inputs.get(folder, 'properties') or {}).get('note')
                   or 'Zillow estimates and the closing documents.',
            flag=('%d of these %d properties still need a current market '
                  'value.' % (len(missing), len(props))) if missing
                 else _flag(folder, 3)))
    else:
        out.append(Section(3, needed='the address and a current value for '
                                     'each property the household owns',
                           why='property is usually the largest asset outside '
                               'the practice, and the plan cannot show a '
                               'balance sheet without it'))

    # 4 and 5 ---------------------------------------------------------------
    # Both sections render from the input store, under 'qualified_accounts'
    # and 'nonqualified_accounts'. Each entry is {label, value, basis}, and
    # the store does not care whether a reader put it there or a person did.
    # That matters: the account reader is still being built, and wiring these
    # sections to it directly would have left them blank until it lands.
    # Pointing both at the store instead means the reader becomes a way of
    # filling the store rather than a prerequisite for the page.
    def _listing(key, number, heading, missing_need, missing_why):
        got = _inputs.get(folder, key)
        rows = (got or {}).get('value') or []
        if not rows:
            return Section(number, needed=missing_need, why=missing_why)
        return Section(number,
            'Below is a list of all %s investable assets that %s currently '
            'owns, along with their respective market values.'
            % (heading, bundle.forename or 'the client'),
            rows=[{'label': r.get('label'),
                   'amount': r.get('amount') or _money(r.get('value')),
                   'detail': r.get('basis')} for r in rows],
            source=(got or {}).get('note') or 'account statements',
            flag=(got or {}).get('flag'))

    out.append(_listing(
        'qualified_accounts', 4, 'QUALIFIED',
        'statements for every retirement and investment account',
        'the plan cannot say whether retirement is reachable without '
        'knowing what is already saved'))
    cash = _cash_flow(folder)
    rows = _listing(
        'nonqualified_accounts', 5, 'NON-QUALIFIED',
        'bank and brokerage statements',
        'the non-qualified side of the balance sheet')
    if cash and cash['accounts']:
        # Built from the cash flow workbook rather than typed in, so the
        # published sentence and the workbook cannot drift apart.
        listed, unread = [], []
        for a in cash['accounts']:
            if not a['readable']:
                unread.append(a['name'])
                listed.append({'label': a['name'],
                               'amount': _money(a['balance']),
                               'basis': 'Balance only. %s' % a['why']})
                continue
            listed.append({
                'label': a['name'],
                'amount': _money(a['balance']),
                'basis': 'Average deposit %s, average expense %s, average '
                         '%s %s, across %d statement periods.'
                         % (_money(a['deposit']), _money(a['expense']),
                            'surplus' if a['surplus'] >= 0 else 'deficit',
                            _money(abs(a['surplus'])), a['periods'])})
        rows = Section(5,
            'Below is a list of all NON-QUALIFIED investable assets that %s '
            'currently owns, along with their respective market values.'
            % (bundle.forename or 'the client'),
            rows=[{'label': x['label'], 'amount': x['amount'],
                   'detail': x['basis']} for x in listed],
            source='Bank statements, via the cash flow workbook.',
            flag=('Transactions could not be read on %d of these accounts '
                  '(%s), so no transfers were found on them and only the '
                  'balance is shown.'
                  % (len(unread), ', '.join(unread))) if unread else None)
    out.append(rows)

    # 6 ---------------------------------------------------------------------
    basis_year = full[-1] if full else latest
    revenue = _series(bundle, 'revenue (P&L)', basis_year)
    if revenue:
        value = revenue * FIRM['practice_value_multiple']
        # "Annualised" only when the year is short. Saying it of a full
        # twelve months is a quiet claim that the figure was extrapolated,
        # which invites someone to go looking for the extrapolation. The
        # corpus says "65% of 2025 revenues" for a full year and "65% of
        # Jan - Nov 2025 revenues annualized" when it genuinely was one.
        months = (bundle.months_by_year or {}).get(basis_year, 12)
        basis = ('%s revenues' % basis_year if months >= 12
                 else 'annualised %s revenues' % basis_year)
        entity = _compose.entity_name(folder) or 'the practice'
        out.append(Section(6,
            'The practice value of the S-corporation, %s, is assumed to be '
            '%s (approx. %d%% of %s) and is scheduled to grow at %.0f%% '
            'annually with a %.0f%% standard deviation. This plan shows the '
            'sale of the practice at retirement without the proceeds being '
            'invested.'
            % (entity, _money(value), FIRM['practice_value_multiple'] * 100,
               basis, FIRM['practice_growth'][0], FIRM['practice_growth'][1]),
            source='%s Profit and Loss, revenue of %s, at the firm multiple.'
                   % (basis_year, _money(revenue))))
        out[-1].value = value
    else:
        out.append(Section(6, needed='a full year of practice revenue',
                           why='practice value is a multiple of it'))

    # 7 ---------------------------------------------------------------------
    # What is known about the building is worth printing even though the
    # value is not known, because it tells the reader why the gap is a gap.
    # The practice's own asset schedule carries leasehold improvements and
    # no building, and its Form 8825 rental totals are zero, so the S-corp
    # is a tenant and the building is held outside it. That means no figure
    # in the practice's books is the building's value, and nobody should go
    # looking for one.
    import intake_form as _ic
    _f = _ic.find_form_near(folder)
    form = _ic.parse(_f) if _f else {}
    addr = _compose.addresses(folder)
    bits = []
    if addr:
        bits.append('in %s, %s' % (addr[0][0][1], addr[0][0][2]))
    sqft = _ic.money(form.get('building_sqft'))
    if sqft:
        bits.append('of {:,.0f} square feet'.format(sqft))
    lead = ('We show that %s owns the practice building%s.'
            % (bundle.forename or 'the client',
               (' ' + ' '.join(bits)) if bits else ''))
    rent = _ic.money(form.get('building_payment'))
    if rent:
        lead += (' The practice pays rent of %s per month, which is an '
                 'expense of the practice and income to %s.'
                 % (_money(rent), bundle.forename or 'the client'))
    out.append(Section(7,
        text=lead,
        needed='a current value for the practice building',
        # This used to be Oyler's own findings, word for word, printed on
        # every client's plan: "Brian owns it personally ... Form 8825 rental
        # totals are zero ... Zillow has no record of the parcel." Rebol's
        # plan said Brian. Only what holds for any client belongs here.
        why='Held outside the practice, so it sits in the plan alongside it '
            'and is usually sold with it or leased on afterwards. A building '
            'the practice rents is not on the practice’s books at its value, '
            'so a county assessment, an appraisal or a Zillow estimate is the '
            'source.',
        flag=_flag(folder, 7)))

    # 8 and 9 ---------------------------------------------------------------
    for number, block, label in ((8, 'Personal debt', 'personal and rental '
                                                      'property'),
                                 (9, 'Practice debt', 'practice')):
        rows = [f for f in bundle.all_facts()
                if _in_block(bundle, f, block) and f.value is not None
                and not f.label.startswith(('Practice total', 'Personal total',
                                            'Practice debt service',
                                            'Personal debt service',
                                            'Practice debt', 'Personal debt'))]
        if rows:
            total = sum(r.value for r in rows)
            out.append(Section(number,
                'The following %s liability positions are worth mentioning.'
                % label,
                rows=[{'label': r.label, 'amount': _money(r.value),
                       'mid': _maturity(folder, r.value),
                       'detail': (r.note or '').replace('  ·  ', ', ') or None}
                      for r in rows] +
                     [{'label': 'Total', 'amount': _money(total),
                       'detail': None, 'rule': True}],
                source='debt schedule and lender statements',
                flag=_flag(folder, number)))
            out[-1].heads = ('Obligation', 'Matures', 'Balance')
        else:
            out.append(Section(number,
                               needed='statements or a schedule for the %s '
                                      'debts' % label,
                               why='debt service is the largest fixed call on '
                                   'cash in most plans'))

    # 10 --------------------------------------------------------------------
    wages = _series(bundle, 'doctor income (P&L)', basis_year)
    rev = _series(bundle, 'revenue (P&L)', basis_year)
    exp = _series(bundle, 'expenses (P&L)', basis_year)
    net = (rev - exp) if (rev and exp) else None
    if wages or net:
        # Four numbers and two growth rates, which as a sentence forces the
        # reader to hold the W-2 in their head while the net profit arrives.
        # As a table the question "what does he actually take out, and what
        # happens to it" is answered by looking.
        rows = []
        if wages:
            rows.append({'label': 'W-2 wages from the practice',
                         'amount': _money(wages),
                         'detail': 'Grown at the %.1f%% inflation rate until '
                                   'retirement.' % FIRM['inflation']})
        if net:
            rows.append({'label': 'Net profit',
                         'amount': _money(net),
                         'detail': 'Revenue of %s less expenses of %s. '
                                   'Distributions grown at 5.0%% until '
                                   'retirement.' % (_money(rev), _money(exp))})
        if wages and net:
            rows.append({'label': 'Total earnings',
                         'amount': _money(wages + net),
                         'detail': None, 'rule': True})
        officer = _series(bundle, 'officer compensation (tax return)',
                          basis_year)
        src = '%s Profit and Loss' % basis_year
        if officer:
            src += ', confirmed against officer compensation of %s on the ' \
                   '1120-S' % _money(officer)
        out.append(Section(10,
            'Current profitability for %s suggests the following earnings.'
            % basis_year,
            rows=rows, source=src + '.', flag=_flag(folder, 10)))
        out[-1].heads = ('Source', 'Amount')
    else:
        out.append(Section(10, needed='a full year P&L and the matching return',
                           why='income is what everything else is measured '
                               'against'))

    # 11 --------------------------------------------------------------------
    out.append(Section(11,
        'For retirement, we assume %d%% of Social Security benefits available '
        'starting at age %d. These benefits are indexed by %.0f%% annually.'
        % (FIRM['social_security_pct'], FIRM['social_security_age'],
           FIRM['social_security_index']),
        source='firm standard'))

    # 12 --------------------------------------------------------------------
    if cash and cash['monthly_including']:
        inc, exc, fixed = (cash['monthly_including'],
                           cash['monthly_excluding'], cash['fixed'])
        # The firm's wording, unchanged across 72 plans: spending stated
        # twice, once without the fixed payments and once with.
        text = ('We presume that current personal expenses are %s monthly '
                '(%s annually), excluding the personal liabilities, '
                'insurance, and savings strategies (approximately %s '
                'annually [or %s monthly] including those payments).'
                % (_money(exc), _money(exc * 12), _money(inc * 12),
                   _money(inc)))
        rows = [{'label': '%s  (%s)' % (name, kind),
                 'amount': _money(amount), 'detail': None}
                for name, amount, kind in
                sorted(cash.get('fixed_rows') or (), key=lambda r: -r[1])]
        if rows:
            rows.append({'label': 'Total excluded', 'amount': _money(fixed),
                         'detail': None, 'rule': True})
        notes = []
        if cash.get('one_offs'):
            notes.append('%d one-off payment%s totalling %s %s been left '
                         'out of the monthly figure, on the Adjustments '
                         'block for review.'
                         % (len(cash['one_offs']),
                            '' if len(cash['one_offs']) == 1 else 's',
                            _money(sum(cash['one_offs'])),
                            'has' if len(cash['one_offs']) == 1 else 'have'))
        unread = [a['name'] for a in cash['accounts'] if not a['readable']]
        if unread:
            notes.append('%d account%s contributed nothing to this figure '
                         'because their transactions could not be read (%s).'
                         % (len(unread), '' if len(unread) == 1 else 's',
                            ', '.join(unread)))
        out.append(Section(12, text, rows=rows,
            source='Cash flow workbook, from the bank statements.',
            flag='  '.join(notes) or None))
        out[-1].heads = ('Liability, insurance or savings', 'Monthly')
    else:
        out.append(Section(12, needed='personal bank statements, so monthly '
                                      'spending can be measured rather than '
                                      'estimated',
                           why='the retirement figure is driven more by what '
                               'the household spends than by what it earns'))

    # 13 --------------------------------------------------------------------
    out.append(Section(13,
        'Any surplus incurred between now and retirement is assumed to be '
        'spent.', source='firm standard'))

    # 14 --------------------------------------------------------------------
    # The IC form asks how much was saved last year as free text, so the
    # answer is often a sentence rather than a number ("Max allowed in plans
    # currently"). Printing that where a figure belongs reads as a figure and
    # is not one: it says the intent, not the amount, and the plan needs the
    # amount. So an answer with no digits in it counts as unanswered, and the
    # client's own words are carried into the ask so nobody asks twice.
    saved = _value(bundle, 'Saved last year')
    numeric = saved is not None and any(c.isdigit() for c in str(saved))
    if numeric:
        out.append(Section(14,
            'Investment amounts currently being put back into investable '
            'assets: %s. These contribution assumptions matter a great deal '
            'to the plan; please tell us if any of it is wrong.' % saved,
            source='IC form'))
    elif saved:
        out.append(Section(14,
            needed='the dollar amount going into each retirement account '
                   'annually, and any employer match',
            why='the IC form answer reads "%s", which states the intent but '
                'not the amount. Contributions are the one lever the client '
                'controls immediately, so the plan needs the figure.'
                % str(saved).strip().rstrip('.')))
    else:
        out.append(Section(14, needed='the current annual contribution to each '
                                      'retirement account, and any employer '
                                      'match',
                           why='it is the one lever the client controls '
                               'immediately'))
    return out


_MATURITY = {}


def _maturity(folder, balance):
    """The year an obligation matures, matched to its balance.

    Read from the debt schedule rather than from the fact's note, because
    the note is prose assembled for the initial notes and maturity never
    made it in. Matched on balance: the schedule and the facts layer carry
    the same figures to the cent, and the names differ between them.

    A year far beyond any plausible term is the schedule's way of saying a
    line revolves and has no maturity. Printing "2099" would put a number in
    a column where the honest answer is that there isn't one.
    """
    if folder not in _MATURITY:
        got = {}
        try:
            import debt as _debt
            for side in ('practice', 'personal'):
                for row in (_debt.gather(folder).get(side) or ()):
                    if row.get('balance') is not None:
                        got[round(row['balance'], 2)] = row.get('maturity')
        except Exception:
            got = {}
        _MATURITY[folder] = got
    year = _MATURITY[folder].get(round(balance, 2)) if balance else None
    if not year:
        return 'not stated'
    if year > datetime.date.today().year + 40:
        return 'revolving'
    return str(year)


_CASH = {}


def _cash_flow(folder):
    """The cash flow figures, computed once per folder."""
    if _cashflow is None:
        return None
    if folder not in _CASH:
        try:
            _CASH[folder] = _cashflow.for_assumptions(folder)
        except Exception:
            _CASH[folder] = None
    return _CASH[folder]


def _amount(text):
    """A printed amount back to a number, or None for 'not valued'."""
    if not text:
        return None
    cleaned = str(text).replace(',', '').replace('$', '').strip()
    neg = cleaned.startswith('(') and cleaned.endswith(')')
    cleaned = cleaned.strip('()')
    try:
        v = float(cleaned)
    except ValueError:
        return None
    return -v if neg else v


# Which sections roll into which line of the closing summary. Debt is listed
# as a subtraction rather than given a sign here, so the page shows it the way
# a balance sheet does.
SUMMARY = (('Real estate', (3,), False),
           ('Practice', (6,), False),
           ('Investable assets', (4, 5), False),
           ('Debt', (8, 9), True))


def summarise(sections):
    """The closing balance sheet, totalled from what the page already prints.

    Deliberately derived from the rendered rows rather than recomputed from
    the readers. If a section is wrong, the summary is wrong in the same way,
    which is the point: a summary that quietly disagrees with the table above
    it is worse than no summary, because the reader cannot tell which of the
    two to believe. Rows marked as their table's own total are skipped so
    they are not counted twice, and a row with no figure ("not valued")
    contributes nothing but is counted as missing.
    """
    by_number = {s.number: s for s in sections}
    lines, missing = [], 0
    for label, numbers, subtract in SUMMARY:
        total, seen = 0.0, False
        for number in numbers:
            sec = by_number.get(number)
            if not sec:
                continue
            if sec.value is not None:
                total += sec.value
                seen = True
            for row in getattr(sec, 'rows', ()) or ():
                if row.get('rule'):
                    continue
                v = _amount(row.get('amount'))
                if v is None:
                    missing += 1
                else:
                    total += v
                    seen = True
        if seen:
            lines.append((label, -total if subtract else total))
    net = sum(v for _l, v in lines)
    return lines, net, missing


def _in_block(bundle, fact, title):
    for block in bundle.blocks:
        if block.title == title and fact in block.facts:
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description='Draft the Assumptions base plan')
    ap.add_argument('folder')
    ap.add_argument('--client', default=None)
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    bundle = _facts.gather(a.folder, client=a.client)
    sections = build(bundle, a.folder)

    if a.json:
        print(json.dumps([{'number': s.number, 'text': s.text,
                           'needed': s.needed, 'why': s.why,
                           'source': s.source} for s in sections], indent=1))
        return

    print('ASSUMPTIONS — BASE PLAN — %s\n' % bundle.client)
    for s in sections:
        if s.complete:
            print('%2d. %s' % (s.number, s.text))
            if s.source:
                print('    [%s]' % s.source)
        else:
            print('%2d. NEEDS: %s' % (s.number, s.needed))
            print('    why: %s' % s.why)
        print()
    done = sum(1 for s in sections if s.complete)
    print('%d of %d sections written from documents' % (done, len(sections)))


if __name__ == '__main__':
    main()
