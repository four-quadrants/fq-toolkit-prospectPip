#!/usr/bin/env python3
"""Build the FQ fact dictionary workbook.

The dictionary is the spine of the whole pipeline: every fact the firm needs,
where it can be read, what it can be checked against, and which outputs consume
it. A fact with no source becomes a follow-up question; a fact with two sources
that disagree becomes a conflict flag; a fact with a source becomes a filled
field on the Prospect Summary, the Assumptions and the consult deck.

The counts in "In N of 17 plans" were measured across the firm's own Assumptions
documents rather than assumed, so a row that looks optional is optional because
a third of the plans do without it.
"""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

import os

NAVY = '16324F'
# Beside this script, wherever it is run from: the same folder is reached by a
# different absolute path from the shell than from the editor.
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'FQ_Fact_Dictionary_v1.xlsx')

hdr = Font(name='Arial', bold=True, color='FFFFFF', size=10)
sec = Font(name='Arial', bold=True, color=NAVY, size=10)
body = Font(name='Arial', size=10)
note = Font(name='Arial', italic=True, color='6B7683', size=9)
fill_hdr = PatternFill('solid', fgColor=NAVY)
fill_sec = PatternFill('solid', fgColor='E8EEF4')
fill_in = PatternFill('solid', fgColor='FFF9E0')
box = Border(bottom=Side(style='thin', color='DDD8D0'))
wrap = Alignment(wrap_text=True, vertical='top')

COLS = [('Section', 20), ('Fact', 34), ('Type', 10), ('In N of 17 plans', 9),
        ('Source documents (where it can be read)', 38),
        ('Source kind', 14),
        ('Second source (for conflict check)', 30),
        ('Consumed by', 26), ('Status', 15), ('Your notes', 30)]

# A source that is itself one of the firm's own outputs cannot be an input:
# reading overhead off the OH worksheet, or personal expenses off the Personal
# Expenses workbook, would make the pipeline feed on what it just produced.
# These are the artifacts this project replaces, so every fact that currently
# leans on one needs a client document behind it instead.
FQ_DERIVED = (
    'personal expenses workbook',
    'prior assumptions',
    'assumptions, prior year',
    'fee study',
    'oh worksheet',
    'initial notes',
)


def is_fq(text):
    t = (text or '').lower()
    return any(k in t for k in FQ_DERIVED)


def source_kind(source):
    """What the PRIMARY source is.

    Judged on the primary alone. A client document that happens to be checked
    against one of our outputs is still a client document; an earlier version
    looked at both and so condemned three perfectly good rows.
    """
    t = (source or '').lower()
    if t.startswith('firm standard'):
        return 'Firm constant'
    if is_fq(t):
        return '4Q-DERIVED'
    if 'computed' in t or t.startswith('sum of') or t.startswith('65%'):
        return 'Computed'
    return 'Client document'


def check_source(second):
    """The second source, but only when it is genuinely independent.

    Reconciling a figure against a workbook we built from that same figure is
    not a check. Those are struck through here rather than counted, so the
    tally of reconcilable facts stays honest.
    """
    if not second:
        return ''
    if is_fq(second):
        return '(%s — our own output, not a check)' % second
    return second

