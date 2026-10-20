#!/usr/bin/env python3
"""Turn a pile of related figures into the line an analyst would write.

    python3 compose.py "<client folder>"

WHY THE VALUE AND NOT A NOTE BESIDE IT
"Associates = 30% of collections" is true and tells a reader nothing. They
still have to find out who the associates are, whether that number is their pay
or their share, how many days they work and whether one of them has left. The
analyst's own line says all of it:

    Martini, 30% of collections, contract 2024. Days 87 to 142 to 107 YTD,
    production $363k to $683k to $737k. Cardosi left after 2025.

That is not a note bolted onto a figure. It IS the figure, composed from eight
of them. So these are built here, from facts that were already read and
checked, and the arithmetic never leaves the tool.

WHAT IS NOT HERE
Judgement. "His 46% may exclude associate pay" is a hypothesis about why two
documents disagree, and it belongs to notes.py, which can say it is a
hypothesis. Everything in this file is composition: counting, totalling,
ordering, and saying what is absent.
"""
import os
import re
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def money(v, cents=False):
    if v is None:
        return None
    return ('${:,.2f}' if cents else '${:,.0f}').format(v)


def k(v):
    """$683k, the way an analyst writes it in a note."""
    if v is None:
        return None
    if abs(v) >= 1e6:
        return '$%.2fm' % (v / 1e6)
    return '$%dk' % round(v / 1000.0)


def arrow(values):
    """'87 to 142 to 107' for a run of years, skipping what is missing."""
    got = [v for v in values if v is not None]
    return ' to '.join(got) if got else None


def practice_debt(rows, unread=()):
    """Every practice obligation as one line, with what is about to fall off."""
    live = [r for r in rows if r.get('balance')]
    if not live:
        return None
    total = sum(r['balance'] for r in live)
    payment = sum(r.get('payment') or 0 for r in live)
    bits = ['%s across %d obligations' % (money(total), len(live))]
    if payment:
        bits.append('%s/mo' % money(payment))

    # What drops off soon is the thing an analyst always notes: it is cash
    # that frees itself without anyone doing anything.
    horizon = datetime.date.today().year + 2
    soon = [r for r in live if r.get('maturity') and r['maturity'] <= horizon]
    if soon:
        bits.append('%d mature by %d' % (len(soon), horizon))

    # A line of credit is not a loan. Drawn to its limit it is a warning; undrawn
    # it is capacity. Either way the balance alone does not say which.
    for r in live:
        if 'credit' not in (r.get('description') or '').lower() \
                and 'credit' not in r['creditor'].lower():
            continue
        avail = r.get('available_credit')
        if avail is not None:
            limit = r['balance'] + avail
            bits.append('LOC drawn to %s of %s' % (money(r['balance']),
                                                   money(limit)))
    if unread:
        bits.append('%d more stated in prose, unread' % len(unread))
    return '. '.join(bits) + '.'


def personal_debt(rows, expected=None):
    if not rows:
        return None
    total = sum(r.get('balance') or 0 for r in rows)
    payment = sum(r.get('payment') or 0 for r in rows)
    named = ', '.join(
        '%s%s' % (r.get('creditor') or '?',
                  (' x%s' % r['account_last4']) if r.get('account_last4') else '')
        for r in rows)
    out = '%s across %d: %s' % (money(total), len(rows), named)
    if payment:
        out += '. %s/mo' % money(payment)
    if expected and expected > len(rows):
        out += '. %d more referenced elsewhere with no statement' % (
            expected - len(rows))
    return out + '.'


