#!/usr/bin/env python3
"""Render the Assumptions to PDF, on the firm's house page furniture.

    python3 assumptions_pdf.py "<client folder>" --client "Dr. Brian Oyler" \
            --out "Assumptions - Oyler.pdf"

WHY A RENDERER AND NOT A SCRIPT THAT WRITES A PDF
Because the sections are already built, by assumptions.build(), and a second
place that knows what section 6 says is a second place for section 6 to be
wrong. This file knows about type and margins and nothing else: hand it a
list of Sections and it draws them.

THE PAGE FURNITURE
Taken from the pipeline map rather than invented: a navy band across the top
carrying an orange eyebrow and the title, the document's identity set right,
and a hairline footer with the firm left, a standing line centred and the
classification right. Matching it matters more than it sounds. These go out
alongside the consult deck and the Business Notes, and a document that looks
like it came from somewhere else reads as less trustworthy than one that does
not, whatever is printed on it.

THREE STATES, AND ALL THREE ARE PRINTED
A section is written, written with a caveat, or waiting on something. The
third is the one that usually gets lost: a plan that silently omits what it
could not support looks finished. So a waiting section prints an orange block
saying what is needed, why, and where to go and get it, in the body of the
plan where the reader cannot miss it.
"""
import os
import re
import sys
import argparse
import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle, KeepTogether)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import facts as _facts                                       # noqa: E402
import assumptions as _asm                                   # noqa: E402

NAVY = colors.HexColor('#16324F')
INK = colors.HexColor('#1B2A41')
MUTE = colors.HexColor('#6C7480')
FAINT = colors.HexColor('#A8A49B')
RULE = colors.HexColor('#D8D4CA')
ORANGE = colors.HexColor('#F08418')
AMBER_BG = colors.HexColor('#FFF3E0')
# The band for alternating table rows. Warm grey off the firm's paper
# colour rather than a blue or a neutral, so the tables sit on the page
# instead of looking pasted onto it.
BAND_BG = colors.HexColor('#F6F4EF')
AMBER_TX = colors.HexColor('#8A5218')
WHITE = colors.white

BAND = 0.86 * inch
LEFT = 0.95 * inch
RIGHT = 0.95 * inch
GUTTER = 0.44 * inch

body = ParagraphStyle('body', fontName='Helvetica', fontSize=9, leading=13,
                      textColor=INK, alignment=TA_LEFT)
label = ParagraphStyle('label', fontName='Helvetica-Bold', fontSize=8,
                       leading=11, textColor=NAVY, spaceAfter=4)
number = ParagraphStyle('number', fontName='Helvetica-Bold', fontSize=13,
                        leading=16, textColor=ORANGE)
source = ParagraphStyle('source', fontName='Helvetica', fontSize=8,
                        leading=11.5, textColor=MUTE)
srcLbl = ParagraphStyle('srcLbl', fontName='Helvetica-Bold', fontSize=7,
                        leading=11.5, textColor=FAINT)
needH = ParagraphStyle('needH', fontName='Helvetica-Bold', fontSize=7.5,
                       leading=11, textColor=AMBER_TX)
needB = ParagraphStyle('needB', fontName='Helvetica', fontSize=8.5,
                       leading=12, textColor=AMBER_TX)
intro = ParagraphStyle('intro', fontName='Helvetica', fontSize=8.5, leading=12,
                       textColor=MUTE)
rowL = ParagraphStyle('rowL', fontName='Helvetica', fontSize=9,
                      leading=12, textColor=INK)
rowR = ParagraphStyle('rowR', fontName='Helvetica-Bold', fontSize=9,
                      leading=12, textColor=NAVY, alignment=2)
# The standing phrase that introduces a table ("Below is a list of all
# QUALIFIED investable assets...") is not information, it is furniture. Set
# at full body weight it competes with the figures underneath, which are the
# only part of the section anyone reads twice. So a section that has a table
# gets its sentence in this quieter style, and a section whose sentence IS
# the content keeps full body weight.
headC = ParagraphStyle('headC', fontName='Helvetica-Bold', fontSize=7,
                       leading=9.5, textColor=WHITE)
