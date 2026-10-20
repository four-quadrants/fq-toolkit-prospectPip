#!/usr/bin/env python3
"""Fill the firm's cash flow workbook from the statement readings.

WHY A TEMPLATE AND NOT A WORKBOOK BUILT FROM NOTHING
Because a Numbers document created from scratch by the library opens with
blank tabs. Every arrangement was tried -- sheets made up front, sheets
made as they are filled, tables renamed, tables left alone, two sheets
rather than four -- and all of them failed the same way on numbers-parser
4.22.0, the latest release. Starting from a real Numbers file and writing
into it works perfectly, including adding sheets, writing values and
attaching comments. So the firm's own template is the skeleton.

That turned out better than the alternative. The workbook keeps the
layout, column widths and formatting the team already reads, and the
output is a file Brogan recognises rather than something new to learn.

WHERE THE REASONING GOES
In cell comments, which is where Will already puts his. An adjustment is
written as a figure in the row it belongs to, with a comment on that cell
saying why. Nothing has to be read off a separate sheet, and the reason
travels with the number.

Comments need an author who already exists in the file: the library cannot
invent one. The template carries Austin Hooker, which is why it had to be
commented on once by hand before any of this could work.

ALL SHEETS BEHAVE THE SAME
The template's first two sheets carry 138 formulas each and the two added
sheets carry none. Rather than leave a workbook where half the entities
recalculate and half do not, every figure is written as a value. The
arithmetic is done here, where the weighting is right; the spreadsheet's
own weights row does not sum to one and understates every three-period
account by 1%.
"""
import os
import sys
import shutil

from numbers_parser import Document

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), '_spec', 'cashflow', 'template',
    'FQ Cash Flow TEMPLATE v3.numbers')

# The template's rows, zero-based. Named rather than scattered as numbers,
# because the layout is the firm's and we follow it rather than invent one.
R_ACCOUNT = 1
R_DATES = 2
R_BEGIN = 3
R_TRANSFER_IN = 4
R_ADDITIONS = 5
R_EXPENSES = 6
R_TRANSFER_OUT = 7
R_ENDING = 8
R_ADJ_FIRST = 10
R_ADJ_OUT = 16
R_ADJ_IN = 17
R_LESS_ADJ = 25
R_WEIGHTS = 27
R_AVG_WEIGHTED = 29
R_MONTHLY = 33
R_SURPLUS = 39          # "Adjusted Deficit/Surplus" blocks start here
SURPLUS_STRIDE = 7      # heading, account, four periods, average

FIRST_ACCOUNT_COL = 2   # column C
ACCOUNT_WIDTH = 4       # four periods per account
AUTHOR = 'Austin Hooker'

def money(v):
    """A figure as it should sit in the sheet.

    Rounded to cents, not to whole dollars. Whole-dollar rounding turned
    the 0.25 weights into zero, and it also threw away the cents the
    firm's own workbooks keep.
    """
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return v
    return round(float(v), 4)


def _columns_needed(n_accounts):
    """Label column, the account blocks, a gap, then the liabilities block."""
    return FIRST_ACCOUNT_COL + ACCOUNT_WIDTH * n_accounts + 1 + 7


FORMULA_ROWS = (R_EXPENSES, R_ADJ_OUT, R_ADJ_IN, R_LESS_ADJ, R_AVG_WEIGHTED)


