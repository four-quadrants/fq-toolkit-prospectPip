#!/usr/bin/env python3
"""Render the consultation deck to PowerPoint, which opens in Keynote.

    python3 deck_pptx.py "<client folder>" --client "Dr. Brian Oyler" \
            --out "Consult deck - Oyler.pptx"

Content comes from deck.py; this file only lays it out. One layout for every
content slide, because the redesign is regular: eyebrow, headline, hero figure
with a line under it, body or table, and the presenter note. What the advisor
still has to supply prints in an amber box on the slide itself, so an
unfinished deck cannot be mistaken for a finished one.

Needs python-pptx (pip install python-pptx).
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pptx import Presentation                                # noqa: E402
from pptx.util import Inches, Pt                             # noqa: E402
from pptx.dml.color import RGBColor                          # noqa: E402
from pptx.enum.text import PP_ALIGN                          # noqa: E402

import deck as _deck                                         # noqa: E402

NAVY = RGBColor(0x16, 0x32, 0x4F)
INK = RGBColor(0x1B, 0x2A, 0x41)
MUTE = RGBColor(0x6C, 0x74, 0x80)
ORANGE = RGBColor(0xF0, 0x84, 0x18)
BAND = RGBColor(0xF6, 0xF4, 0xEF)
RULE = RGBColor(0xD8, 0xD4, 0xCA)
AMBER_BG = RGBColor(0xFF, 0xF3, 0xE0)
AMBER_TX = RGBColor(0x8A, 0x52, 0x18)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = 'Helvetica Neue'
LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    'assets', 'fq_logo.png')

W, H = Inches(13.333), Inches(7.5)


def _text(slide, x, y, w, h, text, size, color=INK, bold=False,
          align=PP_ALIGN.LEFT, spacing=None):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    lines = text if isinstance(text, list) else [text]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = line
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.name = FONT
        r.font.color.rgb = color
        if spacing:
            p.space_after = Pt(spacing)
    return box


def _rect(slide, x, y, w, h, fill):
    shp = slide.shapes.add_shape(1, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def _footer(slide, n):
    _rect(slide, 0, H - Inches(0.45), W, Inches(0.45), BAND)
    _text(slide, Inches(0.6), H - Inches(0.40), Inches(8), Inches(0.35),
          'FOUR QUADRANTS  ·  The Multimillion Dollar Secret for Dentists',
          10, MUTE)
    _text(slide, W - Inches(1.4), H - Inches(0.40), Inches(0.8),
          Inches(0.35), str(n), 10, MUTE, align=PP_ALIGN.RIGHT)


def _table(slide, x, y, w, spec):
    head, rows = spec['head'], spec['rows']
    if not rows:
        return
    n_rows, n_cols = len(rows) + 1, len(head)
    row_h = Inches(0.42)
    shape = slide.shapes.add_table(n_rows, n_cols, x, y, w,
                                   row_h * n_rows)
    t = shape.table
    # Wide label column only when the first column is words; an Age column
    # in a five-column table needs no more room than the figures beside it.
    first = w * (0.62 if n_cols == 2 else 0.46 if n_cols == 3 else
                 0.40 if n_cols == 4 else 0.12)
    t.columns[0].width = int(first)
    for c in range(1, n_cols):
        t.columns[c].width = int((w - first) / (n_cols - 1))
    for r in range(n_rows):
        for c in range(n_cols):
            cell = t.cell(r, c)
            val = head[c] if r == 0 else rows[r - 1][c]
            cell.text = '' if val is None else str(val)
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY if r == 0 else (
                WHITE if r % 2 else BAND)
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.LEFT if c == 0 else PP_ALIGN.RIGHT
                for run in p.runs:
                    run.font.size = Pt(12 if r else 11)
                    run.font.name = FONT
                    run.font.bold = (r == 0)
                    run.font.color.rgb = WHITE if r == 0 else INK


def _title(prs, s, n):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _rect(slide, 0, 0, W, H, NAVY)
    _text(slide, Inches(0.9), Inches(2.3), Inches(11.5), Inches(0.5),
          s.eyebrow, 16, ORANGE, bold=True)
    _text(slide, Inches(0.9), Inches(2.9), Inches(11.5), Inches(1.4),
          s.headline, 46, WHITE, bold=True)
    if s.sub:
        _text(slide, Inches(0.9), Inches(4.3), Inches(11.5), Inches(0.6),
              s.sub, 20, RGBColor(0xC9, 0xD3, 0xDE))
    if os.path.exists(LOGO):
        pic = slide.shapes.add_picture(LOGO, 0, Inches(0.6),
                                       height=Inches(0.8))
        pic.left = W - pic.width - Inches(0.6)
    slide.notes_slide.notes_text_frame.text = s.note or ''


def _content(prs, s, n):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _rect(slide, 0, 0, W, H, WHITE)
    _rect(slide, Inches(0.6), Inches(0.55), Inches(0.08), Inches(0.38), ORANGE)
    _text(slide, Inches(0.8), Inches(0.5), Inches(10), Inches(0.45),
          s.eyebrow, 13, ORANGE, bold=True)
    _text(slide, Inches(0.6), Inches(1.0), Inches(12), Inches(1.0),
          s.headline, 30, NAVY, bold=True)

    left_w = Inches(4.4)
    y = Inches(2.25)
    has_hero = bool(s.hero)
    if has_hero:
        # The hero has to sit on one line: "$32,958/mo" at 54pt wrapped its
        # unit onto the line below and over the subtext.
        size = 54 if len(s.hero) <= 7 else 44 if len(s.hero) <= 9 else 36
        _text(slide, Inches(0.6), y, left_w, Inches(1.2), s.hero, size, NAVY,
              bold=True)
        if s.sub:
            _text(slide, Inches(0.6), y + Inches(1.25), left_w,
                  Inches(1.4), s.sub, 14, MUTE)
    rx = Inches(5.3) if has_hero else Inches(0.6)
    rw = W - rx - Inches(0.6)
    ry = y
    if s.table and s.table.get('rows'):
        _table(slide, rx, ry, rw, s.table)
        ry = ry + Inches(0.42) * (len(s.table['rows']) + 1) + Inches(0.25)
    if s.body:
        target_x = rx if (s.table or has_hero) else Inches(0.6)
        _text(slide, target_x, ry, rw, Inches(2.5),
              ['•  ' + b for b in s.body], 16, INK, spacing=8)
    if s.needs:
        box_h = Inches(0.35) + Inches(0.3) * min(len(s.needs), 6)
        top = H - Inches(0.6) - box_h
        _rect(slide, Inches(0.6), top, W - Inches(1.2), box_h, AMBER_BG)
        lines = ['STILL NEEDED BEFORE THIS SLIDE IS SHOWN'] + \
            ['–  ' + x for x in s.needs[:6]]
        if len(s.needs) > 6:
            lines.append('–  and %d more, in the notes'
                         % (len(s.needs) - 6))
        _text(slide, Inches(0.8), top + Inches(0.08), W - Inches(1.6),
              box_h, lines, 11, AMBER_TX)
    _footer(slide, n)
    note = s.note or ''
    if s.needs:
        note += '\n\nStill needed: ' + '; '.join(s.needs)
    slide.notes_slide.notes_text_frame.text = note


def render(folder, client, out):
    d = _deck.gather(folder, client)
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    waiting = 0
    for n, s in enumerate(d['slides'], 1):
        (_title if s.kind == 'title' else _content)(prs, s, n)
        waiting += bool(s.needs)
    prs.save(out)
    return out, len(d['slides']), waiting


def main():
    ap = argparse.ArgumentParser(description='Render the consult deck')
    ap.add_argument('folder')
    ap.add_argument('--client', default=None)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    out, n, waiting = render(a.folder, a.client, a.out)
    print('%s: %d slides, %d still waiting on the advisor' % (out, n, waiting))


if __name__ == '__main__':
    main()
