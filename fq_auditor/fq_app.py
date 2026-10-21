#!/usr/bin/env python3
"""FQ Toolkit — one window, both tools.

Runs a small web server on this machine only (127.0.0.1) and serves a single
page with two tabs: the Redactor (Cena) and the Auditor. Nothing leaves the Mac;
the server refuses connections that do not come from this machine.

Why a server rather than folding the auditor into the redactor's HTML file:

  * OCR. Browser OCR is measurably worse than native tesseract — it is what made
    a real W-2 unreadable — and the whole pipeline depends on OCR quality.
  * Filing. A browser cannot move a file on disk. It can only hand you a ZIP to
    unpack yourself, which puts the tedious part back on the operator.
  * Verification. The classifier is a couple of thousand lines of Python scored
    against a known answer key. Rewriting it in JavaScript throws that away.

What the operator sees is still one window with both tools in it.

Start it with "Open FQ Toolkit.command", or:  python3 fq_app.py
"""
import os
import re
import io
import sys
import json
import time
import queue
import threading
import subprocess
import webbrowser
import datetime
import http.server
import socketserver
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get('FQ_PORT', '8765'))

# Where the redactor lives. It sits beside the auditor folder in normal use.
REDACTOR_CANDIDATES = [
    os.path.join(HERE, 'Cena.html'),
    os.path.join(HERE, '..', 'Cena_5.html'),
    os.path.join(HERE, '..', 'Cena.html'),
]


def find_redactor():
    for p in REDACTOR_CANDIDATES:
        if os.path.exists(p):
            return os.path.abspath(p)
    return None


# ---------------------------------------------------------------- the root

# The app can only see inside ONE folder, set once and remembered. Without this
# the folder browser could walk the whole disk, which is more access than a
# document tool has any business having — and more than an operator should have
# to trust it not to use.
# Overridable so a second machine — or someone testing — cannot clobber the
# operator's chosen folder. The file lives beside the code, so anyone running
# this app against the same checkout writes to the same place; a stale path from
# another machine then makes every action fail with a message about the folder
# never having been set.
ROOT_FILE = os.environ.get('FQ_ROOT_FILE') or os.path.join(HERE, '.fq_root')


def get_root():
    try:
        with open(ROOT_FILE) as fh:
            p = fh.read().strip()
        if p and os.path.isdir(p):
            return os.path.realpath(p)
        if p:
            # Remembered, but not there now. Usually the share is unmounted, or
            # the path was written by a different machine. Saying "no working
            # folder set" for this sends people hunting for a setting they
            # already made.
            return None
    except OSError:
        pass
    return None


def root_problem():
    """Why there is no usable root, in words the operator can act on."""
    try:
        with open(ROOT_FILE) as fh:
            p = fh.read().strip()
    except OSError:
        p = ''
    if not p:
        return "No working folder chosen yet — press Choose folder."
    if not os.path.isdir(p):
        return ("The working folder is set to %s, which this Mac cannot see. "
                "If that is a server share, check it is mounted; otherwise press "
                "Choose folder to pick it again." % p)
    return "No working folder set."


def choose_folder_dialog(prompt="Choose the folder that holds your client folders"):
    """The standard macOS folder chooser.

    Used instead of an in-app disk browser so nothing is reachable until the
    operator has actually picked something: the app gets one folder, chosen
    through the same dialog any other Mac app would use, and sees nothing until
    then. Returns None if they cancel.
    """
    # Run it inside System Events and activate first, otherwise macOS opens the
    # chooser BEHIND the browser window — the operator sees nothing happen and
    # the app looks broken.
    script = ('tell application "System Events"\n'
              '  activate\n'
              '  set f to choose folder with prompt "%s"\n'
              'end tell\n'
              'POSIX path of f' % prompt.replace('"', "'"))
    try:
        out = subprocess.run(['osascript', '-e', script],
                             capture_output=True, text=True, timeout=300)
    except Exception:
        return None
    path = (out.stdout or '').strip()
    return path if path and os.path.isdir(path) else None


def set_root(path):
    path = os.path.realpath(os.path.abspath(os.path.expanduser(path or '')))
    if not os.path.isdir(path):
        return None
    with open(ROOT_FILE, 'w') as fh:
        fh.write(path)
    return path


def inside_root(path):
    """True only if path is the root or sits beneath it.

    Uses realpath on both sides so a symlink cannot be used to step outside, and
    compares with a trailing separator so "/Clients-old" does not pass as being
    inside "/Clients".
    """
    root = get_root()
    if not root or not path:
        return False
    p = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
    return p == root or p.startswith(root.rstrip(os.sep) + os.sep)


# ---------------------------------------------------------------- job runner

class Job:
    """One audit run, with its output captured line by line for the page.

    The audit is run as a subprocess rather than imported so that a crash in it
    cannot take the window down with it, and so its progress printing arrives
    incrementally instead of all at the end.
    """

    def __init__(self):
        self.lines = []
        self.running = False
        self.returncode = None
        self.folder = None
        self.lock = threading.Lock()

    def start(self, folder, client, greeting, checklist, decisions, redacted,
              file_them=False):
        if self.running:
            return False
        self.lines = []
        self.running = True
        self.returncode = None
        self.folder = folder
        outdir = os.path.join(folder, '_Audit')
        os.makedirs(outdir, exist_ok=True)
        cmd = [sys.executable, os.path.join(HERE, 'audit.py'), folder,
               '--client', client or 'the client',
               '--outdir', outdir,
               '--cache', os.path.join(folder, '.fq_cache')]
        if checklist:
            cmd += ['--checklist', checklist]
        if greeting:
            cmd += ['--greeting', greeting]
        if decisions:
            cmd += ['--decisions', decisions]
        if redacted:
            cmd += ['--redacted-dir', redacted]
        if file_them:
            # Without this the audit still reports what it WOULD file and copies
            # nothing. The flag is the only difference between the preview the
            # operator reads and the copies actually being made.
            cmd += ['--file-them']
        threading.Thread(target=self._run, args=(cmd,), daemon=True).start()
        return True

    def start_cmd(self, cmd, folder):
        """Run any of the toolkit's scripts, streaming its output to the page.

        Used by the Get documents tab. Shares the same log the audit uses, so
        the page only ever has one thing to poll.
        """
        if self.running:
            return False
        self.lines = []
        self.running = True
        self.returncode = None
        self.folder = folder
        threading.Thread(target=self._run, args=(cmd,), daemon=True).start()
        return True

    def _run(self, cmd):
        try:
            p = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in p.stdout:
                line = line.rstrip('\n')
                if 'deprecated' in line.lower():
                    continue                       # library noise, not useful here
                with self.lock:
                    self.lines.append(line)
            p.wait()
            self.returncode = p.returncode
        except Exception as e:
            with self.lock:
                self.lines.append('ERROR: %s' % e)
            self.returncode = 1
        finally:
            self.running = False

    def snapshot(self, since=0):
        with self.lock:
            return self.lines[since:], len(self.lines), self.running, self.returncode


JOB = Job()


# ---------------------------------------------------------------- helpers

STALE_DAYS = 3



# --------------------------------------------------------------------------
# spreadsheets
# --------------------------------------------------------------------------
SHEET_MAX_ROWS = 400
SHEET_MAX_COLS = 30


def _col_letter(i):
    """0 -> A, 26 -> AA. Spreadsheet column names, as the file itself uses."""
    s = ''
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _header_row(rows, look=8):
    """Which row holds the column headings, or None.

    Not row zero. Real client workbooks open with a title ("Debt Schedule
    Template") and often a line of instructions, so treating the first row as
    the header labelled every column with a fragment of a sentence and made the
    grid unreadable. The heading row is the first one that looks like a set of
    short labels: several filled cells, none of them numbers.
    """
    for i, row in enumerate(rows[:look]):
        filled = [c.strip() for c in row if c and c.strip()]
        if len(filled) < 3:
            continue
        if any(re.match(r'^[-+(]?[$]?[\d,]+(\.\d+)?[)%]?$', c) for c in filled):
            continue
        if sum(len(c) for c in filled) / max(1, len(filled)) > 40:
            continue                 # a sentence, not a row of labels
        return i
    return None


def _cell(v):
    """One cell, as the client would recognise it.

    Dates come back as datetimes and str() renders them "2022-08-18 00:00:00",
    which is noise in every column of a debt schedule. Whole floats lose their
    trailing .0 for the same reason.
    """
    if v is None:
        return ''
    if isinstance(v, datetime.datetime):
        return v.strftime('%Y-%m-%d' if (v.hour or v.minute) == 0 else '%Y-%m-%d %H:%M')
    if isinstance(v, datetime.date):
        return v.strftime('%Y-%m-%d')
    if isinstance(v, float) and v == int(v):
        return '%d' % int(v)
    return str(v)


