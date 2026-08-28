#!/usr/bin/env python3
"""Turn LaunchBay request tasks into the auditor's checklist model.

    python3 lb_checklist.py <client folder>          # build from launchbay_tasks.json
    python3 lb_checklist.py <client folder> --show   # print what it made

WHY NOT THE PDF
The auditor has been learning what to expect by parsing a checklist PDF and
reading its layout geometry. That works, but it is guesswork against a document
whose formatting varies per client — Spaulding's parsed to zero items until the
header rule was widened.

LaunchBay already holds the same list as structured data. Each request task
("Initial Document Request", "Expanded Document Request") carries subtasks that
ARE the checklist items, tagged with the stage they belong to and already ticked
off by the team.

WHAT THE COMMENTS ARE FOR
Some items can be answered by typing rather than uploading. Kelly typed her
doctor days and patient counts into the portal:

    "Total Dr. Days worked: 2024: 144  2025: 193  Jan 1-June 30 2026: 94"

She ALSO uploaded three spreadsheets carrying the same numbers, which is what
most clients do. So a comment is an extra route to satisfying an item, never a
replacement: documents are matched first and the comment is a fallback. A
file-hunting auditor with no view of comments reports these missing forever when
the client only typed them — which is what happened on both clients tested.

INPUT
A launchbay_tasks.json written from a Claude session, shaped:

    {"project": "...", "tasks": [
       {"stage": "Initial Document Request", "status": "completed",
        "subtasks": [{"text": "...", "done": true}, ...],
        "comments": [{"who": "...", "text": "..."}]}]}
"""
import os
import re
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vocab                                    # noqa: E402
from checklist_parse import build_item          # noqa: E402  (reuses the semantics)

TASKS = 'launchbay_tasks.json'
OUT = 'checklist_reviewed.json'

# Which side of the house an item belongs to. The request tasks do not say, so it
# is read from the wording — "practice bank statements" is not a personal one.
PRACTICE_HINT = re.compile(
    r'\bpractice\b|\bpractise\b|\boffice\b|provider|hygiene|associate|patients?\b|'
    r'production|fee schedule|doctor days|dr\.? days|payroll|overhead|'
    r'profit\s*&?\s*loss|\bp\s*&\s*l\b|balance sheet|open dental|eaglesoft', re.I)
PERSONAL_HINT = re.compile(
    r'\bpersonal\b|\bhome\b|spouse|w-?2|1099|pay\s?stub|credit report|'
    r'life insurance|529|ira\b|roth|401|hsa\b|birthdate|annuity', re.I)


def side_of(text):
    p = len(PRACTICE_HINT.findall(text or ''))
    q = len(PERSONAL_HINT.findall(text or ''))
    if p > q:
        return 'Practice'
    if q > p:
        return 'Personal'
    return 'Practice'          # request tasks skew practice-first; reviewable


NOISE = {'total', 'your', 'please', 'provide', 'report', 'reports', 'statement',
         'statements', 'years', 'their', 'that', 'with', 'from', 'most', 'recent',
         'copy', 'list', 'both', 'current', 'account', 'accounts', 'information',
         'all', 'and', 'for', 'the', 'any'}


def answered_by_comment(item_text, comments, wants=None):
    """Did the client answer this item in a portal message?

    Checked for EVERY item, not a chosen few — a client might type their
    birthdates, paste a debt list, or write out a balance. Nothing about an item
    says in advance which route they will take.

    Still conservative about what counts: a distinctive word from the item has to
    appear in a comment that also carries numbers, or a message saying "thanks"
    starts satisfying checklist items. Where an item has only ONE distinctive word
    ("patients"), that word plus digits is accepted — that case was being missed.

    Matched with the shared vocabulary's fuzzy word test rather than an exact
    substring, because a client answering "our birthdays are 5/12/80 and
    8/3/79" has answered "Birthdates for both of you" and a substring check
    misses it on one letter.
    """
    words = [w for w in re.findall(r'[a-z]{4,}', (item_text or '').lower())
             if w not in NOISE]
    if not words:
        return None
    need = 2 if len(words) > 2 else 1
    for c in comments or []:
        text = c.get('text') or ''
        if not re.search(r'\d', text):
            continue
        hay = vocab._words(vocab.normalise(text))
        if sum(1 for w in set(words) if vocab.has_word(hay, w)) < need:
            continue

        # Word overlap alone is not enough. It credited Kelly's "NEW Patients:
        # 241..." comment against BOTH "Total New Patients" and "Total Patients",
        # and credited a comment about insurance mix against her paystubs — so
        # documents she had never sent were reported as received.
        #
        # Documents are matched on CONCEPTS, which already know a total patient
        # count is not a new patient count. Comments were matched on a bag of
        # words that knew nothing of the sort. Hold both to the same standard:
        # the comment must actually be ABOUT one of the things the item asked
        # for. A comment whose subject cannot be identified is rejected, because
        # the cost of wrongly marking an item satisfied — the client is never
        # asked again — is far higher than the cost of asking twice.
        if wants:
            if not (set(wants) & set(vocab.concepts_in(text))):
                continue
        return c
    return None


