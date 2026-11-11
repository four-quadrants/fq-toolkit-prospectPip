---
name: fq-analysis-review
description: "Build, load, refresh or pull in a Four Quadrants prospect's REVIEW: the one page per prospect, which is also how the ASSUMPTIONS are built and reviewed. Assumptions first, then what the documents show, the follow-up questions and client email, then the plan, recommendations, projections and slides, and the consult deck built from it. Use when someone says \"build [client]'s assumptions\", \"load [client]'s assumptions\", \"load [client]'s review\", \"load [client]'s analysis review\" or \"consult review\", \"refresh [client]'s review with the new answers and documents\", \"check [client]'s answers\", \"pull in my check\", \"pull in [client]'s questions\", \"pull in [client]'s review\", \"pull in and build [client]'s consult deck\", \"print [client]'s assumptions\", or asks how the review page works (\"walk me through [client]'s review\", \"what's the difference between Plan inputs and Recommendations\"). Comes after the cash flow."
---

# The review (one page per prospect)

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

One page per prospect, worked in stages on the same page. It replaces the
separate analysis and consult reviews (an older client may still have both;
keep working whichever page it has).

1. **The analyst's check: the Assumptions only.** A new page opens in the
   analyst stage and shows the Assumptions and What we found tabs. The
   analyst comments on any section that is wrong or missing (as many comments
   on a section as needed: **+ Add another comment**), each a Note or a
   Question to the client, and asks Claude to pull in the check. Claude fixes
   what the comments point to and refreshes the page. Repeat until clean, then
   the analyst presses **Ready for the lead advisor** (twice) and shares the
   page with him.
2. **The lead advisor: every tab.** On the Assumptions he sorts each of the
   analyst's comments (Note or Question to the client) and adds his own. He
   picks the questions; the email to the client is built on the Email tab.
   The Plan, Recommendations, Projections and Slides tabs are there from the
   start, marked provisional while answers are outstanding, so he can work
   ahead or do it all in one sitting.
3. **Answers come in.** Under each comment he sees the client's answer,
   Claude's verdict on whether it settles the point, and marks it Answered /
   Done, Still open (asked again) or Team to revisit. The page's **Check for
   new answers and documents** button copies "Refresh <Surname>'s review with
   the new answers and documents" for him to paste here.
4. **The deck.** The Slides tab's **Build the deck** copies "Pull in and build
   <Surname>'s consult deck".

When someone asks how to use the page or wants to be walked through it,
read `references/page_guide.md` and follow it. For a first look (setup, or
"make me a training page"), publish their own training page first
(mechanics: The training page), then walk them through it.

Read `references/mechanics.md` for how pages are found, seeded, published,
refreshed and pulled in. Seed with `--mode review` (the default). In
`_Audit/review_pages.json` the page is recorded as `"review"`.

The Recommendations tab's **Add from the library** lists the whole library
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

## Load (also: "build the assumptions")

"Assumptions" and "analysis review" are one step to the analyst: the
assumptions are built and then shown as the page's first tab. Never make a PDF
unless asked.

1. Find the toolkit and the client folder (mechanics: Finding things). Check
   `_Audit/review_pages.json` for an existing page (`review`, or an older
   `analysis` / `consult`); if there is one, this is a refresh, not a new page.
2. Build everything the assumptions rest on, in order, in one run: from
   fq_auditor, `python3 build_outputs.py "<client folder>" --what
   cashflow,assumptions`. That reads every bank statement (each must tie to
   the dollar), writes the cash flow workbook, reads the investment
   statements (accounts and returns), then works out the 14 sections and
   reads, once, what the page needs (pay from the returns, account returns,
   drafted wording, recommendation picks). Where a reading needs Claude and
   the session has no Claude CLI, do that reading in the session and save it
   where the code expects it (as with bank_statements.json and
   doc_readings.json), checked against the document.
3. Seed with `--mode review`. A new page starts in the analyst stage.
4. Before publishing, read `plan.json`'s `assumptions`, `findings` and the
   questions, and tell the analyst briefly what stands out: accounts or debts
   that look wrong or missing, statements that did not tie, questions that
   look mistaken.
