#!/usr/bin/env python3
"""Practice opportunities: The analyst’s lever model, for the consult deck.

Ported from the `practice improvements` tab of `_spec/initial notes-kinsler.xlsx`
formula by formula. `_spec/verify_levers.py` reruns it on Kinsler's own inputs
and checks every lever against his cached values.

EVERY BLOCK IS THE SAME SHAPE
    incremental production -> incremental revenue -> to the owner at a 50%
    target overhead

THE LEVERS, AS HIS SHEET COMPUTES THEM
    overhead to target   (current OH - 50%) x net collections
    adjustment % / mix   (adjust % - ideal) x net production x 99.5%, x (1 - 50%)
                         ideal is 16% when adjust % is 25% or more, else
                         adjust % less ten points
    extra hygiene        gross x hygiene share x (ideal days / days - 1),
                         x (1 - adjust %) x 99.5%, x (1 - 50%)
                         ideal days = max(2 x doctor days, days + 2), only when
                         rooms are free and hygiene is booked 6+ months out
    doctor pull-through  the extra hygiene production x (doctor $ per hygiene $),
                         x (1 - adjust %) x 99.5%, x (1 - 50%)
    new patient %        (last year's NP% - this year's) x patients x net prod
                         per patient x 99.5%, x (1 - 50%)
    fee study            gross x fees-off x FFS share x 99.5%, x (1 - 50%)
    collection %         (99.5% - collection %) x net production x (1 - 50%)
    net prod / patient   (last year - this year, if falling) x patients x 99.5%,
                         x (1 - 50%)

Ranked by dollars. The top five are subtotalled, with a worst-case line that
assumes half the patients leave when a plan is dropped.

HIS OWN CAVEAT, PRINTED RATHER THAN LEFT IN A SPREADSHEET
The blocks overlap, so the sum is not additive. Extra hygiene and doctor
pull-through both start from the same added chair-days; overhead to target
and every revenue lever both raise what reaches the owner.

WHAT IS MISSING IS SAID, NOT GUESSED
A lever whose inputs are not on file comes back with what it needs instead of
a figure. On a first pass most prospects have a P&L and an IC form and not yet
a patient count, so overhead and collections compute and new patients waits.
"""

COLLECT_IDEAL = 0.995
TARGET_OH = 0.60     # the lead advisor's recent decks: Spaulding 60%, Rebol 62%
ATTRITION = 0.50
ADJ_THRESHOLD = 0.25
ADJ_IDEAL_HIGH = 0.16
HYG_RATIO_TARGET = 2


def _need(*names):
    return {'value': None, 'needs': list(names)}


def _ok(v, basis):
    return {'value': v, 'basis': basis, 'needs': []}


