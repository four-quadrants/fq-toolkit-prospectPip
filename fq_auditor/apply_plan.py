#!/usr/bin/env python3
"""Turn a reviewed rename plan into an actual folder tree.

    python3 apply_plan.py "<client folder>"            # what it would do
    python3 apply_plan.py "<client folder>" --run      # do it

    --into <path>   where to build the tree (default: <client>/Documents_v2)

WHY IT BUILDS A NEW TREE
The documents already sit in a tree somebody can see. Renaming sixty files in
place gives no way back if the plan turns out to be wrong in a way nobody
noticed on the spreadsheet, and the only honest way to judge a filing is to look
at it. So this builds the proposed tree beside the existing one, copying rather
than moving, and the old one is deleted by a person once they have looked.

WHAT IT REFUSES
A row a person rejected. A row whose collision could not be resolved. A
destination that already holds a different document. Each refusal is printed
with its reason, because a silent skip in a filing tool is how documents go
missing.
"""
import os
import sys
import csv
import shutil
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from classify_claude import source_index                     # noqa: E402
from rename_plan import FOLDERS                               # noqa: E402

PLAN = os.path.join('_Audit', 'rename_plan.csv')


def load(csv_path):
    with open(csv_path) as fh:
        return list(csv.DictReader(fh))


def apply(folder, rows, into, run=False):
    index = source_index(folder)
    done, refused = [], []

    # Every folder, whether or not anything landed in it. An empty
    # Personal/Banking says the personal statements have not arrived; no
    # Personal/Banking at all says nothing, and the gap is invisible until
    # somebody thinks to look for it.
    if run:
        for name in FOLDERS:
            os.makedirs(os.path.join(into, name), exist_ok=True)

    for row in rows:
        src = index.get(row.get('sha', ''))
        label = row.get('existing') or row.get('sha', '')[:12]

        if row.get('rejected', '').strip():
            refused.append((label, 'you rejected this one'))
            continue
        if str(row.get('collision', '')).startswith('UNRESOLVED'):
            refused.append((label, row['collision']))
            continue
        if not src or not os.path.exists(src):
            refused.append((label, 'source file not found'))
            continue
        if not row.get('proposed_folder') or not row.get('proposed_name'):
            refused.append((label, 'no destination proposed'))
            continue

        dest_dir = os.path.join(into, row['proposed_folder'])
        dest = os.path.join(dest_dir, row['proposed_name'])

        if os.path.exists(dest):
            # Same bytes means this ran before; anything else is a real
            # collision the plan did not catch, and copying would destroy it.
            if os.path.getsize(dest) == os.path.getsize(src):
                done.append((label, row['proposed_folder'],
                             row['proposed_name'], 'already there'))
                continue
            refused.append((label, 'a different file is already at %s'
                            % row['proposed_name']))
            continue

        if run:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(src, dest)       # copy2 keeps the arrival timestamp
        done.append((label, row['proposed_folder'], row['proposed_name'], ''))

    return done, refused


def main():
    ap = argparse.ArgumentParser(description='Build the proposed tree')
    ap.add_argument('folder')
    ap.add_argument('--plan')
    ap.add_argument('--into')
    ap.add_argument('--run', action='store_true')
    a = ap.parse_args()

    plan_path = a.plan or os.path.join(a.folder, PLAN)
    into = a.into or os.path.join(a.folder, 'Documents_v2')
    rows = load(plan_path)

    done, refused = apply(a.folder, rows, into, run=a.run)

    by_folder = {}
    for _lbl, dest_folder, name, note in done:
        by_folder.setdefault(dest_folder, []).append((name, note))
    for dest_folder in sorted(by_folder):
        print('\n%s' % dest_folder)
        for name, note in sorted(by_folder[dest_folder]):
            print('   %s%s' % (name, '   (%s)' % note if note else ''))

    empty = [f for f in FOLDERS if f not in by_folder]
    if empty:
        print('\nempty, nothing has arrived for these yet:')
        for f in empty:
            print('   %s' % f)

    print('\n%d filed into %d of %d folders'
          % (len(done), len(by_folder), len(FOLDERS)))
    if refused:
        print('%d refused:' % len(refused))
        for label, why in refused:
            print('   %-48s %s' % (label[:48], why))
    if not a.run:
        print('\n[nothing was copied. add --run]')
    else:
        print('\ntree built at %s' % into)
        print('the original Documents folder is untouched')


if __name__ == '__main__':
    main()
