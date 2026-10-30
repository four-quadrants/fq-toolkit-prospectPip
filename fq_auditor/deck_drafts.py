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
import glob
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
    """Due diligence findings and the lead advisor’s decisions, when they exist."""
    out = {}
    for name, key in (('review_decisions.json', 'advisor_decisions'),
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
        if (v <= 12 and not _pct) or 1990 <= v <= 2100:
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

THE CLIENT'S DOCUMENTS
Text extracts of the returns and investment statements. Read the ones you
need, the way an advisor would before writing these slides: for the tax
slide, look for what the lead advisor looks for (books vs return, depreciation and
fixed assets, owner health insurance, the state pass-through entity tax
election, meals and travel, when the returns were filed, balances owed or
refunded); for the investment slides, holdings, returns and liquidity.
{docs}

HARD RULES
- Use only facts and figures that appear in the FACT PACK or in the
  documents above. Do not compute new
  figures except simple rounding ($1,105,645 may be $1.1M).
- If neither supports a hole, return null for it. A null is better
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


SKIP_DOC = re.compile(r'\bK-?1\b|_K1_|EF Forms|PreparerFileCopy|\.png$', re.I)


def documents(folder, first=''):
    """The returns and statements a draft may quote, as (name, text file,
    text). The text files are the toolkit's own extracts, so Claude reads
    plain text rather than rendering a 90-page PDF, and the same text is what
    the figures are checked against."""
    import extract
    orig = os.path.join(folder, 'Original_sourcedocs')
    try:
        rows = extract.extract_folder(orig, progress=False)
    except Exception:  # noqa: BLE001
        return []
    cache = os.path.join(orig, '.fq_cache')
    # One entry per document, however many copies arrived (a zip unpacked
    # beside the same files sent singly). The copy whose name was filed
    # ("Personal - Taxes - ...") is the one that says what it is.
    best = {}
    for m in rows:
        k = m.get('sha256') or m['file']
        low = m['file'].lower()
        score = ('taxes' in low or 'investments' in low, len(low))
        if k not in best or score > best[k][0]:
            best[k] = (score, m)
    taxes, other = [], []
    for _score, m in best.values():
        name = m['file']
        if SKIP_DOC.search(name):
            continue
        txt = extract._cache_paths(cache, m['sha256'])[0]
        if not os.path.exists(txt):
            continue
        low = name.lower()
        if re.search(r'instructions|payments due|voucher|e-?file|signature|'
                     r'filing instructions|\.zip$', low):
            continue
        # What the document is, from its text first: a file called "DDS
        # Taxes Acct Statement" is a bank statement, and one called
        # "..._1040_Tax Returns.pdf" is a return whatever its name says.
        try:
            import classify as _cl
            kind = (_cl.classify(m.get('text') or '') or {}).get('doc_type') or ''
        except Exception:  # noqa: BLE001
            kind = ''
        is_return = kind.endswith('tax_return') or (
            not kind and re.search(r'tax returns?|(?<![a-z])(1040|1120s?|1065)(?![0-9])', low))
        if is_return:
            # Children's returns are not the client's tax story.
            if 'personal returns' in low and first and \
                    first.lower() not in low.split('personal returns')[-1][:40]:
                continue
            taxes.append((name, txt, m.get('text') or ''))
        elif 'investments' in low:
            other.append((name, txt, m.get('text') or ''))
    return taxes + other


def _where_free(text, folder):
    """The prompt with the client folder's own path taken out, so the same
    question asked on another machine (the share mounts differently on each
    Mac) finds the same answer."""
    base = re.escape(os.path.basename(os.path.normpath(folder)))
    return re.sub(r'/[^\n]*?/' + base, '<client>', text)


def _cached(cache, prompt, folder):
    """An answer already given to this question, from any machine."""
    want = _where_free(prompt, folder)
    try:
        names = sorted(os.listdir(cache))
    except OSError:
        return None
    for n in names:
        try:
            with open(os.path.join(cache, n)) as fh:
                hit = json.load(fh)
        except (OSError, ValueError):
            continue
        if _where_free(hit.get('prompt') or '', folder) == want:
            m = ask_claude.JSON_BLOCK.search(hit.get('answer') or '')
            try:
                return json.loads(m.group(0)) if m else None
            except ValueError:
                return None
    return None


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
    docs = documents(folder, D.get('first') or '')
    doc_text = '\n'.join('- %s: read %s' % (n, t) for n, t, _x in docs) \
        or '(none)'
    prompt = PROMPT.format(names=D.get('names') or 'the client',
                           style=_style(), holes=hole_text, pack=pack_text,
                           docs=doc_text)
    cache = os.path.join(folder, '.fq_cache', 'drafts')
    got = _cached(cache, prompt, folder)
    if got is None:
        try:
            got = ask_claude.ask_json(
                prompt, cache_dir=cache, timeout=TIMEOUT,
                allow=('Read',) if docs else (),
                add_dirs=(os.path.join(folder, 'Original_sourcedocs',
                                       '.fq_cache'),) if docs else ())
        except Exception as exc:  # noqa: BLE001 - no Claude, no drafts
            prev = _load(os.path.join(folder, '_Audit', 'deck_drafts.json'))
            if prev:
                log('  Claude not available here; using the drafts from the '
                    'last build (%d boxes)' % len(prev))
                return {h['id']: prev[h['id']] for h in holes if prev.get(h['id'])}
            log('  drafts skipped: %s' % exc)
            return {}
    drafts = (got or {}).get('drafts') or {}
    known = _pack_numbers(pack_text + '\n'.join(x for _n, _t, x in docs))
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
    _save(os.path.join(folder, '_Audit', 'deck_drafts.json'), out)
    log('  Claude drafted %d of %d boxes%s'
        % (len(out), len(holes),
           '; %d set aside for a figure not on file (%s)'
           % (len(refused), ', '.join(b for _k, b in refused[:4]))
           if refused else ''))
    return out


INCOME_PROMPT = """From this dental practice owner's tax returns, read four figures
for the most recent year on file that has BOTH the personal return and the
practice return (all four figures from that one year). Read the text files
listed; they are extracts of the returns and statements.

{docs}

Return JSON only:
{{"year": 2025,
  "w2": <the owner's W-2 wages from the practice, Form 1120-S officer
         compensation or the W-2>,
  "deferral": <the owner's own 401(k) elective deferral for a year: W-2 box
         12 code D if a W-2 is on file; otherwise the 401(k) statement's
         employee contributions, annualized (six months x 2), not the
         employer match>,
  "total_tax": <federal total tax from the personal Form 1040 plus the state
         income tax from the state return, for the same year>,
  "distributions": <distributions to the owner from the S corporation for the
         year (Schedule K-1 line 16 D, or Schedule M-2)>,
  "sources": {{"w2": "file and line", "deferral": "...", "total_tax": "...",
              "distributions": "..."}}}}
Use null for any figure you cannot find. Never estimate."""


def income_facts(folder, first=''):
    """The four figures the income structure slide needs, read from the
    returns by Claude, each checked against the documents' own text. Cached
    like the drafts. {} when Claude is not available."""
    docs = [d for d in documents(folder, first)
            if 'investments' not in d[0].lower()]
    saved = os.path.join(folder, '_Audit', 'income_facts.json')
    if not docs or ask_claude is None:
        return _load(saved)
    prompt = INCOME_PROMPT.format(
        docs='\n'.join('- %s: read %s' % (n, t) for n, t, _x in docs))
    cache = os.path.join(folder, '.fq_cache', 'drafts')
    got = _cached(cache, prompt, folder)
    if got is None:
        try:
            got = ask_claude.ask_json(
                prompt, cache_dir=cache, timeout=TIMEOUT, allow=('Read',),
                add_dirs=(os.path.join(folder, 'Original_sourcedocs',
                                       '.fq_cache'),))
        except Exception:  # noqa: BLE001
            # No Claude on this machine: what the last build on one that has
            # it read, if anything.
            return _load(saved)
    got = got or {}
    known = _pack_numbers('\n'.join(x for _n, _t, x in docs))
    out = {'year': got.get('year'), 'sources': got.get('sources') or {}}
    for k in ('w2', 'deferral', 'total_tax', 'distributions'):
        v = got.get(k)
        if isinstance(v, str):
            try:
                v = float(v.replace('$', '').replace(',', ''))
            except ValueError:
                v = None
        if isinstance(v, (int, float)) and v > 0:
            # total tax is a sum of two figures, so it is checked by parts
            # only when it is not itself on the page
            if k == 'total_tax' or any(abs(v - n) <= 1 for n in known):
                out[k] = float(v)
    _save(saved, out)
    return out


def _load(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save(path, data):
    try:
        with open(path, 'w') as fh:
            json.dump(data, fh, indent=1)
    except OSError:
        pass


RETURNS_PROMPT = """Read these investment statements for a dental practice owner and,
for each account below, give its return as the statements show it.

ACCOUNTS (use these labels exactly)
{labels}

STATEMENTS
{docs}

For each account: the return over the longest period the statements state or
let you compute from beginning value, ending value and net contributions, as
an annualized percent, and the dates it covers. An account with no statement
of its own may be measured with another account holding the same investments
(say which). Return JSON only:
{{"accounts": [{{"label": "...", "return_pct": -3.2, "period": "10/1/25-9/30/26",
   "measured_with": null or "the other account's label", "basis": "where it came from"}}]}}
Use null for return_pct when it cannot be found. Never estimate."""


def account_returns(folder, labels, first=''):
    """{label: {return_pct, period, measured_with, basis}} from the investment
    statements, read by Claude and cached like the drafts."""
    saved = os.path.join(folder, '_Audit', 'account_returns.json')
    # The same statements the account reader uses, so the returns are read
    # from the documents the balances came from.
    import accounts as _acc
    docs = []
    for rep in _acc.find_statements(folder):
        text = _acc._text(folder, rep)
        hits = sorted(glob.glob(os.path.join(folder, '.fq_cache', rep['sha'] + '*.txt')) +
                      glob.glob(os.path.join(folder, 'Original_sourcedocs', '.fq_cache',
                                             rep['sha'] + '*.txt')))
        hits = [h for h in hits if not h.endswith('.credit.txt')]
        docs.append((rep['name'], hits[-1] if hits and text else rep['path'], text))
    if not docs or not labels or ask_claude is None:
        return _load(saved)
    prompt = RETURNS_PROMPT.format(
        labels='\n'.join('- ' + l for l in labels),
        docs='\n'.join('- %s: read %s' % (n, t) for n, t, _x in docs))
    cache = os.path.join(folder, '.fq_cache', 'drafts')
    got = _cached(cache, prompt, folder)
    if got is None:
        try:
            got = ask_claude.ask_json(
                prompt, cache_dir=cache, timeout=TIMEOUT, allow=('Read',),
                add_dirs=sorted({os.path.dirname(t) for _n, t, _x in docs}))
        except Exception:  # noqa: BLE001
            return _load(saved)
    out = {}
    for a in (got or {}).get('accounts') or []:
        if a.get('label') in labels:
            r = a.get('return_pct')
            out[a['label']] = {'return_pct': r if isinstance(r, (int, float)) else None,
                               'period': a.get('period'),
                               'measured_with': a.get('measured_with'),
                               'basis': a.get('basis')}
    _save(saved, out)
    return out
