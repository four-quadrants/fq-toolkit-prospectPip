#!/usr/bin/env python3
"""Ask Claude whether each checklist item has actually been satisfied.

    python3 checklist_claude.py "<client folder>"          # what it would ask
    python3 checklist_claude.py "<client folder>" --run     # ask, and save

WHY THIS IS NOT A RULE
"Satisfied" is a judgement about sufficiency, not a pattern match. Four
statements covering three months do not satisfy a request for four months. A
1040 does not satisfy a request for a business return. A debt schedule listing
balances but no rates does not satisfy "full loan information". The rules that
tried to answer this grew a vocabulary of concepts, a proximity window, and a
list of words that must match exactly because "provided" kept matching
"provider" -- and they still got it wrong in ways that took a person to notice.

Claude is given the ask as the client read it, every document that could bear on
it, and what the tool read out of each one. It answers in the firm's own terms:
satisfied, partly satisfied, or missing, and says what is still needed in the
words the client would be asked for it.

WHAT IT IS NOT ASKED
Anything numeric. The months a statement covers, the account it belongs to and
the year on a return are read by the tool and handed over as fact. Claude
decides whether those facts add up to the ask.

THE ANSWER IS A PROPOSAL
Every verdict lands beside the ones a person has already made, and a person's
decision always wins. The review page shows Claude's reasoning so there is
something to disagree with rather than a verdict to take on trust.
"""
import os
import re
import sys
import json
import glob
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import classify                                              # noqa: E402
import ask_claude                                            # noqa: E402

CACHE = '.fq_cache'
VERDICTS = os.path.join('_Audit', 'claude_checklist.json')
CHECKLIST = os.path.join('_Audit', 'checklist_reviewed.json')

SCHEMA = """{
  "verdict": "satisfied, partly satisfied, or missing",
  "reasoning": "one or two sentences a person can disagree with",
  "evidence": ["the documents that satisfy it, by filename"],
  "asks": [
    {"section": "Personal or Practice",
     "text": "one or two short sentences asking for what is outstanding"}
  ],
  "confidence": "high, medium or low"
}"""


def load_checklist(folder):
    path = os.path.join(folder, CHECKLIST)
    if not os.path.exists(path):
        path = os.path.join(folder, os.path.basename(CHECKLIST))
    with open(path) as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else data.get(
        'items', data.get('checklist', []))


def inventory(folder):
    """Every document, as the tool reads it: type, year, period, account.

    This is the factual half. Claude is not asked to work out which month a
    statement covers; it is told, and asked whether the months add up.
    """
    out, seen = [], set()
    # One entry per document. The cache holds the same document several
    # times over: under its hash at each reader version (.v4, .v6) and under
    # its descriptive name. Oyler's 192 documents arrived as 343, and with a
    # cap per question the June statement Claude needed was crowded out by
    # copies of March, so it reported June missing when it was here.
    paths = sorted(glob.glob(os.path.join(folder, CACHE, '*.txt')),
                   key=lambda p: (-int((re.search(r'\.v(\d+)\.txt$', p) or
                                        re.search(r'()$', '')).group(1) or 0),
                                  p))
    for path in paths:
        text = open(path, errors='replace').read()
        if len(text.strip()) < 40:
            continue
        key = ' '.join(text.split())[:400]
        if key in seen:
            continue
        seen.add(key)
        doc = classify.classify(text)
        # The statement's own date beats a guess. Oyler's June statement for
        # x4728 carries a notice about October, and the classifier's
        # "most frequent full date" made it an October statement, so Claude
        # was told June was missing when it was here.
        period = doc.get('period') or doc.get('granularity')
        own = re.search(r'statement\s+date\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})',
                        text[:3000], re.I)
        if own:
            period = 'statement dated %s' % own.group(1)
        out.append({
            'sha': os.path.basename(path).split('.')[0],
            'type': doc.get('doc_type'),
            'side': doc.get('owner_side'),
            'year': doc.get('year'),
            'period': period,
            'account': doc.get('account_tail'),
            'issuer': doc.get('issuer'),
            'entity': doc.get('entity'),
            'first_words': ' '.join(text.split())[:160],
        })
    return out


def names_for(folder):
    """{sha: the name the document will be filed under}, if a plan exists."""
    import csv
    out = {}
    plan = os.path.join(folder, '_Audit', 'rename_plan.csv')
    try:
        with open(plan) as fh:
            for row in csv.DictReader(fh):
                if row.get('sha'):
                    out[row['sha']] = row.get('proposed_name') or row['existing']
    except (OSError, KeyError, ValueError):
        pass
    return out


