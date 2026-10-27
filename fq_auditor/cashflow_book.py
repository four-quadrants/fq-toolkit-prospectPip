#!/usr/bin/env python3
"""The cash flow workbook, laid out by the toolkit (27 October).

WHY NOT THE FIRM TEMPLATE ANY MORE
Filling the template produced an unreadable file. Its Monthly average row
averages itself, its Difference row points at an empty row, it has room for
three accounts so a fourth and fifth came out unformatted, and the toolkit's
adjustments were being written onto formula cells and silently dropped.
Austin's call: a clean layout the toolkit owns.

THE LAYOUT
  Summary     one line per side (Personal, Practice, each LLC): average
              monthly spending after adjustments, the fixed payments taken
              out of it, what is left, annualised, and how many movements
              are waiting for a decision.
  <side>      one block per account, stacked, every block the same:
              periods across, an Average column, money formatted, the
              toolkit's adjustments on their own rows with a comment saying
              why. Then the fixed payments, then the side's totals.
  To review   every flagged movement, with why it was flagged and a Done
              column to tick as you work down it.

WHAT THE ANALYST EDITS
The "Adjust out" and "Adjust in" rows, and the transfers rows, in any
period. Save in Numbers. The next build reads the change back (see
cashflow_review.py) and keeps it. Totals are worked out here, so press
Rebuild after a change to see them move.

THE SKELETON
A Numbers file made from nothing by numbers-parser opens with blank tabs,
so the firm template is still copied and then cleared. Its first two rows
carry merges that survive clearing, so row 2 (index 1) is left empty.
"""
import shutil

from numbers_parser import Document, RGB

import cashflow_workbook as _old

AUTHOR = _old.AUTHOR
TEMPLATE = _old.TEMPLATE

NAVY = RGB(22, 50, 79)
PALE = RGB(234, 243, 249)
AMBER = RGB(255, 244, 204)
WHITE = RGB(255, 255, 255)

# Row labels in an account block. cashflow_review.py reads the sheet back by
# these exact words, so change them in both places or not at all.
L_BEGIN = 'Beginning balance'
L_ADD = 'Deposits'
L_TIN = 'Transfers in'
L_END = 'Ending balance'
L_EXP = 'Money out (beginning + deposits - ending)'
L_TOUT = 'Transfers out'
L_AOUT = 'Adjust out (toolkit; edit to change)'
L_AIN = 'Adjust in (toolkit; edit to change)'
L_NET = 'Spending after adjustments'
BLOCK_ROWS = (L_BEGIN, L_ADD, L_TIN, L_END, L_EXP, L_TOUT, L_AOUT, L_AIN, L_NET)
AVERAGED = (L_ADD, L_EXP, L_TOUT, L_AOUT, L_AIN, L_NET)


class Book(object):
    def __init__(self, out):
        shutil.copy(TEMPLATE, out)
        self.out = out
        self.doc = Document(out)
        d = self.doc
        self.s_title = d.add_style(name='FQ title', bold=True, font_size=16.0,
                                   font_color=NAVY)
        self.s_head = d.add_style(name='FQ head', bold=True, font_color=WHITE,
                                  bg_color=NAVY)
        self.s_acct = d.add_style(name='FQ account', bold=True, bg_color=PALE,
                                  font_color=NAVY)
        self.s_bold = d.add_style(name='FQ bold', bold=True)
        self.s_edit = d.add_style(name='FQ edit', bg_color=AMBER)
        self.s_note = d.add_style(name='FQ note', italic=True,
                                  font_color=RGB(107, 118, 131))
        self.s_wrap = d.add_style(name='FQ wrap', text_wrap=True)
        self.used = 0

    def table(self, name, rows, cols):
        """The next sheet, cleared and sized: a template sheet while any are
        left, then new ones."""
        sheets = self.doc.sheets
        if self.used < len(sheets):
            sheet = sheets[self.used]
            t = sheet.tables[0]
            if t.num_rows > 1:
                t.delete_row(num_rows=t.num_rows - 1, start_row=1)
            if t.num_cols > 1:
                t.delete_column(num_cols=t.num_cols - 1, start_col=1)
            t.write(0, 0, '')
            t.add_row(num_rows=rows - 1)
            t.add_column(num_cols=cols - 1)
        else:
            self.doc.add_sheet(name, num_rows=rows, num_cols=cols)
            sheet = self.doc.sheets[-1]
            t = sheet.tables[0]
        sheet.name = name
        t.name = name
        self.used += 1
        t.col_width(0, 260)
        for c in range(1, cols):
            t.col_width(c, 105)
        # The template's rows are 14pt, which clips every figure. 22 fits a
        # line of 13pt text with room; the title row gets more.
        for r in range(t.num_rows):
            t.row_height(r, 22)
        t.row_height(0, 30)
        return t

    def money(self, t, r, c, v, style=None):
        t.write(r, c, round(float(v or 0), 2), style=style)
        t.set_cell_formatting(r, c, 'currency', currency_code='USD',
                              decimal_places=0, show_thousands_separator=True)

    def count(self, t, r, c, v):
        t.write(r, c, int(v))
        t.set_cell_formatting(r, c, 'number', decimal_places=0)

    def note(self, t, r, c, text):
        if text:
            try:
                t.add_comment(r, c, text, author=AUTHOR)
            except Exception:
                pass

    def finish(self):
        for i in range(self.used, len(self.doc.sheets)):
            self.doc.sheets[i].name = 'Spare %d' % (i + 1)
        self.doc.save(self.out)


