# Pick up here — FQ Intake Auditor

---

## 2026-08-21 — renaming is wired in; one cache rebuild needed

**Run this once.** It picks up both the OCR fix and the renaming in a single pass:

```
cd fq_auditor
python3 audit.py "../RedactorTest" --checklist "../Client_File Checklist.pdf" \
  --client "Bassett" --cache .cache_originals --outdir ../audit-results/rebuild
```

**Scale:** 773 pages, but only **198 need OCR** — the other 575 have text layers and
re-extract instantly. Fully resumable; every finished file caches permanently, so
an interruption costs nothing. Roughly 20 minutes on two throttled sandbox cores;
should be well under that on a real Mac with per-page parallelism.

**Now wired into `audit_folder`:**

- `harvest_household_names` → reads the household off the personal tax return
  (Sara, Daniel, Avery Bassett), then `attach_person` puts a name on a document
  only when exactly one household member appears in it. 28 of 95 attributed.
  Abstains on joint documents by design — `Joint brokerage.pdf` gets no person.
- `build_plan` now returns the proposed NAME as well as the destination, then runs
  collision resolution. One function, so the review page, the writeup and the
  rename log cannot disagree.
- `<Client> - Rename Log.csv` is written every run: old name, new name, sha256,
  reason, destination.
- The review page has a **New name** column, and rows needing period confirmation
  or involved in a collision are shaded for attention.

**Known limitation in person attribution.** "Exactly one household name present"
is safe but not sound: a document that simply never mentions the other spouse gets
attributed to the one it does mention. The Cash App statements came out as Sara's
on that basis, which may or may not be right. It does not affect filing (they go
to `Personal/Investments/Cash App` either way) but it does put a name on a file, so
worth spot-checking after the first real run.

**Batching:** applies to the redactor, not the auditor. The auditor is parallel per
page and permanently cached, so batching gains nothing. For Cena, batch by cost —
the scanned tax returns and the 137-page credit report in their own run, the
mostly-text-layer statements in groups of 15–20 — because the win is surviving a
tab crash and seeing results sooner, not less total OCR.

---

## 2026-08-21 — OCR settings changed, cache must be rebuilt

`OCR_VERSION` in `extract.py` went to **2**, so cache files are now
`<sha>.v2.txt`. The existing `.cache_originals` entries are v1 and will be
ignored — **the next run re-OCRs everything.** ~780 pages, resumable, every
finished file cached permanently.

Why it changed: OCR was told the page resolution explicitly (tesseract guesses,
and guesses badly on a rendered page), and pages that come back implausibly thin
now get a second attempt at PSM 6 / 300 dpi, keeping whichever result reads longer.

Measured effect:

| file | before | after |
|---|---|---|
| `Sara W2 2024.pdf` | 401 chars → **unknown** | 865 chars → **w2**, Personal, high |
| `Daniel Term Life Policy Summary.pdf` | 2490 → w2 | 2514 → **w2** (trap still caught) |

**PSM 6 is a rescue pass, not the default, and that is deliberate.** Making it
primary fixed `Sara W2` but broke `Daniel Term Life Policy Summary` — it lost the
W-2 markers that expose it as a mislabeled file, which is one of the answer-key
traps. Same shape as the redactor's escalation: try the alternative, keep it only
if it is actually better.

**Do not classify by filename.** It is tempting for cases like `Sara W2 2024.pdf`,
but four files in the corpus deliberately contradict their names and
`Daniel Term Life Policy Summary.pdf` really is a W-2. Filename trust would break
the thing the auditor exists to catch.

Also new: `owner_side` inference now actually receives the practice's entity names
(harvested from tax returns / P&Ls / payroll — `infer_side` always accepted them
and nothing ever passed them), and searches the whole document rather than just
the head. Unclear bank statements 23 → 17; documents needing a human decision
34 → 24.

---

**State: working end-to-end and scored.** Nothing is running. Everything below is
in `BassetTestDocs/fq_auditor/`.

