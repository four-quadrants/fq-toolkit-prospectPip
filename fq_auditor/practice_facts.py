#!/usr/bin/env python3
"""The small Word documents a practice writes its own counts into.

    python3 practice_facts.py "<client folder>"
    python3 practice_facts.py "<client folder>" --json

WHY THESE MATTER MORE THAN THE REPORTS
Three figures on the Prospect Summary -- total patients, new patients, and
doctor days worked -- are not on any Dentrix report in a usable form, and the
office manager types them into a one-line Word document instead.

Days worked is simply absent from the reports. The patient counts look present
but measure something else: the Provider Summary's "Patients Seen" is a
patient-provider pairing, so somebody who saw a hygienist and a dentist is
counted twice. On Oyler's 2024 that column totals 7,698 against the practice's
own figure of 3,164 active patients. Both are correct about their own
question; only one is the row the template asks for.

So where one of these documents exists, it is the source, and the reports are
not consulted for that row at all.

WHAT IT READS
A line of prose: "Total New Patients: 2024- 781 new patients / 2025- 660". The
days-worked document names each doctor, which is also the only place in the
whole folder that says who was producing in which year -- and so the only
independent check on the provider-code mapping.
"""
import os
import re
import sys
import glob
import json
import argparse

# Each: the field, and words that identify the document that carries it.
DOCS = [
    ('total_patients', r'total\s+patients'),
    ('new_patients',   r'(total\s+)?new\s+patients'),
    ('doctor_days',    r'(doctor\s+)?days\s+worked'),
]

YEAR_VALUE = re.compile(r'\b(20\d\d)\s*[-–—:]?\s*([\d,]+)')
DOCTOR = re.compile(r'\bDrs?\.?\s+([A-Z][A-Za-z\'\-]+)')


def _text(path):
    """A .docx as plain lines, without needing Word or a conversion step."""
    try:
        import docx
    except ImportError:
        return []
    try:
        doc = docx.Document(path)
    except Exception:
        return []
    out = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            out.append(' '.join(c.text for c in row.cells))
    return [l.strip() for l in out if l.strip()]


def parse_years(lines):
    """{year: number} from prose like '2024- 781 new patients'."""
    out = {}
    for line in lines:
        for year, val in YEAR_VALUE.findall(line):
            try:
                out.setdefault(year, int(val.replace(',', '')))
            except ValueError:
                pass
    return out


def parse_doctor_days(lines):
    """{doctor: {year: days}} plus the per-year total across doctors.

    The document runs "Dr Cardosi 2024- 185 days / 2025- 132 days / Dr Martini
    ...", so a doctor's name opens a block and the year lines beneath belong to
    them until the next name.
    """
    by_doctor, current = {}, None
    for line in lines:
        m = DOCTOR.search(line)
        if m:
            current = m.group(1)
            by_doctor.setdefault(current, {})
            # The same line usually carries that doctor's first year too.
            line = line[m.end():]
        for year, val in YEAR_VALUE.findall(line):
            if current is None:
                continue
            try:
                by_doctor[current].setdefault(year, int(val.replace(',', '')))
            except ValueError:
                pass
    totals = {}
    for years in by_doctor.values():
        for year, days in years.items():
            totals[year] = totals.get(year, 0) + days
    return by_doctor, totals


def find_docs(folder):
    """{field: path} for the count documents in a client folder."""
    found = {}
    for root, _dirs, files in os.walk(folder):
        if os.path.basename(root).startswith('.'):
            continue
        for name in files:
            if not name.lower().endswith('.docx') or name.startswith('~$'):
                continue
            stem = os.path.splitext(name)[0].lower()
            for field, pat in DOCS:
                if field in found or not re.search(pat, stem, re.I):
                    continue
                # "Total New Patients" matches both patient patterns; the more
                # specific one wins, so new patients is tested first on a name
                # that says "new".
                if field == 'total_patients' and 'new' in stem:
                    continue
                found[field] = os.path.join(root, name)
    return found


def gather(folder):
    """Everything these documents state, keyed by field then year."""
    out = {'by_year': {}, 'doctor_days': {}, 'sources': {}}
    docs = find_docs(folder)
    for field, path in docs.items():
        lines = _text(path)
        if not lines:
            continue
        out['sources'][field] = os.path.basename(path)
        if field == 'doctor_days':
            by_doctor, totals = parse_doctor_days(lines)
            out['doctor_days'] = by_doctor
            for year, v in totals.items():
                out['by_year'].setdefault(year, {})['doctor_days'] = v
        else:
            for year, v in parse_years(lines).items():
                out['by_year'].setdefault(year, {})[field] = v
    return out


def main():
    ap = argparse.ArgumentParser(description="The practice's own stated counts")
    ap.add_argument('folder')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    got = gather(a.folder)
    if a.json:
        print(json.dumps(got, indent=1))
        return
    if not got['sources']:
        print('No count documents in %s' % a.folder)
        return
    for field, name in sorted(got['sources'].items()):
        print('  %-16s %s' % (field, name))
    print()
    years = sorted(got['by_year'])
    print('  %-18s %s' % ('', '  '.join('%8s' % y for y in years)))
    for field in ('total_patients', 'new_patients', 'doctor_days'):
        row = ['%8s' % got['by_year'].get(y, {}).get(field, '-') for y in years]
        print('  %-18s %s' % (field, '  '.join(row)))
    if got['doctor_days']:
        print('\n  days by doctor')
        for doc, years_ in sorted(got['doctor_days'].items()):
            print('    %-12s %s' % (doc, ', '.join(
                '%s: %s' % (y, d) for y, d in sorted(years_.items()))))


if __name__ == '__main__':
    main()
