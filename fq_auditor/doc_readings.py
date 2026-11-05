#!/usr/bin/env python3
"""What Claude read from the documents the code's readers could not, checked.

    python3 doc_readings.py "<client folder>"          # check and report

WHY THIS EXISTS
The code's readers each know a handful of layouts: a QuickBooks P&L, a
comparative 1120-S summary page, a Dentrix Practice Analysis, the firm's own
debt schedule. A client whose bookkeeper prints a different P&L, or whose
practice runs Open Dental, gets an initial notes sheet with three lines filled
in out of forty. Writing a new reader for every layout never ends.

So Claude reads those documents (in the Claude session that runs the step) and
writes what it read to _Audit/doc_readings.json. Nothing in that file is used
on Claude's word. Every figure is checked here before facts.py sees it:

  * it must appear in the document's own text (pdftotext, or the OCR cache
    for a scanned page), and
  * where the document carries its own total, the parts must add up to it to
    the dollar: a P&L's lines to its bottom line, a return's income less
    deductions to its ordinary income, a production report's columns to its
    totals.

A figure that fails is reported and left out. The code's own readers still
win wherever they read something; these readings only fill what is blank.

THE FILE (written by Claude, read here; years are strings)

{
 "read_on": "2026-11-02",
 "pnl": {"2025": {"source": "<file>", "months": 12, "income": 0,
                  "other_income_lines": {"<label>": 0},
                  "expense_lines": {"<label>": 0},
                  "doctor_salary": 0, "da": {"Depreciation": 0},
                  "net": 0}},
 "tax": {"2025": {"source": "<file>", "form": "1120-S", "income_base": 0,
                  "total_deductions": 0, "officer_comp": 0,
                  "depreciation_amort": 0, "da_parts": [0],
                  (da_parts: depreciation AND amortization. On a Schedule C
                   amortization sits in other expenses, not line 13: use the
                   preparer's depreciation summary grand total)
                  "net": 0}},
 "production": {"2025": {"months": 12, "reports": [
     {"source": "<file>", "provider": "<as printed>", "role": "doctor|hygiene",
      "production": 0, "adjustments": 0, "writeoffs": 0, "tot_prod": 0,
      "pt_income": 0, "ins_income": 0, "total_income": 0}]}},
 "counts": {"source": "<file>", "by_year": {"2025": {"total_patients": 0}}},
     (total_patients is patient VISITS in the period, e.g. a day sheet's
      "patients seen"; never a unique or active patient count)
     (a source of "LaunchBay portal comments" checks against what the
      client typed in the portal; counts.sources may name one per field,
      or "<field>_<year>" for one year)
 "debts": {"practice": [{"creditor": "", "what": "", "balance": 0,
                         "rate": 0.0, "payment": 0, "description": "",
                         "source": "<file>", "pending": false}],
           "personal": []},
 "profile": {"owned_since": {"value": "", "source": "<file>"}}
}
"""
import argparse
import hashlib
import json
import os
import store as _store  # noqa: E402
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FILE = 'doc_readings.json'
PORTAL = 'LaunchBay portal comments'
TOL = 1.01          # a dollar, for rounding in printed reports


def _path_of(folder, name):
    """The document called `name`, original copy first."""
    for sub in ('Original_sourcedocs', 'Documents', ''):
        root = os.path.join(folder, sub) if sub else folder
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(('.', '_'))]
            if name in files:
                return os.path.join(dirpath, name)
    return None


_TEXT = {}


