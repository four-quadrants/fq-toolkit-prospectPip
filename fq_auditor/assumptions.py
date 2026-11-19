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
import re
import sys
import json
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import facts as _facts                                       # noqa: E402
import compose as _compose                                   # noqa: E402
import inputs as _inputs                                     # noqa: E402
import store as _store                                       # noqa: E402

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
        # How the figures were worked out, one step a line, with this
        # client's own numbers ("revenue x 65% = practice value"). Shown on
        # the review page under the section, closed until opened.
        self.workings = []

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


def _long_date(iso):
    """2026-10-08 as October 8, 2026; anything else as given."""
    try:
        d = datetime.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    return '%s %d, %d' % (d.strftime('%B'), d.day, d.year)


def _w2_rows(folder, wages):
    """The Income assumption's W-2 lines, one per household member.

    Paystubs first (doc_readings "pay": gross for one period times the
    periods a year, each gross checked on the stub), with that person's W-2
    beside it when the returns were read (income_facts). Without paystubs,
    one line per W-2 read (owner, then spouse). Without either, the P&L's
    doctor wages as one line, as before. Each row carries '_v', the figure
    the total adds.
    """
    grow = 'Grown at the %.1f%% inflation rate until retirement.' % FIRM['inflation']
    try:
        with open(_store.json_path(folder, 'income_facts.json')) as fh:
            f = json.load(fh)
    except (OSError, ValueError, AttributeError):
        f = {}
    owner = os.path.basename(folder.rstrip('/')).split(' - ')[0]
    owner_first = (owner.split(',')[1].split() or [''])[0] if ',' in owner else ''
    spouse = (f.get('spouse_name') or '').split(' ')[0]
    w2_of = {}
    if owner_first and f.get('w2'):
        w2_of[owner_first.lower()] = f['w2']
    if spouse and f.get('spouse_w2'):
        w2_of[spouse.lower()] = f['spouse_w2']
    yr = f.get('year')
    try:
        import doc_readings as _dr
        pay = (_dr.check(folder)[0] or {}).get('pay') or []
    except Exception:                                        # noqa: BLE001
        pay = []

    def first_of(name):
        # "Example, Jane M" or "Jane Example"
        if ',' in name:
            bits = name.split(',', 1)[1].split()
        else:
            bits = name.split()
        return bits[0] if bits else name

    def display(name):
        if ',' in name:
            last, rest = name.split(',', 1)
            return '%s %s' % (first_of(name), last.strip().title())
        return name

    rows = []
    if pay:
        # The owner first, then the rest as the stubs list them.
        pay = sorted(pay, key=lambda p: first_of(p['name']).lower() != owner_first.lower())
        for p in pay:
            per = {12: 'month', 24: 'half-month', 26: 'two weeks', 52: 'week'}[p['periods']]
            bits = ['%s a pay period (every %s) times %d, from the paystub of %s.'
                    % (_money(p['gross'], pence=True), per, p['periods'],
                       _long_date(p.get('pay_date')) or 'the latest stub')]
            w2 = w2_of.get(first_of(p['name']).lower())
            if w2:
                bits.append('%s W-2: %s.' % (yr or 'Last year\'s', _money(w2)))
            if first_of(p['name']).lower() == owner_first.lower():
                bits.append(grow)
            rows.append({'label': '%s, W-2 wages' % display(p['name']),
                         'amount': _money(p['annual']), 'detail': ' '.join(bits),
                         '_v': p['annual'], '_stub': True,
                         '_owner': first_of(p['name']).lower() == owner_first.lower()})
        return rows
    # No paystubs: the owner's wages stay the P&L's (as before), named, and
    # a spouse's W-2 read from the returns gets its own line.
    surname = owner.split(',')[0].strip()
    rows.append({'label': ('%s %s, W-2 wages' % (owner_first, surname)).strip()
                 if owner_first else 'W-2 wages from the practice',
                 'amount': _money(wages), 'detail': grow, '_v': wages})
    if spouse and f.get('spouse_w2'):
        rows.append({'label': '%s, W-2 wages' % spouse,
                     'amount': _money(f['spouse_w2']),
                     'detail': 'Read from the %s returns.' % (yr or 'latest'),
                     '_v': f['spouse_w2']})
    return rows


def paid_off_rows(folder, cash):
    """The cash flow's fixed liability payments for loans paid off since the
    statements (the 'paid_off' input): [(payee, monthly, kind, keyword)].
    Their payments have stopped, so the spending figure that includes the
    fixed payments leaves them out, here and in the projection alike."""
    gone = (_inputs.get(folder, 'paid_off') or {}).get('value') or {}
    out = []
    for r in (cash or {}).get('fixed_rows') or ():
        if r[2] != 'Liability':
            continue
        k = next((k for k in gone if k.lower() in r[0].lower()), None)
        if k:
            out.append((r[0], r[1], r[2], k))
    return out


def _money_num(v):
    """A typed dollar figure as a number ('$399,818' -> 399818.0), else None."""
    if v is None or v == '':
        return None
    try:
        return float(str(v).replace('$', '').replace(',', '').strip())
    except ValueError:
        return None


def _ic_saved(saved):
    """The IC form's 'saved last year' answer as dollars a year, or None
    when it has no figure in it ("Max allowed in plans" is intent, not an
    amount). "40K" is 40,000."""
    m = re.search(r'\$?\s*([\d,.]+)\s*([kK])?', str(saved or ''))
    if not m or not any(c.isdigit() for c in m.group(1)):
        return None
    try:
        v = float(m.group(1).replace(',', '')) * (1000 if m.group(2) else 1)
    except ValueError:
        return None
    return v if v >= 1000 else None


