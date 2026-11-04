#!/usr/bin/env python3
"""Write the initial-notes workbook from what the documents say.

    python3 workbook.py "<client folder>" --out "Initial notes - Oyler.xlsx"

WHY A WORKBOOK AND NOT THE PAGE
Both, eventually. The page is where this is going; the workbook is what the
team reads today, and a figure nobody can check is worth nothing however it is
rendered. So the readers produce the facts once and this is one of two views of
them.

THE LAYOUT CHANGE
The notes sections of the existing template are paragraphs. Each one holds
eight or ten separate facts in a single cell, which cannot be scanned, sorted,
compared across clients, or pointed at by a Source Map entry. Here every fact
is its own row: a label, a value, and the document it came from. The prose that
genuinely is prose -- an analyst's judgement about a transition plan -- stays
prose, in its own row, marked as a note rather than a figure.

EVERY FIGURE CARRIES ITS SOURCE
Not as a comment somebody has to hover, but as two columns on the row itself,
and again on the Source Map tab. A row with no source is yellow and says what
is needed. That is the analyst’s convention from the Kinsler build, kept because it
works.
"""
import os
import sys
import argparse
import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import facts as _facts                                       # noqa: E402

NAVY = '16324F'
ORANGE = 'F08418'

HEAD = Font(name='Arial', bold=True, color='FFFFFF', size=10)
SECTION = Font(name='Arial', bold=True, color=NAVY, size=11)
LABEL = Font(name='Arial', size=10)
VALUE = Font(name='Arial', size=10, color='0000FF')       # keyed input
DERIVED = Font(name='Arial', size=10)                     # formula
NOTE = Font(name='Arial', size=9, color='6B7683')
SRC = Font(name='Arial', size=8, color='8A9099')

F_HEAD = PatternFill('solid', fgColor=NAVY)
F_SECTION = PatternFill('solid', fgColor='E8EEF4')
F_NEEDED = PatternFill('solid', fgColor='FFF4CC')
BOX = Border(bottom=Side(style='thin', color='E4E0D8'))
WRAP = Alignment(wrap_text=True, vertical='top')

MONEY = '$#,##0;($#,##0);-'
PCT = '0.0%'
NUM = '#,##0'


def _sheet_head(ws, title, subtitle, widths):
    ws['A1'] = title
    ws['A1'].font = Font(name='Arial', bold=True, size=14, color=NAVY)
    ws['A2'] = subtitle
    ws['A2'].font = NOTE
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    return 4


def _section(ws, row, text, span):
    ws.cell(row, 1, text.upper()).font = SECTION
    for c in range(1, span + 1):
        ws.cell(row, c).fill = F_SECTION
    return row + 1


