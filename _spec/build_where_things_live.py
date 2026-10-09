#!/usr/bin/env python3
"""One page: which half of the work is the app, and which half is Claude.

The question this answers is the one that keeps coming back. Two different
things are being built, they meet in one place, and it is easy to lose track of
which is which.

The dividing line is not cleverness. It is whether the work is the same every
time. Downloading, reading, naming and filing sixty documents is the same job on
every client, it has to happen unattended, and it has to give the same answer
twice. That is an app. Working out what a practice's numbers mean, and writing a
plan from them, is different for every client and needs judgement at every step.
That is a conversation, which is what a skill is.

They meet in the client folder. The app fills it; the skills read it.
"""
import os
import datetime
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
from reportlab.lib import colors

W, H = landscape(letter)
NAVY = colors.HexColor('#16324F')
ORANGE = colors.HexColor('#F08418')
GREY = colors.HexColor('#8A9099')
DGREY = colors.HexColor('#5D6773')
LINE = colors.HexColor('#DFDAD0')
GREEN = colors.HexColor('#1F7A4D')
BLUE = colors.HexColor('#2F6DA3')
PURPLE = colors.HexColor('#6B4C8A')
PAPER = colors.HexColor('#FBFAF8')

M = 40
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'FQ_Where_Things_Live.pdf')
c = canvas.Canvas(OUT, pagesize=landscape(letter))


def wrapped(x, y, text, width, size=7, font='Helvetica', lead=8.6,
            colour=DGREY, centred=False):
    c.setFillColor(colour)
    c.setFont(font, size)
    for ln in simpleSplit(text, font, size, width):
        if centred:
            c.drawCentredString(x, y, ln)
        else:
            c.drawString(x, y, ln)
        y -= lead
    return y


def arrow(x1, y1, x2, y2, colour=ORANGE, width=1.4):
    c.setStrokeColor(colour)
    c.setLineWidth(width)
    c.line(x1, y1, x2, y2)
    c.setFillColor(colour)
    p = c.beginPath()
    if abs(y2 - y1) < 1:
        p.moveTo(x2, y2)
        p.lineTo(x2 - 6, y2 + 3.2)
        p.lineTo(x2 - 6, y2 - 3.2)
    else:
        down = y2 < y1
        p.moveTo(x2, y2)
        p.lineTo(x2 - 3.2, y2 + (6 if down else -6))
        p.lineTo(x2 + 3.2, y2 + (6 if down else -6))
    p.close()
    c.drawPath(p, stroke=0, fill=1)


# header
c.setFillColor(NAVY)
c.rect(0, H - 62, W, 62, stroke=0, fill=1)
c.setFillColor(ORANGE)
c.setFont('Helvetica-Bold', 8)
c.drawString(M, H - 26, 'WHERE THINGS LIVE  ·  THE APP AND THE SKILLS')
c.setFillColor(colors.white)
c.setFont('Helvetica-Bold', 17)
c.drawString(M, H - 48, 'Two things are being built, and they meet in one place')
c.setFillColor(colors.HexColor('#9FB0C2'))
c.setFont('Helvetica', 7.5)
c.drawRightString(W - M, H - 32, 'FQ PROSPECT PIPELINE  ·  %s'
                  % datetime.date.today().strftime('%d.%m.%Y'))

y = H - 86
y = wrapped(M, y, 'The line is not which is cleverer. It is whether the work '
                  'is the same every time. Reading and filing sixty documents '
                  'is the same job on every client, has to run unattended, and '
                  'has to give the same answer twice: that is an app. Working '
                  'out what a practice’s numbers mean is different every '
                  'time and needs judgement at each step: that is a '
                  'conversation, which is what a skill is.',
            W - 2 * M, size=9, lead=11.5)
y -= 12

colw = (W - 2 * M - 46) / 2
xL, xR = M, M + colw + 46
top = y

# ---------------------------------------------------------------- left: app
c.setFillColor(PAPER)
c.setStrokeColor(BLUE)
c.setLineWidth(1.3)
c.rect(xL, top - 250, colw, 250, stroke=1, fill=1)
c.setFillColor(BLUE)
c.rect(xL, top - 5, colw, 5, stroke=0, fill=1)
c.setFillColor(NAVY)
c.setFont('Helvetica-Bold', 12)
c.drawString(xL + 14, top - 24, 'THE APP')
c.setFillColor(BLUE)
c.setFont('Helvetica-Bold', 7)
c.drawString(xL + 14, top - 36, 'BUTTONS IN A BROWSER  ·  RUNS ON THE MAC')
yy = wrapped(xL + 14, top - 52,
             'Same job every client. Must run unattended and give the same '
             'answer twice.', colw - 28, size=7.4)

