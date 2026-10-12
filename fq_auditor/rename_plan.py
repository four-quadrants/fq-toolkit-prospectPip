#!/usr/bin/env python3
"""Propose a folder and a name for every document, and move nothing.

    python3 rename_plan.py "<client folder>"            # what it would ask
    python3 rename_plan.py "<client folder>" --run      # ask, write the plan
    python3 rename_plan.py "<client folder>" --csv out.csv

WHY NAMING AND FILING ARE ONE QUESTION
Both need the same read: the institution, the product, the last four, the
period, whose it is. Asking twice would be asking the same document the same
thing twice and risking two different answers.

WHY THE FOLDERS ARE FLAT
The subfolders were carrying information the filenames should carry. An account
folder named x4728 holding a file named "04 Apr 30 2026 Civista Cking Stmt" puts
the account number and the product in two different places, neither of which
survives the file being moved or attached to an email. Flat folders with
complete names survive both.

That makes the last four mandatory on a statement, which NAMING.md section 4 did
not require while the folder carried it. It is the one rule the flattening
changes.

NOTHING IS MOVED
This writes a plan. A person reads it, and the filing step executes whatever
survives that reading. A tool that renames sixty documents on its own judgement
is a tool nobody runs twice.
"""
import os
import re
import sys
import csv
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import classify                                              # noqa: E402
import ask_claude                                            # noqa: E402
from classify_claude import (source_index, CLAUDE_CAN_OPEN,   # noqa: E402
                             CACHE, CLASSIFY_CACHE)

# Flat. Every folder a document can land in, and nothing below them.
FOLDERS = [
    'Business/Banking', 'Business/Credit Cards', 'Business/Debt',
    'Business/Financials', 'Business/Taxes', 'Business/Payroll',
    'Business/Production', 'Business/Fees', 'Business/Associate Info',
    'Business/Insurance', 'Business/Valuation', 'Business/Misc',
    'Personal/Banking', 'Personal/Credit Cards', 'Personal/Debt',
    'Personal/Investments', 'Personal/Taxes',
    'Personal/Insurance', 'Personal/Pay Info', 'Personal/Credit Reports',
    'Personal/Misc',
]

CONVENTION = """NAMING, from the firm's standing convention:

  statements      [Person] <Kind> (<Institution>) x<last4> <YYYY-MM>.pdf
                  Kind is Chk, Sav, MM, HYSA, CD, CC, Brok, IRA, Roth, 401k,
                  403b, 457, 529 or HSA, read from beside the account number.
                  Annual statements use <YYYY> instead of <YYYY-MM>.
  wage and tax    [Person] <Type> <YYYY>.pdf
                  e.g. Brian W-2 2024.pdf, Personal tax return 2024.pdf,
                  Business tax return 2025.pdf
  practice        <Type> <YYYY-MM>.pdf or <Type> <YYYY>.pdf
                  e.g. P&L 2025.pdf, Payroll summary 2026-02.pdf. No person.
  one-offs        [Person] <Type> [YYYY].pdf
                  e.g. Lease.pdf, Fee schedule 2026.pdf, Staff roster.pdf

  A person's name appears ONLY on a document that belongs to one person: W-2,
  paystub, personal brokerage or retirement, personal insurance, credit report.
  Never on a joint return, never on an S-corp return, never on anything
  belonging to the practice.

  The last four is REQUIRED on any account statement, because the folders are
  flat and nothing else carries it.

  A period is REQUIRED on anything that arrives as a run: statements, payroll,
  W-2s, paystubs, tax returns, P&L, balance sheets. If it is required and you
  cannot read it, write "(year TBD)" rather than inventing one.

  Keep the file's existing extension."""

SCHEMA = """{
  "folder": "one of the folders listed, copied exactly",
  "filename": "the new name including extension, following the convention",
  "keep_existing_name": true or false,
  "doc_type": "what the document is, in a word or two",
  "period": "YYYY-MM or YYYY or null",
  "account_last4": "four digits or null",
  "person": "the one person it belongs to, or null",
  "evidence": "the words on the page that told you, quoted",
  "confidence": "high, medium or low"
}"""