def _fact_row(ws, row, fact, cols=5):
    """One fact: label, value, the analyst note, as-of, source.

    The note column is why this is readable where the old template was not.
    There, the context lived in a paragraph at the bottom of the sheet and had
    to be matched to its figure by eye.
    """
    ws.cell(row, 1, fact.label).font = LABEL
    ws.cell(row, 1).alignment = WRAP
    cell = ws.cell(row, 2, fact.value)
    cell.font = VALUE if fact.value is not None else LABEL
    # A composed value is a sentence and has to wrap. A figure is a figure and
    # reads better flush right. Deciding by type rather than by column keeps
    # "Cardosi (left after 2025), days 185 to 132..." readable in the same
    # column as $720,061.
    if isinstance(fact.value, str) and len(fact.value) > 24:
        cell.alignment = Alignment(wrap_text=True, vertical='top')
    else:
        cell.alignment = Alignment(horizontal='right', vertical='top')
    if fact.fmt:
        cell.number_format = fact.fmt
    note = fact.note or ''
    for extra in (fact.flags or ()):
        note += ('  ' if note else '') + ('FLAG: %s' % extra)
    for q in (fact.questions or ()):
        note += ('  ' if note else '') + ('ASK: %s' % q)
    ws.cell(row, 3, note).font = NOTE
    ws.cell(row, 3).alignment = WRAP
    ws.cell(row, 4, fact.as_of or '').font = SRC
    ws.cell(row, 5, fact.source or '').font = SRC
    ws.cell(row, 5).alignment = WRAP
    longest = max(len(str(fact.value or '')), len(note))
    if longest > 60:
        # Roughly two columns' worth of characters per line, and Excel will not
        # auto-height a wrapped cell that was written by a library.
        ws.row_dimensions[row].height = min(
            90, 14 * (1 + longest // 60))
    for c in range(1, cols + 1):
        ws.cell(row, c).border = BOX
        if fact.value is None:
            ws.cell(row, c).fill = F_NEEDED
    if fact.value is None and fact.needed:
        ws.cell(row, 3, fact.needed).font = NOTE
        ws.cell(row, 3).alignment = WRAP
    if fact.flags:
        ws.cell(row, 3).fill = PatternFill('solid', fgColor='FBEAE6')
    return row + 1


def _overhead_simple(block_facts, by_year):
    """The front sheet's overhead: one line per year and basis, nothing else.

    The parts (income base, expenses, doctor wages, D&A) are on the by year
    sheet. The facts that carry them stay in the bundle for the deck; they are
    only not printed here.
    """
    by_label = {f.label: f for f in block_facts}
    out = []
    said = by_label.get('Overhead, client says')
    if said is not None:
        out.append(said)
    years = sorted(by_year)
    headline = by_label.get('Overhead')
    last_pnl = [y for y in years if by_year[y].get('pnl_pct') is not None]
    for basis, pct_key, src_key in (('P&L', 'pnl_pct', 'pnl_source'),
                                    ('Tax return', 'tax_pct', 'tax_source')):
        for y in years:
            v = by_year[y].get(pct_key)
            if v is None:
                continue
            m = by_year[y].get('pnl_months') if basis == 'P&L' else None
            label = '%s overhead, %s%s' % (basis, y, ' (%d months)' % m
                                           if m and m < 12 else '')
            f = _facts.Fact(label, v / 100.0, PCT, by_year[y].get(src_key),
                            'see the by year sheet for the figures')
            if headline is not None and basis == 'P&L' and last_pnl \
                    and y == last_pnl[-1]:
                f.note, f.flags = headline.note, headline.flags
                f.questions = headline.questions
            out.append(f)
    return out


def _overhead_table(ws, row, by_year, ytd=None):
    """Overhead year over year with every figure that goes into it.

    P&L against P&L and return against return, the way the firm's old sheet
    laid it out. The dollar overhead and the % are live formulas on the
    figures above them, so an edited figure carries through.
    """
    years = sorted(by_year)

    def ycol(i):
        # The same columns as the year-by-year table above it: the first
        # year, then each later year followed by its change column.
        return 2 if i == 0 else 1 + 2 * i

    # The year to date gets an annualized column beside it, as on the
    # metric table above (the lead advisor fills it in by hand otherwise).
    ytd_i = None
    if ytd and ytd.get('year') in years and years.index(ytd['year']) == len(years) - 1:
        m = by_year[ytd['year']].get('pnl_months') or ytd.get('months')
        if m and m < 12:
            ytd_i, ytd_m = years.index(ytd['year']), m

    last = ycol(len(years) - 1) + (1 if len(years) > 1 else 0)
    ws.cell(row, 1, 'OVERHEAD').font = SECTION
    for c in range(1, last + 1):
        ws.cell(row, c).fill = F_SECTION
    row += 1
    for c in range(1, last + 1):
        ws.cell(row, c).fill = F_HEAD
    for i, y in enumerate(years):
        m = by_year[y].get('pnl_months')
        c = ws.cell(row, ycol(i), y if not m or m >= 12
                    else '%s (%d mo P&L)' % (y, m))
        c.font = HEAD
        if i == ytd_i:
            ws.cell(row, ycol(i) + 1, '%s annualized' % y).font = HEAD
            ws.cell(row, ycol(i) + 2, 'change').font = HEAD
        elif i:
            ws.cell(row, ycol(i) + 1, 'change').font = HEAD
    row += 1

    def line(label, key=None, formula=None, fmt=MONEY, bold=False):
        nonlocal row
        ws.cell(row, 1, label).font = Font(name='Arial', size=10, bold=bold)
        ws.cell(row, 1).border = BOX
        for i, y in enumerate(years):
            col = ycol(i)
            if formula:
                v = formula(get_column_letter(col))
            else:
                v = by_year[y].get(key)
            c = ws.cell(row, col, v)
            c.number_format = fmt
            c.font = Font(name='Arial', size=10, bold=bold,
                          color=None if formula else '0000FF')
            if v is None:
                c.fill = F_NEEDED
            here = get_column_letter(col)
            if i == ytd_i:
                a = ws.cell(row, col + 1)
                if formula:
                    a.value = formula(get_column_letter(col + 1))
                elif v is not None:
                    a.value = '=%s%d/%d*12' % (here, row, ytd_m)
                a.number_format = fmt
                a.font = Font(name='Arial', size=10, italic=True, bold=bold)
                here = get_column_letter(col + 1)
            if i and fmt == '0.0%':
                prev = get_column_letter(ycol(i - 1))
                d = ws.cell(row, col + (2 if i == ytd_i else 1),
                            '=IFERROR((%s%d-%s%d)*100,"")' % (here, row, prev, row))
                d.number_format, d.font = '+0.0 "pts";-0.0 "pts";0.0', DERIVED
        row += 1
        return row - 1

    ws.cell(row, 1, 'P&L basis').font = Font(name='Arial', bold=True, size=10)
    row += 1
    r_inc = line('income', 'pnl_income')
    r_oth = line('other income', 'pnl_other')
    r_base = line('income base', formula=lambda c: '=%s%d+%s%d' % (c, r_inc, c, r_oth))
    r_exp = line('total expenses', 'pnl_expenses')
    r_dr = line('less doctor wages', 'pnl_dr')
    r_da = line('less depreciation and amortisation', 'pnl_da')
    r_oh = line('overhead', formula=lambda c: '=%s%d-%s%d-%s%d'
                % (c, r_exp, c, r_dr, c, r_da))
    line('overhead %', formula=lambda c: '=IFERROR(%s%d/%s%d,"")'
         % (c, r_oh, c, r_base), fmt='0.0%', bold=True)
    row += 1
    ws.cell(row, 1, 'Tax basis').font = Font(name='Arial', bold=True, size=10)
    row += 1
    t_base = line('gross income on the return', 'tax_base')
    t_ded = line('total deductions', 'tax_deductions')
    t_off = line('less officer compensation', 'tax_officer')
    t_da = line('less depreciation and amortisation', 'tax_da')
    t_oh = line('overhead', formula=lambda c: '=IF(%s%d="","",%s%d-%s%d-%s%d)'
                % (c, t_ded, c, t_ded, c, t_off, c, t_da))
    line('overhead %', formula=lambda c: '=IFERROR(%s%d/%s%d,"")'
         % (c, t_oh, c, t_base), fmt='0.0%', bold=True)
    note = ws.cell(row, 1, 'Compare within a basis, not across: the P&L is '
                   'what the bookkeeper booked, the return is what the '
                   'preparer deducted.')
    note.font = NOTE
    return row + 1


def _cash_sheet(wb, bundle):
    """Light cash flow: each bank account, statement by statement.

    Not the cash flow analysis (that is Stage 2). Just what the lead advisor
    works out by hand at the initial notes: where the balance went each
    month, what moved between the client's own accounts, and the average.
    """
    accts = getattr(bundle, 'cash_light', None) or []
    if not accts:
        return
    ws = wb.create_sheet('cash flow (light)')
    r = _sheet_head(ws, 'Cash flow, light  —  %s' % bundle.client,
                    'Per bank account, per statement: balance in, money in, '
                    'money out, balance out, and transfers to the client\'s '
                    'own accounts. Every statement balances to the dollar.',
                    [16, 14, 14, 14, 14, 14, 16, 40])
    for a in accts:
        ws.cell(r, 1, a.get('account')).font = SECTION
        for c in range(1, 9):
            ws.cell(r, c).fill = F_SECTION
        r += 1
        for i, h in enumerate(('period', 'start', 'in', 'out', 'end',
                               'change', 'to own accts', 'note'), 1):
            ws.cell(r, i, h).font = HEAD
            ws.cell(r, i).fill = F_HEAD
        r += 1
        first = r
        for m in a['months']:
            ws.cell(r, 1, m.get('period')).font = LABEL
            for j, k in enumerate(('start', 'deposits', 'withdrawals', 'end'), 2):
                c = ws.cell(r, j, m.get(k))
                c.number_format, c.font = MONEY, VALUE
            c = ws.cell(r, 6, '=E%d-B%d' % (r, r))
            c.number_format, c.font = MONEY, DERIVED
            c = ws.cell(r, 7, m.get('transfers_out'))
            c.number_format, c.font = MONEY, VALUE
            ws.cell(r, 8, m.get('note') or '').font = NOTE
            r += 1
        ws.cell(r, 1, 'average a month').font = Font(name='Arial', size=10, bold=True)
        for col in (6, 7):
            L = get_column_letter(col)
            c = ws.cell(r, col, '=IFERROR(AVERAGE(%s%d:%s%d),"")' % (L, first, L, r - 1))
            c.number_format = MONEY
            c.font = Font(name='Arial', size=10, bold=True)
        if a.get('note'):
            ws.cell(r, 8, a['note']).font = NOTE
        r += 2


def _summary_sheet(wb, bundle):
    """The lead advisor's summary page, pre-filled for him to edit.

    Areas to improve come from _Audit/summary.json (Claude drafts them from
    the flags); the savings projection is live formulas on the inputs at the
    top, so he can change the savings or the rate and watch it move.
    """
    import json
    try:
        S = json.load(open(os.path.join(bundle.folder, '_Audit', 'summary.json')))
    except (OSError, ValueError, TypeError):
        return
    ws = wb.create_sheet('Summary')
    r = _sheet_head(ws, 'Summary  —  %s' % bundle.client,
                    'A draft for the lead advisor: edit the areas, the '
                    'averages and the savings inputs freely.',
                    [46, 16, 16, 16, 16])
    ws.cell(r, 1, 'AREAS TO IMPROVE').font = SECTION
    for c in range(1, 6):
        ws.cell(r, c).fill = F_SECTION
    r += 1
    for a in S.get('areas') or ():
        ws.cell(r, 1, a).font = LABEL
        ws.cell(r, 1).alignment = WRAP
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        r += 1
    r += 1
    ws.cell(r, 1, 'AVERAGES').font = SECTION
    for c in range(1, 6):
        ws.cell(r, c).fill = F_SECTION
    r += 1
    for i, h in enumerate(('', 'stated', 'average', 'use'), 1):
        ws.cell(r, i, h).font = HEAD
        ws.cell(r, i).fill = F_HEAD
    r += 1
    for row in S.get('averages') or ():
        label, stated, avg, use, fmt = (list(row) + [None] * 5)[:5]
        ws.cell(r, 1, label).font = LABEL
        for j, v in enumerate((stated, avg, use), 2):
            c = ws.cell(r, j, v)
            c.number_format = PCT if fmt == 'pct' else MONEY
            c.font = VALUE if v is not None else LABEL
        r += 1
    P = S.get('projection') or {}
    paths = P.get('paths') or []
    if not paths:
        return
    r += 1
    ws.cell(r, 1, 'SAVINGS PROJECTION').font = SECTION
    for c in range(1, 6):
        ws.cell(r, c).fill = F_SECTION
    r += 1
    ws.cell(r, 1, 'saved a year').font = LABEL
    ws.cell(r + 1, 1, 'return').font = LABEL
    for j, p in enumerate(paths, 2):
        ws.cell(r - 1, j, p.get('label')).font = HEAD
        c = ws.cell(r, j, p.get('save'))
        c.number_format, c.font = MONEY, VALUE
        c = ws.cell(r + 1, j, p.get('rate'))
        c.number_format, c.font = '0.0%', VALUE
    sv, rt = r, r + 1
    r += 2
    ws.cell(r, 1, 'age').font = HEAD
    ws.cell(r, 1).fill = F_HEAD
    r += 1
    age, end = P.get('age'), P.get('retire_age')
    start_row = r
    for a in range(age, (end or age) + 1):
        ws.cell(r, 1, a).font = LABEL
        for j in range(2, 2 + len(paths)):
            L = get_column_letter(j)
            c = ws.cell(r, j, P.get('start') if r == start_row else
                        '=%s%d*(1+%s$%d)+%s$%d' % (L, r - 1, L, rt, L, sv))
            c.number_format = MONEY
            c.font = VALUE if r == start_row else DERIVED
        r += 1


def write(bundle, out):
    wb = Workbook()

    # ---------------------------------------------------------- initial notes
    ws = wb.active
    ws.title = 'initial notes'
    row = _sheet_head(
        ws, 'Initial notes  —  %s' % bundle.client,
        'Blue is a figure read from a document. Yellow means nobody has '
        'supplied it yet. Every row names where it came from.',
        [30, 46, 60, 13, 30])

    for block in bundle.blocks:
        row = _section(ws, row, block.title, 5)
        head = ('', 'value', 'note', 'as of', 'source')
        for i, h in enumerate(head, 1):
            ws.cell(row, i, h).font = HEAD
            ws.cell(row, i).fill = F_HEAD
        row += 1
        facts_shown = block.facts
        if block.title == 'Overhead' and getattr(bundle, 'overhead_by_year', None):
            facts_shown = _overhead_simple(block.facts, bundle.overhead_by_year)
        for fact in facts_shown:
            row = _fact_row(ws, row, fact)
        row += 1

    # ------------------------------------------------------------ by year
    if bundle.years:
        ws2 = wb.create_sheet('by year')
        ytd = getattr(bundle, 'ytd', None)
        ytd_year = ytd['year'] if ytd else None
        extra = 1 if ytd else 0
        r = _sheet_head(ws2, 'Practice, year by year  —  %s' % bundle.client,
                        'One column per year. Change columns compute '
                        'themselves.' + (
                            ' %s is year to date (%d months); the annualized '
                            'column is YTD / %d x 12, and its change compares '
                            'the annualized figure with the year before. '
                            'Ratios are carried as they are.'
                            % (ytd_year, ytd['months'], ytd['months'])
                            if ytd else ''),
                        [34] + [15] * (len(bundle.years) * 2 + extra))
        notes_col = 2 + len(bundle.years) * 2 + extra
        ws2.column_dimensions[get_column_letter(notes_col)].width = 70
        ws2.cell(r, notes_col, 'note').font = HEAD
        ws2.cell(r, notes_col).fill = F_HEAD
        ws2.cell(r, 1, 'metric').font = HEAD
        ws2.cell(r, 1).fill = F_HEAD
        col = 2
        for i, y in enumerate(bundle.years):
            head = y
            if y == ytd_year:
                head = '%s YTD (%d mo)' % (y, ytd['months'])
            ws2.cell(r, col, head).font = HEAD
            ws2.cell(r, col).fill = F_HEAD
            col += 1
            if y == ytd_year:
                ws2.cell(r, col, '%s annualized' % y).font = HEAD
                ws2.cell(r, col).fill = F_HEAD
                col += 1
            if i:
                ws2.cell(r, col, 'change').font = HEAD
                ws2.cell(r, col).fill = F_HEAD
                col += 1
        r += 1
        # These are in the overhead table below, with their parts, so they
        # are not repeated in the metric list. (The bundle keeps them; the
        # assumptions read them by name.)
        in_oh_table = {'revenue (P&L)', 'doctor income (P&L)',
                       'depreciation / amortisation', 'expenses (P&L)',
                       'overhead, P&L basis', 'overhead, tax basis',
                       'gross receipts (tax return)',
                       'officer compensation (tax return)'} \
            if getattr(bundle, 'overhead_by_year', None) else set()
        for name, by_year, fmt in bundle.series:
            if name in in_oh_table:
                continue
            ws2.cell(r, 1, name).font = LABEL
            col = 2
            prev_letter = None
            # A total annualizes; a ratio (a %, or anything per patient or
            # per day) is the same rate whatever the period.
            is_rate = fmt == PCT or '/' in name or '%' in name
            for i, y in enumerate(bundle.years):
                v = by_year.get(y)
                c = ws2.cell(r, col, v)
                c.font = VALUE if v is not None else LABEL
                c.number_format = fmt
                if v is None:
                    c.fill = F_NEEDED
                letter = get_column_letter(col)
                col += 1
                if y == ytd_year:
                    ac = ws2.cell(r, col)
                    if v is None:
                        ac.value = None
                    elif is_rate:
                        ac.value = '=%s%d' % (letter, r)
                    else:
                        ac.value = '=%s%d/%d*12' % (letter, r, (getattr(bundle, 'series_months', {}) or {}).get(name) or ytd['months'])
                    ac.number_format = fmt
                    ac.font = Font(name='Arial', size=10, italic=True)
                    letter = get_column_letter(col)
                    col += 1
                if i:
                    # A live formula, so an edited figure updates its own
                    # change column rather than disagreeing with it.
                    cc = ws2.cell(r, col)
                    cc.value = ('=IFERROR(%s%d/%s%d-1,"")'
                                % (letter, r, prev_letter, r))
                    cc.number_format = '+0.0%;-0.0%;-'
                    cc.font = DERIVED
                    col += 1
                prev_letter = letter
            got = bundle.series_notes.get(name)
            if got:
                text = got.get('note') or ''
                for extra in (got.get('flags') or ())[:1]:
                    text += ('  ' if text else '') + 'FLAG: %s' % extra
                cell = ws2.cell(r, notes_col, text)
                cell.font = NOTE
                cell.alignment = WRAP
                if got.get('flags'):
                    cell.fill = PatternFill('solid', fgColor='FBEAE6')
            ws2.cell(r, 1).border = BOX
            r += 1

        if getattr(bundle, 'overhead_by_year', None):
            _overhead_table(ws2, r + 1, bundle.overhead_by_year, ytd)

    # ---------------------------------------------------------- source map
    _cash_sheet(wb, bundle)
    _summary_sheet(wb, bundle)

    ws3 = wb.create_sheet('Source Map')
    r = _sheet_head(ws3, 'Source Map  —  %s' % bundle.client,
                    'Generated, not typed. Every figure above appears here '
                    'with the document and the place in it.',
                    [34, 44, 40, 40])
    for i, h in enumerate(('field', 'source document', 'where in it', 'note'), 1):
        ws3.cell(r, i, h).font = HEAD
        ws3.cell(r, i).fill = F_HEAD
    r += 1
    for fact in bundle.all_facts():
        if not fact.source:
            continue
        ws3.cell(r, 1, fact.label).font = LABEL
        ws3.cell(r, 2, fact.source).font = LABEL
        ws3.cell(r, 3, fact.where or '').font = LABEL
        ws3.cell(r, 4, fact.note or '').font = NOTE
        for c in range(1, 5):
            ws3.cell(r, c).alignment = WRAP
            ws3.cell(r, c).border = BOX
        r += 1

    # ----------------------------------------------------------- open items
    ws4 = wb.create_sheet('Open Items')
    r = _sheet_head(ws4, 'Open Items  —  %s' % bundle.client,
                    'What is still needed. Rank these yourself; the tool can '
                    'only say what is absent, not what it costs.',
                    [10, 44, 44, 26])
    for i, h in enumerate(('rank', 'item', 'why it matters', 'where it bites'), 1):
        ws4.cell(r, i, h).font = HEAD
        ws4.cell(r, i).fill = F_HEAD
    r += 1
    for fact in bundle.all_facts():
        if fact.value is not None:
            continue
        ws4.cell(r, 1, '').fill = F_NEEDED
        ws4.cell(r, 2, fact.needed or ('%s has not been supplied' % fact.label))
        ws4.cell(r, 3, fact.why or '')
        ws4.cell(r, 4, fact.label)
        for c in range(1, 5):
            ws4.cell(r, c).font = LABEL
            ws4.cell(r, c).alignment = WRAP
            ws4.cell(r, c).border = BOX
        r += 1

    for sheet in wb:
        sheet.freeze_panes = 'A5'
    wb.save(out)
    return out


def main():
    ap = argparse.ArgumentParser(description='Write the initial-notes workbook')
    ap.add_argument('folder')
    ap.add_argument('--client', default=None)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    bundle = _facts.gather(a.folder, client=a.client)
    out = a.out or os.path.join(a.folder, '_Audit',
                                'Initial notes - %s.xlsx' % bundle.client)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write(bundle, out)
    known = sum(1 for f in bundle.all_facts() if f.value is not None)
    total = len(list(bundle.all_facts()))
    print('%s\n%d of %d facts filled, %d still open'
          % (out, known, total, total - known))


if __name__ == '__main__':
    main()
