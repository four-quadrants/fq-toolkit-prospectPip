#!/usr/bin/env python3
"""Everything the documents say about one client, in one structure.

    python3 facts.py "<client folder>"

WHY THIS EXISTS
The readers each answer their own question: overhead from the P&L, the tax
basis from the return, production from the scans, debt from the schedule. Until
now the page stitched them together inline, which meant a second output could
only be built by stitching them again, differently, and the two would drift.

So the stitching happens once, here, and the outputs are views. The workbook
and the Prospect Summary read the same facts and cannot disagree about them.

A FACT IS NOT A NUMBER
It is a number, a label, where it came from, what it is as of, and -- when it
is absent -- what is needed to get it and why that matters. A figure stripped
of its source is the thing this whole project exists to stop producing.
"""
import os
import store as _store  # noqa: E402
import re
import sys
import argparse
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import summary as _summary                                   # noqa: E402
import tax_basis as _tax                                     # noqa: E402
import production as _prod                                   # noqa: E402
import practice_facts as _pf                                 # noqa: E402
import debt as _debt                                         # noqa: E402
import intake_form as _ic                                    # noqa: E402
import compose as _compose                                   # noqa: E402
import assets as _assets                                     # noqa: E402

MONEY = '$#,##0;($#,##0);-'
PCT = '0.0%'
NUM = '#,##0'
# Per patient and per day: the lead advisor reads these to the cent.
MONEY2 = '$#,##0.00;($#,##0.00);-'
NUM2 = '#,##0.00'
TEXT = None


class Fact(object):
    __slots__ = ('label', 'value', 'fmt', 'source', 'where', 'as_of',
                 'note', 'needed', 'why', 'flags', 'questions')

    def __init__(self, label, value=None, fmt=TEXT, source=None, where=None,
                 as_of=None, note=None, needed=None, why=None,
                 flags=None, questions=None):
        self.label, self.value, self.fmt = label, value, fmt
        self.source, self.where, self.as_of = source, where, as_of
        self.note, self.needed, self.why = note, needed, why
        # Written by notes.py when it has been run; empty otherwise, and the
        # workbook simply shows a narrower note column.
        self.flags, self.questions = flags or [], questions or []


Block = namedtuple('Block', 'title facts')

STATES = {'AL': 'Alabama', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California',
          'CO': 'Colorado', 'FL': 'Florida', 'GA': 'Georgia', 'ID': 'Idaho',
          'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
          'KY': 'Kentucky', 'LA': 'Louisiana', 'MI': 'Michigan',
          'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri',
          'NE': 'Nebraska', 'NV': 'Nevada', 'NC': 'North Carolina',
          'OH': 'Ohio', 'OK': 'Oklahoma', 'OR': 'Oregon',
          'PA': 'Pennsylvania', 'SC': 'South Carolina', 'TN': 'Tennessee',
          'TX': 'Texas', 'UT': 'Utah', 'VA': 'Virginia', 'WA': 'Washington',
          'WI': 'Wisconsin', 'WV': 'West Virginia', 'NY': 'New York',
          'NJ': 'New Jersey', 'MD': 'Maryland', 'MA': 'Massachusetts'}


class Bundle(object):
    def __init__(self, client, blocks, years, series, folder=None):
        self.client, self.blocks = client, blocks
        # So anything downstream can reach the client's own documents without
        # being told again where they are.
        self.folder = folder
        self.years, self.series = years, series
        # How many months each year's P&L actually covers, so anything
        # downstream can tell a full year from a year to date.
        self.months_by_year = {}
        # Notes written about a year-by-year metric rather than a block fact.
        # The first version dropped these on the floor: six of nine notes
        # named a series row, which is exactly where a trend observation
        # belongs, and none of them reached the page.
        self.series_notes = {}
        # {year: P&L and tax-basis overhead parts}, for the side-by-side table.
        self.overhead_by_year = {}
        # {'year', 'months'} when the newest year is a year to date.
        self.ytd = None

    @property
    def forename(self):
        """The given name, which is what the plan's prose actually uses.

        Every one of the 44 plans reviewed says "We assume that Brian is set
        to retire", never the surname and never the title. The documents name
        the client as "Dr. Brian Oyler" or "Oyler, Brian", so the given name
        is the second word of the former and the second field of the latter.
        """
        name = (self.client or '').strip()
        if not name:
            return None
        if ',' in name:
            tail = name.split(',', 1)[1]
            parts = tail.split()
        else:
            parts = [p for p in name.replace('.', ' ').split()
                     if p.lower() not in ('dr', 'drs', 'mr', 'mrs', 'ms')]
            parts = parts[:-1] if len(parts) > 1 else parts
        return parts[0] if parts else None

    @property
    def surname(self):
        """The family name, as the plan's prose uses it ("the Oyler home").

        The client string arrives as "Dr. Brian Oyler" or "Oyler, Brian", so
        take the last word of the former and the first field of the latter,
        after dropping a title.
        """
        name = (self.client or '').strip()
        if not name:
            return None
        if ',' in name:
            name = name.split(',')[0]
        parts = [p for p in name.replace('.', ' ').split()
                 if p.lower() not in ('dr', 'drs', 'mr', 'mrs', 'ms')]
        return parts[-1] if parts else None

    def all_facts(self):
        for block in self.blocks:
            for fact in block.facts:
                yield fact


