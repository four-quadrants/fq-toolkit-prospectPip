---
name: fq-consult-review
description: "Load, refresh or pull in a Four Quadrants prospect's CONSULT REVIEW: the lead advisor's second review page, after the client's answers are in, with open questions, the plan figures and every assumption, the recommendations checklist, the projections what-if, and the slides that still need a decision. Use when someone says \"load [client]'s consult review\", \"refresh [client]'s consult review\", \"pull in [client]'s consult review\", or \"pull in [client]'s review\" once an analysis review has been done. Pulling it in is what the consult deck is built from."
---

# Consult review

## Where the .json files live

Every .json the toolkit keeps for a client (launchbay_manifest, launchbay_tasks,
checklist_reviewed, claude_checklist, doc_readings, notes, summary,
review_pages, review_decisions, bank_statements and the rest) lives in one
folder beside the clients, never in the client folder:
`Prospects/<year>/4.) Claude outputs/<Surname>/<name>_<Client>.json`, for example
`Prospects/2026/4.) Claude outputs/Example/notes_Example, Jane.json`. Get the exact path
with `python3 fq_auditor/store.py "<client folder>" notes.json` and read and
write it there. Wherever this skill says `_Audit/<name>.json` or a .json "in
the client folder", it means that path. The client folder keeps the documents
and the outputs people open (initial notes, cash flow, deck).

The second review page. The lead advisor decides the plan here: figures and
assumptions, which recommendations go in and when, the pay structure, 4Q's
returns for each account, and any slide wording Claude drafted. Read
`references/mechanics.md` for how pages are found, seeded, published, refreshed
and pulled in.

## Load

Before seeding a NEW consult review, pull the analysis review in once more
(fq-analysis-review, "pull in") so the answers typed on it since are carried:
the consult review's Notes & questions tab lists everything asked and noted
on the analysis review, with its answer, for the lead advisor to mark
Answered well or Follow up (a follow-up becomes an open question). The
Recommendations tab's **Add from the library** lists the whole library
(`fq_auditor/recommendations_library.md`); what he adds there is pulled in
like any other recommendation. A recommendation he writes himself (Add a
recommendation) joins the library at pull-in and stays for every client
after. When someone asks to take one out of the library, delete its `##`
block from `recommendations_library.md` (and only that), and say which.
The tab lists the client's suggested ones plus the firm's most common, about
a dozen; everything else is under Add from the library.

The Slides tab opens with the deck's outline: he can take any slide out, or
add his own after any slide, picking from pictures of nine layouts (from
Numbered points and Statement to a Detailed table like the account-by-account
slide), each filling the slide in the deck's own look. A slide left out for
the client (nothing to show) can be included anyway; its boxes are then left
for him to fill. If the deck template or a layout changes, run
`python3 fq_auditor/slide_layouts.py` to redraw the layout pictures on the page. The pull in reports "deck: N slide(s)
removed, N added"; the next deck build applies them.

1. Find the toolkit and the client folder. Check `_Audit/review_pages.json` for
   an existing consult page (then this is a refresh).
2. Seed with `--mode consult`. The seed carries over his decisions from the
   analysis review, and lists the analysis questions that documents received
   since have answered (`answered_by_docs`).
3. Before publishing, tell the analyst briefly what stands out: recommendations
   suggested and why, figures still missing (4Q returns, building value), and
   questions still open.
4. Publish a new page (with the slide pictures), or refresh the existing one's
   data.

## Pull in

1. Pull in (mechanics: Pulling in). The recommendations he left ticked become
   the savings table; his figures and assumptions go into the plan inputs.
2. Act on every note and client answer printed, before anything else, and say
   what was done about each.
3. Build the deck, in the same run: from fq_auditor,
   `FQ_NO_CLAUDE=1 FQ_ROOT_FILE=/tmp/fqroot python3 build_outputs.py "<client folder>" --what deck`.
   It fills the firm's consult template from the plan and his slide
   decisions (taken out, added, layouts) and saves `Consult deck -
   <Surname>.pptx` in the client folder; it opens in Keynote. Say how many
   places are still marked [ADVISOR] for him to write, and that the deck
   can be rebuilt any time after he changes the page.

## "Build the deck" from the page

The consult review's Slides tab has a **Build the deck** button. It copies
one line, "Pull in and build <Surname>'s consult deck", for the lead advisor
or analyst to paste here. That line means: Pull in (above), act on the notes
and answers, then build the deck. The page itself cannot reach the client
folder; Claude does.
