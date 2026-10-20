#!/usr/bin/env python3
"""Refuse a commit that carries a client's real details into the code.

Installed as a git pre-commit hook. Reads only what is staged, and only the
lines being ADDED — an existing line nobody touched is not this commit's
problem, and flagging it would make the hook something people switch off.

WHY THIS EXISTS
The repo has always said, in .gitignore: "If you add an example, invent it;
never paste one out of a live client folder." That rule was broken three times
in a fortnight, every time while documenting a real bug:

  - a client's document password, quoted in a docstring explaining why the
    password handling was needed
  - a real bank account number, quoted in a comment about which letterhead the
    classifier reads
  - two real dates of birth, quoted in a comment about recognising a birthdate
    with no word attached to it

Each was written in good faith, each looked like careful documentation, and
each put live client data into version control where it outlives the folder it
came from. Reviewing at commit time was not enough, because by then the value
looks like part of the explanation.

So the check runs at the moment of committing, names the line, and stops.

Bypass with `git commit --no-verify` when a match is genuinely a false alarm —
but prefer inventing a different example, which is what the rule asks for.
"""
import os
import re
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Files worth reading. Client documents never belong in the repo at all — the
# allow-list .gitignore handles that — so this is about code and prose.
WATCH = ('.py', '.md', '.txt', '.command', '.html', '.json')

# Values that are meant to be here. The repo documents its detectors with
# obviously-fake numbers, and a hook that cries about those is a hook that gets
# disabled within a week.
ALLOWED = {
    '123456789', '12345678', '1234567890',      # textbook placeholders
    '1234567890123456', '1234 5678 9012 3456',
    '000000000', '111111111', '987654321',
    '1545-0074',                                 # an IRS form number
    '192.168.62.170',                            # the office server
}

# Deliberately invented examples that live in the codebase. Listed so the hook
# stays quiet about them without having to weaken the patterns themselves.
ALLOWED_INVENTED = {
    '481920365', '5550142398', '009-5550142', '4417208899', '412-55-8830',
    '412 55 8830', '4108', '2274', '03/09/1971', '11/22/1974',
    '104729386001',
}

PATTERNS = [
    ('SSN',              re.compile(r'\b\d{3}-\d{2}-\d{4}\b')),
    ('SSN (spaced)',     re.compile(r'\b\d{3}\s+\d{2}\s+\d{4}\b')),
    ('account number',   re.compile(r'\b\d{8,17}\b')),
    ('card number',      re.compile(r'\b(?:\d[ -]?){13,16}\b')),
    # A birth year, not any year. Statement periods and payment dates are all
    # over this codebase's comments — "1.1.26 - 3.31.26", "8/14/2026" — and
    # every one of them matched a plain date pattern. Nobody in a client folder
    # was born last year.
    ('date of birth',    re.compile(r'\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])'
                                    r'[/-](19[2-9]\d|200\d)\b')),
]

# Minified JavaScript is one enormous line of buffer sizes and bit masks. The
# vendored redactor is 9.8 MB of it, and reading it produced 58 flags, none of
# them client data.
MAX_LINE = 400

# Lines that are obviously not client data whatever they contain.
SKIP_LINE = re.compile(r'^\s*(?:#\s*)?(?:https?://|version|copyright|sha256|'
                       r'[0-9a-f]{16,}\s*$)', re.I)


def staged_additions():
    """(path, line number in the new file, text) for every added line."""
    out = subprocess.run(['git', 'diff', '--cached', '-U0'],
                         capture_output=True, text=True)
    path, lineno, rows = None, 0, []
    for line in out.stdout.splitlines():
        if line.startswith('+++ b/'):
            path = line[6:]
            continue
        m = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)', line)
        if m:
            lineno = int(m.group(1))
            continue
        if line.startswith('+') and not line.startswith('+++'):
            if path and path.endswith(WATCH):
                rows.append((path, lineno, line[1:]))
            lineno += 1
    return rows


def suspicious(text):
    """Every worrying value on one line, with what it looks like."""
    if SKIP_LINE.match(text) or len(text) > MAX_LINE:
        return []
    # A CSS colour is eight hex digits that happen to be decimal. #35486380 is
    # a button hover state, not an account.
    text = re.sub(r'#[0-9a-fA-F]{3,8}\b', ' ', text)
    # An example is invented as a whole line, not value by value. The comment
    # documenting the dependent-SSN rule reads "JANE DOE 123456789 01/02/2010":
    # the SSN is a known placeholder, so the date beside it is plainly part of
    # the same made-up example and flagging it only teaches people to ignore
    # the hook.
    # Whitespace varies — the same invented SSN appears as "412 55 8830" and
    # "412   55   8830" in different comments — so compare with runs collapsed.
    flat = re.sub(r'\s+', ' ', text)
    if any(tok in text or tok in flat for tok in ALLOWED | ALLOWED_INVENTED):
        return []
    hits = []
    for label, pat in PATTERNS:
        for m in pat.finditer(text):
            raw = m.group(0)
            bare = re.sub(r'\D', '', raw)
            if raw in ALLOWED or bare in ALLOWED or raw in ALLOWED_INVENTED:
                continue
            # A run of digits that is plainly a year, a size, or a line of code
            # rather than an identifier.
            if label == 'account number' and (
                    re.match(r'^(19|20)\d{6}$', bare)          # a date
                    or len(bare) <= 8 and bare.startswith('20')):
                continue
            hits.append((label, raw))
    return hits


def main():
    rows = staged_additions()
    problems = []
    for path, lineno, text in rows:
        for label, value in suspicious(text):
            problems.append((path, lineno, label, value, text.strip()))

    if not problems:
        return 0

    red = '\033[31m' if sys.stderr.isatty() else ''
    off = '\033[0m' if sys.stderr.isatty() else ''
    print('', file=sys.stderr)
    print('%sThis commit looks like it contains real client data.%s'
          % (red, off), file=sys.stderr)
    print('', file=sys.stderr)
    for path, lineno, label, value, text in problems[:20]:
        print('  %s:%d' % (path, lineno), file=sys.stderr)
        print('     %-16s %s' % (label, value), file=sys.stderr)
        print('     %s' % text[:100], file=sys.stderr)
        print('', file=sys.stderr)
    if len(problems) > 20:
        print('  ...and %d more' % (len(problems) - 20), file=sys.stderr)

    print('The repo\'s own rule, from .gitignore:', file=sys.stderr)
    print('  "If you add an example, invent it; never paste one out of a '
          'live client folder."', file=sys.stderr)
    print('', file=sys.stderr)
    print('Invent a different value and commit again. If this is genuinely a '
          'false alarm,', file=sys.stderr)
    print('add it to ALLOWED_INVENTED in fq_auditor/precommit_check.py, or '
          'bypass once with:', file=sys.stderr)
    print('    git commit --no-verify', file=sys.stderr)
    print('', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