def contributions(folder, saved=None):
    """What is going into investable assets each year, by account, for the
    Contributions assumption and the plan's 'saved a year today'.

    The lead advisor's rule: the paystubs, annualized (each retirement
    deduction for the period times the pay periods a year), plus what the
    investment and plan statements show going in, annualized from the
    months they cover. Without paystubs, the IC form's figure until the
    paystubs come in. Only when neither gives a figure, the 401(k)
    deferrals on the last W-2s. The W-2 figures sit beside the paystub
    lines as a check.

    None, or {'rows', 'total', 'from', 'source', 'workings', 'basis'} where
    basis is 'paystubs', 'ic' or 'w2'."""
    try:
        import doc_readings as _dr
        got = _dr.check(folder)[0] or {}
    except Exception:                                        # noqa: BLE001
        got = {}
    try:
        with open(_store.json_path(folder, 'income_facts.json')) as fh:
            inf = json.load(fh)
    except (OSError, ValueError, AttributeError):
        inf = {}
    owner = os.path.basename(folder.rstrip('/')).split(' - ')[0]
    owner_first = (owner.split(',')[1].split() or [''])[0] if ',' in owner else ''
    spouse_first = (inf.get('spouse_name') or '').split(' ')[0]
    w2_def = {}
    if owner_first and inf.get('deferral'):
        w2_def[owner_first.lower()] = inf['deferral']
    if spouse_first and inf.get('spouse_deferral'):
        w2_def[spouse_first.lower()] = inf['spouse_deferral']

    def first_of(name):
        bits = name.split(',', 1)[1].split() if ',' in name else name.split()
        return bits[0] if bits else name

    per_word = {12: 'month', 24: 'half-month', 26: 'two weeks', 52: 'week'}
    rows, steps = [], []
    pay = [p for p in (got.get('pay') or ()) if p.get('deferrals')]
    pay.sort(key=lambda p: first_of(p['name']).lower() != owner_first.lower())
    for p in pay:
        who = first_of(p['name'])
        for d in p['deferrals']:
            bits = ['%s a pay period (every %s) times %d, from the paystub of %s.'
                    % (_money(d['amount'], pence=True), per_word[p['periods']], p['periods'],
                       _long_date(p.get('pay_date')) or 'the latest stub')]
            w2 = w2_def.get(who.lower())
            if w2:
                bits.append('%s W-2: %s.' % (inf.get('year') or 'Last year\'s', _money(w2)))
            rows.append({'label': '%s %s: employee deferral' % (who, d['kind']),
                         'amount': _money(d['annual']), 'detail': ' '.join(bits),
                         '_v': d['annual']})
            steps.append('%s %s: %s x %d pay periods = %s.'
                         % (who, d['kind'], _money(d['amount'], pence=True), p['periods'],
                            _money(d['annual'])))
    if rows:
        for c in got.get('contributions') or ():
            what = {'employer': 'employer contribution', 'personal': 'contribution'}.get(
                c.get('kind'), 'contribution')
            rows.append({'label': '%s: %s' % (c.get('account') or 'Account', what),
                         'amount': _money(c['annual']),
                         'detail': '%s in over %s (%s), from %s.'
                                   % (_money(c['amount'], pence=True),
                                      '%g months' % c['months'], c.get('period') or 'the statement',
                                      c.get('source')),
                         '_v': c['annual']})
            steps.append('%s: %s over %g months x 12 / %g = %s.'
                         % (c.get('account'), _money(c['amount'], pence=True), c['months'],
                            c['months'], _money(c['annual'])))
        total = sum(r['_v'] for r in rows)
        if len(rows) > 1:
            steps.append('Total a year: %s = %s.' % (' + '.join(r['amount'] for r in rows),
                                                     _money(total)))
        stmts = bool(got.get('contributions'))
        return {'rows': rows, 'total': total, 'basis': 'paystubs', 'workings': steps,
                'from': 'the paystubs, annualized%s (%s)'
                        % (' and the investment statements' if stmts else '',
                           ' + '.join(r['amount'] for r in rows)),
                'source': 'Paystubs, annualized%s; the W-2s beside them as a check.'
                          % (', and the investment statements' if stmts else '')}
    ic = _ic_saved(saved)
    if ic:
        return {'rows': [], 'total': ic, 'basis': 'ic', 'workings': [],
                'from': 'the IC form ("%s"), until the paystubs come in' % str(saved).strip(),
                'source': 'IC form, until the paystubs come in.'}
    defs = [(n, v) for n, v in ((owner_first, inf.get('deferral')),
                                (spouse_first or 'Spouse', inf.get('spouse_deferral'))) if v]
    if defs:
        kind = 'Roth 401(k)' if str(inf.get('deferral_kind') or '').lower() == 'roth' else '401(k)'
        src = inf.get('sources') or {}
        rows = [{'label': '%s %s: employee deferral' % (n, kind), 'amount': _money(v),
                 'detail': '%s W-2%s.' % (inf.get('year') or 'Latest',
                                          (', ' + src.get(k)) if src.get(k) else ''),
                 '_v': float(v)}
                for (n, v), k in zip(defs, ('deferral', 'spouse_deferral'))]
        total = sum(r['_v'] for r in rows)
        return {'rows': rows, 'total': total, 'basis': 'w2',
                'workings': (['Total a year: %s = %s.' % (' + '.join(r['amount'] for r in rows),
                                                          _money(total))] if len(rows) > 1 else []),
                'from': 'the 401(k) deferrals on the %s W-2s (%s), until the paystubs come in'
                        % (inf.get('year') or 'latest', ' + '.join(r['amount'] for r in rows)),
                'source': 'W-2s, until the paystubs come in.'}
    return None


def _net_distributions(folder):
    """Money the owner actually takes home from the practice, a year: every
    transfer from a practice account to a personal one, less every transfer
    the other way (money put back in). Shown under Income but never added to
    Total earnings, which already counts the net profit it comes out of.

    Read from the bank statements' transactions, counted once: on the
    personal side where that account's statements were read, else on the
    practice side. Annualized over the months the statements cover. Returns
    (annual or None, detail).
    """
    try:
        import transactions as _tx
        sides, banks = _tx.sides_of(folder), _tx.banks_of(folder)
        moves = _tx.gather(folder)
        for k in moves:
            _tx.apply_rules(moves[k], sides, banks)
        _tx.match_across(moves)
    except Exception:                                        # noqa: BLE001
        moves, sides = {}, {}
    read = {_tx_digits(k[1]) for k, rows in moves.items() if rows}
    dist = back = 0.0
    dates = []
    for (side, key), rows in moves.items():
        for r in rows:
            if r.get('date'):
                dates.append(r['date'])
            if r.get('kind') != 'transfer' or not r.get('amount'):
                continue
            here = sides.get(_tx_digits(r.get('account')) or _tx_digits(key))
            cp = _tx_digits(r.get('counterparty') or '')
            there = sides.get(cp)
            if {here, there} != {'Personal', 'Business'}:
                continue
            if here == 'Business' and cp in read:
                continue        # counted on the personal statement instead
            out_of_practice = (here == 'Personal' and r['direction'] == 'credit') or \
                              (here == 'Business' and r['direction'] == 'debit')
            if out_of_practice:
                dist += r['amount']
            else:
                back += r['amount']
    months = None
    if dates:
        months = max(1.0, ((max(dates) - min(dates)).days + 1) / 30.44)
    try:
        with open(_store.json_path(folder, 'income_facts.json')) as fh:
            f = json.load(fh)
    except (OSError, ValueError, AttributeError):
        f = {}
    ret = f.get('distributions')
    ret_txt = (' The %s return shows distributions of %s.' % (f.get('year') or 'latest',
                                                             _money(ret))) if ret else ''
    if (dist or back) and months:
        annual = (dist - back) * 12.0 / months
        return annual, ('Practice to personal %s, less %s put back into the '
                        'practice, over %.0f months of statements, annualized.%s '
                        'Not added to the total: it comes out of the net profit.'
                        % (_money(dist), _money(back), months, ret_txt))
    if ret:
        return ret, ('No transfers between the practice and personal accounts '
                     'found on the statements, so this is the return\'s figure.%s '
                     'Not added to the total: it comes out of the net profit.'
                     % ret_txt)
    return None, ('No transfers between the practice and personal accounts were '
                  'found on the statements, and the return shows none. Ask how '
                  'the owner takes money out of the practice.')


def _tx_digits(v):
    return ''.join(c for c in str(v or '') if c.isdigit())[-4:]


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



def _born(text):
    """A birthdate typed MM/DD/YYYY (or M-D-YY) as (MM/DD/YYYY, age today), else (None, None)."""
    try:
        mo, dd, yy = [int(x) for x in re.split(r'[/-]', str(text).strip())]
    except (ValueError, TypeError, AttributeError):
        return None, None
    if yy < 100:
        yy += 1900 if yy > 30 else 2000
    today = datetime.date.today()
    age = today.year - yy - ((today.month, today.day) < (mo, dd))
    return '%02d/%02d/%d' % (mo, dd, yy), age


def premises_word(bundle, folder):
    """'condo' or 'building': the team's word ('premises' in the input
    store) first, then what the documents showed (the Office location fact)."""
    return str(_inputs.value(folder, 'premises') or '').strip().lower() or (
        'condo' if 'owns the condo' in str(_value(bundle, 'Office location') or '')
        else 'building')


