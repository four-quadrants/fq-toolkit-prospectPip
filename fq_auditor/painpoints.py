#!/usr/bin/env python3
"""The pain points block at the end of the initial notes.

WHAT BROGAN WRITES
Read from four of his initial notes (Farag, Spaulding, Wright, Kinsler): two
kinds of line near the end.

  1. The dentist's pain in their own words ("Dentist PAIN: 1, work/life
     balance; 2, QB..."), from the call and the IC form's true/false page.
  2. The consult themes, each a short heading with the evidence after a dash:
     "Tax management, late files, surprises, penalties", "Practice
     efficiencies: hyg efficiency %, collect %, adjust %", "Debt structuring",
     "QB improvements, not tying to taxes, deprec/amort", "CPA upgrade
     needed", "Comprehensive plan, biz/personal". Then the fee range and the
     timeline, which are the advisor's.

Every line here is a theme plus the figure that earns it, so nothing appears
that the documents do not support. The call itself is not read yet; what the
dentist said on it goes in by hand, and the row says so.
"""
import re
import email
from email import policy


def _form_text(path):
    """The IC form's plain text, decoded. It arrives as an .eml."""
    try:
        with open(path, 'rb') as fh:
            msg = email.message_from_binary_file(fh, policy=policy.default)
        part = msg.get_body(preferencelist=('plain',))
        if part is not None:
            return part.get_content()
    except Exception:
        pass
    try:
        return open(path, errors='replace').read()
    except Exception:
        return ''


# An answer on the form's true/false page reads "True. I am not ready to
# settle." The answer sentence is the client's own wording, so it is quoted
# as it stands. Only the ones that name a problem are kept.


# The form's fixed statements, the answer that makes each one a pain, and how
# The lead advisor would put it. The answer alone ("True. I am not satisfied.") loses
# what he is not satisfied with.
STATEMENTS = [
    ('willing to settle', 'True', 'not willing to settle where things are'),
    ('practice bank account balances', 'True',
     'not satisfied with the practice bank balances'),
    ('should be making more', 'True', 'should be making more for the work'),
    ('too much time working on the business', 'True',
     'too much time on the business side'),
    ('no one dental-specific', 'True', 'no one dental-specific to talk to'),
    ('plan in place that connects', 'False',
     'no plan connecting the practice to retirement'),
    ('saving enough to meet', 'False', 'not saving enough for retirement'),
    ('personal bank account balances', 'True',
     'unhappy with the personal bank balances'),
]


def own_words(form_path, form=None):
    """The form's answers that name a problem, in short form."""
    out = []
    # A scanned form has been read already: its statements arrive as pairs.
    if form and form.get('_statements'):
        for pair in form['_statements']:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            stmt, ans = str(pair[0]), str(pair[1]).strip()
            for key, pain, short in STATEMENTS:
                if key in stmt and ans.startswith(pain) and short not in out:
                    out.append(short)
        return out
    if not form_path or not form_path.lower().endswith('.eml'):
        return []
    lines = [l.strip() for l in _form_text(form_path).splitlines() if l.strip()]
    for i, line in enumerate(lines[:-1]):
        nxt = lines[i + 1]
        for key, pain, short in STATEMENTS:
            if key in line and nxt.startswith(pain + '.') and short not in out:
                out.append(short)
        if 'tried to improve my practice with' in line and \
                not re.match(r'(True|False)\b', nxt):
            tried = ', '.join(x.strip() for x in nxt.split(';') if x.strip())
            if tried and ('has tried ' + tried) not in out:
                out.append('has tried ' + tried)
    return out


def _pct(v):
    return None if v is None else '%.1f%%' % (v * 100 if v <= 1.5 else v)


def _last(by_year):
    ys = [y for y in sorted(by_year) if by_year.get(y) is not None]
    return (ys[-1], by_year[ys[-1]]) if ys else (None, None)


def call_needs(folder):
    """What the Otter call summaries say the client needs and objects to.

    Otter's summary carries labelled lines ("Need", "Objections",
    "Competition") as a heading on one line and the answer on the next.
    """
    import glob
    import os
    out = []
    if not folder:
        return out
    paths = []
    for pat in ('*.pages', '*/*.pages', '*/*/*.pages'):
        paths += glob.glob(os.path.join(folder, pat))
    try:
        import iwork
    except ImportError:
        return out
    for p in sorted(set(paths)):
        if 'otter' not in os.path.basename(p).lower():
            continue
        try:
            lines = [l.strip() for l in iwork.text_of(p).splitlines()]
        except Exception:
            continue
        for head in ('Need', 'Objections', 'Competition'):
            for i, l in enumerate(lines[:-1]):
                if l == head and lines[i + 1]:
                    out.append((head, lines[i + 1], os.path.basename(p)))
                    break
    return out


