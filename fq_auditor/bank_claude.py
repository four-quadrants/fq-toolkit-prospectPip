#!/usr/bin/env python3
"""Bank statements, read by Claude, checked by arithmetic.

    python3 bank_claude.py "<client folder>"        # read anything new, report

Every bank statement on file is read by Claude on the team seat: the bank,
the account's last four digits, whose name it is in, the period, the
beginning and ending balances, the totals in and out, and every
transaction. A reading is used only when it ties out:

    beginning + money in - money out = ending        (to the dollar)
    the transactions add up to the totals in and out (to the dollar)

A statement whose reading does not tie keeps the toolkit's own reading if
that one ties, and otherwise is reported as unreadable rather than counted.
The readings are saved in _Audit/bank_statements.json, one per statement,
keyed on the file's fingerprint, so each statement is read once.

Why Claude first: the toolkit's own reader knows the banks it has been
taught. Spaulding's Huntington statements were a bank it had not seen,
filed under the wrong side and the wrong accounts; it produced figures that
looked plausible and were wrong. A reading that has to balance cannot be
quietly wrong.
"""
import argparse
import concurrent.futures
import datetime
import glob
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SAVED = os.path.join('_Audit', 'bank_statements.json')
VERSION = 1
TIMEOUT = 600
WORKERS = 4

PROMPT = """Read this bank statement exactly. It is one statement for one account
(if the file holds more than one account, read each as its own statement).

FILE: {name}
{how}

Return JSON only:
{{"statements": [{{
  "bank": "Huntington", "account_last4": "5130",
  "holder": "the name(s) the account is in, as printed",
  "business": true or false (true if the holder is a company, practice,
             LLC, PA, PC, DDS etc.; false for a person or a custodian
             account for a child),
  "period_start": "YYYY-MM-DD", "period_end": "YYYY-MM-DD",
  "beginning_balance": 0.00, "ending_balance": 0.00,
  "total_in": 0.00 (all deposits and credits, as the statement totals them),
  "total_out": 0.00 (all withdrawals, checks, debits and fees, positive),
  "transactions": [{{"date": "YYYY-MM-DD", "description": "as printed",
                     "amount": 0.00 (positive), "direction": "in" or "out"}}]
}}]}}
Copy every figure exactly as printed. Include every transaction, checks and
fees too. If the statement prints totals, use them for total_in/total_out.
Never estimate; if something is not printed, use null."""


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def statement_files(folder):
    """Every bank statement: those filed under Documents/*/Banking, and any
    in the client's uploads whose name says it is one."""
    import statements as _st
    paths = glob.glob(os.path.join(folder, 'Documents', '*', 'Banking', '**', '*'),
                      recursive=True)
    raw = os.path.join(folder, 'Original_sourcedocs')
    if os.path.isdir(raw):
        for f in os.listdir(raw):
            stem = os.path.splitext(f)[0]
            if _st.BANKISH.search(stem) and not _st.NOT_BANK.search(stem):
                paths.append(os.path.join(raw, f))
    seen, out = set(), []
    for p in sorted(paths):
        if not os.path.isfile(p) or os.path.basename(p).startswith('.'):
            continue
        if _st.NOT_BANK.search(os.path.basename(p)) or \
                re.search(r'\bhsa\b|healthequity|529|coinbase|crypto|policy|life ins|'
                          r'annuit|credit report|w-?2\b|1099', os.path.basename(p), re.I):
            continue
        if not (_st._is_pdf(p) or p.lower().endswith(('.png', '.jpg', '.jpeg'))):
            continue
        try:
            d = _sha(p)
        except OSError:
            continue
        if d in seen:
            continue
        seen.add(d)
        out.append({'path': p, 'sha': d, 'name': os.path.basename(p)})
    return out


