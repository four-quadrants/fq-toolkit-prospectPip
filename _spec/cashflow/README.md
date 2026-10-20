# Cash flow reference material

Drop files here so the cash flow reader can be built from how the firm
actually does this, rather than from a method invented to fit the output.

The target is the per-account line that appears in section 5 of the
Assumptions, which on Brogan's Oyler plan reads:

    Personal Money Market (US Bank x1145):  $1,581
    —Average deposit $2,291, Average adjusted expense $123 (after xfers),
      average surplus +$2,168

Reproducing that needs two things: the statements the figures came from,
and the working that turned one into the other.

---

## workbooks/

The Numbers files converted to Excel. **Oyler first**, then two or three
others, ideally ones that differ from each other: a single practice with
few accounts, and one with several entities.

These are the important half. The statements show what went in and out;
only the workbook shows the rules that were applied to them, and the rules
are the part that cannot be guessed. Specifically, what is wanted from
them:

- **How a transfer is recognised.** Matching an amount and a date across
  two accounts is the obvious method, but it would miss a transfer to an
  account we hold no statement for, and it would falsely pair two
  unrelated payments that happen to be equal. Whatever test is actually
  applied is better than that guess.
- **What "adjusted" removes besides transfers.** The x0393 line reads
  "Average adjusted deposit $250 (after xfers in)", so inbound transfers
  come out of deposits too, not only outbound ones out of expenses.
  Whether anything else comes out (owner draws, credit card payments,
  loan proceeds) is not visible from the result.
- **The averaging window.** Per month across the months covered, or per
  statement. The accounts carry different numbers of statements, so this
  moves every figure on the page.
- **Which balance is printed.** The plan's boilerplate says values were
  "based off an average of historical banking statements", but the figures
  match the latest statement balance. Those are different methods.

Leave the formulas intact. A workbook with the formulas in it answers all
four questions at once; a workbook of pasted values answers none of them.

## statements/

The source PDFs the workbook figures were derived from, for the same
clients. One folder per client is fine, or per account; naming does not
matter as long as they are not mixed between clients.

Worth knowing: Oyler's statements are already filed under his client
folder, so his do not need re-supplying unless the set here differs.

---

## A naming trap worth avoiding

Two of Oyler's Civista files are named "Statement-6" and "Statement-9"
where 6 is the later quarter: Statement-9 ends 1 July at $139.34 and
Statement-6 ends 1 October at $1,879.68. Reading the highest number as the
most recent gives the wrong balance by $1,740 on that account alone.

Nothing needs renaming. The reader now selects on the ending-balance date
printed inside the statement rather than on the filename. It is noted here
because any human doing this by hand will hit the same trap.