def read_sheets(path, kind=None):
    """A workbook as rows and columns, not as a paragraph.

    The text extractor flattens a spreadsheet into a run of words, which is
    fine for classifying it and useless for reading it: asked whether a debt
    schedule includes personal debt, you need to see which column says what and
    which rows sit under which heading. That is a table or it is nothing.

    Values only — formulas are resolved to their last computed result, which is
    what the client saw when they saved it. Blank leading/trailing columns are
    trimmed so a sheet that starts at column F does not open as a wall of empty
    cells.
    """
    kind = (kind or os.path.splitext(path)[1]).lower()
    out = []

    if kind == '.docx':
        # Word documents that are really tables. Clients answer "total patients,
        # new patients, doctor days" with a single Word table far more often
        # than with a spreadsheet, and flattening it to text produced a wall of
        # pipes nobody could read. Paragraphs outside the tables are kept as
        # single-cell rows so a note above the numbers is not lost.
        import docx as _docx
        d = _docx.Document(path)
        lead = [pp.text.strip() for pp in d.paragraphs if pp.text.strip()]
        for i, tb in enumerate(d.tables):
            rows = []
            for row in tb.rows[:SHEET_MAX_ROWS]:
                rows.append([c.text.replace('\xa0', ' ').strip()
                             for c in row.cells][:SHEET_MAX_COLS])
            while rows and not any(c for c in rows[0]):
                rows.pop(0)
            while rows and not any(c for c in rows[-1]):
                rows.pop()
            if not rows:
                continue
            width = max(len(r) for r in rows)
            rows = [r + [''] * (width - len(r)) for r in rows]
            keep = [j for j in range(width) if any(r[j] for r in rows)]
            rows = [[r[j] for j in keep] for r in rows]
            out.append({'name': ('Table %d' % (i + 1)) if len(d.tables) > 1 else 'Table',
                        'rows': rows,
                        'cols': [_col_letter(j) for j in range(len(keep))],
                        'header': _header_row(rows), 'truncated': False})
        if lead and not out:
            out.append({'name': os.path.basename(path),
                        'rows': [[l] for l in lead], 'cols': ['A'],
                        'header': None, 'truncated': False})
        return out

    if kind in ('.csv', '.tsv', '.txt'):
        import csv as _csv
        delim = '\t' if kind == '.tsv' else ','
        with open(path, newline='', errors='replace') as fh:
            rows = [r[:SHEET_MAX_COLS] for _, r in
                    zip(range(SHEET_MAX_ROWS), _csv.reader(fh, delimiter=delim))]
        return [{'name': os.path.basename(path), 'rows': rows, 'truncated': False}]

    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            rows, n = [], 0
            for row in ws.iter_rows(values_only=True):
                if n >= SHEET_MAX_ROWS:
                    break
                cells = [_cell(v) for v in row[:SHEET_MAX_COLS]]
                rows.append(cells)
                n += 1
            while rows and not any(c.strip() for c in rows[0]):
                rows.pop(0)
            while rows and not any(c.strip() for c in rows[-1]):
                rows.pop()
            if not rows:
                continue
            width = max(len(r) for r in rows)
            rows = [r + [''] * (width - len(r)) for r in rows]

            # Drop empty columns wherever they are, not just at the edges. This
            # workbook carries several blank spacer columns in the middle, and
            # keeping them pushed the real figures off the side of the panel.
            # The original column letters are kept so what is on screen can
            # still be matched against the file itself.
            keep = [i for i in range(width) if any((r[i] or '').strip() for r in rows)]
            rows = [[r[i] for i in keep] for r in rows]
            out.append({'name': ws.title, 'rows': rows,
                        'cols': [_col_letter(i) for i in keep],
                        'header': _header_row(rows),
                        'truncated': n >= SHEET_MAX_ROWS})
    finally:
        wb.close()
    return out


# Sentinel: the file is a readable PDF that we cannot decrypt. Distinct from
# None ("nothing to render here"), because the two need different words on
# screen — one is a missing password, the other is a spreadsheet.
LOCKED = object()


# 2000, not 1400. A bank statement is the densest thing clients send and the
# one most often opened to check an account number; at 1400 the digits were
# at the edge of legible once the panel scaled the image to fit.
def render_first_page(path, max_px=2000):
    """PNG bytes of page one, or of the image itself. None if not viewable."""
    import io as _io
    ext = os.path.splitext(path)[1].lower()
    try:
        import extract as _extract
        kind = _extract.resolve_kind(path)
    except Exception:
        kind = ext

    if kind in ('.png', '.jpg', '.jpeg', '.tif', '.tiff'):
        from PIL import Image
        im = Image.open(path)
        im.thumbnail((max_px, max_px))
        buf = _io.BytesIO()
        im.convert('RGB').save(buf, 'PNG')
        return buf.getvalue()

    if kind == '.pdf':
        import pymupdf
        # Through extract.open_pdf, never pymupdf.open directly. This was the
        # fifth call site to reach for the raw opener and the second to be
        # caught doing it: a document the client sent us the password for
        # rendered as "nothing to show", because only the extraction path knew
        # how to unlock it. LOCKED is returned rather than None so the caller
        # can say which of the two problems this is.
        import extract as _x
        doc = _x.open_pdf(path)
        if doc is None:
            return LOCKED
        try:
            if not len(doc):
                return None
            page = doc[0]
            scale = min(max_px / max(page.rect.width, page.rect.height), 3.0)
            return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale)).tobytes('png')
        finally:
            doc.close()
    return None


def lb_status(folder):
    """How fresh is the document list, and how much is waiting?

    The operator running this has no LaunchBay access and no Claude. Everything
    they can know about what the client has sent comes from the manifest a
    scheduled refresh drops into the client folder. If that refresh stops
    running, the list quietly freezes — and a frozen list is indistinguishable
    from a client who has sent nothing new. So the age is always reported, and
    anything older than a few days is called out rather than left to be noticed.
    """
    import lb_fetch
    folder = os.path.abspath(folder)
    # The manifest belongs to the client folder; the documents land one level in.
    for base in (folder, os.path.dirname(folder)):
        man_path = os.path.join(base, lb_fetch.MANIFEST)
        if os.path.exists(man_path):
            break
    else:
        return {'error': "No document list in this folder yet. Ask Austin to run "
                         "the LaunchBay refresh for this client."}

    man = lb_fetch.load_json(man_path, None) or {}
    state = lb_fetch.load_json(os.path.join(os.path.dirname(man_path),
                                            lb_fetch.FETCHED), {})
    # A document that FAILED to download is not a document still waiting. It
    # will not arrive by pressing Download again, so counting it as outstanding
    # left the Audit button grey for ever with nothing on screen explaining why
    # — which reads as a broken tool rather than as three files the CDN refuses
    # to serve. Counted separately, and said out loud.
    failed = dict(state.get('__failed__') or {})
    waiting = 0
    for f in man.get('files') or []:
        if (f.get('kind') or 'collection') not in lb_fetch.CLIENT_UPLOAD_TYPES:
            continue
        fid = str(f.get('id') or f.get('url') or '')
        if fid in failed or fid in state:
            continue
        waiting += 1

    days = (time.time() - os.path.getmtime(man_path)) / 86400.0
    if days < 1:
        age = 'today'
    elif days < 2:
        age = 'yesterday'
    else:
        age = '%d days ago' % int(days)
    return {'to_fetch': waiting, 'age': age, 'stale': days >= STALE_DAYS,
            'project': man.get('project') or '',
            'failed': [{'name': v.get('name') or '?', 'why': v.get('why') or ''}
                       for v in failed.values()]}


def guess_inputs(folder):
    """Everything the run needs that we can work out for ourselves."""
    out = {'checklist': '', 'decisions': '', 'redacted': '', 'client': '', 'greeting': ''}
    parent = os.path.dirname(folder.rstrip('/')) or '/'

    settings = os.path.join(folder, '.fq_settings')
    if os.path.exists(settings):
        for line in open(settings, errors='ignore'):
            m = re.match(r'(\w+)="(.*)"\s*$', line.strip())
            if m and m.group(1).lower() in out:
                out[m.group(1).lower()] = m.group(2)

    if not out['checklist'] or not os.path.exists(out['checklist']):
        # The reviewed JSON first, found the same way the audit finds it — by
        # walking up from the documents folder. This page used to look only for a
        # PDF named "checklist", so a client whose checklist came from LaunchBay
        # was told "No checklist found — the standard one will be used" while the
        # audit went on to use the right one. The reassurance and the warning were
        # both wrong, which is worse than either.
        try:
            from audit import find_reviewed_checklist
            found = find_reviewed_checklist(folder)
        except Exception:
            found = None
        if found:
            out['checklist'] = found
        else:
            for d in (folder, parent):
                try:
                    hit = [f for f in os.listdir(d)
                           if f.lower().endswith('.pdf') and 'checklist' in f.lower()]
                except OSError:
                    hit = []
                if hit:
                    out['checklist'] = os.path.join(d, hit[0])
                    break

    # _Audit FIRST. That is where the app writes when you press Save decisions, so
    # it is the newest and the one you meant. A stale decisions.json left in the
    # folder root from an earlier manual export would otherwise win and silently
    # ignore what you just chose.
    #
    # ~/Downloads was on this list and had to come off. Decisions are filing
    # instructions for SPECIFIC documents; a file left in Downloads belongs to
    # whichever client was worked on last. On the first server run it quietly
    # applied seven decisions from another client — the log said "carried your
    # decisions from /Users/.../Downloads/decisions.json" and nothing about that
    # made it obvious they were someone else's. Only this client's folder counts.
    for c in (os.path.join(folder, '_Audit', 'decisions.json'),
              os.path.join(folder, 'decisions.json'),
              os.path.join(os.path.dirname(folder.rstrip('/')), '_Audit', 'decisions.json')):
        if os.path.exists(c):
            out['decisions'] = c
            break

    for d in (folder, parent):
        try:
            hit = [f for f in os.listdir(d)
                   if f.lower().startswith('redacted-batch')
                   and os.path.isdir(os.path.join(d, f))]
        except OSError:
            hit = []
        if hit:
            out['redacted'] = os.path.join(d, sorted(hit)[-1])
            break

    # Fall back to LaunchBay's own name for the project rather than the folder
    # name. The folder is whatever someone typed — "Oyler, Brian - TEST",
    # "Spaulding, Kelli due 7:20" — and that ends up in the client's email.
    project = ''
    try:
        import lb_fetch as _lb
        for base in (folder, os.path.dirname(folder.rstrip('/'))):
            man = os.path.join(base, _lb.MANIFEST)
            if os.path.exists(man):
                project = (_lb.load_json(man, {}) or {}).get('project') or ''
                break
    except Exception:
        pass

    if not out['client']:
        out['client'] = project or os.path.basename(folder.rstrip('/'))
    if not out['greeting']:
        out['greeting'] = greeting_from(project)
    return out


def greeting_from(project):
    """"Dr. Brian Oyler" -> "Dr. Oyler". Empty if there is nothing to go on.

    How a client is addressed is the first line they read, so getting it from
    LaunchBay beats getting it from a folder name — and beats leaving the
    operator to type it, which is where "Dear Oyler, Brian - TEST" comes from.
    """
    name = (project or '').strip()
    if not name:
        return ''
    parts = name.split()
    title = parts[0] if parts and parts[0].rstrip('.').lower() in ('dr', 'mr', 'mrs', 'ms') else ''
    last = parts[-1] if parts else ''
    if not last:
        return ''
    return ('%s %s' % (title, last)).strip() if title else last


def save_settings(folder, client, greeting, checklist):
    try:
        with open(os.path.join(folder, '.fq_settings'), 'w') as fh:
            fh.write('CLIENT="%s"\nGREETING="%s"\nCHECKLIST="%s"\n'
                     % (client or '', greeting or '', checklist or ''))
    except OSError:
        pass


# What tells us a folder is a CLIENT rather than a drawer holding clients.
# Any one of these is enough: a folder that has been pulled has the manifest, one
# that has been worked has _Audit, and one the team set up by hand has a
# Documents tree long before this tool sees it.
_CLIENT_MARKS = ('Original_sourcedocs', 'launchbay_manifest.json', '_Audit',
                 'Documents', '3.) Documents')


