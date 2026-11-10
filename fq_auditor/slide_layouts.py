#!/usr/bin/env python3
"""Pictures of the layouts a new slide can take, for the review page.

    python3 slide_layouts.py        # rebuild the pictures inside the page

Each layout is built from the deck template with sample wording (generic, no
client), turned into a small picture, and written into
assets/review_page.html between the LAYOUT_PICS markers, so the page needs
no extra files. Run it again whenever the template or a layout changes.
"""
import base64
import io
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deck_template as dt                                   # noqa: E402

SAMPLES = {
    'points': {'eyebrow': 'Next steps', 'title': 'What happens after today',
               'items': ['Sign the agreement and the ACH form', 'Send the expanded documents',
                         'Kick-off call in two weeks', 'First monthly report by the 15th']},
    'statement': {'eyebrow': 'A word on taxes', 'title': 'The S-corp question',
                  'body': 'Electing S-corp status this year saves an estimated '
                          '$18,000 in self-employment tax.\nWe file the election by March 15.'},
    'statement_points': {'eyebrow': 'The bottom line', 'title': 'Cash first, then everything else',
                         'body': 'One month of overhead in the practice account before any new spending.',
                         'items': ['Pause discretionary spending for twelve months',
                                   'Open a $120,000 line of credit as the backstop',
                                   'Review every decision over $5,000 with us']},
    'figures': {'eyebrow': 'At a glance', 'title': 'Three numbers that matter', 'note': 'From the P&L and return',
                'figures': [['$1.2M', 'Collections', 'Up 9% on the year before, with the same doctor days.'],
                            ['62%', 'Overhead', 'Seven points above the target, mostly staff and supplies.'],
                            ['$0', 'Saved last year', 'Nothing put away for retirement in the last twelve months.']]},
    'columns': {'eyebrow': 'The plan', 'title': 'Three priorities this year',
                'columns': [['Cash', 'One month of overhead in the account\nA line of credit as backstop'],
                            ['Taxes', 'Quarterly projections\nNo surprises in April'],
                            ['Savings', 'New 401(k) with profit share\nFunded from the first month']]},
    'two': {'eyebrow': 'How you get paid', 'title': 'Today and with Four Quadrants',
            'columns': [['Today', 'Distributions taken as needed\nW-2 set years ago\nTax bill a surprise each April'],
                        ['With Four Quadrants', 'A set W-2 and a set distribution\n401(k) maxed every year\nQuarterly estimates, no surprises']]},
    'compare': {'eyebrow': 'Side by side', 'title': 'Where you are, where you could be',
                'heads': ['', 'Today', 'With Four Quadrants'],
                'rows': [['Overhead', '68%', '60%'], ['Take-home', '$310,000', '$385,000'],
                         ['Saved a year', '$24,000', '$96,000']],
                'body': 'Includes our fees\nEvery figure on the right is after what we charge.'},
    'accounts': {'eyebrow': 'Investments, today', 'title': 'Account by account', 'note': 'Against 4Q\u2019s returns, annualized',
                 'rows': [['401(k)', 'Employer plan', '$412,000', 'One target-date fund, 0.36% a year', 'Yes', '\u22122.4%', 'a year'],
                          ['SEP IRA', 'Brokerage', '$186,000', '16 positions, 34% in cash', 'Yes', '\u22129.1%', 'a year'],
                          ['529 plans (3)', 'Children', '$58,000', 'Annuity-based, high fees', 'For college', '\u22125.1%', '']],
                 'figure': '$32,600', 'body': 'More they would have this year at Four Quadrants\u2019 returns, on the same balances.'},
    'steps': {'eyebrow': 'Getting started', 'title': 'The first ninety days', 'body': 'Onboarding',
              'steps': [['Week 1', 'Agreement signed, documents in'], ['Week 2', 'Kick-off call and access set up'],
                        ['Month 1', 'Books cleaned up and reconciled'], ['Month 2', 'New pay structure in place'],
                        ['Month 3', 'First quarterly review']]},
}