PASSWORD_HINT = re.compile(r'\bpass\s?word\b|\bpasscode\b|\bpw\b|\bunlock\b', re.I)


def write_password_notes(folder, data, quiet=False):
    """Put any password a client sent where the person opening the file will see it.

    Clients send encrypted returns and then post the password in a portal
    comment. That comment ends up inside launchbay_tasks.json — a file nobody
    opening a zip has any reason to read — so the document is effectively
    unopenable even though the password arrived. This writes it beside the
    documents instead.

    Written verbatim rather than parsed. Guessing which digits are "the
    password" out of a sentence is exactly the kind of cleverness that hands
    someone a wrong string and no way to tell.

    NOTE: this puts the password in clear text next to the file it unlocks, on
    whatever share the client folder lives on. That is a deliberate trade — it
    was requested, and an unopenable document helps nobody — but it does mean
    the encryption stops protecting anything against someone who can already
    reach the folder.
    """
    hits = []
    for task in data.get('tasks') or []:
        for c in task.get('comments') or []:
            text = (c.get('text') or '').strip()
            if text and PASSWORD_HINT.search(text):
                hits.append((c.get('who') or 'client', text))
    if not hits:
        return None

    intake = os.path.join(folder, 'Original_sourcedocs')
    target = intake if os.path.isdir(intake) else folder
    path = os.path.join(target, '_PASSWORDS.txt')

    lines = ["Passwords the client sent through the LaunchBay portal.",
             "Copied word for word — nothing here has been interpreted.",
             "",
             "Written by the FQ toolkit on %s for: %s"
             % (__import__('time').strftime('%Y-%m-%d'), data.get('project') or '?'),
             "=" * 68, ""]
    for who, text in hits:
        lines.append("%s wrote:" % who)
        lines.append("    " + text.replace("\n", "\n    "))
        lines.append("")
    with open(path, 'w') as fh:
        fh.write("\n".join(lines))
    if not quiet:
        print("Wrote %s (%d password message(s))" % (path, len(hits)))
    return path


def build(tasks_path, quiet=False):
    with open(tasks_path) as fh:
        data = json.load(fh)

    items, seen = [], set()
    for task in data.get('tasks') or []:
        stage = task.get('stage') or 'Request'
        comments = task.get('comments') or []
        for st in task.get('subtasks') or []:
            text = (st.get('text') or '').strip()
            if not text:
                continue
            key = re.sub(r'\W+', ' ', text.lower()).strip()[:80]
            if key in seen:
                continue          # the expanded list repeats some initial items
            seen.add(key)

            raw = {'section': side_of(text), 'text': text, 'subs': []}
            try:
                item = build_item(raw)
            except Exception:
                continue
            item['stage'] = stage
            item['team_marked_done'] = bool(st.get('done'))

            hit = answered_by_comment(text, comments, item.get('satisfied_by'))
            if hit:
                # Recorded as an ADDITIONAL route, never as a substitute. Documents
                # are still matched first: Spaulding both uploaded her doctor-days
                # spreadsheets and typed the numbers in a comment, and preferring
                # the comment would have ignored three real files.
                item['answered_in_portal'] = {
                    'who': hit.get('who'), 'text': (hit.get('text') or '')[:300]}
                item['confirmed_unavailable'] = False
            items.append(item)

    if not quiet:
        print("Project: %s" % (data.get('project') or '?'))
        print("%d checklist item(s) from %d request task(s)"
              % (len(items), len(data.get('tasks') or [])))
        answered = [i for i in items if i.get('answered_in_portal')]
        if answered:
            print("%d answered in the portal rather than uploaded:" % len(answered))
            for i in answered:
                print("   - %s" % (i.get('label') or i.get('id'))[:70])
    return items


def main():
    ap = argparse.ArgumentParser(description="Build the checklist from LaunchBay request tasks")
    ap.add_argument('folder', help="the client folder")
    ap.add_argument('--tasks', default=None, help="tasks json (default: <folder>/%s)" % TASKS)
    ap.add_argument('--show', action='store_true', help="print every item")
    a = ap.parse_args()

    tasks_path = a.tasks or os.path.join(a.folder, TASKS)
    if not os.path.exists(tasks_path):
        sys.exit("No %s in %s — ask Claude to write one for this client."
                 % (TASKS, a.folder))
    items = build(tasks_path)

    out = os.path.join(a.folder, OUT)
    with open(out, 'w') as fh:
        json.dump(items, fh, indent=2)
    print("\nWrote %s" % out)

    with open(tasks_path) as fh:
        write_password_notes(a.folder, json.load(fh))

    if a.show:
        print()
        for i in items:
            flags = []
            if i.get('optional'):
                flags.append('optional')
            if i.get('answered_in_portal'):
                flags.append('answered in portal')
            if i.get('team_marked_done'):
                flags.append('team ticked')
            print("[%s / %s] %s" % (i.get('stage', '?')[:8], i.get('section'),
                                    ', '.join(i.get('satisfied_by') or ['?'])))
            print("    %s%s" % ((i.get('client_ask') or '')[:88],
                                ('   (' + '; '.join(flags) + ')') if flags else ''))


if __name__ == '__main__':
    main()