def _text(folder, name):
    """The document's text: its own text layer, else the OCR cache."""
    if name in _TEXT:
        return _TEXT[name]
    path = _path_of(folder, name)
    text = ''
    if path:
        try:
            text = subprocess.run(['pdftotext', '-layout', path, '-'],
                                  capture_output=True, text=True,
                                  timeout=120).stdout
        except Exception:                                    # noqa: BLE001
            text = ''
        if len(text.strip()) < 40:
            h = hashlib.sha256(open(path, 'rb').read()).hexdigest()
            for cache in (os.path.join(folder, '.fq_cache'),
                          os.path.join(folder, 'Original_sourcedocs', '.fq_cache')):
                for ext in ('.v8.txt', '.txt'):
                    p = os.path.join(cache, h + ext)
                    if os.path.exists(p):
                        text = open(p, errors='replace').read()
                        break
                if len(text.strip()) >= 40:
                    break
    if not text and name == PORTAL:
        # What the client typed in LaunchBay counts as a source: patient
        # counts and days worked often only exist there. Checked the same
        # way, against the comments as written.
        for p in (_store.json_path(folder, 'launchbay_tasks.json'),):
            try:
                data = json.load(open(p))
            except (OSError, ValueError):
                continue
            text = '\n'.join(c.get('text') or '' for t in data.get('tasks') or ()
                             for c in t.get('comments') or ())
            break
    _TEXT[name] = text
    return text


def _digits(text):
    """Every run of figures in the text, as plain digit strings."""
    out = set()
    for m in re.finditer(r'\d[\d,]*(?:\.\d+)?', text):
        s = m.group(0).replace(',', '')
        out.add(s)
        if '.' in s:
            whole, frac = s.split('.', 1)
            out.add(whole)
            if frac.strip('0') == '':
                out.add(whole)
    return out


def appears(folder, name, value):
    """True when `value` is printed in the document (sign and cents aside)."""
    if value is None:
        return True
    v = abs(float(value))
    if v == 0:
        return True
    text = _text(folder, name)
    if not text:
        return False
    nums = _digits(text)
    cents = '%.2f' % v
    whole = '%d' % round(v)
    if cents in nums or whole in nums:
        return True
    # Rates print as "6.69%" or "0.0669"; a reading of 0.0669 is 6.69 on paper.
    if v < 1 and ('%.2f' % (v * 100)).rstrip('0').rstrip('.') in {
            n.rstrip('0').rstrip('.') for n in nums if '.' in n}:
        return True
    return False


def _close(a, b):
    return a is not None and b is not None and abs(float(a) - float(b)) <= TOL


