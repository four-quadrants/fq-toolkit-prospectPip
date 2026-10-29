# Cash flow: the rules, as the firm applies them

Settled with the firm, 15 October 2026, by reading four of the firm's own
expense workbooks (Oyler, Bassett, Kinsler, Meier) and the lead advisor's published
Oyler Assumptions, then checking each conclusion against him.

Written down because the arithmetic is easy and the rules are not. Every
figure below was either derived from a formula in a real workbook or
answered directly by the firm; nothing here is inferred from how the output
looks.

---

## The core calculation

Per account, per statement period:

    Expenses        = Beginning balance + Additions - Ending balance
    Adjusted exp.   = Expenses - Adjustments OUT + Adjustments IN
    Adjusted dep.   = Additions - Transfers IN

Expenses are **never parsed from transaction lines**. They are derived as
the figure that makes the statement reconcile. This is the single most
important thing in the file: it means three numbers off a statement summary
are enough, the result is correct by construction, and no transaction-level
OCR is needed for the headline figure.

Per account the published line is then:

    Average adjusted deposit, average adjusted expense, and the difference,
    each averaged across the periods covered.

## Annualising

Sum the window, divide by the months it actually spans, multiply by twelve.

This replaces the hand-typed weights row found in every existing workbook,
and the replacement is not cosmetic. The weights do not sum to one. Three
periods are weighted 0.33 each, which totals 0.99, so every three-period
account is understated by exactly 1%.

Measured on Oyler: his Civista x0222 is weighted 0.33 three times and comes
to $8,995 a month where the true average is $9,087. That $92 is the entire
difference between his published personal expenses of $13,985 and the
$14,077 this method produces. Annualised, about $1,100.

The same arithmetic bites harder elsewhere: seven periods at 0.14 is 0.98,
and a fifth column added without changing 0.25 to 0.20 inflates every
figure by 25%.

Accounts need not cover the same window as each other; the figures are
averages. What matters is that the statements are close to each other, not
that they are close to the build date. A build taking a week is the firm's
problem, not a reason to ask the prospect for more statements.

---

## What is removed from deposits, and what is not

**1. Borrowing is always excluded.** Policy loans, credit card draws,
HELOC draws, new mortgage proceeds. Money borrowed is not income. Applied
as a rule, not a proposal, with the reason printed.

**2. Personal to personal is excluded.** Moving his own money between his
own accounts is not a deposit.

**2b. Personal to business is KEPT in expenses.** Money Brian puts into
his own practice account stays as spending, even though it is still his.
The firm's ruling, 19 October: The lead advisor left both the $10,000 "Short term
loan" and the $50,000 "Loan" to x4728 in expenses, and that is the firm's
treatment. The workbook notes each one rather than applying it silently,
because it is the one place an obvious transfer is deliberately not
treated as one.

**3. Business to personal is KEPT as a deposit.** It is a distribution and
it is income reaching the household. Netting it out would understate what
the family actually lives on.

   Exception: a one-off lump is excluded and noted. The test is that the
   flow appears in at most two of four periods AND is more than double the
   median of the remaining periods. Anything tripping it becomes a proposal
   on the Adjustments sheet, never a silent decision, because this is the
   adjustment that moves household income most.

Rule 3 is why the personal/business split has to be right: the same
$20,000 between two accounts is a transfer if both are personal and income
if it came from the practice. Direction is not symmetric.

## Periods are statement periods, not calendar months

The plan uses whatever period the statement covers, typically the 26th to
the 25th, not a calendar month. The firm's ruling, 19 October.

The reason is reconciliation: beginning plus additions less ending is
exact for the period the statement actually covers, and nothing has to be
interpolated. Reallocating to calendar months would mean splitting
transactions across boundaries and estimating balances mid-month, and the
figures would stop being derivable from the documents.

The cost is that figures do not line up with a month-by-month view. On
Oyler this shows as $2,500 and $4,000 differences against the lead advisor's August
and September columns, which are calendar months. Those differences are
expected and are not errors.

## Inference, where a description names a bank but not an account

Some movements name the destination bank only: "TRANSFER US BANK TRANSFER
WEB". Where the client holds accounts at that bank and all of them sit on
the same side of the house, the movement is treated as his own money
moving, and marked as inferred rather than stated.

This is doing real work and should be watched. On Oyler it covers thirteen
payments worth $34,000, and it is what makes June and July reconcile to
The lead advisor's figures exactly. A bank holding accounts on both sides is skipped,
since naming it would then say nothing about where the money went.

## A period is not a month

Averages divide by the months the statements COVER, read off the dates
printed on them, never by the number of statements.

This is the rule stated at the top of this file and it was still got
wrong in the code. Oyler's Civista x0222 has four statements, but the
first spans 2 April to 1 July. Counting that quarter as one month
understated the account threefold, and the published personal spending
came out at $16,288 a month against a true $13,892.

The same mistake in the other direction would overstate: a client who
sends two statements a month would have his spending doubled.

## Reading direction: the balance beats the section heading

Some banks split credits from debits into separate sections, so the
heading says which way the money went. Others print one register with
Debits, Credits and Balance columns, and the text extractor flattens the
columns away, so every transaction looks identical.

