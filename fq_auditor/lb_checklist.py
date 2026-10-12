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

TASKS = os.path.join('_Audit', 'launchbay_tasks.json')
OUT = os.path.join('_Audit', 'checklist_reviewed.json')

# Which side of the house an item belongs to. The request tasks do not say, so it
# is read from the wording — "practice bank statements" is not a personal one.
PRACTICE_HINT = re.compile(
    r'\bpractice\b|\bpractise\b|\boffice\b|provider|hygiene|associate|patients?\b|'
    r'production|fee schedule|doctor days|dr\.? days|payroll|overhead|'
    r'profit\s*&?\s*loss|\bp\s*&\s*l\b|balance sheet|open dental|eaglesoft', re.I)
PERSONAL_HINT = re.compile(
    r'\bpersonal\b|\bhome\b|spouse|w-?2|1099|pay\s?stub|credit report|'
    # "birth date" as two words: Oyler's expanded request says "Birth date for
    # Brian", which matched nothing, so the item defaulted to Practice and a
    # personal document answering it was reported as the wrong side.
    r'life insurance|529|ira\b|roth|401|hsa\b|birth\s?dates?|annuity|'
    r'credit report|w-?2s?\b|pay\s?stub', re.I)


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



# A message that asks for something, or promises it, is not an answer.
#
# Rebol's client satisfied both QuickBooks items with "Items 3, 4: I can set you
# up with a Quickbooks sign in, I just need the appropriate email to send the
# invite" — a request for information, read as a submission. The other candidate
# was "What email should I send the invite to?", a plain question. Neither is
# separable by length or by how many concepts it touches: his catch-all was 430
# characters and 2 concepts, his real answers 40 to 100 characters and 1 to 2.
#
# What separates them is mood. An answer states; these ask and promise.
PENDING = re.compile(
    r'\?|'                                     # any question at all
    r"\bwill\s+\w+|"                           # any promise of a future send
    r"\b(i'?ll|as soon as|plan to|planning to|going to|"
    r"i need|i just need|can you|could you|let me know|"
    r"isn'?t working|is not working|trying to|working on)\b", re.I)
# The list used to name the verbs — "will upload", "will send", "will get" —
# and a client wrote "will include P&L and Balance sheets for these". That
# passed as an ANSWER, and would have marked her Profit & Loss and Balance
# Sheet items satisfied on the strength of a sentence promising to send them
# later. Naming verbs meant the guard only caught the phrasings someone had
# already thought of, so it now matches "will" followed by anything.
#
# The cost is real and accepted: a message reading "we will not have one" is a
# genuine answer and is now rejected too. Rejecting only means the auditor
# declines to close the item by itself and leaves it to a human, which is the
# safe direction. Crediting a promise is not recoverable — nobody chases an
# item that already looks answered.
# "not yet" is deliberately NOT in that list. It rejected "We don't have a
# written financial plan and 2025 personal taxes are not yet complete" — one
# message carrying a real answer about one item and a pending note about
# another. Losing the answer to catch the promise is the wrong trade.


def sounds_like_an_answer(text):
    """False when the message asks for something or promises it later."""
    return not PENDING.search(text or '')


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
        if not sounds_like_an_answer(text):
            continue
        hay = vocab._words(vocab.normalise(text))
        # Word overlap is a proxy for subject; concept overlap is the real test,
        # and it is the stricter of the two — it was added precisely because
        # word overlap credited a "NEW Patients" comment against "Total
        # Patients". So where the concepts agree, the words need not.
        #
        # Rebol's client answered "Birthdates for both of you" with "Item 11 -
        # AB 03/09/1971, CD 11/22/1974". The word "birthdates" appears
        # nowhere in it, so the item read unanswered with the answer sitting in
        # the thread. Concepts see it; words never could.
        concept_hit = bool(wants and (set(wants) & set(vocab.concepts_in(text))))
        if not concept_hit and sum(
                1 for w in set(words) if vocab.has_word(hay, w)) < need:
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

    # `seen` de-duplicates repeated SUBTASK TEXT across stages. `_seen_ids` is a
    # different job: it guarantees the generated ids are unique, which they were
    # not — see _slug in checklist_parse. Kept separate because two items can
    # legitimately share wording across stages and still need distinct ids.
    items, seen, _seen_ids = [], set(), set()
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
                item = build_item(raw, _seen_ids)
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
        legacy = os.path.join(a.folder, os.path.basename(TASKS))
        if os.path.exists(legacy):
            tasks_path = legacy
    if not os.path.exists(tasks_path):
        sys.exit("No %s in %s — ask Claude to write one for this client."
                 % (TASKS, a.folder))
    items = build(tasks_path)

    out = os.path.join(a.folder, OUT)
    os.makedirs(os.path.dirname(out), exist_ok=True)
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


