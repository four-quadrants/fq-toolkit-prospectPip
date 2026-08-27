"""The per-client ledger — what we have seen, what we filed, what we asked for.

Intake is not a one-shot job. A client sends half of what was requested, you sort
it, and the rest arrives a week later. Without a memory of the first pass the
second one re-litigates all of it: documents already filed get proposed again,
and the client gets asked for things they already sent.

The ledger is one JSON file per client, at <client>/_Audit/ledger.json. It records:

    documents  sha256 -> first seen, last seen, name(s) used, where it was filed
    checklist  item id -> status each run, and when it first went satisfied
    runs       a short history: when, how many documents, what changed

Keyed by SHA-256 of file CONTENTS throughout, for the same reason decisions are:
filenames change, and this has to survive both renaming and filing.

Nothing here decides anything. It answers three questions the audit cannot
answer on its own — is this document new, has it already been filed, and has
this checklist item been outstanding since last time — and leaves the judgement
to the code that asked.
"""
import os
import json
import datetime

LEDGER_NAME = 'ledger.json'
VERSION = 1


def path_for(outdir):
    return os.path.join(outdir, LEDGER_NAME)


def load(outdir):
    """The ledger as it stands, or an empty one on the first run."""
    p = path_for(outdir)
    if os.path.exists(p):
        try:
            with open(p) as fh:
                data = json.load(fh)
            if isinstance(data, dict) and data.get('version'):
                data.setdefault('documents', {})
                data.setdefault('checklist', {})
                data.setdefault('runs', [])
                return data
        except Exception:
            # A corrupt ledger must not stop an audit. Start a fresh one and let
            # the old file sit there; losing history is bad, losing the run is worse.
            pass
    return {'version': VERSION, 'documents': {}, 'checklist': {}, 'runs': []}


def save(outdir, led):
    os.makedirs(outdir, exist_ok=True)
    tmp = path_for(outdir) + '.tmp'
    with open(tmp, 'w') as fh:
        json.dump(led, fh, indent=1, sort_keys=True)
    os.replace(tmp, path_for(outdir))       # atomic, so a crash cannot truncate it
    return path_for(outdir)


def _today():
    return datetime.date.today().isoformat()


def observe(led, docs):
    """Record this run's documents. Returns the hashes that are NEW.

    A document is new the first time its contents are seen, no matter what it is
    called. A renamed copy of something already recorded is not new.
    """
    new = []
    today = _today()
    for d in docs:
        sha = d.get('sha256')
        if not sha:
            continue
        rec = led['documents'].get(sha)
        if rec is None:
            led['documents'][sha] = {
                'first_seen': today,
                'last_seen': today,
                'names': [d.get('file')],
                'doc_type': d.get('doc_type'),
                'filed_to': None,
                'filed_on': None,
                'filed_as': None,
            }
            new.append(sha)
        else:
            rec['last_seen'] = today
            rec['doc_type'] = d.get('doc_type') or rec.get('doc_type')
            name = d.get('file')
            if name and name not in rec.get('names', []):
                rec.setdefault('names', []).append(name)
    return new


def is_filed(led, sha):
    rec = led['documents'].get(sha or '')
    return bool(rec and rec.get('filed_to'))


def filed_where(led, sha):
    rec = led['documents'].get(sha or '')
    if not rec or not rec.get('filed_to'):
        return None
    return {'to': rec['filed_to'], 'as': rec.get('filed_as'), 'on': rec.get('filed_on')}


def record_filed(led, sha, dest, filed_as):
    rec = led['documents'].setdefault(sha, {'first_seen': _today(), 'names': []})
    rec['filed_to'] = dest
    rec['filed_as'] = filed_as
    rec['filed_on'] = _today()
    return rec


def update_checklist(led, results):
    """Track each checklist item across runs.

    Returns (newly_satisfied, still_outstanding, outstanding_since) so the run can
    say what CHANGED rather than restating the whole list. Chasing a client is
    about the delta.
    """
    today = _today()
    newly_satisfied, still_outstanding, since = [], [], {}
    for r in results:
        item = r.get('item') or {}
        iid = item.get('id') or item.get('label')
        if not iid:
            continue
        status = r.get('status')
        rec = led['checklist'].setdefault(iid, {
            'label': item.get('label'), 'section': item.get('section'),
            'first_seen': today, 'status': None, 'satisfied_on': None,
            'outstanding_since': today, 'history': [],
        })
        was = rec.get('status')
        if was != status:
            rec['history'].append({'on': today, 'from': was, 'to': status})
        rec['status'] = status
        rec['label'] = item.get('label') or rec.get('label')

        if status == 'satisfied':
            if was != 'satisfied':
                rec['satisfied_on'] = today
                newly_satisfied.append(rec['label'] or iid)
            rec['outstanding_since'] = None
        else:
            if not rec.get('outstanding_since'):
                rec['outstanding_since'] = today
            still_outstanding.append(rec['label'] or iid)
            since[rec['label'] or iid] = rec['outstanding_since']
    return newly_satisfied, still_outstanding, since


def record_run(led, n_docs, n_new, counts):
    led['runs'].append({
        'on': _today(),
        'documents': n_docs,
        'new': n_new,
        'satisfied': counts.get('satisfied', 0),
        'missing': counts.get('missing', 0),
        'mismatched': counts.get('mismatched', 0),
    })
    led['runs'] = led['runs'][-50:]          # a history, not an archive
    return led


def summarise(led, new_hashes, newly_satisfied, still_outstanding, since):
    """What a human wants to read at the end of a second or third pass."""
    L = []
    first_run = len(led.get('runs', [])) <= 1
    if first_run:
        L.append('First pass for this client — everything here is new.')
        return L

    L.append('%d new document(s) since the last run.' % len(new_hashes))
    if newly_satisfied:
        L.append('Now satisfied: ' + '; '.join(newly_satisfied[:6])
                 + (' …' if len(newly_satisfied) > 6 else ''))
    filed = sum(1 for r in led['documents'].values() if r.get('filed_to'))
    L.append('%d of %d document(s) have already been filed.'
             % (filed, len(led['documents'])))
    if still_outstanding:
        stale = [(lbl, since.get(lbl)) for lbl in still_outstanding if since.get(lbl)]
        stale.sort(key=lambda x: x[1] or '')
        if stale and stale[0][1]:
            L.append('Longest outstanding: "%s", since %s.' % (stale[0][0], stale[0][1]))
    return L
