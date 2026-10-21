# Brogan's savings worksheet: what is typed and what is computed

Read from the formulas of three Excel exports (Oyler, Kinsler, Meier), 21
October 2026. The worksheets themselves sit beside this file and are not in
git; the findings are.

## Computed, and now computed by the toolkit

| Figure | Formula in his sheet | Toolkit |
|---|---|---|
| Target retirement income | not a formula: the largest income, in $1,000s, that leaves the 9% path at or above zero at the horizon | savings, solved; matches Rebol, Spaulding, Kinsler, Bassett exactly |
| Practice value at the consult | 65% of collections: Oyler 0.65 x 4,103,930 = 2,667,000; Kinsler 909,463; Meier 2,245,104 | facts + FIRM multiple |
| Practice growth | x1.03 a year (K column) | same |
| Building growth | x1.02 a year (L column) | same |
| Sale, net | (practice + building at retirement) x 0.7, less debt at sale | same; see faults below |
| Expenses | personal spending incl. liabilities x 12, x1.032 a year | cash flow workbook |
| Proposed deferrals + match | max deferral + W-2 x match (Oyler 32,500 + 360,000 x 4% = 46,900) | computable from the W-2 and plan |
| Tax saving on added deferral | x 0.3 | same |
| Each cashflow GAIN in the savings list | "3% lower overhead = 122.4k" is 3% of collections; fee increase on production; bank surpluses from the cash flow; refinance as the payment cut x 12; better tax management as the average tax surprise | levers + cash flow; to wire |

## Ideal practice bank balance

One month of practice expenses on the most recent reliable overhead (Austin,
21 October). The toolkit takes the overhead numerator of the newest full-year
P&L over twelve, rounded up to the next $10k. Rebol gives $180k, as on his
deck. Oyler gives $280k against $200k on his deck, and Spaulding $60k against
$75k, so which overhead figure counts as "reliable" is still open.

## Overhead goal

Not settled at the firm. The deck uses Bryan's 50% unless the advisor sets one,
and says so in the presenter note.

## Typed by the advisor

| Figure | Seen |
|---|---|
| Building value | Oyler 4,500,000; Kinsler 536,000; Meier 2,100,000. Not in the documents; the Assumptions already asks for it (section 7). |
| A larger practice value, for the second scenario | Oyler 4,667,000 against the 65% figure of 2,667,000 |
| How much of each gain is INVESTED ("assume 9k") | See the pattern below. This is the one real judgement in the sheet. |
| Steps after year 3 | Kinsler +18,000 in years 5-7 and 8-13; Oyler +24,000 in year 5; Meier +18,000 |
| Current W-2 and distributions | from the W-2 and the books; typed today |

## The invested amounts follow a pattern

Recurring gains are phased in by a fixed step a year; one-time items take a
share once:

| Gain | Oyler | Kinsler | Meier |
|---|---|---|---|
| 3% lower overhead | 6k, 18k, 36k | 9k, 15k, 21k | 12k, 24k, 36k |
| Fee increase | 3k | 3k, 6k, 9k | 6k, 9k, 12k |
| Bank surplus, one time | 20k of 65.7k | 100k of 203k | 550k of 707k; 50k of 141k |
| Loan drop-off | | 12k of 23.2k; 48k of 82.3k | |

Proposal: the toolkit builds the list of gains from the documents, prefills the
invested column with this ramp, and the advisor adjusts it. That leaves one
table to review instead of a worksheet to build.

## Faults in his sheet, not to copy

- The debt deducted at sale is the same 81,546 in all three workbooks: a block
  carried over from another client and never updated.
- Net proceeds read row 10's practice and building values whatever the
  retirement year.
- Oyler's current savings is 47,500 at the top and 47,800 in the list.
- Oyler's current path grows the first year at 8.25%; his Four Quadrants path
  starts the following January.
