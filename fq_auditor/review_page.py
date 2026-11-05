#!/usr/bin/env python3
"""The lead advisor’s consult review page: what goes onto it, and what comes back.

    python3 review_page.py seed  "<client folder>" --out <dir>
    python3 review_page.py apply "<client folder>" <plan_figures.json>

THE PAGE
A private claude.ai page per client (an artifact with a small database), where
the lead advisor sees the toolkit's proposal for every figure the consult deck uses, the
workings behind them (starting portfolio, sale, savings sources, levers, the
year-by-year savings worksheet), the concerns from the initial notes, and the
follow-up questions. He types his own figure where he disagrees and marks each
question Send, Answered or Strike.

WHY TWO STEPS
The toolkit has no claude.ai login; only Claude can read and write the page's
database. So Claude runs `seed` and loads the JSON it writes into the page,
and after the lead advisor has decided, Claude saves the page's "plan/figures" record to
a file and runs `apply`, which writes his decisions where the toolkit reads
them:
  _Audit/plan_inputs.json, key "deck"   his figures and the concerns, which
                                          the deck and the plan card use
  _Audit/review_decisions.json           his question decisions and wording,
                                          which the follow-up email uses

THE RECORD THAT SAVES
Everything the lead advisor changes lives on the one "plan/figures" record: "decided"
(his figures), "concerns", "qdecisions" and "qtext" (question decision and
wording, by question id). The page writes nothing else, because in the
Claude app's viewer the store hands back read-only objects and the
per-question records never took a write (found 29 Oct, after a morning of it).
"""
import os
import store as _store  # noqa: E402
import re
import sys
import json
HERE = os.path.dirname(os.path.abspath(__file__))
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _num(text):
    """'$599,000' -> 599000.0; '65' -> 65.0; '60%' -> 0.6."""
    if text in (None, ''):
        return None
    t = str(text).strip()
    pct = t.endswith('%')
    m = re.search(r'-?[\d,]*\.?\d+', t.replace('$', ''))
    if not m:
        return None
    v = float(m.group(0).replace(',', ''))
    if t.lower().endswith(('k',)):
        v *= 1000
    if t.lower().endswith(('m', 'mm')):
        v *= 1000000
    return v / 100.0 if pct else v


