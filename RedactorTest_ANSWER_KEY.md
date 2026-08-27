# RedactorTest — Ground Truth / Answer Key

**Location:** `BassetTestDocs/RedactorTest/` (single flat folder, no subfolders)
**Files:** 94 documents + `_GROUND_TRUTH_manifest.csv` = 95 items
**Source:** copied from the 192-file `Personal/` and `Business/` tree. **No file contents were altered** — every copy is a byte-for-byte match of its source (MD5-verified in the manifest, `content_intact = YES` for all 94).

Only **filenames** were changed in the ways below. Everything else keeps its real name.

---

## 1. Mislabeled files (real content, WRONG filename) — 4

The hardest test: the app must judge by content, not filename.

| Filename in folder (the lie) | What it ACTUALLY is |
|---|---|
| `Hollingsworth Homeowners Insurance Declaration 2025.pdf` | Arvest Free Blue **March** bank statement (acct 3095) |
| `Practice April 2026 bank stmt.pdf` | **Feb 2026 payroll summary** (business) |
| `Grant Term Life Policy Summary.pdf` | Grant's **2023 W-2** |
| `Cash_App_January_2026_Account_Statement.pdf` | **2024 Individual tax return** (Hollingsworth) |

## 2. Intentionally omitted months (reconciliation / gap detection) — 7

App should flag the missing month in each series.

| Series | Present | MISSING (flag this) |
|---|---|---|
| Arvest Free Blue (3095) | Jan, Feb, Apr | **March** |
| BancFirst (8936) | Dec, Jan, Mar | **Feb** |
| Arvest MM (9299) | Jan, Feb, Mar | **April** |
| Cash App | Dec, Feb, Mar | **January** |
| Office Citibank CC | Jan, Mar, May | **April** |
| Payroll summaries | Dec, Jan, Mar | **Feb 2026** |
| Practice bank stmt (x5063) | Dec, Jan, Mar | **Feb 2026** |
| Provider Productivity | Jan, Feb, Apr | **March 2026** (March *Day Sheet* IS present) |

**Trap / overlap:** Three "missing" months are actually present in the folder *under a mislabeled name* — 3095 March (as the insurance decl), payroll Feb (as the April bank stmt), and Cash App Jan (which is really the tax return). A strong app should notice the gap AND that a disguised file could fill it (or, for Cash App, that the "January" file is the wrong content entirely).

**Controls (complete, no gap):** Eastman CU (Dec–Mar) and RRFD Properties (Dec–Mar) are full series — the app should NOT flag these.

## 3. Duplicates / near-duplicates (dedup test) — 2

| Filename | Relationship |
|---|---|
| `Elise Roth (1).pdf` | byte-identical to `Elise Roth.pdf` |
| `529 March stmt copy.pdf` | near-identical to `529 March stmt.pdf` |

## 4. Name-collision renames (bookkeeping, not a trap)

Two source files were both named `Debts.docx` in different folders. To avoid silent overwrite when flattening, they became `Personal Debts.docx` and `Business Debts.docx`. A few other files got minor cleanups (double spaces, parentheses) — all logged in the manifest's `source_path` column.

---

### How to score
`_GROUND_TRUTH_manifest.csv` (inside the folder) is the full row-by-row key: `dest_filename, category, curveball, source_path, content_intact, md5`. Filter the `curveball` column to see every planted item. Compare the app's output against this.
