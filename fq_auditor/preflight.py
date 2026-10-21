#!/usr/bin/env python3
"""Check this Mac can run the FQ Toolkit, and say plainly what is missing.

    python3 preflight.py              # check everything, print a report
    python3 preflight.py --quiet      # print only problems
    python3 preflight.py --json       # machine-readable, for the launcher

WHY THIS EXISTS
Standing the toolkit up on a second machine means Python, four libraries, a
text reader, a mounted server share and a free port all being right at once.
Discovering that one traceback at a time is how an afternoon disappears — and
the person doing it is not the person who wrote the code, so a stack trace is
worse than useless to them.

Every check answers three things: what is wrong, why it matters, and the exact
command that fixes it. A check that only reports failure has moved the problem
rather than solved it.

Nothing here installs anything or touches client files. It only looks.
"""
import os
import re
import sys
import json
import socket
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

# What the app actually imports, and what breaks without each one. The reason
# text matters: told "openpyxl is missing", nobody knows whether that is fatal
# or cosmetic, so they either panic or ignore it.
LIBS = [
    ('pymupdf',    'pymupdf',     'reading PDFs — nothing works without it',      True),
    ('PIL',        'pillow',      'page previews and the logo',                   True),
    ('openpyxl',   'openpyxl',    'reading spreadsheets and the preview grid',    True),
    ('docx',       'python-docx', 'writing the internal audit report',            True),
    ('pytesseract', 'pytesseract', 'reading scanned documents (OCR)',             True),
    # The Build Outputs tab. Missing from this list until 21 October, so a
    # new Mac passed the check and then failed on its first build.
    ('numbers_parser', 'numbers-parser', 'writing the cash flow workbook',      True),
    ('reportlab',  'reportlab',   'writing the Assumptions PDF',                  True),
    ('pptx',       'python-pptx', 'writing the consultation deck',                True),
]

PORT = int(os.environ.get('FQ_PORT', '8765'))
MIN_PY = (3, 9)


class Report:
    """Collects results so the exit code and the printout agree."""

    def __init__(self):
        self.rows = []

    def add(self, ok, name, detail, fix=None, fatal=True):
        self.rows.append({'ok': bool(ok), 'name': name, 'detail': detail,
                          'fix': fix, 'fatal': bool(fatal)})

    @property
    def broken(self):
        return [r for r in self.rows if not r['ok'] and r['fatal']]

    @property
    def warnings(self):
        return [r for r in self.rows if not r['ok'] and not r['fatal']]


def check_python(rep):
    v = sys.version_info
    ok = v >= MIN_PY
    rep.add(ok, 'Python',
            'version %d.%d.%d' % (v.major, v.minor, v.micro) if ok else
            'version %d.%d is too old (need %d.%d or newer)'
            % (v.major, v.minor, MIN_PY[0], MIN_PY[1]),
            fix='brew install python')


def check_libs(rep):
    import importlib
    missing = []
    for mod, pipname, why, fatal in LIBS:
        try:
            importlib.import_module(mod)
            rep.add(True, pipname, why)
        except Exception as e:
            missing.append(pipname)
            rep.add(False, pipname, '%s — needed for %s' % (type(e).__name__, why),
                    fatal=fatal)
    if missing:
        # One command that fixes all of them, rather than making someone run
        # five. --break-system-packages is what Homebrew's Python requires,
        # and Apple's own Python 3.9 rejects it as an unknown option: the new
        # iMac on 20 October. --user is what Apple's needs.
        apple = sys.executable.startswith(('/usr/bin/', '/Library/Developer/',
                                           '/Applications/Xcode'))
        flag = '--user' if apple else '--break-system-packages'
        rep.rows.append({'ok': False, 'name': 'install them all', 'fatal': False,
                         'detail': 'run this once',
                         'fix': 'python3 -m pip install %s ' % flag
                                + ' '.join(missing)})


def check_tesseract(rep):
    """On PATH is not the same as working, so run it."""
    path = None
    for d in ('', '/opt/homebrew/bin/', '/usr/local/bin/'):
        cand = d + 'tesseract'
        try:
            out = subprocess.run([cand, '--version'], capture_output=True,
                                 text=True, timeout=15)
            if out.returncode == 0:
                path = cand
                ver = (out.stdout or out.stderr).splitlines()[0].strip()
                rep.add(True, 'tesseract', ver + (' (%s)' % d if d else ''))
                break
        except Exception:
            continue
    if not path:
        rep.add(False, 'tesseract',
                'not installed — scanned documents cannot be read, and a scanned '
                'statement will look like an empty file rather than an error',
                fix='brew install tesseract')


