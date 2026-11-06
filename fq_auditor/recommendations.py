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
import store as _store  # noqa: E402
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
    ('s_corp', 'Incorporate the practice (S corporation election)', 1, 'cash'),
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
    ('growth_trend', 'Current growth trend continues', 1, 'practice'),
    ('marketing_ends', 'A marketing campaign or contract ends (direct mail, consultant)', 1, 'cash'),
    ('associate_change', 'Associate or doctor days change', 2, 'practice'),
    ('remove_pmi', 'Remove PMI on the home mortgage', 1, 'cash'),
    ('profit_share', 'New or redirected profit share / cash balance plan', 2, 'plan'),
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


def propose(folder, D=None, use_claude=True):
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
    f = D.get('income_facts') or {}
    if not f.get('w2') and not (D.get('facts') or {}).get('Doctor wages'):
        put('s_corp', True, None,
            'The practice files on Schedule C: no W-2, self-employment tax on '
            'every dollar of profit, and tax estimates that swing. An S '
            'corporation allows a W-2 and distributions (his Spaulding deck).',
            invested=[0, 0, 0])
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
        n = len(rf.get('candidates') or [])
        put('refinance', bool(worth) or rf['freed'] >= 1000, rf['freed'] * 12,
            '%d practice loan%s that are costly or on short schedules (%s a '
            'month today); stretched over %d years at %.0f%% they free about '
            '%s a month.' % (n, '' if n == 1 else 's',
                             '${:,.0f}'.format(rf['payment_now']), _plan.REFI_YEARS,
                             _plan.REFI_RATE * 100, '${:,.0f}'.format(rf['freed'])),
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
    # Claude's pass over the library: it fills in what the rules could not
    # size, and adds what the rules do not know to look for.
    if use_claude:
        for c in _saved_candidates(folder):
            key = re.sub(r'[^a-z0-9_]', '_', str(c['key']).lower())
            have = out.get(key)
            if have and have['suggested'] and have['gain'] is not None:
                continue
            gain = c.get('gain') if isinstance(c.get('gain'), (int, float)) else None
            inv = [c.get('invested_year1') or 0, c.get('invested_year2') or 0,
                   c.get('invested_year2') or 0]
            year = 2 if str(c.get('year')) == '2' else 1
            if key not in years:
                years[key] = year
                kinds[key] = 'cash'
                LABEL[key] = c.get('label') or key
            put(key, bool(c.get('suggested')), gain,
                ((have or {}).get('basis') + ' ' if have and have.get('basis') else '') +
                'Claude: ' + (c.get('basis') or ''),
                invested=inv if any(inv) else None,
                label=c.get('label') if key not in dict((k, 1) for k, *_r in CATALOG) else None)
    for key, _l, _y, _k in CATALOG:
        if key not in out:
            put(key, False, None, '')
    rows = list(out.values())
    order = [k for k, _l, _y, _k in CATALOG]
    rows.sort(key=lambda r: (not r['suggested'],
                             order.index(r['key']) if r['key'] in order else len(order)))
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


# ---- Claude reads the library against the client ---------------------------

LIBRARY = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'recommendations_library.md')
SAVED = 'recommendations_claude.json'

PROMPT = """You are helping a Four Quadrants advisor prepare a consult for a dental
practice owner. Below is the firm's library of recommendations (what each is,
when it applies, the signs in the documents, how it is sized), then what the
toolkit has found for this client, then what its own rules already propose.

Go through the WHOLE library. For each recommendation that this client's
facts point to, and that the rules did not already size, say so. Also
propose anything the library does not have if the facts clearly call for it
(give it a new key).

LIBRARY
{library}

THIS CLIENT
{facts}

ALREADY PROPOSED BY THE RULES (key: figure a year, or null)
{rules}

Return JSON only:
{{"candidates": [{{"key": "growth_trend", "label": "...",
  "suggested": true, "year": 1 or 2,
  "gain": number a year or null if it cannot be sized from these facts,
  "invested_year1": number or null, "invested_year2": number or null,
  "basis": "one or two sentences: which facts point to it and how it was sized"}}]}}
Only use figures that appear in THIS CLIENT, or simple arithmetic on them
(say the arithmetic in basis). Leave a figure null rather than guess."""


def _fact_pack(folder, D):
    import json as _json
    pack = {'facts': D.get('facts'), 'concerns': (D.get('adv') or {}).get('concerns'),
            'levers': {k: {'value': v.get('value'), 'basis': v.get('basis')}
                       for k, v in (D.get('levers') or {}).items()},
            'lever_inputs': D.get('lever_inputs'),
            'pay_from_returns': D.get('income_facts'),
            'practice_debts': D.get('practice_debts'),
            'start_portfolio': D.get('start_parts'),
            'current_savings': D.get('current_savings'),
            'household_spend_a_year': D.get('spend')}
    try:
        import deck as _deck
        pack['production_by_year'] = _deck.annual_pi(folder)
    except Exception:  # noqa: BLE001
        pass
    try:
        import inputs as _inputs
        pack['accounts'] = [_inputs.value(folder, 'qualified_accounts'),
                            _inputs.value(folder, 'nonqualified_accounts')]
    except Exception:  # noqa: BLE001
        pass
    try:
        import debt as _debt
        pack['personal_debts'] = _debt.gather(folder).get('personal')
    except Exception:  # noqa: BLE001
        pass
    try:
        import summary as _summary
        pack['pnl'] = _summary.gather(folder)
    except Exception:  # noqa: BLE001
        pass
    text = _json.dumps(pack, default=str)
    return text[:60000]