def compute(x):
    """x is a dict of inputs; any may be None. Returns the ranked levers."""
    g = x.get
    # The goal overhead is the advisor's call on the deck (Rebol 62%,
    # Spaulding 60%, Kinsler 51%); the analyst’s model defaults it to 50%. Every
    # block hands the owner what is left after it, so it drives them all.
    target = g('target_overhead') or TARGET_OH
    owner = 1 - target
    out = {}

    # Overhead to the 50% target, on net collections.
    if g('overhead') is not None and g('net_collections'):
        v = max(0.0, (g('overhead') - target) * g('net_collections'))
        out['overhead'] = _ok(v, 'Overhead %.1f%% to a %.0f%% goal, on '
                              'net collections of $%s.'
                              % (100 * g('overhead'), 100 * target,
                                 '{:,.0f}'.format(g('net_collections'))))
    else:
        out['overhead'] = _need('overhead', 'net collections')

    # Adjustment % and plan mix.
    adj, net = g('adjust_pct'), g('net_production')
    if adj is not None and net and adj < ADJ_THRESHOLD and \
            not g('adjust_rule_below_threshold'):
        # The analyst’s sheet would take ten points off any adjustment rate below
        # 25%, which on a fee-for-service practice (Oyler, 5%) proposes
        # dropping carriers it does not take. Below the threshold there is
        # no plan-mix lever; his rule is kept behind a switch.
        out['adjustment'] = _ok(0.0, 'Adjustments of %.1f%% are below the '
                                '25%% where dropping carriers pays.'
                                % (100 * adj))
        out['adjustment']['worst_case'] = 0.0
    elif adj is not None and net:
        ideal = ADJ_IDEAL_HIGH if adj >= ADJ_THRESHOLD else adj - 0.10
        gap = adj - ideal
        v = net * gap * COLLECT_IDEAL * owner
        out['adjustment'] = _ok(v, 'Adjustments of %.1f%% against an ideal '
                                'of %.1f%%.' % (100 * adj, 100 * ideal))
        out['adjustment']['worst_case'] = v * (1 - ATTRITION)
    else:
        out['adjustment'] = _need('adjustment %', 'net production')

    # Extra hygiene chair-days, and the doctor work they pull through.
    days, dds = g('hygiene_days'), g('doctor_days')
    gross, hyg = g('gross_production'), g('hygiene_share')
    if None not in (days, dds, gross, hyg, adj) and days:
        room = g('hygiene_rooms_free') and g('hygiene_booked_6mo')
        ideal = max(HYG_RATIO_TARGET * dds, days + 2) if room else days
        add_gross = gross * hyg * (ideal / float(days) - 1)
        v = add_gross * (1 - adj) * COLLECT_IDEAL * owner
        out['hygiene'] = _ok(v, 'Hygiene %g to %g chair-days a week.'
                             % (days, ideal))
        ratio = g('doctor_per_hygiene_dollar')
        if ratio:
            v2 = add_gross * ratio * (1 - adj) * COLLECT_IDEAL * owner
            out['pull_through'] = _ok(v2, 'Doctor production of $%.2f per '
                                      'hygiene dollar on the added days.'
                                      % ratio)
        else:
            out['pull_through'] = _need('doctor and hygiene production split')
    else:
        out['hygiene'] = _need('hygiene days', 'doctor days',
                               'gross production', 'hygiene share',
                               'adjustment %')
        out['pull_through'] = _need('the hygiene lever first')

    # New patient % back to last year's.
    now, before = g('np_pct'), g('np_pct_prior')
    pats, npp = g('patients'), g('net_per_patient_prior')
    if None not in (now, before, pats, npp):
        v = max(0.0, before - now) * pats * npp * COLLECT_IDEAL * owner
        out['new_patients'] = _ok(v, 'New patients from %.1f%% back to '
                                  '%.1f%%.' % (100 * now, 100 * before))
    else:
        out['new_patients'] = _need('patients seen', 'new patient % by year')

    # Fee study, scoped to fee-for-service.
    off, ffs = g('fees_off'), g('ffs_share')
    if None not in (off, ffs, gross):
        v = max(0.0, gross * off * ffs * COLLECT_IDEAL * owner)
        out['fees'] = _ok(v, 'Fees %.1f%% below the benchmark on the %.0f%% '
                          'of production that is fee-for-service.'
                          % (100 * off, 100 * ffs))
        # The analyst computes it but holds it out of the top five when the FFS
        # share is his assumption rather than the practice's figure
        # ("hold - needs FFS %"). Same here.
        if g('ffs_share_assumed'):
            out['fees']['hold'] = 'needs the real fee-for-service share'
    else:
        out['fees'] = _need('fee study', 'fee-for-service share')

    # Collection ratio to 99.5%.
    col = g('collection_pct')
    if col is not None and col > 1.02:
        # More collected than produced: the production export counts
        # something the income side does not (or the reverse). Not a lever
        # until someone looks.
        out['collections'] = _need('a collection %% that makes sense (read %.0f%%)'
                                   % (100 * col))
    elif col is not None and net:
        v = max(0.0, (COLLECT_IDEAL - col) * net) * owner
        out['collections'] = _ok(v, 'Collections from %.1f%% to 99.5%%.'
                                 % (100 * col))
    else:
        out['collections'] = _need('collection %', 'net production')

    # Net production per patient, only if it fell.
    npp_now = g('net_per_patient')
    if None not in (npp_now, npp, pats):
        v = max(0.0, npp - npp_now) * pats * COLLECT_IDEAL * owner
        out['per_patient'] = _ok(v, 'Net production per patient back to '
                                 'last year’s.')
    else:
        out['per_patient'] = _need('patients seen', 'net production by year')

    return out


LABELS = {
    'overhead': 'Overhead reduction to 50% target',
    'adjustment': 'Adjustment % / plan mix (drop carriers)',
    'pull_through': 'Doctor production pulled through by extra hygiene',
    'hygiene': 'Hygiene chair-days',
    'new_patients': 'New patient % (recover last year’s rate)',
    'fees': 'Fee study (raise fees to benchmark, FFS-scoped)',
    'collections': 'Collection % to 99.5% ideal',
    'per_patient': 'Net production per patient',
}


def ranked(levers, top=5):
    """Computed levers by dollars, the top-n subtotal, and the worst case."""
    rows = sorted(((k, v) for k, v in levers.items()
                   if v.get('value') is not None),
                  key=lambda kv: -kv[1]['value'])
    head = [kv for kv in rows if not kv[1].get('hold')][:top]
    sub = sum(v['value'] for _, v in head)
    worst = sub
    for k, v in head:
        if k == 'adjustment':
            worst = worst - v['value'] + v['worst_case']
    waiting = [(k, v['needs']) for k, v in levers.items()
               if v.get('value') is None]
    return {'rows': [(k, LABELS[k], v['value'], v['basis']) for k, v in rows],
            'top_subtotal': sub, 'worst_case': worst, 'waiting': waiting,
            'caveat': 'The levers overlap, so the total is not the sum of '
                      'the parts.'}