def _partner(bundle, folder):
    """The second person the plan covers, or None when the client is single.

    {'name', 'age', 'retire_age', 'source'}. Age from the input store
    ('spouse_age', typed by the team) first, then the IC form. Name from the
    input store ('spouse_name'), then the W-2s read (income_facts). Retirement
    age only when the team typed one ('spouse_retire_age').
    """
    status = str(_value(bundle, 'Marital status') or '').lower()
    # A birthdate beats a stated age: typed by the team ('spouse_birthdate',
    # MM/DD/YYYY), the age it gives today.
    born, born_age = _born(_inputs.value(folder, 'spouse_birthdate'))
    typed_age = born_age or _inputs.value(folder, 'spouse_age')
    form_age = _value(bundle, 'Spouse age')
    if not (typed_age or form_age or 'married' in status or 'partner' in status):
        return None
    if status and 'married' not in status and 'partner' not in status \
            and not typed_age:
        return None

    def _n(v):
        if v is None:
            return None
        m = re.search(r'\d{2}', str(v))
        return float(m.group(0)) if m else None
    age = _n(typed_age) or _n(form_age)
    try:
        with open(_store.json_path(folder, 'income_facts.json')) as fh:
            inf = json.load(fh)
    except (OSError, ValueError, AttributeError):
        inf = {}
    name = (_inputs.value(folder, 'spouse_name') or inf.get('spouse_name') or '')
    name = str(name).split(' ')[0] or None
    return {'name': name, 'age': age, 'born': born,
            'retire_age': _n(_inputs.value(folder, 'spouse_retire_age')),
            'source': ('born %s' % born) if born_age else
                      ('typed by the team' if _n(typed_age) else 'IC form')}


def _m(v):
    """Money for a working line: whole dollars, a minus sign when negative."""
    return ('-' if v < 0 else '') + _money(abs(v))