# --------------------------------------------------------------------------
# the portal conversation
# --------------------------------------------------------------------------
# Comments are not only the client answering. Chad wrote "the only things we're
# missing are the Personal Debt Schedule" on Oyler a week before the auditor
# reached the same conclusion by reading documents, and Kelly wrote "I don't
# get paystubs" against an item the auditor still reports as missing. Both are
# knowledge the team already had and the tool was throwing away.
#
# Shown, never acted on. These are surfaced next to the item so a person can
# read them and decide; nothing here marks anything satisfied. That line matters
# because the matching is good, not perfect — see MAX_CONCEPTS below.
MAX_CONCEPTS = 3


def _is_client(who, project):
    """Is this comment from the client rather than from us?

    Worked out from the project name — "Oyler, Brian" tells us Brian Oyler is
    the client and everyone else on the thread is ours. Better than a hardcoded
    staff list, which would silently mislabel the next person who joins.
    """
    who = (who or '').lower()
    parts = [p.strip().lower() for p in re.split(r'[,\-–]', project or '') if p.strip()]
    return any(p and p in who for p in parts) or any(
        w and w in who for p in parts for w in p.split() if len(w) > 2)


def all_comments(data):
    """Every comment on the project, newest last, tagged with who said it."""
    out = []
    project = data.get('project') or ''
    for task in data.get('tasks') or []:
        for c in task.get('comments') or []:
            text = (c.get('text') or '').strip()
            if not text:
                continue
            out.append({'who': c.get('who') or 'someone',
                        'text': text,
                        'stage': task.get('stage') or '',
                        'from_client': _is_client(c.get('who'), project)})
    return out


def discussion_for(item, comments):
    """Comments that look like they are about this checklist item.

    Two filters, both learned from the real threads:

    1. The comment has to touch one of the concepts the item asks for.
    2. It must not touch more than MAX_CONCEPTS of them. A long chatty message
       — one client's paragraph about an $844 interest payment mentioned debt,
       balance, credit, profit and production — matches half the checklist and
       tells you nothing about any of it. A comment about everything is about
       nothing.

    Plus the item has to be named: at least one distinctive word from the ask
    has to appear, so "thanks, will do" never attaches to anything.
    """
    want = set(item.get('satisfied_by') or [])
    if not want:
        return []
    words = [w for w in re.findall(r'[a-z]{4,}', (item.get('label') or '').lower())
             if w not in NOISE]
    hits = []
    for c in comments:
        cons = set(vocab.concepts_in(c['text']))
        if len(cons) > MAX_CONCEPTS or not (want & cons):
            continue
        # Same reasoning as answered_by_comment: the concept test already
        # established the subject, so a message that names the thing only in
        # numbers still belongs beside its item.
        hay = vocab._words(vocab.normalise(c['text']))
        if words and not (want & cons) and not any(
                vocab.has_word(hay, w) for w in words):
            continue
        hits.append(c)
    return hits


def attach_discussion(items, data):
    """Hang the relevant comments off each item, in place."""
    comments = all_comments(data)
    for it in items:
        found = discussion_for(it, comments)
        if found:
            it['discussion'] = [{'who': c['who'], 'text': c['text'][:400],
                                 'from_client': c['from_client']} for c in found[:4]]
    return comments
