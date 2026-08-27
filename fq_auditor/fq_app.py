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
ROOT_FILE = os.path.join(HERE, '.fq_root')


def get_root():
    try:
        with open(ROOT_FILE) as fh:
            p = fh.read().strip()
        if p and os.path.isdir(p):
            return os.path.realpath(p)
    except OSError:
        pass
    return None


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
    # folder root or in Downloads from an earlier manual export would otherwise
    # win and silently ignore what you just chose.
    for c in (os.path.join(folder, '_Audit', 'decisions.json'),
              os.path.join(folder, 'decisions.json'),
              os.path.expanduser('~/Downloads/decisions.json')):
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

    if not out['client']:
        out['client'] = os.path.basename(folder.rstrip('/'))
    return out


def save_settings(folder, client, greeting, checklist):
    try:
        with open(os.path.join(folder, '.fq_settings'), 'w') as fh:
            fh.write('CLIENT="%s"\nGREETING="%s"\nCHECKLIST="%s"\n'
                     % (client or '', greeting or '', checklist or ''))
    except OSError:
        pass


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
                entries.append({'name': name, 'path': full, 'count': n})
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

PAGE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FQ Toolkit</title>
<style>
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
     background:#F7F6F3;color:#1B2A41;height:100vh;display:flex;flex-direction:column}
header{background:#1B2A41;color:#fff;padding:0 20px;display:flex;align-items:center;gap:22px;
       flex:0 0 54px}
header h1{font-size:16px;margin:0;font-weight:600;letter-spacing:.2px}
nav{display:flex;gap:4px;margin-left:8px}
nav button{background:transparent;border:0;color:#cbd5e1;font:inherit;font-size:14px;
     padding:8px 15px;border-radius:8px;cursor:pointer}
