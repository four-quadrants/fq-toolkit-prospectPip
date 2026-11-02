---
name: fq-analysis-review
description: "Load or pull in a Four Quadrants prospect's ANALYSIS REVIEW: the lead advisor's first review page, showing what the documents show (accounts, debts, credit cards, pay from the returns, bank accounts) and the follow-up questions for the client, with the client email built on the page. Use when someone says \"load [client]'s analysis review\", \"make the analysis review for [client]\", \"refresh [client]'s analysis review\", \"pull in [client]'s analysis review\", or \"pull in [client]'s questions\". Comes after the app has built the client's Assumptions, and before the consult review."
---

# Analysis review

The first of the lead advisor's two review pages for a prospect. He checks the
data the plan will rest on and decides which follow-up questions go to the
client. The page writes the email itself as he marks questions; he edits and
copies it from the page's Email tab. Read `references/mechanics.md` for how
pages are found, seeded, published, refreshed and pulled in.

## Load

1. Find the toolkit and the client folder (mechanics: Finding things). Check
   `_Audit/review_pages.json` for an existing analysis page; if there is one,
   this is a refresh, not a new page.
2. Seed with `--mode analysis`.
3. Before publishing, read `plan.json`'s `findings` and the questions, and tell
   the analyst briefly what stands out: accounts or debts that look wrong or
   missing, statements that did not tie, questions that look mistaken.
4. Publish a new page, or refresh the existing one's data.

## Pull in

1. Pull in (mechanics: Pulling in).
2. Report: how many questions he marked Send / Answered / Strike, any notes,
   and that the email is on the page's Email tab (also saved as an `.eml` in
   `_Audit`).
3. Next step for the analyst: send the email (or the lead advisor sends it);
   when answers come back, new documents go through Intake and Update in the
   app; typed answers go in the boxes under each question on this page; then
   load the consult review.