def associates(roles, production_by_year, days_by_doctor, years, comp=None):
    """Who the associates are, what they produce, and who has gone."""
    people = [(c, r) for c, r in roles.items()
              if r.get('role') == 'associate' and
              (r.get('name') or '').lower() not in ('orthodontics',)]
    if not people:
        return None
    parts = []
    for code, role in sorted(people, key=lambda cr: cr[1].get('name') or cr[0]):
        name = (role.get('name') or code).replace('Dr. ', '').split()[-1]
        prod = [production_by_year.get(y, {}).get(code) for y in years]
        days = [(days_by_doctor.get(name) or {}).get(y) for y in years]
        bit = name
        if role.get('through'):
            bit += ' (left after %s)' % role['through']
        shown = arrow([str(d) for d in days if d is not None])
        if shown:
            bit += ', days %s' % shown
        shown = arrow([k(p) for p in prod if p is not None])
        if shown:
            bit += ', production %s' % shown
        parts.append(bit)
    line = '; '.join(parts)
    if comp:
        line = '%s. Comp: %s' % (line, comp)
    return line + '.'


def overhead(pnl_pct, tax_pct, stated_pct, year):
    """The three bases in one line, because they are only useful together."""
    bits = []
    if pnl_pct is not None:
        bits.append('%.1f%% on the %s P&L' % (pnl_pct, year))
    if tax_pct is not None:
        bits.append('%.1f%% on the return' % tax_pct)
    if stated_pct is not None:
        bits.append('%.0f%% client-stated' % stated_pct)
    if not bits:
        return None
    line = ' / '.join(bits)
    if pnl_pct is not None and stated_pct is not None:
        line += '. Gap to the client’s figure: %.0f points' % abs(
            pnl_pct - stated_pct)
    return line + '.'


def collections(stated, documented, year):
    if documented is None:
        return None
    line = '%s on the %s P&L' % (money(documented), year)
    if stated is not None:
        delta = documented - stated
        line += '; client stated %s (%s %s)' % (
            money(stated), money(abs(delta)),
            'lower' if delta > 0 else 'higher')
    return line + '.'


def bank_accounts(accounts, personal_expected=True):
    """What is in the accounts, and whose accounts are missing."""
    if not accounts:
        return None
    cash = [a for a in accounts if a.get('kind') == 'Cash']
    if not cash:
        return None
    total = sum(a['balance'] for a in cash)
    sides = {a.get('side') for a in cash}
    line = '%s across %d account%s' % (money(total), len(cash),
                                       '' if len(cash) == 1 else 's')
    if sides == {'Practice'} and personal_expected:
        line += ', all practice. No personal statements provided'
    as_of = sorted(a.get('as_of') or '' for a in cash)
    if as_of and as_of[-1]:
        line += ', latest %s' % as_of[-1]
    return line + '.'


ADDRESS = re.compile(
    r'\b(\d{3,5}\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?\s+'
    r'(?:Dr|Drive|St|Street|Rd|Road|Ln|Lane|Way|Blvd|Ave|Avenue))'
    r'[,\s]+([A-Z][a-z]+)[,\s]+([A-Z]{2})\s+(\d{5})', re.I)


SUFFIX = {'dr': 'Drive', 'drive': 'Drive', 'st': 'Street', 'street': 'Street',
          'rd': 'Road', 'road': 'Road', 'ln': 'Lane', 'lane': 'Lane',
          'ave': 'Avenue', 'avenue': 'Avenue', 'blvd': 'Boulevard',
          'boulevard': 'Boulevard', 'way': 'Way'}


def _normal_street(street):
    """One spelling per street. "Flossie Dr" and "Flossie Drive" are one
    address, and counting them separately made the practice look like two."""
    parts = street.split()
    if parts and parts[-1].lower().rstrip('.') in SUFFIX:
        parts[-1] = SUFFIX[parts[-1].lower().rstrip('.')]
    return ' '.join(p.title() for p in parts)


def cache_dir(folder):
    """Where the extracted text for this client lives.

    Two places, historically: loose in the client folder from an early
    audit, and under Original_sourcedocs once the documents were filed.
    Readers that knew about only one of them silently read half the client's
    file -- which is how Oyler's home address came back as his ex-wife's
    house, from a cache written before he moved.
    """
    direct = os.path.join(folder, '.fq_cache')
    nested = os.path.join(folder, 'Original_sourcedocs', '.fq_cache')
    if os.path.isdir(direct):
        return direct
    return nested if os.path.isdir(nested) else direct