S = None   # section-header marker row
ROWS = [
    ('PLAN BASIS', S),
    ('', 'Inflation rate', '%', 17, 'Firm standard (3.2%)', '',
     'Assumptions', 'Firm constant'),
    ('', 'Retirement age / date', 'date', 17, 'IC form; discovery call',
     'Assumptions, prior year', 'Assumptions, deck', 'Have'),
    ('', 'Life expectancy', 'age', 14, 'Firm standard (90)', '',
     'Assumptions', 'Firm constant'),

    ('REAL ESTATE', S),
    ('', 'Primary residence value', '$', 9,
     'Zillow / Realtor.com; client estimate', 'Credit report (mortgage)',
     'Assumptions', 'Derived'),
    ('', 'Other property values', '$', 15,
     'Zillow / Realtor.com; client estimate', 'Tax return Sch E',
     'Assumptions', 'Derived'),
    ('', 'Property growth rate / std dev', '%', 17,
     'Firm standard (3.0% / 0.5%)', '', 'Assumptions', 'Firm constant'),

    ('QUALIFIED ASSETS', S),
    ('', '401k balance', '$', 13, '401k statement', 'Credit report; payroll',
     'Assumptions, Prospect Summary', 'Readable'),
    ('', '401k holdings & allocation', 'text', 13, '401k statement', '',
     'Assumptions', 'Readable'),
    ('', '401k YTD return', '%', 13, '401k statement', '',
     'Assumptions', 'Readable'),
    ('', 'IRA / Roth balance', '$', 16, 'IRA statement',
     'Tax return (1099-R, 5498)', 'Assumptions', 'Readable'),
    ('', 'Assumed return / std dev', '%', 17,
     'Firm standard (9.0% / 12.0%)', '', 'Assumptions', 'Firm constant'),

    ('NON-QUALIFIED ASSETS', S),
    ('', 'Bank account balance', '$', 17, 'Bank statement',
     'Debt schedule; prior Assumptions', 'Assumptions, Prospect Summary',
     'Readable'),
    ('', 'Avg monthly deposit', '$', 13, 'Bank statement (computed)',
     'P&L, for practice accounts', 'Assumptions', 'COMPUTE'),
    ('', 'Avg monthly expense', '$', 13, 'Bank statement (computed)',
     'Personal Expenses workbook', 'Assumptions', 'COMPUTE'),
    ('', 'Avg monthly surplus', '$', 13, 'Bank statement (computed)', '',
     'Assumptions', 'COMPUTE'),
    ('', 'Brokerage balance', '$', 17, 'Brokerage statement',
     'Tax return (1099-B / DIV)', 'Assumptions', 'Readable'),
    ('', 'EXISTENCE of an account', 'acct #', None,
     'Transfers in/out on OTHER statements', '', 'Follow-up email',
     'DETECT - ghost acct'),

    ('PRACTICE VALUE', S),
    ('', 'Practice value', '$', 17, '65% of annualised revenue (computed)',
     'Formal valuation report', 'Assumptions, deck', 'COMPUTE'),
    ('', 'Practice building value', '$', 10, 'Client estimate; appraisal',
     'Balance sheet', 'Assumptions', 'Ask'),

    ('LIABILITIES (per loan)', S),
    ('', 'Lender & last 4', 'text', 17, 'Debt schedule; credit report',
     'Bank statement (payee)', 'Assumptions, Prospect Summary', 'Readable'),
    ('', 'Original amount', '$', 17, 'Debt schedule; loan agreement',
     'Credit report', 'Assumptions', 'Readable'),
    ('', 'Current balance', '$', 17, 'Debt schedule; credit report',
     'Balance sheet', 'Assumptions, Prospect Summary', 'Readable'),
    ('', 'Interest rate', '%', 10, 'Loan agreement; debt schedule',
     'Credit report', 'Assumptions', 'Often missing'),
    ('', 'Term / maturity', 'date', 10, 'Loan agreement; debt schedule',
     'Amortisation check', 'Assumptions', 'Often missing'),
    ('', 'Monthly payment', '$', 17, 'Debt schedule',
     'Bank statement; credit report', 'Assumptions, Prospect Summary',
     'CONFLICT-PRONE'),
    ('', 'Escrow portion', '$', None, 'Mortgage statement', '',
     'Assumptions', 'Often missing'),
    ('', 'Line of credit limit & balance', '$', 4,
     'Credit report; bank statement', 'Debt schedule', 'Assumptions',
     'Readable'),

    ('INCOME', S),
    ('', 'Owner W-2', '$', 13, 'Payroll; W-2; 1120-S officer comp',
     'P&L Doctor Wages', 'Assumptions, Prospect Summary', 'Readable'),
    ('', 'Net profit', '$', 13, 'P&L; 1120-S', '', 'Assumptions', 'Readable'),
    ('', 'Net distributions', '$', 13, 'K-1; bank transfers',
     'Balance sheet equity', 'Assumptions', 'Readable'),
    ('', 'Spouse income', '$', None, 'W-2; personal 1040', '',
     'Assumptions', 'Ask'),
    ('', 'Rental income', '$', None, 'Tax return Sch E; lease',
     'Bank statement deposits', 'Assumptions', 'CONFLICT-PRONE'),
    ('', 'Social Security assumption', '%', 8,
     'Firm standard (40% at 65)', '', 'Assumptions', 'Firm constant'),

    ('EXPENSES', S),
    ('', 'Personal expenses, monthly', '$', 17,
     'Personal bank statements (computed)', 'Tax return Sch A; credit report',
     'Assumptions', 'COMPUTE'),
    ('', 'Personal expenses incl. debt / ins / savings', '$', 17,
     'Personal bank statements (computed)', 'Debt schedule + policies',
     'Assumptions', 'COMPUTE'),
    ('', 'Practice expenses, monthly', '$', None,
     'Practice bank statements (computed)', 'P&L total expenses ÷ 12',
     'Assumptions, Prospect Summary', 'COMPUTE'),
    ('', 'Retirement expense target', '$', 17,
     'Discovery call; client estimate', '', 'Assumptions', 'Ask'),

    ('CASHFLOW BY ACCOUNT', S),
    ('', 'Account is practice or personal', 'class', None,
     'Statement header (entity name on the account)',
     'P&L / tax return entity list', 'Assumptions, Prospect Summary',
     'CLASSIFY'),
    ('', 'Beginning / ending balance', '$', None, 'Bank statement', '',
     'Assumptions', 'Readable'),
    ('', 'Additions (true income)', '$', None,
     'Bank statement, net of transfers', 'P&L income; K-1',
     'Assumptions', 'COMPUTE'),
    ('', 'Expenses (true outflow)', '$', None,
     'Bank statement, net of transfers', 'P&L expenses',
     'Assumptions', 'COMPUTE'),
    ('', 'Transfers in / out (netted off)', '$', None,
     'Bank statement, matched both sides', '', 'Assumptions',
     'COMPUTE - match pairs'),
    ('', 'Credit-card payment adjustment', '$', None,
     'Bank statement + card statement', '', 'Assumptions',
     'COMPUTE - avoid double count'),
    ('', 'Monthly surplus / (deficit) per account', '$', None,
     'Additions less expenses (computed)', '',
     'Assumptions, Prospect Summary', 'COMPUTE'),
    ('', 'Weighted monthly average', '$', None,
     'Months weighted, per the workbook', '', 'Assumptions', 'COMPUTE'),
    ('', 'Household combined net', '$', None,
     'Sum across accounts (computed)', '', 'Assumptions, Prospect Summary',
     'COMPUTE'),
    ('', 'Count of deficit months', 'count', None,
     'Per account (computed)', '', 'Prospect Summary', 'COMPUTE'),
    ('', 'Personal / business comingling', 'flag', None,
     'Personal spend on a practice account', '', 'Follow-up email',
     'DETECT - comingling'),

    ('INSURANCE', S),
    ('', 'Life: company, policy #, type', 'text', 17,
     'Policy / annual statement', '', 'Assumptions', 'Readable'),
    ('', 'Life: death benefit', '$', 17, 'Policy / annual statement', '',
     'Assumptions', 'Readable'),
    ('', 'Life: premium & expiration', '$ / date', 17,
     'Policy / annual statement', 'Bank statement (premium debit)',
     'Assumptions', 'Readable'),
    ('', 'Disability: monthly benefit', '$', 15, 'Policy', '',
     'Assumptions', 'Often missing'),
    ('', 'BOE: monthly benefit & wait', '$', 15, 'Policy', '',
     'Assumptions', 'Often missing'),
    ('', 'Umbrella coverage', '$', 16, 'Policy / declarations page', '',
     'Assumptions', 'Often missing'),
    ('', 'Spouse coverage present?', 'y/n', None, 'Policies provided', '',
     'Follow-up email', 'DETECT - gap'),

    ('SAVINGS & CONTRIBUTIONS', S),
    ('', '401k deferral / year', '$', 17, 'Payroll; 401k statement',
     'Tax return', 'Assumptions', 'Readable'),
    ('', 'Employer match %', '%', 17, 'Payroll; plan document', '',
     'Assumptions', 'Readable'),
    ('', 'IRA contribution', '$', 17, 'IRA statement; 1040', '',
     'Assumptions', 'Readable'),
    ('', 'Profit share allocation', '$', None,
     'Year-end TPA illustration', '', 'Assumptions', 'Standing ask'),
    ('', 'Total annual savings', '$', 17, 'Sum of the above (computed)', '',
     'Assumptions, follow-up email', 'COMPUTE'),

    ('PRACTICE OPERATIONS', S),
    ('', 'Gross / net production', '$', None, 'Practice Analysis',
     'Analysis Provider Summary', 'Prospect Summary, deck', 'Readable'),
    ('', 'Production by provider', '$', None,
     'Analysis Provider Summary', 'Days-worked document',
     'Prospect Summary, deck', 'Readable'),
    ('', 'Total / new patients', 'count', None,
     'Practice count documents (.docx)', 'Provider Summary',
     'Prospect Summary', 'Readable'),
    ('', 'Doctor days worked', 'count', None,
     'Practice count documents (.docx)', '', 'Prospect Summary', 'Readable'),
    ('', 'Overhead %', '%', None, 'P&L', 'Tax return (1120-S)',
     'Prospect Summary, deck', 'COMPUTE'),
    ('', 'Fee positioning vs NDAS', '%', None, 'Fee schedule + fee study',
     '', 'Prospect Summary, deck', 'COMPUTE'),
    ('', 'Capacity / booked out', 'text', None,
     'IC form (stale once staff change)', '', 'Follow-up email',
     'Standing ask'),
    ('', 'Staff roster & wages', 'text', None, 'Payroll report',
     'P&L Salaries', 'Prospect Summary', 'Readable'),

    ('ENTITIES & STRUCTURE', S),
    ('', 'Entity list & ownership %', 'text', None, 'Tax returns; K-1s',
     'Operating agreement', 'Assumptions, deck', 'Readable'),
    ('', 'Entity still active?', 'y/n', None, 'Current-year return',
     'Prior-year return', 'Follow-up email', 'DETECT - gap'),
    ('', 'Associate comp structure', 'text', None, 'Employment agreement',
     'P&L associate expenses', 'Prospect Summary', 'Readable'),
    ('', 'Lease: building to practice', 'text', None, 'Lease document',
     'P&L Rents', 'Assumptions', 'Often missing'),
]