headR = ParagraphStyle('headR', parent=headC, alignment=2)
headM = ParagraphStyle('headM', parent=headC, alignment=1)
rowM = ParagraphStyle('rowM', fontName='Helvetica', fontSize=9,
                      leading=12, textColor=INK, alignment=1)
barT = ParagraphStyle('barT', fontName='Helvetica-Bold', fontSize=8.5,
                      leading=11, textColor=WHITE)
barN = ParagraphStyle('barN', fontName='Helvetica-Bold', fontSize=9,
                      leading=11, textColor=WHITE)
itemL = ParagraphStyle('itemL', fontName='Helvetica-Bold', fontSize=9,
                       leading=12, textColor=INK)
itemV = ParagraphStyle('itemV', fontName='Helvetica-Bold', fontSize=9.5,
                       leading=12, textColor=ORANGE, alignment=2)
itemD = ParagraphStyle('itemD', fontName='Helvetica', fontSize=7.5,
                       leading=10, textColor=MUTE)
cardL = ParagraphStyle('cardL', fontName='Helvetica-Bold', fontSize=10,
                       leading=13, textColor=INK)
cardV = ParagraphStyle('cardV', fontName='Helvetica-Bold', fontSize=14,
                       leading=18, textColor=NAVY)
cardD = ParagraphStyle('cardD', fontName='Helvetica', fontSize=8.5,
                       leading=12, textColor=MUTE)
lead = ParagraphStyle('lead', fontName='Helvetica', fontSize=8.5,
                      leading=12, textColor=MUTE)
sumL = ParagraphStyle('sumL', fontName='Helvetica', fontSize=9.5, leading=13,
                      textColor=INK)
sumR = ParagraphStyle('sumR', fontName='Helvetica', fontSize=9.5, leading=13,
                      textColor=INK, alignment=2)
sumT = ParagraphStyle('sumT', fontName='Helvetica-Bold', fontSize=10.5,
                      leading=14, textColor=NAVY)
sumT2 = ParagraphStyle('sumT2', parent=sumT, alignment=2)
rowD = ParagraphStyle('rowD', fontName='Helvetica', fontSize=7.5, leading=10,
                      textColor=MUTE, leftIndent=0)



def _x(text):
    """Escape a bare ampersand for reportlab: "M&T" printed as "M&T;"."""
    return re.sub(r'&(?!(?:[a-zA-Z]+|#\d+);)', '&amp;', str(text or ''))

def _block(rows, width, bg, bar):
    t = Table(rows, colWidths=[width])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg),
        ('LINEBEFORE', (0, 0), (-1, -1), 2.5, bar),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (0, 0), 7),
        ('BOTTOMPADDING', (0, -1), (0, -1), 8),
        ('TOPPADDING', (0, 1), (0, -1), 0),
        ('BOTTOMPADDING', (0, 0), (0, -2), 2),
    ]))
    return t



def _titlebar(number, title, width):
    """The section heading: an orange number against a navy title.

    The number gets its own block of colour so the section reads as one
    object at a glance, and so items underneath can use a quieter device
    without competing with it. Previously sections and items both used a
    filled block and only differed in size, which is why neither level
    was obvious.
    """
    t = Table([[Paragraph('%02d' % number, barN),
                Paragraph(title.upper(), barT)]],
              colWidths=[0.34 * inch, width - 0.34 * inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), ORANGE),
        ('BACKGROUND', (1, 0), (1, 0), NAVY),
        ('LEFTPADDING', (0, 0), (0, 0), 6),
        ('RIGHTPADDING', (0, 0), (0, 0), 6),
        ('LEFTPADDING', (1, 0), (1, 0), 8),
        ('RIGHTPADDING', (1, 0), (1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return t


def _titlebar_old(number, title, width):
    """The section heading as a solid navy bar.

    The only thing previously marking a new section was a small orange
    number in the margin, which on a page of five sections gave the reader
    nothing to scan for. A bar is unsubtle and that is the point.
    """
    t = Table([[Paragraph('%02d &nbsp;&nbsp;&nbsp; %s' % (number, title.upper()),
                          barT)]], colWidths=[width])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NAVY),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return t


def _card(row, width):
    """One entry: name, then the figure on its own line, then the basis.

    Kept deliberately tight. The figure wants to be the thing the eye lands
    on, but a section with seven accounts cannot afford a tall block for
    each, so the air comes out of the padding rather than out of the type.
    """
    lines = [[Paragraph(_x(row['label']), cardL)],
             [Paragraph(_x(row['amount'] or ''), cardV)]]
    if row.get('detail'):
        lines.append([Paragraph(_x(row['detail']), cardD)])
    t = Table(lines, colWidths=[width])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BAND_BG),
        ('LINEBEFORE', (0, 0), (-1, -1), 2.5, ORANGE),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (0, 0), 5),
        ('TOPPADDING', (0, 1), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -2), 0),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 6),
    ]))
    return t