def addresses(folder, head=1500):
    """Addresses printed on the documents, commonest first.

    Read from the letterhead rather than asked for. Every bank statement, P&L
    and tax return carries the practice address at the top, and the mortgage
    statements carry the home; the one that appears most often on practice
    documents is the practice.
    """
    import collections
    import glob as _glob
    seen = collections.Counter()
    for path in _glob.glob(os.path.join(cache_dir(folder), '*.txt')):
        text = ' '.join(open(path, errors='replace').read()[:head].split())
        for m in ADDRESS.finditer(text):
            street, town, state, _zip = m.groups()
            seen[(_normal_street(street), town.title(),
                  state.upper())] += 1
    return seen.most_common()


def office(form, folder):
    """Where the practice is, and on what terms."""
    # Town and state only. The street number is on every document in the
    # folder already, and an initial note is read for where the practice is,
    # not for posting a letter to it.
    found = addresses(folder)
    where = None
    if found:
        _street, town, state = found[0][0]
        where = '%s, %s' % (town, state)
    owns = (form.get('building') or '').strip().lower().startswith('own')
    bits = []
    if where:
        bits.append(where)
    bits.append('owns the building' if owns else
                (form.get('building') or 'tenure not stated'))
    sqft = form.get('building_sqft')
    if sqft:
        try:
            bits.append('{:,.0f} sq ft'.format(float(str(sqft).replace(',', ''))))
        except ValueError:
            bits.append('%s sq ft' % sqft)
    pay = form.get('building_payment')
    if pay:
        try:
            bits.append('%s/mo' % money(float(str(pay).replace(',', '').lstrip('$'))))
        except ValueError:
            bits.append('%s/mo' % pay)
    return ', '.join(bits) + '.' if bits else None


def residence(folder):
    """The home address, which is whichever one is not the practice.

    The practice is the address that appears most often, because it is on
    every statement, return and report. The home turns up on the mortgage and
    the retirement statements. So the second-commonest is the residence, and
    nothing has to be told which town the practice is in.
    """
    got = residence_full(folder)
    if not got:
        return None
    _street, town, state = got
    return '%s, %s' % (town, state)


def residence_full(folder):
    """The home address with its street, as (street, town, state).

    residence() deliberately prints town and state only, because that is what
    the initial notes asked for. The Assumptions needs the street: the
    property section states the address, and whoever pulls the market estimate
    has to type it into Zillow. Reporting "no street address on file" because
    the caller above happened to truncate it is how a figure that is sitting
    in six documents comes to look missing.
    """
    found = addresses(folder)
    if len(found) < 2:
        return None
    return found[1][0]


def schedule(form):
    """How many days the doctor and hygiene chairs run in a week.

    Capacity only. How far out those days are booked is its own row -- see
    booked_out() -- because the three lead times are the practice's demand
    signal and the reviewer wants to find them in one place rather than
    picking them out of three sentences about something else.
    """
    bits = []
    if form.get('doctor_days'):
        bits.append('doctor %s days/wk' % form['doctor_days'])
    if form.get('hygiene_days'):
        bits.append('hygiene %s days/wk' % form['hygiene_days'])
    return '. '.join(bits) + '.' if bits else None


def booked_out(form):
    """Doctor, hygiene and new patient lead times, together on one row.

    These three answer the same question from three directions: how long a
    patient waits. Read together they say whether the practice is capacity
    constrained or demand constrained, which is the difference between hiring
    an associate and spending on marketing. Read apart they say very little,
    which is why they get their own row instead of trailing the days worked.
    """
    bits = []
    if form.get('doctor_booked'):
        bits.append('doctor %s weeks out' % form['doctor_booked'])
    if form.get('hygiene_booked'):
        bits.append('hygiene %s months out' % form['hygiene_booked'])
    if form.get('new_patient_wait'):
        bits.append('new patients next open %s' % form['new_patient_wait'])
    return '. '.join(bits) + '.' if bits else None


