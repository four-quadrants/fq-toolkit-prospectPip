#!/usr/bin/env python3
"""Every active prospect, where it stands, and what to do next.

    python3 prospects.py "<Prospects/2026>"                    # every client folder
    python3 prospects.py "<Prospects/2026>" --hide "Lamberti"  # minus the ones removed
    python3 prospects.py "<Prospects/2026>" --folders          # just the folder names

WHO IS ON THE LIST
Every client folder at the top of the year folder: the team makes one at the
initial call. Folders moved into "1.) Not moving forward" or "2.) Signed"
(anything starting with a digit, "_" or ".") are left off. The analyst
removes the ones they know are gone on their "My Prospects" page in Claude;
Claude passes those in with --hide. A LaunchBay project with no folder never
appears.

WHERE EACH ONE STANDS
Read from what is in the folder: the team's own files (IC form, consult offer
notes, the Expanded List, the ACH form) and the toolkit's (the LaunchBay pull,
the intake, the initial notes, the cash flow, the deck). A matching _TEST copy
counts too. Claude adds what LaunchBay says (new uploads or comments since the
last pull, the project's stage) before drawing the board; this script never
calls LaunchBay.

Read-only: it lists files and reads two small JSON files, nothing else.
"""
import argparse
import glob
import json
import os
import store as _store  # noqa: E402
import re
import sys
from datetime import date

SKIP = re.compile(r'^(\d|_|\.|%s$)' % re.escape(_store.OUT_DIR))


def _has(folder, *patterns):
    for p in patterns:
        if glob.glob(os.path.join(glob.escape(folder), p)):
            return True
    return False


def _docs_count(folder):
    n = 0
    for sub in ('Original_sourcedocs', 'Documents', '3.) Documents'):
        d = os.path.join(folder, sub)
        if os.path.isdir(d):
            for root, dirs, files in os.walk(d):
                dirs[:] = [x for x in dirs if not x.startswith(('.', '_'))]
                n += sum(1 for f in files if not f.startswith('.'))
            if n:
                return n
    return n


def _name(folder_name):
    """'Burgin, Daniel Due 10:30 ' -> ('Burgin, Daniel', '10/30')."""
    s = folder_name.strip()
    m = re.search(r'\s+due\s+(\d{1,2})[:/](\d{1,2})\s*$', s, re.I)
    due = None
    if m:
        due = '%s/%s' % (m.group(1), m.group(2))
        s = s[:m.start()].strip()
    return s, due


def _surname(name):
    return re.split(r'[,\s(]', name.strip())[0].lower()


def _pulled(folder):
    for p in _store.find(folder, 'launchbay_manifest.json'):
        try:
            return (json.load(open(p)).get('pulled') or None)
        except (OSError, ValueError):
            continue
    return None


def status(year_folder, folder_name, tests):
    folder = os.path.join(year_folder, folder_name)
    name, due = _name(folder_name)
    test = tests.get(_surname(name))
    where = [folder] + ([test] if test else [])

    def any_has(*p):
        return any(_has(f, *p) for f in where)

    def any_json(*names):
        return any(_store.find(f, n) for f in where for n in names)

    s = {
        'name': name,
        'folder': folder_name,
        'due': due,
        'test_copy': os.path.basename(test) if test else None,
        'ic_form': _has(folder, 'IC form*', '*IC form*'),
        'documents': max(_docs_count(f) for f in where),
        'pulled': next((p for p in (_pulled(f) for f in where) if p), None),
        'intake': any_json('claude_checklist.json') or any_has('_Audit/*Internal Audit.md'),
        'notes': any_has('Initial notes - *.xlsx', '_Audit/Initial notes*.xlsx'),
        'team_notes': _has(folder, 'intial notes*', 'initial notes-*.numbers'),
        'offer_call': _has(folder, '*onsult offer*'),
        'expanded': _has(folder, 'Expanded list*', 'Expanded List*'),
        'ach': _has(folder, 'ACH Form*', 'ACH form*'),
        'cashflow': any_has('*Cash flow*.numbers') or any_json('bank_statements.json'),
        'assumptions': any_json('assumptions*.json', 'review_page*.json'),
        'deck': any_has('Consult deck*.pptx', '*Consult deck*.pptx'),
    }
    s['stage'], s['next'] = _stage(s)
    return s