# A product word in the client's own name that the proposal lacks means the
# client knew something the reader did not. NAMING.md records this catching 15
# files on one corpus: "Cap 1 HYSA March.pdf" was about to become a checking
# account.
PRODUCT_WORDS = ('hysa', 'money market', 'roth', 'ira', '401k', '403b', '457',
                 '529', 'hsa', 'brokerage', 'savings', 'checking', 'cd')


def build_prompt(text, folders, source_path):
    ext = os.path.splitext(source_path or '')[1].lower()
    readable = ext in CLAUDE_CAN_OPEN
    hint = ' '.join(text.split())[:1200 if readable else 6000]
    if readable:
        body = ('Our text extraction reads:\n"""%s"""\n\nRead the file itself '
                'as well; the text above is only a hint.' % hint)
    else:
        body = ('This is a %s file, which you cannot open directly. Our '
                'extraction is reliable for this format, so judge from the '
                'text below:\n"""%s"""' % (ext, hint))
    return """You are filing and naming documents for a dental practice financial advisory firm.

DOCUMENT: %s
EXISTING NAME: %s

%s

Choose one folder, copied exactly:
%s

%s

Reply with only JSON:
%s

Rules:
- Choose a folder from the list. Do not invent one.
- Set keep_existing_name true only if the existing name already follows the
  convention. A name that is merely descriptive is not enough.
- If the existing name contains a product word your new name does not, say so
  in evidence. The client often knows the product better than the page does.
- Quote the actual words on the page in evidence. Do not paraphrase.
- Low confidence is a useful answer. A wrong confident name is worse.""" % (
        source_path or '(unknown)', os.path.basename(source_path or ''),
        body, '\n'.join('  ' + f for f in folders), CONVENTION, SCHEMA)


def guardrail(existing, proposed):
    """Flag a proposal that drops a product word the client's name carried."""
    low_old, low_new = existing.lower(), (proposed or '').lower()
    for word in PRODUCT_WORDS:
        if word in low_old and word not in low_new:
            return word
    return None


# Words that distinguish two copies of the same document, in the order we would
# rather use them. Read off the client's own filename, because the page itself
# usually does not say which copy it is.
COPY_WORDS = [('preparerfilecopy', 'preparer copy'), ('clientcopy', 'client copy'),
              ('(practice)', 'practice'), ('(provider)', 'provider'),
              ('preparer', 'preparer copy'), ('client', 'client copy'),
              ('copy', 'copy')]


def deduplicate(plan):
    """Make every proposed path unique, or refuse to propose it.

    Two documents proposed into one name is the only outcome here that destroys
    something: the second move overwrites the first and the original is gone.
    It happened three times on sixty-two documents -- a client copy and a
    preparer copy of the same return, and two production reports.

    The fix is to find what the client's own filenames knew that the proposal
    dropped. "ClientCopy" and "PreparerFileCopy" distinguish the pair; so do
    "(Practice)" and "(Provider)". Where nothing distinguishes them, the name is
    left alone and flagged, because a numbered suffix hides the duplicate rather
    than resolving it.
    """
    seen = {}
    for row in plan:
        row['collision'] = ''
    for row in plan:
        dest = '%s/%s' % (row['proposed_folder'], row['proposed_name'])
        seen.setdefault(dest, []).append(row)

    for dest, rows in seen.items():
        if len(rows) < 2:
            continue
        for row in rows:
            old = row['existing'].lower()
            tag = next((label for token, label in COPY_WORDS if token in old),
                       None)
            if not tag:
                row['collision'] = 'no way to tell these apart; left as-is'
                continue
            stem, ext = os.path.splitext(row['proposed_name'])
            row['proposed_name'] = '%s (%s)%s' % (stem, tag, ext)
            row['collision'] = 'renamed to avoid overwriting a sibling'

    # Whatever is still shared could not be resolved, so nothing moves there.
    final = {}
    for row in plan:
        dest = '%s/%s' % (row['proposed_folder'], row['proposed_name'])
        final.setdefault(dest, []).append(row)
    for dest, rows in final.items():
        if len(rows) > 1:
            for row in rows:
                row['proposed_name'] = row['existing']
                row['collision'] = ('UNRESOLVED: %d documents wanted this name'
                                    % len(rows))
    return plan


