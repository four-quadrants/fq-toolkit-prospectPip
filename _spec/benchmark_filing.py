#!/usr/bin/env python3
"""Score the tool's filing against a tree a person filed by hand.

    python3 benchmark_filing.py "<hand-filed tree>" "<tool-filed tree>"
    python3 benchmark_filing.py ... --json baseline.json

WHY THIS EXISTS FIRST
We are about to replace the classifier. Nothing about that is worth doing on an
opinion, so this produces a number for how good the current rules are before a
line of it changes. The same script then scores whatever replaces them, against
the same tree, and the two numbers can be put side by side.

HOW IT MATCHES
By content, never by name. A document the client re-sent under a different
filename is the same document, and the whole point of the tool is that filenames
carry no authority. Two files with the same bytes are the same document.

WHAT IT REPORTS
  - placed the same way a person placed it
  - placed somewhere else (with both paths, so the disagreement can be read)
  - in one tree only (usually just documents added since the audit ran)

Folder names are compared loosely on purpose. "Banking/x4728" and "Banking/4782"
are the same decision about what kind of document it is, and differ only in how
the account was written down -- which is worth seeing, but is not a filing
mistake.
"""
import os
import re
import sys
import json
import hashlib
import argparse
from collections import defaultdict


def digest(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


SKIP_DIRS = {'.fq_cache', '.fq_ocr', '_Audit', '_Withdrawn', '_Converted',
             'Original_sourcedocs', '__MACOSX'}


def walk(root):
    """{digest: [relative paths]} for every real file under a tree."""
    out = defaultdict(list)
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs
                   if d not in SKIP_DIRS and not d.startswith('.')]
        for name in files:
            if name.startswith('.') or name.startswith('~$'):
                continue
            full = os.path.join(dirpath, name)
            try:
                out[digest(full)].append(os.path.relpath(full, root))
            except OSError:
                continue
    return out


def norm_folder(rel):
    """A folder path reduced to the decision it represents.

    Strips the numbering people put on folders ("3.) Documents"), lowercases,
    collapses whitespace, and drops the x from an account folder so that
    "x4728" and "4728" compare equal.
    """
    parts = []
    for part in os.path.dirname(rel).split(os.sep):
        part = re.sub(r'^\s*\d+[.)]\s*', '', part)        # "3.) Documents"
        part = re.sub(r'^x(?=\d{3,})', '', part.strip())  # "x4728" -> "4728"
        part = re.sub(r'\s+', ' ', part).strip().lower()
        if part:
            parts.append(part)
    return '/'.join(parts)


def category(folder, depth=2):
    """The first levels of a folder path: the broad call, not the detail."""
    return '/'.join(folder.split('/')[:depth])


def compare(truth_root, tool_root):
    truth, tool = walk(truth_root), walk(tool_root)
    same, moved, only_truth, only_tool = [], [], [], []

    for h, paths in sorted(tool.items()):
        tool_path = paths[0]
        if h not in truth:
            only_tool.append(tool_path)
            continue
        truth_path = truth[h][0]
        tf, lf = norm_folder(truth_path), norm_folder(tool_path)
        rec = {'document': os.path.basename(tool_path),
               'hand_filed': os.path.dirname(truth_path),
               'tool_filed': os.path.dirname(tool_path)}
        if tf == lf:
            same.append(rec)
        else:
            rec['same_category'] = category(tf) == category(lf)
            moved.append(rec)

    for h, paths in sorted(truth.items()):
        if h not in tool:
            only_truth.append(paths[0])

    matched = len(same) + len(moved)
    return {
        'matched': matched,
        'same_folder': len(same),
        'different_folder': len(moved),
        'same_category_only': sum(1 for m in moved if m['same_category']),
        'wrong_category': sum(1 for m in moved if not m['same_category']),
        'accuracy_folder': round(100.0 * len(same) / matched, 1) if matched else None,
        'accuracy_category': round(
            100.0 * (len(same) + sum(1 for m in moved if m['same_category']))
            / matched, 1) if matched else None,
        'only_in_hand_filed': len(only_truth),
        'only_in_tool_filed': len(only_tool),
        'disagreements': moved,
        'unmatched_tool': only_tool,
    }


def main():
    ap = argparse.ArgumentParser(description='Score filing against a human tree')
    ap.add_argument('truth', help='the hand-filed tree')
    ap.add_argument('tool', help='the tool-filed tree')
    ap.add_argument('--json', help='write the full result here')
    a = ap.parse_args()

    r = compare(a.truth, a.tool)
    if a.json:
        with open(a.json, 'w') as fh:
            json.dump(r, fh, indent=1)

    print('matched by content        %d' % r['matched'])
    print('  filed the same way      %d   (%s%%)'
          % (r['same_folder'], r['accuracy_folder']))
    print('  filed somewhere else    %d' % r['different_folder'])
    print('     right category       %d   (so %s%% got the broad call right)'
          % (r['same_category_only'], r['accuracy_category']))
    print('     wrong category       %d' % r['wrong_category'])
    print('in the hand-filed tree only  %d' % r['only_in_hand_filed'])
    print('in the tool tree only        %d' % r['only_in_tool_filed'])
    if r['disagreements']:
        print('\nwhere they disagree')
        for m in r['disagreements']:
            print('  %-54s' % m['document'][:54])
            print('      person: %s' % m['hand_filed'])
            print('      tool:   %s%s' % (m['tool_filed'],
                                          '' if m['same_category']
                                          else '   <-- wrong category'))


if __name__ == '__main__':
    main()
