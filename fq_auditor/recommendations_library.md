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

<!-- Added Nov 2026 from the twenty most recent delivered consult decks
     (2025 and 2026 signed clients). "Seen" counts are out of those twenty. -->

## Ideal practice bank balance [ideal_bank_balance]
- When: every consult; the first step of the new cash-flow process.
- Signs: practice cash thin or swinging month to month; no stated reserve.
- Size: a target balance of roughly one month or more of overhead (seen
  $80k to $300k); raises, savings and debt strategies start once it is
  reached. Not a savings line itself.
- Seen: all twenty.

## Business line of credit [line_of_credit]
- When: no line of credit, or one too small for the practice's cash swings.
- Signs: no LOC on the debt schedule; short-term or emergency loans.
- Size: about the ideal bank balance. A backstop, not savings.
- Seen: eighteen of twenty.

## Monthly monitoring and a 12-month spending pause [spending_freeze]
- When: every consult, while the new structure settles and reserves build.
- Signs: discretionary spending rising, cash flow unstructured.
- Size: not sized; a rule, monitored monthly.
- Seen: all twenty.

## No new debt without the firm [no_new_debt]
- When: debt added quickly, or emergency borrowing.
- Signs: several new loans in a year; short-term or merchant-cash loans.
- Size: not sized; a rule (often "no new debt for 18+ months").
- Seen: several decks.

## Redirect consumer debt payments [consumer_debt]
- When: credit card, auto or buy-now-pay-later payments once those debts are cleared.
- Size: the payments a year, redirected to savings.
- Seen: one deck.

## Practice pays rent to the owner's building LLC [rent_strategy]
- When: the owner (or the owner's LLC) owns the building the practice uses.
- Signs: building loan or property tax with no rent paid, or rent below market.
- Size: a set monthly rent; take-home kept similar, the practice's cash flow
  and the owner's tax position improve.
- Seen: about nine decks.

## Spouse on payroll and in the 401(k) [spouse_payroll]
- When: the spouse works in or for the practice unpaid, or outside the plan.
- Size: a modest spouse W-2 plus the 401(k) deferral and match it opens.
- Seen: about eight decks.

## Fund the HSA [hsa]
- When: on a high-deductible plan and the HSA is unfunded or sitting in cash.
- Size: the family HSA limit a year, invested.
- Seen: about six decks.

## Pre-tax and after-tax balance [tax_diversification]
- When: nearly all savings are pre-tax (401(k), SEP, IRA).
- Size: not sized; build taxable (non-qualified) savings so retirement tax
  brackets can be managed.
- Seen: about eight decks.

## SEP IRA instead of a new 401(k) [sep_ira]
- When: a small practice where staff make a 401(k) costly, or a SEP already fits.
- Size: the SEP contribution as a share of owner pay, and the tax saved.
- Seen: two decks.

## Interim IRA while a new plan waits [ira_interim]
- When: the current 401(k) is weak (no match, poor funds) and a new plan
  must wait for steady cash flow.
- Size: the IRA maximum against today's contribution.
- Seen: one deck.

## Stop a profit share that mostly pays staff [stop_profit_share]
- When: the profit share's benefit goes mostly to staff.
- Size: the contribution, redirected to owner distributions and savings.
- Seen: one deck.

## Roth deferrals to traditional [roth_to_traditional]
- When: a high-bracket doctor deferring to Roth while owing large taxes.
- Size: the deduction missed at the current bracket.
- Seen: one deck.

## 529 and college funding [college_529]
- When: children's 529s exist with the wrong allocation, or college is undersaved.
- Size: the shortfall to the college target; underperformance against the firm.
- Seen: three decks.

## Firm manages the investments [move_investments]
- When: every consult with investment accounts: annuities, insurance-based
  401(k)s, commissioned share classes, speculative or cash-heavy accounts.
- Size: what each account would have earned at the firm's returns (dollars
  and %), and the total.
- Seen: all twenty.

## Consolidate and roll over accounts [consolidate_accounts]
- When: old employer plans left behind, many accounts holding the same
  funds, or a scattered portfolio (hundreds of positions, crypto, heavy trading).
- Size: not sized; count of accounts and overlap, and underperformance.
- Seen: about five decks.

## Replace illiquid private placements [replace_illiquid]
- When: a large share of savings in private placements with little reporting.
- Size: the share of savings and its underperformance.
- Seen: one deck.

## Monthly dental accounting by the firm [monthly_accounting]
- When: reactive or outside CPA, books not reconciled, financials that do
  not tie to the returns.
- Size: the monthly fee; the benefit is books that tie to the returns and
  advice from monthly figures.
- Seen: all twenty.

## Review and amend prior returns [amend_returns]
- When: errors or missed deductions in the returns on file.
- Size: the refund or deduction found, once.
- Seen: about fifteen decks.

## Quarterly tax projections and withholding [quarterly_estimates]
- When: tax surprises, balances due, penalties or payment plans.
- Size: custom quarterly estimates (or higher W-2 withholding) instead of
  canned ones; stated as no surprises.
- Seen: about nine decks.

## Capture missed deductions [missed_deductions]
- When: deductions the returns leave unused: Section 179 or bonus
  depreciation, cost segregation, shareholder health insurance through the
  W-2, the Augusta rule, accountable plan, HSA or IRA, R&D credit.
- Size: each with a dollar estimate; seen $10k to $15k+ a year in total.
- Seen: most decks.

## Pass-through entity tax election [ptet]
- When: an S corporation or partnership owner in a state that offers PTET.
- Size: state tax on pass-through income, deducted federally; the federal tax saved.
- Seen: about six decks.

## Clear shareholder loans and fix basis [shareholder_loan]
- When: loans to or from the shareholder on the books, or distributions above basis.
- Size: the tax exposure if the loan is treated as a distribution, or
  distributions reclassified as loan repayment.
- Seen: about twelve decks.

## Entity and ownership clean-up [entity_structure]
- When: the building inside the practice entity, an S corporation owned by
  an entity that cannot own one, or several entities with unclear ownership.
- Size: usually not sized (liability and tax exposure); an invalid
  S-corp owner is sized as corporate tax on profits since the election.
- Seen: about nine decks.

## Contractor or employee [worker_classification]
- When: associates or staff paid as 1099 contractors who are employees in practice.
- Size: the payroll tax exposure a year.
- Seen: one deck.

## Outside 1099 income through the practice [route_outside_income]
- When: the owner earns 1099 income outside the practice.
- Size: the practice's cash flow change a month; take-home kept similar.
- Seen: one deck.

## Spouse RSU tax planning [rsu_tax_planning]
- When: a spouse receives large RSU grants without enough withholding.
- Size: the projected tax due at vesting.
- Seen: one deck.

## Transition plan [transition_plan]
- When: the owner is within about ten years of retiring, or the practice is co-owned.
- Size: not sized; partial or full sale and adding owners compared.
- Seen: about eight decks.

## Practice model and schedule [practice_model]
- When: two locations or two doctors on an unsustainable schedule, heavy
  reliance on insurance plans, or a practice "stuck in the middle".
- Size: not sized; options compared (combine locations, drop evenings or
  Saturdays, drop plans, expand).
- Seen: several decks.