def apply(folder, plan_json):
    """Write the lead advisor’s decisions from the page into the client folder."""
    import inputs as _inputs
    with open(plan_json) as fh:
        got = json.load(fh)
    rec = got.get('data', got)
    decided = rec.get('decided') or {}

    entry = dict((_inputs.get(folder, 'deck') or {}).get('value') or {})
    changed = []
    schedule = dict((int(y), v) for y, v in (entry.get('savings_schedule') or []))
    for key, raw in decided.items():
        if raw in (None, ''):
            continue
        if key.startswith('save_'):
            schedule[int(key[5:])] = _num(raw)
            changed.append(key)
            continue
        m = re.match(r'ret_(acct|4q)_(\d+)$', key)
        if m:
            try:
                with open(_store.json_path(folder, 'review_accounts.json')) as fh:
                    acct_map = json.load(fh)
            except (OSError, ValueError):
                acct_map = {}
            label = acct_map.get(m.group(2))
            v = _num(raw)
            if label and v is not None:
                v = v * 100 if '%' in str(raw) else v      # stored as a percent
                rets = entry.setdefault('returns', {})
                rets.setdefault(label, {})['return_pct' if m.group(1) == 'acct'
                                           else 'fq_pct'] = v
                changed.append(key)
            continue
        if key == 'consult_date':
            entry['consult_date_text'] = str(raw).strip()
            changed.append(key)
            continue
        if key == 'refinance':
            entry['refinance'] = str(raw).strip().lower()
            changed.append(key)
            continue
        if key.startswith('a_') or key == 'building_value':
            v = _num(raw)
            if v is not None:
                entry[key] = v
                changed.append(key)
            continue
        if key in ('retire_age', 'target_income', 'sale_net', 'sale_net_fq',
                   'start_portfolio',
                   'current_savings', 'ideal_bank_balance', 'target_overhead',
                   'income_w2_proposed', 'income_tax_rate_proposed',
                   'income_w2', 'income_deferral', 'income_total_tax',
                   'income_distributions'):
            v = _num(raw)
            if key in ('target_overhead', 'income_tax_rate_proposed') and v and v > 1:
                v = v / 100.0
            if v is not None:
                entry[key] = int(v) if key == 'retire_age' else v
                changed.append(key)
    if schedule:
        entry['savings_schedule'] = [[y, schedule[y]] for y in sorted(schedule)]
    # The years he typed himself ("Savings in 2030", a 401(k) starting, a
    # profit share later) are kept apart too, so the schedule the
    # recommendations build can be extended by them rather than replace them.
    typed = {int(k[5:]): _num(v) for k, v in decided.items()
             if k.startswith('save_') and v not in (None, '') and _num(v) is not None}
    entry['savings_steps'] = [[y, typed[y]] for y in sorted(typed)]
    if rec.get('concerns'):
        entry['concerns'] = [[c.get('head', ''), c.get('body', '')]
                             for c in rec['concerns'] if c.get('head')]
        changed.append('concerns')
    # The recommendations he left ticked (and any he added) become the
    # savings slide and the savings schedule.
    recs = rec.get('recommendations') or []
    notes = []
    if recs:
        state = rec.get('recs') or {}
        chosen = []
        for r in recs + [dict(c, key=c.get('key') or 'custom_%d' % i, year=c.get('year') or 2)
                         for i, c in enumerate(rec.get('recs_custom') or [])]:
            st = state.get(r['key']) or {}
            on = st.get('on') if 'on' in st else (r.get('suggested') or r['key'].startswith('custom'))
            if not on:
                continue
            gain = _num(st.get('gain')) if st.get('gain') not in (None, '') else r.get('gain')
            inv = list(r.get('invested') or [0, 0, 0]) + [0, 0, 0]
            for i, k in ((0, 'inv1'), (1, 'inv2')):
                if st.get(k) not in (None, ''):
                    inv[i] = _num(st[k])
            if st.get('inv2') not in (None, ''):
                inv[2] = _num(st['inv2'])
            year = str(st.get('year') or r.get('year') or 1)
            if year == 'later':
                # Kept in view (the note says when), out of the schedule
                notes.append('%s: held for later. %s' % (
                    st.get('label') or r.get('label'), st.get('note') or ''))
                continue
            # Moved to a later year: nothing invested before it starts
            start = int(year) - 1
            full = max(inv[:3]) if any(inv[:3]) else 0
            inv = [0 if i < start else (inv[i] or full) for i in range(3)]
            if st.get('note'):
                notes.append('%s: %s' % (st.get('label') or r.get('label'), st['note']))
            chosen.append(dict(r, label=st.get('label') or r.get('label'),
                               gain=gain, invested=inv[:3], year=int(year)))
        import recommendations as _recmod
        entry['gains_table'] = _recmod.to_gains_table(chosen)
        # His own recommendations join the library, so the next client's
        # review can suggest them (Claude keeps the library; nobody edits it).
        try:
            lib = _recmod.LIBRARY
            text = open(lib).read() if os.path.exists(lib) else ''
            for i, c in enumerate(rec.get('recs_custom') or []):
                st = (rec.get('recs') or {}).get('custom_%d' % i) or {}
                label = (st.get('label') or c.get('label') or '').strip()
                if not label or ('## ' + label.lower()) in text.lower():
                    continue
                key = re.sub(r'[^a-z0-9]+', '_', label.lower()).strip('_')[:40]
                text += ('\n## %s [%s]\n- When: added by the lead advisor on a '
                         'consult review (%s).\n- Signs: %s\n- Size: %s a year as he '
                         'sized it; check against the client.\n- Seen: one consult.\n'
                         % (label, key, datetime.date.today().isoformat(),
                            st.get('note') or 'see his note', st.get('gain') or 'not sized'))
            with open(lib, 'w') as fh:
                fh.write(text)
        except Exception:                                    # noqa: BLE001
            pass
        entry.pop('savings_schedule', None)
        changed.append('recommendations (%d)' % len(chosen))
    _inputs.put(folder, 'deck', entry, by='the lead advisor, on the consult review page',
                note='decided on the review page')

    out = {'read': datetime.datetime.now().isoformat(timespec='seconds'),
           'qdecisions': rec.get('qdecisions') or {},
           'qtext': rec.get('qtext') or {},
           # The client's answers, as recorded on the page: Claude reads them
           # at the refresh and puts what they settle into the plan.
           'qanswers': {k: v for k, v in (rec.get('qanswers') or {}).items() if (v or '').strip()},
           # His reasoning, for whoever (or whatever) builds the deck next:
           # Claude reads these when it pulls the review in.
           'notes': (rec.get('notes') or '').strip(),
           'recommendation_notes': notes,
           # His comments on the Assumptions, by section number.
           'assumption_notes': {k: v.strip() for k, v in
                                (rec.get('assume_notes') or {}).items()
                                if (v or '').strip()},
           # The analyst's check, made on the same page before the lead
           # advisor sees it.
           'stage': rec.get('stage') or 'lead',
           'handoff': rec.get('handoff'),
           'analyst_notes': (rec.get('an_notes') or '').strip(),
           'analyst_assumption_notes': {k: v.strip() for k, v in
                                        (rec.get('an_assume_notes') or {}).items()
                                        if (v or '').strip()}}
    # Slide wording: what was proposed, as edited, unless dropped.
    try:
        with open(_store.json_path(folder, 'review_slides.json')) as fh:
            proposed = json.load(fh)
    except (OSError, ValueError):
        proposed = None
    sd, st = rec.get('sdecisions') or {}, rec.get('stext') or {}
    if proposed is not None:
        out['slides'] = {k: (None if sd.get(k) == 'Drop' else
                             (st.get(k) if st.get(k) not in (None, '') else v))
                         for k, v in proposed.items()}
    # His edits to any other box on the deck: kept only where he changed it,
    # so everything he left alone still follows the figures when they move.
    try:
        with open(_store.json_path(folder, 'review_slides_data.json')) as fh:
            data_text = json.load(fh)
    except (OSError, ValueError):
        data_text = {}
    edits = {k: v for k, v in st.items()
             if k in data_text and v not in (None, '') and v.strip() != data_text[k].strip()}
    if edits:
        out.setdefault('slides', {}).update(edits)
        print('   deck boxes he changed: %s' % ', '.join(sorted(edits)))
    with open(_store.json_path(folder, 'review_decisions.json'), 'w') as fh:
        json.dump(out, fh, indent=1)
    print('   figures applied: %s' % (', '.join(changed) or 'none'))
    print('   question decisions read: %d' % len(out['qdecisions']))
    if out['qanswers']:
        print('   CLIENT ANSWERS (put what they settle into the plan before rebuilding):')
        for k, v in sorted(out['qanswers'].items()):
            print('     %s: %s' % (k, v))
    titles_an = {str(x.get('number')): x.get('title') for x in
                 ((rec.get('assumptions') or {}).get('sections') or ())}
    if out['analyst_notes'] or out['analyst_assumption_notes']:
        print("   THE ANALYST'S CHECK (%s):" % (
            'still with the analyst: fix these, then refresh the page'
            if out['stage'] == 'analyst' else
            'handed to the lead advisor %s' % (out['handoff'] or '')[:10]))
        if out['analyst_notes']:
            print('     ' + out['analyst_notes'])
        for k, v in sorted(out['analyst_assumption_notes'].items(),
                           key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 99):
            print('     - Assumptions %s (%s): %s' % (k, titles_an.get(str(k), ''), v))
    if out['notes'] or notes or out['assumption_notes']:
        print('   NOTES FROM THE LEAD ADVISOR (act on these before building the deck):')
        if out['notes']:
            print('     ' + out['notes'])
        for n in notes:
            print('     - ' + n)
        titles = {str(x.get('number')): x.get('title') for x in
                  ((rec.get('assumptions') or {}).get('sections') or ())}
        for k, v in sorted(out['assumption_notes'].items(),
                           key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 99):
            print('     - Assumptions %s (%s): %s' % (k, titles.get(str(k), ''), v))
    # The follow-up email, now that he has said which questions go.
    try:
        import duediligence as _dd
        _p, email = _dd.write(folder)
        print('   follow-up email written: %s' % os.path.basename(email))
        # Its text, for the review page's Email tab (whoever sends it copies
        # it from there; the .eml opens in Outlook or Mail for the analyst).
        from email import policy
        from email.parser import BytesParser
        with open(email, 'rb') as fh:
            body = BytesParser(policy=policy.default).parse(fh).get_content()
        out['email_text'] = body
        with open(_store.json_path(folder, 'review_decisions.json'), 'w') as fh:
            json.dump(out, fh, indent=1)
    except Exception as exc:                                 # noqa: BLE001
        print('   follow-up email not written: %s' % exc)
    if 'slides' in out:
        print('   slide wording: %d used, %d dropped'
              % (sum(1 for v in out['slides'].values() if v),
                 sum(1 for v in out['slides'].values() if not v)))
    return changed


