#!/usr/bin/env python3
"""Render the two-page Prospect Summary from whatever has been established.

    python3 prospect_page.py "<client folder>"      # writes _Audit/<client> - Prospect Summary.html

WHY EVERY FIELD CARRIES A SOURCE
Rendering the page is the easy half, it is a layout. The hard half is knowing
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
import production as _prod
import tax_basis as _tax
import practice_facts as _facts
import debt as _debt                                     # noqa: E402

GAP = 'NOT YET SENT'
HUMAN = 'NEEDS A HUMAN'


def _e(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def money(v):
    return '{:,.0f}'.format(v) if isinstance(v, (int, float)) else None


def cell(value, source=None, why=None):
    """One field. Empty prints as a rule, not as a label.

    The page is read across a table at a glance, and a row of amber "NEEDS A
    HUMAN" badges shouts louder than the figures that are actually there. The
    template's own answer to an unknown is an em dash, so that is what an empty
    field prints. What is outstanding is said once, in the open-items list,
    where somebody can act on it.
    """
    if value is None:
        return '<span class="nil">-</span>'
    src = ('<span class="src">%s</span>' % _e(source)) if source else ''
    return '%s%s' % (_e(value), src)


ANALYSIS_ROWS = [
    ('Gross production', 'bold0'), ('Production adjustments', ''),
    ('Net production', 'b'), ('Gross collections', ''),
    ('Collection adjustments', ''), ('Net collections', 'b'),
    ('__PRODUCERS__', ''), ('Total patients', ''),
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


def debt_total(debts):
    """Total debt, said in a way that admits what it leaves out.

    A bare total is the most dangerous figure on this page. Oyler's reads
    $1.38m, and the building loan alone is $1.8m more -- it arrived as a letter
    rather than a statement, so nothing has read it. A reader seeing one number
    assumes it is the number. So the count of obligations behind it travels
    with it, and anything unread is named.
    """
    total = (debts.get('practice_balance') or 0) + (debts.get('personal_balance') or 0)
    if not total:
        return None
    n = len(debts.get('practice') or ()) + len(debts.get('personal') or ())
    unread = len(debts.get('unread') or ())
    note = '%d obligations' % n
    if unread:
        note += ', %d more not read' % unread
    return '$' + money(total) + '<span class="src">%s</span>' % note


def cashflow_rows(folder):
    """The cash flow build, or nothing, never a half-built one.

    Wrapped because this page must render for a client whose statements
    have not arrived. An exception here would take the whole summary down,
    and the summary's job is to show what is missing.

    Routed through the Assumptions' own accessor rather than calling the
    cash flow directly, because that one memoises per folder. Building the
    workbook, this page and the Assumptions in one process then costs one
    pass over the statements instead of three, and that pass is seventy
    seconds.
    """
    try:
        import assumptions as _asm
        return _asm._cash_flow(folder)
    except Exception:
        return None


def practice_holdings(folder, form, headline, head_year):
    """The practice and the building he owns it in.

    Both belong on a balance sheet and neither is a bank account, which is
    why they were missing. They are computed the way sections 6 and 7
    compute them rather than read off those sections, because building the
    Assumptions here would mean a second full pass over the folder for two
    figures.

    The building is listed with no value on purpose. Left off, a reader
    totals the page and believes it; listed empty, the gap is visible and
    the note says what would close it.
    """
    import assumptions as _asm
    import compose as _comp

    out = []
    if headline and headline.get('income'):
        mult = _asm.FIRM['practice_value_multiple']
        value = headline['income'] * mult
        out.append({
            'name': _comp.entity_name(folder) or 'The practice',
            'note': '%.0f%% of %s revenues, the firm multiple.'
                    % (mult * 100, head_year),
            'amount': '$' + money(value),
            'value': value})

    sqft = _ic.money(form.get('building_sqft'))
    addr = _comp.addresses(folder)
    bits = []
    if addr:
        bits.append('%s, %s' % (addr[0][0][1], addr[0][0][2]))
    if sqft:
        bits.append('{:,.0f} sq ft'.format(sqft))
    rent = _ic.money(form.get('building_payment'))
    if rent:
        bits.append('practice pays $%s/mo rent' % money(rent))
    if bits:
        out.append({
            'name': 'Practice building, held personally',
            'note': '%s. Needs a county assessment or an appraisal; the '
                    'practice books carry leasehold improvements and no '
                    'building, so no figure in them is its value.'
                    % '. '.join(bits),
            'amount': None, 'value': None})
    return out


def observed_assets(folder, cash, practice=()):
    """Everything observed that the household owns, not just its cash.

    The table was bank accounts only, which made a heading reading "Assets
    observed" wrong rather than merely incomplete: Oyler's properties and
    his retirement accounts are both in the file, and a reader seeing four
    checking accounts under that heading concludes the man owns no house.

    Three groups, each from the source that already owns it, so this table
    cannot disagree with the Assumptions. Property and retirement come
    from the input store, the same place sections 3 and 4 read. Bank
    balances come from the cash flow build, the same place section 5
    reads. Nothing is counted twice because nothing is read twice.
    """
    import inputs as _inputs
    import assumptions as _asm

    def _stored(key):
        got = (_inputs.get(folder, key) or {}).get('value') or []
        out = []
        for r in got:
            amount = r.get('amount') or (
                ('$' + money(r['value'])) if r.get('value') else None)
            out.append({'name': r.get('label') or '?',
                        'note': r.get('basis') or '',
                        'amount': amount,
                        'value': _asm._amount(amount) if amount else None})
        return out

    banks = []
    for r in ((cash or {}).get('accounts') or ()):
        if r.get('balance') is None:
            continue
        banks.append({'name': r['name'], 'note': r.get('bank') or '',
                      'amount': '$' + money(r['balance']),
                      'value': r['balance'],
                      'as_of': r.get('as_of')})
    banks.sort(key=lambda x: -(x['value'] or 0))

    # The non-qualified list in the store is mostly the same bank accounts
    # under their typed-in names, plus the holdings that are not banks at
    # all: Oyler's Reef Capital stake and his bitcoin. Those are the ones
    # worth taking, and $408,526 of Reef is not a rounding difference.
    # Accounts are matched on the last four digits, which is the only
    # token the two namings share ("Personal Savings [US Bank x0393]"
    # against "Savings (US Bank x0393)").
    def _last4(text):
        m = re.findall(r'x(\d{4})', text or '')
        return set(m)
    seen = set()
    for b in banks:
        seen |= _last4(b['name'])
    other = [r for r in _stored('nonqualified_accounts')
             if not (_last4(r['name']) & seen)]

    # Practice first. It is the largest thing the man owns and the reason
    # he is a client, so a balance sheet that opens with his checking
    # account has its priorities from the alphabet rather than the file.
    groups = [('PRACTICE & BUILDING', list(practice)),
              ('PROPERTY', _stored('properties')),
              ('RETIREMENT', _stored('qualified_accounts')),
              ('OTHER INVESTMENTS', other),
              ('BANK ACCOUNTS', banks)]
    return [g for g in groups if g[1]]


def assets_total(groups):
    """Observed assets, with what is behind the figure and what is not.

    Same reasoning as the debt tile. This totals what has arrived, not
    what the household owns, and an asset listed without a value is named
    in the note rather than quietly treated as a zero. A total that
    silently swallows an unvalued house is the most misleading figure this
    page could print.
    """
    rows = [r for _g, items in groups for r in items]
    valued = [r for r in rows if r.get('value')]
    if not valued:
        return None
    note = '%d of %d holdings' % (len(valued), len(rows))
    blank = len(rows) - len(valued)
    if blank:
        note += ', %d not valued' % blank
    return ('$' + money(sum(r['value'] for r in valued))
            + '<span class="src">%s</span>' % note)


def risk_flags(by_year, tax, debts, cash, form, headline, head_year):
    """What the documents already prove is worth asking about.

    Every flag is derived from a figure on this page, which is the whole
    discipline: nothing is flagged that a reader cannot go and check two
    inches away, and nothing is flagged on a hunch.

    Each one carries the section it belongs under, because that is where
    it prints. Collected into one block at the foot of page 1 they read as
    a list of complaints, and the reader has to carry each one back up the
    page to the table it is about. Under the table, a flag is a footnote
    to a figure the eye is already on.

    The distinction against Open items: Open items is what has not
    arrived, a flag is what has arrived and looks wrong.
    """
    out = []

    if headline and headline.get('overhead_pct', 0) > 60:
        out.append(('overhead', 'Overhead above target',
                    'The P&amp;L puts %s overhead at %.1f%% against a %s target.'
                    % (head_year, headline['overhead_pct'], '60%')))

    p, t = by_year.get(head_year), tax.get(head_year)
    if p and t and abs(p['overhead_pct'] - t['overhead_pct']) >= 5:
        out.append(('overhead', 'Books disagree with the return',
                    'Overhead for %s reads %.1f%% on the P&amp;L and %.1f%% on '
                    'the 1120-S. A gap that size is usually a reclassification '
                    'rather than a difference of opinion.'
                    % (head_year, p['overhead_pct'], t['overhead_pct'])))

    want = _ic.money(form.get('overhead_stated'))
    if want and headline and abs(headline['overhead_pct'] - want) >= 10:
        out.append(('overhead',
                    'Client’s estimate is well off the documents',
                    'He puts overhead at %s; the documents put it near %.0f%%. '
                    'That gap is the first conversation, not a rounding '
                    'difference.'
                    % (_e(form.get('overhead_stated')),
                       headline['overhead_pct'])))

    unread = debts.get('unread') or ()
    if unread:
        out.append(('debt', 'Debt nobody has read',
                    '%d obligation%s stated in prose rather than on a '
                    'statement, so %s not in the total above.'
                    % (len(unread), '' if len(unread) == 1 else 's',
                       'it is' if len(unread) == 1 else 'they are')))

    rows = (cash or {}).get('accounts') or ()
    # A deficit on one account is housekeeping; a deficit on the household
    # is the finding. So the personal accounts are judged together.
    short = [r for r in rows if r.get('readable') and (r.get('surplus') or 0) < 0
             and r.get('entity') == 'Personal']
    if short:
        out.append(('cashflow', 'Personal accounts running a deficit',
                    '%s. Money is coming from somewhere else, and the plan '
                    'should say where.'
                    % ', '.join('%s at -$%s/mo'
                                % (_e(r['name']), money(abs(r['surplus'])))
                                for r in short)))

    unreadable = [r for r in rows if not r.get('readable')]
    if unreadable:
        out.append(('assets', 'Statements that would not read',
                    '%d account%s whose transactions could not be extracted, '
                    'so no transfers were found on %s and the spending figure '
                    'does not include %s.'
                    % (len(unreadable), '' if len(unreadable) == 1 else 's',
                       'it' if len(unreadable) == 1 else 'them',
                       'it' if len(unreadable) == 1 else 'them')))

    offs = (cash or {}).get('one_offs') or ()
    if offs:
        out.append(('cashflow', 'Single outflows held out of the run rate',
                    '%d movement%s large enough to distort monthly spending, '
                    'worth $%s in total. Real money, but not a run rate, and '
                    'an analyst has to rule on each.'
                    % (len(offs), '' if len(offs) == 1 else 's',
                       money(sum(abs(x) for x in offs)))))

    return out


def flagbox(flags, section):
    """The flags belonging to one section, or nothing at all.

    Nothing at all is the important half. A heading that prints "no flags"
    under every clean table trains the reader to skip the place flags
    appear, which is the one place they must not skip.
    """
    mine = [(h, w) for s, h, w in flags if s == section]
    if not mine:
        return ''
    out = ['<div class="flags">']
    for head, why in mine:
        out.append('<div class="fl"><div class="flh">%s</div>'
                   '<div class="flw">%s</div></div>' % (head, why))
    out.append('</div>')
    return ''.join(out)


def provider_label(code, role):
    """How a producer is named on the page, following the template's wording."""
    name = (role.get('name') or code).replace('Dr. ', '').split()[-1]
    if role.get('role') == 'owner':
        return 'Production, Dr. %s' % name
    return 'Production, assoc. (%s)' % name


