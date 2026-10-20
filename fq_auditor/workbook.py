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
is needed. That is Bryan's convention from the Kinsler build, kept because it
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
        for fact in block.facts:
            row = _fact_row(ws, row, fact)
        row += 1

    # ------------------------------------------------------------ by year
    if bundle.years:
        ws2 = wb.create_sheet('by year')
        r = _sheet_head(ws2, 'Practice, year by year  —  %s' % bundle.client,
                        'One column per year. Change columns compute '
                        'themselves.',
                        [34] + [15] * (len(bundle.years) * 2))
        notes_col = 2 + len(bundle.years) * 2
        ws2.column_dimensions[get_column_letter(notes_col)].width = 70
        ws2.cell(r, notes_col, 'note').font = HEAD
        ws2.cell(r, notes_col).fill = F_HEAD
        ws2.cell(r, 1, 'metric').font = HEAD
        ws2.cell(r, 1).fill = F_HEAD
        col = 2
        for i, y in enumerate(bundle.years):
            ws2.cell(r, col, y).font = HEAD
            ws2.cell(r, col).fill = F_HEAD
            col += 1
            if i:
                ws2.cell(r, col, 'change').font = HEAD
                ws2.cell(r, col).fill = F_HEAD
                col += 1
        r += 1
        for name, by_year, fmt in bundle.series:
            ws2.cell(r, 1, name).font = LABEL
            col = 2
            prev_letter = None
            for i, y in enumerate(bundle.years):
                v = by_year.get(y)
                c = ws2.cell(r, col, v)
                c.font = VALUE if v is not None else LABEL
                c.number_format = fmt
                if v is None:
                    c.fill = F_NEEDED
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

    # ---------------------------------------------------------- source map
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