5. Publish a new page, or refresh the existing one's data. After a FIRST
   publish, record the URL in `_Audit/review_pages.json` and write it to the
   page as `page_url` (ArtifactData `update` plan/figures), so the hand-off
   can show the link. The analyst checks the Assumptions first; do not tell
   them to share it with the lead advisor yet.

## When the analyst is done with the assumptions

When the analyst says they are done, happy with the assumptions, or asks how
to get it to the lead advisor:

1. Check the page's `stage`. If it is still `analyst`, tell them to press
   **Ready for the lead advisor** (twice) on the page, or, if they ask you to,
   set `stage` to `lead` and `handoff` to now yourself.
2. Give them the page's link (from `_Audit/review_pages.json`) in the reply,
   and the two steps: open the page's **Share** menu and add the lead advisor
   with **Can edit** (view-only saves nothing), then send him the link by
   Teams or email. Claude cannot share the page itself.

## Pull in the analyst's check

When the analyst says "pull in my check" / "pull in [client]'s review" and the
page's `stage` is `analyst`:

1. Pull in (mechanics: Pulling in). Read THE ANALYST'S CHECK it prints.
2. Act on every comment: re-read a document that was misread, correct a
   reading in `_Audit` (bank_statements.json, accounts.json,
   doc_readings.json, credit_report.json) only when the document shows it,
   record a typed figure with `inputs.py`, file a document, rebuild the step
   it changes. Say plainly what was done about each comment and what could
   not be done.
3. Re-seed and refresh the page's data (never its stage or comments).
4. Tell the analyst it is refreshed, and that when it is clean they press
   **Ready for the lead advisor** and share the page with him (edit access).

## Pull in the lead advisor's review

When the page's `stage` is `lead` and he has pressed Done:

1. Pull in (mechanics: Pulling in).
2. Report: how many questions he marked Send / Answered / Strike, his notes
   and section comments, and that the email is on the page's Email tab, to
   copy into Outlook. A comment on an assumption can be a **Note** (for the
   team; act on it) or a **Question to the client** (it is already on the
   Questions tab and in the email; do not also treat it as an instruction).
   Questions he added with **Add a question** are in the email too; the pull
   in lists them as `custom_questions` in review_decisions.json.
3. Next step: the email goes to the client. When answers come back, he
   presses **Check for new answers and documents** (or the analyst asks).

## Refresh with answers ("refresh [client]'s review with the new answers and documents")

1. Gather what came in: re-pull LaunchBay (fq-launchbay-pull) for portal
   answers and uploads, run intake on new documents, and read any answers the
   team typed on the page (`qanswers`) or forwarded.
2. Put each answer on its question: ArtifactData `update` plan/figures
   `qanswers` (merge; never drop one already there). A comment marked as a
   question has the id `aq_<section>` (analyst) or `lq_<section>` (lead
   advisor), with `.2`, `.3` for a second or third comment on the section.
3. Judge every answer: read it against its question and the documents, and
   record whether it settles the point:
   `python3 fq_auditor/review_page.py judge "<client folder>" <id> ok|short "<one line why>"`.
   Short means it leaves a figure or fact the plan needs unknown (a loan with
   no balance, "both of us" with no split, "I believe" with no statement);
   say what is missing. The seed prints ANSWERS TO JUDGE for any answer not
   yet judged.
4. Put what the answers settle into the plan (`inputs.py`, readings), then
   re-seed and refresh the page's data (mechanics: Refreshing). His marks,
   comments and decisions stay.
5. Tell him in a few lines what came in, which answers settle their question
   and which do not, and what changed in the plan.

## Print the assumptions ("print [client]'s assumptions")

The Assumptions tab has a **Print the assumptions** button that copies this
line. From fq_auditor:
`FQ_ASSUMPTIONS_PDF=1 FQ_NO_CLAUDE=1 FQ_ROOT_FILE=/tmp/fqroot python3 build_outputs.py "<client folder>" --what assumptions --outdir "<client folder>"`.
It saves `Assumptions - <Surname>.pdf` in the client folder, the same
sections as the page, ready to print. Present the file so it opens; it
prints from Preview. Comments written on the page are not printed on it.
(Only if someone asks for room to write notes: `FQ_ASSUMPTIONS_PDF=notes`
adds a ruled notes column.)

## The slide library

