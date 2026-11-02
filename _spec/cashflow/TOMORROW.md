# BEFORE HANDOFF (must be done before the project is called finished)

- LaunchBay pull on a schedule. The toolkit has no LaunchBay login; only
  Claude with the LaunchBay connector can write launchbay_manifest.json and
  launchbay_tasks.json (skill: fq-launchbay-pull). Today it only happens when
  someone asks. Set up a weekday-morning scheduled task that pulls every
  active prospect, so new uploads are waiting when the app is opened.
  Decide whose Claude account runs it (the firm leaves in a few weeks).
- New-Mac setup for the analyst, as automated as possible: a one-page guide that
  hands him the exact commands in order (xcode-select --install; Homebrew
  installer; brew install python@3.13 tesseract; Claude Code install and
  login; connect smb://192.168.62.170/Analysis), and Install FQ Toolkit
  doing everything it can itself. The launcher already prefers Homebrew's
  python3.13/3.12 (Apple's 3.9 caps numbers-parser at 4.16: no comments)
  and installs every Python library on first start. Run it on the next analyst's Mac
  with him before the firm leaves.
  PLAN (the firm, 27 Oct): install on BRYAN's workstation first (he has a
  Claude seat), with the firm; the analyst hands it on to the analyst after the firm leaves.
  So the guide is written for the analyst to follow alone, and the LaunchBay
  scheduled pull runs on the analyst's Claude.

# Pickup, Thursday 29 October (goal: a working version by end of day)

1. Review page (Oyler Consult Review artifact): "Up to date" shows, so the
   page reaches its store, but the Strike button did nothing for the firm.
   Likely cause fixed in v4: question rows had no id, so clicks wrote to
   "questions/undefined". Retest: Strike on #12, then read back with
   ArtifactData. Typing a figure did save once (plan doc v6) after the v3
   fix. If it still fails, ask for a screenshot of the page.
2. Read-back: page decisions -> _Audit/plan_inputs.json deck entry
   (retire age, income, sale, schedule, concerns) and the email
   (duediligence.write uses Send rows only).
3. Consult deck for Oyler from the decided plan; open in Keynote.
4. Due diligence button in the app (builds questions + email + seeds the
   page), one review page per client.
5. Commit, then run Spaulding end to end as the "working version" check.

# Wednesday 28 October, afternoon

- Cash flow reader fixes: statement 7/01-8/02 is July (missing month),
  average per statement (quarterly counts 3), inclusive first day,
  "Transfer from X to Y" direction from the text, one-offs out of the
  account line, loan payments matched to the client's debt sheet.
  Oyler excl. fixed $14,203 vs the lead advisor $13,985; most accounts exact.
- Assumptions: Reef/Bitcoin back in section 5, x3309 once, personal debt
  named ("Florida Mortgage (Regions x3779)") plus loans paid with no
  schedule (Guaranteed Rate, Truist) marked "balance needed".
- Due diligence: duediligence.py drafts the questions (Oyler 19, close to
  The lead advisor's real email) and the email text. NOT yet a button in the app.
- Concerns on the deck now come from the initial notes' pain points.
- the lead advisor's review page (artifact, db): Oyler Consult Review
  https://claude.ai/artifact/Lwqpd6UhE6h8JMpWSXsjbf  plan figures with
  proposals, workings (start, sale, sources, levers, savings worksheet),
  concerns, questions with Send/Answered/Strike. Seeded via ArtifactData.
  TODO: (1) the firm tests a save; (2) read-back into plan_inputs deck entry
  and the email; (3) make one page per client automatically; (4) share
  with the lead advisor (edit access); (5) due diligence button in the app.
- Levers for hygiene/new patients/fees/per-patient need hygiene days,
  provider split, FFS share: not read yet.

# Pickup, Wednesday 28 October

Where Tuesday ended:
- Cash flow workbook REBUILT on a toolkit-owned layout (cashflow_book.py),
  The firm approved the preview ("much cleaner"): Summary tab, one tab per
  side with identical account blocks, amber editable rows with comments,
  fixed payments and totals matching the Assumptions (Oyler Personal
  $32,958 incl / $13,892 excl), To review tab with a Done column.
  cashflow_review.read_cells now reads this layout by row label.
  The old template writer (cashflow_workbook.py) only supplies constants.
- The template's adjustments had never landed (written onto formula cells).
- iMac now runs Homebrew python3.13 (launcher prefers 3.13/3.12); numbers-
  parser on it is current, so comments work.
- Build buttons: pale blue when built and current, orange when needed.

Oyler vs the lead advisor's live Assumptions (Oyler Assumptions 2026-BB.pages),
27 Oct. Household: excl. fixed $13,892 vs $13,985 (-$93/mo); incl.
$32,958 vs $33,716 (-$758/mo). Per account (dep / exp, toolkit vs BB):
  x0054   47,598 / 49,999   vs 47,359 / 23,785  (toolkit leaves the $100k
          one-off in the account's expense; BB takes it out)
  x0222    8,740 / 5,297    vs  3,333 / 9,086   (transfers classed differently)
  x0393    3,752 / 1,712    vs    250 / 0       (BB: all transfers)
  x1145    2,326 / 125      vs  2,291 / 123     (months vs periods)
  x2683       40 / 950      vs      0 / 935
  x4728  345,453 / 308,892  vs 311,431 / 315,708
  x9399   34,730 / 36,613   vs 33,949 / 26,322
Work these down tomorrow: one-offs out of the account line, and transfers
between his own accounts on x0222, x0393, x4728 and Moonridge.
Rows are 22pt now (were 14pt and clipped). The firm's edit test: the 0 did
not reach cashflow_review.json; the read-back works when tested with a
library-saved edit, so check whether his edit was saved before the rebuild.

First thing Wednesday:
1. The firm rebuilds Oyler's cash flow in the app, opens it in Numbers, edits
   one amber cell, saves, rebuilds: check the change is kept.
2. Build the Assumptions (step 3, button 3) for Oyler; compare to the
   firm's Assumptions answer key.
3. Due diligence (step 4): the questions list, analyst first, the lead advisor's
   email format (_spec/FOLLOWUPS.md); credit report reader.
4. Consult deck (step 5).
5. Find why the second audit pass took 13 minutes on Rebol.

# Tuesday 27 October, midday

Initial notes checked against the lead advisor's on all three TEST clients:
Oyler 58/62, Spaulding 64/67, Rebol 56/60 (open = advisor fields, investable
assets, and a basis difference when the newest return is an older year).
Fixed today: scanned IC forms read by Claude (_Audit/ic_form.json), Otter
.pages read (iwork.py), portal comments fed to the checklist and to the
counts, Schedule C and Aprio-style 1120-S tax basis, Debt Sheet template
(practice and personal, Business column, file-name side), count tables in
.docx, practice address from the letterhead under the dental name, home from
the newest return with a move noted, fee positioning from the study table
when the file name has no % (Rebol -11.26%, Spaulding -4.79%, both exact).
Fee studies are done BEFORE the notes; the notes only read the result.
OPEN: opening Rebol took ~18 min (re-audit after Claude's checklist took
13 of them). Find out why the second audit pass is slow.

# Pickup, Tuesday 27 October (goal: all the way to the consult deck)

## Where Monday ended

- Intake and filing: done on Oyler. Checklist 31 items, 77% (real gaps,
  most sent after his consult). Build File Tree button now grey "All filed"
  when nothing is left (audit writes _Audit/filing_status.json).
- Initial notes: builds in the app (child output was buffered, fixed with
  PYTHONUNBUFFERED). Open + Show in Finder buttons (Numbers imports .xlsx as
  a new doc that saves to Documents, so Finder shows the real file).
- Bug fixed: QuickBooks PDF headers ("January-December, 2025") now set the
  year; the print date had made Oyler's 2025 P&L a 2026 one. Same-year P&L
  copies keep the one with more lines read (spreadsheet over PDF). Oyler
  overhead back to 77.0%; tax basis 74.0% now shows.
- Pain points: DRAFTED (painpoints.py, last block of the initial notes),
  modelled on the lead advisor's Farag, Spaulding, Wright and Kinsler notes: the
  dentist's own words from the IC form's true/false page, then themes with
  the figure behind each (retirement, OH, efficiencies, fees, debt, QB,
  tax/CPA, comprehensive plan), then fee range and timeline for the advisor.
  Call notes are not read yet, so the call's pain goes in by hand.
- Spaulding and Rebol initial notes are thin (13 of 42, 12 of 41 facts):
  neither TEST folder has an IC form, and Spaulding's tax-basis overhead is
  not read (the lead advisor has 80.70% for 2025). Check these first Tuesday. 2026 YTD doctor
  wages read 0 (the 2026 P&L used is a PDF print).
- Never run fq_app.py in the sandbox without FQ_ROOT_FILE set: it overwrote
  The firm's .fq_root on Monday.

## Tuesday plan

1. Check Initial notes on Spaulding and Rebol after the P&L year fix.
2. Pain points.
3. Assumptions tab (cash flow workbook, review, Assumptions PDF) on Oyler.
4. Due diligence: the questions list (analyst first, then prospect).
5. Consult deck from the plan card. Commit.

# Pickup, Monday 26 October

## Where Friday ended

- Oyler re-pulled from LaunchBay: checklist is now 31 items (initial 11 +
  expanded 20). The August pull only had the initial list. Onboarding-stage
  files (Client File Checklist etc.) left out of the TEST manifest on purpose.
- The re-pull wrote 22 copies of documents already on disk under their
  filed names. Fixed: lb_fetch drops a download whose content matches a file
  already there; build_plan files a second copy wherever the first went.
  The 22 copies were deleted from the TEST folder.
- "Decide these" hint now names Build File Tree, not Save decisions.
- Claude checklist prompt: "most recent" judged as of when sent, not today;
  judge only from the list given. Oyler now 18 satisfied, 7 partly, 6 missing.
- Build buttons no longer fail silently (no client / nothing ticked / busy).
- OPEN: "Build initial notes" did nothing in the app for the firm. The same
  build from the command line works in 31s (47 of 51 facts). So it is the
  app: likely JOB still busy, or the app running old code. First job Monday:
  restart the app, press it, read the log box.
- Handoff to the analyst: intake + initial notes as a pilot next week; due
  diligence and deck after.

# Pickup, Friday 23 October (priority day: make a lot of headway)

## Where Thursday ended

- App is in the firm's order (_spec/SEQUENCE.md): 1 Intake (Client &
  documents / Review & file), 2 Initial notes, 3 Assumptions, 4 Due
  diligence, 5 Consult deck. Redact removed.
- Intake: Claude reads the checklist on every run. Claude Code is now
  installed AND signed in on the iMac (binary at ~/.local/bin/claude). On
  Oyler it answered 11 items: 6 satisfied, 3 partly, 2 missing, against the
  rules' 11 of 11. The app says so out loud if Claude is not signed in.
- Review & file: Oyler's "decide these" went from 66 to 0 (junk files
  skipped, firm files to Consult info / Z.)Planning Team Info, file names
  decide side and folder, ACH flat beside Business and Personal, decree to
  Personal/Misc). PII panel removed; "What to chase" only lists what the
  client owes; "Documents/" no longer shown in folder names.
