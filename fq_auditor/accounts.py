#!/usr/bin/env python3
"""Investment accounts: what each statement says the household holds.

    python3 accounts.py "<client folder>"        # read and print

Fills the Assumptions' sections 4 (qualified) and 5 (non-qualified) and the
deck's starting portfolio and investments slides. Until this existed those
were typed into the input store by hand, which is why only Oyler had them.

Claude reads the statements filed under Documents/Personal/Investments (and
any file whose name says Investments), on the team seat, and returns one row
per account from its newest statement: owner, custodian, type, last four
digits, value, the statement date and what it holds in a sentence. Every
value is checked against the statement's own text where there is text.

A person's entry wins: when the store already holds accounts that someone
typed or corrected, this writes nothing. It only refreshes what it wrote
itself, and only when the statements change.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import inputs as _inputs                                  # noqa: E402

BY = 'read from statements (Claude)'
SAVED = os.path.join('_Audit', 'accounts.json')
TIMEOUT = 900
QUALIFIED = re.compile(r'401|403|457|ira|roth|sep|simple|pension|profit sharing|'
                       r'defined benefit|cash balance', re.I)
KIND = re.compile(r'investments?\b|401\s?\(?k|403\s?\(?b|457|\bira\b|roth|\bsep\b|'
                  r'simple ira|\bhsa\b|brokerage|529|schwab|fidelity|vanguard|'
                  r'valic|corebridge|edward jones|ameriprise|t\.?\s?rowe|vestwell|'
                  r'ascensus|empower|principal|annuity|healthequity|coinbase|'
                  r'drivewealth|morgan stanley|merrill|raymond james|lpl|annuit|'
                  r'security national|policy statement|cash value', re.I)
EXCLUDED = re.compile(r'\bhsa\b|529|health savings', re.I)


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def find_statements(folder):
    paths = glob.glob(os.path.join(folder, 'Documents', '*', 'Investments', '**', '*'),
                      recursive=True)
    # Statements filed somewhere else, or not filed at all (Rebol's VALIC
    # 403(b) was never filed; his HSA went under Banking): by what the name
    # says the account is or who holds it.
    paths += [p for p in glob.glob(os.path.join(folder, 'Original_sourcedocs', '*'))
              if KIND.search(os.path.basename(p))]
    paths += [p for p in glob.glob(os.path.join(folder, 'Documents', '**', '*'),
                                   recursive=True)
              if KIND.search(os.path.basename(p))]
    seen, out = set(), []
    for p in sorted(paths):
        if not os.path.isfile(p) or '/.' in p:
            continue
        name = os.path.basename(p)
        if re.search(r'valuation|notes?\.docx|debt|\.qbb$|credit report|'
                     r'tax return|1040|1120|w-?2\b|1099|\.png$', name, re.I):
            continue
        try:
            d = _sha(p)
        except OSError:
            continue
        if d in seen:
            continue
        seen.add(d)
        out.append({'path': p, 'sha': d, 'name': name})
    return out


def _text(folder, rep):
    for cache in (os.path.join(folder, '.fq_cache'),
                  os.path.join(folder, 'Original_sourcedocs', '.fq_cache')):
        hits = sorted(glob.glob(os.path.join(cache, rep['sha'] + '*.txt')))
        hits = [h for h in hits if not h.endswith('.credit.txt')]
        if hits:
            try:
                return open(hits[-1], errors='replace').read()
            except OSError:
                pass
    return ''


PROMPT = """These are a dental practice owner's household investment statements.
List every account they show, ONE row per account, from that account's NEWEST
statement.

{files}

