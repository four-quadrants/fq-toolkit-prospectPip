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


SCAN_NAME = re.compile(r'casey notes|ic form|ic-form|fast track|intake form', re.I)
SCAN_EXT = ('.pdf', '.jpg', '.jpeg', '.png', '.heic', '.tif', '.tiff')
IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.heic', '.tif', '.tiff')


def _client_of(path):
    d = os.path.dirname(os.path.abspath(path))
    if os.path.basename(d).lower().startswith('original'):
        d = os.path.dirname(d)
    return d


def find_scan(folder):
    """A printed-and-annotated IC form: a PDF scan or phone photos.

    Spaulding's arrived as "Casey notes.pdf", Rebol's as "Casey notes.jpeg"
    plus three IMG_ photos of the other pages, all with Casey's handwriting
    on them. Photos taken together sit together, so every image beside the
    named one is taken as another page of it.
    """
    for d in (folder, os.path.join(folder, 'Original_sourcedocs')):
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for n in names:
            if n.lower().endswith(SCAN_EXT) and SCAN_NAME.search(n):
                return os.path.join(d, n)
    return None


def scan_pages(path):
    """The named scan, plus the photos beside it if it is a photo."""
    if not path.lower().endswith(IMAGE_EXT):
        return [path]
    d = os.path.dirname(path)
    return [path] + [os.path.join(d, n) for n in sorted(os.listdir(d))
                     if n.lower().endswith(IMAGE_EXT)
                     and os.path.join(d, n) != path]


def parse_scan(path):
    """Read a scanned or photographed IC form by asking Claude to look at it.

    OCR cannot: the pages are rotated photos with handwriting across the
    printed answers. Claude reads the printed answer for each question and,
    separately, Casey's handwritten notes, which carry the pain points.
    Cached in the client's _Audit/ic_form.json against the files' sizes and
    dates, so it is asked once per form.
    """
    pages = scan_pages(path)
    client = _client_of(path)
    stamp = {os.path.basename(p): [os.path.getsize(p), int(os.path.getmtime(p))]
             for p in pages}
    cache = os.path.join(client, '_Audit', 'ic_form.json')
    try:
        with open(cache) as fh:
            got = json.load(fh)
        if got.get('files') == stamp:
            return got.get('form') or {}
    except (OSError, ValueError):
        pass

    try:
        import ask_claude
    except ImportError:
        return {}
    if not ask_claude.available():
        return {}
    keys = '\n'.join('  "%s": the answer to the question matching /%s/'
                     % (k, pat) for k, pat in FIELDS)
    prompt = """These files are a dental prospect's "IC Form Fast Track", a HubSpot form
printed out and annotated by hand. Some are photos taken sideways. Read every
page with the Read tool:
%s

Each printed question is followed by the client's printed answer. Reply with
only JSON:
{
  "fields": {
%s
  },
  "statements": [["the printed true/false statement", "the printed answer"]],
  "challenges": "the printed answer to 'What are your Top 3+ Challenges', or null",
  "handwritten": ["each handwritten note, transcribed as written"],
  "pain": ["each item written under a handwritten PAIN heading, if any"]
}
Use the PRINTED answer for fields, exactly as printed; null when the question
is not on the pages or was left blank. Never use a handwritten note as a
field's answer. Do not guess at handwriting you cannot read; skip it.""" % (
        '\n'.join('  ' + p for p in pages), keys)
    try:
        ans = ask_claude.ask_json(prompt, add_dirs=[os.path.dirname(path)],
                                  timeout=600)
    except Exception:
        return {}
    if not ans:
        return {}
    form = {k: str(v).strip() for k, v in (ans.get('fields') or {}).items()
            if v not in (None, '', 'null')}
    form['_statements'] = ans.get('statements') or []
    form['_challenges'] = ans.get('challenges')
    form['_handwritten'] = ans.get('handwritten') or []
    form['_pain'] = ans.get('pain') or []
    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, 'w') as fh:
            json.dump({'files': stamp, 'form': form}, fh, indent=1)
    except OSError:
        pass
    return form


def parse(path):
    """{field: answer} for every question the form actually asked.

    The form prints the question on one line and the answer on the next, so a
    field is read as "the line after the one matching this question". An answer
    that is itself a question — the next label — means the client left it blank,
    and it is recorded as absent rather than as that label's text.
    """
    if not path.lower().endswith('.eml'):
        return parse_scan(path)
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


def _emails(folder):
    """Every .eml in the folder and one level below it.

    The IC form sits loose in the client folder before filing and inside
    Original_sourcedocs after it, and a top-level glob alone found it in the
    first case and not the second -- which printed "NEEDS: the client's target
    retirement age" for a client who had answered the question.
    """
    found = list(glob.glob(os.path.join(folder, '*.eml')))
    found += glob.glob(os.path.join(folder, '*', '*.eml'))
    seen, out = set(), []
    for p in found:
        key = os.path.realpath(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def find_form(folder):
    """The IC form email in a client folder, if one is there."""
    for p in _emails(folder):
        name = os.path.basename(p).lower()
        if 'ic form' in name or 'ic-form' in name:
            return p
    # Fall back to reading them: the file is sometimes named for the client.
    for p in _emails(folder):
        try:
            head = open(p, errors='replace').read(4000)
        except OSError:
            continue
        if 'IC Form' in head or 'HubSpot Form' in head:
            return p
    return None


def find_form_near(folder):
    """The client's IC form: in its own folder, or loose in the folder above
    it only when the file names this client.

    The fallback used to be find_form(parent), and find_form reads one level
    down, so from any client folder it searched every OTHER client's folder.
    On 21 October Rebol's and Spaulding's plans were built from Oyler's IC
    form: age 58, retiring at 68, $800,000 take-home, 16 chairs, and his
    email address, all printed as theirs.
    """
    got = find_form(folder) or find_scan(folder)
    if got:
        return got
    parent = os.path.dirname(folder.rstrip('/'))
    base = os.path.basename(folder.rstrip('/')).lower()
    surname = re.split(r'[,\s]+', base.strip())[0] if base.strip() else ''
    if not surname:
        return None
    for p in glob.glob(os.path.join(parent, '*.eml')):
        name = os.path.basename(p).lower()
        if surname in name and ('ic form' in name or 'ic-form' in name):
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
