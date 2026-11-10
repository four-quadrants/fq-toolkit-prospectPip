---
name: fq-initial-review
description: "Stage 1 of the Four Quadrants prospect pipeline: run the INTAKE (pull, audit, file, and report the open items to the analyst), then build the INITIAL NOTES. Use when someone says \"build [client]'s initial notes\", \"initial notes for [client]\", \"run [client]'s intake\", \"file [client]'s documents\", or \"what is [client] missing\". One line is enough: this skill runs the LaunchBay pull and the intake itself when they have not been done."
---

# Initial review (Stage 1)

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

The analyst says one line. Do the whole step without asking for more.

## Before anything

Everything is in one folder on the share: `/Volumes/Analysis/Brogan/Prospects`.
The toolkit is `Prospects/FQ_Toolkit/prospectPip`; clients are under
`Prospects/2026`. If that folder is not connected to this chat, ask for it
yourself with the folder-access tool (`request_cowork_directory`) and tell the
analyst only "click Allow". Never ask the analyst to find a folder by hand.

Read `Prospects/FQ_Toolkit/prospectPip/CLAUDE.md` (the toolkit's rules) and follow its
section "A short request means the whole step". The short version:

1. **Find the client folder** under `Prospects/2026` by surname. Work in the
   live folder unless the analyst says test.
2. **Read the whole folder first, every file in it**: the IC form, the
   sales lead's notes and the call transcript or Otter summary (.eml, .pages,
   .pdf), the initial docs list, and anything the team already made. A
   scanned or handwritten PDF has no text: render its pages and read them as
   images (the sales lead writes priorities, payer details, family and
   background in the margins). `notes.py` passes the text of every file it
   can read; the handwriting is on you.
   **Check the two inputs the notes cannot do without** before building
   them: `python3 fq_auditor/notes_inputs.py "<client folder>"`. It looks for
   the IC form and the initial call notes (the sales lead's notes, or the
   call's transcript or Otter summary). If either is missing, stop and tell
   the analyst plainly which is still needed and that the initial notes wait
   for it; build only if they say to go ahead without it, and then say in the
   notes which input was missing. The intake (steps 3 and 4) can still run.
3. **Run what is missing, in order.** No `launchbay_manifest.json`, or older
   than 3 days: run the fq-launchbay-pull skill. Documents not downloaded:
   `python3 fq_auditor/lb_fetch.py "<client folder>"`. Not filed: the
   intake (`audit.py ... --file-them`, then Claude's checklist check). Say in
   one line which of these you ran.
   **Not everything comes through LaunchBay.** Production reports emailed to
   the analyst, QuickBooks reports the team pulled with the client's login,
   screenshots of a client's email: ask the analyst whether anything came by
   another route, and have it dropped into the client folder (or
   `Documents/`) before the notes are built. A team-filed `Documents/`
   folder in the live client folder is where to look first.
4. **Report the intake to the analyst** before anything else: every
   checklist item as received, answered in the portal, or open, then the open
   items as a short list. The analyst decides what is truly needed before the
   consult offer call. Team comments (documents complete, consult booked) and
   portal answers count as received; never call those missing.
5. **No client email unless the analyst asks**, after they pick what to chase.

## Claude's readings (do these yourself)

The notes are only as good as two files Claude writes into `_Audit`:

- `notes.json`: the analyst's lines (composition, movement, contradictions
  between the IC form, the call notes and the documents). Format and rules in
  `fq_auditor/notes.py`.
  Notes on the "by year" rows count too: key them by the row's label
  ("days worked, all doctors", "new patients", "gross production"...). Any
  portal comment or call note about a yearly figure goes on its row, with
  what was said, when, and the years it covers.
- `doc_readings.json`: figures from documents the code's readers do not know
  (P&Ls, returns, production, counts, debts). Format in
  `fq_auditor/doc_readings.py`; check it with
  `python3 fq_auditor/doc_readings.py "<client folder>"` and fix what it lists.

What the lead advisor expects in every initial notes (format in
`fq_auditor/doc_readings.py`):

- **Patients = patient VISITS in the period** ("patients seen" on a day
  sheet). Never a unique, total or active patient count: if that is all they
  sent, leave the row blank and note "wrong metric, need patient visits". If a count runs past the money
  figures (to Oct 30 against a P&L to Sep 30), set `counts.ytd_months` and
  note it on the row.
- **`extra` rows** for the by-year tab: year-end bank balances, distributions
  (draws, owner taxes, retirement) and "legal, accounting and consulting
  (P&L)" (every such P&L line, summed: give `parts` per year), from the
  balance sheets and P&Ls, one source per year. From the returns, with
  `"basis": "tax"`: distributions (1120-S Schedule K 16d) and any loan to or
  from the shareholder (Schedule L), noted as a question for the call.
- **Every return on file**, whatever the file is called ("Action needed...
  please sign" is often last year's return): read it into `tax` and add its
  year as an earlier column. Note filing timeliness from the preparer's
  cover-letter date and any Form 4868 / 7004.
- **Gross production = the practice-wide day sheet total.** Provider reports
  give the doctor/hygiene split: add them with `"split_only": true`. For the
  same dates the two should agree; when they do not, say why on the row (a
  report run on a different day, deleted services).
- **Rental property:** ask for the lease and rent figures. **Fees quoted on
  the initial call:** put the range in summary.json `info.fees`, marked
  "quoted on the initial call".
- **Depreciation includes amortization.** On a Schedule C the amortization
  (patient records, goodwill) is in other expenses: `da_parts` takes both,
  matching the preparer's depreciation summary grand total. Mark a balance `"balance": true` (never
  annualized), and give `ytd_months` when a row's newest year runs to a
  different month than the year-to-date column.
- **`cash_light`**: each practice bank account, statement by statement (start,
  in, out, end, interest). Two separate columns: `transfers_out` = moves
  between the practice's own accounts (a sweep to operating or savings: not
  money leaving the practice), and `to_owner` = business to personal (owner
  draws to his accounts and personal bills the practice paid: personal tax
  estimates, student loans). Only `to_owner` is totalled. Rent to the
  owner's building entity goes in neither; say so in the note. Every
  statement must balance. The sheet adds the monthly averages and the
  all-accounts totals; the target balance is the lead advisor's to type.
  This is the light Stage 1 version, not the cash flow analysis.
