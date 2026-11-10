"""What the initial notes cannot be built well without: the IC form, the
notes from the initial call (the sales lead's notes, or the call's
transcript or Otter summary), and the fee study (its results in
Documents/Business/Fees, from the fee-comparison step). Checked before the
notes are built, so Claude can say what is still needed instead of building
around a gap.

    python3 notes_inputs.py "<client folder>"

Prints what was found and what is missing; exits 1 when something is.
"""
import os
import re
import sys

IC = re.compile(r'\bic[ _-]?form', re.I)
# Call notes: the sales lead's own notes ("Chad notes", "Casey notes-initial"),
# or the initial call itself (an email, a recording's Otter summary or
# transcript). Consult offer call notes do not count: they come later.
CALL = re.compile(r'(^[a-z]+ notes\b)|(initial[ _-]?call)|(initial notes-otter)|(initial call notes)', re.I)
SKIP_DIRS = {'Original_sourcedocs', '_Audit', 'Consult info'}
EXTS = ('.eml', '.pages', '.pdf', '.docx', '.doc', '.txt', '.rtf', '.png', '.jpg', '.jpeg', '.heic', '.mp3', '.m4a')


def _files(folder):
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for f in files:
            if f.startswith('.') or '.sb-' in f or not f.lower().endswith(EXTS):
                continue
            yield os.path.relpath(os.path.join(root, f), folder)


def check(folder):
    files = list(_files(folder))
    ic = [f for f in files if IC.search(os.path.basename(f))]
    call = [f for f in files if CALL.search(os.path.basename(f))
            and not IC.search(os.path.basename(f))
            and not re.search(r'consult|initial notes - |brogan', os.path.basename(f), re.I)]
    missing = []
    if not ic:
        missing.append('the IC form')
    if not call:
        missing.append("the initial call notes (the sales lead's notes, or the call's transcript or Otter summary)")
    fee = None
    try:
        import compose as _compose
        pct, txt = _compose.fee_study(folder)
        fee = txt if pct is not None else None
    except Exception:                                        # noqa: BLE001
        fee = None
    if not fee:
        missing.append('the fee study (results in Documents/Business/Fees; run the fee comparison '
                       'on the practice fee schedule if it has not been)')
    return {'ic_form': ic, 'call_notes': call, 'fee_study': fee, 'missing': missing}


def main():
    r = check(sys.argv[1])
    print('IC form: %s' % (', '.join(r['ic_form']) or 'NOT FOUND'))
    print('Initial call notes: %s' % (', '.join(r['call_notes']) or 'NOT FOUND'))
    print('Fee study: %s' % (r['fee_study'] or 'NOT FOUND'))
    if r['missing']:
        print('STILL NEEDED before the initial notes: ' + '; '.join(r['missing']))
        sys.exit(1)


if __name__ == '__main__':
    main()
