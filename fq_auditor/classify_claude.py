#!/usr/bin/env python3
"""Ask Claude where a document belongs, when the rules could not say.

    python3 classify_claude.py "<client folder>"            # what it would ask
    python3 classify_claude.py "<client folder>" --run      # ask, and save
    python3 classify_claude.py "<client folder>" --all      # every document

WHERE THIS SITS
The rules place most documents. On Oyler they placed 59 of 62 and left 3. This
handles the leftovers, and only the leftovers, which is why it costs almost
nothing: a seat's allowance stretches a long way at three documents a client.

IT READS THE FILE, NOT OUR TEXT OF IT
One of Oyler's three is a photographed page whose OCR came back as "Byay TN
ledoree (dagln bhlkn". Handing that text to anything, human or model, is
pointless. So Claude is given the document's path and reads it itself, with our
extracted text offered only as a hint. The documents that defeat the rules are
disproportionately the ones where our own text is the problem.

THE FOLDER LIST IS THE FIRM'S, NOT A GUESS
Measured against a hand-filed tree, the rules got the broad call right 88.5% of
the time but matched the exact folder only 49%. Almost all of that gap was
structure: tax returns filed per person, bank folders named for the entity
rather than the account. So the prompt carries the firm's own folder list and
asks Claude to choose from it, rather than inventing a path.
"""
import os
import re
import sys
import glob
import json
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import classify                                              # noqa: E402
import ask_claude                                            # noqa: E402

CACHE = '.fq_cache'
CLASSIFY_CACHE = os.path.join(CACHE, 'classify')
CORPUS = '_corpus/classifications.jsonl'

SCHEMA = """{
  "doc_type": "one of: personal_tax_return, business_tax_return, tax_correspondence,
                bank_statement, credit_card_statement, investment_statement,
                retirement_statement, insurance_policy, loan_document,
                debt_schedule, pnl, balance_sheet, payroll, production_report,
                fee_schedule, lease, employment_agreement, client_note, other",
  "owner_side": "Personal or Practice",
  "entity": "whose document it is, as printed on it, or null",
  "year": "the year the document reports on, or null",
  "account_last4": "last four digits of the account, or null",
  "folder": "the folder it belongs in, chosen from the list above",
  "evidence": "the words on the page that told you, quoted",
  "confidence": "high, medium or low"
}"""


def folders_in(tree):
    """The folders a person actually uses, read off their own filing."""
    out = set()
    for dirpath, dirs, _files in os.walk(tree):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        rel = os.path.relpath(dirpath, tree)
        if rel != '.':
            out.add(rel)
    return sorted(out)


def unresolved(folder, everything=False):
    """Documents the rules could not place, with their cached text."""
    cache = os.path.join(folder, CACHE)
    out = []
    for path in sorted(glob.glob(os.path.join(cache, '*.txt'))):
        text = open(path, errors='replace').read()
        if len(text.strip()) < 40:
            continue
        doc = classify.classify(text)
        if not everything and doc.get('doc_type') != 'unknown':
            continue
        out.append({'cache_file': path, 'text': text,
                    'rules_said': doc.get('doc_type'),
                    'rules_year': doc.get('year'),
                    'rules_side': doc.get('owner_side')})
    return out


def source_index(folder):
    """{sha256: path} for every document in a client folder.

    The cache names each extracted text after the sha256 of the file it came
    from, and keeps no map back. So the map is rebuilt by hashing the folder,
    which is also the only way that survives a document being moved or renamed
    after it was read.
    """
    import hashlib
    out = {}
    for dirpath, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for name in files:
            if name.startswith('.') or name.startswith('~$'):
                continue
            path = os.path.join(dirpath, name)
            try:
                h = hashlib.sha256()
                with open(path, 'rb') as fh:
                    for block in iter(lambda: fh.read(1 << 20), b''):
                        h.update(block)
            except OSError:
                continue
            # The filed copy is more useful to a reviewer than the original.
            key = h.hexdigest()
            if key not in out or 'Original_sourcedocs' in out[key]:
                out[key] = path
    return out


def source_for(index, cache_file):
    """The document a cached text came from."""
    return index.get(os.path.basename(cache_file).split('.')[0])


# What Claude Code's file reader can open. Everything else is an office or
# Apple format, and those are structured files our own extraction handles well,
# so there is nothing to convert: send our text instead. The division is almost
# exactly the right one. The formats Claude cannot open are the reliable ones to
# extract; the formats it can open are the scans and photographs where our
# extraction is the weak link.
CLAUDE_CAN_OPEN = {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp',
                   '.txt', '.md', '.csv'}


