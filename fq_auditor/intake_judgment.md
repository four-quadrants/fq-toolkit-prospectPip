# How the firm judges a document request

Read by Claude when it checks each checklist item (checklist_claude.py). Claude
keeps this list: when the analyst overrules a verdict, the reason belongs here
so the next client is judged the same way.

## Ask only for what blocks the work

- The client is asked again only for something the plan cannot be built
  without. Anything else is a note for the team, not an ask.
- Prefer a confirmation over a re-send. If a document is probably complete but
  one detail is unclear, ask the client to confirm that detail.

## Periods and years

- A P&L or report that looks a few days or weeks short of year-end (printed
  December 10, 12, and so on) is satisfied. Ask the client to **confirm** it is
  their year-end figure, or whether there were material entries after that
  date. Do not ask them to send it again.
- A practice bought or opened partway through a year has a short first year;
  that is not a gap.
- Year-to-date reports may run past the date asked for (through October when
  September was asked). That is fine.

## Production reports

- The overall practice numbers matter most. Production that arrives combined
  across providers (owner, associate, EFDA in one report) satisfies the item
  unless the request specifically needs the owner's production on its own.
  Note "owner and associate production combined; may need splitting later"
  for the team. Do not ask the client to rerun reports.
- Hygiene reported separately is a bonus, not a requirement.

## Debts and pending purchases

- Terms typed by the client (amount, rate, term, payment), even from a loan
  estimate, are enough for now. The contract or closing disclosure is a note
  for later, not an ask.

## Other entities

- If the documents name an entity the client may own (another LLC, a real
  estate company) and no return for it arrived, ask once whether it files a
  return, and to send it or say there is none.