On the Slides tab, **+ Add a slide after** opens the slide library first:
occasional slides the team has used (practice model options, transition
options and timeline, a fork in the road, future trending, worst case
planning, sole prop vs S-corp, the hierarchy of managing cash, practice
concerns, permanent life insurance, a deeper investments look, corporate
debt structuring), then the blank layouts. The built-in ones are
`fq_auditor/slide_library.json` (generic wording, never a client's); the
ones the team saves are `Prospects/FQ_Toolkit/Slide library (team).json` on
the share. Pictures of the built-in ones are in the page; after changing
the library run `python3 fq_auditor/slide_layouts.py` and republish the page.

At pull-in each library slide prints LIBRARY SLIDE with what it needs:

- Fill every `[bracket]` with this client's figures (from the plan, the
  projections, the documents) in `review_decisions.json` `deck_slides.added`
  and on the page's `slide_add` (ArtifactData `update`, pinned), before the
  deck is built. A figure you cannot find stays in brackets; say which.
- **Investments: deeper dive** first needs a deeper analysis of the
  statements: holdings and allocation, fund and advisory fees, cash drag,
  concentration, and returns against Four Quadrants' over the same dates
  (the fq-investments prospect-portfolio-review method, if installed). Fill
  its fields (layout `deep_dive`): `title` (the finding, a few words;
  `title_accent` the words to colour orange), `note`/`sub` (top right),
  `bars` (up to 8 sectors, position weighted, with ~%), `mix` (cash, equity,
  bonds of the steerable money), `mix_note`, `card_head`/`card_body` (the
  biggest concentration and which funds build it; `**bold**` allowed),
  `recur_head`/`recur_rows` (stocks in more than one fund's top 10, ticker
  and fund weights), `recur_note`, `zoom_head`/`zoom` (the share with no
  published holdings), `zoom_body`, `band` (the takeaway, two parts, the
  second in orange). Tell the lead advisor the main findings.
- A slide marked **Save to the slide library** prints SAVE TO THE SLIDE
  LIBRARY: make it generic in `review_decisions.json` (names and figures to
  `[brackets]`), then run `review_page.py savelib`. It shows in every
  client's library from the next refresh.

## Pull in and build the deck ("pull in and build [client]'s consult deck")

1. Pull in (mechanics: Pulling in). The recommendations he left ticked become
   the savings table; his figures and assumptions go into the plan inputs.
2. Act on every note and client answer printed, before anything else, and say
   what was done about each. Items he marked **Team to revisit** (printed FOR
   THE TEAM TO REVISIT) are raised with the analyst before the deck is built;
   **Still open** items are already back on the Questions tab.
3. Build the deck, in the same run: from fq_auditor,
   `FQ_NO_CLAUDE=1 FQ_ROOT_FILE=/tmp/fqroot python3 build_outputs.py "<client folder>" --what deck`.
   It saves `Consult deck - <Surname>.pptx` in the client folder; it opens in
   Keynote. Say how many places are still marked [ADVISOR] for him to write,
   and that the deck can be rebuilt any time after he changes the page.
4. Things the deck now does on its own; check them in what you report:
   - **Two earners.** When the spouse draws a W-2 from the practice, record
     the plan in the deck entry before building (`inputs.py` or the pull in):
     `income_w2_spouse_proposed` (a year), and if known `income_w2_spouse`
     (today), `income_distributions_proposed` (a month), `rent_home` (a month),
     `roth_to_traditional` (yes), `savings_increase` (a month), `spouse_name`.
     The pay slide then shows both W-2s, distributions and rent taken home.
   - **The current path** slide (today's savings and spending carried
     forward, when it runs out, how much rides on the sale) goes in before
     the annual savings. `no_current_path: yes` in the deck entry leaves it out.
   - **Levers on the year to date**: patients a day, production per patient
     and new patients are sized "back to last year's" when this year has
     slipped.
   - **Names from other clients**: the build prints NAMES FROM OTHER CLIENTS
     if the deck holds one. Say each to the lead advisor before it goes out.
     The same check runs on any deck: `python3 fq_auditor/deck_check.py
     "<deck.pptx>" "<client folder>"`. Names the team's master deck carries
     are listed in `Prospects/FQ_Toolkit/Deck name check (team).txt`.
