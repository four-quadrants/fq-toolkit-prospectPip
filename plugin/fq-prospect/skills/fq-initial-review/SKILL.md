---
name: fq-initial-review
description: "Stage 1 of the Four Quadrants prospect pipeline: build a prospect's INITIAL NOTES, and run the INTAKE (file and check their documents). Use when someone says \"build [client]'s initial notes\", \"initial notes for [client]\", \"run [client]'s intake\", \"file [client]'s documents\", or \"what is [client] missing\". One line is enough: this skill runs the LaunchBay pull and the intake itself when they have not been done."
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
4. **The team's word settles the checklist.** Documents also come by email,
   QuickBooks logins and calls. A team comment that the documents are
   complete, or a consult already booked, means nothing is "missing": gaps
   are team notes only.
5. **No client email unless asked.** Only in Stage 1, only on request.

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
