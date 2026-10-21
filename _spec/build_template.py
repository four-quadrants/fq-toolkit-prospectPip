#!/usr/bin/env python3
"""Turn a finished consult deck into the clean template the generator uses.

    python3 _spec/build_template.py "Oyler Consultation-ah version.pptx"

Run it whenever the designer changes the deck: export the new version from
Keynote (File > Export To > PowerPoint) and point this at it. It writes
`fq_auditor/assets/consult_template.pptx`.

WHY A CLEAN COPY
The template lives in git so every machine has it, and the repo's rule is that
no client's figures go into the history. The firm's deck is a real client's
consult. So every piece of text the generator would replace anyway (a client
figure, or the advisor's words) is blanked here to [TBD] or
[ADVISOR: write this], the client's names become {FIRST} and {SURNAME}, and the
presenter notes on client slides are cleared. What is left is the design and
the firm's boilerplate, which is what a template is.

It then scans the result for anything of the source client's that survived and
refuses to write the file if it finds any.
"""
import os
import re
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'fq_auditor'))
from pptx import Presentation                                # noqa: E402
import deck_template as T                                    # noqa: E402

OUT = os.path.join(HERE, '..', 'fq_auditor', 'assets',
                   'consult_template.pptx')

# Every shape the generator writes a figure into, by template slide.
FILLED = {
    1: ['Text 1', 'Text 4'],
    2: ['Text 5', 'Text 7', 'Text 8', 'Text 11', 'Text 13', 'Text 16',
        'Text 18', 'Text 19', 'Text 20', 'Text 23'],
    3: ['Text 2', 'Text 3', 'Text 28'],
    4: ['Text 23', 'Text 26', 'Text 30', 'Text 33', 'Text 35', 'Text 37'],
    9: ['Text %d' % n for n in (2, 3, 4, 13, 15, 17, 19, 22, 24, 26, 28, 30,
                                33, 35, 37, 39, 41, 44, 46, 48, 50, 52, 55,
                                57, 59, 61, 63, 66, 72, 74)],
    10: ['Text 3', 'Text 4', 'Text 28'],
    13: ['Text 3', 'Text 8', 'Text 20', 'Text 31'],
    15: ['Text 5', 'Text 6', 'Text 24', 'Text 27', 'Text 38', 'Text 41',
         'Text 51', 'Text 53'],
    17: ['Text 3', 'Text 4', 'Text 7'] + ['Text %d' % n for n in (
        14, 16, 18, 20, 22, 25, 27, 29, 31, 33, 36, 38, 40, 42, 44, 47, 49,
        51, 53, 55, 59, 62, 65, 68, 71, 74, 75, 76, 77, 78, 79, 81, 82)],
    20: ['Text 3', 'Text 4', 'Text 5', 'Text 7', 'Text 8', 'Text 9',
         'Text 11', 'Text 12', 'Text 13', 'Text 15', 'Text 16'],
}
FILLED[18] = list(FILLED[17])


def build(src, first, surname, out=OUT):
    prs = Presentation(src)
    for n, slide in enumerate(prs.slides, 1):
        default, shapes = T.SPEC.get(n, ('keep', {}))
        filled = set(FILLED.get(n, []))
        for sh in slide.shapes:
            if not sh.has_text_frame or not sh.text_frame.text.strip():
                continue
            how = 'fill' if sh.name in filled else shapes.get(sh.name, default)
            was = sh.text_frame.text.strip()
            if how in ('fill', 'advisor'):
                T.set_text(sh, '[TBD]' if len(was) <= 18
                           else T.ask('write this'))
            elif how == 'name':
                for p in sh.text_frame.paragraphs:
                    for r in p.runs:
                        r.text = (r.text.replace(first, '{FIRST}')
                                  .replace(first.upper(), '{FIRST}')
                                  .replace(surname, '{SURNAME}')
                                  .replace(surname.upper(), '{SURNAME}'))
        if slide.has_notes_slide and n not in T.KEEP_NOTES:
            slide.notes_slide.notes_text_frame.text = ''

    # Refuse to write anything that still names the source client.
    bad = re.compile(r'%s|%s|\$\d' % (re.escape(first), re.escape(surname)),
                     re.I)
    found = []
    for n, slide in enumerate(prs.slides, 1):
        texts = [sh.text_frame.text for sh in slide.shapes
                 if sh.has_text_frame]
        if slide.has_notes_slide:
            texts.append(slide.notes_slide.notes_text_frame.text)
        for t in texts:
            for m in bad.finditer(t):
                # The firm's own "$5k rule" and fee scale are boilerplate.
                ctx = t[max(0, m.start() - 20):m.end() + 20]
                if re.search(r'\$5k|\$5,000|\$1M', ctx):
                    continue
                found.append((n, ctx))
    if found:
        for n, ctx in found:
            print('slide %d still has: %r' % (n, ctx))
        raise SystemExit('Not written: the template would still carry the '
                         'source client.')
    prs.save(out)
    return out


def main():
    ap = argparse.ArgumentParser(description='Clean consult template')
    ap.add_argument('deck', help="Keynote's PowerPoint export of the deck")
    ap.add_argument('--first', default=T.TEMPLATE_FIRST_SOURCE)
    ap.add_argument('--surname', default=T.TEMPLATE_SURNAME_SOURCE)
    a = ap.parse_args()
    print('wrote %s' % build(a.deck, a.first, a.surname))


if __name__ == '__main__':
    main()