nav button:hover{background:#2A3A52;color:#fff}
nav button.on{background:#E8792B;color:#fff;font-weight:600}
.tag{margin-left:auto;font-size:12px;opacity:.75}
main{flex:1;overflow:hidden;position:relative}
.pane{position:absolute;inset:0;overflow:auto;display:none}
.pane.on{display:block}
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
.step b{background:#1B2A41;color:#fff;width:21px;height:21px;border-radius:50%;
      display:flex;align-items:center;justify-content:center;font-size:12px;flex:0 0 21px}
.hide{display:none}
</style></head><body>

<header>
  <h1>FQ Toolkit</h1>
  <nav>
    <button id="tab-redact" class="on">1 &nbsp;Redact</button>
    <button id="tab-audit">2 &nbsp;Audit &amp; File</button>
    <button id="tab-review">3 &nbsp;Review</button>
  </nav>
  <span class="tag">running on this Mac only &middot; nothing is uploaded</span>
</header>

<main>
  <div class="pane on" id="pane-redact">
    <iframe id="redactframe" src="/redactor"></iframe>
  </div>

  <div class="pane" id="pane-audit"><div class="wrap">
    <h2>Audit &amp; File</h2>
    <p class="sub">Point this at the client's folder. It reads every document, checks them
       against the checklist, and works out where each one should be filed.</p>

    <div class="card" id="rootcard">
      <label>Working folder</label>
      <p class="sub" style="margin:0 0 10px">This app can only see inside one folder,
         and it has no access to anything until you choose it. Pick the folder your
         client folders live in — every action is checked against it, not just the
         list below.</p>
      <div class="row">
        <button class="primary" id="pickroot">Choose folder…</button>
        <span class="sub" id="roothint" style="margin:0">Opens the normal Mac folder chooser.</span>
      </div>
      <div id="rootnow" class="found hide" style="margin-top:10px"></div>
    </div>

    <div class="card" id="pickcard">
      <label>Client folder</label>
      <div class="crumb" id="crumb">…</div>
      <div class="folders" id="folders"></div>
      <div class="row" style="margin-top:10px">
        <button class="ghost" id="up">↑ Up one level</button>
        <button class="ghost" id="home">Back to top</button>
        <span style="flex:1"></span>
        <button class="primary" id="pick">Use this folder</button>
      </div>
    </div>

    <div class="card hide" id="ready">
      <div class="row" style="gap:18px">
        <div style="flex:1;min-width:200px">
          <label>Client name</label>
          <input type="text" id="client" placeholder="Bassett">
        </div>
        <div style="flex:1;min-width:200px">
          <label>Email greeting</label>
          <input type="text" id="greeting" placeholder="Dr. and Mrs. Bassett">
        </div>
      </div>
      <div id="found"></div>
      <div class="row" style="margin-top:16px">
        <button class="primary" id="run">Run the audit</button>
        <span class="sub" style="margin:0">First run takes a few minutes. After that it's quick.</span>
      </div>
    </div>

    <div class="card hide" id="logcard">
      <label>Progress</label>
      <pre class="log" id="log"></pre>
      <div id="done" class="hide" style="margin-top:14px">
        <div class="step"><b>1</b><span>Open the <b>Review</b> tab and work down the list of
          documents that need a filing decision. Each has a preview.</span></div>
        <div class="step"><b>2</b><span>Choose a destination for each one, then press
          <b>Save decisions</b> at the top of that page.</span></div>
        <div class="step"><b>3</b><span>Come back here and run the audit again — your choices
          are picked up automatically.</span></div>
        <div class="step"><b>4</b><span>When the plan above reads correctly, file them.
          Documents are <b>copied</b> into the Personal and Business folders — nothing is
          moved and the originals stay exactly as the client sent them.</span></div>
        <div class="row" style="margin-top:12px">
          <button class="primary" id="goreview">Open the review</button>
          <button class="primary" id="filethem">File them now</button>
          <button class="ghost" id="openfolder">Show the files in Finder</button>
        </div>
      </div>
    </div>
  </div></div>

  <div class="pane" id="pane-review">
    <iframe id="reviewframe" src="about:blank"></iframe>
  </div>
</main>

<script>
var CUR = null, FOLDER = null, since = 0, poll = null;

function show(name){
  ['redact','audit','review'].forEach(function(n){
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
document.getElementById('tab-redact').onclick=function(){show('redact');};
document.getElementById('tab-audit').onclick=function(){show('audit');};
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
    d.entries.forEach(function(e){
      var row=document.createElement('div');
      row.innerHTML='<span>'+e.name+'</span><span class="n">'+e.count+' items</span>';
      row.onclick=function(){ browse(e.path); };
      box.appendChild(row);
    });
  });
}
document.getElementById('up').onclick=function(){ browse(CUR.replace(/\/[^\/]+$/,'')||'/'); };
document.getElementById('home').onclick=function(){ browse(''); };   // '' snaps to the root

document.getElementById('pick').onclick=function(){
  FOLDER=CUR;
  fetch('/api/inspect?folder='+encodeURIComponent(FOLDER)).then(function(r){return r.json();}).then(function(d){
    document.getElementById('ready').classList.remove('hide');
    document.getElementById('client').value=d.client||'';
    document.getElementById('greeting').value=d.greeting||'';
    var f=document.getElementById('found'); f.innerHTML='';
    function note(txt, good){
      var el=document.createElement('div');
      el.className='found'+(good?'':' miss'); el.textContent=txt; f.appendChild(el);
    }
    note(d.n_docs+' documents in '+FOLDER.split('/').pop(), true);
    if(d.checklist) note('Checklist found: '+d.checklist.split('/').pop(), true);
    else note('No checklist found — the standard one will be used', false);
    if(d.decisions) note('Your saved decisions were found and will be applied', true);
    if(d.redacted) note('Redacted copies found, previews will use them', true);
    window.scrollTo(0, document.body.scrollHeight);
  });
};

function runAudit(){
  var btn=document.getElementById('run'); btn.disabled=true;
  document.getElementById('logcard').classList.remove('hide');
  document.getElementById('done').classList.add('hide');
  document.getElementById('log').textContent='';
  since=0;
  fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({folder:FOLDER, client:document.getElementById('client').value,
                         greeting:document.getElementById('greeting').value})})
    .then(function(){ poll=setInterval(tick,700); });
}
document.getElementById('run').onclick=runAudit;

