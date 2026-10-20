#!/usr/bin/env python3
"""Oyler's figures, taken from the firm's existing expense workbook.

Seed data only, so the workbook layout can be judged before the statement
reader exists. Every figure here was read out of
_spec/cashflow/workbooks/Oyler Personal Expenses 2026-BB.xlsx rather than
computed, which is the point: it lets the generated workbook be compared
against the hand-built one line for line.

Note that file is an earlier draft than the published Assumptions. Two
figures moved between the two, both traced and recorded in RULES.md.
"""

PERSONAL = {
 'name': 'Personal',
 'accounts': [
  {'name': 'Personal Checking (Civista x0054)', 'balance': 11373,
   'periods': ['Jun 2025', 'Jul 2025', 'Aug 2025', 'Sep 2025'],
   'beginning': [3430.58, 12616.10, 82950.00, 81952.27],
   'transfers_in': [0, 130000, 0, 0],
   'additions': [60077.14, 151395.27, 34300.17, 73666.34],
   'transfers_out': [19500, 8000, 15000, 16500],
   'ending': [12616.10, 82950.00, 81952.27, 11373.06],
   'adj_out': [29500, 59778, 15687, 117806],
   'adj_in': [3771, 0, 0, 0],
   'surplus_expense': [31391.62, 73061.37, 20297.90, 9939.59]},
  {'name': 'Personal Money Market (US Bank x1145)', 'balance': 1581,
   'periods': ['Jun 2025', 'Jul 2025', 'Aug 2025', 'Sep 2025'],
   'beginning': [77060.51, 1163.64, 2161.60, 2201.41],
   'transfers_in': [0, 0, 0, 0],
   'additions': [6103.13, 997.96, 1032.72, 1029.76],
   'transfers_out': [82000, 0, 0, 0],
   'ending': [1163.64, 2161.60, 2201.41, 1581.17],
   'adj_out': [82000, 0, 0, 0], 'adj_in': [0, 0, 0, 0],
   'surplus_expense': [0, 0, 992.91, 1650.00]},
  {'name': 'Personal Checking (US Bank x2683)', 'balance': 295,
   'periods': ['Jun 2025', 'Jul 2025', 'Aug 2025', 'Sep 2025'],
   'beginning': [383, 177, 117, 143],
   'transfers_in': [500, 500, 800, 1855],
   'additions': [500, 500, 800, 1855],
   'transfers_out': [0, 0, 0, 0],
   'ending': [177, 117, 143, 295],
   'adj_out': [0, 0, 0, 0], 'adj_in': [0, 0, 0, 0],
   'surplus_expense': [706, 560, 774, 1703]},
  {'name': 'Personal Savings (Civista x0222)', 'balance': 1879,
   'periods': ['Jul 2026', 'Aug 2026', 'Sep 2026'],
   'beginning': [139, 1051, 965],
   'transfers_in': [0, 9000, 10000],
   'additions': [10000, 9000, 10000],
   'transfers_out': [0, 0, 0],
   'ending': [1051, 965, 1879],
   'adj_out': [0, 0, 0], 'adj_in': [0, 0, 0],
   'surplus_expense': [9088, 9086, 9086]},
 ],
 'liabilities': [
  ('Mortgage', 2665.45, 'x0054'), ('Mortgage', 4103.16, 'x0054'),
  ('Mortgage', 1906.28, 'x0054'), ('Truist (boat) loan', 1970.15, 'x0054'),
  ('MassMutual premium', 5000.00, 'x0222'),
  ('AuguStar (ALIC) premium', 4085.92, 'x0222'),
 ],
 'adjustments': [
  ('Civista x0054', 'Jun 2025', 'Transfer out', 19500,
   'Four round sums (7,000 / 2,500 / 2,500 / 2,500) plus 5,000, each matched '
   'to an addition on another Oyler account within two days.', 'High'),
  ('Civista x0054', 'Jun 2025', 'Card payment', 3724,
   'Actual card payment 3,724 against the four-period average of 7,658. The '
   'difference is carried back so one heavy month does not distort the '
   'average.', 'By rule'),
  ('Civista x0054', 'Jul 2025', 'Transfer in', 130000,
   'MassMutual policy loan of 80,000 on 7/3 and Amex draw of 50,000 on 7/6. '
   'Borrowing is never a deposit, so both are removed.', 'By rule'),
  ('Civista x0054', 'Jul 2025', 'Transfer out', 8000,
   'Round sums matched to additions on another Oyler account.', 'High'),
  ('Civista x0054', 'Aug 2025', 'Transfer out', 15000,
   'Round sums matched to additions on another Oyler account.', 'High'),
  ('Civista x0054', 'Sep 2025', 'Transfer out', 16500,
   'Round sums matched to additions on another Oyler account.', 'High'),
  ('US Bank x1145', 'Jun 2025', 'Transfer out', 82000,
   'Single sum of 82,000, same day as an addition of equal value on Civista '
   'x0054. Account funding, not spending.', 'High'),
  ('US Bank x2683', 'Aug 2025', 'Unmatched outflow', 0,
   'Counterparty account x3468 has no statement on file. Treated as a '
   'transfer so spending is not overstated, but unverified until that '
   'statement arrives.', 'Unverified'),
  ('Civista x0222', 'Jul 2026', 'Note', 0,
   'Account appears to fund life insurance premiums only (MassMutual and '
   'AuguStar). Expenses here are premiums rather than living costs.',
   'For review'),
 ],
}

