#!/usr/bin/env python3
"""The "here's what we still need" email after intake, from Claude's check.

    python3 intake_email.py "<client folder>"

Written from _Audit/claude_checklist.json: every item Claude marked partly
satisfied or missing, in its own short asks, practice first, then personal.
Shown on the intake review screen in a box with a Copy button (for pasting
into Outlook), and saved as plain text:

    _Audit/Intake follow-up - <Surname>.txt

Nothing is sent. The text is checked for account numbers and other personal
details before it is written; if anything is found, nothing is written and
the reason is printed.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _surname(folder):
    base = os.path.basename(os.path.normpath(folder))
    return re.split(r'[,\s]', base)[0] or 'Client'


def _first(folder):
    try:
        with open(os.path.join(folder, 'launchbay_manifest.json')) as fh:
            proj = json.load(fh).get('project') or ''
        m = re.search(r'Dr\.?\s+(\w+)', proj)
        if m:
            return 'Dr. ' + _surname(folder)
    except (OSError, ValueError):
        pass
    return 'Dr. ' + _surname(folder)


def asks(folder):
    """[(section, text)] from Claude's checklist verdicts, practice first."""
    path = os.path.join(folder, '_Audit', 'claude_checklist.json')
    try:
        with open(path) as fh:
            verdicts = json.load(fh)
    except (OSError, ValueError):
        return []
    try:
        with open(os.path.join(folder, '_Audit', 'decisions.json')) as fh:
            overridden = {k for k, v in (json.load(fh).get('items') or {}).items()
                          if v.get('verdict') == 'satisfied'}
    except (OSError, ValueError):
        overridden = set()
    out = []
    for item, v in verdicts.items():
        # A satisfied item can still carry a confirmation ("confirm the 2024
        # P&L is your year-end figure"), and that stays even when the analyst
        # also marked it satisfied. When the analyst overruled Claude (Claude
        # said partly satisfied or missing), Claude's asks are dropped.
        if item in overridden and (v.get('verdict') or '').lower() != 'satisfied':
            continue
        for a in v.get('asks') or ():
            text = (a.get('text') if isinstance(a, dict) else str(a)).strip()
            sec = (a.get('section') if isinstance(a, dict) else None) or 'Practice'
            if text:
                out.append((sec, text))
    out.sort(key=lambda x: x[0] != 'Practice')
    return out


def render(folder, items):
    return render_text('Dr. ' + _surname(folder), items)


def render_text(name, items):
    lines = ['Hi %s,' % name, '',
             'Thank you for sending everything over. We have gone through it all, '
             'and it puts us in great shape for your debrief. %s' % (
                 'There is just one more thing we need:' if len(items) == 1
                 else 'There are just two things we still need:' if len(items) == 2
                 else 'There are just a few items we still need:'), '']
    last = None
    n = 0
    for sec, text in items:
        if sec != last:
            lines += ['%s:' % ('For the practice' if sec == 'Practice' else 'Personal'), '']
            last = sec
        n += 1
        lines += ['%d. %s' % (n, text), '']
    lines += [('Feel free to upload anything to the portal, or just reply to '
               'this email. ' if len(items) == 1 else
               'Feel free to upload these to the portal as you get them, or reply '
               'to this email with anything easier to type out. ') + 'Thanks again, and '
              'let us know if you have any questions.', '', 'Thanks,', '']
    return '\n'.join(lines)


def write(folder):
    items = asks(folder)
    if not items:
        print('   nothing outstanding: no follow-up email needed')
        return None
    text = render(folder, items)
    try:
        from detectors import scan_residual_pii
        leaks = scan_residual_pii(text)
    except Exception:  # noqa: BLE001
        leaks = {}
    leaks = {k: v for k, v in leaks.items() if not k.lower().startswith('email')}
    if leaks:
        print('   follow-up email NOT written; it would include: %s'
              % '; '.join('%s %s' % (k, ', '.join(v[:2])) for k, v in leaks.items()))
        return None
    out = os.path.join(folder, '_Audit', 'Intake follow-up - %s' % _surname(folder))
    with open(out + '.txt', 'w') as fh:
        fh.write(text)
    print('   follow-up email written: %s.txt (%d items); copy it from the '
          'review screen' % (os.path.basename(out), len(items)))
    return out + '.txt'


def main():
    ap = argparse.ArgumentParser(description='Intake follow-up email')
    ap.add_argument('folder')
    a = ap.parse_args()
    p = write(a.folder)
    if p:
        print('OUTPUT\t%s' % p)
        print('\n' + open(p).read())


if __name__ == '__main__':
    main()
