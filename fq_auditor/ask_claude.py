#!/usr/bin/env python3
"""The one place in the toolkit that asks Claude a question.

    python3 ask_claude.py --check          # is it installed, and on a seat?
    python3 ask_claude.py "what is 2+2?"   # one question, for testing

WHY A SINGLE MODULE
Everything that needs Claude goes through `ask_json` below. Nothing else in the
toolkit knows how the question was answered. That keeps three doors open at no
cost: a different model later, a local model on the machine, or nothing at all
if a question turns out not to need asking.

WHY THE COMMAND LINE AND NOT THE API
The firm pays for Claude by the seat, not by the call. Claude Code signed in
with a seat draws on that seat's allowance; the same binary driven by an API key
bills the organisation per token. Those two look identical from here, so this
module refuses to run when it finds an API key in the environment rather than
quietly spending money. A seat that has run out fails loudly and cheaply; a key
that has not run out fails silently and expensively.

WHAT IT IS AND IS NOT FOR
Asking what a document is, and whether it satisfies a request. Never asking for
a figure. Every number on every page is still read or computed by code, checked
against a second source, and carries its own record of where it came from. A
model that is never asked for a number cannot invent one.
"""
import os
import re
import sys
import json
import time
import hashlib
import subprocess

TIMEOUT = 120
CACHE_DIRNAME = 'classify'


class NotAvailable(RuntimeError):
    """Claude Code is missing, signed out, or would bill per call."""


def _binary():
    """Claude Code's path, searching the usual place the installer uses."""
    from shutil import which
    found = which('claude')
    if found:
        return found
    fallback = os.path.expanduser('~/.local/bin/claude')
    return fallback if os.path.exists(fallback) else None


def check():
    """Why this would or would not work right now, in one dict."""
    path = _binary()
    key = os.environ.get('ANTHROPIC_API_KEY')
    out = {'binary': path, 'api_key_present': bool(key), 'version': None,
           'ok': False, 'reason': None}
    if key:
        out['reason'] = ('ANTHROPIC_API_KEY is set, which would bill this per '
                         'call instead of using the seat. Unset it and retry.')
        return out
    if not path:
        out['reason'] = ('Claude Code is not installed. '
                         'curl -fsSL https://claude.ai/install.sh | bash')
        return out
    try:
        v = subprocess.run([path, '--version'], capture_output=True, text=True,
                           timeout=30)
        out['version'] = (v.stdout or v.stderr).strip()
        out['ok'] = v.returncode == 0
        if not out['ok']:
            out['reason'] = out['version'] or 'claude --version failed'
    except Exception as exc:                                  # noqa: BLE001
        out['reason'] = str(exc)
    return out


def available():
    return check()['ok']


def _cache_path(cache_dir, prompt, allow=(), add_dirs=()):
    """Keyed on how the question was asked, not only on what was asked.

    An earlier version keyed on the prompt alone. Granting Claude permission to
    read the file changed the answers completely and the key not at all, so a
    re-run served the old answers back -- the ones given without having read
    anything.
    """
    shape = '%s|%s|%s' % (prompt, ','.join(allow), ','.join(sorted(add_dirs)))
    key = hashlib.sha1(shape.encode('utf-8')).hexdigest()
    return os.path.join(cache_dir, key + '.json')


def ask(prompt, cache_dir=None, timeout=TIMEOUT, allow=('Read',),
        add_dirs=()):
    """One question, one answer, remembered.

    The same question is never asked twice: the answer is cached on a hash of
    the prompt itself, so re-running a client costs nothing and gives the same
    result. That matters more than the saving. A classifier whose answers move
    between runs cannot be measured, and measuring is the point.
    """
    if cache_dir:
        hit = _cache_path(cache_dir, prompt, allow, add_dirs)
        try:
            with open(hit) as fh:
                return json.load(fh)['answer']
        except (OSError, ValueError, KeyError):
            pass

    state = check()
    if not state['ok']:
        raise NotAvailable(state['reason'])

    # In print mode Claude cannot stop to ask for permission, so a file it was
    # not told it may read is simply not read -- and it answers from whatever
    # else it has, which is how three documents came back judged on a text
    # hint we already knew was unreliable. Read is granted explicitly, and the
    # folders named, because the documents live outside the working directory.
    cmd = [state['binary'], '-p', prompt]
    if allow:
        cmd += ['--allowedTools', ','.join(allow)]
    for d in add_dirs:
        cmd += ['--add-dir', d]

    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise NotAvailable((proc.stderr or proc.stdout or '').strip()
                           or 'claude exited %d' % proc.returncode)
    answer = proc.stdout.strip()

    if cache_dir:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            with open(_cache_path(cache_dir, prompt, allow,
                                  add_dirs), 'w') as fh:
                json.dump({'prompt': prompt, 'answer': answer,
                           'version': state['version'],
                           'seconds': round(time.time() - started, 1),
                           'asked': time.strftime('%Y-%m-%dT%H:%M:%S')},
                          fh, indent=1)
        except OSError:
            pass
    return answer


JSON_BLOCK = re.compile(r'\{.*\}', re.S)


def ask_json(prompt, cache_dir=None, timeout=TIMEOUT, allow=('Read',),
             add_dirs=()):
    """Ask for JSON and get a dict, or None if the reply was not usable.

    The reply is scanned for the outermost braces rather than parsed whole,
    because a model will sometimes wrap perfectly good JSON in a sentence. None
    is returned rather than a guess: a document this could not read is a
    document for a person to look at, which is the same rule the rest of the
    toolkit follows.
    """
    raw = ask(prompt, cache_dir=cache_dir, timeout=timeout,
              allow=allow, add_dirs=add_dirs)
    m = JSON_BLOCK.search(raw or '')
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def main():
    args = sys.argv[1:]
    if not args or args[0] == '--check':
        state = check()
        print('claude binary   %s' % (state['binary'] or 'NOT FOUND'))
        print('version         %s' % (state['version'] or '-'))
        print('API key set     %s' % ('YES - would bill per call'
                                      if state['api_key_present'] else 'no'))
        print('usable          %s' % ('yes' if state['ok'] else 'NO'))
        if state['reason']:
            print('                %s' % state['reason'])
        return 0 if state['ok'] else 1
    print(ask(' '.join(args)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
