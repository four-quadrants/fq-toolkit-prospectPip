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
import re
import sys
import time
import argparse
import traceback
import warnings

# Files left for Python to close and the PDF library's renaming notice:
# harmless, and they filled the build log ("enable tracemalloc to get the
# object allocation traceback").
warnings.simplefilter('ignore', ResourceWarning)
warnings.simplefilter('ignore', DeprecationWarning)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))

# The order matters: the cheap ones first, so an operator watching the log
# has something openable within a few seconds, and the cash flow pass is
# paid once by whichever of the later three runs first.
STEPS = ('workbook', 'cashflow', 'summary', 'assumptions', 'duediligence', 'deck')

TITLES = {
    'workbook': 'Initial notes workbook',
    'cashflow': 'Cash flow workbook',
    'summary': 'Prospect Summary',
    'assumptions': 'Assumptions',
    'deck': 'Consultation deck',
    'duediligence': 'Due diligence questions and email',
}


def _surname(folder, client):
    # The folder is "Oyler, Brian - TEST": the surname is before the comma.
    # Taking the last word of the client string named Oyler's workbook
    # "Cash flow - TEST".
    base = os.path.basename(folder.rstrip('/'))
    if ',' in base:
        return base.split(',')[0].strip()
    if client:
        words = [w for w in re.split(r'[\s,|]+', client)
                 if w and w.upper() != 'TEST' and w not in ('-', 'Dr', 'Dr.')]
        if words:
            return words[-1]
    return base.strip()


def step_workbook(folder, client, outdir):
    import facts as _facts
    import workbook as _wb
    try:
        import notes_inputs as _ni
        _gap = _ni.check(folder)['missing']
        if _gap:
            print('   STILL NEEDED for the initial notes: ' + '; '.join(_gap))
    except Exception:                                        # noqa: BLE001
        pass
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
    import cashflow_book as _cwb       # the toolkit's own layout (27 Oct)
    entities = _cf.build(folder)
    # The household's fixed payments (mortgages, insurance, savings) are
    # found by for_assumptions, not by build; carry them onto the Personal
    # tab so the workbook's totals are the Assumptions' totals.
    try:
        fixed_rows = _cf._liabilities(folder)
        for e in entities or ():
            if e['name'] == 'Personal' and not e.get('liabilities'):
                e['liabilities'] = list(fixed_rows)
    except Exception:
        pass
    if not entities:
        raise RuntimeError('no readable bank statements in this folder')
    out = os.path.join(outdir, 'Cash flow - %s.numbers'
                       % _surname(folder, client))
    path, overflow, _spare = _cwb.write(entities, out)
    # The baseline the analyst’s changes are read against next time.
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
    # The Assumptions now live on the review page (its first tab). A PDF is
    # made only when someone asks for one (FQ_ASSUMPTIONS_PDF=1, or "print
    # the assumptions as a PDF" to Claude).
    out = None
    if os.environ.get('FQ_ASSUMPTIONS_PDF') == '1':
        out = os.path.join(outdir, 'Assumptions - %s.pdf'
                           % (bundle.surname or _surname(folder, client)))
        _pdf.render(sections, bundle.client or client or 'Client', out)
    done = sum(1 for s in sections if s.complete)
    print('   %d of %d sections written from documents' % (done, len(sections)))
    # What the lead advisor's review page needs from the documents, read now
    # so the review can come before any deck: the pay figures from the
    # returns, each account's return, and wording for boxes the numbers
    # cannot fill. Claude reads them once; later steps reuse what it read.
    try:
        import deck_template as _dt
        print('   reading the returns and statements for the review page\u2026')
        D = _dt.figures(folder, client)
        words = _dt.proposed_wording(folder, D)
        try:
            import recommendations as _rec
            _rec.claude_candidates(folder, D)
        except Exception as exc:                             # noqa: BLE001
            print('   recommendations: %s' % exc)
        print('   ready for review: pay structure %s, %d account returns, %d drafted boxes'
              % ('read' if D.get('income_facts', {}).get('total_tax') else 'incomplete',
                 sum(1 for v in (D.get('returns') or {}).values()
                     if v.get('return_pct') is not None), len(words)))
    except Exception as exc:                                 # noqa: BLE001
        print('   review readings skipped: %s' % exc)
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


def step_duediligence(folder, client, outdir):
    import duediligence as _dd
    _path, email = _dd.write(folder, outdir)
    return email


RUNNERS = {
    'duediligence': step_duediligence,
    'deck': step_deck,
    'workbook': step_workbook,
    'cashflow': step_cashflow,
    'summary': step_summary,
    'assumptions': step_assumptions,
}


# The outputs people open; they go in the client folder.
OPENED = ('workbook', 'cashflow', 'assumptions', 'deck')


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

    # What people open (the initial notes, the cash flow, the Assumptions,
    # the deck) goes in the client's own folder, beside the documents. The
    # toolkit's internal pages stay in _Audit, and its .json files in
    # <year>/Claude outputs (store.py).
    audit = os.path.join(a.folder, '_Audit')
    outdir = a.outdir or a.folder
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(audit, exist_ok=True)

    print('Building %d output%s for %s'
          % (len(want), '' if len(want) == 1 else 's',
             a.client or os.path.basename(a.folder.rstrip('/'))))
    print('')

    # Every bank statement is read by Claude first, once, and used only
    # where its reading ties out (bank_claude). Everything below reads the
    # statements through statements.gather, which prefers those readings.
    # The initial notes come before the cash flow and do not use the bank
    # statements, so building them alone does not read them.
    if set(want) & {'cashflow', 'assumptions', 'deck'}:
        try:
            import bank_claude as _bc
            _bc.ensure(a.folder)
        except Exception as exc:                             # noqa: BLE001
            print('  bank statements: Claude reading skipped (%s)' % exc)

    made, failed = [], []
    for n, name in enumerate(want, 1):
        print('%d/%d  %s…' % (n, len(want), TITLES[name]))
        began = time.time()
        try:
            path = RUNNERS[name](a.folder, a.client,
                                 outdir if a.outdir or name in OPENED else audit)
        except Exception as e:
            failed.append((name, str(e)))
            print('   could not build it: %s' % e)
            traceback.print_exc(limit=2)
            continue
        if path:
            made.append(path)
            print('   %s  (%ds)' % (os.path.basename(path), time.time() - began))
        else:
            print('   done, nothing to open: it shows on the review page  (%ds)'
                  % (time.time() - began))

    print('')
    print('%d built, %d failed. They are in %s'
          % (len(want) - len(failed), len(failed), outdir))
    # The app reads these lines to turn each output into a button, so the
    # prefix is a contract rather than decoration.
    for path in made:
        print('OUTPUT\t%s' % path)
    return 1 if failed and not made else 0


if __name__ == '__main__':
    sys.exit(main())