- Open question for the firm: should the Documents level go on disk too, or
  only on the page?
- the lead advisor's five follow-up emails analysed: _spec/FOLLOWUPS.md.

## First thing Friday

1. The firm: restart the app, Oyler TEST, Re-read and review, check Claude's
   verdicts on the tiles; then walk tabs 2-5 and send notes.
2. Wire Claude into naming/sorting documents (classify_claude.py,
   rename_plan.py exist from the old Mac but are not connected).
3. Calculations tying together, then the due diligence questions list
   (drafted from findings, in the lead advisor's format) and the credit report reader.
4. One full client end to end (Rebol; needs his IC form in the folder).

# Pickup, Thursday 22 October

Written at the end of 21 October.

## What landed on 21 October

**The consultation deck is built.** `deck.py` assembles every slide and its
sources, `deck_pptx.py` renders it, and it is the fifth tick box on the Build
Outputs tab. It opens in Keynote. Any slide still waiting on an advisor decision
prints an amber STILL NEEDED box, so an unfinished deck cannot pass for a
finished one.

**The two models under it are checked against the firm's own files.**

- `savings.py` reproduces the lead advisor's savings worksheet row for row, both paths,
  first year to retirement, on 12 of 13 signed clients
  (`_spec/verify_savings.py`). The 13th, Kinsler, has a fault in her own
  sheet: three different sale years.
- `levers.py` reproduces every lever in the analyst's Kinsler model, plus the top-five
  subtotal and the worst case (`_spec/verify_levers.py`).
- End to end, fed the lead advisor's inputs, the deck matches his Spaulding slides
  exactly: $6,015,214, run-out 2074, $158,000 on pace, $20,641,917. Rebol also
  matches exactly through 2039. His 2040 differs by $243,600, which is his
  sheet booking the sale differently from his own note.

**The build now runs on clients other than Oyler.** This morning Rebol and
Spaulding got 2 of 4 outputs; now they get all 5. Oyler is unchanged
($13,892 / $32,958, 77.0%, $6.77m, $1,378,287), rechecked after every change.

**A cross-client leak, fixed.** When a client had no IC form, the toolkit took
whichever IC form it found one folder up. Rebol's and Spaulding's plans were
being built from Oyler's. See `intake_form.find_form_near`.

**Late on 21 October the deck moved onto the firm's own template.**
`deck_template.py` opens `assets/consult_template.pptx` (the firm's redesigned
Oyler deck, exported from Keynote) and changes only the words, so the output
keeps the Barlow fonts, colours and layout and edits in Keynote like the
original. Client figures are written into their shapes. The advisor's prose is
replaced with `[ADVISOR: write this]` or `[TBD]` and never echoed, so nothing of
Oyler's can carry over (checked by scanning Rebol and Spaulding for Brian,
Oyler, Reef, AuguStar, Indiana and his figures). Debt, tax example and
larger-practice slides drop out when there is nothing for them. Fed Oyler's
own inputs it reproduces his savings-future slides ($10,792,517 and
$12,872,517); fed Spaulding's it gives $20,641,917, which is exact.
`deck_pptx.py` is superseded and can be deleted. The template IS in git,
scrubbed: `_spec/build_template.py` turns the designer's Keynote export into it,
blanking every client figure and the advisor's words and turning the names into
{FIRST} and {SURNAME}, and refuses to write it while anything of the source
client survives. `.gitignore` names that one file. When the design changes,
export from Keynote and rerun build_template.