def _pct(v):
    """A percentage as Excel wants it: a fraction, not a number out of 100."""
    return None if v is None else round(v / 100.0, 5)


def attach_notes(bundle, folder):
    """Fold notes.py's output onto the facts it was written about."""
    import json as _json
    path = _store.json_path(folder, 'notes.json')
    try:
        with open(path) as fh:
            written = _json.load(fh)
    except (OSError, ValueError):
        return bundle
    for fact in bundle.all_facts():
        got = written.get(fact.label)
        if not got:
            continue
        if got.get('note'):
            fact.note = got['note']
            # A pain point with nothing from the IC form takes what was
            # written from the calls as its value, rather than a yellow
            # "add from the initial call" over a note that already says it.
            if fact.value is None and fact.where == 'pain point':
                fact.value, fact.note, fact.needed = got['note'], None, None
        # Flags the code raised itself stay; the written ones add to them.
        fact.flags = (list(fact.flags or ()) + [x for x in (got.get('flags') or ())
                                                 if x not in (fact.flags or ())])[:2]
        fact.questions = list(got.get('questions') or ())[:2]

    labels = {f.label for f in bundle.all_facts()}
    for name, _by_year, _fmt in bundle.series:
        got = written.get(name)
        if got and name not in labels:
            bundle.series_notes[name] = got
    return bundle


# Short forms people go by, both ways: a form signed "Bill" is not a mismatch
# for a client filed as William.
NICKNAMES = [{'james', 'jim', 'jimmy', 'jamie'}, {'william', 'will', 'bill', 'billy'},
             {'robert', 'rob', 'bob', 'bobby'}, {'michael', 'mike'},
             {'steven', 'stephen', 'steve'}, {'christopher', 'chris'},
             {'matthew', 'matt'}, {'daniel', 'dan', 'danny'}, {'thomas', 'tom'},
             {'joseph', 'joe'}, {'anthony', 'tony'}, {'katherine', 'kathryn', 'kate', 'katie'},
             {'elizabeth', 'liz', 'beth'}, {'benjamin', 'ben'}, {'samuel', 'sam'},
             {'jonathan', 'jon', 'john'}, {'nicholas', 'nick'}, {'andrew', 'andy', 'drew'},
             {'richard', 'rick', 'rich'}, {'edward', 'ed', 'eddie'}, {'alexander', 'alex'}]


def _same_first(a, b):
    a, b = (a or '').strip().lower(), (b or '').strip().lower()
    if not a or not b or a == b or a.startswith(b) or b.startswith(a):
        return True
    return any(a in g and b in g for g in NICKNAMES)


def ic_mismatch(form, client, profile):
    """Reasons to doubt the IC form in the folder is this client's.

    The form is found by its file name, so a form for another doctor with the
    same surname gets filed and read as this client's (a "Dana" form in a
    Robin's folder: different age, family, software and rent). The name is
    checked against the client folder, and age and marriage against what the
    call notes say (profile).
    """
    why = []
    m = re.match(r'\s*[^,]+,\s*([A-Za-z]+)', client or '')
    first = m.group(1) if m else None
    if first and form.get('first_name') and not _same_first(form['first_name'], first):
        why.append('the form is signed %s %s; the client is %s'
                   % (form.get('first_name'), form.get('last_name') or '', first))
    try:
        fa = int(re.search(r'\d+', str(form.get('age') or '')).group(0))
        pa = int(re.search(r'\d+', str((profile.get('age') or {}).get('value') or '')).group(0))
        if abs(fa - pa) > 2:
            why.append('the form says age %d; the call notes say %d' % (fa, pa))
    except (AttributeError, ValueError):
        pass
    fm = str(form.get('marital_status') or '').lower()
    pm = str((profile.get('marital_status') or {}).get('value') or '').lower()
    if fm and pm and (('single' in fm) != ('single' in pm)) and ('married' in fm or 'married' in pm):
        why.append('the form says %s; the call notes say %s'
                   % (form.get('marital_status'), (profile.get('marital_status') or {}).get('value')))
    return why


