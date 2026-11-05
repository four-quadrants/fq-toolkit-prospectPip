#!/usr/bin/env python3
"""Read the analyst’s changes back out of the cash flow workbook.

    python3 cashflow_review.py "<client folder>"        # show what was changed

WHY
The cash flow workbook is where the analyst reviews the toolkit's reading:
a movement that is not really spending, a transfer that was missed, an
adjustment that is wrong. Until now those changes stayed in the .numbers
file. Every later figure (the Assumptions, the plan card, the deck) was
still built from the unreviewed reading, and rebuilding the workbook threw
the changes away.

HOW
When the toolkit writes the workbook it reads its own cells straight back
and keeps that as a snapshot (_Audit/cashflow_written.json). Later, any cell
the analyst has changed is a difference from the snapshot. Each difference is
kept as a decision (_Audit/cashflow_review.json), keyed by sheet, account and
statement period, never by row or column number, so a rebuild with a new
statement cannot attach an old decision to the wrong month.

WHAT COUNTS
In each account's four period columns:
    Transfers In, Transfers Out      the analyst’s figure replaces ours
    the adjustment lines             a change adds to the adjustments out
    Total Adjustments OUT / IN       where the sheet has no formula there,
                                     the analyst’s figure replaces ours
Anything else on the sheet is not read: changing an ending balance does not
change a statement.

cashflow.build() harvests before it builds and applies the decisions after,
so everything downstream uses the reviewed figures, and a rebuilt workbook
carries them.
"""
import os
import store as _store  # noqa: E402
import sys
import glob
import json
import datetime
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cashflow_workbook as _wb                              # noqa: E402

SNAPSHOT = 'cashflow_written.json'
DECISIONS = 'cashflow_review.json'
ADJ_LINES = list(range(_wb.R_ADJ_FIRST, _wb.R_ADJ_OUT))
# The IN block's own lines, summed by the template into row 17 (0-based).
ADJ_IN_LINES = list(range(_wb.R_ADJ_IN + 1, _wb.R_ADJ_IN + 7))
FIELDS = {_wb.R_TRANSFER_IN: 'transfers_in', _wb.R_TRANSFER_OUT: 'transfers_out',
          _wb.R_ADJ_OUT: 'adj_out', _wb.R_ADJ_IN: 'adj_in'}


def _audit(folder):
    return os.path.join(folder, '_Audit')


def workbook_path(folder):
    # The client folder since outputs moved there; _Audit for older clients.
    got = sorted(glob.glob(os.path.join(glob.escape(folder), 'Cash flow - *.numbers'))
                 + glob.glob(os.path.join(glob.escape(_audit(folder)), 'Cash flow - *.numbers')),
                 key=os.path.getmtime, reverse=True)
    return got[0] if got else None


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    try:
        return round(float(str(v).replace(',', '').replace('$', '')), 2)
    except (TypeError, ValueError):
        return None


def read_cells(path):
    """{sheet: {account: {period: {field: value}}}}, from the toolkit's
    layout (cashflow_book.py). Rows are found by their labels."""
    import cashflow_book as _book
    return _book.read_back(path)


def snapshot(folder, path=None):
    """Called right after the toolkit writes the workbook."""
    path = path or workbook_path(folder)
    if not path:
        return None
    data = {'file': os.path.basename(path), 'mtime': os.path.getmtime(path),
            'cells': read_cells(path)}
    with open(_store.json_path(_audit(folder), SNAPSHOT), 'w') as fh:
        json.dump(data, fh, indent=1)
    return data


def load_decisions(folder):
    try:
        with open(_store.json_path(_audit(folder), DECISIONS)) as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def harvest(folder):
    """Fold any change the analyst made in the workbook into the decisions.

    Does nothing unless the workbook has been saved since the toolkit wrote
    it. Returns the list of new or changed decisions.
    """
    path = workbook_path(folder)
    snap_p = _store.json_path(_audit(folder), SNAPSHOT)
    if not path or not os.path.exists(snap_p):
        return []
    try:
        snap = json.load(open(snap_p))
    except (OSError, ValueError):
        return []
    if os.path.getmtime(path) <= snap.get('mtime', 0) + 1:
        return []
    now = read_cells(path)
    dec = load_decisions(folder)
    changed = []
    for sheet, accts in now.items():
        for acct, periods in accts.items():
            for period, row in periods.items():
                was = (((snap['cells'].get(sheet) or {}).get(acct) or {})
                       .get(period) or {})
                for field in list(FIELDS.values()) + ['adj_lines',
                                                      'adj_in_lines']:
                    a, b = was.get(field), row.get(field)
                    if b is None or a == b:
                        continue
                    key = '|'.join((sheet, acct, period, field))
                    entry = {'sheet': sheet, 'account': acct,
                             'period': period, 'field': field,
                             'toolkit': a, 'analyst': b,
                             'read': datetime.datetime.now().isoformat(
                                 timespec='seconds')}
                    if key in dec:
                        # Keep what the toolkit first said, so a second edit
                        # is measured against the reading, not the first edit.
                        entry['toolkit'] = dec[key]['toolkit']
                    if dec.get(key, {}).get('analyst') != b:
                        changed.append(entry)
                    dec[key] = entry
    with open(_store.json_path(_audit(folder), DECISIONS), 'w') as fh:
        json.dump(dec, fh, indent=1, sort_keys=True)
    # The workbook as it now stands is the new baseline, so the same change
    # is not read twice and a later one is seen against it.
    snapshot(folder, path)
    return changed


def apply(folder, entities):
    """Put the analyst’s figures into the built entities, in place."""
    dec = load_decisions(folder)
    if not dec:
        return 0
    used = 0
    for ent in entities:
        for acct in ent['accounts']:
            for j, period in enumerate(acct['periods']):
                for d in dec.values():
                    if (d['sheet'] != ent['name'] or d['account'] != acct['name']
                            or d['period'] != period):
                        continue
                    f, v = d['field'], d['analyst']
                    if f == 'adj_lines':
                        acct['adj_out'][j] += v - (d['toolkit'] or 0)
                    elif f == 'adj_in_lines':
                        acct['adj_in'][j] += v - (d['toolkit'] or 0)
                    elif f == 'transfers_out':
                        # A transfer out is taken out of expenses through the
                        # adjustments, so the adjustment moves with it.
                        acct['adj_out'][j] += v - acct['transfers_out'][j]
                        acct['transfers_out'][j] = v
                    elif f in acct:
                        acct[f][j] = v
                    used += 1
            # Expenses net of transfers follow the reviewed transfers.
            acct['surplus_expense'] = [
                b + a - e - o for b, a, e, o in
                zip(acct['beginning'], acct['additions'], acct['ending'],
                    acct['transfers_out'])]
            acct['reviewed'] = True
        ent.setdefault('adjustments', [])
    return used


def main():
    ap = argparse.ArgumentParser(description='Cash flow review read-back')
    ap.add_argument('folder')
    a = ap.parse_args()
    new = harvest(a.folder)
    dec = load_decisions(a.folder)
    print('%d new or changed; %d decisions on file' % (len(new), len(dec)))
    for d in sorted(dec.values(), key=lambda d: (d['sheet'], d['account'],
                                                 d['period'])):
        print('  %s / %s / %s  %s: toolkit %s, analyst %s'
              % (d['sheet'], d['account'], d['period'], d['field'],
                 d['toolkit'], d['analyst']))


if __name__ == '__main__':
    main()