The firm's edit test (21 October): edits in Keynote held and exported back
cleanly. Keynote deletes empty text boxes on save, so unused cells are now
[TBD] rather than blank, and the savings-projection totals are left to the
advisor.

## The advisor's inputs

They live in `_Audit/plan_inputs.json` under `deck`. There is no form for them
yet; the next job is a screen in the app. The keys:

    target_income, savings_schedule [[year, amount], ...], sale_net,
    sale_net_fq, tax_split {withholding, estimates}, tax_current
    {withholding, estimates, total_tax}, current_savings, current_expenses
    (overrides the measured figure), retire_age, age, horizon_age,
    target_overhead, fq_first_year_rate, concerns [...], income_structure
    {w2, distributions, deferrals_current, deferrals_proposed}, fees
    [[row, year1, year2], ...], names, consult_date, consult_date_text,
    start_portfolio, building_value, levers {...}

The Rebol and Spaulding TEST folders carry the lead advisor's inputs under that key,
labelled as verification. Oyler's carries only target income and current
savings, because the years of his savings steps are not written down
anywhere I could find.

## FIXED: the review page layout (21 October, evening)

Cause found: render_html.py called load_claude_verdicts() and nothing defined
it, so every audit on the iMac printed "(html render failed: ...)", wrote the
memo and email but no review page, and the app kept showing the August page.
Defined it; a test audit of Oyler TEST now writes the page with the tiles and
no second logo. pyflakes finds no other undefined names. The Review tab
redraws stale pages itself, so opening each TEST client brings it current.

