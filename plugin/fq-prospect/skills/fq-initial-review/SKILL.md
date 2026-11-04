---
name: fq-initial-review
description: "Stage 1 of the Four Quadrants prospect pipeline: run the INTAKE (pull, audit, file, and report the open items to the analyst), then build the INITIAL NOTES. Use when someone says \"build [client]'s initial notes\", \"initial notes for [client]\", \"run [client]'s intake\", \"file [client]'s documents\", or \"what is [client] missing\". One line is enough: this skill runs the LaunchBay pull and the intake itself when they have not been done."
---

# Initial review (Stage 1)

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
2. **Read the whole folder first**: IC form, call notes (.eml, .pages,
   scanned PDFs: look at handwriting yourself), the initial docs list, and
   anything the team already made, such as their own initial notes.
3. **Run what is missing, in order.** No `launchbay_manifest.json`, or older
   than 3 days: run the fq-launchbay-pull skill. Documents not downloaded:
   `python3 fq_auditor/lb_fetch.py "<client folder>"`. Not filed: the
   intake (`audit.py ... --file-them`, then Claude's checklist check). Say in
   one line which of these you ran.
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

- **Patients = patients seen (visits)** from the day sheet or production
  report, never the active patient count. If a count runs past the money
  figures (to Oct 30 against a P&L to Sep 30), set `counts.ytd_months` and
  note it on the row.
- **`extra` rows** for the by-year tab: year-end bank balances, distributions
  (draws, owner taxes, retirement) and professional fees, from the balance
  sheets and P&Ls, one source per year. Mark a balance `"balance": true` (never
  annualized), and give `ytd_months` when a row's newest year runs to a
  different month than the year-to-date column.
- **`cash_light`**: each practice bank account, statement by statement (start,
  in, out, end, interest, transfers to the client's own accounts). Every
  statement must balance. This is the light Stage 1 version, not the cash
  flow analysis.
- **`_Audit/summary.json`** for the Summary tab: areas to improve (drafted
  from the flags, for the lead advisor to edit), averages (stated, average,
  use) and a savings projection (start, age, retirement age, paths: stated
  savings at 8.5%, +20% at 9%, and a conservative pair).
- **Notes** flag when the IC form does not add up (chairs) or the call notes
  disagree (dependents), and carry the call's details onto their rows
  (spouse, advisors, accounts, tax habits, what they are torn between).
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