def _text(folder, rep):
    """The statement's text, line by line as laid out on the page, written
    beside the other extracts for Claude to read."""
    import statements as _st
    text = ''
    if _st._is_pdf(rep['path']):
        text = _st.layout_text(rep['path']) or ''
        if len(re.sub(r'\s', '', text)) < 200:
            try:
                import credit as _credit
                text = _credit._ocr(folder, rep) or text
            except Exception:  # noqa: BLE001
                pass
    if not text:
        return None
    cache = os.path.join(folder, 'Original_sourcedocs', '.fq_cache')
    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, rep['sha'] + '.bank.txt')
    with open(path, 'w') as fh:
        fh.write(text)
    return path, text


def _num(v):
    if v in (None, ''):
        return None
    try:
        return round(float(str(v).replace('$', '').replace(',', '')), 2)
    except ValueError:
        return None


def ties(s):
    """(True, '') when the reading balances, else (False, why)."""
    b, e, i, o = (s.get('beginning_balance'), s.get('ending_balance'),
                  s.get('total_in'), s.get('total_out'))
    if None in (b, e):
        return False, 'no beginning or ending balance'
    tx = s.get('transactions') or []
    tin = round(sum(t['amount'] for t in tx if t['direction'] == 'in'), 2)
    tout = round(sum(t['amount'] for t in tx if t['direction'] == 'out'), 2)
    i = tin if i is None else i
    o = tout if o is None else o
    if abs(b + i - o - e) > 1.0:
        return False, 'balances do not tie: %.2f + %.2f - %.2f != %.2f' % (b, i, o, e)
    if tx and (abs(tin - i) > 1.0 or abs(tout - o) > 1.0):
        return False, ('transactions add to %.2f in / %.2f out against totals '
                       'of %.2f / %.2f' % (tin, tout, i, o))
    return True, ''


def _clean(got):
    out = []
    for s in (got or {}).get('statements') or []:
        r = {k: s.get(k) for k in ('bank', 'account_last4', 'holder', 'business',
                                   'period_start', 'period_end')}
        r['account_last4'] = re.sub(r'\D', '', str(r.get('account_last4') or ''))[-4:] or None
        for k in ('beginning_balance', 'ending_balance', 'total_in', 'total_out'):
            r[k] = _num(s.get(k))
        tx = []
        for t in s.get('transactions') or []:
            a = _num(t.get('amount'))
            if a is None:
                continue
            d = 'in' if str(t.get('direction', '')).lower().startswith(('in', 'cr', 'dep')) else 'out'
            tx.append({'date': t.get('date'), 'description': t.get('description') or '',
                       'amount': abs(a), 'direction': d})
        r['transactions'] = tx
        r['ties'], r['why'] = ties(r)
        out.append(r)
    return out


def read_one(folder, rep):
    import ask_claude
    got = _text(folder, rep)
    if got:
        path, text = got
        tag = hashlib.sha1(text.encode('utf-8', 'replace')).hexdigest()[:10]
        how = ('Its text, laid out line by line as on the page, is in %s '
               '(%d characters, version %s). Read that.' % (path, len(text), tag))
        dirs = [os.path.dirname(path)]
    else:
        how = 'Read the file itself: %s' % rep['path']
        dirs = [os.path.dirname(rep['path'])]
    prompt = PROMPT.format(name=rep['name'], how=how)
    answer = ask_claude.ask_json(prompt, cache_dir=os.path.join(folder, '.fq_cache', 'bank'),
                                 timeout=TIMEOUT, allow=('Read',), add_dirs=dirs)
    return _clean(answer)


def _load(folder):
    try:
        with open(os.path.join(folder, SAVED)) as fh:
            got = json.load(fh)
        return got if got.get('v') == VERSION else {'v': VERSION, 'files': {}}
    except (OSError, ValueError):
        return {'v': VERSION, 'files': {}}