def _payoff(balance, note):
    """(rate %, payment, months) behind an estimated payoff, else None."""
    import math
    rate = re.search(r'(\d+(?:\.\d+)?)%', note or '')
    pay = re.search(r'\$?([\d,]+(?:\.\d+)?)/mo', note or '')
    if not (rate and pay and balance):
        return None
    r = float(rate.group(1)) / 100 / 12
    P = float(pay.group(1).replace(',', ''))
    B = float(balance)
    if P <= 0:
        return None
    if r == 0:
        return float(rate.group(1)), P, B / P
    if r * B >= P:
        return None
    return float(rate.group(1)), P, -math.log(1 - r * B / P) / math.log(1 + r)


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
    # A birthdate beats the stated age: typed by the team ('birthdate'), or
    # read from the IC form, the call notes or the portal (the Birthdate fact).
    owner_born, born_age = _born(_inputs.value(folder, 'birthdate')
                                 or _value(bundle, 'Birthdate'))
    if born_age:
        age = float(born_age)
    if isinstance(age, str):
        m = re.search(r'\b(\d{2})\b', age)
        age = float(m.group(1)) if m else None
    end = (this_year + int(FIRM['life_expectancy'] - age)) if age else None
    # A plan for two people (the lead advisor's rule): the spouse's age and
    # life expectancy are stated beside the owner's, and the plan runs to the
    # later of the two. The age comes from the IC form ("How old is your
    # spouse?") or, when the team typed one, the input store; the name from
    # the W-2s read (income_facts) or the input store.
    partner = _partner(bundle, folder)
    end_partner = None
    if partner and partner.get('age'):
        end_partner = this_year + int(FIRM['life_expectancy'] - partner['age'])
    plan_end = max([y for y in (end, end_partner) if y] or [None]) if (end or end_partner) else None
    out.append(Section(1,
        'We have employed an inflation rate of %.1f%% annually over the life '
        'of the plan (%d-%s).' % (FIRM['inflation'], this_year, plan_end or '----'),
        source='firm standard'))

    # 2 ---------------------------------------------------------------------
    retire_at = _value(bundle, 'Retirement age goal')
    if isinstance(retire_at, str):
        # The IC form's own words ("60-62, depends on the practice"): the
        # first age in them, or nothing to compute from.
        # "down to 3 days by 55 and able to walk away by 65": the last age
        # named is when they stop, so the largest one
        ages = [float(x) for x in re.findall(r'\b([4-8]\d)\b', retire_at)]
        retire_at = max(ages) if ages else None
    said = 'IC form'
    if not retire_at:
        # "ASAP" on the form: the age agreed on a call wins, from the
        # summary's projection (what the analyst wrote from the call notes)
        # or the advisor's input.
        try:
            import json as _json
            import inputs as _inp
            got = _inp.value(folder, 'retire_age')
            if not got:
                with open(_store.json_path(folder, "summary.json")) as fh:
                    got = (_json.load(fh).get('projection') or {}).get('retire_age')
            if got:
                retire_at, said = float(got), 'the call notes'
        except Exception:                                    # noqa: BLE001
            pass
    if age and retire_at:
        year_of = this_year + int(retire_at - age)
        # The corpus wording, unchanged in all 44 plans: given name, the year,
        # the age, then the life expectancy in brackets. Year only, because
        # the firm's plans assume a year-end exit and the IC form carries an
        # age rather than a birth date.
        who = bundle.forename or 'the client'
        if partner and partner.get('age'):
            # Two people: each one's retirement and life expectancy. Without
            # a goal of their own, the spouse stops the same year as the
            # owner, at whatever age that makes them.
            p_name = partner.get('name') or 'their spouse'
            p_retire = partner.get('retire_age')
            p_said = 'retirement age %d typed by the team' % p_retire if p_retire else \
                'no retirement age of their own, so the same year as %s' % who
            p_year = (this_year + int(p_retire - partner['age'])) if p_retire else year_of
            p_retire = p_retire or (partner['age'] + (year_of - this_year))
            text = ('We assume that %s is set to retire in %d, at an age of %d, '
                    'and %s in %d, at an age of %d. Life expectancy used for '
                    'this plan is age %d for both (%s for %s and %s for %s).'
                    % (who, year_of, retire_at, p_name, p_year, p_retire,
                       FIRM['life_expectancy'], end, who, end_partner, p_name))
            source = ('%s: age %d, retirement age goal %d. %s: age %d (%s), %s.'
                      % (said, age, retire_at, p_name, partner['age'],
                         partner.get('source') or 'IC form', p_said))
            out.append(Section(2, text, source=source))
        else:
            out.append(Section(2,
                'We assume that %s is set to retire in %d, at an age of %d. Life '
                'expectancy used for this plan is age %d (%s).'
                % (who, year_of, retire_at, FIRM['life_expectancy'], end),
                source='%s: age %d, retirement age goal %d.'
                       % (said, age, retire_at)))
        if owner_born:
            out[-1].source = out[-1].source.replace(
                '%s: age %d,' % (said, age),
                '%s: age %d (born %s),' % (said, age, owner_born), 1)
        flags = []
        if partner and not partner.get('age'):
            flags.append('Married, but the spouse\u2019s age is not on file: '
                         'add it so the plan covers both of them.')
        # The lead advisor's rule: the analyst enters exact birthdates at the
        # first check of the Assumptions, so every age is worked out from a
        # date rather than an age typed on a form.
        missing = []
        if not owner_born:
            missing.append(who)
        if partner and not partner.get('born'):
            missing.append(partner.get('name') or 'the spouse')
        if missing:
            flags.append('Birthdate%s needed for %s: add %s as a Note on this '
                         'section (MM/DD/YYYY) and %s recorded when the check '
                         'is pulled in. Until then the age comes from the IC '
                         'form.' % (('s', ' and '.join(missing), 'them', 'they are')
                                    if len(missing) > 1 else
                                    ('', missing[0], 'it', 'it is')))
        if flags:
            out[-1].flag = '  '.join(flags)
        # How sections 1 and 2 were worked out.
        le = FIRM['life_expectancy']
        n = int(retire_at - age)
        w1 = ['%s is %d today%s. Life expectancy %d: %d + (%d - %d) = %d.'
              % (who, age, ' (born %s)' % owner_born if owner_born else '',
                 le, this_year, le, age, end)]
        w2 = ['%s: retirement age %d less age today %d = %d years. %d + %d = %d.'
              % (who, retire_at, age, n, this_year, n, year_of)]
        if partner and partner.get('age'):
            pa = partner['age']
            w1.append('%s is %d today%s. %d + (%d - %d) = %d.'
                      % (p_name, pa, ' (born %s)' % partner['born'] if partner.get('born') else '',
                         this_year, le, pa, end_partner))
            w1.append('The plan runs to the later of the two: %s.' % plan_end)
            if partner.get('retire_age'):
                pn = int(partner['retire_age'] - pa)
                w2.append('%s: retirement age %d less age today %d = %d years. %d + %d = %d.'
                          % (p_name, partner['retire_age'], pa, pn, this_year, pn, p_year))
            else:
                w2.append('%s: no retirement age given, so the same year as %s, %d. Age today '
                          '%d + %d years = %d.' % (p_name, who, year_of, pa, n, p_retire))
        out[0].workings = w1
        out[-1].workings = w2
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
    home_link = None
    if not props:
        home = _compose.residence_full(folder)
        val = _inputs.get(folder, 'residence_value')
        if home and val and val.get('value'):
            street, town, state = home
            props = [{'label': '%s, %s' % (town, state),
                      'amount': _money(val['value']),
                      'basis': '%s. %s' % (street, val.get('note') or
                                           _inputs.cite(val, 'Zillow.com'))}]
        elif home:
            # The address is in the documents (statements mailed home, the
            # returns, the credit report): show it, with the Zillow link,
            # and ask only for the value. Asking the client for an address
            # we already have reads as not having looked.
            street, town, state = home
            home_link = _zillow_link(street, town, state)
            props = [{'label': '%s, %s' % (town, state), 'amount': None,
                      'basis': '%s (the home address on the documents). Current '
                               'market value needed: the Zillow link below.' % street}]
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
        if home_link:
            out[-1].link = home_link
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
    try:
        import accounts as _accounts
        _accounts.ensure(folder, log=lambda *_a: None)
    except Exception:                                        # noqa: BLE001
        pass

    def _listing(key, number, heading, missing_need, missing_why):
        got = _inputs.get(folder, key)
        rows = (got or {}).get('value') or []
        if not rows:
            return Section(number, needed=missing_need, why=missing_why)
        # Every row says where its value came from and what the account
        # holds. A value typed from a screenshot or an advisor's summary
        # carries no holdings, and the row says so rather than sitting
        # blank, so the gap is chased instead of missed.
        src_by = (got or {}).get('by') or ''
        as_of = (got or {}).get('as_of') or ''
        bare = 0

        def _detail(r):
            nonlocal bare
            if (r.get('basis') or '').strip():
                return r['basis']
            bare += 1
            return ('Value only%s%s; what the account holds is not on file '
                    '(the statement with its holdings is needed).'
                    % (', from %s' % src_by if src_by else '',
                       ' as of %s' % as_of if as_of else ''))
        def _amt(r):
            v = r.get('amount')
            if isinstance(v, (int, float)):
                return _money(v)
            return v or _money(r.get('value'))
        listed = [{'label': r.get('label'), 'amount': _amt(r),
                   'detail': _detail(r)} for r in rows]
        flag = (got or {}).get('flag')
        if bare:
            flag = ((flag + '  ') if flag else '') + (
                '%d account%s %s a value but no holdings: ask for the latest '
                'full statement%s.' % (bare, '' if bare == 1 else 's',
                                      'has' if bare == 1 else 'have',
                                      '' if bare == 1 else 's'))
        return Section(number,
            'Below is a list of all %s investable assets that %s currently '
            'owns, along with their respective market values.'
            % (heading, bundle.forename or 'the client'),
            rows=listed,
            source=(got or {}).get('note') or src_by or 'account statements',
            flag=flag)

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
        tails = {}
        for a in cash['accounts']:
            m = re.search(r'x(\d{4})', a['name']) or re.search(r'(\d{4})', a['name'])
            if m:
                tails.setdefault(m.group(1), []).append(a)
        def _who(a):
            # "Practice checking: x8478 (Fifth Third)". Whose account and what
            # kind come first, because that is what the reader sorts by.
            side = {'Personal': 'Personal',
                    'Rental properties': 'Rental',
                    'Children\u2019s accounts': 'Child\u2019s'}.get(a.get('entity'), 'Practice')
            kind = (a.get('kind') or 'account').lower()
            return '%s %s: %s' % (side, kind, a['name'])
        for a in cash['accounts']:
            m = re.search(r'x(\d{4})', a['name']) or re.search(r'(\d{4})', a['name'])
            # One account, two readings: Oyler's Eden account x3309 came out
            # once under the practice (unreadable) and once on its own tab.
            if m and not a['readable'] and any(
                    o['readable'] for o in tails.get(m.group(1), ())):
                continue
            if not a['readable']:
                unread.append(a['name'])
                listed.append({'label': _who(a),
                               'amount': _money(a['balance']),
                               'basis': 'Balance only. %s' % a['why']})
                continue
            # A known move since the last statement (the team's
            # 'balance_adjust' input, by last four digits): the balance is
            # moved by it and the row says why.
            adj = ((_inputs.get(folder, 'balance_adjust') or {}).get('value') or {}).get(
                m.group(1) if m else '') or {}
            if adj.get('amount'):
                a = dict(a, balance=a['balance'] + float(adj['amount']))
            listed.append({
                'label': _who(a),
                'amount': _money(a['balance']),
                'basis': ((adj.get('note') + ' ') if adj.get('note') else '') +
                         'Average deposit %s, average expense %s, average '
                         '%s %s, across %d statement period%s.'
                         % (_money(a['deposit']), _money(abs(a['expense'])
                                                         if abs(a['expense']) < 0.5
                                                         else a['expense']),
                            'surplus' if a['surplus'] >= 0 else 'deficit',
                            _money(abs(a['surplus'])), a['periods'],
                            '' if a['periods'] == 1 else 's')})
        # What the statements reader does not cover: brokerage and private
        # holdings recorded in the input store (Oyler's $408,526 at Reef,
        # the Bitcoin named in the decree). The bank-account rows replaced
        # the whole listing and dropped these.
        have = set(tails)
        for r in ((_inputs.get(folder, 'nonqualified_accounts') or {})
                  .get('value') or []):
            m = re.search(r'x(\d{4})', str(r.get('label') or ''))
            if m and m.group(1) in have:
                continue
            # Same rule as sections 4: a figure as money, and a row with no
            # holdings says so rather than sitting blank.
            amt = r.get('amount')
            amt = _money(amt) if isinstance(amt, (int, float)) else (amt or _money(r.get('value')))
            got5 = _inputs.get(folder, 'nonqualified_accounts') or {}
            basis = (r.get('basis') or '').strip() or (
                'Value only%s%s; what the account holds is not on file (the '
                'statement with its holdings is needed).'
                % (', from %s' % got5['by'] if got5.get('by') else '',
                   ' as of %s' % got5['as_of'] if got5.get('as_of') else ''))
            listed.append({'label': r.get('label'), 'amount': amt, 'basis': basis})
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
    # An HSA is a qualified account wherever it was read from (the bank
    # statements, a typed entry, the investment statements): it is listed in
    # section 4 with the retirement accounts, never in section 5.
    hsa_re = re.compile(r'\bhsa\b|health savings', re.I)
    sec4 = next((x for x in out if x.number == 4), None)
    moved = [r for r in (rows.rows or []) if hsa_re.search(str(r.get('label') or ''))]
    if moved and sec4 is not None:
        rows.rows = [r for r in rows.rows if r not in moved]
        have4 = {str(r.get('label')) for r in sec4.rows}
        new = [r for r in moved if str(r.get('label')) not in have4]
        if new:
            if not sec4.rows:
                sec4.text = ('Below is a list of all QUALIFIED investable assets that %s currently '
                             'owns, along with their respective market values.'
                             % (bundle.forename or 'the client'))
                sec4.needed = sec4.why = None
                sec4.source = sec4.source or 'account statements'
            sec4.rows = sec4.rows + new
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
        # Two growth rates, one per path (the lead advisor's rule): 3% on
        # the current path, 4% on the 4Q path, as typed on the review page's
        # Plan inputs where he changed them.
        try:
            import deck as _deck
            adv = _deck._advisor(folder)
        except Exception:                                    # noqa: BLE001
            adv = {}

        def _g(key, default):
            try:
                v = float(str(adv.get(key)).replace('%', ''))
            except (TypeError, ValueError):
                return default
            return v / 100.0 if v > 1 else v
        gc, gq = _g('practice_growth', 0.03), _g('practice_growth_fq', 0.04)
        try:
            years_to = int(float(retire_at) - float(age)) if (age and retire_at) else None
        except (TypeError, ValueError):
            years_to = None
        out[-1].rows = [
            {'label': 'Growth a year, current path', 'amount': '%.1f%%' % (gc * 100),
             'detail': 'Grown to %s at retirement.' % _money(value * (1 + gc) ** max(0, years_to))
             if years_to else None},
            {'label': 'Growth a year, 4Q path', 'amount': '%.1f%%' % (gq * 100),
             'detail': 'Grown to %s at retirement.' % _money(value * (1 + gq) ** max(0, years_to))
             if years_to else None}]
        out[-1].heads = ('Practice value', 'Rate')
        out[-1].workings = ['%s revenue %s x %d%% (the firm multiple) = %s.'
                            % (basis_year, _m(revenue), FIRM['practice_value_multiple'] * 100,
                               _m(value))]
        if years_to:
            for name, g in (('Current path', gc), ('4Q path', gq)):
                out[-1].workings.append('%s: %s x (1 + %.1f%%) ^ %d years to retirement = %s.'
                                        % (name, _m(value), g * 100, years_to,
                                           _m(value * (1 + g) ** years_to)))
        out[-1].text = re.sub(r'scheduled to grow at [\d.]+% annually',
                              'scheduled to grow at %s annually on the current path and '
                              '%s with 4Q,' % (('%.1f' % (gc * 100)).rstrip('0').rstrip('.') + '%',
                                              ('%.1f' % (gq * 100)).rstrip('0').rstrip('.') + '%'),
                              out[-1].text)
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
    # Building or condo: the team's word ('premises' in the input store)
    # first, then what the documents showed (the Office location fact).
    place = premises_word(bundle, folder)
    lead = ('We show that %s owns the practice %s%s.'
            % (bundle.forename or 'the client', place,
               (' ' + ' '.join(bits)) if bits else ''))
    rent = _ic.money(form.get('building_payment'))
    if rent:
        lead += (' The practice pays rent of %s per month, which is an '
                 'expense of the practice and income to %s.'
                 % (_money(rent), bundle.forename or 'the client'))
    out.append(Section(7,
        text=lead,
        needed='a current value for the practice %s' % place,
        # This used to be Oyler's own findings, word for word, printed on
        # every client's plan: "Brian owns it personally ... Form 8825 rental
        # totals are zero ... Zillow has no record of the parcel." Rebol's
        # plan said Brian. Only what holds for any client belongs here.
        why='Held outside the practice, so it sits in the plan alongside it '
            'and is usually sold with it or leased on afterwards. A %s '
            'the practice rents is not on the practice’s books at its value, '
            'so a county assessment, an appraisal or a Zillow estimate is the '
            'source.' % place,
        flag=_flag(folder, 7)))
    out[-1].title = 'Practice %s' % place
    # A value the team recorded (a broker opinion, an appraisal, the county):
    # stated with its source, and the section is no longer waiting on it.
    bval = _inputs.get(folder, 'building_value')
    if bval and bval.get('value'):
        out[-1].text = lead + (' The %s is valued at %s and is assumed to grow '
                               'at 2%% a year, to be sold with the practice at '
                               'retirement.' % (place, _money(float(bval['value']))))
        out[-1].needed = None
        out[-1].why = None
        out[-1].value = float(bval['value'])
        out[-1].source = bval.get('note') or _inputs.cite(bval, 'the team')
        try:
            yrs7 = int(float(retire_at) - float(age)) if (age and retire_at) else None
        except (TypeError, ValueError):
            yrs7 = None
        if yrs7:
            v7 = float(bval['value'])
            out[-1].workings = ['%s x (1 + 2%%) ^ %d years to retirement = %s at the sale.'
                                % (_m(v7), yrs7, _m(v7 * 1.02 ** yrs7))]
    # Rented, not owned: the IC form says "Rent" and nobody has recorded a
    # building value. The section said every client owned the building,
    # which put a building that is not theirs into the plan as missing.
    rents = str(form.get('building') or '').strip().lower().startswith('rent') or \
        re.search(r'\brent\b', str(_value(bundle, 'Office location') or ''), re.I)
    if rents and not (bval and bval.get('value')):
        where = (' ' + ' '.join(bits)) if bits else ''
        sec = out[-1]
        sec.title = 'Practice office'
        sec.text = ('%s rents the practice office%s%s. The building is not '
                    'owned by the household, so it is not in the plan.'
                    % (bundle.forename or 'The client', where,
                       (' for %s per month' % _money(rent)) if rent else ''))
        sec.needed = sec.why = sec.link = None
        sec.source = 'IC form ("Do you rent or own the building?": Rent).'

    # 8 and 9 ---------------------------------------------------------------
    for number, block, label in ((8, 'Personal debt', 'personal and rental '
                                                      'property'),
                                 (9, 'Practice debt', 'practice')):
        rows = [f for f in bundle.all_facts()
                if _in_block(bundle, f, block) and f.value is not None
                and not f.label.startswith(('Practice total', 'Personal total',
                                            'Practice debt service',
                                            'Personal debt service',
                                            'Practice debt', 'Personal debt',
                                            'Building (LLC) total',
                                            'Building (LLC) debt service',
                                            'Practice + building'))]
        extra = []
        if number == 8 and cash:
            # Loans the bank statements show being paid but no schedule or
            # lender statement lists: Oyler's Guaranteed Rate mortgage
            # ($4,103) and Truist boat loan ($1,970). Named with their
            # payment so the gap is visible, not silently left out.
            paid = []
            for r in rows:
                paid += [float(x.replace(',', '')) for x in
                         re.findall(r'([\d,]+(?:\.\d+)?)/mo', r.note or '')]
            # Loans paid off since the statements (the team's 'paid_off'
            # input: payee words and why): not listed as debt still owed.
            gone = (_inputs.get(folder, 'paid_off') or {}).get('value') or {}
            for payee, monthly, kind in cash.get('fixed_rows') or ():
                if kind != 'Liability':
                    continue
                if any(k.lower() in payee.lower() for k in gone):
                    continue
                # Within 1%: a mortgage paid with a little escrow or rounding
                # on top ($2,510 against a $2,496 payment) is the same loan.
                if any(abs(monthly - p) <= max(2, 0.01 * p) for p in paid):
                    continue
                # One bank-statement payment covering several loans from the
                # same lender (Affirm's two loans, $223 + $475, drawn as one
                # $700): matched by the lender's name and the payments added.
                first = (re.findall(r'[a-z]{4,}', payee.lower()) or [''])[0]
                same_lender = [r for r in rows if first and first in (r.label or '').lower()]
                if same_lender:
                    tot = sum(float(x.replace(',', '')) for r in same_lender for x in
                              re.findall(r'([\d,]+(?:\.\d+)?)/mo', r.note or ''))
                    if tot and abs(monthly - tot) <= 5:
                        continue
                # The same loan by its account digits ("Us Bank Home Mtg Mtg
                # Pymt ***7127" is the mortgage x7127), paid above schedule:
                # the lead advisor's Rebol plan, "currently being accelerated
                # by $1,000/month". Said on that loan, not listed again.
                digits = re.findall(r'(\d{4})(?!\d)', payee)
                same = next((r for r in rows if digits and
                             any('x' + d4 in (r.label or '') for d4 in digits)), None)
                if same is not None:
                    if not any(abs(monthly - p) <= 2 for p in paid):
                        same.note = '%s; %s/mo paid on the bank statements' % (
                            same.note or '', _money(monthly))
                    continue
                low = payee.lower()
                what = ('Mortgage' if re.search(r'\bmtge?\b|mortgage|\bmort\b', low)
                        else 'HELOC' if 'heloc' in low else 'Loan')
                lender = next((n for k, n in (('guaranteed rate', 'Guaranteed Rate'),
                                              ('truist', 'Truist'), ('usaa', 'USAA'),
                                              ('wells', 'Wells Fargo'),
                                              ('regions', 'Regions'),
                                              ('m & t', 'M&T'), ('chase', 'Chase'),
                                              ('freddie', 'Freddie Mac'))
                               if k in low), None)
                name = '%s (%s)' % (what, lender) if lender else payee.title()
                extra.append({'label': name, 'amount': 'not stated',
                              'mid': 'not stated',
                              'detail': '%s/mo paid on the bank statements; '
                                        'balance, rate and term needed'
                                        % _money(monthly)})
        if rows or extra:
            def _isnum(v):
                return isinstance(v, (int, float)) and not isinstance(v, bool)
            total = sum(r.value for r in rows if _isnum(r.value))
            listed = [{'label': r.label,
                       'amount': _money(r.value) if _isnum(r.value)
                       else str(r.value or 'not stated'),
                       'mid': _maturity(folder, r.value if _isnum(r.value)
                                        else None,
                                        '%s %s' % (r.label or '', r.note or '')),
                       'detail': (r.note or '').replace('  ·  ', ', ') or None}
                      for r in rows] + extra
            # Earliest payoff first: what frees up cash soonest is what the
            # plan reaches for first. Revolving lines, then anything with no
            # maturity, go last.
            listed.sort(key=_maturity_order)
            out.append(Section(number,
                'The following %s liability positions are worth mentioning, '
                'earliest payoff first.' % label,
                rows=listed +
                     [{'label': 'Total' + (' of stated balances' if extra else ''),
                       'amount': _money(total),
                       'detail': None, 'rule': True}],
                source='debt schedule and lender statements',
                flag=_flag(folder, number)))
            out[-1].heads = ('Obligation', 'Matures', 'Balance')
            steps = []
            for x in listed:
                if '(est.)' not in str(x.get('mid') or ''):
                    continue
                bal = next((r.value for r in rows if r.label == x['label'] and _isnum(r.value)), None)
                got = _payoff(bal, x.get('detail') or '')
                if got:
                    rate, pay, months = got
                    steps.append('%s: %s at %.2f%%, paying %s a month, is paid off in about '
                                 '%d months (%.1f years): %s.'
                                 % (x['label'], _m(bal), rate, _m(pay), round(months),
                                    months / 12, x['mid']))
            nums = [r.value for r in rows if _isnum(r.value)]
            if nums:
                steps.append('Total: %d balance%s added up = %s%s.'
                             % (len(nums), '' if len(nums) == 1 else 's', _m(total),
                                ' (debts with no stated balance are not in it)' if extra else ''))
            if steps:
                steps.insert(0, 'Matures: the year from the debt schedule or the credit report '
                                'where one is given. An "est." year is worked out from the '
                                'balance, rate and payment, n = -ln(1 - rate x balance / '
                                'payment) / ln(1 + rate), monthly.')
            out[-1].workings = steps
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
    da = _series(bundle, 'depreciation / amortisation', basis_year) or 0
    # Net profit is the P&L's bottom line, AFTER the owner's W-2 and
    # depreciation, as every one of the lead advisor's plans states it (W-2
    # plus net profit = what the owner earns). "expenses (P&L)" is overhead,
    # which leaves both out: taking it alone counted the W-2 twice and put
    # one owner's earnings $418,000 too high.
    net = (rev - exp - (wages or 0) - da) if (rev and exp) else None
    if wages or net:
        # Four numbers and two growth rates, which as a sentence forces the
        # reader to hold the W-2 in their head while the net profit arrives.
        # As a table the question "what does he actually take out, and what
        # happens to it" is answered by looking.
        # Every W-2 by person (the lead advisor's rule): the owner, a spouse
        # and any other family member on the payroll, each annualized from
        # their paystubs where Claude read them, else from the W-2s. The
        # P&L's doctor wages remain the fallback for a file with neither.
        rows = _w2_rows(folder, wages) if wages else []
        w2_total = sum(r['_v'] for r in rows) if rows else 0
        stubs = any(r.get('_stub') for r in rows)
        # The owner's W-2 at today's pay rate (from the paystubs) is not the
        # P&L year's W-2. Net profit is restated with today's W-2 taken out,
        # so the lines add up and the total is not counted twice: a raise
        # moves money from profit to W-2, it does not add to the household.
        owner_now = sum(r['_v'] for r in rows if r.get('_owner'))
        net_shown = net
        restated = bool(net and wages and owner_now and abs(owner_now - wages) >= 1)
        if restated:
            net_shown = net - (owner_now - wages)
        for r in rows:
            for k in ('_v', '_stub', '_owner'):
                r.pop(k, None)
        # A net profit the team worked out themselves (the 'net_profit' input,
        # e.g. when the P&L on file is wrong) replaces the P&L's figure.
        np_in = (_inputs.get(folder, 'net_profit') or {})
        np_typed = _money_num(np_in.get('value')) if np_in else None
        if np_typed is not None:
            net = net if net is not None else np_typed
            net_shown, restated = np_typed, False
        if net:
            detail = ('Revenue of %s less overhead of %s, the owner\'s W-2 and '
                      'depreciation.' % (_money(rev), _money(exp)))
            if np_typed is not None:
                detail = ('The team\'s figure%s (the %s P&L works out to %s).'
                          % ((': ' + np_in['note'].rstrip('.')) if np_in.get('note') else '',
                             basis_year, _money(rev - exp - (wages or 0) - da) if (rev and exp) else 'n/a'))
            elif restated:
                detail = ('Revenue of %s less overhead of %s, the owner\'s W-2 at '
                          'today\'s pay rate and depreciation (the %s P&L, with a '
                          'W-2 of %s, shows %s).' % (_money(rev), _money(exp),
                                                    basis_year, _money(wages), _money(net)))
            rows.append({'label': 'Net profit',
                         'amount': _money(net_shown),
                         'detail': detail + ' Distributions grown at 5.0% until retirement.'})
        if wages and net:
            rows.append({'label': 'Total earnings',
                         'amount': _money(w2_total + net_shown),
                         'detail': None, 'rule': True})
        # Below the total, never in it: what actually reaches the household
        # from the practice, net of money put back in.
        nd, nd_detail = _net_distributions(folder)
        rows.append({'label': 'Net distributions (take-home, not in the total)',
                     'amount': _money(nd) if nd is not None else 'none found',
                     'detail': nd_detail})
        officer = _series(bundle, 'officer compensation (tax return)',
                          basis_year)
        src = '%s Profit and Loss' % basis_year
        if stubs:
            src += '; W-2 wages from the paystubs, with the W-2s'
        if officer:
            src += ', confirmed against officer compensation of %s on the ' \
                   '1120-S' % _money(officer)
        out.append(Section(10,
            'Current profitability for %s suggests the following earnings.'
            % basis_year,
            rows=rows, source=src + '.', flag=_flag(folder, 10)))
        out[-1].heads = ('Source', 'Amount')
        steps = []
        for r in rows:
            m = re.search(r'(\$[\d,]+\.\d\d) a pay period .*? times (\d+)', r.get('detail') or '')
            if m:
                steps.append('%s: %s x %s pay periods = %s.'
                             % (r['label'].replace(', W-2 wages', ''), m.group(1), m.group(2),
                                r['amount']))
        if net:
            steps.append('Net profit, %s P&L: revenue %s - overhead %s - owner W-2 %s - '
                         'depreciation %s = %s.' % (basis_year, _m(rev), _m(exp),
                                                    _m(wages or 0), _m(da), _m(net)))
            if restated:
                diff = owner_now - wages
                steps.append('The owner\'s W-2 at today\'s pay rate is %s, %s %s than in %s, '
                             'so net profit is %s by the same: %s %s %s = %s.'
                             % (_m(owner_now), _m(abs(diff)), 'more' if diff > 0 else 'less',
                                basis_year, 'lower' if diff > 0 else 'higher', _m(net),
                                '-' if diff > 0 else '+', _m(abs(diff)), _m(net_shown)))
        if np_typed is not None:
            steps.append('Net profit used: %s, the team\'s figure, in place of the P&L\'s.'
                         % _m(np_typed))
        if wages and net:
            steps.append('Total earnings: W-2s %s + net profit %s = %s.'
                         % (_m(w2_total), _m(net_shown), _m(w2_total + net_shown)))
        out[-1].workings = steps
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
        # Loans paid off since the statements (the 'paid_off' input): their
        # payments stop, so they come out of the fixed payments and of the
        # figure including them. Spending without them is unchanged.
        gone12 = (_inputs.get(folder, 'paid_off') or {}).get('value') or {}
        fixed_rows = list(cash.get('fixed_rows') or ())
        dropped = [r[:3] for r in paid_off_rows(folder, cash)]
        if dropped:
            fixed_rows = [r for r in fixed_rows if tuple(r[:3]) not in [tuple(d) for d in dropped]]
            cut = sum(r[1] for r in dropped)
            inc, fixed = inc - cut, fixed - cut
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
                sorted(fixed_rows, key=lambda r: -r[1])]
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
        steps = []
        pers = [a for a in cash['accounts'] if a.get('monthly_spend') is not None]
        for a in pers:
            steps.append('%s: %s a month spent, averaged over %s statement%s (money out, less '
                         'transfers to their own accounts and one-offs).'
                         % (a['name'], _m(a['monthly_spend']), a.get('months') or a['periods'],
                            '' if (a.get('months') or a['periods']) == 1 else 's'))
        if pers and dropped:
            cut = sum(r[1] for r in dropped)
            steps.append('Personal accounts added up: %s a month including the fixed payments.'
                         % _m(inc + cut))
            for r in dropped:
                k = next(k for k in gone12 if k.lower() in r[0].lower())
                why = gone12[k] if isinstance(gone12[k], str) else (gone12[k] or {}).get('note', '')
                steps.append('Less %s, paid off since the statements (%s): %s a month.'
                             % (k, (why or 'paid_off').rstrip('.'), _m(r[1])))
            steps.append('Including the fixed payments still being made: %s - %s = %s a month; '
                         'x 12 = %s a year.' % (_m(inc + cut), _m(cut), _m(inc), _m(inc * 12)))
        elif pers:
            steps.append('Personal accounts added up: %s a month including the fixed payments; '
                         'x 12 = %s a year.' % (_m(inc), _m(inc * 12)))
        steps.append('Less the fixed payments listed below: %s - %s = %s a month; x 12 = %s a year.'
                     % (_m(inc), _m(fixed), _m(exc), _m(exc * 12)))
        if cash.get('one_offs'):
            steps.append('Left out as one-offs: %s in all (on the cash flow workbook\'s '
                         'To review tab).' % _m(sum(cash['one_offs'])))
        out[-1].workings = steps
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
    con = contributions(folder, saved)
    if con:
        said = (' (the IC form says "%s")' % str(saved).strip()) if saved and con['basis'] != 'ic' else ''
        if con['basis'] == 'ic':
            text = ('Investment amounts currently being put back into investable assets: '
                    '%s a year, from the IC form ("%s"). These contribution assumptions '
                    'matter a great deal to the plan; please tell us if any of it is wrong.'
                    % (_money(con['total']), str(saved).strip()))
        else:
            text = ('Investment amounts currently being put back into investable assets '
                    'include the following%s. These contribution assumptions matter a '
                    'great deal to the plan; please tell us if any of it is wrong.' % said)
        sec = Section(14, text, rows=[{k: v for k, v in r.items() if not k.startswith('_')}
                                      for r in con['rows']],
                      source=con['source'],
                      flag=(None if con['basis'] == 'paystubs' else
                            'Paystubs needed: contributions come from the paystubs, '
                            'annualized; this figure stands until they come in.'))
        if con['rows']:
            sec.heads = ('Contribution', 'A year')
        sec.workings = con['workings']
        out.append(sec)
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

    # 15 --------------------------------------------------------------------
    # Insurance in force. Always printed, so a plan with nothing on file
    # says so rather than leaving the reader to wonder whether it was looked
    # at: the policies Claude read, and any premiums the bank statements
    # show, else what is still needed.
    out.append(_insurance(folder, cash))
    return out