// Filing re-runs the whole audit with --file-them, so the copies are made from a
// plan built seconds ago rather than one that predates the operator's decisions.
function fileThem(){
  if(!confirm('Copy these documents into their folders?\n\n'
            + 'Copies only — the originals are not moved or changed.')) return;
  var b=document.getElementById('filethem'); b.disabled=true;
  document.getElementById('run').disabled=true;
  document.getElementById('done').classList.add('hide');
  document.getElementById('log').textContent='';
  since=0;
  fetch('/api/file',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({folder:FOLDER, client:document.getElementById('client').value,
                         greeting:document.getElementById('greeting').value})})
    .then(function(){ poll=setInterval(tick,700); });
}
document.getElementById('filethem').onclick=fileThem;
window.runAudit=runAudit; window.showTab=show;   // the review frame calls these

function tick(){
  fetch('/api/log?since='+since).then(function(r){return r.json();}).then(function(d){
    since=d.total;
    if(d.lines.length){
      var el=document.getElementById('log');
      el.textContent += d.lines.join('\n')+'\n';
      el.scrollTop=el.scrollHeight;
    }
    if(!d.running){
      clearInterval(poll);
      document.getElementById('run').disabled=false;
      document.getElementById('filethem').disabled=false;
      document.getElementById('done').classList.remove('hide');
      var f=document.getElementById('reviewframe'); f.src='about:blank';
    }
  });
}
document.getElementById('goreview').onclick=function(){ show('review'); };
document.getElementById('openfolder').onclick=function(){
  fetch('/api/reveal?folder='+encodeURIComponent(FOLDER));
};

refreshRoot().then(function(root){ if(root) browse(''); });
</script></body></html>
"""


# ---------------------------------------------------------------- server

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass                                   # keep the console clean for the operator

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
            self._send(400, '{"error":"no working folder set"}')
            return False
        if not inside_root(folder):
            self._send(403, '{"error":"that folder is outside the working folder"}')
            return False
        return True

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        q = self._q()

        if p == '/':
            return self._send(200, PAGE, 'text/html; charset=utf-8')

        if p == '/redactor':
            rp = find_redactor()
            if not rp:
                return self._send(200, '<body style="font:15px -apple-system;padding:40px">'
                                       '<h3>Redactor not found</h3><p>Put <code>Cena.html</code> '
                                       'next to this folder and reload.</p></body>',
                                  'text/html; charset=utf-8')
            with open(rp, 'rb') as fh:
                return self._send(200, fh.read(), 'text/html; charset=utf-8')

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
  var btn = document.getElementById('dlDec');
  if(!btn) return;

  // ONE handler with a state, not a listener plus an onclick. The first version
  // added a save listener and later assigned an onclick for re-running; both
  // stayed attached, so the second click re-entered the save path, disabled the
  // button and left it stuck on "Saving…".
  var fresh = btn.cloneNode(true);
  btn.parentNode.replaceChild(fresh, btn);
  fresh.textContent = 'Save decisions';
  fresh.disabled = false;

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
        if(d === null && a === null){
          return fail('The page script did not finish loading — reload this tab');
        }
        payload = {folder: FOLDER, decisions: {files: d || {}, accounts: a || {}}};
        if(!Object.keys(payload.decisions.files).length &&
           !Object.keys(payload.decisions.accounts).length){
          return fail('Nothing chosen yet — pick a destination first');
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
          state = 'run';
          fresh.disabled = false;
          fresh.textContent = 'Saved \u2014 run the audit again';
        })
        .catch(function(e){ fail(String(e && e.message || e)); });
      return;
    }

    if(state === 'run'){
      state = 'running';
      fresh.disabled = true;
      fresh.textContent = 'Running\u2026';
      try{
        window.parent.showTab('audit');
        window.parent.runAudit();
      }catch(e){
        fresh.disabled = false;
        fresh.textContent = 'Open the Audit tab and press Run';
      }
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
    for attempt in range(20):
        try:
            httpd = Server(('127.0.0.1', port), Handler)
            break
        except OSError:
            port += 1
    else:
        print("Couldn't find a free port."); return 1

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
