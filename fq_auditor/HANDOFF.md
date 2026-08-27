# FQ Intake Auditor — session handoff (Aug 14, 2026)

Everything below is saved in `BassetTestDocs/fq_auditor/`. Nothing is running.

## Where we got to

| Priority | Status |
|---|---|
| 1. Read every page, with caching | **Built.** `extract.py` replaces `extract_cache.py`. All pages, no cap, content-hash cache, parallel workers. OCR of the 93-file batch is **16/93 cached** — resumable, see below. |
| 2. Checklist PDF parser + review step | **Parser built** (`checklist_parse.py`), 16 items parsed from `Client_File Checklist.pdf`. **Waiting on your review** — see below. |
| 3. Tighter classification | **Rewritten** (`classify.py`). Real bugs found and fixed against actual OCR output. More tuning needed once the full corpus is cached. |
| 4. Standalone packaging | Not started. |
| Series/gap + duplicate detection | Not started. Hooks are in place (`series_key` on every doc). |

## The one thing blocking the audit run

You asked to review the parsed checklist before anything runs. It's in
`checklist_parsed.json` (16 items, matching the hardcoded model's count).
Two things I want you to confirm:

1. **Tax years are inferred, not stated.** The checklist only says
   "2025 (if available)" under both Taxes items. I inferred required = **2024**,
   optional = 2025. Given it's August 2026, required may well be 2025 with 2026
   optional. Both items carry a `review_flags` entry saying so. **This is the
   single most likely thing to be wrong.**
2. **"Confirm the Farmer's Life $750,000 premium"** — I mapped this to
   `life_insurance`, so an actual policy summary PDF can satisfy it. The old
   hardcoded model treated it as info-only (`farmers_life_premium`). Mine is
   arguably better since there IS a Farmer's policy summary in the pile, but
   it's a judgement call and it's yours to make.

Everything else parsed cleanly: Personal/Practice split, "previous 4 months"
→ count 4, "both rental properties" → count 2, "January 2024 – April 2026"
→ monthly range, "(if applicable)" and ", if any" → optional flags, and the
compressed insurance items expanded into their full sub-detail lists.

## Resuming the OCR

Run this until it stops printing new files. It's resumable — every completed
file is cached permanently, so an interrupted run loses nothing:

```
cd <this folder>
python3 extract.py "../redacted-batch-2026-08-14 (1)" .cache
```

On your Mac this should be far quicker than it was in my sandbox: more cores,
faster cores, and the work parallelises one file per core.

## Bugs found and fixed (all from real OCR output, not guesses)

- **Every P&L was being missed.** The rule required "Total Income"; QuickBooks
  writes "Total **for** Income". `2024 P & L` came back `unknown` and
  `2025 P & L` came back as a *brokerage statement*.
- **`please` contains `lease`.** The staff-roster item matched the rental-lease
  rule via "**please** list out names". Now word-bounded.
- **Full-year documents were being read as January.** A P&L headed
  "January 1–December 31, 2024" was getting `month=January`, which would have
  poisoned the month-gap detection later. Annual/YTD/quarterly now suppress the
  month.
- **Issuer and account bleed.** Tax returns and balance sheets were picking up
  whichever bank was mentioned inside them (a 1040 tagged "Arvest · x2023").
  Issuer/account are now only read off actual statements.
- **529 statement dated 2003**, from the fund's inception date. Year extraction
  now prefers the statement period and ignores implausible years.

## Known-still-wrong (needs the full corpus to fix properly)

- Annual EagleSoft reports take their year from the **print date**:
  `2025 Provider Productivity` reports as 2026.
- Balance sheets still resolve to a month; they need "as of December 31, 2024"
  handled as annual.
- `Arvest Free Blue April` reads account tail **6840**; the answer key says
  **3095**. An OCR digit error in an account number will split a statement
  series in two and cause a false "missing month". Worth making series grouping
  tolerant of one-character differences.

## Note on the answer key

`RedactorTest_ANSWER_KEY.md` is an excellent test harness — 4 mislabeled files,
7 deliberately omitted months, 2 duplicates, plus 3 traps where the missing
month is present under a mislabeled name. I'll score against it once gap
detection is built.

## Files

- `extract.py` — all-pages OCR + content-hash cache (**replaces `extract_cache.py`**,
  which I couldn't delete — ignore it)
- `classify.py` — rewritten content classifier, emits `owner_side` + `series_key`
- `checklist_parse.py` — checklist PDF → structured model
- `checklist_parsed.json` — **the model awaiting your review**
- `checklist_bassett.py` — unchanged hardcoded fallback
- `detectors.py`, `reconcile.py`, `render_docx.py`, `audit.py` — unchanged so far
- `.cache/` — OCR cache (16 of 93 files)