def production_rows(folder):
    """{year: {metric: value}} from the scanned reports, agreed figures only.

    Two reports per year, not one. The Practice Analysis carries charges and
    collections; the Provider Summary carries the patient counts and the
    per-provider split. An earlier version read the first and dropped the
    second, which is why two thirds of this table printed empty against a
    folder that had the numbers in it.
    """
    rows = {}
    try:
        got = _prod.gather(folder)
    except Exception:
        got = {}
    for year, rec in got.items():
        vals = rec.get('values') or {}
        chk = rec.get('check')
        if chk and not chk['agrees']:
            continue          # the report does not add up; report nothing
        rows[year] = {name: fn(vals) for name, fn in PROD_MAP.items()
                      if fn(vals) is not None}
    try:
        provs = _prod.find_provider_reports(folder)
    except Exception:
        provs = []
    roles = _prod.load_roles(folder)
    for year, path in provs:
        try:
            rec = _prod.read_provider(path)
        except Exception:
            continue
        v = dict(rec.get('values') or {})
        # Patient counts come from the report's TOTAL line only. Summing the
        # per-provider column looks equivalent and is not: one patient seen by
        # a hygienist and a dentist appears in both rows. On Oyler's 2024 that
        # read 814 new patients where the report's own total says 536.
        row = rows.setdefault(year, {})
        # Visits, not patients. The Provider Summary's "Patients Seen" counts
        # each patient once per provider who saw them, which makes it the right
        # numerator for a per-day rate and the wrong one for a headcount.
        if v.get('total_patients'):
            row['_visits'] = v['total_patients']
        # The owner / associate / hygiene split, but only when the providers
        # that were read account for the report's own total. A year where a
        # charge line was unreadable leaves these lines blank rather than
        # printing a split that quietly omits a million dollars.
        total = v.get('total_charges_prov')
        settled = _prod.reconcile_providers(rec.get('providers') or {},
                                            rec.get('activity') or {}, total)
        charges = settled['providers']
        if roles and charges and total:
            sp = _prod.split_production(charges, roles)
            sp['unassigned'] += max(settled['residual'], 0)
            if settled['reconciles']:
                # One line per producing doctor, not a single associate total.
                # Two associates with opposite trajectories net out to a flat
                # line, which hides the only movement worth discussing.
                for code, amount in charges.items():
                    r = (roles.get(code) or {})
                    if r.get('role') not in ('owner', 'associate'):
                        continue
                    row[provider_label(code, r)] = amount
                row['Hygiene production'] = sp['hygiene'] or None
                row = {k: val for k, val in row.items() if val is not None}
                rows[year] = row
        row.update({k: val for k, val in (
            ('Total patients', v.get('total_patients')),
            ('New patients', v.get('new_patients')),
            ('Gross production / patient', v.get('production_per_patient')),
        ) if val is not None})
        if v.get('new_patients') and v.get('total_patients'):
            row['New patients % of total'] = round(
                100.0 * v['new_patients'] / v['total_patients'], 1)

    # The practice's own count documents outrank the reports for these three
    # rows: days worked is on no report at all, and the reports' patient column
    # counts patient-provider pairings rather than patients.
    try:
        facts = _facts.gather(folder).get('by_year') or {}
    except Exception:
        facts = {}
    for year, f in facts.items():
        row = rows.setdefault(year, {})
        for key, label in (('total_patients', 'Total patients'),
                           ('new_patients', 'New patients'),
                           ('doctor_days', 'Days worked')):
            if f.get(key):
                row[label] = f[key]
        row.pop('Gross production / patient', None)
        row.pop('New patients % of total', None)

    # Rows the reports do not print but state between them. Each is computed
    # only from two figures already accepted, so a derived row never outlives
    # the numbers it rests on.
    for year, row in rows.items():
        gross = row.get('Gross production')
        adj = row.get('Production adjustments')
        if gross and adj:
            row['Production adjustment %'] = round(100.0 * adj / gross, 1)
        # Every share is of the whole practice's gross production, so the
        # producer lines and hygiene can be read against each other directly.
        if gross:
            for key in list(row):
                if key.startswith('Production, '):
                    who = key.split(', ', 1)[1]
                    row['%s %% of production' % who] = round(
                        100.0 * row[key] / gross, 1)
            if row.get('Hygiene production'):
                row['Hygiene % of production'] = round(
                    100.0 * row['Hygiene production'] / gross, 1)
        net = row.get('Net production')
        pats = row.get('Total patients')
        new = row.get('New patients')
        days = row.get('Days worked')
        if net and pats:
            row['Net production / patient'] = round(net / pats, 2)
        if gross and pats:
            row['Gross production / patient'] = round(gross / pats, 2)
        if new and pats:
            row['New patients % of total'] = round(100.0 * new / pats, 1)
        row.pop('_visits', None)
        # Patients per day is the practice's patients over the days worked --
        # not visits. An earlier version used the Provider Summary's
        # patient-provider pairings and read 20/day against a true 8.2.
        if days and pats:
            row['Patients / day'] = round(pats / days, 1)
        if days:
            if gross:
                row['Gross production / day'] = round(gross / days, 2)
            if net:
                row['Net production / day'] = round(net / days, 2)
    return rows