def _entry(row, lstyle, dstyle):
    """One entry's name and its basis, as a single cell.

    They used to be two table rows, which is what put a page break between
    a loan and its own interest rate, and what made the gap between the two
    depend on padding rules that had to be unpicked row by row. A cell takes
    a list of flowables, so one entry is now one row and cannot split.
    """
    cell = [Paragraph(_x(row['label']), lstyle)]
    if row.get('detail'):
        cell.append(Paragraph(_x(row['detail']), dstyle))
    return cell if len(cell) > 1 else cell[0]


def _block_list(rows, width):
    """Items as one enclosed table, banded, value in orange.

    One border around the whole set says "these belong together"; the
    banding separates one item from the next; the detail line sits inside
    its item's band rather than floating between two. Three levels, three
    different devices.
    """
    data, styles = [], []
    for i, row in enumerate(rows):
        data.append([_entry(row, itemL, itemD),
                     Paragraph(row['amount'] or '', itemV)])
        if i % 2:
            styles.append(('BACKGROUND', (0, i), (-1, i), BAND_BG))
        if row.get('rule'):
            styles.append(('LINEABOVE', (0, i), (-1, i), 0.75, NAVY))
    t = Table(data, colWidths=[width - 1.4 * inch, 1.4 * inch])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('BOX', (0, 0), (-1, -1), 0.5, RULE),
    ] + styles))
    return t


def _table(rows, heads, width):
    """A ruled table: header row, box, grid, total under a heavy rule.

    Banding alone was not enough. Without a header row the two columns are
    unlabelled, and without a box the block has no edge, so it reads as
    indented text that happens to be aligned rather than as a table.
    """
    # Two or three columns. The middle one is optional because only some
    # tables have something to say between the name and the figure; on a
    # debt schedule that is the maturity, which is the column an adviser
    # actually reads the table for.
    wide = len(heads) == 3
    head_row = [Paragraph(heads[0], headC)]
    if wide:
        head_row.append(Paragraph(heads[1], headM))
    head_row.append(Paragraph(heads[-1], headR))
    data = [head_row]
    styles = [
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TOPPADDING', (0, 0), (-1, 0), 5),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
    ]
    # An entry is one or two physical rows: the figure, and optionally the
    # basis underneath it. A grid drawn across every physical row cuts
    # between a loan and its own interest rate, which splits one entry into
    # two. So lines are drawn per ENTRY, under its last physical row, and
    # the column divider stops before the basis line because that line spans
    # the full width anyway.
    for n, row in enumerate(rows):
        i = n + 1
        cells = [_entry(row, rowL, rowD)]
        if wide:
            cells.append(Paragraph(row.get('mid') or '', rowM))
        cells.append(Paragraph(row['amount'] or '', rowR))
        data.append(cells)
        if (n % 2 == 1) and not row.get('rule'):
            styles.append(('BACKGROUND', (0, i), (-1, i), BAND_BG))
        if row.get('rule'):
            styles.append(('LINEABOVE', (0, i), (-1, i), 0.75, NAVY))
            styles.append(('TOPPADDING', (0, i), (-1, i), 5))
        else:
            styles.append(('LINEBELOW', (0, i), (-1, i), 0.4, RULE))
    styles.append(('INNERGRID', (0, 1), (-2, -1), 0.4, RULE))
    widths = ([width - 2.3 * inch, 1.0 * inch, 1.3 * inch] if wide
              else [width - 1.3 * inch, 1.3 * inch])
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        ('BOX', (0, 0), (-1, -1), 0.9, NAVY),
    ] + styles))
    return t