def themes(form, form_path, p, t, latest, series, fee, debt_head, folder=None):
    """[(theme, evidence or None, source)] in the order the lead advisor lists them."""
    s = {name: vals for name, vals, _fmt in series}
    out = []

    words = own_words(form_path, form)
    # A pain note is a phrase, not a name: Casey writes "PAIN 1) Kelly" to
    # say whose pain follows, and that line alone says nothing.
    said = [str(x).strip() for x in (form.get('_pain') or [])
            if len(str(x).split()) >= 3]
    if form.get('_challenges'):
        said.append('top challenges: %s' % ', '.join(
            x.strip(' .') for x in str(form['_challenges']).splitlines()
            if x.strip()))
    calls = call_needs(folder)
    for head, line, _src in calls:
        if head == 'Need':
            said.append('on the call: %s' % line)
    allw = said + words
    out.append(('Dentist pain, their words',
                '; '.join(allw) if allw else None,
                'IC form, Casey\'s notes and call summary' if allw else
                'Add from the initial call'))
    for head, line, src in calls:
        if head in ('Objections', 'Competition'):
            out.append(('%s (call)' % head, line, src))

    # Retirement
    bits = []
    if (form.get('retire_basis') or '').strip().lower() in ('guess', 'a guess'):
        bits.append('target %s was a guess' % (form.get('retire_target') or '?'))
    if form.get('saved_liquid'):
        bits.append('liquid if walking away today: "%s"' % form['saved_liquid'])
    for w in words:
        if 'retirement' in w:
            bits.append(w)
    if bits:
        out.append(('Retirement planning', '; '.join(bits), 'IC form'))

    # Overhead
    pnl_oh, tax_oh = p.get('overhead_pct'), t.get('overhead_pct')
    if pnl_oh or tax_oh:
        bits = []
        if pnl_oh:
            bits.append('%s on the %s P&L' % (_pct(pnl_oh / 100.0), latest))
        if tax_oh:
            bits.append('%s on the return' % _pct(tax_oh / 100.0))
        if form.get('overhead_stated'):
            stated = str(form['overhead_stated']).strip()
            bits.append('client thinks %s' % (stated if stated.endswith('%') else stated + '%'))
        out.append(('OH improvements', ', '.join(bits) +
                    '. Target is the advisor\'s call.', 'P&L, return, IC form'))

    # Practice efficiencies: only the ones that are off
    eff = []
    y, col = _last(s.get('collection %', {}))
    if col is not None and col < 0.98:
        eff.append('collect %% %s (%s)' % (_pct(col), y))
    y, adj = _last(s.get('production adjustment %', {}))
    if adj is not None and adj > 0.05:
        eff.append('adjust %% %s (%s)' % (_pct(adj), y))
    y, hyg = _last(s.get('hygiene % of production', {}))
    if hyg is not None and hyg < 0.25:
        eff.append('hygiene %s of production (%s)' % (_pct(hyg), y))
    nps = s.get('new patients', {})
    # Full years only. The current year is a year to date, and "660 to 371"
    # compared twelve months of Oyler's with seven.
    import datetime
    this_year = str(datetime.date.today().year)
    full = [yy for yy in sorted(nps) if nps.get(yy) and yy < this_year]
    if len(full) >= 2 and nps[full[-2]] and nps[full[-1]] < nps[full[-2]]:
        eff.append('new patients %s to %s (%s to %s)'
                   % (format(nps[full[-2]], ','), format(nps[full[-1]], ','),
                      full[-2], full[-1]))
    if eff:
        out.append(('Practice efficiencies', ', '.join(eff),
                    'Practice Analysis and counts'))

    # Fees
    pct, _txt = fee or (None, None)
    if pct is not None:
        if pct < 0:
            out.append(('Fee increase', 'fees %.1f%% below the benchmark'
                        % abs(pct), 'fee study'))
        else:
            out.append(('Fees', 'already %.1f%% above the benchmark, so no '
                        'fee lever' % pct, 'fee study'))

    # Debt
    if debt_head:
        out.append(('Debt structuring', debt_head, 'debt schedule'))

    # Books
    bits = []
    if p and not p.get('depreciation_amort'):
        bits.append('no depreciation/amortisation booked on the %s P&L' % latest)
    if pnl_oh and tax_oh and abs(pnl_oh - tax_oh) >= 3:
        bits.append('P&L and return %.1f points apart' % abs(pnl_oh - tax_oh))
    if bits:
        out.append(('QB improvements, not tying to taxes', '; '.join(bits),
                    'P&L and return'))

    # Tax and CPA
    bits = []
    sur = (form.get('tax_surprise') or '').strip()
    if sur.lower().startswith('yes'):
        bits.append('surprises: %s' % sur[:160])
    rating = (form.get('cpa_rating') or '').strip()
    if rating and rating.lower() not in ('good', 'great', 'excellent'):
        bits.append('CPA rated %s' % rating)
    if bits:
        out.append(('Tax management / CPA', '; '.join(bits), 'IC form'))

    out.append(('Comprehensive plan, biz/personal',
                'business decisions drive the personal plan', 'every plan'))
    out.append(('Fee range', None, 'Advisor'))
    out.append(('Timeline', None, 'Advisor'))
    return out