def is_client_folder(d):
    return any(os.path.exists(os.path.join(d, m)) for m in _CLIENT_MARKS)


def list_dir(path):
    """Folders only, and only inside the root. This is a client picker."""
    root = get_root()
    if not root:
        return {'path': '', 'parent': '', 'entries': [], 'root': None}
    path = os.path.realpath(os.path.abspath(os.path.expanduser(path or root)))
    if not os.path.isdir(path) or not inside_root(path):
        path = root                            # anything outside snaps back to the root
    entries = []
    try:
        for name in sorted(os.listdir(path), key=str.lower):
            if name.startswith('.'):
                continue
            full = os.path.join(path, name)
            if os.path.isdir(full):
                try:
                    n = len([f for f in os.listdir(full) if not f.startswith('.')])
                except OSError:
                    n = 0
                entries.append({'name': name, 'path': full, 'count': n,
                                'client': is_client_folder(full)})
    except OSError:
        pass
    parent = os.path.dirname(path)
    if not inside_root(parent):
        parent = ''                            # already at the root; no way further up
    return {'path': path, 'parent': parent, 'entries': entries,
            'root': get_root(), 'at_root': os.path.realpath(path) == get_root()}


def audit_outputs(folder):
    out = os.path.join(folder, '_Audit')
    if not os.path.isdir(out):
        return []
    return sorted(f for f in os.listdir(out) if not f.startswith('.'))


# ---------------------------------------------------------------- the page

def page_html():
    """The app shell with the firm's mark dropped in.

    Substituted at serve time rather than baked into the template so that a
    missing or unreadable logo file degrades to a plain wordmark instead of
    leaving a literal {{LOGO}} on screen.
    """
    try:
        import render_html
        uri = render_html.logo_data_uri(30)
    except Exception:
        uri = None
    tag = ('<img class="logo" src="%s" alt="Four Quadrants"><div class="rule"></div>'
           % uri) if uri else ''
    return PAGE.replace('{{LOGO}}', tag)


PAGE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FQ Toolkit</title>
<style>
:root{
  --fq-orange:#F08418; --fq-orange-dk:#CE6E0D; --fq-slate:#607884;
  --fq-navy:#16324F;   --fq-navy-lt:#22456A;   --fq-baby:#A9CFE5;
  --fq-baby-pale:#EAF3F9;
}
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
     background:#F7F6F3;color:#1B2A41;height:100vh;display:flex;flex-direction:column}
