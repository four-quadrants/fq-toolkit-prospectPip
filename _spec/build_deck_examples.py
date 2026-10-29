#!/usr/bin/env python3
"""Box-by-box examples for the deck drafts, from one of the lead advisor’s decks.

    python3 _spec/build_deck_examples.py "<the lead advisor’s deck>.pptx"

Writes fq_auditor/assets/deck_examples.json: for every template slide and
shape, the words the lead advisor wrote there, with every figure turned into # and the
client's names into Client. The drafts see these as a guide to what each box
is for and how long it runs. The file stays local (the .gitignore allowlist
keeps .json out of git) because the wording still describes that client.
"""
import json
import os
import re
import sys

from pptx import Presentation

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'fq_auditor', 'assets', 'deck_examples.json')


def mask(text, names):
    for n in names:
        text = re.sub(re.escape(n), 'Client', text, flags=re.I)
    text = re.sub(r'\d[\d,.]*', '#', text)
    return ' '.join(text.split())


def main():
    src = sys.argv[1]
    names = sys.argv[2:] or []
    prs = Presentation(src)
    out = {}
    for n, slide in enumerate(prs.slides, 1):
        for sh in slide.shapes:
            if sh.has_text_frame and sh.text_frame.text.strip():
                out['%d.%s' % (n, sh.name)] = mask(sh.text_frame.text, names)
    with open(OUT, 'w') as fh:
        json.dump(out, fh, indent=1)
    print('%d boxes -> %s' % (len(out), OUT))


if __name__ == '__main__':
    main()
