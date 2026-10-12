#!/usr/bin/env python3
"""Write the lines an analyst would write, and only those lines.

    python3 notes.py "<client folder>"            # the prompt, unasked
    python3 notes.py "<client folder>" --run      # ask, and save

WHAT A NOTE IS
Not the figure. The figure is already read, checked and sourced. A note is
everything the figure does not say on its own:

    Practice debt $1.1M from 6 debts, 3 maturing within 2 years. Has an LOC.
    Books depreciation at year end: none on the 2025 or 2026 books, shows in 2024.
    Net income on the 2024 and 2025 books does not match the returns.

Composition, movement, contradiction. The third is the one that matters most:
the analyst has been doing conflict detection by hand, one line at a time.

WHY ONE CALL AND NOT ONE PER FIGURE
Asking per figure forces a note onto every row, and "Age 58" has no note worth
writing. An earlier version did exactly that and produced forty paragraphs
where the analyst writes a dozen lines, with the same contradiction repeated on
six of them.

So the whole picture goes over at once and the answer names only the lines
worth writing on. That is also how a person does it: read everything, write
where there is something to write.
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import facts as _facts                                       # noqa: E402
import ask_claude                                            # noqa: E402

CACHE = os.path.join('.fq_cache', 'notes')
OUT = os.path.join('_Audit', 'notes.json')

SCHEMA = """{
  "notes": [
    {"line": "the exact label from the list above",
     "note": "one or two sentences, forty words at the outside",
     "flags": ["a contradiction with another document, at most two"],
     "questions": ["what you would ask the client, at most two"]}
  ]
}"""


def _short(v):
    if isinstance(v, float) and 0 < abs(v) < 2:
        return '%.1f%%' % (v * 100)
    if isinstance(v, (int, float)):
        return '{:,.0f}'.format(v)
    return str(v)


def picture(bundle):
    """Everything read, as one page a person could scan."""
    lines = []
    for block in bundle.blocks:
        lines.append('\n%s' % block.title.upper())
        for f in block.facts:
            if f.value is None:
                lines.append('  %-38s (not supplied)' % f.label)
            else:
                lines.append('  %-38s %-16s [%s]'
                             % (f.label, _short(f.value),
                                (f.source or 'no source')[:40]))
    lines.append('\nTHREE-YEAR HISTORY')
    for name, by_year, _fmt in bundle.series:
        vals = {y: v for y, v in by_year.items() if v is not None}
        if vals:
            lines.append('  %-38s %s' % (name, '  '.join(
                '%s %s' % (y, _short(v)) for y, v in sorted(vals.items()))))
    return '\n'.join(lines)


def build_prompt(bundle):
    return """You are the analyst writing initial notes on a dental practice
prospect for a financial advisory firm.

Below is everything we have read from this client's documents. Write the notes
an analyst would write beside these figures.

CLIENT: %s

%s

Reply with only JSON:
%s

How to choose what to write on:
- ONLY lines where there is something to say. A figure that speaks for itself
  gets no note. Age, marital status, software, chair counts: no note.
- An analyst writes roughly ten to fifteen notes on a client like this. If you
  are writing thirty, you are padding.
- The most valuable note is one document contradicting another. Write those
  first, on the line they belong to, ONCE. Do not repeat the same
  contradiction across six rows.

How to write them:
- ONE OR TWO SENTENCES. Forty words at the outside. Notes in a spreadsheet
  cell, not a memo.
- Say what the figure is made of when that is knowable, and how it has moved.
- Questions are for the client, not for us. At most two per line.
- Use ONLY the figures above. If a ratio looks not to divide, the denominator
  is probably in the list: check before concluding something is excluded.
- Never write a sentence the figures do not support. A blank line is fine; a
  plausible invention is not.""" % (bundle.client, picture(bundle), SCHEMA)


def main():
    ap = argparse.ArgumentParser(description='Write the analyst lines')
    ap.add_argument('folder')
    ap.add_argument('--client', default=None)
    ap.add_argument('--run', action='store_true')
    a = ap.parse_args()

    bundle = _facts.gather(a.folder, client=a.client)
    prompt = build_prompt(bundle)

    if not a.run:
        print(prompt)
        print('\n[dry run. add --run to ask]')
        return

    state = ask_claude.check()
    if not state['ok']:
        print('cannot ask: %s' % state['reason'])
        return

    answer = ask_claude.ask_json(prompt,
                                 cache_dir=os.path.join(a.folder, CACHE),
                                 add_dirs=[os.path.abspath(a.folder)])
    if not answer or not answer.get('notes'):
        print('no usable answer')
        return

    # Keyed by line, because that is how the workbook looks them up.
    out = {}
    known = {f.label for f in bundle.all_facts()}
    unmatched = []
    for row in answer['notes']:
        line = (row.get('line') or '').strip()
        if line not in known:
            unmatched.append(line)
            continue
        out[line] = {'note': row.get('note'),
                     'flags': list(row.get('flags') or ())[:2],
                     'questions': list(row.get('questions') or ())[:2]}

    path = os.path.join(a.folder, OUT)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        json.dump(out, fh, indent=1)

    for line, got in out.items():
        print('\n%s' % line)
        if got.get('note'):
            print('   %s' % got['note'])
        for f in got['flags']:
            print('   FLAG: %s' % f)
        for q in got['questions']:
            print('   ASK:  %s' % q)
    print('\n%d notes on %d figures' % (len(out), len(list(bundle.all_facts()))))
    if unmatched:
        # A line name that matches nothing is a note that would vanish.
        print('%d note(s) named a line that does not exist: %s'
              % (len(unmatched), ', '.join(unmatched[:4])))


if __name__ == '__main__':
    main()
