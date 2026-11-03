# Review pages: the mechanics

Shared by the analysis review and the consult review. Both are the same page
(the toolkit's `fq_auditor/assets/review_page.html`) in two modes, published as
a private claude.ai artifact per client per stage, with a small database (the
`db` capability).

## Finding things

- **The toolkit**: a connected folder containing `prospectPip/fq_auditor/`
  (on the share: `Prospects/FQ_Toolkit`). Call it TOOLKIT.
- **The client folder**: under the connected Prospects folder
  (`/Volumes/Analysis/Brogan/Prospects/2026`), named like "Example, Jane" or
  "Example, Jane - TEST". If the name is ambiguous, ask which.
- If either folder is not connected, request it (request_cowork_directory)
  before anything else. Use the shell paths the session lists for them.
- **Which page belongs to which client**: `<client>/_Audit/review_pages.json`,
  `{"analysis": "<artifact url>", "consult": "<artifact url>"}`. Read it first;
  write it after publishing a new page.

- **First thing in a session**: read `prospectPip/CLAUDE.md` (the rules and
  the map). On a Mac not used before, or if anything fails to import, run
  `python3 fq_auditor/readycheck.py "<Prospects folder>"` and install what it
  lists before going on.

## Seeding (building the page's data)

Run in the shell, from TOOLKIT/prospectPip/fq_auditor:

```
FQ_NO_CLAUDE=1 FQ_ROOT_FILE=/tmp/fqroot python3 review_page.py seed "<client folder>" --out <scratch dir> --mode analysis|consult
```

- `FQ_NO_CLAUDE=1`: the readings Claude makes (statements, returns, accounts)
  were made by the app's builds on the analyst's Mac and are saved in the
  client's `_Audit`; seeding uses those and must not re-read.
- `FQ_ROOT_FILE` keeps the app's own settings file untouched.
- It takes one to three minutes. Use the longest shell timeout.
- It writes `plan.json`, `workings.json`, `slides.json` (consult), `q<id>.json`
  per question, and `slides/*.jpg` (consult) into the scratch dir.
- If it prints that Claude readings are missing (no `bank_statements.json`,
  `accounts.json` or `income_facts.json` in `_Audit`), tell the analyst to
  build Initial notes, Cash flow and Assumptions in the app first.

## Publishing a NEW page

1. Copy `fq_auditor/assets/review_page.html` to a scratch file and change its
   `<title>` to "<Surname> Analysis Review" or "<Surname> Consult Review".
2. Publish it with the Artifact tool: icon `clipboard`, capabilities `{"db": {}}`,
   a one-line description, and for the consult review `files` mapping
   `slides/<n>.jpg` to each picture the seed made.
3. Write the data with ArtifactData `batch` (one call, all `set`):
   `plan/figures` from plan.json, `plan/workings`, `plan/slides` (consult), and
   `questions/<id>` for every q file.
4. Record the URL in `<client>/_Audit/review_pages.json`.
5. Tell the analyst in one sentence what the page is and that the lead advisor
   cannot open it until they share it from the page's Share menu (edit access).

## Refreshing an EXISTING page (new documents or answers came in)

Never overwrite the lead advisor's work. Re-seed, then:
- ArtifactData `get` plan/figures (note its version).
- `update` plan/figures with ONLY the computed fields: `figures`, `findings`,
  `recommendations`, `pics`, `slide_titles`, `question_ids`, `answered_by_docs`, `assumptions`
  (pinned to that version). Leave `decided`, `qdecisions`, `qtext`, `qanswers`,
  `notes`, `recs`, `recs_custom`, `sdecisions`, `stext`, `email`,
  `email_edited`, `assume_notes`, `stage`, `handoff`, `an_notes`, `an_assume_notes` alone.
- `set` plan/workings, plan/slides and every question doc.
- Question ids are made from the question itself, so decisions stay attached.
- Do not republish the page itself unless the page design changed (republishing
  pops it open for the user).

## Pulling in

1. ArtifactData `get` plan/figures with `out_dir` set to a scratch dir.
2. Run, from fq_auditor:
   ```
   FQ_NO_CLAUDE=1 FQ_ROOT_FILE=/tmp/fqroot python3 review_page.py apply "<client folder>" "<saved figures.json>"
   ```
3. It writes `_Audit/plan_inputs.json` (his figures, recommendations as the
   savings table) and `_Audit/review_decisions.json` (questions, wording,
   answers, notes, slide wording), and the follow-up email `.eml`.
4. Read what it prints. **NOTES FROM THE LEAD ADVISOR** and **CLIENT ANSWERS**
   are instructions from him: act on them before the deck is built (for
   example, a client answer that gives a loan balance goes into the plan inputs
   with `python3 inputs.py`, a note saying "hold the 401(k) until 2028" means
   checking the recommendation was moved to that year). Say plainly what was
   done about each one, and what could not be done.
5. Tell the analyst the next step in the app.

## Do not

- Do not publish when only data changed (it opens the page on the user's
  screen). Data writes are silent.
- Do not paste the artifact URL in chat unless asked; the app shows a card.
- Do not edit client documents or `Original_sourcedocs`.