MOONRIDGE = {
 'name': 'Moonridge',
 'accounts': [
  {'name': 'Moonridge Properties Checking (Wells Fargo x6986)',
   'balance': 40731,
   'periods': ['May 2026', 'Jun 2026', 'Jul 2026', 'Aug 2026'],
   'beginning': [48091.64, 29528.40, 10068.34, 36691.08],
   'transfers_in': [0, 0, 0, 0],
   'additions': [47428.13, 2928.13, 59010.93, 26428.13],
   'transfers_out': [0, 0, 0, 0],
   'ending': [29528.40, 10068.34, 36691.08, 40731.02],
   'adj_out': [43603, 0, 10000, 0],
   'adj_in': [3933.83, 3933.83, 3933.83, 3933.83],
   'surplus_expense': [22388.37, 22388.19, 32388.19, 22388.19]},
 ],
 'liabilities': [],
 'adjustments': [
  ('Wells Fargo x6986', 'May 2026', 'Adjustment out', 43603,
   'Single large outflow in the first period only. Not repeated in the other '
   'three, so excluded from the run rate.', 'For review'),
  ('Wells Fargo x6986', 'Jul 2026', 'Adjustment out', 10000,
   'One-off outflow, not repeated in the other periods.', 'For review'),
  ('Wells Fargo x6986', 'All', 'Adjustment in', 3934,
   'Recurring monthly item added back across all four periods.', 'By rule'),
 ],
}

BIZ = {
 'name': 'Biz',
 'accounts': [
  {'name': 'Practice Checking (Civista x4728)', 'balance': 109434,
   'periods': ['May 2026', 'Jun 2026', 'Jul 2026', 'Aug 2026'],
   'beginning': [106977.98, 17461.84, 21741.46, 75035.80],
   'transfers_in': [39000, 14000, 52000, 0],
   'additions': [342309.96, 323818.96, 367566.15, 317027.90],
   'transfers_out': [5000, 20000.08, 0, 0],
   'ending': [17461.84, 21741.46, 75035.80, 109433.61],
   'adj_out': [83660.18, 23395.67, 0, 19000],
   'adj_in': [0, 0, 24100.92, 16521.11],
   'surplus_expense': [343165.93, 299539.26, 314271.81, 282630.09]},
  {'name': 'Eden Properties Checking (Civista x3309)', 'balance': 469,
   'periods': ['Apr 2026', 'May 2026', 'Jun 2026', 'Jul 2026'],
   'beginning': [454, 460, 465, 469],
   'transfers_in': [0, 0, 0, 0],
   'additions': [15, 15, 15, 15],
   'transfers_out': [0, 0, 0, 0],
   'ending': [460, 465, 469, 469],
   'adj_out': [0, 0, 0, 0], 'adj_in': [0, 0, 0, 0],
   'surplus_expense': [0, 0, 0, 0]},
 ],
 'liabilities': [
  ('Civista loan x7810', 9622.89, 'x4728'),
  ('Civista line of credit x2045', 2326.00, 'x4728'),
  ('Equipment loan x..68', 9900.00, 'x4728'),
  ('Note x..99', 11000.00, 'x4728'),
 ],
 'adjustments': [
  ('Civista x4728', 'May 2026', 'Transfer in', 39000,
   'Round sums arriving from another Oyler entity account.', 'High'),
  ('Civista x4728', 'May 2026', 'Adjustment out', 83660,
   'Large non-recurring outflow in the first period.', 'For review'),
  ('Civista x4728', 'Jul 2026', 'Transfer in', 52000,
   'Round sums arriving from another Oyler entity account.', 'High'),
  ('Civista x3309', 'All', 'Note', 0,
   'Dormant. $15 a month in, nothing out. Holding account rather than an '
   'operating one.', 'For review'),
 ],
}

ENTITIES = [PERSONAL, MOONRIDGE, BIZ]