What survives is the running balance. If it fell, the entry was a debit.
That works on any bank printing the column and does not depend on layout.

Found on Bassett's Arvest accounts, where "Transfer to Loan * 9569" was
being read as money coming IN. On one account that produced $51,000 of
income that never existed.

## Loan repayments are not transfers

"Transfer to Loan * 9569" is a repayment. The wording contains "transfer",
but treating it as one strips debt service out of expenses, which is
backwards: the firm reports liabilities separately and still counts them
as money that left. Repayments stay in expenses, noted. A draw FROM a loan
account is borrowing and never a deposit.

## An account named but not supplied

A description can say what kind of account it went to: "Transfer to
Checking * 5647". A checking or savings account named in his own statement
is his, whether or not he has sent that statement. Those are excluded and
marked as inferred.

Bassett moves money to x5647 three times and the firm counts all three.
Without this rule they are all left as open questions, and the account's
transfers out come to $500 against the firm's $610.

## Telling personal from business

Three independent signals, cross-checked rather than trusted:

- where the document was filed (Documents/Personal/Banking against
  Documents/Business/Banking), which the auditor already decides
- the account holder on the statement letterhead: "BRIAN OYLER" reads
  differently from "Brian C Oyler, DDS Family Dentistry", "Eden
  Properties" or "Moonridge"
- which entity's return or P&L references the account

Where the three disagree, print it. A personal account being run through
the practice is comingling, which is a finding and not a tie to break
quietly.

---

## Credit card smoothing

Kept as the lead advisor does it: each period's card payment is compared to the
average across periods, and the difference is carried back as an adjustment
so one heavy month does not distort the figure.

The firm's reasoning for keeping it, which is worth recording: not because it
is obviously right, but because changing too much of the lead advisor's method in one
go is its own risk. It appears on the Adjustments sheet marked "By rule" so
it is at least visible, which it is not today.

## What is excluded from the expense figure

Three categories, reported separately with a "Paid from" account and
subtotalled by kind rather than lumped together:

- **Liabilities** -- mortgages, car and student loans
- **Insurance** -- life, disability, umbrella premiums
- **Savings** -- retirement and brokerage contributions, HSA, 529

Most prospects arrive with nothing under savings; some do, and it is worth
the category existing for them. The risk when it is missing is silent: a
contribution leaving for a brokerage looks exactly like spending on a
statement, so an unrecorded saver's expenses are overstated by whatever
they put away. The workbook therefore prints an amber flag when a category
is empty rather than simply omitting it.

Keeping the three apart also shows what changed between drafts. Oyler's
draft subtracted all $19,731; the final subtracted only the $10,645 of
liabilities, having recognised that the $9,086 of premiums was already
inside the paying account's expenses. With one combined total that
difference is invisible. The Assumptions then prints both:

    "We presume that current personal expenses are $X monthly ($Y annually)
    excluding the personal liabilities, insurance, and savings strategies
    (approximately $A monthly [or $B annually] including those payments)."

---

## Consistency by default, inconsistency on purpose

The tool applies the same rule to every period and every account. Any
departure is a row on the Adjustments sheet with a reason attached and the
analyst's decision recorded against it.

This exists because of something found in the lead advisor's own draft. In the Oyler
surplus block, three of the four periods compute expenses as `=C7-C8`
(less transfers out) while the fourth is `=F7-F8-F17` (less transfers out
AND less $117,806 of other adjustments). Nobody appears to have chosen that
difference; it is the kind of thing that happens when a formula is edited
in one column. A generated workbook cannot do it, and an analyst who wants
it can say so on a row that says why.

## Where overrides live

In the workbook itself, in a "Your call" column: `yes`, `no`, or a
corrected amount. The file is a real `.numbers` file, written and read with
the `numbers-parser` library, so nobody exports anything.

Decisions are keyed by account plus period plus amount, never by row
number, because a new statement inserts rows and anything keyed on position
would silently reattach an old decision to a different transaction. Once
ruled on, a row stops being a question and renders as confirmed, so the
review shrinks each cycle instead of repeating.

---

## Two things proven against the firm's own output

**The method reproduces the lead advisor's published figures.** US Bank x1145
computes to $2,291 deposit, $661 expense, +$1,630 surplus, matching his
line exactly. Civista x0222 gives $3,333 / $9,086 / -$5,753, exact. US
Bank x2683 gives -$936 against his -$935.

**Where it differed, the difference was explained, not waved away.**
Civista x0054 appeared $12,000 out. The cause was that the workbook
supplied was an earlier draft: the final version stopped treating the
$50,000 Amex draw as a transfer in (deposit average $59,859.73, published
$59,860) and added the $1,305.96 card adjustment back in the final period
(expense average $33,999.11, published $33,999). Surplus $25,860.62 against
a published $25,861. All three reconcile to the cent.

That exercise is the reason rule 1 exists. Under the draft the Amex draw
was borrowing and excluded; under the final it was left in deposits. Both
are borrowing, so both are now excluded by rule, and anyone who disagrees
says so on a row.
