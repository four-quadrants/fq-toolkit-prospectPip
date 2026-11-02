---
name: fq-consult-review
description: "Load, refresh or pull in a Four Quadrants prospect's CONSULT REVIEW: the lead advisor's second review page, after the client's answers are in, with open questions, the plan figures and every assumption, the recommendations checklist, the projections what-if, and the slides that still need a decision. Use when someone says \"load [client]'s consult review\", \"refresh [client]'s consult review\", \"pull in [client]'s consult review\", or \"pull in [client]'s review\" once an analysis review has been done. Pulling it in is what the consult deck is built from."
---

# Consult review

The second review page. The lead advisor decides the plan here: figures and
assumptions, which recommendations go in and when, the pay structure, 4Q's
returns for each account, and any slide wording Claude drafted. Read
`references/mechanics.md` for how pages are found, seeded, published, refreshed
and pulled in.

## Load

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
3. Next step for the analyst: in the app, **Build the deck**.