- **Notes in depth wherever the call or the form said something:** what they
  said about their CPA, advisors, spouse, accounts, taxes, staff, and what
  they are torn between, each on its row.
- **`profile.entity`**: anything about entities beyond the returns (a building
  LLC, a K-1 from another practice). The Entity structure row at the top
  adds it to the entity type the returns show. `profile.premises` ("condo")
  when they own a condo rather than a building.
- **Debts**: the code shows rate, payment, original amount and year, the
  full term, fixed or variable, and lists what is MISSING. Loans of the LLC
  that owns the office building go in `debts.building`, not personal: the
  sheet shows them as their own lines inside practice debt, with a practice
  plus building total (the lead advisor counts them with the practice, since
  the practice's rent pays them). A home or a rental is personal. Fill what the
  documents give; leave the rest to show as missing.
- **`_Audit/summary.json`** for the Summary tab (savings projection, 3-year
  average results, areas to improve with CHECK placeholders, info due /
  consult / fees). Savings: if they save something, project it (8.5%) against
  20% more with 4Q (9%), plus a conservative pair; if they save nothing but
  we know what they have saved, project that balance at 8.5% vs 9% with no
  new saving; if we know neither, planning-figure columns. Results: overhead
  falls 10.9% (relative) from the most recent completed tax return's overhead, savings x6.67, income = latest practice income
  base annualized x (1 - overhead with 4Q). Old notes on this key follow.
- Older guidance for summary.json: averages (stated, average,
  use) and a savings projection (start, age, retirement age, paths: stated
  savings at 8.5%, +20% at 9%, and a conservative pair). If the client saves
  nothing (or gives no figure), never invent one: use two paths with
  `"save": null, "planning": true` (8.5% and 9%), which show as "Planning
  figure only (not what the client saves)" for the lead advisor to fill in.
- **Notes** flag when the IC form does not add up (chairs) or the call notes
  disagree (dependents), and carry the call's details onto their rows
  (spouse, advisors, accounts, tax habits, what they are torn between).
  The full list the lead advisor wants is in `notes.py` ("What the lead
  advisor always wants noted"): the IC form's true/false answers both ways
  (pains admitted AND answers the call contradicts), each spouse's ranked
  priorities on "Dentist pain, their words", who they are NOT in network
  with, spouse details on "Marital status", debt growth since the last
  year-end balance sheet, short terms, a pending mortgage net of the home
  sold, IBR resetting with income, collections projected against last year,
  late or possibly unfinal returns.
- **Areas to improve: leave `areas` out of summary.json.** The sheet writes
  the three standard lines (overhead against the 60% target, savings, debt)
  and leaves room; the lead advisor writes the rest. Give
  `"overhead_target"` only when he has said a different target.
- **Tax notes:** entity type, refunds rolled forward, late filings, amended
  returns not sent, quarterly estimates.

The toolkit's own Claude calls (`ask_claude.py`) are not signed in inside this
workspace, so do not wait on them: read the documents and write these files
yourself, then build with `FQ_NO_CLAUDE=1`. The same goes for the checklist
check in the intake (`_Audit/claude_checklist.json`, format in
`fq_auditor/checklist_claude.py`). Without these files the notes come out
half empty.

## Initial notes

`python3 build_outputs.py "<client folder>" --what workbook`, from
`Prospects/FQ_Toolkit/prospectPip/fq_auditor`. If a document is in a layout the readers
do not know, follow "When the code's readers miss a document" in CLAUDE.md.

If the team's own initial notes are in the folder, compare figure by figure
and say what matches and what does not before calling it done. No cash flow,
assumptions or portfolio work in Stage 1.

## If a download is blocked

If `lb_fetch.py` reports "Tunnel connection failed: 403", the firm's network
setting does not yet allow `cdn.filestackcontent.com` in this chat. Give the
analyst this one line to paste into Terminal, then carry on:

    cd "/Volumes/Analysis/Brogan/Prospects/FQ_Toolkit/prospectPip" && python3 fq_auditor/lb_fetch.py "<client folder on the Mac>"