def ensure(folder, log=print):
    """Read every statement not read yet. Returns the saved readings."""
    saved = _load(folder)
    todo = [r for r in statement_files(folder) if r['sha'] not in saved['files']]
    if not todo:
        return saved
    try:
        import ask_claude
        if not ask_claude.check()['ok']:
            log('  bank statements: Claude not available here; %d not read' % len(todo))
            return saved
    except Exception:  # noqa: BLE001
        return saved
    log('  Claude is reading %d bank statement%s…' % (len(todo), '' if len(todo) == 1 else 's'))

    def one(rep):
        try:
            return rep, read_one(folder, rep), None
        except Exception as exc:  # noqa: BLE001
            return rep, None, str(exc)
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        for rep, got, err in pool.map(one, todo):
            if got is None:
                log('    %s: not read (%s)' % (rep['name'], err))
                continue
            saved['files'][rep['sha']] = {'name': rep['name'], 'path': rep['path'],
                                          'statements': got}
            bad = [s for s in got if not s['ties']]
            log('    %s: %d statement%s%s' % (rep['name'], len(got), '' if len(got) == 1 else 's',
                                             (', DOES NOT TIE: ' + bad[0]['why']) if bad else ', ties'))
    try:
        with open(os.path.join(folder, SAVED), 'w') as fh:
            json.dump(saved, fh, indent=1)
    except OSError:
        pass
    return saved


def _date(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def as_statements(folder):
    """The readings that tie, in the shape statements.gather returns:
    {(side, 'x1234'): [row, ...]}, plus {sha: True} for the files they
    replace. Transactions ride along on each row as 'claude_tx'."""
    saved = _load(folder)
    out, used = {}, {}
    for sha, f in saved['files'].items():
        # A statement whose balances tie but whose transaction list came back
        # short (a practice account with hundreds of lines: Rebol's First
        # Citizens accounts) is still right on the totals. Its figures are
        # used; its transactions come from the toolkit's own reading.
        for st_ in f['statements']:
            st_['balances_tie'] = st_['ties'] or (
                None not in (st_.get('beginning_balance'), st_.get('ending_balance'),
                             st_.get('total_in'), st_.get('total_out')) and
                abs(st_['beginning_balance'] + st_['total_in'] - st_['total_out'] -
                    st_['ending_balance']) <= 1.0)
        good = [s for s in f['statements'] if s['balances_tie']]
        if not good or len(good) != len(f['statements']):
            continue
        used[sha] = True
        for s in good:
            side = 'Business' if s.get('business') else 'Personal'
            key = (side, 'x' + s['account_last4'] if s.get('account_last4') else '?')
            ends = _date(s.get('period_end'))
            tx = []
            for t in s['transactions']:
                d = _date(t.get('date'))
                tx.append({'date': d, 'month': d.month if d else None,
                           'day': d.day if d else None,
                           'description': t['description'], 'amount': t['amount'],
                           'direction': 'credit' if t['direction'] == 'in' else 'debit'})
            out.setdefault(key, []).append({
                'file': '%s - Banking - %s - %s' % (side, key[1], f['name']),
                'bank': s.get('bank'), 'holder': s.get('holder'),
                'beginning': s['beginning_balance'], 'ending': s['ending_balance'],
                'additions': s.get('total_in') if s.get('total_in') is not None
                else round(sum(t['amount'] for t in s['transactions'] if t['direction'] == 'in'), 2),
                'begins': _date(s.get('period_start')), 'ends': ends,
                'account': s.get('account_last4'), 'side': side,
                'expenses': s.get('total_out'),
                'notes': ['Read by Claude; balances and transactions tie.' if s['ties'] else
                          'Read by Claude; balances tie, transactions read by the toolkit.'],
                'source': f['path'], 'text_path': None,
                'claude_tx': tx if s['ties'] else None})
    return out, used


def main():
    ap = argparse.ArgumentParser(description='Bank statements, read by Claude')
    ap.add_argument('folder')
    a = ap.parse_args()
    saved = ensure(a.folder)
    for sha, f in sorted(saved['files'].items(), key=lambda kv: kv[1]['name']):
        for s in f['statements']:
            print('%-60s %-10s x%-5s %s..%s  %10s -> %10s  in %10s out %10s  %s' % (
                f['name'][:60], (s.get('bank') or '')[:10], s.get('account_last4') or '?',
                s.get('period_start'), s.get('period_end'), s.get('beginning_balance'),
                s.get('ending_balance'), s.get('total_in'), s.get('total_out'),
                'ties' if s['ties'] else 'NO: ' + s['why']))


if __name__ == '__main__':
    main()