def gather(folder, client=None):
    client = client or os.path.basename(folder.rstrip('/'))

    form = {}
    src = _ic.find_form_near(folder)
    if src:
        form = _ic.parse(src)
    ic_name = os.path.basename(src) if src else None

    pnl = {p['year']: p for p in _summary.gather(folder) if p.get('year')}
    tax = _tax.gather(folder)
    counts = (_pf.gather(folder) or {}).get('by_year') or {}
    debts = _debt.gather(folder)
    try:
        prod = _prod.gather(folder)
    except Exception:
        prod = {}
    # Balances are read by asking, not by pattern: "balance" appears a dozen
    # times on a statement meaning a dozen things. Absent if assets.py has not
    # been run, and the lines below simply report that nothing has been read.
    try:
        from classify_claude import source_index
        held = _assets.gather(folder, sources=source_index(folder))
    except Exception:
        held = {'accounts': [], 'by_kind': {}, 'total': None}

    # What Claude read from documents the readers above could not, each
    # figure checked against its document (doc_readings.py). It only fills
    # what the readers left blank.
    profile = {}
    ic_doubt = []
    extra_notes = {}
    balance_rows, extra_months = set(), {}
    overhead_extra = []
    count_months = {}
    try:
        import doc_readings as _dr
        got, _problems = _dr.check(folder)
    except Exception:                                        # noqa: BLE001
        got = {}
    if got:
        for y, v in (got.get('pnl') or {}).items():
            pnl.setdefault(y, v)
        for y, v in (got.get('tax') or {}).items():
            tax.setdefault(y, v)
        for y, v in (got.get('production') or {}).items():
            # The production reader leaves a stub ({'values': {}}) for a year
            # whose report it found but could not read: that is not a reading.
            if not (prod.get(y) or {}).get('values'):
                prod[y] = v
        # Patients are patients seen (visits) from the reports, not a count
        # of active patients the client typed up: a reading of patients seen
        # replaces what the code read. Other counts only fill blanks.
        for y, vals in (got.get('counts') or {}).items():
            for k, v in vals.items():
                if k == 'total_patients':
                    counts.setdefault(y, {})[k] = v
                else:
                    counts.setdefault(y, {}).setdefault(k, v)
        count_months = (got.get('counts_months') or {})
        for side in ('practice', 'building', 'personal'):
            # Claude's checked reading wins when there is one: it has put each
            # debt on the right side (a home mortgage typed on the practice
            # schedule) and read terms a template cannot (a quarterly payment).
            if (got.get('debts') or {}).get(side):
                debts[side] = got['debts'][side]
        profile = got.get('profile') or {}
        # Any IC form field can come from the call notes instead (profile in
        # doc_readings, with the notes as its source) when the form is missing
        # or is not this client's: what the client SAID still belongs on the
        # sheet, marked with where it was said.
        form_keys = {k for k, _ in _ic.FIELDS} | {
            'marital_status', 'dependents', 'ownership', 'pms', 'age'}
        ic_doubt = ic_mismatch(form, client, profile) if form else []
        for k in form_keys:
            # When the form looks like someone else's, what the call notes say
            # wins over it; otherwise the notes only fill its blanks.
            if (ic_doubt or not form.get(k)) and (profile.get(k) or {}).get('value'):
                form[k] = profile[k]['value']

    def pv_(key):
        """A profile line Claude read, with the document it came from."""
        v = profile.get(key) or {}
        return v.get('value'), v.get('source')

    # What they own: a condo, when the debt or the analyst says so.
    premises = (pv_('premises')[0] if profile.get('premises') else None) or next(
        ('condo' for side in ('practice', 'personal') for r in (debts.get(side) or [])
         if 'condo' in ' '.join(str(r.get(k) or '') for k in ('description', 'what')).lower()
         and 'home' not in str(r.get('description') or '').lower()
         # a personal condo counts only when it is the office, not a rental
         and (side == 'practice' or re.search(r'office|practice|suite', ' '.join(
             str(r.get(k) or '') for k in ('description', 'what')), re.I))
         and not re.search(r'rental', ' '.join(
             str(r.get(k) or '') for k in ('description', 'what')), re.I)), None)
    years = sorted(set(pnl) | set(prod) | set(counts))[-3:]
    # A return for the year before those (often sent as "Action needed...
    # please sign") adds one earlier column, as the lead advisor lays it out.
    earlier = [y for y in sorted(tax) if years and y < years[0]]
    if earlier:
        years = [earlier[-1]] + years
    full = [y for y in years if (pnl.get(y, {}).get('months') or 0) >= 12]
    latest = full[-1] if full else (years[-1] if years else None)
    p = pnl.get(latest, {})
    # The newest return on file when the P&L year has none yet: Rebol's 2024
    # return is missing, and a blank tax basis hid the 2023 one.
    tax_year = latest if latest in tax else (max(tax) if tax else None)
    t = tax.get(tax_year, {}) if tax_year else {}

    # ------------------------------------------------------------- practice
    if form and not ic_doubt:
        ic_doubt = ic_mismatch(form, client, profile)
    form_file = ic_name
    if ic_doubt:
        # The answers on the sheet now come from the call notes where they
        # had one: say so in the source column rather than naming the form.
        ic_name = 'call notes (the IC form in the folder is doubted)'
    practice = ([Fact('IC form check', "may not be this client's", TEXT, form_file,
                      'name, age and family against the call notes',
                      flags=['IC form may not be this client\'s: %s. Confirm before using '
                             'its answers; the call notes are used instead.' % '; '.join(ic_doubt)])]
                if ic_doubt else []) + [
        Fact('Entity structure', _compose.entity(tax, pv_('entity')[0]), TEXT,
             'tax returns' + (' and %s' % pv_('entity')[1] if pv_('entity')[1]
                              and 'tax return' not in pv_('entity')[1] else '')
             if not (pv_('entity')[1] and 'tax return' in pv_('entity')[1]) else pv_('entity')[1],
             'by year', needed='Ask on the call',
             why='Sole proprietor, S corp or more entities changes the tax plan'),
        Fact('Office location', _compose.office(form, folder, premises), TEXT,
             'document letterheads and the IC form', 'composed',
             needed='Ask on the call',
             why='Where it is, and on what terms, drives the overhead'),
        Fact('Owned since', (form.get('years_owned') and
                             '%s years' % form['years_owned'])
             or pv_('owned_since')[0], TEXT,
             ic_name if form.get('years_owned') else pv_('owned_since')[1],
             'years owned'),
        Fact('Collections', _compose.collections(
            _ic.money(form.get('collections_last')), p.get('income'), latest),
             TEXT, 'P&L %s and IC form' % latest if p else ic_name,
             'composed'),
        Fact('Associates', _compose.associates(
            _prod.load_roles(folder),
            {y: _providers_for(prod, y) for y in years},
            (_pf.gather(folder) or {}).get('doctor_days') or {},
            years, form.get('associate_comp'))
            or form.get('associate_comp')
            or (pv_('associates')[0] and pv_('associates')[0] + (
                ' The IC form says no associates.'
                if str(form.get('has_associates') or '').strip().lower()
                .startswith('no') else ''))
            or ('None' if str(form.get('has_associates') or '').strip()
                .lower().startswith('no') else None), TEXT,
             'Provider Summary, days-worked document, IC form'
             if not pv_('associates')[1] or _prod.load_roles(folder)
             else pv_('associates')[1],
             'composed'),
        Fact('Chairs', form.get('chairs_total') and (
             '%s total (%s op, %s hyg)' % (form.get('chairs_total'),
                                           form.get('chairs_operative'),
                                           form.get('chairs_hygiene'))
             if form.get('chairs_operative') or form.get('chairs_hygiene')
             else '%s total' % form.get('chairs_total')),
             TEXT, ic_name, 'chairs'),
        Fact('Payer mix', _compose.payer_mix(form), TEXT, ic_name,
             'insurances in network'),
        Fact('Schedule', _compose.schedule(form), TEXT, ic_name,
             'doctor and hygiene days worked per week',
             needed='Ask on the call, these go stale fast',
             why='Capacity is the lever behind most of the production work'),
        Fact('Booked out', _compose.booked_out(form), TEXT, ic_name,
             'doctor, hygiene and new patient lead times',
             needed='Ask on the call, these go stale fast',
             why='Whether the practice is short of chairs or short of '
                 'patients, which decides between hiring and marketing'),
        Fact('New patients', _compose.new_patients(form, counts, years), TEXT,
             'IC form and the count documents', 'stated against counted'),
        Fact('Ownership', form.get('ownership'), TEXT, ic_name),
        Fact('Collections projected', _ic.money(form.get('collections_proj'))
             or form.get('collections_proj'),
             MONEY if _ic.money(form.get('collections_proj')) else TEXT,
             ic_name, 'projected collections this year'),
        Fact('Practice management software', form.get('pms'), TEXT, ic_name,
             'practice management software'),
        Fact('Fees off by', _compose.fee_study(folder)[1], TEXT,
             'Documents/Business/Fees', 'the fee study result',
             needed='The fee study is done before the notes. Put its result '
                    '(e.g. "Fee Study -4.79%.pdf") in Documents/Business/Fees '
                    'and rebuild',
             why='Sizes the single easiest revenue lever'),
    ]
    # Projected collections far from last year's actual is a talking point
    # (the lead advisor writes "was just $872K in 2025; big difference").
    _proj = _ic.money(form.get('collections_proj'))
    _last = _ic.money(form.get('collections_last')) or p.get('income')
    if _proj and _last and abs(_proj / _last - 1) >= 0.2:
        for f in practice:
            if f.label == 'Collections projected':
                f.flags = ['Projects ${:,.0f} against ${:,.0f} last year ({:+.0%}); '
                           'what drives the change?'.format(_proj, _last, _proj / _last - 1)]

    # ------------------------------------------------------------- overhead
    overhead = [
        Fact('Overhead', _compose.overhead(
            p.get('overhead_pct'), t.get('overhead_pct'),
            _ic.money(form.get('overhead_stated')), latest, tax_year), TEXT,
             'P&L, 1120-S and IC form', 'composed'),
        Fact('Overhead, client says',
             _pct(_ic.money(form.get('overhead_stated')))
             if re.fullmatch(r'\s*[\d.]+\s*%?\s*', str(form.get('overhead_stated') or ''))
             else form.get('overhead_stated'),
             PCT if re.fullmatch(r'\s*[\d.]+\s*%?\s*', str(form.get('overhead_stated') or ''))
             else TEXT, ic_name, 'approximate overhead percentage'),
        Fact('Overhead, P&L basis', _pct(p.get('overhead_pct')), PCT,
             'P&L %s' % latest if p else None,
             'Expenses + Other Expenses less doctor wages and D&A, '
             'over Income + Other Income'),
        Fact('Overhead, tax basis', _pct(t.get('overhead_pct')), PCT,
             t.get('source') and '%s (%s)' % (t.get('source'), tax_year),
             'total deductions less officer comp and '
                              'depreciation, over total income'),
        Fact('Basis difference', _pct((p.get('overhead_pct') or 0) -
                                      (t.get('overhead_pct') or 0))
             if (p and t and tax_year == latest) else None, PCT, 'derived',
             'P&L basis less tax basis'),
        Fact('Income base (overhead denominator)', p.get('income_base'),
             MONEY, 'P&L %s' % latest if p else None,
             'Total for Income + Total for Other Income',
             note='Overhead is measured against this, not revenue alone. '
                  'Without it the ratio does not divide, and a reader '
                  'reasonably concludes something is being excluded.'),
        Fact('Other income', p.get('other_income'), MONEY,
             'P&L %s' % latest if p else None, 'Total for Other Income'),
        Fact('Total expenses (overhead numerator)', p.get('overhead'), MONEY,
             'P&L %s' % latest if p else None,
             'Expenses + Other Expenses, less doctor wages and D&A'),
        Fact('Doctor wages', p.get('doctor_salary'), MONEY,
             'P&L %s' % latest if p else None, 'Doctor Wages'),
        Fact('Depreciation / amortisation', p.get('depreciation_amort'), MONEY,
             'P&L %s' % latest if p else None,
             ', '.join(p.get('da_found') or ()) or 'none on this P&L'),
    ]

    # ----------------------------------------------------------------- debt
    # Two blocks, not one. Practice debt is the firm's own schedule filled in
    # by the office; personal debt arrives as statements from lenders. They are
    # chased separately, carried separately in the plan, and a reader looking
    # for the mortgage should not be scanning past an equipment loan.
    def obligations(rows, side_label):
        out = []
        for r in rows:
            name = r.get('creditor') or 'unnamed'
            if r.get('account_last4'):
                name += ' x%s' % r['account_last4']
            # "Florida Mortgage (Regions x3779)", as the lead advisor names them.
            if r.get('what'):
                where = STATES.get(r.get('state') or '', '')
                name = '%s%s (%s)' % (where + ' ' if where else '',
                                      r['what'], name)
            bits = []
            if r.get('rate'):
                rate = r['rate'] * 100 if r['rate'] < 1 else r['rate']
                bits.append('%.2f%%' % rate)
            if r.get('payment'):
                bits.append('%s/mo' % _fmt(r['payment']))
            if r.get('description'):
                bits.append(r['description'])
            # Term detail the lead advisor adds by hand otherwise: original
            # amount and year, the full term, fixed or variable, and what is
            # still missing.
            if r.get('original'):
                bits.append('orig %s%s' % (_fmt(r['original']),
                                           ' (%s)' % r['start'] if r.get('start') else ''))
            try:
                span = int(str(r.get('maturity'))[:4]) - int(str(r.get('start'))[:4])
            except (TypeError, ValueError):
                span = None
            if span:
                bits.append('%d-yr term to %s' % (span, r['maturity']))
            elif r.get('maturity'):
                bits.append('matures %s' % r['maturity'])
            if r.get('fixed'):
                bits.append(str(r['fixed']).lower())
            said = (r.get('description') or '').lower()
            missing = [k for k, have in (
                ('rate', r.get('rate') or '%' in said),
                ('payment', r.get('payment')),
                ('original amount', r.get('original') or 'origin' in said),
                ('term', r.get('maturity') or ' yr' in said or 'year' in said or 'month' in said),
                ('fixed/variable', r.get('fixed') or 'fixed' in said or 'variable' in said
                 or 'arm' in said.split() or 'ibr' in said)) if not have]
            if missing:
                bits.append('MISSING: %s' % ', '.join(missing))
            if r.get('pending'):
                out.append(Fact(name, 'Pending', TEXT, r.get('source'),
                                'not owed yet, kept out of the totals',
                                note='  ·  '.join(bits) or None))
                continue
            out.append(Fact(name, r.get('balance'), MONEY, r.get('source'),
                            r.get('as_of') or 'current balance',
                            note='  ·  '.join(bits) or None))
        if rows:
            out.append(Fact('%s total' % side_label,
                            round(sum(r.get('balance') or 0 for r in rows), 2),
                            MONEY, 'derived', 'sum of the rows above'))
            # No payment on any row is unknown, not zero.
            paid = [r.get('payment') for r in rows if r.get('payment')]
            out.append(Fact('%s debt service' % side_label,
                            round(sum(paid), 2) if paid else None,
                            MONEY, 'derived', 'sum of monthly payments',
                            needed=None if paid else 'The monthly payments'))
        return out

    practice_debt = obligations(debts.get('practice') or (), 'Practice')
    # The building LLC's loans sit inside practice debt, as their own lines
    # and subtotal, with a combined total: the practice's rent pays them, and
    # the lead advisor counts them with the practice.
    building = [dict(r, building=True) for r in debts.get('building') or ()]
    if building:
        practice_debt += obligations(building, 'Building (LLC)')
        both = [r for r in (debts.get('practice') or []) + building if not r.get('pending')]
        practice_debt.append(Fact('Practice + building total',
                                  round(sum(r.get('balance') or 0 for r in both), 2),
                                  MONEY, 'derived', 'practice and building LLC together'))
        practice_debt.append(Fact('Practice + building debt service',
                                  round(sum(r.get('payment') or 0 for r in both), 2),
                                  MONEY, 'derived', 'monthly payments, practice and building'))
    personal_debt = obligations(debts.get('personal') or (), 'Personal')

    # The composed line goes first, because it is the one a reader needs and
    # the rows beneath it are the working. "Two mature by 2028" cannot be seen
    # by scanning six balances; it has to be said.
    head = _compose.practice_debt(list(debts.get('practice') or ()) + building,
                                  debts.get('unread') or ())
    if head:
        practice_debt.insert(0, Fact('Practice debt', head, TEXT,
                                     'Debt schedule', 'composed from the rows '
                                     'below'))
    bank = _compose.bank_accounts(held.get('accounts') or ())
    if bank:
        practice.append(Fact('Bank accounts', bank, TEXT, 'bank statements',
                             'latest balance per account'))
    head = _compose.personal_debt(debts.get('personal') or ())
    if head:
        personal_debt.insert(0, Fact('Personal debt', head, TEXT,
                                     'mortgage statements',
                                     'composed from the rows below'))
    for row in debts.get('unread') or ():
        practice_debt.append(Fact('Obligation stated in prose', None, MONEY,
                                  row.get('source'),
                                  needed='A person to read the loan letter',
                                  why='The building loan is the largest single '
                                      'obligation and nothing has read it'))

    # ------------------------------------------------------------- personal
    personal = [
        Fact('Age', _ic.money(form.get('age')), NUM, ic_name, 'age'),
        Fact('Marital status', form.get('marital_status'), TEXT, ic_name),
        Fact('Residence', _compose.residence(folder), TEXT,
             'document letterheads', 'the address that is not the practice'),
        Fact('Dependents', _ic.money(form.get('dependents')), NUM, ic_name),
        Fact('Take-home, stated', _ic.money(form.get('take_home')), MONEY,
             ic_name, 'annual take-home pay'),
        # A number when they gave one; their words when they wrote a sentence
        # (Rebol: "down to 3 days a week ... by 55 and able to walk away by
        # 65" was read as age 3).
        Fact('Retirement age goal',
             _ic.money(form.get('retire_age'))
             if re.fullmatch(r'\s*\d{2}\s*', str(form.get('retire_age') or ''))
             else form.get('retire_age'),
             NUM if re.fullmatch(r'\s*\d{2}\s*', str(form.get('retire_age') or ''))
             else TEXT, ic_name, 'retirement age goal'),
        Fact('Retirement target', form.get('retire_target'), TEXT, ic_name,
             'how much do you think you need',
             note='Client says this was arrived at by: %s'
                  % (form.get('retire_basis') or 'not stated')),
        Fact('Saved last year', form.get('saved_last_year'), TEXT, ic_name),
        Fact('Investable assets', held.get('by_kind', {}).get('Investments'),
             MONEY, 'investment statements', 'latest balance per account',
             needed='Investment and retirement statements, read',
             why='Half the retirement question is what is already there'),
        Fact('CPA rating', form.get('cpa_rating'), TEXT, ic_name,
             'how would you rate your CPA'),
        Fact('Tax surprises', form.get('tax_surprise'), TEXT, ic_name,
             'owe or being refunded'),
        Fact('Liquid if they walked away today', form.get('saved_liquid'),
             TEXT, ic_name, 'if you walked away today'),
        Fact('Email', form.get('email'), TEXT, ic_name),
    ]

    # Practice side first and complete, then the person. Personal debt sat
    # between the practice blocks and the personal ones, which split the
    # household across the sheet.
    blocks = [Block('Practice', practice), Block('Overhead', overhead),
              Block('Practice debt', practice_debt),
              Block('Personal', personal),
              Block('Personal debt', personal_debt)]

    # --------------------------------------------------- the year-by-year
    # The firm's own metric list, in the firm's own order. Anything derived is
    # computed here from figures that were read, never read directly, so the
    # ratio and its parts can never disagree.
    roles = _prod.load_roles(folder)

    def pv(y, *keys):
        """A figure from the Practice Analysis for one year."""
        return _first(prod.get(y, {}).get('values', {}), *keys)

    def providers(y):
        """{code: production} for a year, reconciled against the report."""
        rec = prod.get(y, {})
        settled = _prod.reconcile_providers(
            rec.get('providers') or {}, rec.get('activity') or {},
            (rec.get('values') or {}).get('total_charges_prov'))
        return settled['providers'] if settled.get('reconciles') else {}

    def by_role(y, role):
        tot = sum(v for c, v in providers(y).items()
                  if (roles.get(c) or {}).get('role') == role)
        return round(tot, 2) if tot else None

    def doctors():
        """The producing doctors, owner first, in a stable order."""
        out = [(c, r) for c, r in roles.items()
               if r.get('role') in ('owner', 'associate')]
        out.sort(key=lambda cr: (cr[1].get('role') != 'owner',
                                 cr[1].get('name') or cr[0]))
        return out

    def ratio(num, den, pct=True):
        if not num or not den:
            return None
        v = num / den
        return round(v, 5) if pct else round(v, 2)

    def series_for(getter, fmt):
        return {y: getter(y) for y in years}

    gross = {y: pv(y, 'charges_uninsured', 'charges_insured') for y in years}
    adjust = {y: pv(y, 'adjustments_add') for y in years}
    netprod = {y: pv(y, 'total_charges') for y in years}
    grosscol = {y: (abs(pv(y, 'patient_payments') or 0)
                    + (pv(y, 'insurance_payments') or 0)) or None
                for y in years}
    coladj = {y: pv(y, 'adjustments_less') for y in years}
    netcol = {y: pv(y, 'total_credits') for y in years}
    pats = {y: counts.get(y, {}).get('total_patients') for y in years}
    nps = {y: counts.get(y, {}).get('new_patients') for y in years}
    days = {y: counts.get(y, {}).get('doctor_days') for y in years}
    hyg = {y: by_role(y, 'hygiene')
           or ((prod.get(y) or {}).get('by_role') or {}).get('hygiene')
           for y in years}

    series = [
        ('gross production', gross, MONEY),
        ('production adjustments', adjust, MONEY),
        ('net production', netprod, MONEY),
        ('gross collections', grosscol, MONEY),
        ('collection adjustments', coladj, MONEY),
        ('net collections', netcol, MONEY),
        ('patient visits', pats, NUM),
        ('new patients', nps, NUM),
        ('days worked, all doctors', days, NUM),
    ]

    docs_list = doctors()
    for code, role in docs_list:
        name = (role.get('name') or code).replace('Dr. ', '').split()[-1]
        series.append(('days worked, %s' % name,
                       {y: (_pf.gather(folder).get('doctor_days', {})
                            .get(name, {}) or {}).get(y) for y in years}, NUM))
    for code, role in docs_list:
        name = (role.get('name') or code).replace('Dr. ', '').split()[-1]
        series.append(('production, %s' % name,
                       {y: providers(y).get(code) for y in years}, MONEY))
    series.append(('hygiene production', hyg, MONEY))

    for code, role in docs_list:
        name = (role.get('name') or code).replace('Dr. ', '').split()[-1]
        series.append(('%s %% of production' % name,
                       {y: ratio(providers(y).get(code), gross.get(y))
                        for y in years}, PCT))
    series += [
        ('hygiene % of production',
         {y: ratio(hyg.get(y), gross.get(y)) for y in years}, PCT),
        ('gross production / patient',
         {y: ratio(gross.get(y), pats.get(y), pct=False) for y in years}, MONEY2),
        ('net production / patient',
         {y: ratio(netprod.get(y), pats.get(y), pct=False) for y in years}, MONEY2),
        ('production adjustment %',
         {y: ratio(adjust.get(y), gross.get(y)) for y in years}, PCT),
        ('collection %',
         {y: ratio(netcol.get(y), netprod.get(y)) for y in years}, PCT),
        ('new patients % of total',
         {y: ratio(nps.get(y), pats.get(y)) for y in years}, PCT),
        ('collection adjustment %',
         {y: ratio(coladj.get(y), grosscol.get(y)) for y in years}, PCT),
        ('patients / doctor day',
         {y: ratio(pats.get(y), days.get(y), pct=False) for y in years}, NUM2),
    ]
    for code, role in docs_list:
        name = (role.get('name') or code).replace('Dr. ', '').split()[-1]
        series.append(('production / day, %s' % name,
                       {y: ratio(providers(y).get(code), days.get(y),
                                 pct=False) for y in years}, MONEY2))
    series += [
        ('gross production / doctor day',
         {y: ratio(gross.get(y), days.get(y), pct=False) for y in years}, MONEY2),
        ('revenue (P&L)',
         {y: pnl.get(y, {}).get('income') for y in years}, MONEY),
        ('doctor income (P&L)',
         {y: pnl.get(y, {}).get('doctor_salary') for y in years}, MONEY),
        ('depreciation / amortisation',
         {y: pnl.get(y, {}).get('depreciation_amort') for y in years}, MONEY),
        ('expenses (P&L)',
         {y: pnl.get(y, {}).get('overhead') for y in years}, MONEY),
        ('overhead, P&L basis',
         {y: _pct(pnl.get(y, {}).get('overhead_pct')) for y in years}, PCT),
        ('overhead, tax basis',
         {y: _pct(tax.get(y, {}).get('overhead_pct')) for y in years}, PCT),
        ('gross receipts (tax return)',
         {y: tax.get(y, {}).get('income_base') for y in years}, MONEY),
        ('officer compensation (tax return)',
         {y: tax.get(y, {}).get('officer_comp') for y in years}, MONEY),
    ]
    # ------------------------------------------------- pain points, last
    # Where the lead advisor puts them: the dentist's own words, then the consult
    # themes each with the figure behind it, then fee range and timeline.
    try:
        import painpoints as _pp
        rows = _pp.themes(form, src, p, t, latest, series,
                          _compose.fee_study(folder),
                          _compose.practice_debt(list(debts.get('practice') or ()) + building,
                                                 debts.get('unread') or ()),
                          folder)
        blocks.append(Block('Pain points and consult themes', [
            Fact(theme, evidence, TEXT, source, 'pain point',
                 needed=('Advisor' if source == 'Advisor'
                         else 'Add from the initial call'))
            for theme, evidence, source in rows]))
    except Exception as exc:
        blocks.append(Block('Pain points and consult themes', [
            Fact('Pain points', None, TEXT, None,
                 needed='Could not be drafted (%s)' % exc)]))

    # Rows read from the documents for the lead advisor's extra lines
    # (doc_readings.py "extra"): year-end bank balances, distributions,
    # professional fees.
    for r in (got or {}).get('extra') or ():

        # Bank balances, distributions and fees sit with the overhead (the
        # lead advisor reads them beside the P&L), not in the metric list.
        overhead_extra.append((r['label'], dict(r['by_year']), bool(r.get('balance')),
                               r.get('ytd_months'), r.get('note'), r.get('basis') or 'pnl'))
        if r.get('balance'):
            balance_rows.add(r['label'])
        if r.get('ytd_months'):
            extra_months[r['label']] = r['ytd_months']
        if r.get('note'):
            extra_notes[r['label']] = {'note': r['note']}

    bundle = Bundle(client, blocks, years, series, folder)
    # A count that runs longer than the money (new patients to Oct 30 against
    # a P&L to Sep 30) annualizes on its own months.
    _cm = {'total_patients': 'patient visits', 'new_patients': 'new patients'}
    bundle.series_months = {_cm[k]: v for k, v in count_months.items() if k in _cm}
    bundle.series_months.update(extra_months)
    bundle.balance_rows = balance_rows
    bundle.overhead_extra = overhead_extra
    bundle.cash_light = (got or {}).get('cash_light') or []
    bundle.series_notes.update(extra_notes)
    bundle.months_by_year = {y: (pnl.get(y, {}) or {}).get('months') or 0
                             for y in years}
    # The newest year when it is a year to date: how many months the
    # production covers (the P&L's months when the production report does not
    # say), so the by year sheet can show it annualized beside the YTD.
    bundle.ytd = None
    if years:
        y = years[-1]
        m = (prod.get(y) or {}).get('months') or \
            (pnl.get(y) or {}).get('months') or 0
        if 0 < m < 12:
            bundle.ytd = {'year': y, 'months': m}

    # Overhead side by side: P&L against P&L, return against return, each
    # year in its own column. The two bases differ by design (what the
    # bookkeeper books versus what the preparer deducts), so a trend is only
    # meaningful within one basis.
    oh_years = [y for y in sorted(set(pnl) | set(tax)) if y in years] or sorted(set(pnl) | set(tax))[-3:]
    bundle.overhead_by_year = {
        y: {'pnl_income': (pnl.get(y) or {}).get('income'),
            'pnl_other': (pnl.get(y) or {}).get('other_income'),
            'pnl_base': (pnl.get(y) or {}).get('income_base'),
            'pnl_expenses': ((pnl.get(y) or {}).get('expenses') or 0)
            + ((pnl.get(y) or {}).get('other_expenses') or 0)
            if pnl.get(y) else None,
            'pnl_dr': (pnl.get(y) or {}).get('doctor_salary'),
            'pnl_da': (pnl.get(y) or {}).get('depreciation_amort'),
            'pnl_oh': (pnl.get(y) or {}).get('overhead'),
            'pnl_pct': (pnl.get(y) or {}).get('overhead_pct'),
            'pnl_months': (pnl.get(y) or {}).get('months'),
            'pnl_source': (pnl.get(y) or {}).get('source')
            or ('P&L %s' % y if pnl.get(y) else None),
            'tax_base': (tax.get(y) or {}).get('income_base'),
            'tax_deductions': (tax.get(y) or {}).get('total_deductions'),
            'tax_officer': (tax.get(y) or {}).get('officer_comp'),
            'tax_da': (tax.get(y) or {}).get('depreciation_amort'),
            'tax_oh': (tax.get(y) or {}).get('overhead'),
            'tax_pct': (tax.get(y) or {}).get('overhead_pct'),
            'tax_source': (tax.get(y) or {}).get('source')}
        for y in oh_years}
    return attach_notes(bundle, folder)