*(`HANDOFF.md` is from the first night and is now out of date — this file
supersedes it. `extract_cache.py` is the old proof-stage extractor, replaced by
`extract.py`; I couldn't delete it.)*

---

## What's done

All four of your numbered priorities:

1. **Reads every page**, with a content-hash cache. Parallelised per *page*, not
   per file — client folders are lopsided (ninety small statements plus one
   137-page credit report), and per-file workers left cores idle. That change
   took the credit report from ~14 minutes to under 3 even on a slow sandbox.
2. **Checklist PDF parser** → 16 structured items from `Client_File Checklist.pdf`,
   with a review-before-run gate. Reads layout geometry (indent depth, font
   weight), not prose. Hardcoded model kept as fallback.
3. **Tighter classification** — primary form year, plus bank/credit-card/brokerage
   statements, W-2s, paystubs, payroll summaries, K-1s, Schedule E, credit
   reports, leases, four kinds of insurance, fee schedules, Day Sheet.
4. **Packaged** — `Run Intake Auditor.command` (double-click, drag folder in) and
   `SETUP.md` (plain-English fresh-Mac setup, no dev account).

Plus, beyond the list: statement-series gap detection, duplicate detection,
content-vs-filename contradiction detection, and a rewritten residual-PII
detector with confidence levels.

**Scored against your answer key** (`SCORECARD.md`): 4/4 mislabeled files, 7/8
missing months, both disguised-file traps, both control series correctly left
alone, 2/2 duplicates.

---

## The one thing left from last session

**Score the OCR path on the redacted batch.** Everything so far is scored on
`RedactorTest/` (the unredacted originals, which have text layers on 575 of 780
pages). The redacted batch forces OCR on every page. Classification *should*
agree — same documents — but that's an assumption, not a result.

The cache is at 16 of 93 files. To continue:

```
cd "<this folder>"
python3 extract.py "../redacted-batch-2026-08-14 (1)" .cache
```

Resumable — every finished file is cached permanently, so an interrupted run
loses nothing. Then:

```
python3 audit.py "../redacted-batch-2026-08-14 (1)" \
  --checklist "../Client_File Checklist.pdf" \
  --client "Bassett" --greeting "Dr. and Mrs. Bassett" --cache .cache
```

Compare against `sample_output/` to see where OCR changes the answer.

---

## Waiting on you

**1. The dependent-SSN finding.** See `PII_NOTES.md`. The redacted 1040s appear to
leave dependents' SSNs visible — nine digits in the dependents table between the
child's name and date of birth, same number in both tax years. Needs one manual
check against a source file before we treat it as a redactor bug, because OCR can
assemble nine digits from adjacent columns.

**2. One flagged gap to eyeball.** Cap 1 HYSA January. Those statements are named
"Nov-Dec" and "Jan-Feb", so this may be cycle-labelling rather than a real gap.

**3. A decision.** 68 items land in "unexpected". Most are legitimately not on this
checklist — bank statements, brokerage, credit reports, W-2s. Do you want them
grouped by type instead of listed flat?

---

## Then, in rough order

- **Trailing gaps.** Gap detection only finds months *between* the first and last
  statement provided. Arvest MM stops at March, so a missing April is
  indistinguishable from "April hasn't happened yet". Fixable by passing an
  as-of date.
- **The filing tree.** Your later stage — Personal (Assets, Banking, Credit
  Reports, Debt, Insurance, Investments, Paystubs/W2, Taxes, Misc) and Business
  (Banking, Credit Cards, Debt, Fees, Financials, Insurance, Payroll, Production,
  Taxes, Misc). The classifier already emits `owner_side` on every document and
  flags ambiguous ones with "personal vs practice unclear — needs a human call",
  so this should be a thin layer.
- **Time a real run on your Mac.** My sandbox does ~6s/page on 2 throttled cores;
  I don't want to keep quoting estimates when we can measure it.
- **A second client's checklist.** The parser has only ever seen this one. That's
  the real test of the geometry approach.

---

## Bugs found and fixed, for the record

Each of these came from testing against real OCR output, and none would have been
visible from reading the code:

- **Every P&L was misclassified.** The rule looked for "Total Income"; QuickBooks
  writes "Total **for** Income". One P&L came back as a brokerage statement.
- **Titles were matched against whole documents.** A 137-page credit report
  contains a legend line "PPL: Paid profit and loss" → classified as a P&L. A
  paystub lists "EE Disability Pretax" → classified as a disability policy.
  Titles are now read from the document head only.
- **A complete series looked broken.** RRFD's January statement runs
  `1/01/26 thru 2/01/26`; reading statements by closing date called it February
  and invented a missing January. Cycles closing in the first days of a month now
  roll back.
- **An annual summary satisfied a monthly request.** The EagleSoft item passed as
  satisfied because a year-scoped report was credited with twelve months —
  precisely the mismatch you asked it to catch.
- **`please` contains `lease`.** The staff-roster checklist item matched the
  rental-lease rule through "**please** list out names".
- **Issuer bleed.** A Capital One statement mentioning "Preauthorized Deposit from
  ARVEST BANK" was attributed to Arvest. Earliest match on the page now wins.
- **Practice cards satisfied the personal-card item.** Both items matched the same
  six statements. Side-scoped items no longer accept the other side's documents.
- **The first client email leaked.** It included "account ending 6840" and an
  internal filename. Rather than just fix the wording, the email is now scanned
  after generation and the tool refuses to write it if anything turns up.
- **BancFirst read a different account number on each statement**, splitting one
  series in two. Sub-series under one institution with non-overlapping months are
  now merged, while genuinely separate accounts (three at Arvest, overlapping
  months) stay apart.
- **Google Docs exports** are full of zero-width joiners that broke every regex —
  the staff roster was invisible until text normalisation was added.
