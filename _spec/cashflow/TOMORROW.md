# Pickup, Thursday 22 October

Written at the end of 21 October.

## What landed on 21 October

**The consultation deck is built.** `deck.py` assembles every slide and its
sources, `deck_pptx.py` renders it, and it is the fifth tick box on the Build
Outputs tab. It opens in Keynote. Any slide still waiting on an advisor decision
prints an amber STILL NEEDED box, so an unfinished deck cannot pass for a
finished one.

**The two models under it are checked against the firm's own files.**

- `savings.py` reproduces Brogan's savings worksheet row for row, both paths,
  first year to retirement, on 12 of 13 signed clients
  (`_spec/verify_savings.py`). The 13th, Kinsler, has a fault in her own
  sheet: three different sale years.
- `levers.py` reproduces every lever in Bryan's Kinsler model, plus the top-five
  subtotal and the worst case (`_spec/verify_levers.py`).
- End to end, fed Brogan's inputs, the deck matches his Spaulding slides
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
`deck_template.py` opens `assets/consult_template.pptx` (Austin's redesigned
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

Austin's edit test (21 October): edits in Keynote held and exported back
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

The Rebol and Spaulding TEST folders carry Brogan's inputs under that key,
labelled as verification. Oyler's carries only target income and current
savings, because the years of his savings steps are not written down
anywhere I could find.

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
- **The Spaulding TEST folder has no personal bank statements.** Brogan used a
  Chase x2682 that is not in it.
- The x0054 $100,000 settlement in the surplus block; ten statements unread.

## On the new iMac

Run `python3 -m pip install --user python-pptx`. The preflight now checks for
python-pptx, numbers-parser and reportlab, and suggests `--user` on Apple's
Python, where it used to suggest `--break-system-packages`.