def analysis_rows(prod_rows):
    """The template's rows, with one production line per producer.

    A practice with three doctors needs three lines and three shares; a solo
    practice needs one. The static list could not know which, so the provider
    block is built from whatever the provider map actually turned up.
    """
    producers, shares = [], []
    for row in prod_rows.values():
        for key in row:
            if key.startswith('Production, ') and key not in producers:
                producers.append(key)
    producers.sort(key=lambda k: ('assoc.' in k, k))
    for key in producers:
        shares.append('%s %% of production' % key.split(', ', 1)[1])
    out = []
    for name, cls in ANALYSIS_ROWS:
        if name == '__PRODUCERS__':
            out += [(p, '') for p in producers]
            out.append(('Hygiene production', ''))
            out += [(sh, '') for sh in shares]
            out.append(('Hygiene % of production', ''))
            continue
        out.append((name, cls))
    return out


_BUNDLE = {}


def _bundle(folder, client=None):
    """The facts for this client, read once per run.

    The page used to assemble its own version of these from the intake form,
    which meant two outputs describing the same client from two different
    readings of it. They now share one.
    """
    key = os.path.abspath(folder)
    if key not in _BUNDLE:
        try:
            import facts as _facts
            _BUNDLE[key] = _facts.gather(folder, client=client)
        except Exception:
            _BUNDLE[key] = None
    return _BUNDLE[key]


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


