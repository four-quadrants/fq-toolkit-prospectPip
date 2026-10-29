# The lead advisor's follow-up emails: what they ask, and what in the documents asks it

Read 22 October 2026 from the five emails the firm saved in
`~/Desktop/FQ_Toolkit/FollowUps` on 8 October (Kinsler, Oyler, Rebol, Meier,
Wright). They were saved on the old Mac but never worked into the pipeline.
This is the pattern, so the due diligence step can draft the next one.

## The shape never changes

    Hi {first name(s)},

    Happy {weekday}; our team has been going through all of the information
    that you have provided for the consultation with a fine toothed comb over
    the past weeks/days. In doing so, they have developed some
    questions/items that they wanted to have me follow up on. I've cut/paste
    their questions below:

    1. ... (10 to 17 numbered questions)
    N. Lastly from a personal retirement savings standpoint, it appears that
       ... Does this appear correct to you?

    I think this is all the clarity we have on my end for now; ... From a
    priority standpoint, we're most concerned about #a, b, c first and
    foremost. Lastly, please email this information by {day, date, time} if
    not sooner so my team can continue their research and stay on schedule
    for the {consult date} consultation. ...

The deadline is about a week before the consult: Oyler 10/9 for 10/16, Rebol
6/22 for 6/29, Wright 8/31 for 9/4, Meier 8/3 for 8/20, Kinsler 7/27 for 8/11.

## The questions, by what produces them

| Kind | Example | Seen in | Detectable from |
|---|---|---|---|
| Accounts we have no statements for | "3 additional USAA accounts ... x0407, x1025, x3368" | all 5 | transfers to or from an account not on file |
| An unexplained recurring payment or deposit | "$3,000/month from x3231"; "$2,928.13 from America Pacific"; "Leasing services $450.75 and $364.75" | all 5 | recurring movements with no matching liability, lease or income |
| A one-off large movement | "$52,500 deposit on 6/25"; "$113k of closing funds"; "$21,650 check marked Loan" | 4 of 5 | outliers against the account's own run rate |
| Loan details missing or not adding up | "lake lot payment should be $840 but you pay $1,000"; "CiVista looks like 8 years not 9"; "Wellington normal payment" | all 5 | a payment with no schedule; amortisation against the stated term |
| A debt on the credit report and nowhere else | "a HELOC from Stockyards according to the credit reports" | Kinsler (and Meier's missing report) | credit report tradelines against statements and the IC form |
| New borrowing | "a new $50,000 Amex loan in July"; "HELOC tapped for $49,000" | 2 of 5 | a credit from a lender into a personal account |
| Stated against actual | "rental income stated $7,650 / $4,000 / $8,000; the bank shows $2,300 / $3,100 / $6,750" | Meier | IC form or prior notes against the statements |
| Documents still missing | 2025 return or draft; divorce decree; birthdate; full credit report; provider report; profit-share illustration; second valuation | all 5 | the checklist (already built) |
| Insurance gaps | "policies on Chris but nothing on Kate"; Northwestern Mutual details | 2 of 5 | insurance documents per insured person |
| Entity status | "SFM Enterprises, CV-ICB II, MBO PB: still in place?" | 2 of 5 | entities on the returns with no current documents |
| Practice trend | "revenue dropped from $3.0M to $2.4M"; "1099 dentists in 2024" | 2 of 5 | the P&L and production series |
| Employee loans | "loan to Corey Alves, $36,419, two checks" | 2 of 5 | checks to a person marked loan |
| Capacity (always the same wording) | "how far booked out at 90%+ ... hygiene ... perio ... new patient" | 4 of 5 | standard; asked unless the call notes answer it |
| Retirement savings confirmation (always last) | "it appears you are projecting to save $14,400 for 2026 ... Does this appear correct?" | all 5 | the current-savings figure the plan uses |

## What this means for the build

Most of these come from detectors the toolkit already has, or nearly has
(transfers to accounts not on file, recurring movements, one-off outliers,
the checklist). The new pieces are the credit report reader, the loan
schedule check, and stated-against-actual. The capacity and retirement
savings questions are standing items with the client's figures filled in.

Each drafted question carries the finding behind it (document, page, figure),
the analyst strikes or answers what they can, and the rest goes into this
email for the lead advisor to proof and the onboarding specialist to send.
