# Monday 19 October: where to pick up

Written Friday 16 October. Read this first.

---

## THE DECISION, BEFORE ANY CODE

The firm has to rule on this, and it changes arithmetic rather than
plumbing. Five minutes with the actual Civista x0222 statements settles it.

Four statements were read for that account:

| File         | Begins     | Ends       | Additions | Ending   |
|--------------|------------|------------|-----------|----------|
| Statement-9  | 2 Apr 2026 | 1 Jul 2026 | 23,000    | 139.34   |
| Statement-8  | 2 Jul 2026 | 3 Aug 2026 | 10,000    | 1,051.42 |
| Statement-7  | 2 Jul 2026 | 1 Sep 2026 | 19,000    | 965.50   |
| Statement-6  | 2 Jul 2026 | 1 Oct 2026 | 29,000    | 1,879.68 |

Three of them begin on the same day. The deposits run 10,000 then 19,000
then 29,000, which reads as one period reported three times, each
statement covering everything since 2 July rather than a fresh month.

**Our tool excludes the last two as cumulative. The lead advisor used all three.**

- If the lead advisor is right, the overlap rule is wrong and should come out. It
  currently sits in `statements.gather()`.
- If the tool is right, his $9,086 a month for that account counts the
  same deposits repeatedly, and the personal expense total is overstated.

Note the tool also read an Apr-to-Jul statement he did not use at all.

---

## THEN, IN THIS ORDER

### 1. Two reader bugs (under an hour)

**Moonridge account number.** Four statements exist and read fine, but the
account number is not being picked up, so they group under a key taken
from the folder instead. The lead advisor has them as Wells Fargo x6986. Our
comparison showed Moonridge with no periods at all as a result.

**x0222 periods**, per whatever the firm decides above.

### 2. The transaction line reader (the real work)

Everything else waits on this. Needed: date, description and amount per
line. Then pair an outflow on one account against an inflow on another
within a few days, and apply the rules already agreed in RULES.md:

- borrowing is always out of deposits
- personal to personal is out
- business to personal is kept, unless it is a one-off lump

Expect it to be slow and imperfect. The statements are a mix of digital
text and scans, so accuracy will vary by bank. The honest output is a
proposal list with a confidence against each, which is what the "Your
call" column exists for. Do not aim for a clean answer.

### 3. Re-run the comparison

The test of whether we reproduce the firm. Civista x0054 should fall from
$77,874 a month to roughly the lead advisor's $23,124 once transfers come out. The
comparison script from Friday is worth keeping.

### 4. Back to the Assumptions

Sections 5 and 12 fed from the workbook rather than the figures typed in
by hand on Tuesday.

---

## WHERE FRIDAY LEFT IT

The pipeline runs end to end: statements in, a live Numbers workbook out,
on the firm's own template, with formulas intact and the reasoning in cell
comments.

The comparison against the lead advisor's own workbook:

- **US Bank x1145** matches on all four periods, to the cent
- **Civista x0054** matches except for ten cents of his rounding
- **US Bank x2683** matches, and we are more precise: he rounded to whole
  dollars, the statements carry cents
- **Practice x4728** matches on every overlapping period; we read two
  extra months he did not have
- **x0222** differs, per the decision above
- **Moonridge** empty, per the bug above

## CONSTRAINTS FOUND THE HARD WAY

All of these cost hours. None are obvious. They are in RULES.md too.

- A Numbers file built from nothing by the library opens with blank tabs.
  Start from a real Numbers file and everything works.
- A comment can only be added to a sheet that already contains one. The
  template carries a seed comment on each sheet for this reason.
- A cell that already has a comment cannot take another.
- Formulas cannot be written, but they can be copied by pointing a cell at
  another cell's formula id. References are relative, so copying sideways
  retranslates correctly and copying downwards does not.
- The template's weights row does not sum to one. Three periods at 0.33
  each total 0.99 and understate the account by 1%.