def _section(sec, title, width):
    col = width
    right = [_titlebar(sec.number, title, col), Spacer(1, 5)]

    if sec.text:
        right.append(Paragraph(sec.text,
                               lead if getattr(sec, 'rows', None) else body))

    rows = getattr(sec, 'rows', None)
    heads = getattr(sec, 'heads', None) or ('Item', 'Amount')
    # Cards by default; a table when the section carries its own total.
    # A total only means something under a column of figures, so a section
    # that has one wants a table and a section that does not wants cards.
    # That happens to put debt and income in tables and the asset listings
    # in cards, which is where judgement would have put them anyway.
    if rows and any(r.get('rule') for r in rows):
        # Held together: a column of figures whose total landed on the next
        # page reads as a different number belonging to nothing.
        right.append(Spacer(1, 5))
        right.append(_table(rows, heads, col))
        rows = None

    if rows:
        right.append(Spacer(1, 5))
        right.append(_block_list(rows, col))

    if sec.text or getattr(sec, 'rows', None):
        if sec.source:
            right.append(Spacer(1, 5))
            right.append(Paragraph(
                '<font name="Helvetica-Bold" color="#A8A49B" size="7">'
                'SOURCE</font>&nbsp;&nbsp; ' + sec.source, source))
        if sec.flag:
            right.append(Spacer(1, 6))
            right.append(_block([[Paragraph('CHECK THIS', needH)],
                                 [Paragraph(sec.flag, needB)]],
                                col, AMBER_BG, ORANGE))

    if sec.needed:
        lines = [[Paragraph('STILL NEEDED', needH)],
                 [Paragraph(sec.needed[0].upper() + sec.needed[1:], needB)]]
        if sec.why:
            lines.append([Paragraph(sec.why[0].upper() + sec.why[1:], needB)])
        if getattr(sec, 'link', None):
            lines.append([Paragraph(
                '<link href="%s"><font color="#9C4A16"><u>%s</u></font></link>'
                % (sec.link, sec.link), needB)])
        if sec.text:
            right.append(Spacer(1, 6))
        right.append(_block(lines, col, AMBER_BG, ORANGE))

    # The section number now rides in the title bar, so the old margin
    # gutter has nothing left to hold and the content takes the full column.
    #
    # Only the head of the section is held together, not the whole of it.
    # Holding all of it meant a seven-account section could not start near
    # the foot of a page, so it jumped to the next one and left half a page
    # blank. What actually must not split is a title bar stranded at the
    # bottom with its contents overleaf, which is the first three flowables.
    return [KeepTogether(right[:3])] + right[3:] + [Spacer(1, 13)]


def _furniture(client, when):
    def draw(c, doc):
        c.saveState()
        w, h = letter
        c.setFillColor(NAVY)
        c.rect(0, h - BAND, w, BAND, stroke=0, fill=1)
        c.setFillColor(ORANGE)
        c.setFont('Helvetica-Bold', 7.5)
        c.drawString(LEFT, h - 0.33 * inch,
                     'THE BASE PLAN  ·  WHAT THE DOCUMENTS SUPPORT')
        c.setFillColor(WHITE)
        c.setFont('Helvetica-Bold', 17)
        c.drawString(LEFT, h - 0.64 * inch, 'Assumptions')
        c.setFillColor(colors.HexColor('#8A9099'))
        c.setFont('Helvetica', 7.5)
        c.drawRightString(w - RIGHT, h - 0.33 * inch,
                          '%s  ·  %s' % (client.upper(), when))
        c.drawRightString(w - RIGHT, h - 0.49 * inch,
                          'PAGE %d' % doc.page)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        c.line(LEFT, 0.68 * inch, w - RIGHT, 0.68 * inch)
        c.setFillColor(FAINT)
        c.setFont('Helvetica', 7)
        c.drawString(LEFT, 0.5 * inch, 'FOUR QUADRANTS ADVISORY')
        c.setFont('Helvetica-Oblique', 7)
        c.drawCentredString(w / 2.0, 0.5 * inch,
                            'Every figure carries the document it came from.')
        c.setFont('Helvetica', 7)
        c.drawRightString(w - RIGHT, 0.5 * inch, 'INTERNAL')
        c.restoreState()
    return draw