STEPS = [
    ('Pull', 'the document list and checklist from LaunchBay'),
    ('Fetch', 'every file the prospect uploaded'),
    ('Read', 'OCR at three resolutions, cached, legibility judged'),
    ('Place', 'rules first; Claude Code for what they cannot place'),
    ('Name', 'the firm’s convention, collisions resolved'),
    ('File', 'into the folder tree, after a person approves'),
    ('Check', 'every item against the checklist'),
    ('Summarise', 'the Prospect Summary, filling as documents arrive'),
]
yy -= 6
for i, (name, detail) in enumerate(STEPS):
    c.setFillColor(BLUE if i < 7 else ORANGE)
    c.circle(xL + 20, yy + 3, 2.4, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(xL + 28, yy, name)
    c.setFillColor(DGREY)
    c.setFont('Helvetica', 7)
    c.drawString(xL + 28 + c.stringWidth(name, 'Helvetica-Bold', 8) + 6, yy,
                 detail)
    yy -= 14
c.setFillColor(GREY)
c.setFont('Helvetica-Oblique', 6.8)
c.drawString(xL + 14, top - 240, 'Every number here is read or computed by code '
                                 'and checked against a second source.')

# --------------------------------------------------------------- right: skills
c.setFillColor(PAPER)
c.setStrokeColor(ORANGE)
c.setLineWidth(1.3)
c.rect(xR, top - 250, colw, 250, stroke=1, fill=1)
c.setFillColor(ORANGE)
c.rect(xR, top - 5, colw, 5, stroke=0, fill=1)
c.setFillColor(NAVY)
c.setFont('Helvetica-Bold', 12)
c.drawString(xR + 14, top - 24, 'THE SKILLS')
c.setFillColor(ORANGE)
c.setFont('Helvetica-Bold', 7)
c.drawString(xR + 14, top - 36, 'A CONVERSATION IN CLAUDE  ·  ON A SEAT')
yy = wrapped(xR + 14, top - 52,
             'Different every client. Needs a person ruling on things as it '
             'goes.', colw - 28, size=7.4)

SKILLS = [
    ('cashflow-analysis', 'per-account surplus, transfers netted, comingling'),
    ('debt-analysis', 'every loan’s ten fields, amortisation checked'),
    ('investment-analysis', 'balances, allocation, and a verdict on each'),
    ('insurance-analysis', 'policies, benefits, and the gaps'),
    ('tax-return-analysis', 'officer comp, distributions, entity status'),
    ('overhead-analysis', 'the firm methodology, off the P&L'),
    ('assumptions-builder', 'the base plan and the proposed plan'),
    ('due-diligence', 'what is missing or contradictory, as questions'),
    ('consult-deck', 'client slides merged with the standing slides'),
]
yy -= 6
for name, detail in SKILLS:
    c.setFillColor(ORANGE)
    c.circle(xR + 20, yy + 3, 2.4, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 7.6)
    c.drawString(xR + 28, yy, name)
    c.setFillColor(DGREY)
    c.setFont('Helvetica', 7)
    c.drawString(xR + 28 + c.stringWidth(name, 'Helvetica-Bold', 7.6) + 6, yy,
                 detail)
    yy -= 14
c.setFillColor(GREY)
c.setFont('Helvetica-Oblique', 6.8)
c.drawString(xR + 14, top - 240, 'Judgement, varied documents, and a person in '
                                 'the loop throughout.')

# ------------------------------------------------- the ground they meet on
y = top - 268
bw = W - 2 * M
c.setFillColor(colors.HexColor('#F3F6F9'))
c.setStrokeColor(NAVY)
c.setLineWidth(1.2)
c.rect(M, y - 74, bw, 74, stroke=1, fill=1)
arrow(xL + colw / 2, top - 252, xL + colw / 2, y - 2, BLUE)
arrow(xR + colw / 2, y - 2, xR + colw / 2, top - 252, ORANGE)
c.setFillColor(NAVY)
c.setFont('Helvetica-Bold', 10)
c.drawCentredString(W / 2, y - 18, 'THE CLIENT FOLDER')
wrapped(W / 2, y - 32, 'The app fills it. The skills read it and write back '
        'into it. Neither calls the other, and neither has to be running for '
        'the other to work.', bw - 40, size=8, lead=10, centred=True)
c.setFillColor(GREY)
c.setFont('Helvetica', 7)
c.drawCentredString(W / 2, y - 62,
                    'filed documents  ·  extracted text  ·  the facts '
                    'read from them, each with its source  ·  the '
                    'classification ledger  ·  the Assumptions')

# footer
c.setStrokeColor(LINE)
c.setLineWidth(0.7)
c.line(M, 34, W - M, 34)
c.setFillColor(GREY)
c.setFont('Helvetica', 7)
c.drawString(M, 24, 'FOUR QUADRANTS ADVISORY  ·  PROSPECT PIPELINE')
c.setFont('Helvetica-Oblique', 7)
c.drawCentredString(W / 2, 24, 'If a step has to happen the same way every '
                               'time, it belongs on the left.')
c.drawRightString(W - M, 24, 'INTERNAL')
c.save()
print(OUT)