Agreed plan, in the firm's order:
1. Decide the overall sequence of steps in the app.
2. Fine-tune the calculations so everything ties together.
3. Run one full client end to end: pull documents from LaunchBay through to
   the finished consult deck.

## (history) the review page layout

The firm re-ran the audit on the new iMac and still saw the old review layout.
What is known:

- the firm's re-run wrote no new review page. Searched all of 2026 at 15:16:
  the newest Intake Review.html is still Oyler RERUN - Sep30 (12 Oct). Every
  other one dates from Aug or early Sep. So that run failed or stopped before
  drawing the page; its progress log will say where.
- The 12 Oct RERUN page is the newest layout in git: a donut, small green /
  orange / grey status squares, collapsible checklist groups, no second logo
  (render_html.py, commits 3cf7e19 and later). A copy is in the session
  outputs as review_oct12_layout.html.
- SETTLED: The firm confirmed that IS the layout he means (progress ring,
  small tiles, collapsible checklist). It is in the code. The only problem is
  that the audit run on the iMac did not get as far as writing the page.
  First job: get his progress log, find where the run stops, fix it, then
  re-audit the TEST clients so each has the current page.
- (Earlier question, now answered:) is that the layout the firm means? If not, the newer one may
  have lived only on the old Mac, uncommitted or in a file outside git's
  allowlist (it only keeps .py and .md). Check the old Mac's
  FQ_Toolkit/prospectPip for anything newer than 12 Oct.