header{background:linear-gradient(180deg,var(--fq-navy) 0%,var(--fq-navy-lt) 100%);
       color:#fff;padding:0 20px;display:flex;align-items:center;gap:18px;flex:0 0 58px}
header img.logo{height:30px;width:auto;display:block;flex-shrink:0}
header .rule{width:1px;height:26px;background:rgba(169,207,229,.35);flex-shrink:0}
header h1{font-size:16px;margin:0;font-weight:600;letter-spacing:.2px}
nav{display:flex;gap:4px;margin-left:8px}
nav button{background:transparent;border:0;color:#cbd5e1;font:inherit;font-size:14px;
     padding:8px 15px;border-radius:8px;cursor:pointer}
nav button:hover{background:#2A4C74;color:#fff}
nav button.on{background:var(--fq-orange);color:#fff;font-weight:600}
.tag{margin-left:auto;font-size:12px;opacity:.75}
main{flex:1;overflow:hidden;position:relative}
.pane{position:absolute;inset:0;overflow:auto;display:none}
.pane.on{display:block}
/* The review pane is the one pane with furniture below the frame, so it lays
   itself out as a column: frame takes the room, bar keeps its place at the
   bottom instead of scrolling away. */
#pane-review.on{display:flex;flex-direction:column;overflow:hidden}
#pane-review iframe{flex:1 1 auto;height:auto;min-height:0}
iframe{width:100%;height:100%;border:0;background:#fff}
.wrap{max-width:900px;margin:0 auto;padding:26px 24px 60px}
h2{font-size:17px;margin:0 0 4px}
.sub{color:#6C7480;font-size:13.5px;margin:0 0 18px}
.card{background:#fff;border:1px solid #E4E0D8;border-radius:10px;padding:18px 20px;margin-bottom:16px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
label{font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:#6C7480;
      display:block;margin-bottom:4px}
input[type=text]{font:inherit;font-size:14px;padding:9px 11px;border:1px solid #D8D4CA;
      border-radius:8px;width:100%;background:#fff}
button.primary{background:#E8792B;color:#fff;border:0;font:inherit;font-size:15px;font-weight:600;
      padding:11px 22px;border-radius:9px;cursor:pointer}
button.primary:disabled{opacity:.5;cursor:default}
button.ghost{background:#fff;border:1px solid #D8D4CA;font:inherit;font-size:13px;
      padding:7px 13px;border-radius:8px;cursor:pointer}
.crumb{font:12.5px ui-monospace,Menlo,monospace;color:#5A6270;background:#F2F0EB;
      padding:7px 10px;border-radius:7px;word-break:break-all;margin-bottom:10px}
.folders{max-height:260px;overflow:auto;border:1px solid #EFEBE3;border-radius:8px}
.folders .clientrow{background:var(--fq-baby-pale);font-weight:600;color:var(--fq-navy)}
.folders .clientrow:hover{background:var(--fq-baby)}
.folders .clientrow.picked{background:var(--fq-baby);box-shadow:inset 3px 0 0 var(--fq-orange)}
#golog{max-height:240px;overflow:auto}
.rootchange summary{font-size:12.5px;color:#8A9099;cursor:pointer}
.rootchange{margin-top:8px}
.folders div{padding:8px 11px;border-bottom:1px solid #F4F1EB;cursor:pointer;font-size:14px;
      display:flex;justify-content:space-between}
.folders div:last-child{border-bottom:0}
.folders div:hover{background:#FFF6EE}
.folders .n{color:#9aa2ad;font-size:12px}
.found{font-size:13px;color:#1E6B38;background:#EAF3EC;border:1px solid #BEDCC6;
      border-radius:8px;padding:9px 12px;margin-top:10px}
.miss{color:#8A5218;background:#FFF3E0;border-color:#F0D9B5}
pre.log{background:#141C28;color:#cfe3ff;border-radius:9px;padding:14px;font:12.5px/1.6 ui-monospace,Menlo,monospace;
      white-space:pre-wrap;max-height:320px;overflow:auto;margin:0}
.step{display:flex;gap:11px;align-items:flex-start;margin:9px 0;font-size:14px}
.step b{background:var(--fq-slate);color:#fff;width:21px;height:21px;border-radius:50%;
      display:flex;align-items:center;justify-content:center;font-size:12px;flex:0 0 21px}
/* The filing bar used to sit above the review, which put the irreversible
   button in the path of someone still reading. It now sits under the review,
   right-aligned — you reach it by finishing. */
#filebar{display:flex;gap:14px;align-items:center;justify-content:flex-end;
      padding:12px 18px;border-top:1px solid #E3E7EC;background:#fff;flex-wrap:wrap}
#filebar .sub{margin:0;text-align:right;order:-1}
/* The Audit button earns its colour. Green means every document LaunchBay
   lists is already on disk, so there is nothing left to fetch and moving on
   costs you nothing. It stays neutral while anything is outstanding — and also
   when the list is stale, because "nothing new" from a list that stopped
   refreshing looks identical to a client who has sent nothing, and that is
   exactly the case where a green light would be a lie. */
#skipget.ready{background:#1E8449;border-color:#1E8449;color:#fff;font-weight:600}
#skipget.ready:hover{background:#186B3A}
#skipget .tick{margin-right:6px}
/* One row per output: the tick, the name, and what the file actually is.
   The third part matters more than it looks, because "Assumptions" means
   nothing to somebody in their first week. */
label.ck{display:flex;align-items:baseline;gap:8px;padding:7px 2px;
  border-bottom:1px solid #F0EDE6;cursor:pointer}
label.ck:last-child{border-bottom:none}
label.ck b{font-size:13px;color:#16324F;font-weight:600}
label.ck span{font-size:11.5px;color:#8A9099}
#buildmade{flex-wrap:wrap;gap:6px}
/* The Consult plan card: the few choices the advisor still makes, laid over
   what the documents already work out. A placeholder is the worked-out
   figure; typing over it is the override. */
.plan .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px 14px}
.plan .grid input,.plan table input{width:100%}
.plan table{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
.plan th{font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:#6C7480;
  text-align:right;padding:6px 4px;border-bottom:1px solid #E4E0D8}
.plan th:first-child,.plan td:first-child{text-align:left}
.plan td{padding:4px;border-bottom:1px solid #F2EFE9;vertical-align:top}
.plan td input{text-align:right;padding:6px 7px;font-size:13px}
.plan td:first-child input{text-align:left}
.plan .basis{font-size:11px;color:#9AA0A8;margin-top:2px}
.plan .x{background:none;border:0;color:#B0B5BC;cursor:pointer;font-size:15px}
.plan .sum{display:flex;gap:22px;flex-wrap:wrap;background:#F6F4EF;border-radius:8px;
  padding:12px 14px;margin:14px 0 4px}
.plan .sum div{font-size:12px;color:#6C7480}
.plan .sum b{display:block;font-size:18px;color:#16324F}
.plan h3{font-size:13px;margin:18px 0 6px;color:#16324F}
.plan .hint{font-size:11.5px;color:#8A9099;margin-top:3px}
.hide{display:none}
</style></head><body>

<header>
  {{LOGO}}
  <h1>FQ Toolkit</h1>
  <nav>
    <button id="tab-get" class="on">1 &nbsp;Download Files</button>
    <button id="tab-review">3 &nbsp;Review</button>
    <button id="tab-build">5 &nbsp;Build Outputs</button>
    <button id="tab-redact">4 &nbsp;Redact</button>
  </nav>
  <span class="tag">running on this Mac only &middot; nothing is uploaded</span>
</header>

<main>
  <div class="pane" id="pane-redact">
    <iframe id="redactframe" src="/redactor"></iframe>
  </div>

  <div class="pane on" id="pane-get"><div class="wrap">
    <h2>Choose a client</h2>
    <p class="sub">Click a client and the whole job runs: anything they have
       uploaded is downloaded, the documents are read, and the review opens with
       what needs you.</p>

    <div class="card" id="pickcard">
      <div class="crumb" id="crumb">…</div>
      <div class="folders" id="folders"></div>
      <div class="row" style="margin-top:10px">
        <button class="ghost" id="up">↑ Up one level</button>
        <button class="ghost" id="home">Back to top</button>
        <span style="flex:1"></span>
        <button class="primary" id="go" disabled>Pick a client first</button>
      </div>
    </div>

    <!-- The working folder is set once and then left alone. It used to be a
         primary button at the top of the page, which made "choose a different
         folder" look like the first step of the job rather than something you
         do about once a year. It is now a line of text with a quiet way back. -->
    <div class="card hide" id="gocard">
      <div class="row" style="gap:18px">
        <div style="flex:1;min-width:200px">
          <label>Client name</label>
          <input type="text" id="client" placeholder="filled in from LaunchBay">
        </div>
        <div style="flex:1;min-width:200px">
          <label>Email greeting</label>
          <input type="text" id="greeting" placeholder="Dr. Lastname">
        </div>
      </div>
      <div id="foldernow" class="found" style="margin-top:10px">No client chosen yet.</div>
      <div id="found"></div>
      <label style="margin-top:12px">Progress</label>
      <pre class="log" id="golog"></pre>
      <div class="row" style="margin-top:10px">
        <button class="ghost" id="openfolder">Show the files in Finder</button>
      </div>
    </div>

    <div class="card" id="rootcard">
      <label>Working folder</label>
      <div id="rootnow" class="found hide"></div>
      <details class="rootchange">
        <summary>Change it</summary>
        <p class="sub" style="margin:8px 0 10px">The app can see inside this folder
           and nothing else. Every action is checked against it. Changing it is
           rarely needed — it should point at Prospects.</p>
        <div class="row">
          <button class="ghost" id="pickroot">Choose a different folder…</button>
          <span class="sub" id="roothint" style="margin:0">Opens the normal Mac folder chooser.</span>
        </div>
      </details>
    </div>

    <div class="card hide" id="lbcard">
      <label>Documents from the client</label>
      <div id="lbstatus" class="found">Checking…</div>
      <div class="row" style="margin-top:12px">
        <button class="ghost" id="getdocs">Check for new uploads</button>
        <button class="ghost" id="skipget">Re-read the documents</button>
      </div>
      <pre class="log hide" id="lblog" style="margin-top:12px"></pre>
    </div>
  </div></div>

  <div class="pane" id="pane-review">
    <iframe id="reviewframe" src="about:blank"></iframe>
    <div id="filebar">
      <span class="sub" id="filestatus" style="margin:0">Copies every document into
        Personal and Business. Originals are never moved.</span>
      <button class="primary" id="filethem">Build File Tree</button>
    </div>
  </div>

  <!-- The step that was missing. Everything the toolkit produces was a
       command line away, which meant one person could run it. Four tick
       boxes and a button is the whole answer to "what do I click". -->
  <div class="pane" id="pane-build"><div class="wrap">
    <h2>Build the outputs</h2>
    <p class="sub">Runs on the documents already read for this client. The
       initial notes workbook is the one the team opens first; the rest are
       built from the same reading, so they cannot disagree with it.</p>

    <div class="card plan" id="plancard">
      <div class="row">
        <div style="flex:1"><b style="color:#16324F">Consult plan</b>
          <div class="sub" style="margin:2px 0 0">What goes into the deck. Every
            figure is worked out from the documents; fill a box only to change it.</div></div>
        <button class="ghost" id="planload" disabled>Work out the plan</button>
      </div>
      <div id="planbody" class="hide"></div>
    </div>

    <div class="card">
      <div class="crumb" id="buildwho">No client chosen yet</div>
      <label style="margin-top:10px">What to build</label>
      <div id="buildwhat">
        <label class="ck"><input type="checkbox" value="workbook" checked>
          <b>Initial notes workbook</b>
          <span>.xlsx, every fact with the document it came from</span></label>
        <label class="ck"><input type="checkbox" value="cashflow" checked>
          <b>Cash flow workbook</b>
          <span>.numbers, on the firm template, with the adjustments block</span></label>
        <label class="ck"><input type="checkbox" value="summary" checked>
          <b>Prospect Summary</b>
          <span>the two-page internal page, with risk flags</span></label>
        <label class="ck"><input type="checkbox" value="assumptions" checked>
          <b>Assumptions</b>
          <span>the plan PDF, printing what is still needed</span></label>
        <label class="ck"><input type="checkbox" value="deck" checked>
          <b>Consultation deck</b>
          <span>.pptx (opens in Keynote), with what the advisor still has to decide</span></label>
      </div>
      <div class="row" style="margin-top:12px">
        <span class="sub" style="margin:0;flex:1">About two minutes
          for all five.</span>
        <button class="primary" id="buildgo" disabled>Pick a client first</button>
      </div>
      <pre class="log hide" id="buildlog" style="margin-top:12px"></pre>
      <div id="buildmade" class="row hide" style="margin-top:10px"></div>
    </div>
  </div></div>
</main>

<script>
var CUR = null, FOLDER = null, since = 0, poll = null;

function show(name){
  ['get','redact','review','build'].forEach(function(n){
    document.getElementById('pane-'+n).classList.toggle('on', n===name);
    document.getElementById('tab-'+n).classList.toggle('on', n===name);
  });
  if(name==='review' && FOLDER){
    // Always reload. Relying on src==='about:blank' to decide meant a page built
    // before the last run could stay on screen, which looks exactly like
    // decisions having been ignored.
    var f=document.getElementById('reviewframe');
    f.src='/review?folder='+encodeURIComponent(FOLDER)+'&t='+Date.now();
  }
}
document.getElementById('tab-get').onclick=function(){show('get');};
document.getElementById('tab-redact').onclick=function(){show('redact');};
document.getElementById('tab-build').onclick=function(){show('build');};

// --- Build outputs ----------------------------------------------------
// The same log the audit and the LaunchBay fetch use, because the page
// only ever has one job running and one thing to poll.
var BPOLL=null;
function buildReady(){
  var b=document.getElementById('buildgo');
  b.disabled = !FOLDER;
  b.textContent = FOLDER ? 'Build them' : 'Pick a client first';
  document.getElementById('buildwho').textContent =
    FOLDER ? FOLDER.split('/').pop() : 'No client chosen yet';
}
document.getElementById('buildgo').onclick=function(){
  if(!FOLDER) return;
  var want=[];
  document.querySelectorAll('#buildwhat input:checked').forEach(function(i){
    want.push(i.value);
  });
  if(!want.length) return;
  var log=document.getElementById('buildlog');
  var made=document.getElementById('buildmade');
  log.classList.remove('hide'); log.textContent='';
  made.classList.add('hide'); made.innerHTML='';
  this.disabled=true; this.textContent='Building…';
  fetch('/api/build',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({folder:FOLDER, what:want.join(',')})})
    .then(function(r){return r.json();})
    .then(function(j){
      if(j.error){ log.textContent=j.error; buildReady(); return; }
      var at=0;
      BPOLL=setInterval(function(){
        fetch('/api/log?since='+at).then(function(r){return r.json();})
          .then(function(s){
            at=s.total;
            if(s.lines.length){
              log.textContent += s.lines.join('\n')+'\n';
              log.scrollTop=log.scrollHeight;
            }
            if(!s.running){
              clearInterval(BPOLL); BPOLL=null;
              buildReady();
              // Each output becomes a button that opens it in whatever
              // the Mac uses for that file. A path in a log is not a
              // deliverable; a thing you can click is.
              var paths=log.textContent.split('\n')
                .filter(function(l){return l.indexOf('OUTPUT\t')===0;})
                .map(function(l){return l.slice(7);});
              if(paths.length){
                made.classList.remove('hide');
                paths.forEach(function(p){
                  var b=document.createElement('button');
                  b.className='ghost';
                  b.textContent='Open '+p.split('/').pop();
                  b.onclick=function(){
                    fetch('/api/openfile',{method:'POST',
                      headers:{'Content-Type':'application/json'},
                      body:JSON.stringify({path:p, folder:FOLDER})});
                  };
                  made.appendChild(b);
                });
              }
            }
          });
      }, 700);
    });
};
document.getElementById('skipget').onclick=function(){
  if(PICKED) startClient(PICKED.path, PICKED.name);
};

// --- Consult plan -----------------------------------------------------
// One card, three parts: the basics, the table the savings schedule is built
// from, and the client's concerns. Nothing here is required: an empty box
// means "use the worked-out figure", which is shown as the placeholder.
var PLAN=null;
function money(v){ return (v===null||v===undefined||v==='')?'':
  '$'+Math.round(v).toLocaleString('en-US'); }
function numIn(v){ if(v===null||v===undefined) return ''; var s=String(v).replace(/[$,\s]/g,'');
  if(s==='') return ''; var n=parseFloat(s); return isNaN(n)?'':n; }
function esc(s){ return String(s===null||s===undefined?'':s).replace(/[&<>"]/g,
  function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
function planReady(){
  var b=document.getElementById('planload');
  b.disabled=!FOLDER;
  document.getElementById('planbody').classList.add('hide');
  PLAN=null;
}
function field(id,label,val,ph,hint){
  return '<div><label>'+label+'</label><input type="text" id="'+id+'" value="'+esc(val)+
    '" placeholder="'+esc(ph)+'">'+(hint?'<div class="hint">'+hint+'</div>':'')+'</div>';
}
function gainRow(g){
  var inv=g.invested||['','',''];
  return '<tr><td><input type="text" class="g-label" value="'+esc(g.label)+'">'+
    (g.basis?'<div class="basis">'+esc(g.basis)+'</div>':'')+
    '<input type="hidden" class="g-kind" value="'+esc(g.kind||'cash')+'"></td>'+
    '<td><input type="text" class="g-gain" value="'+esc(money(g.gain))+'"></td>'+
    [0,1,2].map(function(i){return '<td><input type="text" class="g-y'+i+'" value="'+
      esc(money(inv[i]))+'"></td>';}).join('')+
    '<td><button class="x" title="Remove">&times;</button></td></tr>';
}
function renderPlan(d){
  PLAN=d; var e=d.entry||{};
  var body=document.getElementById('planbody');
  var pct=function(v){return (v===null||v===undefined)?'':(v*100).toFixed(1)+'%';};
  var h='';
  h+='<div class="sum">'+
    '<div>Retirement income<b>'+(d.income?money(d.income)+'/yr':'—')+'</b>'+
      (d.income_derived?'what the schedule pays to 90':'as entered')+'</div>'+
    '<div>Wealth at retirement<b>'+(d.fq_wealth?money(d.fq_wealth):'—')+'</b>'+
      (d.current_wealth?'against '+money(d.current_wealth)+' today':'')+'</div>'+
    '<div>Sale, net<b>'+(d.sale_net?money(d.sale_net):'—')+'</b>'+
      (d.retire_year?'in '+d.retire_year:'')+'</div>'+
    '<div>Saved, years 1–3<b>'+(d.schedule||[]).map(function(s){return money(s[1]);}).join(' / ')+'</b></div>'+
    '</div>';
  if(d.need && d.need.length) h+='<div class="found miss">Still needed before the '+
    'projection runs: '+d.need.join(', ')+'.</div>';
  h+='<h3>Basics</h3><div class="grid">'+
    field('p-date','Consult date',e.consult_date||'','YYYY-MM-DD')+
    field('p-save','Current savings / yr',e.current_savings?money(e.current_savings):'',
      d.current_savings?money(d.current_savings):'401(k) + match + other','Today’s, all accounts')+
    field('p-bldg','Building value',e.building_value?money(e.building_value):'',
      d.owns_building?'owns it: enter a value':'rents (IC form)',
      d.owns_building?'Included in the sale':'Leave empty if they rent')+
    field('p-age','Retirement age',e.retire_age||'',d.retire_age||'from the IC form')+
    field('p-bank','Ideal practice bank balance',e.ideal_bank_balance?money(e.ideal_bank_balance):'',
      money(d.ideal_balance),'One month of overhead')+
    field('p-oh','Overhead goal',e.target_overhead?pct(e.target_overhead):'',
      d.overhead_goal?pct(d.overhead_goal):'50.0%','Today '+pct(d.overhead))+
    field('p-income','Retirement income',e.target_income?money(e.target_income):'',
      d.income?money(d.income)+' (worked out)':'worked out','Leave empty to use what the plan pays')+
    field('p-salenet','Sale, net',e.sale_net?money(e.sale_net):'',money(d.sale_net),
      'Practice'+(d.building?' and building':'')+' at retirement, after tax')+
    field('p-start','Investable today',e.start_portfolio?money(e.start_portfolio):'',
      money(d.start),'From the Assumptions')+
    '</div>';
  h+='<h3>Where the savings come from</h3>'+
    '<table id="p-gains"><tr><th>Source</th><th>A year</th><th>Year 1</th><th>Year 2</th>'+
    '<th>Year 3</th><th></th></tr>'+(d.gains||[]).map(gainRow).join('')+'</table>'+
    '<div class="row" style="margin-top:8px"><button class="ghost" id="p-add">Add a source</button>'+
    '<span class="hint">Invested amounts are proposed on the firm’s ramp. One-time items (**) count in year 1 only.</span></div>';
  var con=e.concerns||[];
  h+='<h3>Biggest concerns</h3>';
  for(var i=0;i<5;i++){
    var c=con[i]||['',''];
    h+='<div class="row" style="margin-bottom:6px"><input type="text" class="c-head" style="flex:1" '+
      'placeholder="Heading" value="'+esc(c[0])+'"><input type="text" class="c-body" style="flex:2" '+
      'placeholder="In the client’s words" value="'+esc(c[1])+'"></div>';
  }
  h+='<div class="row" style="margin-top:14px"><span class="sub" id="p-msg" style="margin:0;flex:1"></span>'+
    '<button class="primary" id="p-save-btn">Save the plan</button></div>';
  body.innerHTML=h; body.classList.remove('hide');
  body.querySelectorAll('.x').forEach(function(b){b.onclick=function(){
    this.closest('tr').remove();};});
  document.getElementById('p-add').onclick=function(){
    var t=document.getElementById('p-gains');
    t.insertAdjacentHTML('beforeend',gainRow({label:'',kind:'cash',invested:['','','']}));
    var x=t.querySelectorAll('.x'); x[x.length-1].onclick=function(){this.closest('tr').remove();};
  };
  document.getElementById('p-save-btn').onclick=savePlan;
}
function loadPlan(){
  var b=document.getElementById('planload');
  b.disabled=true; b.textContent='Working it out… (about a minute)';
  fetch('/api/plan?folder='+encodeURIComponent(FOLDER))
    .then(function(r){return r.json();})
    .then(function(d){
      b.disabled=false; b.textContent='Work it out again';
      if(d.error){ var bd=document.getElementById('planbody');
        bd.innerHTML='<div class="found miss">'+esc(d.error)+'</div>'; bd.classList.remove('hide'); return; }
      renderPlan(d);
    });
}
function savePlan(){
  var v=function(id){return document.getElementById(id).value.trim();};
  var pc=function(s){ s=String(s).replace('%','').trim(); if(!s) return ''; var n=parseFloat(s);
    return isNaN(n)?'':(n>1?n/100:n); };
  var rows=[];
  document.querySelectorAll('#p-gains tr').forEach(function(tr,i){
    if(i===0) return;
    var q=function(c){return tr.querySelector(c).value;};
    var label=q('.g-label').trim(); if(!label) return;
    rows.push({label:label, kind:q('.g-kind'), gain:numIn(q('.g-gain')),
      invested:[numIn(q('.g-y0'))||0,numIn(q('.g-y1'))||0,numIn(q('.g-y2'))||0]});
  });
  // The table is saved only when it differs from the proposal, so a client
  // whose figures change still gets a fresh proposal next time.
  var proposed=JSON.stringify((PLAN.gains||[]).map(function(g){
    return [g.label,Math.round(g.gain||0)].concat(g.invested.map(function(x){return Math.round(x||0);}));}));
  var mine=JSON.stringify(rows.map(function(g){
    return [g.label,Math.round(g.gain||0)].concat(g.invested.map(function(x){return Math.round(x||0);}));}));
  var con=[];
  var hs=document.querySelectorAll('.c-head'), bs=document.querySelectorAll('.c-body');
  for(var i=0;i<hs.length;i++){ if(hs[i].value.trim()) con.push([hs[i].value.trim(), bs[i].value.trim()]); }
  var entry={
    consult_date:v('p-date'), current_savings:numIn(v('p-save')),
    building_value:numIn(v('p-bldg')), retire_age:numIn(v('p-age')),
    ideal_bank_balance:numIn(v('p-bank')), target_overhead:pc(v('p-oh')),
    target_income:numIn(v('p-income')), sale_net:numIn(v('p-salenet')),
    start_portfolio:numIn(v('p-start')),
    gains_table:(mine!==proposed)?rows:'', concerns:con.length?con:''
  };
  var m=document.getElementById('p-msg'); m.textContent='Saving…';
  fetch('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({folder:FOLDER, entry:entry})})
    .then(function(r){return r.json();})
    .then(function(j){ m.textContent=j.saved?'Saved. Working the plan out again…':'Not saved.';
      if(j.saved) loadPlan(); });
}
document.getElementById('planload').onclick=loadPlan;

// --- Get documents ----------------------------------------------------
// Reads the manifest the scheduled refresh left in the client folder. There is
// no LaunchBay login here: every upload carries a direct download link, so the
// only thing this needs is the list.
// Everything is here / something is still missing, said in colour as well as
// words. The coworker running this does not know the pipeline; the point is
// that "am I allowed to move on yet" should be answerable at a glance.
function setReady(ok){
  var b=document.getElementById('skipget');
  if(!b) return;
  b.classList.toggle('ready', !!ok);
  b.innerHTML = ok ? '<span class="tick">\u2713</span>Audit' : 'Audit';
  b.title = ok ? 'Every document on the list is already downloaded — go ahead.'
               : 'Some documents may still be missing. You can still audit what is here.';
}

function lbRefresh(){
  if(!FOLDER) return;
  document.getElementById('lbcard').classList.remove('hide');
  var el=document.getElementById('lbstatus');
  el.textContent='Checking…';
  fetch('/api/lbstatus?folder='+encodeURIComponent(FOLDER))
    .then(function(r){return r.json();})
    .then(function(d){
      var b=document.getElementById('getdocs');
      if(d.error){ el.textContent=d.error; b.disabled=true; setReady(false); return; }
      // Always clickable, even with nothing waiting. Greying it out left the
      // operator no way to re-check or to finish a half-done download, and a
      // dead button reads as a broken one. Pressing it when nothing is new
      // costs a second and prints 'nothing new', which is a useful answer.
      b.disabled = false;
      var lines=[];
      // Name the client from the manifest, not from the folder name. Folders get
      // renamed and mistyped; this is what LaunchBay actually calls the project,
      // so it is the check that you are about to download the right person's
      // documents into the right place.
      if(d.project) lines.push(d.project);
      lines.push(d.to_fetch ? (d.to_fetch+' new document(s) waiting to download.')
                            : 'Nothing new — every document on the list is already here.');
      lines.push('The list was refreshed '+d.age+'.');
      // Said plainly, because a stale list looks exactly like a client who has
      // sent nothing. If the refresh stopped running, this is the only clue.
      if(d.stale) lines.push('WARNING: that is old. Ask Austin whether the daily '
                             +'refresh is still running before trusting "nothing new".');
      // Named, because "3 documents are missing" with no names sends someone
      // hunting through the folder for which three.
      if(d.failed && d.failed.length){
        lines.push('');
        lines.push(d.failed.length + ' document(s) could not be downloaded. '
                   + 'Pressing Download again will not help — ask Austin:');
        d.failed.forEach(function(f){ lines.push('   - ' + f.name); });
      }
      el.textContent=lines.join('\n');
      setReady(!d.to_fetch && !d.stale);
    })
    .catch(function(){ el.textContent='Could not read the list.'; setReady(false); });
}
document.getElementById('getdocs').onclick=function(){
  var b=document.getElementById('getdocs'); b.disabled=true;
  var log=document.getElementById('lblog'); log.classList.remove('hide');
  log.textContent=''; since=0;
  fetch('/api/lbfetch',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({folder:FOLDER})})
    .then(function(){ poll=setInterval(lbTick,700); });
};
function lbTick(){
  fetch('/api/log?since='+since).then(function(r){return r.json();}).then(function(d){
    since=d.total;
    if(d.lines.length){
      var el=document.getElementById('lblog');
      el.textContent += d.lines.join('\n')+'\n';
      el.scrollTop=el.scrollHeight;
    }
    if(!d.running){ clearInterval(poll); lbRefresh(); }
  });
}
document.getElementById('tab-review').onclick=function(){show('review');};

function refreshRoot(){
  return fetch('/api/root').then(function(r){return r.json();}).then(function(d){
    var box=document.getElementById('rootnow');
    var pick=document.getElementById('pickcard');
    if(d.root){
      box.textContent='Access limited to: '+d.root;
      document.getElementById('pickroot').textContent='Choose a different folder…';
      box.classList.remove('hide');
      pick.classList.remove('hide');
    }else{
      box.classList.add('hide');
      pick.classList.add('hide');
    }
    return d.root;
  });
}
document.getElementById('pickroot').onclick=function(){
  var b=this, hint=document.getElementById('roothint');
  b.disabled=true; hint.textContent='Waiting for you to choose…';
  fetch('/api/pickroot',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})
   .then(function(r){return r.json();})
   .then(function(d){
     b.disabled=false;
     if(d.cancelled){ hint.textContent='Nothing chosen — the app still has no access.'; return; }
     hint.textContent='';
     refreshRoot().then(function(){ browse(''); });
   })
   .catch(function(){ b.disabled=false; hint.textContent='Could not open the chooser.'; });
};

function browse(path){
  fetch('/api/ls?path='+encodeURIComponent(path||'')).then(function(r){return r.json();}).then(function(d){
    if(!d.root){ return; }
    CUR=d.path;
    document.getElementById('crumb').textContent=d.path;
    // No way above the working folder, so the control is hidden there rather
    // than sitting dead.
    document.getElementById('up').style.display = d.at_root ? 'none' : '';
    var box=document.getElementById('folders'); box.innerHTML='';
    if(!d.entries.length){ box.innerHTML='<div><span style="color:#9aa2ad">no folders here</span></div>'; }
    // A drawer opens. A CLIENT starts the job. There used to be one confirm
    // button reading "Use <whatever folder you are standing in>" — which, while
    // browsing 2026, offered to audit the whole year. Clicking a client is now
    // the decision, and nothing else can be selected by accident.
    d.entries.forEach(function(e){
      var row=document.createElement('div');
      row.className = e.client ? 'clientrow' : '';
      row.dataset.path = e.path;
      row.innerHTML='<span>'+(e.client?'':'› ')+e.name+'</span>'
        + '<span class="n">'+(e.client ? 'open this client' : e.count+' items')+'</span>';
      // Selecting and starting are two different things. Firing the whole job
      // on a single click means a mis-click is a five-minute run on the wrong
      // client, and there is no moment to notice before it happens.
      row.onclick=function(){ e.client ? selectClient(e.path, e.name) : browse(e.path); };
      box.appendChild(row);
    });
  });
}
document.getElementById('go').onclick=function(){
  if(PICKED) startClient(PICKED.path, PICKED.name);
};
document.getElementById('up').onclick=function(){ browse(CUR.replace(/\/[^\/]+$/,'')||'/'); };
document.getElementById('home').onclick=function(){ browse(''); };   // '' snaps to the root

var PICKED = null;
function selectClient(path, name){
  PICKED = {path: path, name: name};
  var b = document.getElementById('go');
  b.disabled = false;
  b.textContent = 'Download and audit \u201c' + name + '\u201d';
  document.querySelectorAll('.folders .clientrow').forEach(function(r){
    r.classList.toggle('picked', r.dataset.path === path);
  });
  var crumb = document.getElementById('crumb');
  if(crumb) crumb.textContent = path;
}

// One press, the whole job. It used to be three — Download, Audit, Review —
// each of which could be done out of order, skipped, or pressed twice. They
// are not three decisions; they are one job with three stages, and the operator
// has no useful choice between them.
function startClient(path, name){
  CUR = path;
  FOLDER = path;
  document.getElementById('foldernow').textContent = FOLDER;
  buildReady(); planReady();
  var crumb = document.getElementById('crumb');
  if(crumb) crumb.textContent = path;
  var st = document.getElementById('golog');
  document.getElementById('gocard').classList.remove('hide');
  st.textContent = 'Opening ' + name + '…\n';
  // Read the client's details first, so the audit runs under the right name and
  // we know whether there is a checklist to grade against at all.
  fetch('/api/inspect?folder='+encodeURIComponent(FOLDER))
    .then(function(r){return r.json();}).then(function(d){
      document.getElementById('client').value = d.client || name;
      document.getElementById('greeting').value = d.greeting || '';
      if(!d.checklist){
        st.textContent += '\nNo checklist for this client yet — they have not '
          + 'been pulled from LaunchBay.\nEverything would be graded against '
          + 'another client’s list, so the run has stopped here.\n';
        return;
      }
      st.textContent += 'Downloading anything new…\n';
      goFetch(st);
    });
}
function goFetch(st){
  since = 0;
  fetch('/api/lbfetch',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({folder:FOLDER})})
    .then(function(){ poll=setInterval(function(){ goTick(st, goAudit); }, 700); });
}
function goTick(st, next){
  fetch('/api/log?since='+since).then(function(r){return r.json();}).then(function(d){
    since=d.total;
    if(d.lines.length){ st.textContent += d.lines.join('\n')+'\n'; st.scrollTop=st.scrollHeight; }
    if(!d.running){ clearInterval(poll); next(st); }
  });
}
function goAudit(st){
  st.textContent += '\nReading the documents. The first run on a client takes a '
    + 'few minutes.\n';
  since = 0;
  fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({folder:FOLDER, client:document.getElementById('client').value,
                         greeting:document.getElementById('greeting').value})})
    .then(function(){ poll=setInterval(function(){ goTick(st, goDone); }, 700); });
}
function goDone(st){
  st.textContent += '\nDone. Opening the review.\n';
  lbRefresh();
  show('review');
}


// Filing re-runs the whole audit with --file-them, so the copies are made from a
// plan built seconds ago rather than one that predates the operator's decisions.
// Lives on the Review tab, where you have just looked at what it plans to do.
// It reports into its own status line rather than the audit log, because that
// log is on another tab — hiding the only feedback behind a tab switch made the
// button look broken.
function fileThem(){
  if(!FOLDER){ alert('Choose a client folder on the Get documents tab first.'); return; }
  if(!confirm('Copy these documents into their folders?\n\n'
            + 'Copies only — the originals are not moved or changed.')) return;
  var b=document.getElementById('filethem'); b.disabled=true;
  var st=document.getElementById('filestatus');
  st.textContent='Filing… this re-reads the documents, so it takes a minute.';
  since=0;
  fetch('/api/file',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({folder:FOLDER, client:document.getElementById('client').value,
                         greeting:document.getElementById('greeting').value})})
    .then(function(){ poll=setInterval(fileTick,700); })
    .catch(function(e){ st.textContent='Could not start filing: '+e; b.disabled=false; });
}

function fileTick(){
  fetch('/api/log?since=0').then(function(r){return r.json();}).then(function(d){
    var st=document.getElementById('filestatus');
    // Pull the lines that say what happened out of the run's output, so the
    // answer is on screen without sending anyone to another tab to read a log.
    var said=[];
    d.lines.forEach(function(l){
      if(/document\(s\) filed|skipped|refused|satisfied ·/.test(l)) said.push(l.trim());
    });
    if(said.length) st.textContent=said.join('   ·   ');
    if(!d.running){
      clearInterval(poll);
      document.getElementById('filethem').disabled=false;
      if(!said.length) st.textContent='Finished, but it reported nothing — check the '
                                    + 'Audit & File tab for the full output.';
      var f=document.getElementById('reviewframe');
      f.src='/review?folder='+encodeURIComponent(FOLDER)+'&t='+Date.now();
    }
  });
}
document.getElementById('filethem').onclick=fileThem;
window.showTab=show;   // the review frame calls this

document.getElementById('openfolder').onclick=function(){
  fetch('/api/reveal?folder='+encodeURIComponent(FOLDER));
};

refreshRoot().then(function(root){ if(root){ browse(''); } });
</script></body></html>
"""


# ---------------------------------------------------------------- server


def plan_payload(folder):
    """Everything the Consult plan card shows: what the documents and the
    models work out, and what the advisor has already entered.

    Built by the same code the deck uses (deck_template.figures), so the card
    and the deck cannot disagree.
    """
    import deck_template as _dt
    import plan as _plan
    client = guess_inputs(folder).get('client')
    D = _dt.figures(folder, client)
    p = D.get('proj')

    def num(v):
        return None if v is None else round(float(v), 2)
    rows = []
    for g in D['gains']:
        rows.append({'key': g.get('key'), 'label': g['label'],
                     'gain': num(g['gain']), 'kind': g.get('kind'),
                     'basis': g.get('basis'),
                     'invested': [num(_plan.invested(g, i)) for i in range(3)]})
    lv = D['lever_inputs']
    return {
        'client': client,
        'first': D['first'],
        'entry': D['adv'],
        'age': D['age'], 'retire_age': D['retire_age'],
        'owns_building': D['owns_building'], 'building': D.get('building'),
        'collections': num(D.get('collections')),
        'sale_gross': num(D.get('sale_gross')), 'sale_net': num(D.get('sale')),
        'ideal_balance': D.get('ideal_balance'),
        'overhead': D.get('overhead'),
        'overhead_goal': lv.get('target_overhead'),
        'start': num(D.get('start')), 'spend': num(D.get('spend')),
        'current_savings': D.get('current_savings'),
        'gains': rows,
        'schedule': [[y, num(a)] for y, a in (D.get('schedule') or [])],
        'income': D.get('income'),
        'income_derived': D.get('income_derived'),
        'need': D.get('need_proj'),
        'retire_year': p and p['retire_year'],
        'fq_wealth': num(p and p['fq_at_retirement']),
        'current_wealth': num(p and p['current_at_retirement']),
        'runout_year': p and p['runout_year'],
    }


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass                                   # keep the console clean for the operator

    def _locate(self, path, folder):
        """Find a file whose recorded path came from another machine.

        Documents are keyed by the absolute path seen at audit time. Open the
        same client folder from a different Mac — or after the share remounts
        somewhere else — and that path no longer exists, while the file is
        sitting exactly where it always was.
        """
        if os.path.isfile(path) or not folder:
            return path
        name = os.path.basename(path)
        for cand in (os.path.join(folder, 'Original_sourcedocs', name),
                     os.path.join(folder, name)):
            if os.path.isfile(cand):
                return cand
        return path

    def _send(self, code, body, ctype='application/json'):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _q(self):
        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

    def _guard(self, folder):
        """Refuse anything outside the root. Checked on EVERY endpoint that takes
        a path, not just the browser, so the limit holds even if the page is
        modified or a URL is typed by hand."""
        if not get_root():
            self._send(400, json.dumps({'error': root_problem()}))
            return False
        if not inside_root(folder):
            self._send(403, '{"error":"that folder is outside the working folder"}')
            return False
        return True

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        q = self._q()

        if p == '/':
            return self._send(200, page_html(), 'text/html; charset=utf-8')

        if p == '/redactor':
            rp = find_redactor()
            if not rp:
                return self._send(200, '<body style="font:15px -apple-system;padding:40px">'
                                       '<h3>Redactor not found</h3><p>Put <code>Cena.html</code> '
                                       'next to this folder and reload.</p></body>',
                                  'text/html; charset=utf-8')
            with open(rp, 'rb') as fh:
                return self._send(200, fh.read(), 'text/html; charset=utf-8')

        if p == '/api/plan':
            # The Consult plan card. Slow on first open (the cash flow is read
            # in full), so the page shows that it is working.
            folder = (q.get('folder') or [''])[0]
            if not self._guard(folder):
                return
            try:
                return self._send(200, json.dumps(plan_payload(folder),
                                                  default=str))
            except Exception as e:                        # noqa: BLE001
                return self._send(200, json.dumps(
                    {'error': 'Could not work out the plan: %s' % e}))

        if p == '/api/sheet':
            # Spreadsheets, shown as spreadsheets.
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            path = (q.get('path') or [''])[0]
            folder = (q.get('folder') or [''])[0]
            path = self._locate(path, folder)
            if not self._guard(path):
                return
            if not os.path.isfile(path):
                return self._send(404, '{"error":"no such file"}')
            try:
                import extract as _extract
                sheets = read_sheets(path, _extract.resolve_kind(path))
            except Exception as e:
                return self._send(200, json.dumps({'error': str(e)}))
            if not sheets:
                return self._send(200, json.dumps({'error': 'this workbook has no readable cells'}))
            return self._send(200, json.dumps({'sheets': sheets}))

        if p == '/api/previewtext':
            # For anything with no page to photograph — a spreadsheet, a CSV, a
            # QuickBooks backup. The text was already extracted during the audit,
            # so showing it costs nothing and keeps the operator inside the
            # review instead of launching Numbers.
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            path = (q.get('path') or [''])[0]
            folder = (q.get('folder') or [''])[0]
            if not os.path.isfile(path) and folder:
                name = os.path.basename(path)
                for cand in (os.path.join(folder, 'Original_sourcedocs', name),
                             os.path.join(folder, name)):
                    if os.path.isfile(cand):
                        path = cand
                        break
            if not self._guard(path):
                return
            if not os.path.isfile(path):
                return self._send(404, '{"error":"no such file"}')
            try:
                import extract as _extract
                text = None

                # The cache lives in the CLIENT folder, not beside the documents.
                # Looking only next to the file found nothing, so every PDF fell
                # through to the non-PDF reader — which returns '' for a PDF —
                # and reported "no readable text" for documents full of text.
                here = os.path.dirname(path)
                for cache in (os.path.join(here, '.fq_cache'),
                              os.path.join(os.path.dirname(here), '.fq_cache'),
                              os.path.join(folder, '.fq_cache') if folder else ''):
                    if cache and os.path.isdir(cache):
                        digest = _extract.file_hash(path)
                        txt_p, _ = _extract._cache_paths(cache, digest)
                        if os.path.exists(txt_p):
                            text = open(txt_p, errors='ignore').read()
                            break

                if not (text or '').strip():
                    kind = _extract.resolve_kind(path)
                    if kind == '.pdf':
                        text = _extract.extract_pdf(path)[0]
                    else:
                        text = _extract.extract_other(path, kind)
            except Exception as e:
                return self._send(500, json.dumps({'error': str(e)}))
            text = (text or '').strip()
            if not text:
                text = '(no readable text in this file)'
            return self._send(200, json.dumps({'text': text[:20000]}))

        if p == '/api/preview':
            # First page of a document, rendered on demand as a PNG.
            #
            # Deliberately NOT embedded in the review page: that file gets saved
            # and passed around, and a page carrying images of a client's bank
            # statements is a different kind of object from one carrying a list
            # of filenames. Served live, it is only ever visible to whoever is
            # running the app on this machine.
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            path = (q.get('path') or [''])[0]
            folder = (q.get('folder') or [''])[0]
            if not os.path.isfile(path) and folder:
                name = os.path.basename(path)
                for cand in (os.path.join(folder, 'Original_sourcedocs', name),
                             os.path.join(folder, name)):
                    if os.path.isfile(cand):
                        path = cand
                        break
            if not self._guard(path):
                return
            if not os.path.isfile(path):
                return self._send(404, '{"error":"no such file"}')
            try:
                png = render_first_page(path)
            except Exception as e:
                return self._send(500, json.dumps({'error': str(e)}))
            if png is LOCKED:
                return self._send(423, json.dumps({'error':
                    'This PDF is encrypted and none of the passwords the client sent '
                    'will open it. Ask them for the password, then re-run the audit.',
                    'locked': True, 'final': True}))
            if png is None:
                # Name the file type rather than shrugging. A QuickBooks backup
                # has nothing to render and never will; "nothing to show"
                # reads like a fault in the tool.
                _k = os.path.splitext(path)[1].lower()
                if _k in ('.qbb', '.qbw', '.qbm'):
                    return self._send(415, json.dumps({'error':
                        'QuickBooks backup file. There is no page to show — it has to be '
                        'restored in QuickBooks. The audit has already read what it can '
                        'from the file name and size.', 'final': True}))
                return self._send(415, '{"error":"nothing to show for this file type"}')
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(len(png)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(png)
            return

        if p == '/api/lbstatus':
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            folder = (q.get('folder') or [''])[0]
            if not self._guard(folder):
                return
            return self._send(200, json.dumps(lb_status(folder)))

        if p == '/api/root':
            return self._send(200, json.dumps({'root': get_root()}))

        if p == '/api/ls':
            return self._send(200, json.dumps(list_dir((q.get('path') or [''])[0])))

        if p == '/api/inspect':
            folder = (q.get('folder') or [''])[0]
            if not self._guard(folder):
                return
            info = guess_inputs(folder)
            try:
                info['n_docs'] = len([f for f in os.listdir(folder)
                                      if not f.startswith('.')
                                      and os.path.isfile(os.path.join(folder, f))])
            except OSError:
                info['n_docs'] = 0
            return self._send(200, json.dumps(info))

        if p == '/api/log':
            since = int((q.get('since') or ['0'])[0])
            lines, total, running, rc = JOB.snapshot(since)
            return self._send(200, json.dumps({'lines': lines, 'total': total,
                                               'running': running, 'rc': rc}))

        if p == '/review':
            folder = (q.get('folder') or [''])[0]
            if not self._guard(folder):
                return
            out = os.path.join(folder, '_Audit')
            hit = [f for f in audit_outputs(folder) if f.endswith('Intake Review.html')]
            if not hit:
                return self._send(200, '<body style="font:15px -apple-system;padding:40px">'
                                       '<h3>No review yet</h3><p>Run the audit first.</p></body>',
                                  'text/html; charset=utf-8')
            with open(os.path.join(out, hit[0]), 'rb') as fh:
                html = fh.read().decode('utf-8', 'replace')
            # Swap the page's "download a file, then re-run" step for a direct save
            # back to the server. That round trip was the clunkiest part of the tool.
            # Inject at the LAST </body> only. str.replace hits every occurrence,
            # and the page's own JavaScript builds an HTML document as a string
            # for the writeup download — that string contains "</body>", so the
            # shim was being spliced into the middle of a JS string literal,
            # breaking the whole script block. The symptom was the save button
            # reporting that it could not read the decisions: the script that
            # defines them had never run.
            # The page ships with connect-src 'none' — correct for a file sitting
            # in a folder, since it holds client PII and should not be able to
            # talk to anything. Served here it has to reach ONE place: this
            # server, on this machine, to save the decisions. 'self' allows
            # exactly that and nothing else; every other origin stays refused.
            html = html.replace("connect-src 'none'", "connect-src 'self'", 1)

            # Same reasoning for images. The saved file allows "img-src data:"
            # only — right for a page sitting in a client folder, since it means
            # the page cannot fetch anything. But the document preview is served
            # from this app rather than embedded, precisely SO it is not baked
            # into the file, and that rule blocked it: the browser refused the
            # image and the page fell back to showing text. curl has no CSP,
            # which is why every test passed while the real thing failed.
            html = html.replace("img-src data:", "img-src data: 'self'", 1)

            head, sep, tail = html.rpartition('</body>')
            html = (head + SAVE_SHIM % json.dumps(folder) + sep + tail) if sep \
                else (html + SAVE_SHIM % json.dumps(folder))
            return self._send(200, html, 'text/html; charset=utf-8')

        if p == '/api/reveal':
            folder = (q.get('folder') or [''])[0]
            if not self._guard(folder):
                return
            try:
                subprocess.Popen(['open', os.path.join(folder, '_Audit')])
            except Exception:
                pass
            return self._send(200, '{"ok":true}')

        return self._send(404, '{"error":"not found"}')

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n) if n else b'{}'
        try:
            data = json.loads(raw.decode('utf-8') or '{}')
        except Exception:
            data = {}

        # One endpoint for both, because filing IS an audit run — the documents
        # have to be re-read and re-planned before anything is copied, or the
        # operator could file against a plan made before their last decision.
        if p in ('/api/run', '/api/file'):
            folder = data.get('folder') or ''
            if not self._guard(folder):
                return
            if not os.path.isdir(folder):
                return self._send(400, '{"error":"not a folder"}')
            g = guess_inputs(folder)
            client = data.get('client') or g['client']
            greeting = data.get('greeting') or g['greeting']
            save_settings(folder, client, greeting, g['checklist'])
            JOB.start(folder, client, greeting, g['checklist'], g['decisions'],
                      g['redacted'], file_them=(p == '/api/file'))
            return self._send(200, '{"started":true}')

        if p == '/api/plan':
            # The advisor's choices, kept beside the client's other typed
            # figures (_Audit/plan_inputs.json, key 'deck'). Merged, so a
            # field the card does not show is never wiped.
            folder = data.get('folder') or ''
            if not self._guard(folder):
                return
            import inputs as _inputs
            got = (_inputs.get(folder, 'deck') or {}).get('value') or {}
            for k, v in (data.get('entry') or {}).items():
                if v in (None, '', []):
                    got.pop(k, None)
                else:
                    got[k] = v
            _inputs.put(folder, 'deck', got, by='FQ Toolkit app',
                        note='Entered on the Consult plan card.')
            return self._send(200, '{"saved":true}')

        if p == '/api/build':
            # The outputs, built in one process so the cash flow pass is
            # paid once rather than once per output. Streamed through the
            # same job the audit uses, so the page has one thing to poll.
            folder = data.get('folder') or ''
            if not self._guard(folder):
                return
            if not os.path.isdir(folder):
                return self._send(400, '{"error":"not a folder"}')
            if JOB.running:
                return self._send(200, json.dumps(
                    {'error': 'Something is already running. Wait for it to '
                              'finish, then build.'}))
            client = data.get('client') or guess_inputs(folder)['client']
            cmd = [sys.executable, os.path.join(HERE, 'build_outputs.py'),
                   folder, '--outdir', os.path.join(folder, '_Audit')]
            if client:
                cmd += ['--client', client]
            if data.get('what'):
                cmd += ['--what', data['what']]
            JOB.start_cmd(cmd, folder)
            return self._send(200, '{"started":true}')

        if p == '/api/openfile':
            # Opens a client document in Preview/Excel/whatever, for the review
            # page. Guarded by the same root check as every other path endpoint,
            # so it can only ever open something inside the chosen folder.
            path = data.get('path') or ''
            folder = data.get('folder') or ''

            # The review page stores absolute paths, recorded on whichever
            # machine ran the audit. Open it from a different Mac — or after the
            # client folder has moved — and every one of them is wrong. So the
            # stored path is a hint, not the answer: if it is not there, look for
            # the same filename inside the folder this page belongs to.
            if not os.path.isfile(path) and folder:
                name = os.path.basename(path)
                for cand in (os.path.join(folder, 'Original_sourcedocs', name),
                             os.path.join(folder, name),
                             os.path.join(os.path.dirname(folder.rstrip('/')), name)):
                    if os.path.isfile(cand):
                        path = cand
                        break

            if not self._guard(path):
                return
            if not os.path.isfile(path):
                return self._send(400, json.dumps(
                    {'error': 'Could not find that file. It may have been moved '
                              'or renamed since this page was written — re-run '
                              'the audit.'}))
            try:
                subprocess.Popen(['open', path])
            except Exception as e:
                return self._send(500, json.dumps({'error': str(e)}))
            return self._send(200, '{"opened":true}')

        if p == '/api/lbfetch':
            folder = data.get('folder') or ''
            if not self._guard(folder):
                return
            if not os.path.isdir(folder):
                return self._send(400, '{"error":"not a folder"}')
            JOB.start_cmd([sys.executable, os.path.join(HERE, 'lb_fetch.py'), folder],
                          folder)
            return self._send(200, '{"started":true}')

        if p == '/api/pickroot':
            # The dialog is the ONLY way in. Until it returns a folder the app has
            # no reach at all, which is the point: access is granted by the
            # operator picking, not assumed at startup.
            chosen = choose_folder_dialog()
            if not chosen:
                return self._send(200, json.dumps({'cancelled': True}))
            return self._send(200, json.dumps({'root': set_root(chosen)}))

        if p == '/api/setroot':
            # Settable once from the page, and only to a folder that exists. This
            # is the only endpoint allowed to reach outside the current root.
            newroot = set_root(data.get('path') or '')
            if not newroot:
                return self._send(400, '{"error":"that folder does not exist"}')
            return self._send(200, json.dumps({'root': newroot}))

        if p == '/api/decisions':
            folder = data.get('folder') or ''
            if not self._guard(folder):
                return
            if not os.path.isdir(folder):
                return self._send(400, '{"error":"not a folder"}')
            out = os.path.join(folder, '_Audit')
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, 'decisions.json'), 'w') as fh:
                json.dump(data.get('decisions') or {}, fh, indent=1)
            return self._send(200, '{"saved":true}')

        return self._send(404, '{"error":"not found"}')


# Injected into the review page when it is served through the app. The standalone
# file still works on its own — this only adds a direct save when it is open here.
SAVE_SHIM = r"""
<script>
(function(){
  var FOLDER = %s;
  // Published so the Open buttons can tell the server which client folder
  // this page belongs to, and it can find a file whose recorded absolute
  // path came from another machine.
  window.__FQ_FOLDER__ = FOLDER;

  // Autosave. The page calls this whenever anything changes, debounced, so
  // there is no button to forget and nothing to lose by closing the tab.
  // The old Save button remains below for the standalone file, but when the
  // page is served here it becomes a status line instead.
  window.__FQ_SAVE__ = function(decisions){
    var el = document.getElementById('dlDec');
    if(el){ el.textContent = 'Saving\u2026'; el.className = 'savestate busy'; }
    fetch('/api/decisions', {method:'POST', headers:{'Content-Type':'application/json'},
                             body: JSON.stringify({folder: FOLDER, decisions: decisions})})
      .then(function(r){ if(!r.ok) throw new Error('server said ' + r.status); })
      .then(function(){
        if(el){ el.textContent = 'Saved \u2713'; el.className = 'savestate'; }
      })
      .catch(function(e){
        if(el){ el.textContent = 'NOT SAVED \u2014 ' + (e && e.message || e);
                el.className = 'savestate bad'; }
        if(window.console) console.error('[fq] autosave failed:', e);
      });
  };

  var btn = document.getElementById('dlDec');
  if(!btn) return;

  // ONE handler with a state, not a listener plus an onclick. The first version
  // added a save listener and later assigned an onclick for re-running; both
  // stayed attached, so the second click re-entered the save path, disabled the
  // button and left it stuck on "Saving…".
  var fresh = btn.cloneNode(true);
  btn.parentNode.replaceChild(fresh, btn);
  // Saved as you go now, so this is a status line rather than a button.
  // It still works if clicked, for anyone who reaches for it out of habit.
  fresh.textContent = 'Saved \u2713';
  fresh.disabled = true;

  var state = 'save';                       // save -> run -> running

  function fail(msg){
    state = 'save';
    fresh.disabled = false;
    fresh.textContent = msg || 'Save failed — try again';
    if(window.console) console.error('[fq] save/run problem:', msg);
  }

  fresh.addEventListener('click', function(){
    if(state === 'save'){
      var payload;
      try{
        // Read them defensively and SAY what went wrong. A generic message here
        // cost a round trip: "could not read the decisions" told neither of us
        // which of the two registers was missing.
        var d = (typeof DEC   !== 'undefined') ? DEC   : null;
        var a = (typeof ACCTS !== 'undefined') ? ACCTS : null;
        // Checklist verdicts ride in the same envelope. Leaving them out of the
        // payload meant marking an item and pressing Save silently discarded it
        // — the page showed the change, the file never received it.
        var it = (typeof ITEMS !== 'undefined') ? ITEMS : null;
        if(d === null && a === null){
          return fail('The page script did not finish loading — reload this tab');
        }
        payload = {folder: FOLDER,
                   decisions: {files: d || {}, accounts: a || {}, items: it || {}}};
        if(!Object.keys(payload.decisions.files).length &&
           !Object.keys(payload.decisions.accounts).length &&
           !Object.keys(payload.decisions.items).length){
          return fail('Nothing chosen yet — pick a destination or mark an item first');
        }
      }catch(e){
        return fail('Could not read the decisions: ' + (e && e.message || e));
      }
      state = 'saving';
      fresh.disabled = true;
      fresh.textContent = 'Saving\u2026';
      fetch('/api/decisions', {method:'POST', headers:{'Content-Type':'application/json'},
                               body: JSON.stringify(payload)})
        .then(function(r){
          if(!r.ok) throw new Error('server said ' + r.status);
          return r.json();
        })
        .then(function(){
          // Saving used to hand you a second button that jumped to the Audit
          // tab and re-ran everything. That step is gone: Build File Tree runs
          // the audit itself, so it already picks these decisions up. Being
          // sent to another tab to repeat work the next button does anyway is
          // what made this feel broken.
          // Saved, but not finished. Locking the button after one save forced a
          // reload to make a second change, which is the opposite of how anyone
          // reviews: you look at one document, decide, look at the next. The
          // button confirms, then re-arms itself the moment anything changes.
          state = 'save';
          fresh.disabled = true;
          fresh.textContent = 'Saved \u2713';
          var rearm = function(){
            document.removeEventListener('change', rearm, true);
            document.removeEventListener('input', rearm, true);
            fresh.textContent = 'Save decisions';
            fresh.disabled = false;
          };
          document.addEventListener('change', rearm, true);
          document.addEventListener('input', rearm, true);
          try{
            var st = window.parent.document.getElementById('filestatus');
            if(st) st.textContent = 'Decisions saved. Press Build File Tree to apply them.';
          }catch(e){}
        })
        .catch(function(e){ fail(String(e && e.message || e)); });
      return;
    }
  });
})();
</script>
"""



class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    # 127.0.0.1 only: the server is not reachable from anywhere but this Mac.
    port = PORT
    hopped = False
    for attempt in range(20):
        try:
            httpd = Server(('127.0.0.1', port), Handler)
            break
        except OSError:
            port += 1
            hopped = True
    else:
        print("Couldn't find a free port."); return 1

    # Hopping ports quietly is a trap. An older copy of the app keeps answering
    # on the usual address, so the browser goes on talking to yesterday's code
    # while this window insists it restarted — every fix looks like it failed.
    # Cost us most of an afternoon, so it says so now.
    if hopped:
        print("\n" + "!" * 70)
        print("  Another copy of FQ Toolkit is ALREADY RUNNING on port %d." % PORT)
        print("  This one had to move to port %d." % port)
        print("")
        print("  Your browser will keep using the OLD copy unless you either")
        print("  use the address below, or stop the old one first:")
        print("")
        print("      pkill -f fq_app.py     then start this again")
        print("!" * 70)

    url = 'http://127.0.0.1:%d/' % port
    print("\n  FQ Toolkit is running.")
    print("  Open it at: %s" % url)
    print("\n  Leave this window open while you work.")
    print("  Close it (or press Ctrl+C) when you're done.\n")
    threading.Thread(target=lambda: (time.sleep(0.6), webbrowser.open(url)), daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.\n")
    return 0


if __name__ == '__main__':
    sys.exit(main())
