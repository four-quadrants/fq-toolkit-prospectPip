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

MONEY = '$#,##0;($#,##0);-'
PCT = '0.0%'
NUM = '#,##0'
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


class Bundle(object):
    def __init__(self, client, blocks, years, series):
        self.client, self.blocks = client, blocks
        self.years, self.series = years, series

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
    path = os.path.join(folder, '_Audit', 'notes.json')
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
        fact.flags = list(got.get('flags') or ())[:2]
        fact.questions = list(got.get('questions') or ())[:2]
    return bundle


def gather(folder, client=None):
    client = client or os.path.basename(folder.rstrip('/'))

    form = {}
    src = _ic.find_form(folder) or _ic.find_form(os.path.dirname(folder.rstrip('/')))
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

    years = sorted(set(pnl) | set(prod) | set(counts))[-3:]
    full = [y for y in years if (pnl.get(y, {}).get('months') or 0) >= 12]
    latest = full[-1] if full else (years[-1] if years else None)
    p = pnl.get(latest, {})
    t = tax.get(latest, {})

    # ------------------------------------------------------------- practice
    practice = [
        Fact('Office location', form.get('building') and
             'Owns the building' or None, TEXT, ic_name, 'rent or own',
             needed='Ask on the call', why='Lease terms drive the overhead'),
        Fact('Owned since', form.get('years_owned') and
             '%s years' % form['years_owned'], TEXT, ic_name, 'years owned'),
        Fact('Collections, stated', _ic.money(form.get('collections_last')),
             MONEY, ic_name, 'annual collections last year'),
        Fact('Collections, documented', p.get('income'), MONEY,
             'P&L %s' % latest if p else None, 'Total for Income'),
        Fact('Associates', form.get('associate_comp'), TEXT, ic_name,
             'associate compensation'),
        Fact('Chairs', form.get('chairs_total') and
             '%s total (%s op, %s hyg)' % (form.get('chairs_total'),
                                           form.get('chairs_operative'),
                                           form.get('chairs_hygiene')),
             TEXT, ic_name, 'chairs'),
        Fact('In-network', form.get('in_network'), TEXT, ic_name,
             'insurances in network'),
        Fact('Practice management software', form.get('pms'), TEXT, ic_name,
             'practice management software'),
        Fact('Fees off by', None, PCT, None,
             needed='Fee schedule and the NDAS study',
             why='Sizes the single easiest revenue lever'),
    ]

    # ------------------------------------------------------------- overhead
    overhead = [
        Fact('Overhead, client says', _pct(_ic.money(form.get('overhead_stated'))),
             PCT, ic_name, 'approximate overhead percentage'),
        Fact('Overhead, P&L basis', _pct(p.get('overhead_pct')), PCT,
             'P&L %s' % latest if p else None,
             'Expenses + Other Expenses less doctor wages and D&A, '
             'over Income + Other Income'),
        Fact('Overhead, tax basis', _pct(t.get('overhead_pct')), PCT,
             t.get('source'), 'total deductions less officer comp and '
                              'depreciation, over total income'),
        Fact('Basis difference', _pct((p.get('overhead_pct') or 0) -
                                      (t.get('overhead_pct') or 0))
             if (p and t) else None, PCT, 'derived',
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
            bits = []
            if r.get('rate'):
                rate = r['rate'] * 100 if r['rate'] < 1 else r['rate']
                bits.append('%.2f%%' % rate)
            if r.get('payment'):
                bits.append('%s/mo' % _fmt(r['payment']))
            if r.get('description'):
                bits.append(r['description'])
            out.append(Fact(name, r.get('balance'), MONEY, r.get('source'),
                            r.get('as_of') or 'current balance',
                            note='  ·  '.join(bits) or None))
        if rows:
            out.append(Fact('%s total' % side_label,
                            round(sum(r.get('balance') or 0 for r in rows), 2),
                            MONEY, 'derived', 'sum of the rows above'))
            out.append(Fact('%s debt service' % side_label,
                            round(sum(r.get('payment') or 0 for r in rows), 2),
                            MONEY, 'derived', 'sum of monthly payments'))
        return out

    practice_debt = obligations(debts.get('practice') or (), 'Practice')
    personal_debt = obligations(debts.get('personal') or (), 'Personal')
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
        Fact('Dependents', _ic.money(form.get('dependents')), NUM, ic_name),
        Fact('Take-home, stated', _ic.money(form.get('take_home')), MONEY,
             ic_name, 'annual take-home pay'),
        Fact('Retirement age goal', _ic.money(form.get('retire_age')), NUM,
             ic_name, 'retirement age goal'),
        Fact('Retirement target', form.get('retire_target'), TEXT, ic_name,
             'how much do you think you need',
             note='Client says this was arrived at by: %s'
                  % (form.get('retire_basis') or 'not stated')),
        Fact('Saved last year', form.get('saved_last_year'), TEXT, ic_name),
        Fact('Investable assets', None, MONEY, None,
             needed='Investment and retirement statements, read',
             why='Half the retirement question is what is already there'),
        Fact('Personal bank balances', None, MONEY, None,
             needed='Personal bank statements; none have arrived',
             why='The personal cashflow cannot start without them'),
        Fact('CPA rating', form.get('cpa_rating'), TEXT, ic_name,
             'how would you rate your CPA'),
    ]

    blocks = [Block('Practice', practice), Block('Overhead', overhead),
              Block('Practice debt', practice_debt),
              Block('Personal debt', personal_debt),
              Block('Personal', personal)]

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
    hyg = {y: by_role(y, 'hygiene') for y in years}

    series = [
        ('gross production', gross, MONEY),
        ('production adjustments', adjust, MONEY),
        ('net production', netprod, MONEY),
        ('gross collections', grosscol, MONEY),
        ('collection adjustments', coladj, MONEY),
        ('net collections', netcol, MONEY),
        ('patients (procedures)', pats, NUM),
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
         {y: ratio(gross.get(y), pats.get(y), pct=False) for y in years}, MONEY),
        ('net production / patient',
         {y: ratio(netprod.get(y), pats.get(y), pct=False) for y in years}, MONEY),
        ('production adjustment %',
         {y: ratio(adjust.get(y), gross.get(y)) for y in years}, PCT),
        ('collection %',
         {y: ratio(netcol.get(y), netprod.get(y)) for y in years}, PCT),
        ('new patients % of total',
         {y: ratio(nps.get(y), pats.get(y)) for y in years}, PCT),
        ('collection adjustment %',
         {y: ratio(coladj.get(y), grosscol.get(y)) for y in years}, PCT),
        ('patients / doctor day',
         {y: ratio(pats.get(y), days.get(y), pct=False) for y in years}, NUM),
    ]
    for code, role in docs_list:
        name = (role.get('name') or code).replace('Dr. ', '').split()[-1]
        series.append(('production / day, %s' % name,
                       {y: ratio(providers(y).get(code), days.get(y),
                                 pct=False) for y in years}, MONEY))
    series += [
        ('gross production / doctor day',
         {y: ratio(gross.get(y), days.get(y), pct=False) for y in years}, MONEY),
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
    return attach_notes(Bundle(client, blocks, years, series), folder)


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