def _avg(xs):
    return sum(xs) / float(len(xs)) if xs else 0.0


def _net(a):
    exp = [b + d - e for b, d, e in zip(a['beginning'], a['additions'], a['ending'])]
    return exp, [x - o + n for x, o, n in zip(exp, a['adj_out'], a['adj_in'])]


def _reasons(entity):
    out = {}
    for acct, per, kind, amount, why, conf in entity.get('adjustments') or ():
        out.setdefault((acct, per, kind), []).append(
            '%s [%s]' % (' '.join(str(why).split()), conf))
    return out


def _months(a):
    return a.get('months') or len(a['periods']) or 1


def side_totals(entity):
    """(spending, one-offs, fixed, left), monthly. The same arithmetic as
    cashflow.for_assumptions, so the workbook and the Assumptions agree:
    each account over the months its statements cover, one-off outflows
    out of the run rate, fixed payments out last. Oyler Personal:
    $32,958 including fixed payments, $13,892 excluding."""
    monthly = sum(sum(_net(a)[1]) / _months(a) for a in entity['accounts'])
    once = sum(sum(a.get('one_offs') or ()) / _months(a)
               for a in entity['accounts'])
    fixed = sum(x[1] for x in entity.get('liabilities') or ())
    return monthly, once, fixed, monthly - once - fixed


def write_side(book, entity):
    accts = entity['accounts']
    width = max([len(a['periods']) for a in accts] + [1])
    rows = 4 + sum(len(BLOCK_ROWS) + 3 for a in accts) \
        + len(entity.get('liabilities') or ()) + 14
    t = book.table(entity['name'], rows, width + 3)
    why = _reasons(entity)

    t.write(0, 0, '%s cash flow' % entity['name'], style=book.s_title)
    t.write(2, 0, 'Amber rows can be edited: change a figure, save, and '
                  'rebuild. The toolkit keeps your change.', style=book.s_note)
    r = 4
    for a in accts:
        n = len(a['periods'])
        t.write(r, 0, a['name'], style=book.s_acct)
        for j, p in enumerate(a['periods']):
            t.write(r, 1 + j, p, style=book.s_acct)
        t.write(r, 1 + width, 'Monthly avg', style=book.s_acct)
        book.note(t, r, 1 + width, 'Totals over the %.2f months these '
                  'statements cover.' % _months(a))
        exp, net = _net(a)
        series = {L_BEGIN: a['beginning'], L_ADD: a['additions'],
                  L_TIN: a['transfers_in'], L_END: a['ending'], L_EXP: exp,
                  L_TOUT: a['transfers_out'], L_AOUT: a['adj_out'],
                  L_AIN: a['adj_in'], L_NET: net}
        kinds = {L_TIN: 'Transfer in', L_TOUT: 'Transfer out',
                 L_AOUT: 'Adjustment out', L_AIN: 'Adjustment in'}
        for k, label in enumerate(BLOCK_ROWS, 1):
            rr = r + k
            editable = label in (L_TIN, L_TOUT, L_AOUT, L_AIN)
            t.write(rr, 0, label, style=book.s_bold if label == L_NET else None)
            for j in range(n):
                style = book.s_edit if editable else (
                    book.s_bold if label == L_NET else None)
                book.money(t, rr, 1 + j, series[label][j], style)
                if label in kinds:
                    notes = why.get((a['name'], a['periods'][j], kinds[label]))
                    if notes:
                        book.note(t, rr, 1 + j, '\n'.join(notes))
            if label in AVERAGED:
                book.money(t, rr, 1 + width, sum(series[label]) / _months(a),
                           book.s_bold if label == L_NET else None)
        if a.get('one_offs'):
            book.note(t, r, 0, 'One-off movements seen: %s' % ', '.join(
                '${:,.0f}'.format(x) for x in a['one_offs']))
        r += len(BLOCK_ROWS) + 3

    items = entity.get('liabilities') or ()
    t.write(r, 0, 'Fixed payments taken out (loans, insurance, savings)',
            style=book.s_head)
    t.write(r, 1, 'Monthly', style=book.s_head)
    t.write(r, 2, 'Paid from', style=book.s_head)
    r += 1
    for label, amount, paid_from in items:
        t.write(r, 0, label)
        book.money(t, r, 1, amount)
        t.write(r, 2, paid_from or '')
        r += 1
    if not items:
        t.write(r, 0, 'None found on these statements', style=book.s_note)
        r += 1

    monthly, once, fixed, left = side_totals(entity)
    r += 1
    t.write(r, 0, 'Totals for %s' % entity['name'], style=book.s_head)
    t.write(r, 1, 'Monthly', style=book.s_head)
    t.write(r, 2, 'Annual', style=book.s_head)
    lines = [('Spending after adjustments, all accounts', monthly, False),
             ('Less one-off outflows (on To review)', once, False),
             ('Spending including fixed payments', monthly - once, True),
             ('Less fixed payments above', fixed, False),
             ('Spending excluding fixed payments', left, True)]
    for label, v, bold in lines:
        r += 1
        st = book.s_bold if bold else None
        t.write(r, 0, label, style=st)
        book.money(t, r, 1, v, st)
        book.money(t, r, 2, v * 12, st)
    book.note(t, r, 1, 'Section 12 of the Assumptions prints this figure '
                       'and the one two rows up.')
    if t.num_rows > r + 1:
        t.delete_row(num_rows=t.num_rows - r - 1, start_row=r + 1)


