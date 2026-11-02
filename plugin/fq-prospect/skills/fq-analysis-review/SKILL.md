---
name: fq-analysis-review
description: "Build, load or pull in a Four Quadrants prospect's ANALYSIS REVIEW, which is also how the ASSUMPTIONS are built and reviewed: one page whose first tab is the assumptions, then what the documents show, the follow-up questions and the client email. Use when someone says \"build [client]'s assumptions\", \"load [client]'s assumptions\", \"assumptions for [client]\", \"load [client]'s analysis review\", \"make the analysis review for [client]\", \"refresh [client]'s analysis review\", \"pull in my check\", \"pull in [client]'s analysis review\", or \"pull in [client]'s questions\". Comes after the cash flow, and before the consult review."
---

# Analysis review

The review page for a prospect's analysis, worked in two passes on the same
page:

1. **The analyst's check: the Assumptions only.** A new page opens in the
   analyst stage and shows the Assumptions and What we found tabs (so the analyst sees what the documents already settle). The analyst comments on
   any section that is wrong or missing and asks Claude to pull in the check.
   Claude fixes what the comments point to and refreshes the page. Repeat
   until it is clean, then the analyst presses **Ready for the lead advisor**
   (twice: the second click confirms). The page then shows the sharing steps
   and its own link.
2. **The lead advisor's review: every tab.** Assumptions, What we found,
   Questions and Email. He sees the analyst's comments above his own boxes. He decides the questions (the
   analyst's marks are his starting point), comments, and the email to the
   client is built on the page from the questions he keeps.

Read `references/mechanics.md` for how pages are found, seeded, published,
refreshed and pulled in.

## Load (also: "build the assumptions")

"Assumptions" and "analysis review" are one step to the analyst: the
assumptions are built and then shown as the page's first tab. Never make a PDF
unless asked.

1. Find the toolkit and the client folder (mechanics: Finding things). Check
   `_Audit/review_pages.json` for an existing analysis page; if there is one,
   this is a refresh, not a new page.
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
3. Seed with `--mode analysis`. A new page starts in the analyst stage.
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
   copy into Outlook.
3. Next step for the analyst: the email goes to the client; when answers come
   back, new documents go through intake and an update; typed answers go in
   the boxes under each question on this page; then load the consult review.