def fmt(name, v):
    """A figure in the units its row is in: dollars, a count, or a percent."""
    if '%' in name:
        return '%.1f%%' % v
    if '/ patient' in name or '/ day' in name:
        return '{:,.0f}'.format(v)
    return money(v)


def _delta(cur, prev, pt=False):
    """The template's change column: signed, coloured, blank when unknowable."""
    if cur is None or prev in (None, 0):
        return ''
    if pt:
        d = cur - prev
        txt = 'flat' if abs(d) < 0.05 else '%+.1fpt' % d
    else:
        d = 100.0 * (cur - prev) / abs(prev)
        txt = 'flat' if abs(d) < 0.5 else '%+.1f%%' % d
    k = 'up' if d > 0 else ('dn' if d < 0 else 'fl')
    return '<span class="%s">%s</span>' % (k, txt)


def build(folder, client=None):
    client = client or os.path.basename(folder.rstrip('/'))
    form = {}
    src = _ic.find_form(folder) or _ic.find_form(os.path.dirname(folder.rstrip('/')))
    if src:
        form = _ic.parse(src)
    pnl = _summary.gather(folder)
    by_year = {p['year']: p for p in pnl if p.get('year')}
    years = sorted(by_year)[-3:]
    prod_rows = production_rows(folder)
    try:
        tax = _tax.gather(folder)
    except Exception:
        tax = {}
    try:
        debts = _debt.gather(folder)
    except Exception:
        debts = {}
    cash = cashflow_rows(folder)
    # A part-year column is labelled and never compared. Oyler's newest sheet is
    # a single July, and beside two full years its change column read -42%,
    # which is the arithmetic of an unfinished year, not a falling practice.
    partial = {y for y in years
               if 0 < (by_year.get(y, {}).get('months') or 12) < 12}
    full = [y for y in years if y not in partial]
    head_year = full[-1] if full else (years[-1] if years else None)
    headline = by_year.get(head_year) if head_year else None
    holdings = observed_assets(
        folder, cash, practice_holdings(folder, form, headline, head_year))
    # Worked out once, printed in four places. Each flag carries the
    # section it belongs under and prints there, beneath the table whose
    # figure it is about.
    flags = risk_flags(by_year, tax, debts, cash, form, headline, head_year)

    L = []
    a = L.append
    a('<!doctype html><meta charset="utf-8">'
      '<title>Prospect summary, %s</title>' % _e(client))
    a('<style>%s</style>' % CSS)

    # ---------------------------------------------------------------- page 1
    a('<div class="pg">')
    a('<div class="band"><div>')
    a('<div class="kick">PROSPECT SUMMARY &nbsp;·&nbsp; ONBOARDING &amp; DATA INTAKE</div>')
    name, _, prac = client.partition('|')
    a('<h1>%s%s</h1>'
      % (_e(name.strip()),
         ('<span class="bar">|</span>%s' % _e(prac.strip())) if prac.strip() else ''))
    bits = [x for x in (form.get('pms') and 'Dentrix' or None,
                        form.get('ownership'),
                        form.get('years_owned') and '%s years owned' % form['years_owned'],
                        form.get('age') and 'Age %s' % form['age'],
                        form.get('marital_status'),
                        (form.get('dependents') is not None and
                         '%s dependents' % form.get('dependents')) or None) if x]
    a('<div class="sub">%s</div>' % ' · '.join(_e(b) for b in bits))
    a('</div><div class="bmeta">PREPARED %s<br>'
      '<span class="stage">STAGE &nbsp;DATA RECEIVED</span></div></div>'
      % datetime.date.today().strftime('%m.%d.%Y'))

    a('<div class="kpis">')
    for label, val in (
        ("NET COLLECTIONS '%s" % (head_year[-2:] if head_year else ''),
         ('$' + money(headline['income'])) if headline else None),
        ('OVERHEAD', ('%.1f%%' % headline['overhead_pct']) if headline else None),
        ('OWNER COMP',
         ('$' + money(_ic.money(form.get('take_home'))))
         if _ic.money(form.get('take_home')) else None),
        ('TOTAL DEBT', debt_total(debts)),
        ('OBSERVED ASSETS', assets_total(holdings))):
        rendered = val if (val and '<span' in str(val)) else cell(val)
        a('<div class="kpi"><div class="kl">%s</div><div class="kv">%s</div></div>'
          % (label, rendered))
    a('</div>')

    a('<div class="cols"><div class="colL">')
    a('<h2>Initial notes</h2>')
    # The same facts the workbook prints. The page used to assemble its own
    # version of these from the intake form, which meant two outputs describing
    # one client from two separate readings of it, free to drift apart.
    bundle = _bundle(folder, client)
    for head, titles in (('PRACTICE', ('Practice', 'Overhead', 'Practice debt')),
                         ('PERSONAL', ('Personal', 'Personal debt'))):
        a('<div class="tag %s">%s</div><ul class="notes">'
          % ('tp' if head == 'PRACTICE' else 'tn', head))
        for block in (bundle.blocks if bundle else ()):
            if block.title not in titles:
                continue
            for f in block.facts:
                # Figures belong in the tables; this column is the prose.
                if f.value is None or isinstance(f.value, (int, float)):
                    continue
                a('<li><b>%s</b>, %s%s</li>'
                  % (_e(f.label), _e(str(f.value)),
                     ('<span class="why"> %s</span>' % _e(f.note))
                     if f.note else ''))
        a('</ul>')
    a('</div>')

    # ---- right: the numbers ---------------------------------------------
    a('<div class="colR">')
    a('<h2>Practice analysis<span class="src2">SOURCE: PMS + PRACTICE FINANCIALS</span></h2>')
    a('<table class="an"><tr><th>METRIC</th>')
    for n, y in enumerate(years):
        a('<th>%s%s</th>' % (y, '&nbsp;YTD' if y in partial else ''))
        if n:
            a('<th class="d">Δ%s→%s</th>' % (years[n - 1][-2:], y[-2:]))
    a('</tr>')
    for nm, cls in analysis_rows(prod_rows):
        a('<tr class="%s"><td>%s</td>' % ('b' if cls == 'b' else '', _e(nm)))
        prev = None
        for n, y in enumerate(years):
            v = prod_rows.get(y, {}).get(nm)
            a('<td>%s</td>' % (fmt(nm, v) if v is not None else cell(None)))
            if n:
                comparable = y not in partial and years[n - 1] not in partial
                a('<td class="d">%s</td>'
                  % (_delta(v, prev, pt='%' in nm) if comparable else ''))
            prev = v
        a('</tr>')
    a('</table>')

    a('<h2>Overhead<span class="src2">TAX RETURNS VS. PRACTICE FINANCIALS</span></h2>')
    a('<table class="an"><tr><th>BASIS</th>%s<th class="d">3-YR MOVE</th>'
      '<th>TARGET</th></tr>' % ''.join('<th>%s</th>' % y for y in years))
    a('<tr><td>Tax returns (1120-S)</td>')
    for y in years:
        t = tax.get(y)
        a('<td>%s</td>' % ('%.1f%%' % t['overhead_pct'] if t else cell(None)))
    tmv = ''
    if tax.get(years[0]) and tax.get(years[-1]):
        tmv = _delta(tax[years[-1]]['overhead_pct'],
                     tax[years[0]]['overhead_pct'], pt=True)
    a('<td class="d">%s</td><td>&le;60%%</td></tr>' % tmv)
    a('<tr><td>Practice financials (P&amp;L)</td>')
    for y in years:
        p = by_year.get(y)
        a('<td>%s</td>' % ('%.1f%%' % p['overhead_pct'] if p else cell(None)))
    mv = ''
    if len(years) > 1 and by_year.get(years[0]) and by_year.get(years[-1]):
        mv = _delta(by_year[years[-1]]['overhead_pct'],
                    by_year[years[0]]['overhead_pct'], pt=True)
    a('<td class="d">%s</td><td>&le;60%%</td></tr>' % mv)
    stated = form.get('overhead_stated')
    a('<tr><td>Client’s own estimate</td>')
    for y in years:
        a('<td>%s</td>' % (_e(stated) if (stated and y == years[-1])
                           else cell(None)))
    a('<td class="d"></td><td></td></tr>')
    # The template's basis difference is books against the return -- the two
    # accounts of the same year. The client's own estimate is a third thing and
    # is compared separately, below, because it is a belief rather than a basis.
    want = _ic.money(stated)
    a('<tr class="b"><td>Basis difference</td>')
    for y in years:
        p, t = by_year.get(y), tax.get(y)
        a('<td>%s</td>' % ('%+.1fpt' % (p['overhead_pct'] - t['overhead_pct'])
                           if (p and t) else cell(None)))
    a('<td class="d"></td><td></td></tr></table>')
    if want and headline:
        bits = ['the P&amp;L for %s puts overhead at %.1f%%'
                % (head_year, headline['overhead_pct'])]
        if tax.get(head_year):
            bits.append('the return puts it at %.1f%%'
                        % tax[head_year]['overhead_pct'])
        if want:
            bits.append('the client puts it at %s' % _e(stated))
        tail = ''
        if want:
            tail = (' The two documents agree within a few points; the '
                    'client’s own figure is %.0f points below them, and '
                    'settling that is the first conversation.'
                    % abs(headline['overhead_pct'] - want))
        a('<p class="note"><b>Reconciliation:</b> %s. Both bases hold out what '
          'the owner pays himself.%s</p>' % ('; '.join(bits), tail))

    a(flagbox(flags, 'overhead'))

    a('<div class="two">')
    # The fee study the firm already runs. Its output lands in
    # Documents/Business/Fees with the percentage in the filename, so this
    # reads the firm's own result rather than recomputing it.
    import compose as _comp
    _pct, fee_line = _comp.fee_study(folder)
    a('<div><h3>Fee positioning</h3><p class="small">%s</p></div>'
      % (_e(fee_line) if fee_line else cell(
          None, why='fee study not yet run for this client')))
    a('<div><h3>Open items</h3><ul class="oi">%s</ul></div>'
      % ''.join('<li>%s</li>' % _e(t) for t in open_items(folder, form, by_year)))
    a('</div></div></div>')

    a('<div class="markup">ADVISOR NOTES / MEETING MARKUP'
      '<div class="ruled"><div></div><div></div><div></div></div></div>')
    a('<div class="ft"><span>FOUR QUADRANTS ADVISORY · PROSPECT SUMMARY</span>'
      '<span>CONFIDENTIAL, INTERNAL USE ONLY</span><span>PAGE 1 OF 2</span></div>')
    a('</div>')

    # ---------------------------------------------------------------- page 2
    a('<div class="pg">')
    a('<div class="band p2"><h1 class="h2p">DEBT, CASHFLOW &amp; ASSETS</h1>'
      '<div class="bmeta">%s · %s</div></div>'
      % (_e(client.replace('|', '/')), datetime.date.today().strftime('%m.%d.%Y')))
    a('<h2>Debt schedule</h2>')
    a('<table class="an"><tr><th>OBLIGATION</th><th>TYPE</th><th>ORIGINAL</th>'
      '<th>BALANCE</th><th>RATE</th><th>PAYMENT</th><th>MATURITY</th></tr>')
    for side, rows in (('PRACTICE', debts.get('practice') or ()),
                       ('PERSONAL', debts.get('personal') or ())):
        a('<tr><td colspan="7" class="side">%s</td></tr>' % side)
        if not rows:
            a('<tr><td colspan="7">%s</td></tr>' % cell(None))
            continue
        total = payment = 0
        for r in rows:
            rate = r.get('rate')
            if rate and rate < 1:
                rate *= 100
            name = r.get('creditor') or '?'
            if r.get('account_last4'):
                name += ' x%s' % r['account_last4']
            total += r.get('balance') or 0
            payment += r.get('payment') or 0
            a('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
              '<td>%s</td><td>%s</td></tr>'
              % (_e(name), _e(r.get('description') or ''),
                 money(r.get('original')) or cell(None),
                 money(r.get('balance')) or cell(None),
                 ('%.2f%%' % rate) if rate else cell(None),
                 (money(r.get('payment')) + '/mo') if r.get('payment')
                 else cell(None),
                 _e(str(r.get('maturity'))) if r.get('maturity')
                 else cell(None)))
        a('<tr class="b"><td>%s subtotal</td><td></td><td></td><td>%s</td>'
          '<td></td><td>%s</td><td></td></tr>'
          % (side.title(), money(total), money(payment) + '/mo'))
    # An obligation whose terms exist only inside a sentence is listed, not
    # parsed. Oyler's building loan is the largest single debt in the file and
    # arrived as a letter.
    for r in debts.get('unread') or ():
        a('<tr><td colspan="7">%s</td></tr>'
          % cell(None, why='stated in prose, needs a person: %s'
                 % _e(r.get('source') or '')))
    a('</table>')
    a(flagbox(flags, 'debt'))

    a('<h2>Cashflow analysis<span class="src2">MONTHLY SURPLUS / (DEFICIT) BY '
      'ACCOUNT</span></h2>')
    a('<table class="an"><tr><th>ACCOUNT</th><th>AVG</th><th>NEG</th>'
      '<th>TREND</th></tr>')
    rows = (cash or {}).get('accounts') or ()
    if not rows:
        a('<tr><td colspan="4">%s</td></tr>'
          % cell(None, why='no bank statements read for this client yet'))
    for r in rows:
        # An account whose transactions could not be read has no surplus
        # worth printing: its deposits and expenses still contain money
        # that only moved between the client's own accounts. Printing the
        # figure anyway and marking it would be worse than printing the
        # reason, because the figure is what gets quoted.
        if not r.get('readable'):
            a('<tr><td>%s</td><td colspan="3">%s</td></tr>'
              % (_e(r['name']), cell(None, why=r.get('why') or '')))
            continue
        s = r.get('surplus') or 0
        neg, periods = r.get('negatives') or 0, r.get('periods') or 0
        a('<tr><td>%s</td><td class="%s">%s%s/mo</td><td>%s</td>'
          '<td>%s</td></tr>'
          % (_e(r['name']), 'neg' if s < 0 else '',
             '-$' if s < 0 else '$', money(abs(s)),
             ('%d of %d' % (neg, periods)) if periods else cell(None),
             _e(r.get('trend') or '') or '<span class="src">too few '
             'periods</span>'))
    a('</table>')
    a(flagbox(flags, 'cashflow'))

    a('<h2>Assets observed<span class="src2">PRACTICE, PROPERTY, RETIREMENT '
      '&amp; BANK, AS DOCUMENTED</span></h2>')
    a('<table class="an"><tr><th>HOLDING</th><th>BASIS</th><th>VALUE</th>'
      '<th>AS OF</th></tr>')
    if not holdings:
        a('<tr><td colspan="4">%s</td></tr>'
          % cell(None, why='no property, retirement or bank documents read '
                           'for this client yet'))
    total = 0
    for head, items in holdings:
        a('<tr><td colspan="4" class="side">%s</td></tr>' % head)
        for r in items:
            total += r.get('value') or 0
            a('<tr><td>%s</td><td class="bs">%s</td><td>%s</td>'
              '<td>%s</td></tr>'
              % (_e(r['name']), _e(r['note']),
                 _e(r['amount']) if r.get('amount')
                 else cell(None, why='no value yet'),
                 r['as_of'].strftime('%d %b %Y') if r.get('as_of')
                 else ''))
    if holdings:
        a('<tr class="b"><td>Total observed</td><td></td><td>$%s</td>'
          '<td></td></tr>' % money(total))
    a('</table>')
    # The tile above and this table are the same figure, so they cannot
    # disagree. What they can both miss is a holding nobody has sent a
    # document for, which is why the count travels with the total.
    a('<p class="note">What the documents show, not everything the household '
      'owns. Against total debt of %s this is a net position of %s, which '
      'the Assumptions states in full.</p>'
      % (('$' + money((debts.get('practice_balance') or 0)
                      + (debts.get('personal_balance') or 0))),
         ('$' + money(total - (debts.get('practice_balance') or 0)
                      - (debts.get('personal_balance') or 0)))))
    a(flagbox(flags, 'assets'))

    a('<div class="two">')
    a('<div><h3>Entities &amp; ownership</h3><p class="small">%s</p></div>'
      % cell(None))
    a('<div><h3>Insurance &amp; retirement</h3><p class="small">%s</p></div>'
      % cell(None))
    a('</div>')
    a('<div class="markup">ADVISOR NOTES / MEETING MARKUP<div class="ruled">'
      '<div></div><div></div><div></div><div></div></div></div>')
    a('<div class="ft"><span>FOUR QUADRANTS ADVISORY · PROSPECT SUMMARY</span>'
      '<span>CONFIDENTIAL, INTERNAL USE ONLY</span><span>PAGE 2 OF 2</span></div>')
    a('</div>')
    return '\n'.join(L)