def build_prompt(doc, folders, source_path):
    ext = os.path.splitext(source_path or '')[1].lower()
    readable = ext in CLAUDE_CAN_OPEN
    # A structured file gets a generous slice of our text, because that text is
    # trustworthy. A scan gets a short hint and an instruction to go and look.
    hint = ' '.join(doc['text'].split())[:6000 if not readable else 1200]
    legible = len(re.findall(r'[A-Za-z0-9]', hint)) / max(len(hint), 1) > 0.55
    return """You are filing documents for a dental practice financial advisory firm.

Read this document and say what it is and where it belongs.

DOCUMENT: %s

%s

The firm files into exactly these folders. Choose one, copied exactly:
%s

Reply with only JSON, no other words:
%s

Rules:
- Choose a folder from the list. Do not invent one.
- If you cannot tell, say confidence "low" and explain in evidence. A wrong
  confident answer is worse than an admitted uncertainty.
- Quote the actual words on the page in evidence. Do not paraphrase.""" % (
        source_path or '(path unknown)',
        _body(hint, readable, legible, ext),
        '\n'.join('  ' + f for f in folders),
        SCHEMA)


def _body(hint, readable, legible, ext):
    """What to put in front of Claude for this kind of file."""
    if not readable:
        return ('This is a %s file, which you cannot open directly. Our '
                'extraction of it is reliable for this format, so judge from '
                'the text below:\n"""%s"""' % (ext or 'office', hint))
    if legible:
        return ('Our text extraction reads:\n"""%s"""\n\nRead the file '
                'itself as well; the text above is only a hint.' % hint)
    return ('Our text extraction of this document came back unreadable, which '
            'usually means it is a photograph or a poor scan. Do not rely on '
            'it. Read the file itself.')


def record(folder, doc, answer, prompt, source_path, corpus_root=None):
    """Write the answer beside the client's other cached reads, and to the
    firm-wide ledger. The ledger is the thing that becomes training data; the
    client copy is only so a re-run costs nothing."""
    stamp = {'client': os.path.basename(folder.rstrip('/')),
             'document': os.path.basename(source_path or doc['cache_file']),
             'path': os.path.dirname(source_path or ''),
             'rules_said': doc['rules_said'],
             'claude_said': answer,
             'human_said': None,
             'asked': time.strftime('%Y-%m-%dT%H:%M:%S'),
             'prompt_chars': len(prompt)}
    cdir = os.path.join(folder, CLASSIFY_CACHE)
    os.makedirs(cdir, exist_ok=True)
    name = os.path.basename(doc['cache_file']).split('.')[0] + '.json'
    with open(os.path.join(cdir, name), 'w') as fh:
        json.dump(stamp, fh, indent=1)
    if corpus_root:
        try:
            ledger = os.path.join(corpus_root, CORPUS)
            os.makedirs(os.path.dirname(ledger), exist_ok=True)
            with open(ledger, 'a') as fh:
                fh.write(json.dumps(stamp) + '\n')
        except OSError:
            pass
    return stamp


def main():
    ap = argparse.ArgumentParser(description='Place what the rules could not')
    ap.add_argument('folder')
    ap.add_argument('--tree', help="a hand-filed tree to take the folder list "
                                   "from (defaults to this client's own)")
    ap.add_argument('--run', action='store_true', help='actually ask Claude')
    ap.add_argument('--all', action='store_true', help='every document, not '
                                                       'just the unresolved')
    ap.add_argument('--corpus', help='root to append the firm-wide ledger to')
    a = ap.parse_args()

    tree = a.tree or os.path.join(a.folder, 'Documents')
    folders = folders_in(tree)
    docs = unresolved(a.folder, everything=a.all)
    index = source_index(a.folder)
    print('%d document%s the rules could not place' %
          (len(docs), '' if len(docs) == 1 else 's'))
    print('%d folders to choose from\n' % len(folders))
    if not docs:
        return

    if not a.run:
        print(build_prompt(docs[0], folders,
                           source_for(index, docs[0]['cache_file'])))
        print('\n[dry run. add --run to ask]')
        return

    state = ask_claude.check()
    if not state['ok']:
        print('cannot ask: %s' % state['reason'])
        return

    cdir = os.path.join(a.folder, CLASSIFY_CACHE)
    for doc in docs:
        src = source_for(index, doc['cache_file'])
        prompt = build_prompt(doc, folders, src)
        print('asking about %s ...' % os.path.basename(src or doc['cache_file']))
        try:
            answer = ask_claude.ask_json(
                prompt, cache_dir=cdir,
                add_dirs=[os.path.abspath(a.folder)])
        except ask_claude.NotAvailable as exc:
            print('  stopped: %s' % exc)
            break
        if not answer:
            print('  no usable answer; left for a person')
            continue
        record(a.folder, doc, answer, prompt, src, a.corpus)
        print('  %-26s -> %s   (%s)' % (answer.get('doc_type'),
                                        answer.get('folder'),
                                        answer.get('confidence')))
        if answer.get('evidence'):
            print('     because: %s' % str(answer['evidence'])[:90])


if __name__ == '__main__':
    main()
