#!/usr/bin/env python3
"""Brogan's consult review page: what goes onto it, and what comes back.

    python3 review_page.py seed  "<client folder>" --out <dir>
    python3 review_page.py apply "<client folder>" <plan_figures.json>

THE PAGE
A private claude.ai page per client (an artifact with a small database), where
Brogan sees the toolkit's proposal for every figure the consult deck uses, the
workings behind them (starting portfolio, sale, savings sources, levers, the
year-by-year savings worksheet), the concerns from the initial notes, and the
follow-up questions. He types his own figure where he disagrees and marks each
question Send, Answered or Strike.

WHY TWO STEPS
The toolkit has no claude.ai login; only Claude can read and write the page's
database. So Claude runs `seed` and loads the JSON it writes into the page,
and after Brogan has decided, Claude saves the page's "plan/figures" record to
a file and runs `apply`, which writes his decisions where the toolkit reads
them:
  _Audit/plan_inputs.json, key "deck"   his figures and the concerns, which
                                          the deck and the plan card use
  _Audit/review_decisions.json           his question decisions and wording,
                                          which the follow-up email uses

THE RECORD THAT SAVES
Everything Brogan changes lives on the one "plan/figures" record: "decided"
(his figures), "concerns", "qdecisions" and "qtext" (question decision and
wording, by question id). The page writes nothing else, because in the
Claude app's viewer the store hands back read-only objects and the
per-question records never took a write (found 29 Oct, after a morning of it).
"""
import os
import re
import sys
import json
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
    """Write Brogan's decisions from the page into the client folder."""
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
        if key == 'consult_date':
            entry['consult_date_text'] = str(raw).strip()
            changed.append(key)
            continue
        if key in ('retire_age', 'target_income', 'sale_net', 'start_portfolio',
                   'current_savings', 'ideal_bank_balance', 'target_overhead'):
            v = _num(raw)
            if key == 'target_overhead' and v and v > 1:
                v = v / 100.0
            if v is not None:
                entry[key] = int(v) if key == 'retire_age' else v
                changed.append(key)
    if schedule:
        entry['savings_schedule'] = [[y, schedule[y]] for y in sorted(schedule)]
    if rec.get('concerns'):
        entry['concerns'] = [[c.get('head', ''), c.get('body', '')]
                             for c in rec['concerns'] if c.get('head')]
        changed.append('concerns')
    _inputs.put(folder, 'deck', entry, by='Brogan, on the consult review page',
                note='decided on the review page')

    out = {'read': datetime.datetime.now().isoformat(timespec='seconds'),
           'qdecisions': rec.get('qdecisions') or {},
           'qtext': rec.get('qtext') or {}}
    with open(os.path.join(folder, '_Audit', 'review_decisions.json'), 'w') as fh:
        json.dump(out, fh, indent=1)
    print('   figures applied: %s' % (', '.join(changed) or 'none'))
    print('   question decisions read: %d' % len(out['qdecisions']))
    return changed


def decisions(folder):
    """{question key: (decision, wording)} from the last apply, by the
    question's stable key (seed writes the key onto each question)."""
    try:
        with open(os.path.join(folder, '_Audit', 'review_decisions.json')) as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {}
    try:
        with open(os.path.join(folder, '_Audit', 'review_questions.json')) as fh:
            ids = json.load(fh)              # {question id: question key}
    except (OSError, ValueError):
        ids = {}
    out = {}
    for qid, key in ids.items():
        d = (got.get('qdecisions') or {}).get(qid)
        t = (got.get('qtext') or {}).get(qid)
        if d or t:
            out[key] = (d, t)
    return out


def seed(folder, outdir):
    """The JSON files Claude loads into a client's review page."""
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
    rows = dd.findings(folder)
    rows.sort(key=lambda r: (r[0] == 'savings', r[0] == 'capacity',
                             {'High': 0}.get(r[4], 1)))
    ids = {}
    for i, (key, q, why, src, pri, dec) in enumerate(rows, 1):
        qid = 'q%02d' % i
        ids[qid] = key
        with open(os.path.join(outdir, qid + '.json'), 'w') as fh:
            json.dump({'n': i, 'key': key, 'text': q, 'why': why, 'source': src,
                       'priority': pri, 'decision': dec}, fh)
    with open(os.path.join(folder, '_Audit', 'review_questions.json'), 'w') as fh:
        json.dump(ids, fh, indent=1)
    plan = {'client': D['names'], 'surname': D['surname'], 'figures': figs,
            'concerns': [{'head': h, 'body': b} for h, b in D['adv'].get('concerns') or []],
            'decided': {}, 'qdecisions': {}, 'qtext': {},
            'question_ids': sorted(ids)}
    with open(os.path.join(outdir, 'plan.json'), 'w') as fh:
        json.dump(plan, fh)

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
    work['base'] = {'fq_at': pr.get('fq_at_retirement'),
                    'cur_at': pr.get('current_at_retirement')}
    with open(os.path.join(outdir, 'workings.json'), 'w') as fh:
        json.dump(work, fh)
    print('   %d figures, %d concerns, %d questions written to %s'
          % (len(figs), len(plan['concerns']), len(ids), outdir))
    return outdir


def main():
    ap = argparse.ArgumentParser(description='Brogan’s consult review page')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('seed')
    s.add_argument('folder')
    s.add_argument('--out', required=True)
    a_ = sub.add_parser('apply')
    a_.add_argument('folder')
    a_.add_argument('plan_json')
    a = ap.parse_args()
    if a.cmd == 'seed':
        seed(a.folder, a.out)
    else:
        apply(a.folder, a.plan_json)


if __name__ == '__main__':
    main()
