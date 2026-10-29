# The consultation deck: where every number on it comes from

Worked out 20 October by reading the redesigned deck
(`Oyler Consultation-ah version.key`), the lead advisor's savings worksheet, and
The analyst's Kinsler workbook. Written down because the answer took a morning
to establish and would take another morning to establish twice.

## Reading a Keynote file without Keynote

`.key` is a zip of IWA: snappy-compressed protobuf, one file per slide.
numbers_parser decompresses the chunks but cannot parse Keynote's message
types, so the chunks are decompressed with its helper and the text runs are
read straight out of the payload. Enough to learn a deck's structure, which
is all it is for. The scratch reader is `readkey.py`; presenter notes come
out too, and they carry the reasoning behind each slide.

No PowerPoint export is needed.

## The deck's shape

Nineteen slides, and the redesign is regular in a way the old one was not:
every slide is an eyebrow, a headline, one hero stat with a line of subtext,
the body, and a presenter note. That regularity is what makes it
generatable.

## Where the numbers come from

**Boilerplate, five slides.** 4Q Tax & Accounting 101, team breakdown, Four
Quadrants results, how we invest, client process and agreement.

**Derivable from what the toolkit already builds, seven slides.**
Corporate debt structuring is the debt schedule. Investments current is
sections 4 and 5 of the Assumptions. Practice opportunities is the analyst's
lever model, below. Cashflow management, biggest concerns, and the two tax
review slides.

**From the lead advisor's savings worksheet and the personal return, seven slides.**

`Consult info/savings worksheet.numbers`, with an Excel export in Downloads
from 13 October that is more useful because the formulas survive the export.

Two sheets, `age 65 ret-2.667M` and `age 65 ret-4.667M`, which are the two
practice-value scenarios on the pair of savings-future slides. Three blocks
down each sheet: the current path at 8.5%, the current path running out of
money, and the Four Quadrants path at 9.0%.

Its inputs are mostly ours already:

- starting portfolio `(69120+628000+408525)`, the Vestwell 401k, the
  Provident IRA and the Reef stake, which the Assumptions already carries
  to the dollar
- retirement expenses year one `33716*12`, the lead advisor's personal spending
  including liabilities; ours computes $32,958 for the same thing
- expenses inflate 3.2%, returns 8.5% current against 9.0% proposed, all
  already in the FIRM constants
- current savings `24500+14400+8600` = $47,500, the deck's "today's $47.5k"

The income-structure slide is rows 200 to 212 of the same sheet: proposed
W-2 $360,000, proposed distributions $14,180 x 12, deferrals plus match
$38,900 current against $46,900 proposed, difference $8,000, tax saving
$2,400 as `=C210*0.3`. The slide says "$8.0k/yr more" and "over $2.4k/yr".
Same cells.

**The tax slide is the 1040 plus one decision, not a model.** Current:
withholding $319k, estimates $0, owed $280k, so a $39k refund. Proposed:
withholding $169k, estimates $111k, same $280k owed, $0 balance. Three
figures off the personal return and one choice about how to split the same
bill. Nobody models anything.

## The analyst's lever model

The `practice improvements` tab of `initial notes-kinsler.xlsx`. Each block
takes incremental production to incremental revenue to the owner at a 50%
target overhead. Levers: overhead to target, adjustment % and plan mix,
doctor production pulled through by extra hygiene, hygiene chair-days, new
patient %, the fee study, collection ratio. Ranked by dollars with a
confidence rating; the top five subtotal, with a worst-case attrition line
underneath.

Every input is a reference back to the initial notes workbook:
`'initial notes'!P18` gross production, `!P24` patients seen, `!O41` net
production per patient, `!J10` overhead on the tax basis. Nothing typed.
So the lever model is computable from the workbook the toolkit generates.

Its own caveat is worth printing on the slide rather than leaving in a
spreadsheet nobody opens: the blocks overlap, so the sum is not additive.

## What the advisor decides, and always will

Four things, and they are the whole of the form to build:

1. the target retirement income ($599,000 for Oyler, typed, not computed)
2. the brokerage savings schedule, stepping $73,900 to $101,900 to
   $122,900 to $146,900
3. the practice and building sale assumption at retirement
4. the withholding against estimates split

Nothing else on the deck is unsourced.
