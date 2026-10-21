#!/usr/bin/env python3
"""Build a client's analysis outputs, in one pass over the documents.

    python3 build_outputs.py "<client folder>" --client "Dr. Brian Oyler" \
            --what workbook,summary,cashflow,assumptions,deck

WHY ONE SCRIPT RATHER THAN FOUR
Because three of the four need the cash flow, and the cash flow is seventy
seconds of reading statements. Run as four commands that is three and a half
minutes of the same work done three times. Run in one process the Assumptions'
memo holds it, and the second and third builders get it free.

The other reason is the one the team actually feels. Four scripts is four
things to remember the name of, in an order nobody wrote down. This is the
list, in the order the outputs depend on each other, and the app calls it with
tick boxes.

EVERY STEP IS OPTIONAL AND EVERY STEP REPORTS
A step that fails says so and the next one still runs, because a client whose
statements will not parse should still get the workbook and the summary. A run
that stopped at the first error would give them nothing and look like a broken
tool rather than a missing document.
"""
import os
import sys
import time
import argparse
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))

# The order matters: the cheap ones first, so an operator watching the log
# has something openable within a few seconds, and the cash flow pass is
# paid once by whichever of the later three runs first.
STEPS = ('workbook', 'cashflow', 'summary', 'assumptions', 'deck')

TITLES = {
    'workbook': 'Initial notes workbook',
    'cashflow': 'Cash flow workbook',
    'summary': 'Prospect Summary',
    'assumptions': 'Assumptions',
    'deck': 'Consultation deck',
}


def _surname(folder, client):
    if client:
        return client.split('|')[0].strip().split()[-1]
    return os.path.basename(folder.rstrip('/')).split(',')[0].strip()


def step_workbook(folder, client, outdir):
    import facts as _facts
    import workbook as _wb
    bundle = _facts.gather(folder, client=client)
    out = os.path.join(outdir, 'Initial notes - %s.xlsx'
                       % (bundle.client or _surname(folder, client)))
    _wb.write(bundle, out)
    known = sum(1 for f in bundle.all_facts() if f.value is not None)
    total = len(list(bundle.all_facts()))
    print('   %d of %d facts filled, %d still open'
          % (known, total, total - known))
    return out


def step_cashflow(folder, client, outdir):
    import cashflow as _cf
    import cashflow_workbook as _cwb
    entities = _cf.build(folder)
    if not entities:
        raise RuntimeError('no readable bank statements in this folder')
    out = os.path.join(outdir, 'Cash flow - %s.numbers'
                       % _surname(folder, client))
    path, overflow, _spare = _cwb.write(entities, out)
    # The baseline the analyst's changes are read against next time.
    try:
        import cashflow_review as _review
        _review.snapshot(folder, path)
        n = len(_review.load_decisions(folder))
        if n:
            print('   %d of the analyst\u2019s changes from the last review '
                  'carried into it.' % n)
    except Exception as e:                                   # noqa: BLE001
        print('   could not record the review baseline: %s' % e)
    if overflow:
        print('   %d entit%s did not fit: the template holds four sheets.'
              % (overflow, 'y' if overflow == 1 else 'ies'))
    waiting = sum(len(e['adjustments']) for e in entities)
    if waiting:
        print('   %d movement%s need a decision, on the adjustments block '
              'of each sheet.' % (waiting, '' if waiting == 1 else 's'))
    return path


def step_summary(folder, client, outdir):
    import prospect_page as _pp
    out = os.path.join(outdir, 'Prospect Summary.html')
    with open(out, 'w') as fh:
        fh.write(_pp.build(folder, client))
    return out


def step_assumptions(folder, client, outdir):
    import facts as _facts
    import assumptions as _asm
    import assumptions_pdf as _pdf
    bundle = _facts.gather(folder, client=client)
    sections = _asm.build(bundle, folder)
    out = os.path.join(outdir, 'Assumptions - %s.pdf'
                       % (bundle.surname or _surname(folder, client)))
    _pdf.render(sections, bundle.client or client or 'Client', out)
    done = sum(1 for s in sections if s.complete)
    print('   %d of %d sections written from documents' % (done, len(sections)))
    return out


def step_deck(folder, client, outdir):
    # Last, because it draws on everything above it: the cash flow, the
    # Assumptions store, and the two models.
    # Built on the firm's redesigned deck (assets/consult_template.pptx),
    # so it opens and edits in Keynote like a hand-made one.
    import deck_template as _dt
    out = os.path.join(outdir, 'Consult deck - %s.pptx'
                       % _surname(folder, client))
    path, n, prompts, dropped = _dt.render(folder, client, out)
    print('   %d slides, %d places marked for the advisor%s'
          % (n, prompts, ('; left out slides %s of the template'
                          % ', '.join(map(str, dropped))) if dropped else ''))
    return path


RUNNERS = {
    'deck': step_deck,
    'workbook': step_workbook,
    'cashflow': step_cashflow,
    'summary': step_summary,
    'assumptions': step_assumptions,
}


def main():
    ap = argparse.ArgumentParser(description='Build a client’s outputs')
    ap.add_argument('folder')
    ap.add_argument('--client', default=None)
    ap.add_argument('--outdir', default=None)
    ap.add_argument('--what', default=','.join(STEPS),
                    help='comma separated: %s' % ', '.join(STEPS))
    a = ap.parse_args()

    want = [s.strip() for s in a.what.split(',') if s.strip() in RUNNERS]
    if not want:
        print('Nothing to build.')
        return 1
    want = [s for s in STEPS if s in want]

    outdir = a.outdir or os.path.join(a.folder, '_Audit')
    os.makedirs(outdir, exist_ok=True)

    print('Building %d output%s for %s'
          % (len(want), '' if len(want) == 1 else 's',
             a.client or os.path.basename(a.folder.rstrip('/'))))
    print('')

    made, failed = [], []
    for n, name in enumerate(want, 1):
        print('%d/%d  %s…' % (n, len(want), TITLES[name]))
        began = time.time()
        try:
            path = RUNNERS[name](a.folder, a.client, outdir)
        except Exception as e:
            failed.append((name, str(e)))
            print('   could not build it: %s' % e)
            traceback.print_exc(limit=2)
            continue
        made.append(path)
        print('   %s  (%ds)' % (os.path.basename(path), time.time() - began))

    print('')
    print('%d built, %d failed. They are in %s'
          % (len(made), len(failed), outdir))
    # The app reads these lines to turn each output into a button, so the
    # prefix is a contract rather than decoration.
    for path in made:
        print('OUTPUT\t%s' % path)
    return 1 if failed and not made else 0


if __name__ == '__main__':
    sys.exit(main())