# The plan's own running order, named. The numbers are the firm's and do not
# move; the titles are ours, so the reader can find the section about the
# building without reading the fourteen that are not.
TITLES = {
    1: 'Inflation and plan horizon',
    2: 'Retirement and life expectancy',
    3: 'Personal real estate',
    4: 'Qualified investable assets',
    5: 'Non-qualified investable assets',
    6: 'Practice value',
    7: 'Practice building',
    8: 'Personal debt',
    9: 'Practice debt',
    10: 'Income',
    11: 'Social Security',
    12: 'Personal spending',
    13: 'Surplus',
    14: 'Contributions',
}


def render(sections, client, out, practice=None):
    when = datetime.date.today().strftime('%d.%m.%Y')
    doc = BaseDocTemplate(
        out, pagesize=letter, leftMargin=LEFT, rightMargin=RIGHT,
        topMargin=BAND + 0.3 * inch, bottomMargin=0.95 * inch,
        title='Assumptions - %s' % client, author='Four Quadrants Advisory')
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id='f', leftPadding=0, rightPadding=0, topPadding=0,
                  bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id='p', frames=[frame],
                                       onPage=_furniture(client, when))])

    done = sum(1 for s in sections if s.complete)
    story = []
    if practice:
        story.append(Paragraph(practice, intro))
        story.append(Spacer(1, 3))
    story.append(Paragraph(
        '%d of %d sections are written from the documents on file. The '
        'remaining %d are printed with what is needed and why, rather than '
        'omitted.' % (done, len(sections), len(sections) - done), intro))
    story.append(Spacer(1, 10))
    for sec in sections:
        story.extend(_section(sec, TITLES.get(sec.number, ''), doc.width))
    story.append(_summary(sections, doc.width))
    doc.build(story)
    return out


def _summary(sections, width):
    """The closing balance sheet. Every figure is a total of a table above.

    Placed at the end rather than the top because it reads as a conclusion:
    the document spends fourteen sections establishing what the man owns and
    owes, and this is the answer. It is also the document's only internal
    check. An account counted twice or a property left out shows up here as a
    total that looks wrong, which is a kind of error no individual section
    can reveal about itself.
    """
    lines, net, missing = _asm.summarise(sections)
    data, styles, i = [], [], 0
    for name, value in lines:
        data.append([Paragraph(name, sumL),
                     Paragraph(_fmt(value), sumR)])
        if i % 2 == 1:
            styles.append(('BACKGROUND', (0, i), (-1, i), BAND_BG))
        i += 1
    data.append([Paragraph('Net', sumT), Paragraph(_fmt(net), sumT2)])
    styles.append(('LINEABOVE', (0, i), (-1, i), 0.75, NAVY))
    styles.append(('TOPPADDING', (0, i), (-1, i), 7))

    tbl = Table(data, colWidths=[width - 1.6 * inch, 1.6 * inch])
    tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 1.1, NAVY),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, RULE),
    ] + styles))

    head = Paragraph('WHERE THIS LEAVES THE BALANCE SHEET', label)
    note = ('Each figure above is the total of a table in this document, so '
            'the two cannot disagree.')
    if missing:
        note += (' %d asset%s in those tables has no figure yet, so the net '
                 'is understated.' % (missing, '' if missing == 1 else 's'))
    return KeepTogether([Spacer(1, 10), head, Spacer(1, 5), tbl,
                         Spacer(1, 5), Paragraph(note, source)])


def _fmt(v):
    return ('(${:,.0f})'.format(abs(v)) if v < 0 else '${:,.0f}'.format(v))


def main():
    ap = argparse.ArgumentParser(description='Render the Assumptions to PDF')
    ap.add_argument('folder')
    ap.add_argument('--client', default=None)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    bundle = _facts.gather(a.folder, client=a.client)
    sections = _asm.build(bundle, a.folder)
    out = a.out or ('Assumptions - %s.pdf' % (bundle.surname or 'client'))
    render(sections, bundle.client or 'Client', out)
    done = sum(1 for s in sections if s.complete)
    print(out)
    print('%d of %d sections written from documents' % (done, len(sections)))


if __name__ == '__main__':
    main()