class Filler(object):
    """One entity written onto one sheet of the template."""

    def __init__(self, table, entity):
        self.t = table
        self.e = entity
        self.notes = []

    def put(self, row, col, value, comment=None, workings=None):
        """Write a cell, unless the template computes it already.

        The library cannot write formulas: handed "=C4+C6-C9" it stores the
        string. But the template already carries the right formulas in the
        right cells, so the answer is not to write those cells at all. Fill
        the inputs and the sheet does its own arithmetic, which keeps it
        live for whoever opens it.

        Where a sheet has no formula in that cell, the figure is computed
        here and the working goes into the comment, so a reader can still
        see how it was reached.
        """
        if self.t.cell(row, col).is_formula:
            return
        self.t.write(row, col, money(value))
        if workings and not comment:
            comment = workings
        if comment:
            # Collected and applied after every value is in place: adding a
            # comment rewrites part of the document, and doing it between
            # writes has been unreliable.
            self.notes.append((row, col, comment))

    def run(self):
        n_accounts = len(self.e['accounts'])
        need = _columns_needed(n_accounts)
        if self.t.num_cols < need:
            self.t.add_column(need - self.t.num_cols)
        # The template is 61 rows, which holds three surplus blocks. A
        # client with five accounts needs five, so the sheet grows to fit
        # rather than writing past the end.
        rows_needed = R_SURPLUS + SURPLUS_STRIDE * n_accounts + 2
        if self.t.num_rows < rows_needed:
            self.t.add_row(rows_needed - self.t.num_rows)

        # The template ships with a previous client's dates and zeros in
        # the account blocks. Anything not overwritten stays, so a client
        # with two statement periods inherits two more from whoever the
        # template was made from. Clear the whole region first.
        last = FIRST_ACCOUNT_COL + ACCOUNT_WIDTH * len(self.e['accounts'])
        for row in list(range(R_ACCOUNT, R_AVG_WEIGHTED + 1)) + [R_MONTHLY]:
            for col in range(FIRST_ACCOUNT_COL, max(last, self.t.num_cols - 8)):
                cell = self.t.cell(row, col)
                # Never clear a formula. Blanking one replaces it with an
                # empty string, and the sheet loses the arithmetic that is
                # the reason for using the template at all: the first pass
                # took the personal sheet from 138 formulas down to 65.
                if cell.is_formula:
                    continue
                if cell.value not in (None, ''):
                    self.t.write(row, col, '')

        reasons = {}
        for row in self.e.get('adjustments', ()):
            reasons.setdefault(row[0], []).append(row)

        self._extend_formulas(n_accounts)
        for i, acct in enumerate(self.e['accounts']):
            self._account(i, acct, reasons)
        self._surplus()
        self._liabilities(need)

        for row, col, text in self.notes:
            # A cell that already has a comment cannot take another without
            # being treated as a reply, and the template's seed comments
            # sit at B2 on every sheet.
            if self.t.cell(row, col).comments:
                continue
            try:
                self.t.add_comment(row, col, text, author=AUTHOR)
            except Exception:
                pass          # a comment is never worth losing the file over
        return self.t

    def _copy_formula(self, from_row, from_col, to_row, to_col):
        """Give a cell the same formula as another one.

        The library has no way to write a formula: handed "=C4+C6-C9" it
        stores the string. But a formula already in the file can be pointed
        at from another cell, and the references are stored relative to
        wherever the cell sits -- "same column, three rows up" rather than
        "C4". So the copy retranslates itself. The Expenses formula taken
        from row 7 lands on row 60 as C57+C59-C62 without being asked to.

        This reaches past the public API into the cell's formula id, so it
        is wrapped: a missing formula is worth less than a broken file.
        """
        try:
            source = self.t.cell(from_row, from_col)
            if not source.is_formula:
                return False
            target = self.t.cell(to_row, to_col)
            if target.is_formula:
                return True
            # A row created by add_row has no cell storage until something
            # is written into it, and a formula id set on an empty cell is
            # dropped on save. Writing a zero first gives it somewhere to
            # live; the formula replaces the zero when Numbers opens it.
            self.t.write(to_row, to_col, 0)
            self.t.cell(to_row, to_col)._formula_id = source._formula_id
            return True
        except Exception:
            return False

    def _extend_formulas(self, n_accounts):
        """Carry the template's formulas into the blocks it does not have.

        The template covers three accounts and three surplus blocks. A
        client with five of each would otherwise get two blocks of dead
        values among three live ones, which is the inconsistency this was
        meant to remove.
        """
        for i in range(1, n_accounts):
            base = FIRST_ACCOUNT_COL + ACCOUNT_WIDTH * i
            for j in range(ACCOUNT_WIDTH):
                col = base + j
                if col >= self.t.num_cols:
                    break
                for row in FORMULA_ROWS:
                    self._copy_formula(row, FIRST_ACCOUNT_COL + j, row, col)
                # Every column of an account block but the first carries
                # the previous period's closing balance.
                if j:
                    self._copy_formula(R_BEGIN, FIRST_ACCOUNT_COL + 1,
                                       R_BEGIN, col)
                self._copy_formula(R_MONTHLY, FIRST_ACCOUNT_COL + 2,
                                   R_MONTHLY, base + 2)

        # The surplus blocks are deliberately NOT extended this way. Their
        # formulas read the account rows at the top of the sheet, and
        # because references are stored relative to the cell, copying one
        # 21 rows down moves what it points at: block four came out as
        # C27-C26 rather than reading its own account. The account blocks
        # copy cleanly because they move sideways, not downwards, and a
        # column shift is exactly what a relative reference handles.
        #
        # So blocks beyond the template's three are computed here instead,
        # with the working in the comment.

    def _account(self, i, acct, reasons):
        base = FIRST_ACCOUNT_COL + ACCOUNT_WIDTH * i
        self.put(R_ACCOUNT, base, acct['name'])
        periods = acct['periods']
        exp = [b + d - e for b, d, e in
               zip(acct['beginning'], acct['additions'], acct['ending'])]
        adj = [x - o + n for x, o, n in
               zip(exp, acct['adj_out'], acct['adj_in'])]

        mine = reasons.get(acct['name'], [])
        for j, period in enumerate(periods):
            col = base + j
            if col >= base + ACCOUNT_WIDTH:
                self.notes.append(
                    (R_ACCOUNT, base,
                     'This account has %d statement periods; the sheet holds '
                     'four. The later ones are not shown and are not in the '
                     'averages.' % len(periods)))
                break
            self.put(R_DATES, col, period)
            self.put(R_BEGIN, col, acct['beginning'][j])
            self.put(R_TRANSFER_IN, col, acct['transfers_in'][j],
                     _reason(mine, period, 'Transfer in'))
            self.put(R_ADDITIONS, col, acct['additions'][j])
            self.put(R_EXPENSES, col, exp[j], workings=
                     'Computed here because this sheet carries no formula '
                     'for it: beginning %s plus additions %s less ending '
                     '%s.' % tuple('{:,.2f}'.format(v) for v in
                                   (acct['beginning'][j],
                                    acct['additions'][j],
                                    acct['ending'][j])))
            self.put(R_TRANSFER_OUT, col, acct['transfers_out'][j],
                     _reason(mine, period, 'Transfer out'))
            self.put(R_ENDING, col, acct['ending'][j])
            self.put(R_ADJ_OUT, col, acct['adj_out'][j],
                     _reason(mine, period, 'Adjustment out'))
            self.put(R_ADJ_IN, col, acct['adj_in'][j],
                     _reason(mine, period, 'Adjustment in'))
            self.put(R_LESS_ADJ, col, adj[j], workings=
                     'Computed here: expenses less adjustments out, plus '
                     'adjustments in.')
            # The weights are an input, so they can be corrected in place
            # and the template's own formulas then produce the right
            # answer. They ship as 0.25 regardless of how many periods
            # there are; three periods at 0.33 total 0.99 and understate
            # the account by 1%. One over the number of periods is exact.
            self.put(R_WEIGHTS, col, round(1.0 / len(periods), 6),
                     comment=('%d statement periods, so each weighs 1/%d. '
                              'The template ships 0.25; at three periods '
                              'that totals 0.99 and loses 1%%.'
                              % (len(periods), len(periods)))
                     if j == 0 else None)
            self.put(R_AVG_WEIGHTED, col, adj[j] / float(len(periods)),
                     workings='Computed here: adjusted expenses divided by '
                              'the %d periods covered.' % len(periods))

        n = len(periods)
        self.put(R_MONTHLY, base, round(sum(adj) / n),
                 workings='Computed here: the mean of %d statement period%s.'
                          % (n, '' if n == 1 else 's'))

    def _surplus(self):
        row = R_SURPLUS
        for acct in self.e['accounts']:
            dep = [d - i for d, i in
                   zip(acct['additions'], acct['transfers_in'])]
            sexp = acct['surplus_expense']
            self.put(row, 1, 'Adjusted Deficit/Surplus')
            self.put(row + 1, 1, acct['name'])
            for lab, col in (('Deposit', 2), ('Expense', 3),
                             ('Deficit/Surplus', 4)):
                self.put(row + 1, col, lab)
            for j, period in enumerate(acct['periods'][:4]):
                self.put(row + 2 + j, 1, period)
                self.put(row + 2 + j, 2, dep[j])
                self.put(row + 2 + j, 3, sexp[j])
                self.put(row + 2 + j, 4, dep[j] - sexp[j])
            n = len(acct['periods'])
            d, e = sum(dep) / n, sum(sexp) / n
            self.put(row + 6, 2, round(d),
                     workings='Mean adjusted deposit across %d periods.' % n)
            self.put(row + 6, 3, round(e),
                     workings='Mean adjusted expense across %d periods.' % n)
            self.put(row + 6, 4, round(d - e),
                     comment='Goes to section 5 of the Assumptions.')
            row += SURPLUS_STRIDE

    def _liabilities(self, need):
        base = need - 7
        items = self.e.get('liabilities', ())
        self.put(R_DATES, base, 'Liabilities, insurance and savings:')
        for i, (label, amount, paid_from) in enumerate(items):
            self.put(R_BEGIN + i, base, label)
            self.put(R_BEGIN + i, base + 1, amount)
            self.put(R_BEGIN + i, base + 6, paid_from)
        total = sum(x[1] for x in items)
        self.put(R_BEGIN + len(items) + 1, base, 'Total')
        self.put(R_BEGIN + len(items) + 1, base + 1, round(total),
                 'Excluded from the expense figures. Mortgages and loans, '
                 'insurance premiums, and retirement or brokerage '
                 'contributions.')

        monthly = 0
        for acct in self.e['accounts']:
            exp = [b + d - e for b, d, e in
                   zip(acct['beginning'], acct['additions'], acct['ending'])]
            adj = [x - o + n for x, o, n in
                   zip(exp, acct['adj_out'], acct['adj_in'])]
            monthly += round(sum(adj) / len(acct['periods']))
        self.put(R_LESS_ADJ, base, 'Avg Monthly Expenses:')
        self.put(R_LESS_ADJ, base + 1, round(monthly),
                 'Including liabilities, insurance and savings, because '
                 'those payments left the accounts like any other debit.')
        self.put(R_LESS_ADJ + 2, base, 'Less the above:')
        self.put(R_LESS_ADJ + 2, base + 1, round(monthly - total))
        self.put(R_LESS_ADJ + 4, base, 'Annualised:')
        self.put(R_LESS_ADJ + 4, base + 1, round((monthly - total) * 12),
                 'Section 12 of the Assumptions prints the monthly and '
                 'annual figures excluding these payments.')


def _reason(rows, period, kind):
    """The analyst-facing reason for an adjustment of this kind and period."""
    for acct, per, this_kind, amount, why, confidence in rows:
        if this_kind == kind and per in (period, 'All'):
            return '%s. [%s]' % (why, confidence)
    return None


def write(entities, out, template=None):
    """Fill the template and save it as this client's workbook."""
    src = template or TEMPLATE
    if not os.path.exists(src):
        raise IOError('Cash flow template missing: %s' % src)
    shutil.copy(src, out)

    doc = Document(out)
    spare = len(doc.sheets) - len(entities)
    for i, entity in enumerate(entities[:len(doc.sheets)]):
        sheet = doc.sheets[i]
        sheet.name = entity['name']
        sheet.tables[0].name = entity['name']
        Filler(sheet.tables[0], entity).run()
    for i in range(len(entities), len(doc.sheets)):
        doc.sheets[i].name = 'Unused %d' % (i + 1)
    doc.save(out)
    return out, max(0, len(entities) - len(doc.sheets)), spare
