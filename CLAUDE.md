# FQ Toolkit (prospect pipeline): read this first

Four Quadrants advises dental practice owners. This toolkit takes a prospect
from their uploaded documents to the consult deck. The people changing it are
analysts, not developers: explain changes in plain words, keep answers short,
and do the work rather than describing it.

## The pipeline, in order

Claude is the front door: the analyst asks for each step in a Claude session
with the toolkit and the Prospects folder connected, and Claude runs the code
below. The work happens in three stages, and nothing from a later stage is
built early.

**Stage 1, initial review** (the initial document list)

| Step | Code (fq_auditor/) | Output |
|---|---|---|
| LaunchBay pull (Claude skill) | lb_fetch.py, lb_checklist.py | launchbay_*.json, checklist |
| Intake: audit, file, report open items to the analyst | audit.py, classify.py, checklist_claude.py, intake_email.py | Documents/ tree; the open-items list in the chat (a follow-up email only if asked) |
| Initial notes | facts.py, workbook.py, credit.py, doc_readings.py | Initial notes .xlsx in the client folder |

Then the team holds the consult offer call. No cash flow, assumptions or
portfolio work happens before the client accepts the consult.

**Stage 2, consult accepted** (the Expanded List is sent and comes back)

| Step | Code (fq_auditor/) | Output |
|---|---|---|
| Pull and intake again, for the expanded documents | as above | |
| Cash flow | bank_claude.py, statements.py, transactions.py, cashflow.py, cashflow_book.py | Cash flow .numbers, bank_statements.json |
| Portfolio analysis | accounts.py (and the prospect-portfolio-review skill) | accounts.json |
| Assumptions | assumptions.py, deck_drafts.py, recommendations.py | the review page's Assumptions tab (a PDF only on request), income_facts.json |

**Stage 3, the lead advisor's deep dive and the consult**

| Step | Code (fq_auditor/) | Output |
|---|---|---|
| Analysis review, analyst's check: the analyst works the page first, Claude fixes what he flags | review_page.py, assets/review_page.html | review page on claude.ai (stage "analyst") |
| Analysis review, lead advisor: the analyst hands it over; he checks and picks his questions | as above | the same page (stage "lead"); the questions email is copied from it |
| Answers come back: intake, then rebuild what changed | as above | |
| Consult review: plan, recommendations, projections, slides | review_page.py | review page on claude.ai |
| Deck | deck_template.py (+ plan.py, savings.py, levers.py) | Consult deck .pptx |

The app (`fq_app.py`, port 8765) is kept as a fallback only; day to day the
steps run through Claude. `fq_auditor/SETUP.md` is the operator guide; the
`plugin/fq-prospect` folder holds the Claude skills.

## A short request means the whole step

The analyst says one line ("build [client]'s initial notes", "build [client]'s
assumptions"). Claude does everything that step needs without being told:

1. **Find the client folder** under `Prospects/2026` by surname. Work in it
   (the live folder) unless the analyst says test.
2. **Read the whole folder first**: IC form, call notes (.eml, .pages, scans),
   the initial docs list, and anything the team made (e.g. their own initial
   notes). See "Read the whole client folder" below.
3. **Run any earlier step that is missing or stale, in order.** No
   `launchbay_manifest.json`, or older than 3 days: pull from LaunchBay. New
   documents not yet filed: run the intake. Then the step asked for. Say in
   one line which earlier steps you ran.
4. **The intake always ends with a report to the analyst**: every checklist
   item as received, answered in the portal, or open, with the open items
   listed plainly. The analyst decides which of those are truly needed before
   the consult offer call. Team comments ("we have everything", a consult
   already booked) and portal answers count as received.
5. **No client email unless the analyst asks for one**, after they have
   picked the open items to chase.
6. **If the team's own version of the output is in the folder** (their
   initial notes, Assumptions PDF, deck), compare against it and say which
   figures match and which do not before calling the step done.

## Where this is heading (the evolution list)

Not built yet; raise these when the work touches them.

- **Initial notes as a shared document.** Today they are an .xlsx in the
  client folder; without Excel it opens as an unsaved Numbers copy and saves
  to Downloads unless someone picks the folder. Aim: notes that are easy to
  read, create and edit in one shared place (a Claude page or a cloud doc),
  where the lead advisor's edits come straight back without a "BB" copy.
- **Deck slides still built by hand:** S-corp comparison, current path,
  household allocation.
- **Tax analyzer in the initial notes:** a few plain lines from the returns,
  like the lead advisor's "tax analysis" tab on Burgin: entity type and what
  it costs, refunds or balances due by year (the "surprise"), late or
  amended filings, whether quarterly estimates moved with income.
