# Scored against `RedactorTest_ANSWER_KEY.md`

Run on all 95 files in `RedactorTest/` (780 pages, 198 needing OCR).
Command used is in `SETUP.md`; output is in `sample_output/`.

## Mislabeled files — 4 of 4 caught

The core test: judge by content, never by filename.

| File (the lie) | Answer key says | Auditor said | |
|---|---|---|---|
| `Hollingsworth Homeowners Insurance Declaration 2025.pdf` | Arvest bank statement | bank statement | ✅ |
| `Practice April 2026 bank stmt.pdf` | Feb 2026 payroll summary | payroll summary, February 2026 | ✅ |
| `Grant Term Life Policy Summary.pdf` | Grant's 2023 W-2 | w2 | ✅ |
| `Cash_App_January_2026_Account_Statement.pdf` | 2024 individual tax return | personal tax return, 2024 | ✅ |

No false positives.

## Missing months — 7 of 8 caught

| Series | Answer key | Auditor | |
|---|---|---|---|
| Arvest Free Blue | March | March 2026 | ✅ |
| BancFirst | Feb | February 2026 | ✅ |
| Cash App | January | January 2026 | ✅ |
| Office Citibank CC | April | February **and** April 2026 | ✅ + extra |
| Payroll summaries | Feb 2026 | February 2026 | ✅ |
| Practice bank stmt (x5063) | Feb 2026 | February 2026 | ✅ |
| Provider Productivity | March 2026 | March 2026 | ✅ |
| Arvest MM | April | **not caught** | ❌ |

**Why Arvest MM was missed — a real limitation, not a bug.** Gap detection only
finds months *between* the first and last statement given. Arvest MM runs
Jan–Feb–Mar, so a missing April is indistinguishable from "April hasn't happened
yet" without knowing how many months were asked for. Where the checklist states a
depth ("previous 4 months"), that rule catches it instead. To catch trailing gaps
on series the checklist doesn't mention, the tool would need a stated as-of date.
Easy to add if you want it.

**The two extras.** Citibank's February is flagged alongside April. The client
provided Jan, Mar, May, so February is genuinely absent from a monthly series —
the answer key only lists the deliberately planted one. Cap 1 HYSA January is
also flagged; those statements are named "Nov-Dec" and "Jan-Feb", so this one is
worth your eye — it may be a cycle-labelling artifact rather than a real gap.

## Both traps caught

Where the "missing" month is actually present under a mislabeled name, the
report says so explicitly:

- March 2026 Arvest statement → disguised as `Hollingsworth Homeowners Insurance Declaration 2025.pdf`
- February 2026 payroll summary → disguised as `Practice April 2026 bank stmt.pdf`

The month still counts as missing until a human confirms, which is the right
default: nothing gets silently accepted on the strength of a guess.

## Controls correctly left alone

Eastman CU (Dec–Mar) and RRFD Properties (Dec–Mar) are complete series and were
**not** flagged. RRFD nearly produced a false positive: its January statement
runs `1/01/26 thru 2/01/26`, and reading a statement by its closing date called
that February, inventing a missing January. Cycles closing in the first days of a
month now roll back.

## Duplicates — 2 of 2

- `529 March stmt copy.pdf` = `529 March stmt.pdf` ✅
- `Elise Roth (1).pdf` = `Elise Roth.pdf` ✅
- Also found: `Business Debts.docx` and `Personal Debts.docx` are byte-identical.
  The answer key treats these as a bookkeeping rename, but they really are the
  same file, so flagging is correct — worth knowing they're not two documents.

## Client email safety

The email is checked after it's written, not merely built carefully. It's scanned
for SSN/EIN/account patterns and for every source filename; if anything turns up
the tool refuses to write the file. Confirmed on this run:

- no account numbers (an earlier draft leaked "account ending 6840" — now blocked)
- no internal filenames (a draft cited `Cash_App_January_2026_Account_Statement.pdf`)
- no residual-PII findings
- optional items dropped: Business Overhead Insurance ("if applicable") and the
  bonus structure ("if any") never appear
- satisfied items dropped

## Caveats on this run

- Scored on the **unredacted originals**, which have text layers on 575 of 780
  pages. The redacted batch exercises the OCR path on every page; classification
  should agree but hasn't been scored yet. That's the next check.
- 57 of 95 files show residual PII — expected here, since these are the originals.
  On the redacted batch this number is the real signal.
- 68 items land in "unexpected". Most are legitimately not on this checklist
  (bank statements, brokerage, credit reports, W-2s). Worth deciding whether you
  want those grouped by type rather than listed flat.
- `2025 Provider Productivity` and `2024 Day Sheet` are annual reports whose year
  came from the print date. Now corrected via the "From EOM" period, but annual
  EagleSoft reports are worth spot-checking.