def decisions(folder):
    """{question key: (decision, wording)} from the last apply, by the
    question's stable key (seed writes the key onto each question)."""
    try:
        with open(_store.json_path(folder, 'review_decisions.json')) as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {}
    try:
        with open(_store.json_path(folder, 'review_questions.json')) as fh:
            ids = json.load(fh)              # {question id: question key}
    except (OSError, ValueError):
        ids = {}
    def words(t):
        return set(re.findall(r'[a-z0-9]{3,}', (t or '').lower()))
    texts = {qid: (v.get('text') if isinstance(v, dict) else '') for qid, v in ids.items()}
    keys = {qid: (v.get('key') if isinstance(v, dict) else v) for qid, v in ids.items()}
    out = {}
    for qid, key in keys.items():
        d = (got.get('qdecisions') or {}).get(qid)
        if d:
            out[key] = (d, None)
    # Reworded questions, matched to the question they were written from.
    # The list can be renumbered when the page is refreshed (Spaulding: an
    # edit made to the old question 1, the tax returns, arrived after the
    # refresh had made question 1 the mortgage); the words say which it was.
    for qid, t in (got.get('qtext') or {}).items():
        if not (t or '').strip():
            continue
        w = words(t)
        best, score = qid if qid in keys else None, -1.0
        for other, txt in texts.items():
            if not txt:
                continue
            o = words(txt)
            sc = len(w & o) / float(len(w | o) or 1)
            if sc > score:
                best, score = other, sc
        if best is None:
            continue
        key = keys[best]
        out[key] = ((out.get(key) or (None, None))[0], t)
    return out


def findings(folder, D):
    """What the documents show, for the lead advisor to sanity-check on the
    analysis review: accounts, debts, cards, pay, cash flow, each with where
    it came from."""
    import inputs as _inputs
    import debt as _debt
    out = {'accounts': [], 'debts': [], 'cards': [], 'pay': [], 'cash': [], 'concerns': []}
    for key, side in (('qualified_accounts', 'Retirement'), ('nonqualified_accounts', 'Other')):
        for r in _inputs.value(folder, key) or []:
            out['accounts'].append({'side': side, 'label': r.get('label'),
                                    'value': r.get('value') or r.get('amount'),
                                    'basis': r.get('basis') or '',
                                    'counted': not r.get('excluded')})
    try:
        g = _debt.gather(folder)
        for side in ('personal', 'practice'):
            for r in g.get(side) or []:
                out['debts'].append({'side': side.title(), 'label': '%s %s' % (
                    r.get('creditor') or '', ('x' + r['account_last4']) if r.get('account_last4') else ''),
                    'what': r.get('what') or r.get('description') or '',
                    'balance': r.get('balance'), 'payment': r.get('payment'),
                    'rate': r.get('rate'), 'basis': r.get('source') or ''})
    except Exception:                                        # noqa: BLE001
        pass
    try:
        import credit as _credit
        for c in (_credit.read(folder, log=lambda *_a: None) or {}).get('cards') or []:
            out['cards'].append({'label': c.get('lender'), 'balance': c.get('balance'),
                                 'limit': c.get('limit')})
    except Exception:                                        # noqa: BLE001
        pass
    f = D.get('income_facts') or {}
    src = f.get('sources') or {}
    for k, lab in (('w2', 'Owner W-2'), ('deferral', 'Owner 401(k) deferral'),
                   ('total_tax', 'Total income tax'), ('distributions', 'Distributions')):
        out['pay'].append({'label': '%s (%s)' % (lab, f.get('year') or '?'),
                           'value': f.get(k), 'basis': src.get(k) or ''})
    cash = D.get('cash') or {}
    for a in cash.get('accounts') or []:
        out['cash'].append({'label': '%s %s' % (a.get('entity') or '', a.get('name') or ''),
                            'balance': a.get('balance'),
                            'surplus': a.get('surplus'), 'as_of': str(a.get('as_of') or '')})
    out['spend'] = D.get('spend')
    out['concerns'] = [{'head': h, 'body': b} for h, b in D['adv'].get('concerns') or []]
    return out