- **Planning figure** for clients who save nothing: ask the lead advisor
  whether he uses one, and make it the rule.

## Setting someone up

The toolkit runs from the share: `Analysis/Brogan/Prospects/FQ_Toolkit/prospectPip`,
so connecting the Prospects folder gives a chat both the code and the
clients. `START_HERE.md` (copied to `Prospects/START HERE - FQ Toolkit.md`)
is the script Claude follows to set up a new Mac. Edit the repo copy and copy
it to the share when it changes.

## A new Mac, or "check the FQ toolkit is ready"

Run `python3 fq_auditor/readycheck.py "<Prospects folder>"`. It lists any
missing library or tool with the command that installs it in the workspace;
install them, run it again, and say it is ready. The Mac itself needs only
the Claude app, the Analysis share and the cloned toolkit (SETUP.md Part 1).

## Rules that are not negotiable

- **No client data in git.** `.gitignore` is an allowlist (code and docs only).
  Never paste real names, account numbers, birthdates, balances or file names
  from a client folder into code, comments or docs: invent examples ("Dr. Jane
  Example", 7-digit figures). `fq_auditor/precommit_check.py` blocks commits
  that look like client data; never bypass it.
- **No staff names** anywhere in the pipeline: "the lead advisor", "the
  analyst", "the onboarding specialist".
- **Work on `_TEST` copies** under `Prospects/2026/_TEST/`, never inside a live
  client folder unless the analyst asks.
- **Claude reads; code checks.** Anything Claude reads from a document (bank
  statements, credit reports, returns, accounts) must be checked against the
  document: bank statements must balance to the dollar, figures must appear in
  the text. Unchecked values are flagged, never used quietly.
- **Team seat, not API billing.** `ask_claude.py` calls the signed-in Claude
  Code CLI and refuses to run if `ANTHROPIC_API_KEY` is set. Keep it that way.
- **Never start fq_app.py from a sandbox without `FQ_ROOT_FILE=/tmp/fqroot`**
  (it would overwrite the analyst's saved client root). In a sandbox with no
  Claude login, set `FQ_NO_CLAUDE=1`: saved readings in `_Audit` are used.
- **No em dashes** in anything the team or clients read.

## Emails to the client

Claude never sends or drafts email in anyone's mailbox. The intake follow-up,
written only once the analyst has picked the open items to chase, is shown in the chat as plain text for the analyst to copy into Outlook (and
saved as `_Audit/Intake follow-up - <Surname>.txt`). The later questions email
is built on the lead advisor's analysis review page and copied from there.

## Read the whole client folder, not only the documents

Beside `Original_sourcedocs` the client folder holds what the team gathered
before any document arrived: the IC form (`IC form.eml`), the onboarding
specialist's notes (often a scanned PDF with handwriting), and the Otter call
summary (`.pages`). The audit and the initial notes both use them:
`intake_form.py` reads the IC form, `checklist_claude.call_context` gives the
form and call notes to the checklist check, and `notes.py` reads the call
notes. Handwriting cannot be OCR'd reliably, so Claude looks at those pages
itself. Where what the client said disagrees with the documents (no associates
on the form, a second doctor in the production report), that is a flag for
the team, not something to resolve quietly.

## When the code's readers miss a document

The readers know a few layouts (QuickBooks P&L, comparative 1120-S page,
Dentrix Practice Analysis, the firm's debt schedule). When a client's documents
are in another layout, Claude reads them and writes `_Audit/doc_readings.json`
(format in `fq_auditor/doc_readings.py`). Every figure must appear in its
document and every total must tie, or it is left out. Run
`python3 fq_auditor/doc_readings.py "<client>"` and fix anything it lists
before building.

## How to check a change

- `python3 -m pyflakes <file>` on what you touched.
- Run the step on a `_TEST` client: `python3 build_outputs.py "<client>" --what
  cashflow` (or workbook, assumptions, deck), and compare against the lead
  advisor's own work for that client in `_TEST/_Converted/2.) Signed/<client>/`
  (initial notes, Assumptions PDFs, consult decks). Say which figures match and
  which do not.
- The app's dots go orange when code an output is built from changes; that is
  expected after a change. **Update** rebuilds.

## Committing

```
git add -A && python3 fq_auditor/precommit_check.py && git commit -m "..." && git push
```

Do not run git write commands from a sandbox that mounts the repo (it can
leave a lock file); give the analyst the command instead.
