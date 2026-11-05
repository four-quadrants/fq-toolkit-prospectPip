#!/usr/bin/env python3
"""Where a client's .json working files live.

    python3 store.py "<client folder>" notes.json     # print where it lives
    python3 store.py "<client folder>" --sweep        # move this client's in
    python3 store.py "<year folder>" --sweep-all      # move every client's in

WHY
The .json files are the toolkit's working memory (the LaunchBay pull, the
checklist verdicts, Claude's readings, the review decisions). Nobody opens
them, and kept in the client folder they bury the documents the team does
open. So they all live in one folder beside the clients:

    Prospects/2026/Claude outputs/notes_Example, Jane.json

Same file name as before, with _<client> added. The client is the folder
name without its "due 11:6" date, so a folder later moved into
"2.) Signed" keeps finding its files.

OLD LOCATIONS
A file still sitting in the client folder or its _Audit (an older client, or
written there by a Claude skill) is moved in the first time it is asked for,
when it is newer than the one already here. Nothing else changes for the
caller: every module asks json_path() and gets one path to read and write.
"""
import os
import re
import shutil
import sys

OUT_DIR = 'Claude outputs'
_YEAR = re.compile(r'^\d{4}$')
_DUE = re.compile(r'\s+due\s+\d{1,2}[:/]\d{1,2}\s*$', re.I)


def client_folder(folder):
    """The client folder, given it, its _Audit or its documents folder."""
    folder = os.path.abspath(folder.rstrip('/'))
    while os.path.basename(folder) in ('_Audit', 'Original_sourcedocs', 'Documents'):
        folder = os.path.dirname(folder)
    return folder


def client_name(folder):
    """'Example, Jane due 11:6 ' -> 'Example, Jane'."""
    name = _DUE.sub('', os.path.basename(client_folder(folder))).strip()
    return name.replace(':', '-').replace('/', '-')


def year_folder(folder):
    """The Prospects/<year> folder above the client (its parent if none)."""
    folder = client_folder(folder)
    up = folder
    while True:
        parent = os.path.dirname(up)
        if parent == up:
            return os.path.dirname(folder)
        if _YEAR.match(os.path.basename(parent)):
            return parent
        up = parent


def out_dir(folder):
    return os.path.join(year_folder(folder), OUT_DIR)


def _legacy(folder, name):
    folder = client_folder(folder)
    return [os.path.join(folder, '_Audit', name), os.path.join(folder, name)]


def _mtime(p):
    try:
        return os.path.getmtime(p)
    except OSError:
        return None


def json_path(folder, name):
    """Where <name> lives for this client; old copies are moved in first."""
    stem, ext = os.path.splitext(os.path.basename(name))
    target = os.path.join(out_dir(folder), '%s_%s%s' % (stem, client_name(folder), ext))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    here = _mtime(target)
    for old in _legacy(folder, os.path.basename(name)):
        t = _mtime(old)
        if t is None or (here is not None and t <= here):
            continue
        try:
            shutil.move(old, target)
        except OSError:
            shutil.copy2(old, target)
        here = _mtime(target)
    return target


def find(folder, pattern):
    """Read-only: the paths of this client's .json files matching a name
    pattern ('claude_checklist.json', 'review_page*.json'), here or in the
    old places. Moves nothing and creates nothing (the prospect board uses it)."""
    import glob
    stem, ext = os.path.splitext(pattern)
    hits = glob.glob(os.path.join(glob.escape(out_dir(folder)),
                                  '%s_%s%s' % (stem, glob.escape(client_name(folder)), ext)))
    for old in _legacy(folder, pattern):
        hits += glob.glob(os.path.join(glob.escape(os.path.dirname(old)), os.path.basename(old)))
    return hits


def sweep(folder):
    """Move every .json from this client's folder and _Audit; list what moved."""
    folder = client_folder(folder)
    moved = []
    for d in (folder, os.path.join(folder, '_Audit')):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith('.json') and not f.startswith('.'):
                json_path(folder, f)
                moved.append(os.path.join(os.path.basename(d), f))
    return moved


def main():
    a = sys.argv[1:]
    if len(a) == 2 and a[1] == '--sweep':
        for m in sweep(a[0]):
            print('moved', m)
        print('into', out_dir(a[0]))
    elif len(a) == 2 and a[1] == '--sweep-all':
        for c in sorted(os.listdir(a[0])):
            p = os.path.join(a[0], c)
            if os.path.isdir(p) and not re.match(r'^(\d|_|\.)', c) and c != OUT_DIR:
                n = len(sweep(p))
                print('%-40s %d moved' % (c, n))
    elif len(a) == 2:
        print(json_path(a[0], a[1]))
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
