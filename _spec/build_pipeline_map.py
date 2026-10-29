#!/usr/bin/env python3
"""Draw the pipeline map: what happens to a prospect's documents, in order.

Four landscape pages. One for the client-facing timeline, one for the machinery
underneath it, one for how a single fact travels from a document to a slide, and
one for what is built against what is not.

Written for people who do not work in the tool. Every box names what comes out
of it, because a stage nobody can see the output of is a stage nobody trusts.
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
AMBER = colors.HexColor('#D9741A')
RED = colors.HexColor('#C0392B')
BLUE = colors.HexColor('#2F6DA3')
PURPLE = colors.HexColor('#6B4C8A')
PAPER = colors.HexColor('#FBFAF8')

M = 40
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'FQ_Pipeline_Map.pdf')
c = canvas.Canvas(OUT, pagesize=landscape(letter))

BUILT, PART, TODO = 'BUILT', 'PARTLY BUILT', 'TO BUILD'
STATUS_COLOUR = {BUILT: GREEN, PART: AMBER, TODO: RED}


def band(title, kicker, page_no, of=4):
    c.setFillColor(NAVY)
    c.rect(0, H - 62, W, 62, stroke=0, fill=1)
    c.setFillColor(ORANGE)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(M, H - 26, kicker)
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', 17)
    c.drawString(M, H - 48, title)
    c.setFillColor(colors.HexColor('#9FB0C2'))
    c.setFont('Helvetica', 7.5)
    c.drawRightString(W - M, H - 26,
                      'FQ PROSPECT PIPELINE  ·  %s'
                      % datetime.date.today().strftime('%d.%m.%Y'))
    c.drawRightString(W - M, H - 40, 'PAGE %d OF %d' % (page_no, of))


def foot(note=''):
    c.setStrokeColor(LINE)
    c.setLineWidth(0.7)
    c.line(M, 34, W - M, 34)
    c.setFillColor(GREY)
    c.setFont('Helvetica', 7)
    c.drawString(M, 24, 'FOUR QUADRANTS ADVISORY  ·  PROSPECT PIPELINE')
    if note:
        c.setFont('Helvetica-Oblique', 7)
        c.drawCentredString(W / 2, 24, note)
    c.drawRightString(W - M, 24, 'INTERNAL')


def h2(y, text):
    c.setFillColor(ORANGE)
    c.rect(M, y - 2, 3, 11, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 9.5)
    c.drawString(M + 8, y, text.upper())
    return y - 16


def wrapped(x, y, text, width, size=6.8, font='Helvetica', lead=8.2,
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


def arrow(x1, y, x2, colour=LINE):
    c.setStrokeColor(colour)
    c.setLineWidth(1.1)
    c.line(x1, y, x2 - 4, y)
    c.setFillColor(colour)
    p = c.beginPath()
    p.moveTo(x2, y)
    p.lineTo(x2 - 5, y + 2.6)
    p.lineTo(x2 - 5, y - 2.6)
    p.close()
    c.drawPath(p, stroke=0, fill=1)


# ===================================================================== PAGE 1
band('How a prospect moves through the firm',
     'THE TIMELINE  ·  WHAT THE CLIENT SEES', 1)

y = H - 86
y = wrapped(M, y, 'Five moments the prospect experiences. Underneath each one '
                  'sits work the firm does; that is page 2. Nothing here '
                  'changes: the pipeline is being built to fit this, not the '
                  'other way round.', W - 2 * M, size=9.5, lead=13)
y -= 16

MOMENTS = [
    ('1', 'INITIAL LIST', 'We send the first document request.',
     'Checklist out, portal opened', 'LaunchBay'),
    ('2', 'DOCUMENTS ARRIVE', 'The prospect uploads, usually in pieces, '
     'usually over weeks.', 'Documents land in the portal', 'LaunchBay'),
    ('3', 'CONSULT OFFER CALL', 'Sales confirms the prospect wants the '
     'consultation.', 'Go-ahead to build the deck', 'Sales'),
    ('4', 'EXPANDED LIST', 'A second, bigger request now that we know what we '
     'are looking at.', 'Expanded list out', 'LaunchBay'),
    ('5', 'THE CONSULTATION', 'The onboarding team presents. This is what '
     'everything upstream exists for.', 'Consult deck presented',
     'Onboarding team'),
]

bw = (W - 2 * M - 4 * 12) / 5
ytop = y
for i, (n, name, desc, outp, who) in enumerate(MOMENTS):
    x = M + i * (bw + 12)
    c.setFillColor(PAPER)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.9)
    c.rect(x, ytop - 185, bw, 185, stroke=1, fill=1)
    c.setFillColor(NAVY)
    c.rect(x, ytop - 5, bw, 5, stroke=0, fill=1)
    c.setFillColor(ORANGE)
    c.setFont('Helvetica-Bold', 26)
    c.drawString(x + 13, ytop - 40, n)
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 10)
    c.drawString(x + 13, ytop - 58, name)
    yy = wrapped(x + 13, ytop - 78, desc, bw - 26, size=8, lead=10.5)
    c.setStrokeColor(LINE)
    c.line(x + 13, yy - 4, x + bw - 13, yy - 4)
    c.setFillColor(GREY)
    c.setFont('Helvetica-Bold', 6.4)
    c.drawString(x + 13, yy - 18, 'OUTPUT')
    wrapped(x + 13, yy - 30, outp, bw - 26, size=8, lead=10, colour=NAVY,
            font='Helvetica-Bold')
    c.setFillColor(colors.HexColor('#F3F6F9'))
    c.rect(x, ytop - 185, bw, 22, stroke=0, fill=1)
    c.setFillColor(BLUE)
    c.setFont('Helvetica-Bold', 6.6)
    c.drawString(x + 13, ytop - 178, who.upper())
    if i < 4:
        arrow(x + bw + 2, ytop - 90, x + bw + 10)

y = ytop - 207
y = h2(y, 'What the firm produces alongside it, and whose job it is today')
DELIVERABLES = [
    ('Prospect Summary', 'ONBOARDING SPECIALIST  \u00b7  builds as documents arrive',
     'Replaces the old initial notes workbook. Tells the team what is here, what is '
     'missing and what needs judgement. It fills in as more documents come '
     'in, and it is what the offer call is made on.', BLUE),
    ('Assumptions, to ~80%', 'ONBOARDING SPECIALIST  \u00b7  after #4',
     'The base plan, built from the documents. Most of it is done before the '
     'COO ever opens it.', ORANGE),
    ('Finalize Assumptions / Due Diligence', 'COO  \u00b7  before #5',
     'The analysis is checked against what has and has not been received. '
     'That produces the list of questions and confirmations for the prospect, '
     'and their answers complete the plan.', PURPLE),
    ('Create the consult deck', 'ONBOARDING TEAM  \u00b7  before #5',
     'Client slides merged with the standing slides. Built from the finished '
     'plan, not from the documents again.', GREEN),
]
dw = (W - 2 * M - 3 * 14) / 4
for i, (name, when, desc, col) in enumerate(DELIVERABLES):
    x = M + i * (dw + 14)
    c.setFillColor(colors.white)
    c.setStrokeColor(LINE)
    c.rect(x, y - 118, dw, 118, stroke=1, fill=1)
    c.setFillColor(col)
    c.rect(x, y - 118, 4, 118, stroke=0, fill=1)
    # A long title wraps onto a second line rather than running off the card,
    # and everything beneath it shifts down by however many lines it took.
    lines = simpleSplit(name, 'Helvetica-Bold', 10, dw - 28)
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 10)
    ty = y - 20
    for ln in lines:
        c.drawString(x + 14, ty, ln)
        ty -= 12
    drop = (len(lines) - 1) * 12
    role, _, moment = when.partition('·')
    c.setFillColor(col)
    c.setFont('Helvetica-Bold', 6.6)
    c.drawString(x + 14, y - 33 - drop, role.strip().upper())
    c.setFillColor(GREY)
    c.setFont('Helvetica', 6.6)
    c.drawString(x + 14, y - 43 - drop, moment.strip())
    c.setStrokeColor(LINE)
    c.line(x + 14, y - 51 - drop, x + dw - 14, y - 51 - drop)
    wrapped(x + 14, y - 63 - drop, desc, dw - 28, size=7.6, lead=9.8)

y -= 137
y = h2(y, 'What changes')
CHANGE = [
    ('Opening and filing the documents',
     'Most of a day, by hand, every prospect',
     'Minutes, unattended. Built and working'),
    ('Knowing what is missing',
     'Found by reading everything, late',
     'On the Prospect Summary before anyone opens a file'),
    ('The due diligence behind the questions',
     'Hours of the COO’s reading',
     'Flagged automatically; the COO rules on it'),
    ('Building the Assumptions',
     'Started from last client’s document',
     'Generated from the facts, with sources attached'),
]
cw = (W - 2 * M - 3 * 12) / 4
for i, (what, now, after) in enumerate(CHANGE):
    x = M + i * (cw + 12)
    c.setFillColor(colors.white)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.9)
    c.rect(x, y - 76, cw, 76, stroke=1, fill=1)
    yy = wrapped(x + 11, y - 14, what, cw - 22, size=7.6, lead=9.4,
                 colour=NAVY, font='Helvetica-Bold')
    c.setFillColor(RED)
    c.setFont('Helvetica-Bold', 5.8)
    c.drawString(x + 11, yy - 4, 'TODAY')
    yy = wrapped(x + 11, yy - 14, now, cw - 22, size=6.8, lead=8.4)
    c.setFillColor(GREEN)
    c.setFont('Helvetica-Bold', 5.8)
    c.drawString(x + 11, yy - 3, 'WITH THE PIPELINE')
    wrapped(x + 11, yy - 13, after, cw - 22, size=6.8, lead=8.4, colour=NAVY)

foot('The timeline is fixed. The pipeline is built to fit it.')
c.showPage()

# ===================================================================== PAGE 2
band('The machinery underneath',
     'THE PIPELINE  ·  SIXTEEN STEPS, EIGHT SKILLS TO BUILD', 2)

y = H - 84
STAGES = [
    ('INTAKE', BLUE, 'Onboarding specialist', [
        ('Pull', 'fq-launchbay-pull', 'Document list + checklist out of '
         'LaunchBay', BUILT),
        ('Fetch', 'auditor', 'Download every document the prospect sent',
         BUILT),
        ('Read', 'auditor', 'OCR and classify by content, never by filename',
         BUILT),
        ('Audit & file', 'auditor', 'Match against the checklist; file into '
         'the folder tree', BUILT),
        ('Prospect Summary', 'auditor', 'Two pages: what is here, what is '
         'missing, what needs judgement', PART),
    ]),
    ('ANALYSIS', ORANGE, 'Onboarding specialist + COO, where the hours go '
     'today', [
        ('Cashflow & expenses', 'cashflow-analysis (fork)', 'Per-account '
         'surplus, transfers netted, comingling, ghost accounts', PART),
        ('Liabilities', 'debt-analysis', 'Every loan’s ten fields; '
         'amortisation checks; three sources reconciled', TODO),
        ('Qualified assets', 'investment-analysis', 'Balances, allocation, '
         'returns, and a verdict on each', TODO),
        ('Insurance', 'insurance-analysis', 'Policies, benefits, premiums; '
         'coverage gaps', TODO),
        ('Income & entities', 'tax-return-analysis', '1120-S, 1040, K-1, '
         'Sch E. Officer comp, distributions, entity status', TODO),
        ('Overhead', 'overhead-analysis', 'Firm methodology, off the P&L',
         BUILT),
        ('Fee positioning', 'fee-comparison', 'Practice fees against the '
         'NDAS percentile', BUILT),
        ('Production', 'auditor', 'Practice Analysis + Provider Summary, '
         'per doctor', BUILT),
    ]),
    ('SYNTHESIS', GREEN, 'Onboarding specialist, then COO + team', [
        ('Assumptions', 'assumptions-builder', 'Base plan and proposed plan, '
         'from the facts rather than last client’s document', TODO),
        ('Due diligence list', 'followup-builder', 'What is still missing or '
         'contradictory, as questions for the prospect', TODO),
        ('Consult deck', 'consult-deck', 'Client slides merged with the '
         'standing slides', TODO),
    ]),
]

for title, colour, owner, items in STAGES:
    c.setFillColor(colour)
    c.rect(M, y - 10, 3, 13, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 9)
    c.drawString(M + 9, y - 8, title)
    off = M + 9 + c.stringWidth(title, 'Helvetica-Bold', 9) + 8
    c.setFillColor(GREY)
    c.setFont('Helvetica', 6.5)
    c.drawString(off, y - 8, '%d steps' % len(items))
    c.setFillColor(colour)
    c.setFont('Helvetica-Bold', 6.5)
    c.drawString(off + 44, y - 8, owner.upper())
    y -= 20

    per_row = 5
    bwid = (W - 2 * M - (per_row - 1) * 8) / per_row
    for i, (name, skill, desc, status) in enumerate(items):
        col = i % per_row
        if col == 0 and i:
            y -= 76
        x = M + col * (bwid + 8)
        scol = STATUS_COLOUR[status]
        c.setFillColor(colors.white)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.9)
        c.rect(x, y - 70, bwid, 70, stroke=1, fill=1)
        c.setFillColor(scol)
        c.rect(x, y - 3, bwid, 3, stroke=0, fill=1)
        c.setFillColor(NAVY)
        c.setFont('Helvetica-Bold', 7.6)
        c.drawString(x + 7, y - 15, name)
        c.setFillColor(colour)
        c.setFont('Helvetica-Oblique', 6)
        c.drawString(x + 7, y - 24, skill)
        wrapped(x + 7, y - 35, desc, bwid - 14, size=6.1, lead=7.4)
        c.setFillColor(scol)
        c.setFont('Helvetica-Bold', 5.6)
        c.drawString(x + 7, y - 64, status)
    y -= 86

c.setFillColor(GREY)
c.setFont('Helvetica-Oblique', 7)
c.drawString(M, y + 4, 'Green = working today.  Amber = built but incomplete.  '
                       'Red = not started.  Eight skills to build, five of them '
                       'in the analysis half where the hours go; three more '
                       '(launchbay-pull, overhead, fee-comparison) already '
                       'exist, and the auditor is the tool rather than a skill.')
foot()
c.showPage()

# ===================================================================== PAGE 3
band('How one fact travels', 'THE FACT DICTIONARY  ·  72 FACTS', 3)

y = H - 84
y = wrapped(M, y, 'Everything hangs off one list: every fact the firm needs, '
                  'which documents can carry it, and what it gets checked '
                  'against. A fact with no source becomes a question. A fact '
                  'with two sources that disagree becomes a flag. A fact with '
                  'a source becomes a filled field, in all four outputs '
                  'at once.', W - 2 * M, size=8.5, lead=11)
y -= 14

colw = (W - 2 * M - 70) / 3
x1 = M
x2 = M + colw + 35
x3 = M + 2 * colw + 70

c.setFillColor(NAVY)
c.setFont('Helvetica-Bold', 8)
for x, t in ((x1, 'CLIENT DOCUMENTS'), (x2, 'THE DICTIONARY'),
             (x3, 'THE FOUR OUTPUTS')):
    c.drawString(x, y, t)
y -= 6

docs = ['Bank statements', 'Tax returns (1120-S, 1040, K-1)', 'P&L and balance sheet',
        'Debt schedule', 'Credit report', 'Payroll report',
        'Insurance policies', 'Investment statements',
        'Practice Analysis + Provider Summary', 'Fee schedule',
        'Leases and contracts', 'IC intake form', 'Call notes']
yy = y
for d in docs:
    c.setFillColor(BLUE)
    c.circle(x1 + 3, yy - 3, 1.8, stroke=0, fill=1)
    c.setFillColor(DGREY)
    c.setFont('Helvetica', 7)
    c.drawString(x1 + 10, yy - 5, d)
    yy -= 12.5
docs_bottom = yy

c.setFillColor(colors.HexColor('#F6F4EF'))
c.setStrokeColor(ORANGE)
c.setLineWidth(1.1)
c.rect(x2, y - 150, colw, 150, stroke=1, fill=1)
inner = y - 14
c.setFillColor(NAVY)
c.setFont('Helvetica-Bold', 7.5)
c.drawString(x2 + 10, inner, '72 facts · 11 sections')
inner -= 14
for label, detail, col in [
        ('Readable', 'a document states it outright', GREEN),
        ('Computed', 'we calculate it from others', BLUE),
        ('Detected', 'found by comparing documents', PURPLE),
        ('Ask', 'only a person can answer', AMBER),
        ('Conflict-prone', 'seen disagreeing across your own documents', RED)]:
    c.setFillColor(col)
    c.rect(x2 + 10, inner - 1, 3, 7, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 6.6)
    c.drawString(x2 + 18, inner, label)
    c.setFillColor(DGREY)
    c.setFont('Helvetica', 6.4)
    c.drawString(x2 + 18 + c.stringWidth(label, 'Helvetica-Bold', 6.6) + 5,
                 inner, ': ' + detail)
    inner -= 13
inner -= 4
c.setStrokeColor(LINE)
c.line(x2 + 10, inner + 4, x2 + colw - 10, inner + 4)
wrapped(x2 + 10, inner - 6, 'Every figure carries its source: the folder it '
        'lives in, the file, the page, and the line. A figure with no source '
        'record is not published. It prints as a dash and joins the '
        'due diligence list.', colw - 20, size=6.4, lead=8)

outs = [('Prospect Summary', 'what is here, what is missing', BLUE, False),
        ('ASSUMPTIONS', 'the plan everything else reads from', ORANGE, True),
        ('Due diligence list', 'what to ask next', PURPLE, False),
        ('Consult deck', 'what the team presents', GREEN, False)]
yy = y
for name, detail, col, hub in outs:
    hgt = 46 if hub else 32
    c.setFillColor(colors.HexColor('#F6F4EF') if hub else colors.white)
    c.setStrokeColor(col if hub else LINE)
    c.setLineWidth(1.4 if hub else 0.9)
    c.rect(x3, yy - hgt, colw, hgt, stroke=1, fill=1)
    c.setFillColor(col)
    c.rect(x3, yy - hgt, 4 if hub else 3, hgt, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 9 if hub else 7.6)
    c.drawString(x3 + 11, yy - (19 if hub else 14), name)
    c.setFillColor(GREY)
    c.setFont('Helvetica', 6.4)
    c.drawString(x3 + 11, yy - (31 if hub else 25), detail)
    if hub:
        c.setFillColor(col)
        c.setFont('Helvetica-Bold', 5.6)
        c.drawString(x3 + 11, yy - 40, 'FEEDS THE TWO BELOW; BUILT FROM THE '
                                       'ONE ABOVE')
    yy -= hgt + 8

# the three non-hub boxes connect to the hub rather than sitting beside it
c.setStrokeColor(ORANGE)
c.setLineWidth(0.9)
c.setDash(2, 2)
c.line(x3 - 8, y - 16, x3 - 8, yy + 24)
c.setDash()

y = min(docs_bottom, y - 160) - 10
y = h2(y, 'Three outputs for every analysis')
for i, (fmt, rank, detail) in enumerate([
        ('Workbook (.xlsx)', 'PRIMARY', 'One row per figure with its full '
         'source record, live formulas. A reviewer checks the arithmetic '
         'themselves.'),
        ('PDF', 'PRIMARY', 'The presentation copy. Source tag against each '
         'figure, full records in an appendix.'),
        ('HTML', 'OPTIONAL', 'For anyone who wants it. Never the only '
         'format.')]):
    bw3 = (W - 2 * M - 2 * 14) / 3
    x = M + i * (bw3 + 14)
    c.setFillColor(colors.white)
    c.setStrokeColor(LINE)
    c.rect(x, y - 44, bw3, 44, stroke=1, fill=1)
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(x + 10, y - 15, fmt)
    c.setFillColor(GREEN if rank == 'PRIMARY' else GREY)
    c.setFont('Helvetica-Bold', 5.8)
    c.drawString(x + 10 + c.stringWidth(fmt, 'Helvetica-Bold', 8) + 8, y - 15,
                 rank)
    wrapped(x + 10, y - 27, detail, bw3 - 20, size=6.4, lead=7.8)

foot()
c.showPage()

# ===================================================================== PAGE 4
band('What is built, and what it would take',
     'STATUS  ·  THE ORDER OF WORK', 4)

y = H - 86
y = h2(y, 'Today')
FACTS = [('16', 'steps in the pipeline'), ('8', 'skills to build, 3 exist'),
         ('72', 'facts in the dictionary'), ('30', 'with an independent check'),
         ('311', 'legacy files converted'), ('1', 'client proven end to end')]
fw = (W - 2 * M - 5 * 10) / 6
for i, (big, small) in enumerate(FACTS):
    x = M + i * (fw + 10)
    c.setFillColor(PAPER)
    c.setStrokeColor(LINE)
    c.rect(x, y - 48, fw, 48, stroke=1, fill=1)
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 20)
    c.drawCentredString(x + fw / 2, y - 26, big)
    c.setFillColor(GREY)
    c.setFont('Helvetica', 6.4)
    wrapped(x + fw / 2, y - 37, small, fw - 10, size=6.4, lead=7.5,
            centred=True)
y -= 66

y = h2(y, 'The order I would build it')
ORDER = [
    ('1', 'Finish the Prospect Summary',
     'Risk flags, debt and asset tiles, fee positioning, page 2. Straight '
     'into the onboarding specialist\u2019s hands. It replaces the '
     'file-opening done by hand today.', 'A SESSION OR TWO'),
    ('2', 'Prove the intake half on a second client',
     'Everything so far is tuned to one folder. The P&L reader already '
     'returned nothing on Larsen. This is the honest test.', 'A SESSION'),
    ('3', 'Cashflow & expenses',
     'Fork the existing skill, extend it: practice accounts, account '
     'classification, weighted averages, the two expense figures.', 'THE BIGGEST ONE'),
    ('4', 'Liabilities, then tax returns',
     'The two that feed the most fields and produce the most follow-up '
     'questions. Amortisation checks live here.', 'A SESSION EACH'),
    ('5', 'Investments and insurance',
     'Varied statement formats; both carry a judgement, not just a figure.',
     'A SESSION EACH'),
    ('6', 'Assumptions builder',
     'Only once the facts beneath it are reliable. Generating this kills the '
     'copy-paste errors. Oyler\u2019s current plan still names another '
     'client.', 'A SESSION OR TWO'),
    ('7', 'Due diligence list, then the deck',
     'The due diligence list falls out of the analysis once it is reliable; '
     'the deck is assembly. Both come last because neither can be better '
     'than what feeds them.', 'A SESSION EACH'),
]
for n, title, detail, size in ORDER:
    c.setFillColor(ORANGE)
    c.setFont('Helvetica-Bold', 11)
    c.drawString(M, y, n)
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 8.6)
    c.drawString(M + 15, y, title)
    c.setFillColor(GREY)
    c.setFont('Helvetica-Bold', 6)
    c.drawRightString(W - M, y, size)
    wrapped(M + 15, y - 11, detail, W - 2 * M - 70, size=7, lead=8.6)
    y -= 30

y -= 4
c.setFillColor(colors.HexColor('#FDF3E4'))
c.setStrokeColor(colors.HexColor('#E8CDA0'))
c.setLineWidth(0.9)
c.rect(M, y - 44, W - 2 * M, 50, stroke=1, fill=1)
c.setFillColor(NAVY)
c.setFont('Helvetica-Bold', 8.6)
c.drawString(M + 12, y - 8, 'What actually sets the pace')
wrapped(M + 12, y - 22, 'Build time is not the constraint. The production '
        'reader, the provider reconciliation and the tax-basis reader were '
        'all built in a day. What sets the pace is review time on each piece, '
        'and having real documents from a second and third prospect to test '
        'against. Every stage marked green has been proven on one '
        'client folder, and the one time the P&L reader met a second prospect '
        'it produced nothing, because that bookkeeper uses a different chart '
        'of accounts.', W - 2 * M - 24, size=7, lead=8.6)

foot()
c.save()
print(OUT)
