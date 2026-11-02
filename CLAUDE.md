# FQ Toolkit (prospect pipeline): read this first

Four Quadrants advises dental practice owners. This toolkit takes a prospect
from their uploaded documents to the consult deck. The people changing it are
analysts, not developers: explain changes in plain words, keep answers short,
and do the work rather than describing it.

## The pipeline, in order

| Step | Code (fq_auditor/) | Output in `<client>/_Audit` |
|---|---|---|
| LaunchBay pull (Claude skill) | lb_fetch.py, lb_checklist.py | launchbay_*.json, checklist |
| Intake: audit, file | audit.py, classify.py, render_html.py | Intake Review, Filing Log |
| Initial notes | facts.py, workbook.py, credit.py, doc_readings.py | Initial notes .xlsx, credit_report.json, doc_readings.json |
| Cash flow | bank_claude.py, statements.py, transactions.py, cashflow.py, cashflow_book.py | Cash flow .numbers, bank_statements.json |
| Assumptions | assumptions.py, accounts.py, deck_drafts.py, recommendations.py | Assumptions .pdf, accounts.json, income_facts.json |
| Analysis review / consult review (Claude) | review_page.py, assets/review_page.html | review pages on claude.ai |
| Deck | deck_template.py (+ plan.py, savings.py, levers.py) | Consult deck .pptx |

The app is `fq_app.py` (local web page, port 8765), started by
`Open FQ Toolkit.command`. Builds run `build_outputs.py`. `SETUP.md` is the
operator guide; the `plugin/fq-prospect` folder holds the Claude skills.

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