def seed(folder, outdir, mode='consult'):
    """The JSON files Claude loads into a client's review page. mode
    'analysis' is the first review (what the documents show, and the
    questions); 'consult' is the second (the plan, recommendations,
    projections and slides), once the answers are in."""
    import importlib.util
    import deck_template as dt
    import duediligence as dd
    os.makedirs(outdir, exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location('fq_app', os.path.join(here, 'fq_app.py'))
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    p = app.plan_payload(folder)
    D = dt.figures(folder, p.get('client'))

    def money(v):
        return '${:,.0f}'.format(v) if v is not None else 'not worked out'
    figs = [
        dict(key='consult_date', label='Consult date',
             proposed=D['adv'].get('consult_date_text') or 'not set',
             basis='From the plan entry.'),
        dict(key='retire_age', label='Retirement age',
             proposed='%d (in %d)' % (p['retire_age'], p['retire_year']),
             basis='IC form: retirement age goal.'),
        dict(key='target_income', label='Target retirement income, a year',
             proposed=money(p['income']), basis='Today’s dollars.'),
        dict(key='sale_net', label='Practice and building sale, net',
             proposed=money(p['sale_net']),
             basis='65% of collections grown to retirement, plus the building, after tax.'),
        # The sale on the 4Q path: a better-run practice sells for more. The
        # lead advisor's Spaulding deck used $0.937M on the current path and
        # $1.791M with 4Q; without this figure the page could only set one.
        dict(key='sale_net_fq', label='Practice sale, net, on the 4Q path',
             proposed=money(D['adv'].get('sale_net_fq') or p['sale_net']),
             basis='Same as the current path unless you set it: the practice '
                   'the plan builds should sell for more.'),
        dict(key='start_portfolio', label='Starting portfolio', proposed=money(p['start']),
             basis='Qualified plus non-qualified investable assets on file.'),
        dict(key='current_savings', label='Saved a year today',
             proposed=money(p['current_savings']),
             basis='Contributions found on the statements and the IC form.'),
    ]
    for y, v in (p.get('schedule') or [])[:5]:
        figs.append(dict(key='save_%d' % y, label='Savings in %d' % y, proposed=money(v),
                         basis='Current savings plus the practice and personal levers, on the firm’s ramp.'))
    figs += [
        dict(key='ideal_bank_balance', label='Ideal practice bank balance',
             proposed=money(p['ideal_balance']), basis='One month of expenses at recent overhead.'),
        dict(key='target_overhead', label='Overhead target',
             proposed='%d%%' % round((p.get('overhead_goal') or .6) * 100),
             basis='Firm default; the P&L shows %.0f%% today.' % ((p.get('overhead') or 0) * 100)),
        dict(key='fq_wealth', label='Wealth at retirement, with 4Q',
             proposed=money(p.get('fq_wealth')),
             basis='From the projection; changes when the figures above change.'),
    ]
    # Every assumption the models run on, at the firm's figure or the one
    # already decided, for the lead advisor to change.
    def shown(v, pct):
        return '%.2f%%' % (v * 100) if pct else ('%g' % v)
    for key, mod, const, label, pct in dt.ASSUMPTIONS:
        figs.append(dict(key=key, label=label, group='Assumptions',
                         proposed=shown(getattr(mod, const), pct),
                         basis='Firm default.' if getattr(mod, const) ==
                         dt._ASSUMPTION_DEFAULTS[key] else 'As decided earlier.'))
    figs.append(dict(key='building_value', label='Building value today',
                     group='Assumptions',
                     proposed=money(D.get('building')) if D.get('building') else
                     ('needed: the client owns the building' if D.get('owns_building')
                      else 'not owned'),
                     basis='Grown to retirement and sold with the practice.'))
    figs.append(dict(key='refinance', label='Include the debt refinance (yes / no)',
                     group='Assumptions', proposed='yes',
                     basis='Counts the refinance as a savings source on the savings slide.'))
    # The pay structure (slide 11): today's figures from the returns, and
    # the two the proposal turns on.
    inc = dt.income_structure(D)
    srcs = (D.get('income_facts') or {}).get('sources') or {}
    yr = (D.get('income_facts') or {}).get('year')
    for key, label, val, basis in (
            ('income_w2', 'Owner W-2 today, a year', inc and inc['w2'] * 12,
             srcs.get('w2') or 'From the return.'),
            ('income_deferral', 'Owner 401(k) deferral today, a year',
             inc and inc['def'] * 12, srcs.get('deferral') or 'From the return.'),
            ('income_total_tax', 'Total income tax, a year', inc and inc['tax'] * 12,
             (srcs.get('total_tax') or 'Federal plus state, from the returns.')
             + (' (%s)' % yr if yr else '')),
            ('income_distributions', 'Distributions today, a year',
             inc and inc['dist'] * 12, srcs.get('distributions') or 'From the return.'),
            ('income_w2_proposed', 'Proposed W-2, a year', inc and inc['p_w2'] * 12,
             'Today’s W-2 down to the next $5,000 a month.'),
            ('income_tax_rate_proposed', 'Tax rate on the proposed W-2',
             None if not inc else '%d%%' % round(inc['p_rate'] * 100),
             'Firm default. Distributions are set so take-home stays the same.')):
        figs.append(dict(key=key, label=label, slide=11,
                         proposed=val if isinstance(val, str) else money(val),
                         basis=basis))
    # Returns against 4Q (slide 15): each account's return from its
    # statements, and 4Q's over the same dates, which only the firm has.
    rets = D.get('returns') or {}
    acct_map = {}
    for i, (label, value) in enumerate(D.get('slide_parts') or []):
        r = rets.get(label) or {}
        name = label.replace('[', '(').replace(']', ')')
        acct_map[str(i)] = label
        if r.get('measured_with'):
            per = 'Measured with %s' % re.sub(r'\s*\[.*?\]', '', r['measured_with'])
            figs.append(dict(key='ret_4q_%d' % i, slide=15,
                             label='%s: 4Q return' % name, proposed='same as that account',
                             basis=per + '; leave blank.'))
            continue
        figs.append(dict(key='ret_acct_%d' % i, slide=15,
                         label='%s: return, annualized' % name,
                         proposed=('%.2f%%' % r['return_pct']) if r.get('return_pct') is not None
                         else 'not on the statements',
                         basis=('%s. %s' % (r.get('period') or 'Period not stated',
                                            r.get('basis') or '')).strip()))
        figs.append(dict(key='ret_4q_%d' % i, slide=15,
                         label='%s: 4Q return, same dates' % name,
                         proposed='needed',
                         basis='4Q\u2019s annualized return for %s. The firm\u2019s '
                               'figure; the slide\u2019s "vs 4Q" and "left on the '
                               'table" are worked from it.' % (r.get('period') or 'the same period')))
    with open(_store.json_path(folder, 'review_accounts.json'), 'w') as fh:
        json.dump(acct_map, fh, indent=1)
    # The recommendations: the firm's whole list, the ones the documents
    # point to ticked, for the lead advisor to keep, change or add to.
    try:
        import recommendations as _rec
        recs = _rec.propose(folder, D) if mode == 'consult' else []
    except Exception as exc:                                 # noqa: BLE001
        print('   recommendations skipped: %s' % exc)
        recs = []
    rows = dd.findings(folder)
    rows.sort(key=lambda r: (r[0] == 'savings', r[0] == 'capacity',
                             {'High': 0}.get(r[4], 1)))
    ids = {}
    for i, (key, q, why, src, pri, dec) in enumerate(rows, 1):
        # Named by the question itself, not its place in the list, so a
        # refresh that reorders the questions keeps every decision and
        # rewording on the question it was made for.
        import hashlib
        qid = 'q' + hashlib.sha1(key.encode('utf-8')).hexdigest()[:10]
        ids[qid] = {'key': key, 'text': q}
        with open(os.path.join(outdir, qid + '.json'), 'w') as fh:
            json.dump({'n': i, 'key': key, 'text': q, 'why': why, 'source': src,
                       'priority': pri, 'decision': dec}, fh)
    with open(_store.json_path(folder, 'review_questions.json'), 'w') as fh:
        json.dump(ids, fh, indent=1)
    # The questions the analysis review asked, kept so the consult review can
    # say which of them the documents have since answered: a question the
    # toolkit no longer raises, after new documents, is one they settled.
    asked_path = _store.json_path(folder, 'analysis_questions.json')
    answered_by_docs = []
    if mode == 'analysis':
        with open(asked_path, 'w') as fh:
            json.dump({v['key']: v['text'] for v in ids.values()}, fh, indent=1)
    else:
        try:
            with open(asked_path) as fh:
                asked = json.load(fh)
        except (OSError, ValueError):
            asked = {}
        now = {v['key'] for v in ids.values()}
        for key, text in asked.items():
            if key not in now:
                answered_by_docs.append({'text': text})
    # The slide wording Claude drafted from the documents, for approval.
    try:
        words = dt.proposed_wording(folder, D) if mode == 'consult' else []
    except Exception as exc:  # noqa: BLE001 - the page works without it
        print('   slide wording skipped: %s' % exc)
        words = []
    slides = {'items': [{'id': w['id'], 'slide': w['slide'],
                         'heading': w['heading'], 'hint': w['example'],
                         'text': w['text'], 'status': 'check'} for w in words]}
    # Everything else the deck says about this client, box by box, so the
    # lead advisor can read the whole deck slide by slide beside its picture
    # and change any of it: the figures, the concerns, the lever rows, the
    # debt wording. His edits are applied when the deck is built.
    data_text = {}
    if mode == 'consult':
        try:
            have = {it['id'] for it in slides['items']}
            for it in deck_boxes(folder, D):
                if it['id'] in have:
                    continue
                slides['items'].append(it)
                data_text[it['id']] = it['text']
        except Exception as exc:                             # noqa: BLE001
            print('   deck boxes skipped: %s' % exc)
        slides['items'].sort(key=lambda it: (it['slide'], int(
            (re.findall(r'(\d+)$', it['id']) or ['0'])[0])))
    with open(_store.json_path(folder, 'review_slides_data.json'), 'w') as fh:
        json.dump(data_text, fh, indent=1)
    fig_slides = sorted({f['slide'] for f in figs if f.get('slide')})
    pics = slide_pictures(folder, slides['items'], outdir, also=fig_slides) \
        if mode == 'consult' else {}
    for it in slides['items']:
        it['pic'] = pics.get(it['slide'])
    titles = {}
    try:
        from pptx import Presentation
        tp = Presentation(dt.TEMPLATE)
        for n in sorted({it['slide'] for it in slides['items']} | set(fig_slides)):
            tx = [sh.text_frame.text.strip() for sh in tp.slides[n - 1].shapes
                  if sh.has_text_frame and sh.text_frame.text.strip()]
            titles[n] = ' / '.join(tx[:2])[:80]
    except Exception:  # noqa: BLE001
        pass
    with open(os.path.join(outdir, 'slides.json'), 'w') as fh:
        json.dump(slides, fh)
    with open(_store.json_path(folder, 'review_slides.json'), 'w') as fh:
        json.dump({w['id']: w['text'] for w in words}, fh, indent=1)
    plan = {'client': D['names'], 'surname': D['surname'], 'figures': figs,
            'concerns': [{'head': h, 'body': b} for h, b in D['adv'].get('concerns') or []],
            'decided': {}, 'qdecisions': {}, 'qtext': {},
            'sdecisions': {}, 'stext': {}, 'qanswers': {}, 'notes': '',
            'recommendations': recs, 'recs': {}, 'recs_custom': [],
            'pics': {str(k): v for k, v in pics.items()},
            'slide_titles': {str(k): v for k, v in titles.items()},
            'question_ids': sorted(ids), 'mode': mode,
            'answered_by_docs': answered_by_docs,
            'findings': findings(folder, D) if mode == 'analysis' else None}
    # The Assumptions, as the first tab: the lead advisor reads the plan's
    # base figures in the layout he knows before anything else.
    try:
        import assumptions as _asm
        plan['assumptions'] = _asm.payload(folder, p.get('client'))
    except Exception as exc:                                 # noqa: BLE001
        print('   assumptions tab skipped: %s' % exc)
        plan['assumptions'] = None
    # What the lead advisor already decided on an earlier review (the
    # analysis review, or this page before a refresh) carries over, matched
    # by the question itself.
    try:
        prev = decisions(folder)
        with open(_store.json_path(folder, 'review_decisions.json')) as fh:
            prev_all = json.load(fh)
    except (OSError, ValueError):
        prev, prev_all = {}, {}
    by_key = {v['key'] if isinstance(v, dict) else v: k for k, v in ids.items()}
    for key, (d, t) in prev.items():
        qid = by_key.get(key)
        if qid and d:
            plan['qdecisions'][qid] = d
        if qid and t:
            plan['qtext'][qid] = t
    plan['notes'] = prev_all.get('notes') or ''
    plan['assume_notes'] = prev_all.get('assumption_notes') or {}
    plan['an_notes'] = prev_all.get('analyst_notes') or ''
    plan['an_assume_notes'] = prev_all.get('analyst_assumption_notes') or {}
    # A new analysis review starts with the analyst; the consult review is
    # the lead advisor's.
    plan['stage'] = ('analyst' if mode == 'analysis' and
                     prev_all.get('stage') != 'lead' else 'lead')
    plan['handoff'] = prev_all.get('handoff')
    # The page's own link, so the hand-off can show it. Known once the page
    # has been published (review_pages.json); Claude writes it after the
    # first publish otherwise.
    try:
        with open(_store.json_path(folder, 'review_pages.json')) as fh:
            plan['page_url'] = (json.load(fh) or {}).get(mode)
    except (OSError, ValueError):
        plan['page_url'] = None
    with open(os.path.join(outdir, 'plan.json'), 'w') as fh:
        json.dump(plan, fh, default=str)

    pr = D['proj'] or {}
    get = lambda d, y: (d or {}).get(str(y), (d or {}).get(y))   # noqa: E731
    proj_rows = []
    for y in sorted(int(k) for k in (pr.get('current') or {})):
        if y > pr['retire_year'] + 3:
            break
        proj_rows.append([y, round(get(pr['current_deposits'], y) or 0),
                          round(get(pr['current'], y) or 0),
                          round(get(pr['fq_deposits'], y) or 0),
                          round(get(pr['fq'], y) or 0)])
    import plan as P
    import savings as S
    names = {'overhead': 'Overhead to goal', 'adjustment': 'Insurance adjustments',
             'hygiene': 'Hygiene days', 'pull_through': 'Doctor pull-through from hygiene',
             'new_patients': 'New patient flow', 'fees': 'Fee increase',
             'collections': 'Collection %', 'per_patient': 'Production per patient'}
    work = {
        'start_parts': [[a, round(b)] for a, b in D['start_parts']],
        'start': round(D['start'] or 0),
        'gains': [{'label': g['label'], 'gain': round(g['gain'] or 0), 'basis': g.get('basis'),
                   'invested': [round(x or 0) for x in g['invested']], 'kind': g.get('kind')}
                  for g in p['gains']],
        'levers': [{'label': names.get(k, k),
                    'value': round(v['value']) if v.get('value') is not None else None,
                    'basis': v.get('basis') or ('Needs: ' + ', '.join(v.get('needs') or []))}
                   for k, v in (D['levers'] or {}).items()],
        'sale': {'collections': round(D['collections'] or 0), 'multiple': P.PRACTICE_MULTIPLE,
                 'years': int((D['retire_age'] or 0) - (D['age'] or 0)),
                 'growth': P.PRACTICE_GROWTH, 'building': D['building'],
                 'building_growth': P.BUILDING_GROWTH, 'net_factor': P.SALE_NET,
                 'gross': round(D['sale_gross'] or 0), 'net': round(D['sale_derived'] or 0),
                 'advisor': D['adv'].get('sale_net')},
        'projection': {'rows': proj_rows, 'current_rate': S.CURRENT_RETURN,
                       'fq_rate': S.FQ_RETURN, 'first_year_fq': S.FIRST_YEAR_FQ_RETURN,
                       'spend': round(D['spend'] or 0), 'income': D['income'],
                       'retire_year': pr.get('retire_year')},
    }
    # What the page's what-if needs to rerun the projection in the browser
    # (a port of savings.project, checked to the dollar on Oyler).
    lv = D.get('lever_inputs') or {}
    adv = D['adv']
    work['model'] = {
        'consult_date': adv.get('consult_date') or datetime.date.today().isoformat(),
        'age': D['age'], 'retire_age': D['retire_age'], 'start': D['start'],
        'current_savings': D['current_savings'], 'spend': D['spend'],
        'schedule': [list(x) for x in (D['schedule'] or [])], 'income': D['income'],
        'sale_net': D.get('sale') or 0, 'horizon': adv.get('horizon_age') or 90,
        'first_year': pr.get('first_year'), 'overhead': lv.get('overhead'),
        'target_overhead': lv.get('target_overhead') or 0.6,
        'net_collections': lv.get('net_collections'),
        # The two parts of the sale at the planned retirement, so the page can
        # regrow each at its own rate when the retirement age changes.
        'sale_practice': (D['collections'] or 0) * P.PRACTICE_MULTIPLE * (1 + P.PRACTICE_GROWTH) ** max(0, int((D['retire_age'] or 0) - (D['age'] or 0))),
        'sale_building': (D['building'] or 0) * (1 + P.BUILDING_GROWTH) ** max(0, int((D['retire_age'] or 0) - (D['age'] or 0)))}
    work['model']['rates'] = {'inflation': S.INFLATION, 'current': S.CURRENT_RETURN,
                              'fq': S.FQ_RETURN, 'first': S.FIRST_YEAR_FQ_RETURN,
                              'practice_growth': P.PRACTICE_GROWTH,
                              'building_growth': P.BUILDING_GROWTH}
    work['base'] = {'fq_at': pr.get('fq_at_retirement'),
                    'cur_at': pr.get('current_at_retirement')}
    with open(os.path.join(outdir, 'workings.json'), 'w') as fh:
        json.dump(work, fh)
    print('   %d figures, %d concerns, %d questions written to %s'
          % (len(figs), len(plan['concerns']), len(ids), outdir))
    return outdir


def deck_boxes(folder, D):
    """Every box on the deck as it is built now that says something about
    this client: its text, how much it needs a person, and what the firm
    usually puts there.

    Read from a deck built for the purpose, against the template: a box whose
    text is still the template's is the firm's standing wording and left
    out; everything else (figures, sentences, and every box still marked for
    the advisor) is listed. Reading the built deck rather than the fill list
    is what catches the boxes nothing fills, like the fees and 4Q's returns.
    """
    import tempfile
    from pptx import Presentation
    import deck_template as dt
    scratch = tempfile.mkdtemp()
    path = os.path.join(scratch, 'boxes.pptx')
    dt.render(folder, None, path)
    built = Presentation(path)
    tmpl = Presentation(dt.TEMPLATE)
    drop = sorted(dt.dropped(D))
    keep_n = [n for n in range(1, len(tmpl.slides) + 1) if n not in drop]
    try:
        with open(os.path.join(HERE, 'assets', 'deck_examples.json')) as fh:
            examples = json.load(fh)
    except (OSError, ValueError):
        examples = {}
    out = []
    for idx, slide in enumerate(built.slides):
        n = keep_n[idx]
        was = {sh.name: sh.text_frame.text.strip()
               for sh in tmpl.slides[n - 1].shapes if sh.has_text_frame}
        for sh in slide.shapes:
            if not sh.has_text_frame:
                continue
            text = sh.text_frame.text.strip()
            blank = text.startswith(('[ADVISOR', '[TBD')) or text == 'TBD'
            if not text or (text == was.get(sh.name) and not blank):
                continue
            status = 'needed' if blank else _box_status(n, text, D)
            ex = examples.get('%d.%s' % (n, sh.name))
            out.append({'id': '%d.%s' % (n, sh.name), 'slide': n, 'heading': '',
                        'status': status, 'data': True,
                        'text': '' if blank else text.replace('\u2019', "'"),
                        'hint': ('Like: \u201c%s\u201d' % ex[:120]) if ex and ex.strip()
                        not in ('#', '$#', '#%') else
                        {'needed': 'still to write',
                         'check': 'worded by the code from the documents: read it',
                         'sure': 'from the checked documents or a decision already made'}[status]})
    import shutil
    shutil.rmtree(scratch, ignore_errors=True)
    return out


# Slides whose wording is the code's own judgment, worth a read even when
# every figure in it is right: the tax red flags and the debt structuring.
_JUDGED_SLIDES = {7, 10}


def _box_status(n, text, D):
    """How much a deck box needs a person: 'sure', or 'check'.

    Sure: a figure carried from the checked documents or the plan, or the
    lead advisor's own words (his concerns on slide 3). Check: a sentence the
    code composed, an estimate, or anything on a judged slide. Blank boxes are
    'needed' and decided by the caller.
    """
    t = str(text).strip()
    if n == 3 and (D.get('adv') or {}).get('concerns'):
        return 'sure'
    # The firm's standing wording with the client's name or balance dropped
    # in (tax solutions, the cash flow process): the same on every deck.
    if n in (8, 13):
        return 'sure'
    if re.search(r'\b(est\.|about|approx|roughly|likely|look like)\b|~|\?', t, re.I):
        return 'check'
    if n in _JUDGED_SLIDES and len(t) > 25:
        return 'check'
    if len(t) > 70:
        return 'check'
    return 'sure'


def slide_pictures(folder, items, outdir, also=()):
    """A picture of each slide that has wording to approve, from the client's
    built deck, with every box on it outlined and numbered to match the list
    on the review page. Returns {template slide: file name}."""
    import shutil
    import subprocess
    import tempfile
    import glob
    from pptx import Presentation
    from pptx.util import Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    import deck_template as dt
    if not (items or also):
        return {}
    # A deck built here, only to take pictures of: the review comes before
    # any deck the team uses, so there may not be one yet.
    scratch = tempfile.mkdtemp()
    deck_path = os.path.join(scratch, 'review.pptx')
    try:
        dt.render(folder, None, deck_path)
    except Exception as exc:                                 # noqa: BLE001
        print('   slide pictures skipped: %s' % exc)
        return {}
    D = dt.figures(folder, None)
    drop = dt.dropped(D)
    prs = Presentation(deck_path)
    want = {n: [] for n in also}
    # Numbered within each slide, 1, 2, 3... in reading order, to match the
    # list beside its picture.
    for it in items:
        want.setdefault(it['slide'], []).append(it)
        it['n'] = len(want[it['slide']])
    keep = {}
    for n, its in want.items():
        idx = n - 1 - sum(1 for d in drop if d < n)
        if idx >= len(prs.slides):
            continue
        slide = prs.slides[idx]
        by = {sh.name: sh for sh in slide.shapes}
        for it in its:
            sh = by.get(it['id'].split('.', 1)[1])
            if sh is None:
                continue
            box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, sh.left, sh.top,
                                         sh.width, sh.height)
            box.fill.background()
            # The outline says how much the box needs a person, as the list
            # beside the picture does: needed, to check, sure.
            col = {'needed': RGBColor(0xC2, 0x41, 0x0C), 'sure': RGBColor(0x1E, 0x7A, 0x46),
                   'check': RGBColor(0xE0, 0xB4, 0x00)}.get(it.get('status'),
                                                            RGBColor(0xE0, 0x6C, 0x00))
            box.line.color.rgb = col
            box.line.width = Pt(2.5)
            tag = slide.shapes.add_shape(MSO_SHAPE.OVAL, sh.left - Pt(9),
                                         sh.top - Pt(9), Pt(20), Pt(20))
            tag.fill.solid()
            tag.fill.fore_color.rgb = col
            tag.line.fill.background()
            tf = tag.text_frame
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
            tf.text = str(it['n'])
            r = tf.paragraphs[0].runs[0]
            r.font.size = Pt(9)
            r.font.bold = True
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        keep[idx] = n
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, 'marked.pptx')
    prs.save(src)
    subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', tmp, src],
                   capture_output=True, timeout=300)
    pdf = os.path.join(tmp, 'marked.pdf')
    out = {}
    if os.path.exists(pdf):
        os.makedirs(os.path.join(outdir, 'slides'), exist_ok=True)
        for idx, n in keep.items():
            base = os.path.join(tmp, 's%d' % n)
            subprocess.run(['pdftoppm', '-jpeg', '-r', '90', '-f', str(idx + 1),
                            '-l', str(idx + 1), '-singlefile', pdf, base],
                           capture_output=True, timeout=120)
            if os.path.exists(base + '.jpg'):
                name = 'slides/%d.jpg' % n
                shutil.copy(base + '.jpg', os.path.join(outdir, name))
                out[n] = name
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(scratch, ignore_errors=True)
    return out


def main():
    ap = argparse.ArgumentParser(description='the lead advisor’s consult review page')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('seed')
    s.add_argument('folder')
    s.add_argument('--out', required=True)
    s.add_argument('--mode', choices=('analysis', 'consult'), default='consult')
    a_ = sub.add_parser('apply')
    a_.add_argument('folder')
    a_.add_argument('plan_json')
    a = ap.parse_args()
    if a.cmd == 'seed':
        seed(a.folder, a.out, a.mode)
    else:
        apply(a.folder, a.plan_json)


if __name__ == '__main__':
    main()