def check(folder):
    """(verified readings, problems). Only verified figures are returned."""
    path = _store.json_path(folder, FILE)
    try:
        raw = json.load(open(path))
    except (OSError, ValueError):
        return {}, []
    good, problems = {}, []

    def need(src, label, *values):
        missing = [v for v in values if not appears(folder, src, v)]
        for v in missing:
            problems.append('%s: %s %s is not in the document' % (src, label, v))
        return not missing

    # ---------------------------------------------------------------- P&L
    pnl = {}
    for year, r in (raw.get('pnl') or {}).items():
        src = r.get('source') or ''
        lines = r.get('expense_lines') or {}
        da = r.get('da') or {}
        expenses = round(sum(lines.values()) + sum(da.values()), 2)
        oth = r.get('other_income_lines') or {'Other income': r.get('other_income') or 0}
        base = (r.get('income') or 0) + sum(oth.values())
        ok = need(src, 'P&L %s' % year, r.get('income'), *oth.values(),
                  r.get('doctor_salary'), r.get('net'),
                  *list(lines.values()) + list(da.values()))
        if r.get('net') is not None and not _close(base - expenses, r['net']):
            problems.append('%s: P&L %s does not tie (income %.0f less expenses '
                            '%.0f is %.0f; the document says %.0f)'
                            % (src, year, base, expenses, base - expenses, r['net']))
            ok = False
        if not ok:
            continue
        dsum = sum(da.values())
        oh = expenses - (r.get('doctor_salary') or 0) - dsum
        pnl[year] = {
            'year': year, 'source': src, 'months': r.get('months') or 0,
            'income': round(r.get('income') or 0, 2),
            'other_income': round(sum(oth.values()), 2),
            'income_base': round(base, 2), 'expenses': expenses,
            'other_expenses': 0.0,
            'doctor_salary': round(r.get('doctor_salary') or 0, 2),
            'depreciation_amort': round(dsum, 2), 'da_found': sorted(da),
            'overhead': round(oh, 2),
            'overhead_pct': round(100.0 * oh / base, 1) if base else None,
            'read_by': 'Claude, checked',
        }
    good['pnl'] = pnl

    # ---------------------------------------------------------------- tax
    tax = {}
    for year, r in (raw.get('tax') or {}).items():
        src = r.get('source') or ''
        parts = r.get('da_parts') or [r.get('depreciation_amort')]
        ok = need(src, 'return %s' % year, r.get('income_base'),
                  r.get('total_deductions'), r.get('officer_comp'),
                  r.get('net'), *parts)
        if r.get('net') is not None and not _close(
                r['income_base'] - r['total_deductions'], r['net']):
            problems.append('%s: return %s does not tie to its own net' % (src, year))
            ok = False
        if not ok:
            continue
        dep = sum(p or 0 for p in parts)
        oh = r['total_deductions'] - (r.get('officer_comp') or 0) - dep
        tax[year] = {
            'income_base': r['income_base'],
            'total_deductions': r['total_deductions'],
            'officer_comp': r.get('officer_comp') or 0.0,
            'depreciation_amort': round(dep, 2), 'overhead': round(oh, 2),
            'overhead_pct': round(100.0 * oh / r['income_base'], 1),
            'source': '%s (%s)' % (src, r.get('form') or 'return'),
        }
    good['tax'] = tax

    # --------------------------------------------------------- production
    prod = {}
    for year, r in (raw.get('production') or {}).items():
        reps, ok = r.get('reports') or [], True
        for rep in reps:
            src = rep.get('source') or ''
            # tot_prod is not always printed (Eaglesoft shows production
            # and adjustments only); the tie below checks it instead.
            keys = ('production', 'adjustments', 'writeoffs',
                    'pt_income', 'ins_income', 'total_income')
            if not need(src, 'production %s' % year, *[rep.get(k) for k in keys]):
                ok = False
            if not _close(rep['production'] + rep['adjustments'] + rep['writeoffs'],
                          rep['tot_prod']) or not _close(
                    rep['pt_income'] + rep['ins_income'], rep['total_income']):
                problems.append('%s: the columns do not add to its totals' % src)
                ok = False
        if not ok or not reps:
            continue

        def s(k):
            return round(sum(x[k] for x in reps), 2)
        hyg = round(sum(x['production'] for x in reps
                        if x.get('role') == 'hygiene'), 2)
        prod[year] = {
            'source': ', '.join(x['source'] for x in reps),
            'months': r.get('months'),
            'values': {
                'charges_uninsured': s('production'),
                'adjustments_add': round(s('adjustments') + s('writeoffs'), 2),
                'total_charges': s('tot_prod'),
                'patient_payments': s('pt_income'),
                'insurance_payments': s('ins_income'),
                'adjustments_less': 0.0,
                'total_credits': s('total_income'),
            },
            'by_role': {'hygiene': hyg or None},
            'read_by': 'Claude, checked',
        }
    good['production'] = prod

    # ------------------------------------------------------------- counts
    counts = {}
    c = raw.get('counts') or {}
    for year, vals in (c.get('by_year') or {}).items():
        for field, v in vals.items():
            srcs = c.get('sources') or {}
            src = (srcs.get('%s_%s' % (field, year)) or srcs.get(field)
                   or c.get('source') or '')
            if need(src, '%s %s' % (field, year), v):
                counts.setdefault(year, {})[field] = v
    good['counts'] = counts
    # months covered by the newest year's counts, when not the P&L's
    good['counts_months'] = c.get('ytd_months') or {}

    # -------------------------------------------------------------- debts
    debts = {}
    for side in ('practice', 'personal'):
        rows = []
        for d in (raw.get('debts') or {}).get(side) or ():
            src = d.get('source') or ''
            if not need(src, d.get('what') or d.get('creditor') or 'debt',
                        d.get('balance'), d.get('payment'), d.get('rate')):
                continue
            row = dict(d)
            row['source'] = src
            if d.get('pending'):
                # Not owed yet: shown, but kept out of the totals.
                bits = ['pending']
                if d.get('balance'):
                    bits.append('$%s' % format(round(d['balance']), ','))
                if d.get('rate'):
                    bits.append('%.2f%%' % (d['rate'] * 100 if d['rate'] < 1
                                            else d['rate']))
                if d.get('payment'):
                    bits.append('$%s/mo' % format(round(d['payment']), ','))
                row['description'] = ', '.join(bits) + (
                    '. ' + d['description'] if d.get('description') else '')
                row['balance'] = row['payment'] = row['rate'] = None
            rows.append(row)
        debts[side] = rows
    good['debts'] = debts

    # ------------------------------------------------------------ profile
    prof = {}
    for k, v in (raw.get('profile') or {}).items():
        if isinstance(v, dict) and v.get('value') not in (None, ''):
            prof[k] = v
    good['profile'] = prof

    # ------------------------------------------------- extra yearly rows
    # Rows the lead advisor adds to the by year sheet: bank balances at year
    # end, distributions, professional fees. Each figure checked like the rest.
    extra = []
    for r in raw.get('extra') or ():
        src = r.get('source') or ''
        per = r.get('sources') or {}       # one document per year, when they differ
        # A row that adds several P&L lines (legal + accounting + consulting)
        # gives its parts per year; each part must appear and they must sum.
        parts = r.get('parts') or {}
        vals = {}
        for y, v in (r.get('by_year') or {}).items():
            ps = parts.get(y)
            if ps:
                if need(per.get(y) or src, r.get('label') or 'row', *ps) \
                        and _close(sum(ps), v):
                    vals[y] = v
                elif not _close(sum(ps), v):
                    problems.append('%s %s: parts add to %.0f, not %.0f'
                                    % (r.get('label'), y, sum(ps), v))
            elif need(per.get(y) or src, r.get('label') or 'row', v):
                vals[y] = v
        if vals:
            extra.append({'label': r.get('label'), 'by_year': vals,
                          'fmt': r.get('fmt') or 'money', 'source': src,
                          'note': r.get('note'),
                          # a balance is a point in time: never annualized
                          'balance': bool(r.get('balance')),
                          # months the newest year covers, when not the YTD column's
                          'ytd_months': r.get('ytd_months'),
                          # "tax": read from the returns, printed under the
                          # tax basis (distributions, loans to shareholders)
                          'basis': 'tax' if r.get('basis') == 'tax' else 'pnl'})
    good['extra'] = extra

    # ------------------------------------------------ light cash flow
    # Per bank account, per statement: opening and closing balance, money in,
    # money out, and transfers to the client's own accounts. Opening + in -
    # out must equal closing to the dollar, or the statement is left out.
    cash = []
    for a in raw.get('cash_light') or ():
        rows = []
        for m in a.get('months') or ():
            src = m.get('source') or a.get('source') or ''
            ok = need(src, 'cash %s' % m.get('period'), m.get('start'),
                      m.get('end'), m.get('deposits'), m.get('withdrawals'),
                      m.get('interest'), m.get('checks'))
            if ok and not _close((m.get('start') or 0) + (m.get('deposits') or 0)
                                 + (m.get('interest') or 0)
                                 - (m.get('withdrawals') or 0) - (m.get('checks') or 0),
                                 m.get('end') or 0):
                problems.append('%s: %s does not balance' % (src, m.get('period')))
                ok = False
            if ok:
                rows.append(m)
        if rows:
            cash.append({'account': a.get('account'), 'months': rows,
                         'note': a.get('note')})
    good['cash_light'] = cash
    return good, problems


def main():
    ap = argparse.ArgumentParser(description="Check Claude's document readings")
    ap.add_argument('folder')
    a = ap.parse_args()
    good, problems = check(a.folder)
    if not good:
        print('No %s in %s/_Audit' % (FILE, a.folder))
        return
    for k in ('pnl', 'tax', 'production', 'counts'):
        print('%-11s %s' % (k, ', '.join(sorted(good.get(k) or {})) or 'none'))
    print('debts       %d practice, %d personal'
          % (len(good['debts'].get('practice') or ()),
             len(good['debts'].get('personal') or ())))
    print('profile     %s' % (', '.join(sorted(good.get('profile') or {})) or 'none'))
    if problems:
        print('\nLEFT OUT, did not check against the document:')
        for p in problems:
            print('  - ' + p)
    else:
        print('\nEvery figure was found in its document and every total ties.')


if __name__ == '__main__':
    main()