INSURERS = re.compile(r'\b(guardian|northwestern mutual|mass ?mutual|principal life|'
                      r'ameritas|lincoln (?:national|financial)|prudential|metlife|'
                      r'new york life|ohio national|the standard|standard ins|unum|'
                      r'mutual of omaha|assurity|penn mutual|pacific life|'
                      r'john hancock|transamerica|banner life|protective life|'
                      r'state farm life|aflac|lloyds)\b', re.I)


def _insurer_payments(folder):
    """[(insurer, monthly, last4)]: insurers paid in two or more months on
    any account's statements, read from bank_statements.json."""
    try:
        with open(_store.json_path(folder, 'bank_statements.json')) as fh:
            got = json.load(fh)
    except (OSError, ValueError, AttributeError):
        return []
    seen = {}
    for f in (got.get('files') or {}).values():
        for st in f.get('statements') or ():
            acct = st.get('account_last4') or '????'
            for t in st.get('transactions') or ():
                if t.get('direction') == 'in':
                    continue
                m = INSURERS.search(str(t.get('description') or ''))
                if not m:
                    continue
                key = (m.group(1).title(), acct)
                month = str(t.get('date') or '')[:7]
                seen.setdefault(key, {})[month] = abs(float(t.get('amount') or 0))
    out = []
    for (name, acct), by_month in sorted(seen.items()):
        if len(by_month) >= 2:
            vals = sorted(by_month.values())
            out.append((name, vals[len(vals) // 2], acct))
    return out


def _insurance(folder, cash):
    try:
        import doc_readings as _dr
        pols = (_dr.check(folder)[0] or {}).get('insurance') or []
    except Exception:                                        # noqa: BLE001
        pols = []
    rows = []
    for p in pols:
        label = ' '.join(x for x in ((p.get('carrier') or '').strip(),
                                     (p.get('kind') or 'policy').strip()) if x)
        if p.get('insured'):
            label += ', on %s' % p['insured']
        bits = []
        if p.get('coverage'):
            bits.append('%s %s' % (_money(p['coverage']),
                                   p.get('coverage_note') or 'coverage'))
        if p.get('cash_value'):
            bits.append('cash value %s' % _money(p['cash_value']))
        if p.get('premium'):
            bits.append('premium %s a %s' % (_money(p['premium']),
                                             p.get('premium_period') or 'month'))
        if p.get('source'):
            bits.append('from %s' % p['source'])
        shown = p.get('coverage') or p.get('cash_value')
        rows.append({'label': label, 'amount': _money(shown) if shown else None,
                     'detail': '; '.join(bits) + '.' if bits else None})
    carriers = ' '.join((p.get('carrier') or '').lower() for p in pols)
    seen = [(n, a) for n, a, k in ((cash or {}).get('fixed_rows') or ())
            if k == 'Insurance' and not any(w in carriers for w in
                                             str(n).lower().split()[:1])]
    # Premiums the practice pays (a disability or overhead policy through
    # the practice account) never reach the personal fixed payments above:
    # Tanksley's Guardian $92.68 a month from the practice account was
    # missed that way. Insurers named on any account's statements, paid in
    # two months or more, are listed with the account that pays them.
    named = {str(n).lower() for n, _a in seen}
    for name, monthly, acct in _insurer_payments(folder):
        if name.lower() in carriers or any(name.lower().split()[0] in n for n in named):
            continue
        rows.append({'label': '%s (premium paid from x%s)' % (name, acct),
                     'amount': None,
                     'detail': '%s a month (%s a year) on the bank statements; '
                               'the policy itself is not on file.'
                               % (_money(monthly), _money(monthly * 12))})
    if seen:
        for name, monthly in seen:
            rows.append({'label': '%s (premium on the bank statements)' % name,
                         'amount': None,
                         'detail': '%s a month (%s a year); the policy itself is not on file.'
                                   % (_money(monthly), _money(monthly * 12))})
    if not rows:
        return Section(15, needed='the life, disability and business overhead '
                                  'insurance policies in force (none found in '
                                  'the documents, and no premiums on the bank '
                                  'statements)',
                       why='the plan has to show what protects the income and '
                           'the debts if something happens to the owner')
    sec = Section(15, '%s the following insurance in force.'
                  % ('We show' if pols else 'The bank statements show premiums for')
                  + ('' if pols and all(r.get('amount') for r in rows)
                     else ' The policies behind the premiums are still needed.'),
                  rows=rows,
                  source='Policy documents.' if pols else 'Bank statements.',
                  flag=_flag(folder, 15))
    sec.heads = ('Policy', 'Coverage')
    return sec


_MATURITY = {}


def _maturity_order(row):
    m = str(row.get('mid') or '')
    year = re.search(r'(\d{4})', m)
    if year:
        return (0, int(year.group(1)), m)
    return (1 if 'revolving' in m else 2, 0, m)


def _maturity(folder, balance, note=None):
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
    # A term written into the note ("2-yr term to Nov 2027"): the loan ends
    # then at the latest. The estimate from the payments still wins when it
    # is sooner (a mortgage paid ahead of its 30-year schedule); when the
    # stated end is sooner (a 0% loan whose balance is a few months old),
    # the stated end is printed.
    stated = None
    if not year:
        said = re.search(r'term to (?:[A-Za-z]{3,9}\s+)?(\d{4})|matures\s+(?:[A-Za-z]{3,9}\s+)?(\d{4})',
                         str(note or ''))
        if said:
            stated = int(said.group(1) or said.group(2))
    if not year and re.search(r'credit card|line of credit|\bloc\b|heloc',
                              str(note or ''), re.I):
        return 'revolving'
    if not year and re.search(r'\bpending\b', str(note or ''), re.I):
        return 'pending'
    if not year and balance and note:
        # Worked out from the balance, rate and payment when nothing states
        # the end date: n = -ln(1 - rB/P) / ln(1 + r), monthly.
        import math
        rate = re.search(r'(\d+(?:\.\d+)?)%', note)
        pay = re.search(r'\$?([\d,]+(?:\.\d+)?)/mo', note)
        if rate and pay:
            r = float(rate.group(1)) / 100 / 12
            P = float(pay.group(1).replace(',', ''))
            B = float(balance)
            if 'credit card' in note.lower() or 'line of credit' in note.lower():
                return 'revolving'
            n = None
            if P > 0 and r == 0:
                n = B / P
            elif P > 0 and r * B < P:
                n = -math.log(1 - r * B / P) / math.log(1 + r)
            if n is not None and n < 12 * 40:
                end = datetime.date.today() + datetime.timedelta(days=30.44 * n)
                if stated and stated < end.year:
                    return str(stated)
                return 'about %d (est.)' % end.year
    if not year and stated:
        year = stated
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
           ('Practice real estate', (7,), False),
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


def payload(folder, client=None):
    """The Assumptions as data, for the lead advisor's review page.

    The same sections, rows and closing summary as the PDF, built by the same
    code, so the page and the PDF cannot say different things.
    """
    import assumptions_pdf as _pdf
    bundle = _facts.gather(folder, client=client)
    sections = build(bundle, folder)
    out = []
    for sec in sections:
        out.append({
            'number': sec.number,
            'title': getattr(sec, 'title', None) or _pdf.TITLES.get(sec.number, ''),
            'text': sec.text, 'source': sec.source, 'flag': sec.flag,
            'needed': sec.needed, 'why': sec.why, 'link': sec.link,
            'heads': list(getattr(sec, 'heads', None) or ()),
            'workings': list(getattr(sec, 'workings', None) or ()),
            'rows': [{'label': r.get('label'), 'amount': r.get('amount'),
                      'mid': r.get('mid'),
                      'detail': r.get('detail'), 'rule': bool(r.get('rule'))}
                     for r in (getattr(sec, 'rows', None) or ())]})
    lines, net, missing = summarise(sections)
    return {'sections': out,
            'done': sum(1 for x in sections if x.complete),
            'summary': {'lines': [[a, b] for a, b in lines], 'net': net,
                        'missing': missing}}


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