def _providers_for(prod, year):
    """{code: production} for one year, reconciled, or empty."""
    rec = prod.get(year, {})
    settled = _prod.reconcile_providers(
        rec.get('providers') or {}, rec.get('activity') or {},
        (rec.get('values') or {}).get('total_charges_prov'))
    return settled['providers'] if settled.get('reconciles') else {}


def _fmt(v):
    return '{:,.0f}'.format(v) if isinstance(v, (int, float)) else str(v)


def _first(values, *keys):
    got = [values.get(k) for k in keys if values.get(k) is not None]
    return round(sum(got), 2) if got else None


def main():
    ap = argparse.ArgumentParser(description='Every fact, with its source')
    ap.add_argument('folder')
    ap.add_argument('--client', default=None)
    a = ap.parse_args()
    b = gather(a.folder, a.client)
    for block in b.blocks:
        print('\n%s' % block.title.upper())
        for f in block.facts:
            mark = ' ' if f.value is not None else '!'
            print('  %s %-30s %-18s %s' % (
                mark, f.label[:30],
                ('%s' % f.value)[:18] if f.value is not None else '(needed)',
                (f.source or '')[:34]))
    known = sum(1 for f in b.all_facts() if f.value is not None)
    print('\n%d of %d filled' % (known, len(list(b.all_facts()))))


if __name__ == '__main__':
    main()