LEGEND = [
    'The yellow column is yours. Corrections, facts I have missed, sources I '
    'have named wrongly — put them there and I will rebuild from it.',
    'Status — Readable: a document states it outright. COMPUTE: we '
    'calculate it. DETECT: it is found by comparing documents, not by reading '
    'one. Ask: only a person can answer. CONFLICT-PRONE: observed disagreeing '
    'across sources in your own follow-up emails.',
    '"In N of 17 plans" is measured, not estimated — it counts how many '
    'of the firm’s 17 Assumptions documents carry that fact. Blank means '
    'it is not an Assumptions field; it feeds the Prospect Summary or the '
    'follow-up instead.',
    'Source kind \u2014 Client document: something the prospect sends. '
    '4Q-DERIVED (red): one of our own outputs, which cannot be an input '
    'without the pipeline feeding on itself. Every red row needs a client '
    'document found for it before that fact can be trusted.',

    'Second source is what the first gets checked against. A row with two '
    'sources can be reconciled automatically. A row with one cannot — it '
    'can only be reported.',
]


def main():
    wb = Workbook()
    ws = wb.active
    ws.title = 'Fact dictionary'

    ws.append([c[0] for c in COLS])
    for i, (_name, width) in enumerate(COLS, 1):
        cell = ws.cell(1, i)
        cell.font = hdr
        cell.fill = fill_hdr
        cell.alignment = wrap
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = 'A2'

    r = 2
    for row in ROWS:
        if len(row) == 2:                       # a section header
            ws.cell(r, 1, row[0]).font = sec
            for col in range(1, len(COLS) + 1):
                ws.cell(r, col).fill = fill_sec
            r += 1
            continue
        section, fact, typ, n, source, second, consumed, status = row
        kind = source_kind(source)
        values = [section, fact, typ, n, source, kind, check_source(second),
                  consumed, status, '']
        for col, value in enumerate(values, 1):
            cell = ws.cell(r, col, value)
            cell.font = body
            cell.alignment = wrap
            cell.border = box
            if col == 4 and isinstance(value, int):
                cell.alignment = Alignment(horizontal='center')
            if col == 6 and kind == '4Q-DERIVED':
                cell.font = Font(name='Arial', size=10, bold=True,
                                 color='C0392B')
                cell.fill = PatternFill('solid', fgColor='FBEAE6')
            if col == 10:
                cell.fill = fill_in
        r += 1

    r += 1
    ws.cell(r, 1, 'HOW TO USE').font = sec
    r += 1
    for text in LEGEND:
        ws.cell(r, 1, text).font = note
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
        ws.cell(r, 1).alignment = wrap
        ws.row_dimensions[r].height = 30
        r += 1

    add_provenance_sheet(wb)
    wb.save(OUT)
    print(OUT)