def _stage(s):
    """(stage label, [(button, what it sends)]). Claude refines with LaunchBay."""
    n = s['name'].split(',')[0]
    accepted = s['expanded'] or s['ach']
    if s['deck']:
        return 'Stage 3 · deck built', [
            ('Check the deck', "Open %s's consult deck and tell me what still needs a human check." % n)]
    if s['assumptions']:
        return 'Stage 3 · review', [
            ('Load the review', "Load %s's review." % n),
            ('Pull in my check', "Pull in my check for %s." % n),
            ('New answers came in', "Refresh %s's review with the new answers and documents." % n)]
    if accepted:
        if s['cashflow']:
            return 'Stage 2 · cash flow done', [
                ('Build assumptions', "Build %s's assumptions." % n)]
        return 'Stage 2 · consult accepted', [
            ('Run the intake', "Run %s's intake for the expanded documents and show me what is still open." % n),
            ('Build assumptions', "Build %s's assumptions." % n)]
    if s['notes'] or s['team_notes']:
        return 'Stage 1 · notes done', [
            ('He accepted the consult', "%s accepted the consult. What do I do next?" % n),
            ('Show open items', "Show me %s's open items." % n),
            ('Update initial notes', "Update %s's initial notes with anything new." % n)]
    if s['intake']:
        return 'Stage 1 · intake done', [
            ('Show open items', "Show me %s's open items so I can pick what we need before the consult offer call." % n),
            ('Build initial notes', "Build %s's initial notes." % n)]
    if s['documents'] or s['pulled']:
        return 'Stage 1 · documents in', [
            ('Run the intake', "Run %s's intake." % n)]
    return 'Stage 1 · waiting on documents', [
        ('Check LaunchBay', "Pull %s from LaunchBay and tell me what has come in." % n)]


def _folders(year_folder):
    return sorted(f for f in os.listdir(year_folder)
                  if not SKIP.match(f) and os.path.isdir(os.path.join(year_folder, f)))


def _match(folders, word):
    w = word.strip().lower().replace(' due', '')
    hits = [f for f in folders if w in f.lower()] or \
           [f for f in folders if _surname(_name(f)[0]) == _surname(w)]
    return hits[0] if len(hits) == 1 else None


def board(year_folder, hide=()):
    tests = {}
    tdir = os.path.join(year_folder, '_TEST')
    if os.path.isdir(tdir):
        for t in os.listdir(tdir):
            if os.path.isdir(os.path.join(tdir, t)) and not t.startswith(('.', '_')):
                tests.setdefault(_surname(t), os.path.join(tdir, t))
    folders = _folders(year_folder)
    hidden = {f for f in (_match(folders, w) for w in hide) if f}
    out = [status(year_folder, f, tests) for f in folders if f not in hidden]
    return {'year_folder': year_folder, 'read_on': date.today().isoformat(),
            'prospects': out, 'hidden': sorted(hidden)}


def main():
    ap = argparse.ArgumentParser(description='Where every active prospect stands')
    ap.add_argument('year_folder', help='the Prospects/<year> folder')
    ap.add_argument('--hide', action='append', default=[],
                    help='a prospect removed from the board (repeat for each)')
    ap.add_argument('--folders', action='store_true')
    a = ap.parse_args()
    if not os.path.isdir(a.year_folder):
        sys.exit('No such folder: %s' % a.year_folder)
    if a.folders:
        print(json.dumps({'folders': _folders(a.year_folder)}, indent=1))
        return
    print(json.dumps(board(a.year_folder, a.hide), indent=1))


if __name__ == '__main__':
    main()
