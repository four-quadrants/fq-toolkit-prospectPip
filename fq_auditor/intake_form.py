#!/usr/bin/env python3
"""Read the IC Form submission that starts every prospect file.

    python3 intake_form.py "<client folder>"            # show what it found
    python3 intake_form.py "<client folder>" --json

WHY THIS AND NOT THE CALL NOTES
The Prospect Summary's left column is the client's own account of themselves —
age, ownership, chairs, payer mix, what they think their overhead is, what they
think they need to retire. None of it is in a financial document, so for a while
the only source was a case summary somebody typed up by hand.

That summary says at the top where it came from: "Compiled from CE intake
worksheet and initial call transcript". The worksheet is a HubSpot form and it
arrives as an email, label on one line and answer on the next, which is as
structured as anything the client sends. The call transcript is the other half
and cannot be read at all — the Otter email is a share link, so the words live
behind a login.

So this reads the half that is readable, and the summary says plainly that the
rest needs a person. The point is not to replace the analyst; it is to stop them
retyping thirty answers the client already typed.

WHAT IT WILL NOT DO
Guess. A question the form did not ask comes back absent, not inferred, because
the one thing worse than a blank field in front of a prospect is a confident
wrong one.
"""
import os
import re
import sys
import json
import glob
import email
import email.policy
import argparse

# Each field: where it lands, and the question wording to look for. Matched on a
# distinctive fragment rather than the whole sentence, because the form's
# wording gets edited and a full-string match would silently stop finding a
# field that is still being asked.
FIELDS = [
    ('first_name',        r'^first name$'),
    ('last_name',         r'^last name$'),
    ('email',             r'^email$'),
    ('age',               r'^age$'),
    ('marital_status',    r'^marital status'),
    ('dependents',        r'number of dependents'),
    ('ownership',         r'sole owner or are there partners'),
    ('years_owned',       r'how many years have you owned'),
    ('collections_last',  r'annual collections last year'),
    ('collections_proj',  r'projected collections this year'),
    ('building',          r'rent or own the building'),
    ('building_sqft',     r'what is the sq\.? ?ft'),
    ('building_payment',  r'what is the monthly payment'),
    ('chairs_total',      r'total number of chairs'),
    ('chairs_operative',  r'chairs are operative'),
    ('chairs_hygiene',    r'how many are hygiene'),
    ('chairs_overflow',   r'how many are overflow'),
    ('in_network',        r'insurances in network'),
    ('has_associates',    r'do you have any associates'),
    ('associate_comp',    r'compensation structure for your associate'),
    ('overhead_stated',   r'approximate overhead percentage'),
    ('pms',               r'practice management software'),
    ('take_home',         r'annual take-?home pay or taxable income'),
    ('saved_last_year',   r'how much did you save for retirement'),
    ('saved_liquid',      r'if you walked away today'),
    ('retire_age',        r'retirement age goal'),
    ('retire_target',     r'how much do you think you need'),
    ('retire_basis',      r'how you arrived at your target'),
    ('doctor_days',       r'how many doctor days'),
    ('doctor_booked',     r'booked out at 90% capacity'),
    ('hygiene_days',      r'how many hygiene days'),
    ('hygiene_booked',    r'hygiene department currently booked'),
    ('new_patient_wait',  r'how quickly can a new patient be seen'),
    ('new_patients_mo',   r'new patients do you average'),
    ('cpa_rating',        r'current CPA, how would you rate'),
    ('tax_surprise',      r'owe or are being refunded'),
]

SKIP = re.compile(r'^(email preview|contact|form:|you.ve got a new submission|'
                  r'brian .* submitted|.* submitted a form)', re.I)


def _plain(path):
    """The body of a form-submission email, as lines."""
    with open(path, errors='replace') as fh:
        msg = email.message_from_file(fh, policy=email.policy.default)
    body = msg.get_body(preferencelist=('plain', 'html'))
    if body is None:
        return []
    text = body.get_content()
    text = re.sub(r'<[^>]+>', '\n', text)
    text = re.sub(r'&nbsp;?', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    return [l.strip() for l in text.split('\n') if l.strip()]


def parse(path):
    """{field: answer} for every question the form actually asked.

    The form prints the question on one line and the answer on the next, so a
    field is read as "the line after the one matching this question". An answer
    that is itself a question — the next label — means the client left it blank,
    and it is recorded as absent rather than as that label's text.
    """
    lines = _plain(path)
    if not lines:
        return {}
    questions = [(key, re.compile(pat, re.I)) for key, pat in FIELDS]
    labels = [p for _, p in questions]
    out = {}
    for i, line in enumerate(lines):
        if SKIP.match(line):
            continue
        for key, pat in questions:
            if key in out or not pat.search(line):
                continue
            nxt = lines[i + 1] if i + 1 < len(lines) else ''
            if not nxt or any(p.search(nxt) for p in labels):
                continue              # unanswered; the next line is another question
            out[key] = nxt
            break
    return out


def find_form(folder):
    """The IC form email in a client folder, if one is there."""
    for p in glob.glob(os.path.join(folder, '*.eml')):
        name = os.path.basename(p).lower()
        if 'ic form' in name or 'ic-form' in name:
            return p
    # Fall back to reading them: the file is sometimes named for the client.
    for p in glob.glob(os.path.join(folder, '*.eml')):
        try:
            head = open(p, errors='replace').read(4000)
        except OSError:
            continue
        if 'IC Form' in head or 'HubSpot Form' in head:
            return p
    return None


def money(v):
    """'3,900,000' or '22500.00' as a number, or None."""
    if not v:
        return None
    m = re.search(r'-?[\d,]+(?:\.\d+)?', str(v).replace('$', ''))
    if not m:
        return None
    try:
        return float(m.group(0).replace(',', ''))
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser(description="Read a prospect's IC form")
    ap.add_argument('folder')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    path = find_form(args.folder)
    if not path:
        print('No IC form email in %s' % args.folder)
        return
    got = parse(path)
    if args.json:
        print(json.dumps(got, indent=1))
        return
    print('From %s\n' % os.path.basename(path))
    for key, _ in FIELDS:
        print('  %-18s %s' % (key, got.get(key, '—')))
    missing = [k for k, _ in FIELDS if k not in got]
    if missing:
        print('\n  not answered on the form: %s' % ', '.join(missing))


if __name__ == '__main__':
    main()