def _fee_done(folder):
    import compose as _comp
    return bool(_comp.fee_study(folder)[0])


def open_items(folder, form, by_year):
    """What is still outstanding, said once and in plain words.

    This replaces the badges. A reader wants the gaps as a short list they can
    work through, not scattered through a table as a label beside every figure
    that happens to be absent.
    """
    out = []
    if not by_year:
        out.append('Profit & loss, not yet readable')
    if not form:
        out.append('IC intake form, not in the folder')
    out.append('Debt schedule, practice sheet is free text; personal not sent')
    out.append('Personal bank + HSA statements, for the cashflow')
    out.append('Remaining investment statements, for assets observed')
    out.append('Fee schedule, for fee positioning')
    out.append('Tax returns, for the overhead tax basis')
    return out


CSS = """
body{background:#EFEDE7;margin:0;padding:24px;
  font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,sans-serif;
  color:#1B2A41;-webkit-font-smoothing:antialiased}
.pg{max-width:940px;margin:0 auto 24px;background:#fff;
  box-shadow:0 1px 4px rgba(0,0,0,.14);padding-bottom:16px}
.band{background:#16324F;color:#fff;padding:16px 26px 14px;
  display:flex;justify-content:space-between;align-items:flex-start}
.band.p2{align-items:center;padding:12px 26px}
.kick{font-size:9.5px;letter-spacing:1.6px;color:#F08418;font-weight:600}
h1{margin:5px 0 0;font-size:27px;font-weight:700;letter-spacing:-.3px}
h1 .bar{color:#F08418;font-weight:300;margin:0 9px}
.h2p{font-size:17px;letter-spacing:1.4px;margin:0}
.sub{font-size:11.5px;color:#BFCBD8;margin-top:5px}
.bmeta{font-size:9.5px;letter-spacing:1.1px;color:#9FB0C2;text-align:right;
  line-height:1.7;white-space:nowrap}
.stage{color:#F08418}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:9px;
  padding:14px 26px 2px}
.kpi{border:1px solid #DFDAD0;padding:7px 10px 8px}
.kl{font-size:8.5px;letter-spacing:1px;color:#8A9099}
.kv{font-size:19px;font-weight:700;color:#16324F;margin-top:1px;
  white-space:nowrap}
.cols{display:grid;grid-template-columns:37% 63%;gap:26px;padding:12px 26px 0}
h2{font-size:11px;letter-spacing:1.3px;text-transform:uppercase;color:#16324F;
  border-left:3px solid #F08418;padding-left:8px;margin:18px 0 7px;
  font-weight:700;display:flex;justify-content:space-between;align-items:baseline}
.colL h2:first-child,.colR h2:first-child{margin-top:4px}
h3{font-size:10px;letter-spacing:1.2px;text-transform:uppercase;color:#F08418;
  margin:14px 0 5px;border-bottom:1px solid #E4E0D8;padding-bottom:4px}
.src2{font-size:8.5px;letter-spacing:1px;color:#A4ABB4;font-weight:400}
.tag{display:inline-block;font-size:9px;letter-spacing:1.2px;font-weight:700;
  padding:2px 7px;margin:10px 0 2px}
.tp{background:#E8F0F7;color:#2F6DA3}
.tn{background:#F3EDF7;color:#6B4C8A}
ul.notes{list-style:none;margin:4px 0 0;padding:0}
ul.notes li{position:relative;padding-left:12px;margin-bottom:8px;
  font-size:12px;line-height:1.5}
ul.notes li:before{content:"";position:absolute;left:0;top:6px;width:4px;
  height:4px;background:#F08418}
ul.notes b{color:#16324F}
table.an{width:100%;border-collapse:collapse;font-size:11.5px}
table.an th{text-align:right;font-size:8.5px;letter-spacing:.7px;color:#8A9099;
  border-bottom:1px solid #16324F;padding:4px 5px;font-weight:600}
table.an th:first-child{text-align:left}
table.an td{padding:3.5px 5px;border-bottom:1px solid #F2EFE9;text-align:right;
  font-variant-numeric:tabular-nums}
table.an td:first-child{text-align:left;color:#3C4A5A}
table.an tr.b td{font-weight:700;color:#16324F}
table.an tr:nth-child(even) td{background:#FBFAF8}
td.d,th.d{font-size:10px}
.up{color:#1F7A4D}.dn{color:#C0392B}.fl{color:#8A9099}
.side{font-size:9px;letter-spacing:1.2px;color:#2F6DA3;background:#E8F0F7;
  font-weight:700;padding:3px 5px}
.nil{color:#C3C8CE}
.src{font-size:8.5px;color:#A4ABB4;margin-left:5px}
/* A deficit is read as a deficit, not as a number with a sign in front
   of it. The colour is the only thing on the cashflow table doing that
   work, since the column is otherwise all figures of the same shape. */
.neg{color:#B3261E;font-weight:600}
/* Two to a row, so four flags take four lines rather than eight, and a
   client with none leaves a sentence rather than a hole. */
.flags{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:7px}
.fl{border-left:2.5px solid #F08418;background:#FFF8EF;padding:6px 9px}
.flh{font-size:10px;font-weight:700;color:#8A5218;letter-spacing:.2px}
.flw{font-size:9.5px;color:#6B5234;line-height:1.45;margin-top:2px}
/* The basis column is provenance, not a figure. Set quieter so the
   values stay the thing the eye runs down. */
.bs{font-size:9px;color:#6C7480;line-height:1.4}
.note{font-size:10.5px;color:#5D6773;margin:7px 0 0;line-height:1.5}
.note b{color:#16324F}
.small{font-size:11px;color:#5D6773}
.two{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:4px}
ul.oi{list-style:none;margin:4px 0 0;padding:0;counter-reset:oi}
ul.oi li{counter-increment:oi;font-size:10.5px;color:#5D6773;
  padding:2.5px 0 2.5px 18px;position:relative;border-bottom:1px solid #F5F2EC}
ul.oi li:before{content:counter(oi);position:absolute;left:0;top:3px;
  font-size:9px;color:#F08418;font-weight:700}
.markup{margin:18px 26px 0;font-size:9px;letter-spacing:1.3px;color:#8A9099}
.ruled{margin-top:5px;border:1px solid #E4E0D8}
.ruled div{height:21px;border-bottom:1px solid #EFECE5}
.ruled div:last-child{border-bottom:none}
.ft{margin:14px 26px 0;border-top:1px solid #E4E0D8;padding-top:7px;
  font-size:8.5px;letter-spacing:1px;color:#A4ABB4;
  display:flex;justify-content:space-between}
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
