# Recommendations library

Every recommendation the firm has put on a consult deck's "Where the money
comes from" slide, with when it applies and how it is sized. Claude reads this
for each client (recommendations.py) and proposes the ones the documents point
to; the lead advisor decides on the consult review.

Claude keeps this list; nobody edits it by hand. A recommendation the lead
advisor adds on a consult review is appended when the review is pulled in.
One `##` heading per recommendation, the key in brackets, then the four lines.
No client names: say what was true, not who it was true for.

## Current savings [current]
- When: always, first row.
- Signs: retirement plan deferrals, matches and other contributions on the
  statements and the IC form.
- Size: what is saved a year today, plus any extra 401(k) under a new pay
  structure. All of it invested.
- Seen: every deck.

## Bank surplus balances [personal_surplus] [practice_surplus] [llc_surplus]
- When: balances above what the accounts need.
- Signs: personal balances above two months of spending; practice balances
  above the ideal practice balance (one month of expenses); LLC or other
  entity accounts carrying cash.
- Size: the surplus, once. About half invested (one-time cash; some kept back).
- Seen: most decks; a large one put $550k of $707k to work.

## New payroll and distribution structure [pay_structure]
- When: an S corporation owner whose W-2 and distributions are out of balance
  (tax surprises, irregular distributions).
- Signs: W-2, total tax and distributions on the returns.
- Size: W-2 down to a reasonable figure, 401(k) to the maximum, distributions
  set so take-home is unchanged; the practice keeps the difference.
- Seen: most S-corp decks.

## Incorporate the practice [s_corp]
- When: a sole proprietor (Schedule C).
- Signs: no 1120-S, no W-2 from the practice, self-employment tax on all
  profit, swinging tax estimates.
- Size: the self-employment tax saved on profit above a reasonable W-2; the
  advisor sizes it. Usually paired with a new pay structure after the election.
- Seen: a sole-prop deck had its own "sole prop vs S-corp" slide.

## Stop debt acceleration [stop_acceleration]
- When: loans are being paid above their schedule while savings are thin.
- Signs: payments on the bank statements larger than the scheduled payment on
  the loan statement, debt sheet or credit report (mortgage, HELOC, auto,
  building loan).
- Size: the extra paid a month, times 12. About three quarters invested.
- Seen: two decks; one freed $41,100 a year, one combined it with removing PMI.

## Practice debt refinance [refinance]
- When: costly practice loans (5% or more, revolving, or no stated rate), or
  several loans on short schedules (equipment financed over five years).
- Signs: the debt sheet and loan statements; loans added recently.
- Size: the candidates' payments now, against their balance over 10 years at
  7%; the difference is freed. About a quarter invested. Often year two, "only
  if needed for cashflow".
- Seen: several decks, stated as a range ("$8-9k/mo").

## Loan paid off [loan_dropoff]
- When: a loan ends within the year (not a balloon).
- Signs: maturity within a year and a balance under two years of payments.
- Size: the payment, times 12. Usually not invested; it supports cashflow.
- Seen: an Itero scanner loan dropping off.

## Lower overhead [overhead]
- When: always, as a target.
- Size: 3% of collections a year, phased in (a small share invested in year
  one, more each year).
- Seen: every deck, often combined with a fee increase and adjustments.

## Fee increase [fees]
- When: the fee study shows fees below the benchmark.
- Signs: the fee study (percent below the 80th or 90th percentile).
- Size: gross production x the gap x the fee-for-service share, to the owner.
- Seen: "+3% / +4% / +5% fee increase" on most decks.

## Lower production adjustment % [adjustment]
- When: adjustments (insurance write-offs) are high, usually 25% or more.
- Signs: production reports; adjustments against gross production.
- Size: the gap to 16%, on net production, to the owner.
- Seen: "-3.3% / -5% adjust %".

## Improved collection % [collections]
- When: collections below 99.5% of net production.
- Size: the gap, on net production, to the owner.

## New patients back up [new_patients]
- When: new patients as a share of patients fell from the prior year.
- Size: patients x the drop x net production per patient, to the owner.

## Hygiene and doctor production [hygiene] [per_day]
- When: hygiene days are short of twice the doctor days with rooms free, or
  production per day is low.
- Size: added hygiene days, the doctor work they pull through, or more
  patients a day; to the owner.
- Seen: "3% increase in hygiene share", "+0.9 more patients a day", "8.8%
  increase in doctor production a day".

## Current growth trend continues [growth_trend]
- When: the practice has grown steadily for two or three years and is still
  growing.
- Signs: production or collections by year (production reports, P&Ls).
- Size: the trend carried forward a year, on revenue; the owner's share at the
  target overhead. Usually not invested in year one.
- Seen: "current trending, 3 years: $330,000 revenue, $88,300 to owners".

## A marketing campaign or contract ends [marketing_ends]
- When: a large marketing, consulting or service contract is ending or can be
  ended.
- Signs: a recurring marketing or consultant line on the P&L or the bank
  statements (direct mail, an agency, a practice consultant), or the client
  says it is ending.
- Size: the annual cost. A small share invested.
- Seen: "direct mail campaign ends: $33,700".

## Associate or doctor days change [associate_change]
- When: an associate or the owner is changing days.
- Signs: the IC form, call notes, payroll.
- Size: the change in production or pay; the advisor sizes it.
- Seen: "associate drops 2 days a week: $112,500".

## New 401(k) [new_401k] and profit share [profit_share]
- When: the household saves through SIMPLE IRAs or no 401(k); or a profit
  share is in place that would serve better as distributions, or is missing.
- Size: the extra the plan allows, all invested.
- Seen: "replace the SIMPLE IRA with a new 401(k) and max it", "divert
  profit share to take-home distributions".

## Life insurance and annuities [life_term] [cash_values]
- When: permanent life (universal, whole, VUL) or an annuity with cash value.
- Signs: policy and annuity statements.
- Size: premium saved by moving to term (a share invested); the cash value
  invested once when the policy is replaced.
- Seen: four decks.

## Remove PMI [remove_pmi]
- When: a mortgage still carries PMI with enough equity to drop it.
- Signs: mortgage statement escrow lines.
- Size: the PMI a year.

## Sell a building or property [sell_property]
- When: a building or property is a drag, or the client wants out.
- Size: the net proceeds, once; a share invested.
- Seen: "sell the building: $200,000, $100,000 invested".

## Better tax management [tax_management]
- When: always worth considering; sized by the advisor.
- Seen: "$32,500 to $101,700", a small share invested.

## $5,000 rule [five_k_rule]
- When: every consult. The firm advises on any decision over $5,000; not sized.