def new_patients(form, counts, years):
    """What the client says against what the reports count."""
    stated = form.get('new_patients_mo')
    bits = []
    if stated:
        bits.append('%s/month claimed' % stated)
    actual = [(y, (counts.get(y) or {}).get('new_patients')) for y in years]
    actual = [(y, n) for y, n in actual if n]
    if actual:
        bits.append('reports show ' + ', '.join(
            '%s in %s' % ('{:,}'.format(n), y) for y, n in actual))
    return '. '.join(bits) + '.' if bits else None


def payer_mix(form):
    if not form.get('in_network'):
        return None
    yes = str(form['in_network']).strip().lower().startswith(('y', 'in'))
    return ('In network with some carriers.' if yes
            else 'Out of network, 100% fee for service.')


FEE_PCT = re.compile(r'([+-]?\d{1,3}\.\d{1,2})\s*%')


def fee_study(folder):
    """How far the practice's fees sit from the benchmark.

    The firm already has a convention for this and it is better than anything
    worth inventing: the fee study lands in Documents/Business/Fees, and the
    result file carries the percentage in its own name -- "Fee study results
    -47.33%.eml". So the figure is read off the filename, and the workbook
    beside it is the working.

    A positive number means fees sit above the benchmark, a negative below.
    Nothing here computes it; the fee-comparison skill does, and this only
    finds what it left behind.
    """
    import glob as _glob
    best = None
    for path in _glob.glob(os.path.join(folder, '**', '*'), recursive=True):
        name = os.path.basename(path)
        if 'fee' not in name.lower():
            continue
        m = FEE_PCT.search(name)
        if not m:
            continue
        pct = float(m.group(1))
        # A results file is the statement; a workbook that happens to carry a
        # percentage in its name is the working behind it.
        weight = 2 if 'result' in name.lower() else 1
        if best is None or weight > best[0]:
            best = (weight, pct, name)
    if not best:
        return None, None
    _w, pct, name = best
    where = 'above' if pct > 0 else 'below'
    return pct, '%+.2f%% %s the benchmark (from %s).' % (pct, where, name)


ENTITY_LINE = re.compile(
    r'^\s*([A-Z][A-Za-z.,&\'\- ]{6,70}?(?:,?\s*(?:DDS|DMD|P\.?C\.?|LLC|'
    r'L\.L\.C\.|Inc\.?|PLLC))[A-Za-z.,& ]{0,30})\s*$', re.M)


def entity_name(folder):
    """The practice's legal name, as the tax return states it.

    The plan names the entity in the practice-value section ("the
    S-corporation, Macatawa Smiles"), and the return is the only document
    that states the legal name rather than a bookkeeper's abbreviation.

    Matched on content, not on filename. The audit cache names its files by
    content hash, so "which file is the 1120-S" cannot be answered by
    looking at the name; and a filename like "2025 Oyler Family
    Dentistry_Profit and Loss.xlsx" would otherwise be mistaken for the
    company's name, which is how a plan ends up naming an S-corporation
    after a spreadsheet.
    """
    import glob as _glob
    seen = {}
    for path in _glob.glob(os.path.join(cache_dir(folder), '*.txt')):
        head = open(path, errors='replace').read(5000)
        # The IRS header on the form itself, and the preparer's cover
        # sheet, which is often the only page with a text layer.
        if not re.search(r'S[- ]Corporation Return|Income Tax Return for an'
                         r' S Corporation', head, re.I):
            continue
        for hit in ENTITY_LINE.findall(head):
            hit = ' '.join(hit.split()).strip(' ,')
            if 4 < len(hit) < 72:
                seen[hit] = seen.get(hit, 0) + 1
    if not seen:
        return None
    return sorted(seen.items(), key=lambda kv: (-kv[1], len(kv[0])))[0][0]