def claude_candidates(folder, D=None, log=print):
    """Claude's pass over the library for this client, saved to _Audit and
    reused until the client's facts change. [] when Claude is not available."""
    import json as _json
    import hashlib
    saved_path = _store.json_path(folder, SAVED)
    if D is None:
        import deck_template as _dt
        D = _dt.figures(folder, None)
    rules = {r['key']: r['gain'] for r in propose(folder, D, use_claude=False)
             if r['suggested']}
    facts = _fact_pack(folder, D)
    library = open(LIBRARY).read() if os.path.exists(LIBRARY) else ''
    stamp = hashlib.sha1((facts + library + _json.dumps(rules)).encode()).hexdigest()
    try:
        prev = _json.load(open(saved_path))
        if prev.get('stamp') == stamp:
            return prev.get('candidates') or []
    except (OSError, ValueError):
        prev = {}
    try:
        import ask_claude
        got = ask_claude.ask_json(PROMPT.format(library=library, facts=facts,
                                                rules=_json.dumps(rules)),
                                  cache_dir=os.path.join(folder, '.fq_cache', 'recs'),
                                  timeout=600, allow=())
    except Exception as exc:  # noqa: BLE001
        log('  recommendations: Claude pass skipped (%s)' % exc)
        return prev.get('candidates') or []
    cands = [c for c in (got or {}).get('candidates') or [] if c.get('key')]
    try:
        with open(saved_path, 'w') as fh:
            _json.dump({'stamp': stamp, 'candidates': cands}, fh, indent=1)
    except OSError:
        pass
    log('  recommendations: Claude proposed %d from the library' % len(cands))
    return cands


def _saved_candidates(folder):
    import json as _json
    try:
        return _json.load(open(_store.json_path(folder, SAVED))).get('candidates') or []
    except (OSError, ValueError):
        return []


# ---- the whole library, for the review page's "Add from the library" -------

GROUPS = [
    ('Cash flow process', ('ideal_bank_balance', 'line_of_credit', 'spending_freeze',
                           'five_k_rule', 'no_new_debt', 'consumer_debt')),
    ('Savings and retirement', ('current', 'personal_surplus', 'practice_surplus', 'llc_surplus',
                                'new_401k', 'profit_share', 'spouse_payroll', 'hsa',
                                'tax_diversification', 'sep_ira', 'ira_interim',
                                'stop_profit_share', 'roth_to_traditional', 'college_529')),
    ('Investments', ('move_investments', 'consolidate_accounts', 'replace_illiquid')),
    ('Tax and entity', ('pay_structure', 's_corp', 'tax_management', 'rent_strategy',
                        'monthly_accounting', 'amend_returns', 'quarterly_estimates',
                        'missed_deductions', 'ptet', 'shareholder_loan', 'entity_structure',
                        'worker_classification', 'route_outside_income', 'rsu_tax_planning')),
    ('Debt', ('stop_acceleration', 'refinance', 'loan_dropoff', 'remove_pmi')),
    ('Practice production', ('overhead', 'fees', 'adjustment', 'collections', 'new_patients',
                             'hygiene', 'per_day', 'growth_trend', 'marketing_ends',
                             'associate_change')),
    ('Practice model and transition', ('practice_model', 'transition_plan')),
    ('Insurance and property', ('life_term', 'cash_values', 'sell_property')),
]


def library_entries():
    """Every recommendation in the library, grouped, for the picker:
    [{key, keys, label, group, when, signs, size, seen}]. One ## heading per
    entry; the keys are the bracketed words in it."""
    try:
        text = open(LIBRARY).read()
    except OSError:
        return []
    out = []
    for block in re.split(r'\n(?=## )', text):
        if not block.startswith('## '):
            continue
        head, _, body = block.partition('\n')
        keys = re.findall(r'\[([a-z0-9_]+)\]', head)
        label = re.sub(r'\s*\[[a-z0-9_]+\]', '', head[3:]).strip()
        label = re.sub(r'\s+and\s*$', '', label)
        fields = {}
        cur = None
        for line in body.split('\n'):
            m = re.match(r'-\s*(When|Signs|Size|Seen):\s*(.*)', line)
            if m:
                cur = m.group(1).lower()
                fields[cur] = m.group(2).strip()
            elif cur and line.strip() and not line.startswith('#'):
                fields[cur] += ' ' + line.strip()
        group = next((g for g, ks in GROUPS if set(keys) & set(ks)), 'Added on past consults')
        out.append({'key': keys[0] if keys else re.sub(r'[^a-z0-9]+', '_', label.lower())[:40],
                    'keys': keys, 'label': label, 'group': group,
                    'when': fields.get('when', ''), 'signs': fields.get('signs', ''),
                    'size': fields.get('size', ''), 'seen': fields.get('seen', '')})
    order = [g for g, _ in GROUPS] + ['Added on past consults']
    out.sort(key=lambda e: order.index(e['group']))
    return out