## Consult plan card (Build Outputs tab)

"Work out the plan" shows what the documents and models give: retirement
income, wealth, the sale, years 1-3 saved, the basics (each worked-out figure
as the placeholder), the table of savings sources with proposed invested
amounts, and five concerns. "Save the plan" writes the deck entry in
_Audit/plan_inputs.json (merged; an emptied box goes back to the worked-out
figure) and works it out again. The deck is then built from it. The table is
kept only if the advisor changed it.

## Next

1. **The advisor form in the app.** It writes the `deck` entry. It is the last
   thing between the deck and the team.
2. **A 1040 reader** for the tax slide (lines 24, 25d, 26). The figures sit
   apart from their labels in the extracted text, the same problem the
   statements had, so `statements.layout_text` is the place to start.

## Still open

- **Patient counts and the provider split are not read,** so the hygiene, new
  patient and per-patient levers wait on a typed input. Overhead, collections
  and adjustments compute.
- **The card-payment rule is unsettled.** Reading "Withdrawal" as borrowing is
  wrong, but fixing it moves Oyler from $13,892 to $12,973. The note is in
  `transactions.BORROW_WORDS`.
- **Rebol's answer keys contradict each other** ($16,505 Assumptions, $28,506
  workbook, $31,924 deck). Spaulding and Oyler are the trustworthy tests.
- **The Spaulding TEST folder has no personal bank statements.** The lead advisor used a
  Chase x2682 that is not in it.
- The x0054 $100,000 settlement in the surplus block; ten statements unread.

## On the new iMac

Run `python3 -m pip install --user python-pptx`. The preflight now checks for
python-pptx, numbers-parser and reportlab, and suggests `--user` on Apple's
Python, where it used to suggest `--break-system-packages`.

## Thursday Oct 29, afternoon: deck drafts