def build(out_dir):
    from pptx import Presentation
    prs = Presentation(dt.TEMPLATE)
    keys = [k for k, _l, _d in dt.LAYOUT_INFO]
    added = [dict(SAMPLES[k], layout=k, after=99) for k in keys]
    dt.apply_deck_edits(prs, {'removed': list(range(1, len(prs.slides) + 1)), 'added': added}, [])
    path = os.path.join(out_dir, 'layouts.pptx')
    prs.save(path)
    subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', out_dir, path],
                   capture_output=True, timeout=300)
    import pymupdf
    from PIL import Image
    doc = pymupdf.open(os.path.join(out_dir, 'layouts.pdf'))
    pics = {}
    for k, page in zip(keys, doc):
        pix = page.get_pixmap(dpi=36)
        img = Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=72)
        pics[k] = 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()
    return pics


def build_library(out_dir):
    """Pictures of the occasional slides in slide_library.json, each built
    from its preset (generic wording, brackets where the client's figures
    go). A library slide that is a template slide uses that slide's picture."""
    from pptx import Presentation
    lib = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'slide_library.json')))['slides']
    made = [e for e in lib if e.get('preset')]
    prs = Presentation(dt.TEMPLATE)
    added = [dict(e['preset'], after=99) for e in made]
    tmpl = [e for e in lib if e.get('template_slide')]
    dt.apply_deck_edits(prs, {'removed': [n for n in range(1, len(prs.slides) + 1)
                                          if n not in {e['template_slide'] for e in tmpl}],
                              'added': added}, [])
    path = os.path.join(out_dir, 'library.pptx')
    prs.save(path)
    subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', out_dir, path],
                   capture_output=True, timeout=300)
    import pymupdf
    from PIL import Image
    doc = pymupdf.open(os.path.join(out_dir, 'library.pdf'))
    pages = list(doc)
    order = tmpl + made              # the kept template slides come first
    out = []
    for e, page in zip(order, pages):
        pix = page.get_pixmap(dpi=36)
        img = Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=72)
        d = {k: v for k, v in e.items()}
        d['pic'] = 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()
        out.append(d)
    keys = [e['key'] for e in lib]
    return sorted(out, key=lambda d: keys.index(d['key']))


def main():
    lib = build_library(tempfile.mkdtemp())
    page = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'review_page.html')
    html = open(page).read()
    block = '/*SLIDE_LIB*/var SLIDELIB=%s;/*END_SLIDE_LIB*/' % json.dumps(lib)
    if '/*SLIDE_LIB*/' in html:
        html = re.sub(r'/\*SLIDE_LIB\*/.*?/\*END_SLIDE_LIB\*/', lambda m: block, html, flags=re.S)
    else:
        html = html.replace('/*LAYOUT_PICS*/', block + '\n  /*LAYOUT_PICS*/', 1)
    open(page, 'w').write(html)
    print('%d library slides written into the page' % len(lib))
    pics = build(tempfile.mkdtemp())
    info = [{'key': k, 'label': l, 'desc': d, 'pic': pics.get(k, '')} for k, l, d in dt.LAYOUT_INFO]
    page = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'review_page.html')
    html = open(page).read()
    block = '/*LAYOUT_PICS*/var LAYOUTS=%s;/*END_LAYOUT_PICS*/' % json.dumps(info)
    html, n = re.subn(r'/\*LAYOUT_PICS\*/.*?/\*END_LAYOUT_PICS\*/', lambda m: block, html, flags=re.S)
    if not n:
        sys.exit('No LAYOUT_PICS marker in the page.')
    open(page, 'w').write(html)
    print('%d layout pictures written into the page (%d KB)'
          % (len(info), sum(len(x['pic']) for x in info) // 1024))


if __name__ == '__main__':
    main()