For each account return:
  owner (first name), custodian (e.g. Edward Jones, Vestwell), type (401k,
  403b, Traditional IRA, Roth IRA, SEP IRA, SIMPLE IRA, Brokerage, 529, HSA,
  Crypto, Private placement, Cash value life, Other), last4 (account digits,
  or null), value (total account value on the statement, as printed),
  as_of (statement end date, MM/DD/YYYY), holds (one short sentence: how many
  funds or positions and the rough mix, e.g. "Seven mutual funds, about 60%
  stocks and 40% bonds"), source (the file you took it from).
Copy values exactly. Use null when not shown. Never estimate.
Return JSON only: {{"accounts": [{{...}}]}}"""


def read(folder, log=print, use_claude=True):
    reps = find_statements(folder)
    key = sorted(r['sha'] for r in reps)
    saved_path = os.path.join(folder, SAVED)
    try:
        with open(saved_path) as fh:
            saved = json.load(fh)
        if saved.get('key') == key:
            return saved
    except (OSError, ValueError):
        pass
    if not reps or not use_claude:
        return None
    lines, texts, dirs = [], [], set()
    cache = os.path.join(folder, 'Original_sourcedocs', '.fq_cache')
    for r in reps:
        t = _text(folder, r)
        if t and len(re.sub(r'\s', '', t)) > 200:
            hit = sorted(glob.glob(os.path.join(folder, '.fq_cache', r['sha'] + '*.txt')) +
                         glob.glob(os.path.join(cache, r['sha'] + '*.txt')))
            lines.append('- %s: read %s' % (r['name'], hit[-1]))
            dirs.add(os.path.dirname(hit[-1]))
            texts.append(t)
        else:
            lines.append('- %s: read the file itself %s' % (r['name'], r['path']))
            dirs.add(os.path.dirname(r['path']))
    import ask_claude
    try:
        got = ask_claude.ask_json(PROMPT.format(files='\n'.join(lines)),
                                  cache_dir=os.path.join(folder, '.fq_cache', 'accounts'),
                                  timeout=TIMEOUT, allow=('Read',), add_dirs=sorted(dirs))
    except Exception as exc:  # noqa: BLE001
        log('  accounts not read: %s' % exc)
        return None
    flat = ' '.join(texts).replace(',', '')
    rows = []
    for a in (got or {}).get('accounts') or []:
        v = a.get('value')
        try:
            v = float(str(v).replace('$', '').replace(',', '')) if v is not None else None
        except ValueError:
            v = None
        checked = v is not None and ('%.2f' % v in flat or str(int(v)) in flat)
        rows.append(dict(a, value=v, checked=checked))
    out = {'key': key, 'accounts': rows}
    try:
        with open(saved_path, 'w') as fh:
            json.dump(out, fh, indent=1)
    except OSError:
        pass
    return out


def label(a):
    who = (a.get('owner') or '').strip().title()
    kind = a.get('type') or 'Account'
    tail = ' x%s' % a['last4'] if a.get('last4') else ''
    cust = re.sub(r'\s*\((?:advisor|adviser|via)[^)]*\)', '', a.get('custodian') or '?')
    return '%s %s [%s%s]' % (who, kind, cust, tail)


def ensure(folder, log=print):
    """Fill sections 4 and 5 in the input store from the statements, unless
    a person has already filled them."""
    for key in ('qualified_accounts', 'nonqualified_accounts'):
        got = _inputs.get(folder, key)
        if got and got.get('value') and got.get('by') != BY:
            return False
    got = read(folder, log=log)
    if not got or not got.get('accounts'):
        return False
    # One spelling per person: statements say "Chris" on one and
    # "Christopher" on the next; the shorter, as the family uses it.
    firsts = [(a.get('owner') or '').split()[0] for a in got['accounts']
              if (a.get('owner') or '').split()]
    short = {}
    for f in firsts:
        for g in firsts:
            if g.lower().startswith(f.lower()[:4]) and len(g) < len(short.get(f, f)):
                short[f] = g
    for a in got['accounts']:
        w = (a.get('owner') or '').split()
        if w and '&' not in a.get('owner'):
            a['owner'] = short.get(w[0], w[0])
    q, n = [], []
    for a in got['accounts']:
        if a.get('value') is None:
            continue
        row = {'label': label(a), 'value': a['value'],
               'basis': 'per the %s statement of %s; %s' % (
                   a.get('custodian') or 'account', a.get('as_of') or '?',
                   (a.get('holds') or '').rstrip('.')) +
               ('' if a.get('checked') else ' (value not found in the statement text: check)')}
        if EXCLUDED.search(a.get('type') or ''):
            row['excluded'] = True
            n.append(row)
        elif QUALIFIED.search(a.get('type') or ''):
            q.append(row)
        else:
            n.append(row)
    note = 'Claude, from %d statement(s)' % len(got.get('key') or [])
    # Written only when something changed: every step that reads the
    # portfolio calls this, and a rewrite of the same figures would make the
    # Assumptions look older than its own inputs (an orange dot for nothing).
    for key, rows in (('qualified_accounts', q), ('nonqualified_accounts', n)):
        if rows and (_inputs.value(folder, key) or []) != rows:
            _inputs.put(folder, key, rows, by=BY, note=note)
    return True


def main():
    ap = argparse.ArgumentParser(description='Investment accounts from the statements')
    ap.add_argument('folder')
    a = ap.parse_args()
    ensure(a.folder)
    for key in ('qualified_accounts', 'nonqualified_accounts'):
        print(key)
        for r in _inputs.value(a.folder, key) or []:
            print('   %-50s %12s  %s' % (r['label'][:50], '{:,.0f}'.format(r['value'] or 0),
                                       r.get('basis', '')[:80]))


if __name__ == '__main__':
    main()