def relevant(item, docs, cap=40):
    """Documents that could bear on this item.

    Three groups, in order. Documents of a type that would satisfy the ask.
    Documents the tool could not type at all, because an unrecognised document
    is exactly where a correctly-provided item hides. Then, if there is room,
    documents on the same side of the house, so an ask about personal accounts
    can see that only practice ones arrived.

    Handing over all sixty-two for every item was the first attempt. It makes
    each prompt enormous, costs a seat allowance that is shared with everything
    else, and buries the two documents that matter in sixty that do not.
    """
    side = {'Personal': 'Personal', 'Practice': 'Practice'}.get(
        item.get('section'))
    types = set(item.get('satisfied_by') or ())

    matched = [d for d in docs if d.get('type') in types]
    untyped = [d for d in docs if d.get('type') in (None, 'unknown')
               and d not in matched]
    same_side = [d for d in docs if side and d.get('side') == side
                 and d not in matched and d not in untyped]

    out = matched + untyped
    # Pad only when nothing of the right kind arrived. Then the question is
    # "what did turn up instead", and seeing the practice statements is how
    # Claude can say the personal ones are the ones still missing. When matches
    # exist, more documents only make the answer harder to find.
    if not matched:
        out += same_side[:max(0, 10 - len(out))]
    return out[:cap]


def build_prompt(item, docs, names):
    lines = []
    for d in docs:
        bits = [b for b in (d['type'], d['side'], d['year'], d['period'],
                            ('x%s' % d['account']) if d['account'] else None,
                            d['issuer']) if b]
        lines.append('  - %s\n      [%s]\n      "%s"'
                     % (names.get(d['sha'], d['sha'][:12]),
                        ', '.join(str(b) for b in bits),
                        d['first_words'][:140]))
    asked = item.get('client_ask') or item.get('label')
    extra = ''
    if item.get('years'):
        extra += '\nYears asked for: %s' % ', '.join(item['years'])
    if item.get('count'):
        extra += '\nHow many asked for: %s' % item['count']
    if item.get('granularity'):
        extra += '\nArriving as: %s' % item['granularity']

    return """You are checking a document request for a dental practice financial advisory firm.

WHAT WAS ASKED OF THE CLIENT:
%s%s

WHAT THE CLIENT HAS SENT, with what we read from each:
%s

Has the ask been satisfied?

Reply with only JSON:
%s

How to judge:
- Count what was asked for. Four months means four months; three is partly.
- A run of months must be unbroken. A gap in the middle is partly, not
  satisfied, and the missing month should be named.
- Every account means every account. If the ask covers all accounts and only
  some appear, say which are present and that others may exist.
- A document of the right kind for the wrong entity or the wrong year does not
  satisfy the ask. Say so plainly.

How to write the asks:
- If it is satisfied, asks is an empty list.
- An item covering both sides of the house produces TWO asks, one marked
  Personal and one Practice. They are two different things to chase, and a
  client reading a Practice heading should not find their own 1040 under it.
  If one side is already satisfied, produce one ask for the other side only.
- BE BRISK. One or two short sentences. These land in a numbered list and the
  reader has fifteen of them.
- Name what we already have only when it stops the client re-sending it.
- No thanking, no softening, no explaining our process. "Please send the June
  2026 statement for the practice account ending 4728. We have March to May."
  is the whole thing.""" % (
        asked, extra, '\n'.join(lines) or '  (nothing relevant has arrived)',
        SCHEMA)


def main():
    ap = argparse.ArgumentParser(description='Judge the checklist with Claude')
    ap.add_argument('folder')
    ap.add_argument('--run', action='store_true')
    ap.add_argument('--only', help='one item id, for testing')
    a = ap.parse_args()

    items = load_checklist(a.folder)
    docs = inventory(a.folder)
    names = names_for(a.folder)
    if a.only:
        items = [i for i in items if i.get('id') == a.only]
    print('%d checklist items, %d documents\n' % (len(items), len(docs)))

    if not a.run:
        item = items[0]
        print(build_prompt(item, relevant(item, docs), names))
        print('\n[dry run. add --run to ask]')
        return

    state = ask_claude.check()
    if not state['ok']:
        print('cannot ask: %s' % state['reason'])
        return

    cdir = os.path.join(a.folder, CACHE, 'checklist')
    out, counts = {}, {}
    for item in items:
        prompt = build_prompt(item, relevant(item, docs), names)
        try:
            ans = ask_claude.ask_json(prompt, cache_dir=cdir,
                                      add_dirs=[os.path.abspath(a.folder)])
        except ask_claude.NotAvailable as exc:
            print('stopped: %s' % exc)
            break
        if not ans:
            continue
        out[item['id']] = {'label': item.get('label'), **ans}
        v = ans.get('verdict', '?')
        counts[v] = counts.get(v, 0) + 1
        mark = {'satisfied': ' ', 'partly satisfied': '~',
                'missing': '!'}.get(v, '?')
        print('%s %-54s %s (%s)' % (mark, (item.get('label') or '')[:54],
                                    v, ans.get('confidence')))
        if ans.get('reasoning'):
            print('     %s' % str(ans['reasoning'])[:110])

    # Nothing answered is a failure, not a result: writing an empty file and
    # saying "written to" looked like success on a Mac that was not signed
    # in (22 October). Leave any earlier answers where they are.
    if not out:
        print('No answers came back, so nothing was written.')
        return
    path = os.path.join(a.folder, VERDICTS)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        json.dump(out, fh, indent=1)
    print('\n' + '  '.join('%s: %d' % (k, v) for k, v in sorted(counts.items())))
    print('written to %s' % path)


if __name__ == '__main__':
    main()