def write_summary(book, entities):
    t = book.table('Summary', len(entities) + 8, 8)
    t.write(0, 0, 'Cash flow summary', style=book.s_title)
    heads = ('Side', 'Accounts', 'Spending / mo', 'Fixed payments / mo',
             'Excl. fixed / mo', 'Excl. fixed / yr', 'Incl. fixed / yr',
             'To review')
    for c, h in enumerate(heads):
        t.write(3, c, h, style=book.s_head)
    for i, e in enumerate(entities):
        r = 4 + i
        monthly, once, fixed, left = side_totals(e)
        t.write(r, 0, e['name'], style=book.s_bold)
        book.count(t, r, 1, len(e['accounts']))
        book.money(t, r, 2, monthly - once)
        book.money(t, r, 3, fixed)
        book.money(t, r, 4, left, book.s_bold)
        book.money(t, r, 5, left * 12)
        book.money(t, r, 6, (monthly - once) * 12)
        book.count(t, r, 7, len(e.get('adjustments') or ()))
    t.write(5 + len(entities), 0,
            'Spending = money out of each account less transfers between '
            'the client\'s own accounts and one-offs, averaged over the '
            'statement months. Detail on each side\'s tab.', style=book.s_note)


def write_review(book, entities):
    rows = [(e['name'],) + tuple(x) for e in entities
            for x in (e.get('adjustments') or ())]
    t = book.table('To review', len(rows) + 5, 8)
    t.write(0, 0, 'To review: %d movement%s' % (len(rows),
                                               '' if len(rows) == 1 else 's'),
            style=book.s_title)
    t.write(1, 0, '')
    heads = ('Side', 'Account', 'Period', 'Kind', 'Amount', 'Why it is flagged',
             'Confidence', 'Done')
    for c, h in enumerate(heads):
        t.write(3, c, h, style=book.s_head)
    t.col_width(5, 460)
    for i, (side, acct, per, kind, amount, why, conf) in enumerate(rows):
        r = 4 + i
        t.write(r, 0, side)
        t.write(r, 1, acct)
        t.write(r, 2, per)
        t.write(r, 3, kind)
        book.money(t, r, 4, amount)
        text = ' '.join(str(why).split())
        t.write(r, 5, text, style=book.s_wrap)
        # About 75 characters a line at this width.
        t.row_height(r, max(22, 18 * (1 + len(text) // 75)))
        t.write(r, 6, conf)
        t.write(r, 7, False)


def write(entities, out, template=None):
    """Same signature as cashflow_workbook.write: (path, overflow, spare)."""
    book = Book(out)
    write_summary(book, entities)
    for e in entities:
        write_side(book, e)
    write_review(book, entities)
    spare = len(book.doc.sheets) - book.used
    book.finish()
    return out, 0, max(0, spare)


def read_back(path):
    """{sheet: {account: {period: {field: value}}}} from a saved workbook.

    The analyst's figures, read by row label. Fields match
    cashflow_review.FIELDS: transfers_in, transfers_out, adj_lines (the
    Adjust out row) and adj_in_lines (the Adjust in row).
    """
    names = {L_TIN: 'transfers_in', L_TOUT: 'transfers_out',
             L_AOUT: 'adj_lines', L_AIN: 'adj_in_lines'}
    doc = Document(path)
    out = {}
    for sheet in doc.sheets:
        if sheet.name in ('Summary', 'To review') or sheet.name.startswith('Spare'):
            continue
        t = sheet.tables[0]
        accounts, r = {}, 0
        while r < t.num_rows - 1:
            nxt = t.cell(r + 1, 0).value
            if nxt == L_BEGIN:
                name = str(t.cell(r, 0).value)
                periods = []
                for c in range(1, t.num_cols):
                    v = t.cell(r, c).value
                    if not v or v == 'Average':
                        break
                    periods.append((c, str(v)))
                rec = {p: {} for _c, p in periods}
                for k in range(1, len(BLOCK_ROWS) + 1):
                    label = t.cell(r + k, 0).value
                    if label not in names:
                        continue
                    for c, p in periods:
                        v = t.cell(r + k, c).value
                        try:
                            rec[p][names[label]] = round(float(v), 2)
                        except (TypeError, ValueError):
                            rec[p][names[label]] = None
                accounts[name] = rec
                r += len(BLOCK_ROWS)
            r += 1
        out[sheet.name] = accounts
    return out
