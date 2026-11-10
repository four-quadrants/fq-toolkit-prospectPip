# Walking someone through the review page

For when the lead advisor (or anyone) asks how to use a prospect's review
page: "walk me through [client]'s review", "how does this page work", "what's
the difference between Plan inputs and Recommendations", "what does Team to
revisit do". He should never need someone to sit with him: answer here, in
plain words.

## How to walk him through it

- Find the page (`_Audit/review_pages.json`, key `review`) and read its live
  data first (ArtifactData `get` plan/figures), so answers are about what is
  on HIS page: "you have 3 questions marked Send and 2 answers still to
  come", not "questions can be marked Send".
- One tab at a time, in the order below. For each: what it is for, what he
  does there, what happens next. Then stop and ask if he wants the next tab
  or has a question. Short answers; no wall of text.
- Never change anything on his page while walking him through it unless he
  asks. If he asks you to ("mark that one answered", "set retirement to
  62"), do it with ArtifactData `update` on plan/figures, pinned to the
  version you read, and say what you changed.
- If he asks something this guide does not cover, look at the page and the
  review skill before answering. If it is something the page cannot do, say
  so and say what to do instead.

## The page in one breath

One page per prospect. The analyst checks the Assumptions first, then hands
it to him. He sorts the comments, picks the questions and copies the client
email. While the answers are out he can already shape the plan (it says
"provisional"). When answers come in he presses **Check for new answers and
documents**, pastes the line into Claude, and the answers land on their
questions with Claude's verdict. When the plan is right he presses **Build the
deck** on the Slides tab. Everything he types or clicks saves as he goes and
stays when he closes the page; Claude's refreshes never overwrite his work.

## Tab by tab

**Assumptions.** The plan's base figures, laid out like the Assumptions
document, section by section, each with its source. Yellow boxes are the
analyst's comments. Under each one he picks **Note** (for the team) or
**Question to the client** (goes on the Questions tab and into the email).
Under every section is his own comment box; **+ Add another comment** adds
more, each with its own Note / Question switch. Once answers come in, each
question shows the client's answer and Claude's verdict (green: settles it;
red: does not, with why), and he marks it **Answered**, **Still open: ask
again** (it goes back on the Questions tab), or **Team to revisit** (Claude
raises it with the analyst before the deck is built). Notes get **Done** or
**Team to revisit**.

**Print the assumptions** (button at the top of the Assumptions tab) copies a
line for Claude, which saves the Assumptions as a PDF in the client folder,
ready to print.

**What we found.** What the documents show (accounts, debts, cards, pay,
cash), each with where it came from. Read-only: if something is wrong, say so
in a comment on the Assumptions section it belongs to.

**Questions.** Every question for the client: the toolkit's drafted ones plus
any comment marked as a question and any he adds (**+ Add a question**). Each
gets **Send** (in the email), **Answered** (settled from the file, not
asked), **Strike** (drop it) or **Check first**. He can reword any of them.
Answers can be typed in the box under each question, but normally Claude puts
them there on a refresh.

**Email.** The email to the client, written from the questions marked Send.
He can edit it freely; **Copy the email** and paste into Outlook. If he
changes the questions after editing it, a yellow note offers to rebuild it.

**Plan inputs.** Single figures the plan and deck run on: retirement age, target
retirement income, the sale at retirement, starting portfolio, saved a year
today, ideal bank balance, overhead target, the savings by plan year, and
(under Assumptions) every rate and rule: returns, inflation, practice
multiple and growth, building value, refinance terms. The middle column is
the toolkit's starting figure (worked out from the documents and the firm's
usual rules, before anyone decides anything); type in "Your figure" to change
it, leave it blank to keep it. What 4Q proposes to the client is what he ends
up with here.
Also here: **Notes for the team** (anything that should shape the deck) and
**Biggest concerns** (the wording on the concerns slide).

**Recommendations.** Where the new savings come from: each recommendation
(raise fees, refinance, pay structure, overhead, and so on) with what it
frees up a year and how much of it gets invested in Year 1 and Year 2. The
ones the documents point to are ticked. Untick what does not fit, tick or add
what does, change amounts, move one to a later year or "later" (kept in view,
out of the plan), add a note. **Add from the library** brings in any
recommendation the firm has used; **Add a recommendation** writes a new one
(it joins the library for every client after). What stays ticked becomes the
Annual savings slide and the savings schedule.

**Projections.** A sandbox. It starts from the plan as it stands (his Plan
inputs, and the starting figure wherever he typed none). The worksheet behind the numbers (starting
portfolio, the sale, the practice levers, year-by-year savings) and a
**What if** box: change retirement age, income, sale, current savings,
overhead target or any savings step and the results recalculate at once.
Nothing is saved until **Use these figures**, which copies them onto Plan
inputs. **Back to the plan inputs** undoes his tries.

**Slides.** The whole deck as it would be built now, slide by slide, each
box that comes from this client outlined and numbered. He can change any
box's wording, **Use** or **Drop** what Claude drafted, take a slide out, add
his own after any slide, or include a slide that was left out. **+ Add a
slide after** opens the **slide library** first: occasional slides the team
has used before (practice model options, transition options, worst case
planning, sole prop vs S-corp, a deeper investments look, and others), with
[brackets] Claude fills with the client's figures; then nine blank layouts.
**Save to the slide library** on a slide he made keeps it for every client
after.
The filter shows Still needed / Check / Sure. **Build the deck** copies the
line to paste into Claude; the deck lands in the client folder and opens in
Keynote. It can be rebuilt any time.

**Notes & questions.** Everything written on the page in one list, with who
wrote it and where it stands. Nothing to do here; it is the overview.

## Questions he will ask

**Plan inputs vs Recommendations: where do I change a number?**
- Recommendations decide *where* the savings come from and how much of each
  gets invested in years 1 and 2. Change a recommendation's amount, timing or
  whether it is in at all there.
- Plan inputs hold single figures and rules: retirement age, income target,
  sale, building value, returns, bank balance, overhead target. Change those
  on Plan inputs.
- Savings by plan year appear on Plan inputs too. Leave them blank and they
  follow the recommendations. Type a year's savings there only to state that
  year's total outright; a typed year wins over the recommendations for that
  year.
- Projections is for trying things; **Use these figures** puts them on
  Plan inputs.

**When do I mark things?** Questions: before the email goes (Send / Strike).
Answers: after Claude refreshes with them (Answered / Still open / Team to
revisit). Nothing has to be marked before he can work Plan inputs.

**What does "provisional" mean?** Some questions are still waiting on the
client. He can work ahead; figures an answer changes are updated when the
answers come in, and his own figures stay.

**Will my work disappear?** No. It saves as he types, survives closing the
page, and Claude's refreshes only update what the documents produce.

**Who else sees it?** Anyone it is shared with (the analyst, the team). They
see his comments and marks; edits by anyone save to the same page.

**What does Claude do on its own vs when asked?** The page cannot start
Claude. The two buttons (**Check for new answers and documents**, **Build the
deck**) copy a line to paste into Claude. He can also just ask Claude in his
own words.

**What is the "starting figure" / does it mean 4Q's proposal?** No. It is the
toolkit's first draft from the documents and the firm's usual rules. 4Q's
proposal is what he decides on this page; the deck is built from his figures.
