#!/usr/bin/env python3
"""Claude drafts the client-specific prose the deck still lacks.

After deck_template has filled every slide it can from the numbers, what is
left is prose an advisor would write: the tax red flags, the income structure,
where the investments stand, the fee wording. This asks Claude for all of it
in one go, from a fact pack built from the client's own files, on the team
seat (ask_claude refuses if an API key is set).

THE RULES THE DRAFTS ARE HELD TO
    Every figure in a draft must already be in the fact pack. A draft quoting
    a number that is not there is thrown away and the slot stays a grey
    placeholder, so nothing invented reaches a client.
    The template's own words are from another client's deck. Claude sees them
    only as a guide to length and tone and is told not to reuse their facts.
    Drafts are cached on the fact pack, so a rebuild with nothing new costs
    nothing and gives the same words. A new document changes the pack and
    asks again.
    The presenter notes on each slide say which boxes were drafted, so the
    advisor knows what to read before the meeting.
"""
import json
import os
import re

try:
    import ask_claude
except ImportError:  # pragma: no cover
    ask_claude = None

HERE = os.path.dirname(os.path.abspath(__file__))
STYLE = os.path.join(HERE, 'deck_style.md')
TIMEOUT = 900

SKIP = {'folder', 'proj', 'proj2', 'gains', 'gains_proposed'}


def _round(v):
    if isinstance(v, float):
        return round(v, 4) if abs(v) < 10 else round(v, 0)
    if isinstance(v, dict):
        return {k: _round(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_round(x) for x in v]
    return v


def fact_pack(D, extra=None):
    """The figures and facts the drafts may use, as one JSON-ready dict."""
    pack = {k: _round(v) for k, v in D.items() if k not in SKIP}
    for key in ('proj', 'proj2'):
        p = D.get(key) or {}
        ry = str(p.get('retire_year', ''))
        if ry:
            pack[key + '_at_retirement'] = {
                path: _round((p.get(path) or {}).get(ry))
                for path in ('current', 'proposed', 'fq') if p.get(path)}
    pack['lever_gains'] = [
        {'label': g.get('label'), 'gain': _round(g.get('gain')),
         'basis': g.get('basis')} for g in (D.get('gains_proposed') or [])]
    if extra:
        pack.update(extra)
    return pack


def _extra(folder):
    """Due diligence findings and Brogan's decisions, when they exist."""
    out = {}
    for name, key in (('review_decisions.json', 'brogan_decisions'),
                      ('ic_form.json', 'intake_form')):
        p = os.path.join(folder, '_Audit', name)
        try:
            with open(p) as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if key == 'intake_form':
            data = {k: v for k, v in data.items()
                    if not k.startswith('_') or k in ('_statements',
                                                      '_challenges', '_pain')}
        out[key] = data
    try:
        import duediligence
        out['due_diligence'] = [
            {k: f.get(k) for k in ('topic', 'question', 'why') if f.get(k)}
            for f in duediligence.findings(folder)][:25]
    except Exception:  # noqa: BLE001 - the drafts do without it
        pass
    return out


NUM = re.compile(r'(?<![A-Za-z])\$?(\d[\d,]*\.?\d*)\s*(k|K|m|M|million|'
                 r'billion|%)?')


def _numbers(text):
    vals = []
    for m in NUM.finditer(text):
        raw, unit = m.group(1).rstrip('.').replace(',', ''), m.group(2) or ''
        try:
            v = float(raw)
        except ValueError:
            continue
        if unit in ('k', 'K'):
            v *= 1e3
        elif unit in ('m', 'M', 'million'):
            v *= 1e6
        vals.append((v, unit == '%', m.group(0)))
    return vals


def _pack_numbers(pack_text):
    out = set()
    for v, pct, _raw in _numbers(pack_text):
        out.add(v)
        if not pct and 0 < abs(v) < 1.5:
            out.add(round(v * 100, 2))  # 0.74 in the pack is 74% on a slide
    return out


def grounded(text, known):
    """Every figure in the draft is in the pack, give or take rounding."""
    for v, _pct, raw in _numbers(text):
        if v <= 12 or 1990 <= v <= 2100:
            continue  # counts, ages in single digits, years
        if not any(abs(v - k) <= max(0.015 * abs(k), 0.6) for k in known):
            return False, raw
    return True, None


PROMPT = """You are drafting the client-specific text for a Four Quadrants
consult deck for {names}, a dental practice owner. The deck is built from a
template; most boxes are already filled from the numbers. The boxes listed
under HOLES still need text.

For each hole you see: the slide number, the slide's heading, the box id, and
the words that box held in a different client's deck, with figures shown as #.
The example tells you what the box is for (a red flag, a monthly figure, a
label) and how long it runs. Write this client's version of it. NEVER reuse
the example's facts; a figure must come from the FACT PACK.

STYLE
{style}

HARD RULES
- Use only facts and figures that appear in the FACT PACK. Do not compute new
  figures except simple rounding ($1,105,645 may be $1.1M).
- If the pack does not support a hole, return null for it. A null is better
  than a guess; the advisor fills it.
- Keep each draft at or under the example's length.
- No em dashes. Plain sentences. Address the client as "you" where the
  example does.

Reply with JSON only: {{"drafts": {{"<box id>": "text or null", ...}}}}

HOLES
{holes}

FACT PACK
{pack}
"""


def _style():
    try:
        with open(STYLE) as fh:
            return fh.read().strip()
    except OSError:
        return ''


def draft(folder, D, holes, log=print):
    """holes: list of dicts {id, slide, heading, example}. Returns {id: text}.

    Anything that cannot be drafted is simply absent from the result, and the
    caller leaves the placeholder in place.
    """
    if not holes or ask_claude is None:
        return {}
    pack = fact_pack(D, _extra(folder))
    pack_text = json.dumps(pack, default=str, indent=0)
    hole_text = '\n'.join(
        '- id {id} | slide {slide} "{heading}" | example: {example}'.format(**h)
        for h in holes)
    prompt = PROMPT.format(names=D.get('names') or 'the client',
                           style=_style(), holes=hole_text, pack=pack_text)
    cache = os.path.join(folder, '.fq_cache', 'drafts')
    try:
        got = ask_claude.ask_json(prompt, cache_dir=cache, timeout=TIMEOUT,
                                  allow=())
    except Exception as exc:  # noqa: BLE001 - no Claude, no drafts
        log('  drafts skipped: %s' % exc)
        return {}
    drafts = (got or {}).get('drafts') or {}
    known = _pack_numbers(pack_text)
    out, refused = {}, []
    ids = {h['id'] for h in holes}
    for k, text in drafts.items():
        if k not in ids or not isinstance(text, str) or not text.strip():
            continue
        text = text.replace('—', ', ').replace('–', '-').strip()
        ok, bad = grounded(text, known)
        if ok:
            out[k] = text
        else:
            refused.append((k, bad))
    log('  Claude drafted %d of %d boxes%s'
        % (len(out), len(holes),
           '; %d set aside for a figure not on file (%s)'
           % (len(refused), ', '.join(b for _k, b in refused[:4]))
           if refused else ''))
    return out