# Every figure that reaches a page has to say where it came from, precisely
# enough that a reviewer can open the source and land on the line without
# hunting. That is a property of the pipeline, not of any one output, so the
# record below is emitted by every module and travels with the number.
PROVENANCE = [
    ('field', 'Which fact in the dictionary', 'overhead_pct'),
    ('value', 'The figure as published', '77.0'),
    ('document', 'File name as the client sent it',
     '2025 Oyler Family Dentistry_Profit and Loss.xlsx'),
    ('path', 'Where it lives in the client folder, so a reviewer can go '
             'straight to it',
     'Documents/Business/Financials/'),
    ('label', 'What the thing is, in the reviewer’s own words',
     'Practice checking, Civista x4728'),
    ('location', 'Where in that document',
     'Sheet "Summary", rows "Total for Expenses" + "Total for Other Expenses"'),
    ('page', 'Page number, for paged documents', '3'),
    ('method', 'Read, computed, or detected',
     'computed: (2,436,541 + 1,232,474 - 390,000) / 4,255,973'),
    ('confidence', 'How the figure was settled',
     'two of three OCR passes agreed; parts reconcile to report total'),
    ('second_source', 'What it was checked against, if anything',
     '1120-S 2025 return: 74.0% (basis difference +3.0pt)'),
    ('as_of', 'Date the source document speaks to', '31/12/2025'),
    ('needs_human', 'Set when a person must settle it', 'FALSE'),
]