def check_port(rep, port=PORT):
    s = socket.socket()
    try:
        s.bind(('127.0.0.1', port))
        rep.add(True, 'port %d' % port, 'free')
    except OSError:
        # Not fatal: the app hops to the next port. It IS worth saying, because
        # a browser pointed at the old port shows a stale copy of the app and
        # every change you make appears to do nothing.
        rep.add(False, 'port %d' % port,
                'already in use — probably an older copy of the app still running. '
                'It will start on a different port, and a browser tab left on %d '
                'will keep showing the old one.' % port,
                fix='pkill -f fq_app.py', fatal=False)
    finally:
        s.close()


def check_share(rep, path=None):
    """The prospects share. Everything downstream reads and writes here."""
    path = path or os.environ.get('FQ_SHARE') or '/Volumes/Analysis'
    if not os.path.isdir(path):
        return rep.add(False, 'Analysis share',
                       '%s is not mounted — the client folders live here' % path,
                       fix='In Finder: Go → Connect to Server → '
                           'smb://192.168.62.170/Analysis')
    # Mounted is not the same as writable, and a read-only mount fails later,
    # confusingly, at the moment of filing rather than here.
    probe = os.path.join(path, '.fq_write_test')
    try:
        with open(probe, 'w') as fh:
            fh.write('x')
    except Exception as e:
        return rep.add(False, 'Analysis share',
                       '%s is mounted but cannot be written to (%s)'
                       % (path, type(e).__name__),
                       fix='Check with Austin that your account has write access.',
                       fatal=False)
    # Writing is the check. Tidying up afterwards is not: some SMB mounts allow
    # create and refuse delete, and treating a failed cleanup as a failed write
    # reports a working share as broken.
    try:
        os.remove(probe)
    except Exception:
        rep.add(True, 'Analysis share',
                '%s mounted and writable (left %s behind — this mount does not '
                'allow deletes, which is worth knowing but does not stop anything)'
                % (path, os.path.basename(probe)))
        return
    rep.add(True, 'Analysis share', '%s mounted and writable' % path)


def check_assets(rep):
    logo = os.path.join(HERE, 'assets', 'fq_logo.png')
    rep.add(os.path.isfile(logo), 'logo',
            'present' if os.path.isfile(logo) else
            'assets/fq_logo.png is missing — the header falls back to plain text',
            fix='git pull', fatal=False)


def run(share=None, port=PORT):
    rep = Report()
    check_python(rep)
    check_libs(rep)
    check_tesseract(rep)
    check_port(rep, port)
    check_share(rep, share)
    check_assets(rep)
    return rep


def main():
    ap = argparse.ArgumentParser(description="Check this Mac can run the FQ Toolkit")
    ap.add_argument('--json', action='store_true', help="machine-readable output")
    ap.add_argument('--quiet', action='store_true', help="print only problems")
    ap.add_argument('--share', default=None, help="path to the Analysis share")
    ap.add_argument('--port', type=int, default=PORT)
    a = ap.parse_args()

    rep = run(a.share, a.port)

    if a.json:
        print(json.dumps({'ok': not rep.broken, 'checks': rep.rows}, indent=1))
        return 1 if rep.broken else 0

    bold = '\033[1m'; off = '\033[0m'
    red = '\033[31m'; green = '\033[32m'; yellow = '\033[33m'
    tty = sys.stdout.isatty()
    if not tty:
        bold = off = red = green = yellow = ''

    print('\n%sFQ Toolkit — checking this Mac%s\n' % (bold, off))
    for r in rep.rows:
        if r['ok'] and a.quiet:
            continue
        if r['ok']:
            mark, colour = '  ok  ', green
        elif r['fatal']:
            mark, colour = ' STOP ', red
        else:
            mark, colour = ' note ', yellow
        print('%s[%s]%s %-14s %s' % (colour, mark, off, r['name'], r['detail']))
        if r['fix'] and not r['ok']:
            print('        fix: %s' % r['fix'])

    print('')
    if rep.broken:
        print('%s%d thing(s) must be fixed before the toolkit will run.%s'
              % (red, len(rep.broken), off))
        print('Run the fixes above, then run this check again.')
    elif rep.warnings:
        print('%sReady to run.%s %d thing(s) worth knowing about, listed above.'
              % (green, off, len(rep.warnings)))
    else:
        print('%sReady to run.%s Everything this needs is installed.' % (green, off))
    print('')
    return 1 if rep.broken else 0


if __name__ == '__main__':
    sys.exit(main())
