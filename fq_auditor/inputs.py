#!/usr/bin/env python3
"""Figures a human supplied, kept so a rebuild cannot throw them away.

    python3 inputs.py "<client folder>"                       # show them
    python3 inputs.py "<client folder>" --set residence_value \
            --value 675000 --as-of 2026-10-13 \
            --url "https://www.zillow.com/..." --by "<your name>"

WHY THIS EXISTS
Some figures a plan needs cannot be read out of a document, because no
document carries them. A Zillow estimate is the clearest case: Zillow blocks
automated requests, the number changes weekly, and the firm's own convention
is that an analyst sometimes adjusts off the estimate rather than taking it
flat ("per Zillow + 0%"). So a person looks it up and types it in.

The danger with a typed figure is that it is invisible. It sits in the
document with the same authority as a figure read from a tax return, and
nobody can tell six months later where it came from or how stale it is. Worse,
the next regeneration silently overwrites it and the work is simply gone.

So every typed figure is stored here with four things attached, not one:

    value       what was entered
    as_of       the date it was true, which for a market estimate is the
                date somebody actually looked, not the date of the plan
    url         where to go to check it
    by          who entered it

That is enough for the source line under the section to say "per Zillow.com,
13 October 2026" and for anyone to verify it in one click. It also makes the
staleness checkable: a property value carried over from eleven months ago is
a finding, and finding it requires knowing when it was pulled.

WHERE IT LIVES
_Audit/plan_inputs.json, beside the other audit artefacts rather than loose in
the client folder, because it is working state and not something the client
sent. Rebuilds read it and never write it.
"""
import os
import sys
import json
import argparse
import datetime

STORE = os.path.join('_Audit', 'plan_inputs.json')


def path_for(folder):
    return os.path.join(folder, STORE)


def load(folder):
    """Every human-supplied figure for this client, by key."""
    try:
        with open(path_for(folder), errors='replace') as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def get(folder, key):
    """One entry, or None. Always a dict when present."""
    got = load(folder).get(key)
    return got if isinstance(got, dict) else None


def value(folder, key):
    """Just the figure, for callers that do not need the provenance."""
    got = get(folder, key)
    return got.get('value') if got else None


def put(folder, key, value, as_of=None, url=None, by=None, note=None):
    """Record a figure. Overwrites the key, keeping no history.

    No history on purpose: the point of the store is what the plan should say
    now. A superseded Zillow estimate is not evidence of anything, and keeping
    a trail of them invites someone to cite the wrong one.
    """
    store = load(folder)
    store[key] = {
        'value': value,
        'as_of': as_of or datetime.date.today().isoformat(),
        'url': url,
        'by': by,
        'note': note,
        'recorded': datetime.datetime.now().isoformat(timespec='seconds'),
    }
    dest = path_for(folder)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, 'w') as fh:
        json.dump(store, fh, indent=1, sort_keys=True)
    return store[key]


def cite(entry, what):
    """The source line for a typed figure: where it came from and when.

    Reads "per Zillow.com, 13 October 2026" rather than "per Zillow.com",
    because an estimate without a date cannot be judged stale, and a stale
    property value moves the whole balance sheet.
    """
    if not entry:
        return None
    bits = ['per %s' % what]
    if entry.get('as_of'):
        try:
            when = datetime.date.fromisoformat(entry['as_of'])
            bits.append(when.strftime('%-d %B %Y'))
        except ValueError:
            bits.append(str(entry['as_of']))
    if entry.get('by'):
        bits.append('entered by %s' % entry['by'])
    return ', '.join(bits)


def stale(entry, months=6):
    """Has this figure aged past the point where it should be re-checked?"""
    if not entry or not entry.get('as_of'):
        return False
    try:
        when = datetime.date.fromisoformat(entry['as_of'])
    except ValueError:
        return False
    return (datetime.date.today() - when).days > months * 30


def main():
    ap = argparse.ArgumentParser(description='Figures a human supplied')
    ap.add_argument('folder')
    ap.add_argument('--set', dest='key', default=None)
    ap.add_argument('--value', default=None)
    ap.add_argument('--as-of', dest='as_of', default=None)
    ap.add_argument('--url', default=None)
    ap.add_argument('--by', default=None)
    ap.add_argument('--note', default=None)
    a = ap.parse_args()

    if a.key:
        try:
            val = float(str(a.value).replace(',', '').replace('$', ''))
        except (TypeError, ValueError):
            val = a.value
        got = put(a.folder, a.key, val, a.as_of, a.url, a.by, a.note)
        print('%s = %s  (%s)' % (a.key, got['value'], got['as_of']))
        return

    store = load(a.folder)
    if not store:
        print('No human-supplied figures recorded for this client.')
        return
    for key in sorted(store):
        e = store[key]
        print('%-22s %-14s %s%s' % (
            key, e.get('value'), e.get('as_of') or '',
            '   STALE' if stale(e) else ''))
        if e.get('url'):
            print('%-22s %s' % ('', e['url']))


if __name__ == '__main__':
    main()