- Deck now fills investments (94% illiquid, bar, what's inside) from the data. Advisor markers 135 -> 85.
- New fq_auditor/deck_drafts.py: Claude drafts the remaining boxes (tax red flags, pay structure, returns, fees)
  in one call on the team seat, cached in <client>/.fq_cache/drafts. A draft quoting a figure not in the fact
  pack is thrown away. Presenter notes list the drafted boxes. FQ_NO_DRAFTS=1 turns it off.
- Box-by-box examples: fq_auditor/assets/deck_examples.json, built by
  python3 _spec/build_deck_examples.py "<the lead advisor deck>.pptx" Oyler Brian
  It is NOT in git (json). HANDOFF: copy assets/deck_examples.json and consult_template.pptx to the analyst's machine.
- The sandbox claude is not logged in, so drafts were only tested with a stub. First live run is on the firm's Mac.

## Friday Oct 30 plan (handoff Monday)

Done Thursday: review page has slide-by-slide pictures, assumptions group (all rates and rules), pay structure
(slide 11, from Claude reading the returns), 4Q return prompts (slide 15), slide 16 sources from the model, fee and
tax slides left for the lead advisor / accounting. Oyler vs the real deck: 356 of 494 boxes identical, 27 blank by
design (7 tax, 6 fees, 5 4Q, 9 insurance-policy rows), 111 differ (mostly judgment: concerns wording, levers chosen,
custom slide 8 wording, distributions year).

Friday, in order:
0. CREDIT REPORT READER (vital: where most debts and many assets are found). Test files: Oyler has five
   photographed pages (Personal - Credit Reports - IMG_6553..6557.png); Rebol has full PDFs for both spouses
   (CRR and KMR, Equifax / Experian / TransUnion, June 2026). Claude reads each tradeline (creditor, type,
   balance, payment, rate if shown, opened, status, individual or joint), dedupes across bureaus and spouses,
   and the rows join debt.py's list beside the debt sheet and statements, each with its source. Feeds the
   Assumptions section 8, the debt slide, the refinance and the due diligence questions (loans with no
   statement on file).
1. Oyler: rebuild (401(k) deferral from the statement), check slide 11 and 16 again.
2. Spaulding gaps: levers slide empty (no lever inputs found), investments slide empty (start_parts empty though
   start = $312,080). Same check on Rebol.
3. App: rename Build Deck to "Draft the deck for review" / "Build the final deck"; step bar Review dot.
4. Runbook: "load [client]'s review page", "pull in [client]'s review"; one review page per client (copy of the
   Oyler page HTML, new artifact per client).
5. Run Spaulding, Rebol, Prather end to end in the app; load their review pages.
6. Setup guide for the analyst's Mac; scheduled LaunchBay pull; commit.

## Friday Oct 30, end of day: where things stand (handoff Monday)

Built today
- credit.py: credit reports read (Equifax parsed in code, others by Claude; pictures-only PDFs OCR'd by the toolkit
  first). Merged across bureaus/spouses by identical balance+payment. Rebol 5/6 of the lead advisor's loans (the 6th is
  an LLC loan, not on personal credit); found a HELOC the debt sheet missed.
- accounts.py: investment accounts read by Claude from every statement (named by kind/custodian, not just the
  Investments folder). Rebol 6/6 and Spaulding 9/9 (incl. annuity) to the dollar.
- bank_claude.py: EVERY bank statement read by Claude first; used only if it ties (beginning + in - out = ending,
  transactions = totals). Spaulding 14/14 tie. Rebol (73) and Oyler (41) not yet read: their next build does it.
- statements.py: printed account/holder beat the filing folder; Huntington layout reader.
- recommendations.py: catalog of 22 from 8 consult decks; review page checklist with year buttons and notes.
- Two reviews per client: Analysis review (what we found + questions + live email on the page) and Consult review
  (open questions, plan, recommendations, projections, slides). review_page_template in fq_auditor/assets.
- Spaulding: analysis review JZvGC5yjwQrDqg8up4mueu; consult review Qs7D5JCSA19VGmD2Z5nZzh. Rebol consult
  J42FM935RKGnx5NtSibeWo. Oyler (old layout) Lwqpd6UhE6h8JMpWSXsjbf.

Monday, in order
1. Spaulding: lead-advisor pass on the consult review, pull in, build the deck, compare to his real deck.
2. Consult-review load should mark questions answered by documents that arrived since (re-run findings; a question no
   longer raised = "answered by the documents"). The consult review never makes an email.
3. Speed: loading a review page takes 1.5-3 min here; fine for now.
4. Rebol + Oyler: Update once so bank_claude reads their statements; spot-check cash flow vs his.
5. FQ Prospect plugin (skills: LaunchBay pull, load/pull analysis review, load/pull consult review).
6. Setup guide for the analyst's Mac: xcode-select --install; Homebrew; brew install python@3.13 tesseract poppler;
   Claude Code login; mount smb://192.168.62.170/Analysis. Copy assets (consult_template.pptx, deck_examples.json).
7. Commit.
8. GitHub: transfer the repo to the firm's GitHub organization (repo Settings > Danger zone > Transfer;
   needs owner rights in the org), keep it private, give both analysts Admin access. On each Mac afterwards:
   git remote set-url origin <new org URL>. Files git does not carry (allowlist): fq_auditor/assets/
   consult_template.pptx and deck_examples.json; copy them by hand (deck_examples holds masked client wording,
   so it stays out of git).
