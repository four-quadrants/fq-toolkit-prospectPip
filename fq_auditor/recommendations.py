#!/usr/bin/env python3
"""The recommendations the plan can make, and which ones this client's
documents point to.

    python3 recommendations.py "<client folder>"

THE LIST
Every row on the "Where the money comes from" slide of eight of the lead
advisor's consult decks (Farag, Bobby and Cedrick McDonald, Meier, Rebol,
Spaulding, Willis, Wright; Oyler's redesign). The same twenty or so
recommendations recur; what changes from client to client is which ones
apply and the figures. Each entry below says when the documents point to
it, what it is worth a year if that can be worked out, and how much of it
he usually invests (his decks: one-time balances about half, a practice
lever a small share stepping up each year, a new 401(k) all of it).

ON THE REVIEW PAGE
All of them are listed as a checklist. The ones the documents point to are
ticked, with the figure and the reason; the rest are there to tick if the
lead advisor wants them, with the amount for him to fill in. He can add his
own as well. What he leaves ticked becomes the savings slide and the
savings schedule the projections use (the deck entry's "gains_table").
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ONCE_SHARE = 0.5
ACCEL_SHARE = 0.75     # Rebol: $41,100 freed, $30,000 invested
REFI_SHARE = 0.25      # Oyler: $96,000 freed, $24,000 invested
TERM_SHARE = 0.4       # Farag $3,000 of $7,400; Cedrick $6,000 of $7,200
REFI_RATE_WORTH_IT = 0.06

# key, label, year, kind (base, once, cash, practice, refi, plan)
CATALOG = [
    ('current', 'Current savings', 1, 'base'),
    ('practice_surplus', 'Practice bank surplus balance **', 1, 'once'),
    ('personal_surplus', 'Personal bank surplus balance **', 1, 'once'),
    ('llc_surplus', 'LLC / other entity bank surplus balance **', 1, 'once'),
    ('pay_structure', 'New payroll & distribution structure', 1, 'cash'),
    ('stop_acceleration', 'Stop personal & LLC debt acceleration', 1, 'cash'),
    ('refinance', 'Practice debt refinance', 2, 'refi'),
    ('overhead', '−3% overhead', 1, 'practice'),
    ('fees', 'Fee increase', 1, 'practice'),
    ('adjustment', 'Lower production adjustment %', 1, 'practice'),
    ('collections', 'Improved collection %', 2, 'practice'),
    ('new_patients', 'New patient % back up', 2, 'practice'),
    ('hygiene', 'More hygiene days / higher hygiene share', 2, 'practice'),
    ('per_day', 'More patients or production per day', 2, 'practice'),
    ('new_401k', 'New 401(k) plan, max the 401(k)', 2, 'plan'),
    ('life_term', 'Replace permanent life insurance with term', 2, 'cash'),
    ('cash_values', 'Invest the cash values of life policies or annuities **', 2, 'once'),
    ('tax_management', 'Better tax management', 2, 'cash'),
    ('sell_property', 'Sell a building or property **', 2, 'once'),
    ('loan_dropoff', 'Loan paid off, payment freed', 2, 'cash'),
    ('marketing_ends', 'A marketing or other contract ends', 2, 'cash'),
    ('five_k_rule', '$5,000 rule', 1, 'cash'),
]
LABEL = {k: l for k, l, _y, _k in CATALOG}


def _r(v, step=100):
    return int(round((v or 0) / step)) * step if v else None


def _invest(kind, gain, share=None):
    if gain is None:
        return [None, None, None]
    import plan as _plan
    if share is not None:
        x = _plan._round(gain * share)
        return [x, x, x]
    return [_plan.invested({'kind': kind, 'gain': gain}, i) for i in range(3)]


def acceleration(folder):
    """Loans paid above their schedule, from the bank statements: the debt
    list's own payment against what the statements show going out to the
    same account. [(label, scheduled, paid)]."""
    try:
        import debt as _debt
        import cashflow as _cf
        rows = _debt.gather(folder).get('personal') or []
        paid = _cf._liabilities(folder)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for r in rows:
        l4 = str(r.get('account_last4') or '')[-4:]
        if not l4 or not r.get('payment'):
            continue
        for payee, monthly, kind in paid:
            if kind == 'Liability' and l4 in re.sub(r'\D', ' ', payee or '').split() or \
                    (kind == 'Liability' and payee and payee.endswith(l4)):
                if monthly - r['payment'] > 25:
                    out.append(('%s (%s x%s)' % (r.get('what') or 'Loan',
                                                 r.get('creditor') or '', l4),
                                r['payment'], monthly))
                break
    return out


def propose(folder, D=None):
    """[{key, label, year, kind, suggested, gain, invested, basis}] for the
    whole catalog, the suggested ones first."""
    import deck_template as _dt
    import plan as _plan
    D = D or _dt.figures(folder, None)
    g = {x['key']: x for x in (D.get('gains_proposed') or [])}
    lev = D.get('levers') or {}
    out = {}

    years = {k: y for k, _l2, y, _k in CATALOG}
    kinds = {k: kk for k, _l2, _y, kk in CATALOG}

    def put(key, suggested, gain=None, basis='', invested=None, label=None):
        year, kind = years[key], kinds[key]
        inv = list(invested or _invest(kind, gain))
        if year == 2 and inv:
            # A year-two recommendation saves nothing in year one.
            inv = [0] + inv[:2]
        out[key] = {'key': key, 'label': label or LABEL[key], 'year': year,
                    'kind': kind, 'suggested': bool(suggested),
                    'gain': _r(gain), 'basis': basis, 'invested': inv}

    if 'current' in g:
        put('current', True, g['current']['gain'], g['current']['basis'],
            label=g['current']['label'])
    for k in ('practice_surplus', 'personal_surplus'):
        if k in g:
            put(k, True, g[k]['gain'], g[k]['basis'])
    inc = _dt.income_structure(D)
    if inc and inc['gain'] > 0:
        put('pay_structure', True, inc['gain'] * 12,
            'W-2 from %s to %s a month and distributions set so take-home is '
            'unchanged: the practice keeps %s a month more.'
            % ('${:,.0f}'.format(inc['w2']), '${:,.0f}'.format(inc['p_w2']),
               '${:,.0f}'.format(inc['gain'])), invested=[0, 0, 0])
    acc = acceleration(folder)
    if acc:
        extra = sum(p - s for _l, s, p in acc) * 12
        put('stop_acceleration', True, extra,
            'Paid above schedule on the bank statements: ' + '; '.join(
                '%s %s/mo against %s' % (l, '${:,.0f}'.format(p), '${:,.0f}'.format(s))
                for l, s, p in acc) + '.',
            invested=_invest('cash', extra, ACCEL_SHARE))
    rf = _plan.refinance(D.get('practice_debts'))
    worth = [r for r in rf.get('candidates') or []
             if (r.get('rate') or 0) >= REFI_RATE_WORTH_IT or r.get('rate') is None]
    if rf.get('freed'):
        put('refinance', bool(worth), rf['freed'] * 12,
            ('%d practice loans at 6%% or more, or with no stated rate; '
             'consolidated at %.0f%% over %d years they free %s a month.'
             % (len(worth), _plan.REFI_RATE * 100, _plan.REFI_YEARS,
                '${:,.0f}'.format(rf['freed'])))
            if worth else 'The practice loans are mostly cheap; a refinance '
                          'would free %s a month but is not proposed.'
                          % '${:,.0f}'.format(rf['freed']),
            invested=_invest('refi', rf['freed'] * 12, REFI_SHARE))
    if 'overhead' in g:
        put('overhead', True, g['overhead']['gain'], g['overhead']['basis'])
    for key in ('fees', 'adjustment', 'collections', 'new_patients'):
        v = (lev.get(key) or {}).get('value')
        if v:
            put(key, v > 5000, v, (lev[key] or {}).get('basis') or '')
    for key in ('hygiene', 'pull_through'):
        v = (lev.get(key) or {}).get('value')
        if v:
            put('hygiene', v > 5000, v, (lev[key] or {}).get('basis') or '')
            break
    # Retirement plan: a SIMPLE IRA or no 401(k) at all points to a new 401(k)
    labels = ' '.join(l for l, _a in D.get('start_parts') or [])
    if re.search(r'simple', labels, re.I) or not re.search(r'401', labels):
        put('new_401k', True, None,
            'The household saves through %s; a 401(k) allows far more, '
            'pre-tax.' % ('SIMPLE IRAs' if re.search(r'simple', labels, re.I)
                          else 'no 401(k)'))
    # Life insurance and annuities with cash value
    docs = ' '.join(os.listdir(os.path.join(folder, 'Original_sourcedocs'))) \
        if os.path.isdir(os.path.join(folder, 'Original_sourcedocs')) else ''
    if re.search(r'universal|whole life|\bvul\b|augustar|cash value|annuity|'
                 r'life ins|life policy', docs, re.I):
        put('life_term', True, None, 'Permanent life or annuity statements are '
                                     'on file; compare the premium with term.')
        cv = []
        try:
            import inputs as _inputs
            for key in ('qualified_accounts', 'nonqualified_accounts'):
                for row in _inputs.value(folder, key) or []:
                    if re.search(r'cash value|annuit|life', row.get('label') or '', re.I):
                        cv.append((row['label'], row.get('value') or 0))
        except Exception:  # noqa: BLE001
            pass
        total = sum(v for _l, v in cv)
        put('cash_values', True, total or None,
            ('Cash value on file: ' + ', '.join('%s %s' % (l, '${:,.0f}'.format(v))
                                                for l, v in cv) + '.') if cv else
            'Cash value on those policies could be invested once the policies '
            'are replaced.',
            invested=_invest('once', total, 0.6) if total else None)
    # Loans ending within two years
    import datetime
    soon = [r for r in (D.get('practice_debts') or [])
            if r.get('maturity') and r.get('payment') and
            0 <= r['maturity'] - datetime.date.today().year <= 1
            # paid off, not a balloon to refinance (HomeTrust: $311k left)
            and (r.get('balance') or 0) <= 24 * r['payment']]
    if soon:
        put('loan_dropoff', True, sum(r['payment'] for r in soon) * 12,
            'Ending within a year: ' + ', '.join(
                '%s %s/mo' % (r.get('creditor'), '${:,.0f}'.format(r['payment']))
                for r in soon) + '.', invested=[0, 0, 0])
    put('five_k_rule', True, None, 'Every consult: the firm advises on any '
                                   'decision over $5,000.', invested=[None, None, None])
    for key, _l, _y, _k in CATALOG:
        if key not in out:
            put(key, False, None, '')
    rows = list(out.values())
    order = [k for k, _l, _y, _k in CATALOG]
    rows.sort(key=lambda r: (not r['suggested'], order.index(r['key'])))
    return rows


def to_gains_table(chosen):
    """The deck entry's gains_table from the rows left ticked."""
    out = []
    for r in chosen:
        if r.get('gain') in (None, '') and not any(r.get('invested') or []):
            continue
        out.append({'key': r['key'], 'label': r['label'], 'gain': r.get('gain') or 0,
                    'kind': 'once' if r.get('kind') == 'once' else
                    ('base' if r['key'] == 'current' else
                     'practice' if r.get('kind') == 'practice' else 'cash'),
                    'invested': [x or 0 for x in (r.get('invested') or [0, 0, 0])],
                    'year': r.get('year') or 1})
    return out


def main():
    ap = argparse.ArgumentParser(description='Recommendations for one client')
    ap.add_argument('folder')
    a = ap.parse_args()
    for r in propose(a.folder):
        print('%s %-55s %10s  %s' % ('[x]' if r['suggested'] else '[ ]', r['label'][:55],
                                     '{:,.0f}'.format(r['gain']) if r['gain'] else '',
                                     r['basis'][:90]))


if __name__ == '__main__':
    main()