def documents(folder):
    """Every document, with its cached text and what the rules made of it."""
    import glob
    out = []
    for path in sorted(glob.glob(os.path.join(folder, CACHE, '*.txt'))):
        text = open(path, errors='replace').read()
        if len(text.strip()) < 40:
            continue
        out.append({'cache_file': path, 'text': text,
                    'rules_said': classify.classify(text).get('doc_type')})
    return out


def main():
    ap = argparse.ArgumentParser(description='Propose folders and names')
    ap.add_argument('folder')
    ap.add_argument('--run', action='store_true')
    ap.add_argument('--csv')
    ap.add_argument('--limit', type=int)
    a = ap.parse_args()

    docs = documents(a.folder)
    index = source_index(a.folder)
    if a.limit:
        docs = docs[:a.limit]
    print('%d documents\n' % len(docs))

    if not a.run:
        src = index.get(os.path.basename(docs[0]['cache_file']).split('.')[0])
        print(build_prompt(docs[0]['text'], FOLDERS, src))
        print('\n[dry run. add --run to ask]')
        return

    state = ask_claude.check()
    if not state['ok']:
        print('cannot ask: %s' % state['reason'])
        return

    cdir = os.path.join(a.folder, CLASSIFY_CACHE)
    plan, flagged = [], 0
    for i, doc in enumerate(docs, 1):
        src = index.get(os.path.basename(doc['cache_file']).split('.')[0])
        if not src:
            continue
        existing = os.path.basename(src)
        prompt = build_prompt(doc['text'], FOLDERS, src)
        try:
            ans = ask_claude.ask_json(prompt, cache_dir=cdir,
                                      add_dirs=[os.path.abspath(a.folder)])
        except ask_claude.NotAvailable as exc:
            print('stopped at %d: %s' % (i, exc))
            break
        if not ans:
            print('%3d  %-44s  no usable answer' % (i, existing[:44]))
            continue
        proposed = ans.get('filename') or existing
        if ans.get('keep_existing_name'):
            proposed = existing
        lost = guardrail(existing, proposed)
        if lost:
            flagged += 1
        row = {'sha': os.path.basename(doc['cache_file']).split('.')[0],
               'existing': existing,
               'existing_folder': os.path.relpath(os.path.dirname(src),
                                                  a.folder),
               'proposed_folder': ans.get('folder'),
               'proposed_name': proposed,
               'confidence': ans.get('confidence'),
               'lost_product_word': lost or '',
               'evidence': str(ans.get('evidence') or '')[:200],
               # Yours to fill in. Any text here and filing leaves that
               # document alone, so rejecting one costs a word rather than a
               # conversation.
               'rejected': ''}
        plan.append(row)
        mark = '  <-- drops "%s"' % lost if lost else ''
        print('%3d  %-42s\n     -> %s/%s   (%s)%s'
              % (i, existing[:42], row['proposed_folder'],
                 row['proposed_name'], row['confidence'], mark))

    plan = deduplicate(plan)
    collided = [r for r in plan if r['collision']]
    unresolved = [r for r in plan if r['collision'].startswith('UNRESOLVED')]
    if collided:
        print('\ncollisions found and handled:')
        for r in collided:
            print('  %-42s -> %s' % (r['existing'][:42], r['proposed_name']))
            print('       %s' % r['collision'])

    # Column order is for the person reading it, not for the code. The three
    # columns a reviewer actually uses sit together on the left: what it was,
    # what is proposed, and the box to say no in.
    ORDER = ['existing', 'proposed_folder', 'proposed_name', 'rejected',
             'confidence', 'existing_folder', 'collision',
             'lost_product_word', 'evidence', 'sha']

    out = a.csv or os.path.join(a.folder, '_Audit', 'rename_plan.csv')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', newline='') as fh:
        fields = ([c for c in ORDER if c in plan[0]] +
                  [c for c in plan[0] if c not in ORDER]) if plan else []
        w = csv.DictWriter(fh, fieldnames=fields) if plan else None
        if w:
            w.writeheader()
            w.writerows(plan)
    print('\n%d proposed, %d flagged for dropping a product word, '
          '%d collisions, %d still unresolved' %
          (len(plan), flagged, len(collided), len(unresolved)))
    print('plan written to %s' % out)
    print('nothing has been moved or renamed')


if __name__ == '__main__':
    main()