OUTPUTS = [
    ('Workbook (.xlsx)', 'Primary',
     'One row per figure with its full provenance record, plus a tab per '
     'analysis section. Reviewers sort, filter and check the arithmetic '
     'themselves. Live formulas, not pasted results.'),
    ('PDF', 'Primary',
     'The presentation copy. Each figure carries a short source tag; a '
     'provenance appendix at the back lists the full record keyed by tag.'),
    ('HTML', 'Optional',
     'Interactive version for anyone who wants it. Never the only format '
     '— the workbook and PDF stand on their own.'),
]


def add_provenance_sheet(wb):
    """The source-reference record every published figure must carry."""
    ws = wb.create_sheet('Source reference')
    cols = [('Field', 20), ('What it holds', 42), ('Example', 62)]
    ws.append([c[0] for c in cols])
    for i, (_n, width) in enumerate(cols, 1):
        ws.cell(1, i).font = hdr
        ws.cell(1, i).fill = fill_hdr
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = 'A2'

    r = 2
    ws.cell(r, 1, 'THE RECORD — emitted with every figure').font = sec
    for col in range(1, 4):
        ws.cell(r, col).fill = fill_sec
    r += 1
    for name, holds, example in PROVENANCE:
        for col, value in enumerate((name, holds, example), 1):
            cell = ws.cell(r, col, value)
            cell.font = body
            cell.alignment = wrap
            cell.border = box
        r += 1

    r += 1
    ws.cell(r, 1, 'DELIVERABLE FORMATS').font = sec
    for col in range(1, 4):
        ws.cell(r, col).fill = fill_sec
    r += 1
    for name, rank, detail in OUTPUTS:
        for col, value in enumerate((name, rank, detail), 1):
            cell = ws.cell(r, col, value)
            cell.font = body
            cell.alignment = wrap
            cell.border = box
        ws.row_dimensions[r].height = 42
        r += 1

    r += 1
    for text in [
        'A figure with no provenance record does not get published. If the '
        'pipeline cannot say where a number came from, it prints as a dash '
        'and joins the follow-up list instead.',
        'The point of "location" is that a reviewer can open the source and '
        'land on the line. A file name alone is not enough — name the '
        'sheet and row, the page, or the transaction date and amount.',
    ]:
        ws.cell(r, 1, text).font = note
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        ws.cell(r, 1).alignment = wrap
        ws.row_dimensions[r].height = 30
        r += 1


if __name__ == '__main__':
    main()
