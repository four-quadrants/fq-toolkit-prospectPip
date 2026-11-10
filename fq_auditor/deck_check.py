#!/usr/bin/env python3
"""Before a consult deck goes out: names in it that belong to another client.

A deck started from another client's (or edited from one) carries their names
along: a spouse, a child, a business. The lead advisor's Tanksley deck still
had two names from another household and one from a different practice. This
lists every name in the deck that matches another prospect's or client's
folder (any year), and is not this client's own.

    python3 deck_check.py "<deck.pptx>" "<client folder>"

The deck build runs it too and prints what it finds.
"""
import os
import re
import sys

COMMON = {'Four', 'Quadrants', 'Dental', 'Practice', 'Consult', 'Consultation', 'Year', 'Month',
          'Plan', 'Review', 'English', 'Young', 'Price', 'Rich', 'Long', 'Best', 'Grant', 'Hope',
          'Cash', 'Bond', 'Banks', 'Page', 'Major', 'Minor', 'Strong', 'Little', 'Small', 'Rule',
          # custodians and carriers that share a surname with someone (Edward Jones)
          'Jones', 'James', 'Morgan', 'Stanley', 'Wells', 'Fargo', 'Lincoln', 'Hamilton', 'Edward',
          'Raymond', 'Guardian', 'Principal', 'Mutual', 'Fidelity', 'Schwab', 'Vanguard'}


# Names that ride along in the team's own master deck from client to client
# (a household's lines left in the template), so they turn up in decks for
# people they have nothing to do with. Kept on the share, outside git, since
# they are a real household's names: one name per line.
LEFTOVERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..',
                              'Deck name check (team).txt')


def _master_leftovers():
    try:
        return [l.strip() for l in open(LEFTOVERS_FILE) if l.strip() and not l.startswith('#')]
    except OSError:
        return []


def _names_from_folder(name):
    """'Tanksley, Paige due 9:9' -> {'Tanksley', 'Paige'}; 'Compton, William & Anna' adds 'Anna'."""
    base = re.sub(r'\b(due|Due)\b.*$', '', name)
    base = re.sub(r'\(.*?\)|-\s*TEST|TEST|new|re-engage', ' ', base)
    return {w for w in re.findall(r"[A-Z][a-z]{2,}(?:-[A-Z][a-z]+)?", base)}


def other_names(prospects_root, client_folder):
    own = _names_from_folder(os.path.basename(client_folder.rstrip('/')))
    try:
        import inputs as _inputs
        adv = (_inputs.get(client_folder, 'deck') or {}).get('value') or {}
        own |= set(re.findall(r"[A-Z][a-z]{2,}", str(adv.get('names') or _inputs.value(client_folder, 'names') or '')))
    except Exception:                                        # noqa: BLE001
        pass
    others = {}
    for year in os.listdir(prospects_root):
        ydir = os.path.join(prospects_root, year)
        if not (year[:2] == '20' and os.path.isdir(ydir)):
            continue
        for d in os.listdir(ydir):
            path = os.path.join(ydir, d)
            if not os.path.isdir(path):
                continue
            kids = [d] if ',' in d else [k for k in os.listdir(path) if ',' in k and os.path.isdir(os.path.join(path, k))]
            for k in kids:
                for n in _names_from_folder(k):
                    if n not in own and n not in COMMON:
                        others.setdefault(n, k)
    for n in _master_leftovers():
        if n not in own:
            others.setdefault(n, "the team's master deck")
    return others, own


def check(deck_path, client_folder, prospects_root=None):
    from pptx import Presentation
    if prospects_root is None:
        prospects_root = os.path.dirname(os.path.dirname(os.path.abspath(client_folder)))
        if os.path.basename(os.path.dirname(os.path.abspath(client_folder))) == '_TEST':
            prospects_root = os.path.dirname(prospects_root)
    others, _own = other_names(prospects_root, client_folder)
    hits = []
    prs = Presentation(deck_path)
    for i, slide in enumerate(prs.slides, 1):
        texts = [sh.text_frame.text for sh in slide.shapes if sh.has_text_frame]
        try:
            texts.append(slide.notes_slide.notes_text_frame.text)
        except Exception:                                    # noqa: BLE001
            pass
        for t in texts:
            for w in set(re.findall(r"\b[A-Z][a-z]{2,}\b", t)):
                if w in others:
                    hits.append((i, w, others[w], t.strip().replace('\n', ' ')[:80]))
    return hits


def main():
    hits = check(sys.argv[1], sys.argv[2])
    if not hits:
        print('No names from other clients found.')
        return
    print('NAMES FROM OTHER CLIENTS (check each before the deck goes out):')
    for i, w, who, t in hits:
        print('  slide %d: "%s" (from %s): %s' % (i, w, who, t))


if __name__ == '__main__':
    main()
