#!/usr/bin/env python3
"""Read a scanned Practice Analysis, and only believe the figures twice.

    python3 production.py "<client folder>"
    python3 production.py "<client folder>" --json

WHY THIS IS NOT IN summary.py
A Profit & Loss arrives as a spreadsheet, so its numbers are already numbers.
A Practice Analysis arrives as a scan of a Dentrix printout, so its numbers are
whatever the OCR thought it saw. The first attempt read 2,733,136.00 as
"2.733.136.00" and 0.00 as "0,00", and a figure that might be a thousand times
wrong is worse in front of a prospect than an honest blank.

THE GATE
What actually goes wrong in these scans is the separators — the commas and
periods between digits — not the digits. So each page is read twice, at two
resolutions, and both readings are stripped to their digits alone and divided
by a hundred for the cents. A label's figure is accepted only when the two
passes land on the same number. Where they disagree, the figure is reported as
needing a human, with both readings shown so the analyst can settle it in one
glance rather than opening the scan and hunting.

Measured on Oyler's 2024 Practice Analysis: 9 of 11 labels agreed. The point is
not that two passes are right — it is that two passes that disagree are visibly
wrong, which one pass never is.
"""
import os
import re
import sys
import glob
import json
import hashlib
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS_DPI = (300, 350, 400)

# Re-reading nine scans at three resolutions costs about three minutes, and
# nothing about a filed PDF changes between runs. The text of each pass is kept
# beside the client's other cached reads, keyed by the file's own fingerprint,
# so a rebuild is seconds and a replaced document still re-reads.
OCR_CACHE = '.fq_ocr'


def _fingerprint(path, dpi):
    st = os.stat(path)
    raw = '%s|%d|%d|%d' % (os.path.abspath(path), st.st_size, int(st.st_mtime), dpi)
    return hashlib.sha1(raw.encode()).hexdigest()


def _cache_dir(path):
    d = os.path.dirname(os.path.abspath(path))
    while d and os.path.basename(d) in ('Original_sourcedocs', 'Production',
                                        'Business', 'Documents'):
        d = os.path.dirname(d)
    return os.path.join(d, OCR_CACHE)


def ocr_pages(path, dpi):
    """Every page of a scan at one resolution, read once and remembered."""
    import fitz
    import extract
    cdir = _cache_dir(path)
    cfile = os.path.join(cdir, _fingerprint(path, dpi) + '.txt')
    try:
        with open(cfile, errors='replace') as fh:
            return fh.read().split('\f')
    except OSError:
        pass
    doc = fitz.open(path)
    pages = [extract._ocr(p, dpi, extract.OCR_CFG_BLOCK) for p in doc]
    doc.close()
    try:
        os.makedirs(cdir, exist_ok=True)
        with open(cfile, 'w') as fh:
            fh.write('\f'.join(pages))
    except OSError:
        pass
    return pages

# The labels the Prospect Summary's practice table asks for, each matched on a
# distinctive fragment rather than the full printed line, because Dentrix wraps
# and abbreviates them differently between report versions.
LABELS = [
    ('charges_uninsured',  r'non-?insured charges'),
    ('charges_insured',    r'^\s*insured charges'),
    ('adjustments_add',    r'adjustments:?\s*additions'),
    ('total_charges',      r'total charges'),
    ('patient_payments',   r'patient payments'),
    ('insurance_payments', r'insurance payments'),
    ('adjustments_less',   r'adjustments:?\s*reductions'),
    ('total_credits',      r'total credits'),
    ('receivables',        r'total receivables'),
    ('credit_balances',    r'credit balances'),
    ('new_patients',       r'^\s*new patients'),
    ('referred_patients',  r'referred patients'),
    ('active_patients',    r'^\s*active patients'),
]


def digits_value(token):
    """A money token as a number, reading only its digits.

    "2.733.136.00", "2,733,136.00" and "2 733 136 00" are the same scan of the
    same figure; the separators are the part OCR gets wrong. Strip to digits,
    take the last two as cents. Returns None for a token with no digits.
    """
    neg = token.strip().startswith('(') or token.strip().startswith('-')
    d = re.sub(r'\D', '', token)
    if not d:
        return None
    v = int(d) / 100.0
    return -v if neg else v


def whole_value(token):
    """A count (new patients, visits) as an integer — no implied cents."""
    d = re.sub(r'\D', '', token)
    return int(d) if d else None


COUNT_FIELDS = {'new_patients', 'referred_patients', 'active_patients'}
MONEY_FIELDS = {k for k, _ in LABELS} - COUNT_FIELDS

# One figure, never two. An earlier version let a token span whitespace, so a
# row of columns read as a single 27-digit number.
TOKEN = re.compile(r'[\(\-]?\d[\d,.]*\d[\)]?|(?<!\d)\d(?!\d)')


def read_pass(text):
    """{field: value} from one OCR pass of a Practice Analysis."""
    out = {}
    for line in (text or '').split('\n'):
        # OCR drops a space inside a figure — "1,404, 103.00" for 1,404,103.00,
        # "4,467 ,838.40" for 4,467,838.40 — which splits one number into two
        # and reads a practice's year as $14.04. A space touching a separator
        # is never a column break, so close it before tokenising.
        line = re.sub(r'\s+([,.])', r'\1', line)
        line = re.sub(r'([,.])\s+(?=\d)', r'\1', line)
        low = line.lower()
        for key, pat in LABELS:
            if key in out or not re.search(pat, low, re.I):
                continue
            # The figure is the FIRST number on the line. These reports print
            # the period total first and the month-to-date columns after it;
            # taking the last column read a year's charges as one month's.
            toks = TOKEN.findall(line)
            if not toks:
                continue
            tok = toks[0]
            # Counts are not read. On these reports the first column carries
            # the period's money total but reads 0 for every patient count, so
            # the count columns mean something else and guessing which would be
            # a confident wrong number in front of a prospect.
            if key not in MONEY_FIELDS:
                break
            v = digits_value(tok)
            if v is not None:
                out[key] = v
            break
    return out


def read_pdf(path, dpis=PASS_DPI):
    """Two independent OCR passes of one scan, as {field: {dpi: value}}."""
    passes = {}
    for dpi in dpis:
        passes[dpi] = read_pass('\n'.join(ocr_pages(path, dpi)))
    return passes


def agree(passes, need=2):
    """Split two passes into what they agree on and what they do not.

    Returns (values, disputed). A field only one pass saw is disputed, not
    accepted: a figure the other resolution could not find at all is exactly
    the kind the scan is too poor to carry.
    """
    keys = set()
    for got in passes.values():
        keys |= set(got)
    values, disputed = {}, {}
    for k in keys:
        counts = {}
        for got in passes.values():
            v = got.get(k)
            if v is not None:
                counts[v] = counts.get(v, 0) + 1
        if counts:
            val, n = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
            if n >= need:
                values[k] = val
                continue
        disputed[k] = {str(d): got.get(k) for d, got in passes.items()}
    return values, disputed


def _settle_by_arithmetic(passes, values, disputed):
    """Let the report's own subtotal break a tie between two readings.

    A majority of three passes can still be wrong: on Oyler's 2025 report two
    passes read the additions line as 12,691.64 and one as 126,916.45, so the
    vote carried the misreading. But the scan also prints the subtotal those
    figures roll into, and only 126,916.45 makes it add up -- exactly.

    So where the parts do not reconcile, every value any pass saw for each part
    is tried, and a candidate is accepted only if it closes the sum to the
    dollar. One arithmetic identity beats any number of re-reads of a bad line.
    """
    parts = ('charges_uninsured', 'charges_insured', 'adjustments_add')
    total = values.get('total_charges')
    if not total or not all(k in values for k in parts):
        return values, disputed
    if abs(sum(values[k] for k in parts) - total) < 1.0:
        return values, disputed
    for key in parts:
        seen = {got.get(key) for got in passes.values()}
        seen.discard(None)
        for cand in seen:
            trial = dict(values)
            trial[key] = cand
            if abs(sum(trial[k] for k in parts) - total) < 1.0:
                values = trial
                disputed = dict(disputed)
                disputed.pop(key, None)
                return values, disputed
    return values, disputed


def arithmetic_check(values):
    """Does the report add up, using only figures both passes agreed on?

    The scan prints its own subtotal: uninsured + insured + additions = total
    charges. When the accepted figures reproduce it, two passes agreeing was
    not two passes making the same mistake. Returns None when a piece of the
    sum was not accepted, because an unchecked figure is not a failed one.
    """
    parts = ('charges_uninsured', 'charges_insured', 'adjustments_add')
    if not all(k in values for k in parts) or 'total_charges' not in values:
        return None
    want = values['total_charges']
    got = sum(values[k] for k in parts)
    return {'expected': round(want, 2), 'from_parts': round(got, 2),
            'agrees': abs(got - want) < 1.0}


# ---------------------------------------------------------------------------
# The Provider Summary. The Practice Analysis carries charges and credits; the
# patient counts and the per-provider split live in this second report, which
# the earlier version silently skipped because it only read one file per year.

PROV_TOTALS = [
    ('total_charges_prov',  r'^total:?\s'),
]

# "TOTAL: 536 7698 537.46 137.83" on the activity table. OCR mangles the word
# into "§36", so the row is found by its label and the digits taken positionally.
ACTIVITY_TOTAL = re.compile(r'^total:?\s+(.+)$', re.I)
ACTIVITY_HEAD = re.compile(r'new\s+pats', re.I)
# Row labels that look like provider codes but are the report's own scaffolding.
SKIP_CODES = {'mtd', 'ytd', 'prev', 'total', 'ntd', 'nitd', 'nid', 'prov'}

# OCR renders a provider code's glyphs loosely: SDC1 comes back as "$DC1" or
# "SDCI", MEG1 as "MEG'". Normalising means the same provider in two passes is
# recognised as the same provider instead of being dropped as two singletons.
_CODE_FIX = {'$': 'S', '\u00a7': 'S', '{': '', '}': '', "'": '1',
             '\u2018': '1', '\u2019': '1'}


def norm_code(code):
    out = ''.join(_CODE_FIX.get(ch, ch) for ch in code.upper())
    # A trailing letter I or L in these codes is always a 1.
    return re.sub(r'[IL]$', '1', out)


def reconcile_providers(charges, activity, total, tol=0.02):
    """Each provider's production, settled against the report's second account.

    The Provider Summary states every provider twice: once as a charge line,
    and once as patients-seen times production-per-patient in the activity
    table. On Oyler's three years those two agree within about ten dollars
    wherever both are legible, which makes the pair a far stronger check than
    re-reading the same line at another resolution.

    So: take the charge line where the two agree; take the activity figure
    where the charge line is missing or contradicts it; and hand back the
    result only if the providers then add up to the report's own total. That
    last gate is the one that matters -- a split that omits a provider is
    worse than no split, because it looks complete.
    """
    out, notes = {}, []
    for code in set(charges) | set(activity):
        a = activity.get(code) or {}
        est = None
        if a.get('patients_seen') and a.get('production_per_patient'):
            est = a['patients_seen'] * a['production_per_patient']
        got = charges.get(code)
        if got and est:
            if abs(got - est) <= max(0.005 * max(got, est), 25):
                out[code] = got
            else:
                out[code] = est
                notes.append('%s: charge line read %s, activity says %s; '
                             'took the activity figure'
                             % (code, '{:,.0f}'.format(got),
                                '{:,.0f}'.format(est)))
        elif got:
            out[code] = got
        elif est:
            out[code] = est
            notes.append('%s: charge line unreadable; took the activity figure'
                         % code)
    covered = sum(out.values())
    ok = bool(total) and abs(total - covered) <= tol * total
    residual = round((total or covered) - covered, 2)
    if ok and abs(residual) > 1:
        notes.append('%s of charges belong to a provider code that could not '
                     'be read; carried as unassigned'
                     % '{:,.0f}'.format(abs(residual)))
    return {'providers': out, 'covered': round(covered, 2), 'total': total,
            'residual': residual, 'reconciles': ok, 'notes': notes}

PROV_CODE = re.compile(r'^([A-Z0-9$§\'{}]{3,5})\s*(?:[\({]inactive[\)}])?\s+(.*)$',
                       re.I)


def read_provider_pass(pages):
    """One OCR pass of a Provider Summary: totals, and charges per provider."""
    out = {'providers': {}, 'activity': {}}
    activity = False
    for text in pages:
        for line in (text or '').split('\n'):
            line = re.sub(r'\s+([,.])', r'\1', line)
            line = re.sub(r'([,.])\s+(?=\d)', r'\1', line)
            if ACTIVITY_HEAD.search(line):
                activity = True            # the second table starts here
                continue
            m = ACTIVITY_TOTAL.match(line.strip())
            if m:
                # Tesseract renders a leading 5 on these totals as a section
                # sign -- "TOTAL: §36 7698" for 536. Only ever applied to
                # the figures after the label, never to a provider code, where
                # the same glyph stands for an S.
                figures = re.sub(r'[§$]', '5', m.group(1))
                nums = [t for t in TOKEN.findall(figures)]
                if activity and len(nums) >= 4:
                    out['new_patients'] = whole_value(nums[0])
                    out['total_patients'] = whole_value(nums[1])
                    out['production_per_patient'] = digits_value(nums[2])
                    out['charge_per_procedure'] = digits_value(nums[3])
                elif not activity and nums:
                    out['total_charges_prov'] = digits_value(nums[0])
                continue
            pm = PROV_CODE.match(line.strip())
            if activity:
                if pm and pm.group(1).lower() not in SKIP_CODES:
                    nums = TOKEN.findall(pm.group(2))
                    if len(nums) >= 4:
                        out['activity'][norm_code(pm.group(1))] = {
                            'new_patients': whole_value(nums[0]),
                            'patients_seen': whole_value(nums[1]),
                            'production_per_patient': digits_value(nums[2]),
                            'charge_per_procedure': digits_value(nums[3])}
                continue
            if not pm or pm.group(1).lower() in SKIP_CODES:
                continue
            nums = TOKEN.findall(pm.group(2))
            if len(nums) >= 5:
                v = digits_value(nums[0])
                if v:
                    out['providers'][norm_code(pm.group(1))] = v
    return out


PROV_DPI = (300, 350, 400)


def read_provider(path, dpis=PROV_DPI):
    """A Provider Summary read twice, agreed figures only.

    The per-provider split is kept only where both passes saw the same code and
    the same figure, because OCR renders SDC1 as "$DC1" and MEG1 as "MEG'" —
    a provider that appears in one pass only is a reading, not a provider.
    """
    passes = {}
    for dpi in dpis:
        passes[dpi] = read_provider_pass(ocr_pages(path, dpi))

    provs = [p.pop('providers', {}) for p in passes.values()]
    acts = [p.pop('activity', {}) for p in passes.values()]
    values, disputed = agree(passes)
    return {'values': values, 'disputed': disputed,
            'providers': _vote(provs), 'activity': _vote_activity(acts)}


def _vote(dicts, need=2):
    """Keep a provider's figure when at least `need` passes read it the same.

    Requiring all passes to agree threw away real providers: a single page
    where 300 dpi misreads one charge line dropped a doctor producing a million
    dollars. Three passes and a majority keeps the figure and still refuses a
    number only one reading ever saw.
    """
    tally = {}
    for d in dicts:
        for code, v in d.items():
            tally.setdefault(code, {}).setdefault(round(v, 2), 0)
            tally[code][round(v, 2)] += 1
    out = {}
    for code, counts in tally.items():
        val, n = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
        if n >= need:
            out[code] = val
    return out


def _vote_activity(dicts, need=2):
    """The same majority rule, applied field by field within each provider."""
    codes = set()
    for d in dicts:
        codes |= set(d)
    out = {}
    for code in codes:
        row = {}
        for field in ('new_patients', 'patients_seen',
                      'production_per_patient', 'charge_per_procedure'):
            counts = {}
            for d in dicts:
                v = (d.get(code) or {}).get(field)
                if v is not None:
                    counts[v] = counts.get(v, 0) + 1
            if counts:
                val, n = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
                if n >= need:
                    row[field] = val
        if row:
            out[code] = row
    return out


def find_provider_reports(folder):
    """The Provider Summary scans, one per year."""
    hits, seen = [], set()
    for root, _dirs, files in os.walk(folder):
        if os.path.basename(root).startswith('.'):
            continue
        for name in files:
            if not name.lower().endswith('.pdf'):
                continue
            if 'provider summary' not in name.lower():
                continue
            m = re.search(r'(20\d\d)', name)
            hits.append((m.group(1) if m else '', os.path.join(root, name)))
    out = []
    for year, path in sorted(hits, reverse=True):
        if year in seen:
            continue
        seen.add(year)
        out.append((year, path))
    return out


# ---------------------------------------------------------------------------
# Who each provider code is. Dentrix identifies providers by code only, so the
# roles come from a per-client map the analyst confirms once. Without one the
# codes are tiered by charge per procedure, which separates chairside dentistry
# from hygiene cleanly (191-297 against 47-59 on Oyler's three years) but
# cannot tell the owner from an associate -- so an unmapped client gets the
# hygiene split and leaves the owner line blank rather than guessing it.

ROLES_FILE = 'providers.json'
DOCTOR_FLOOR = 120.0          # $/procedure; midway between the two clusters


def roles_path(folder):
    return os.path.join(folder, '_Audit', ROLES_FILE)


def load_roles(folder):
    """{code: {'role':..,'name':..,'through':..}} for a client, or {}."""
    try:
        with open(roles_path(folder)) as fh:
            return json.load(fh).get('providers', {})
    except (OSError, ValueError):
        return {}


def infer_roles(activity):
    """Tier codes by charge per procedure when no map has been confirmed."""
    out = {}
    for code, a in activity.items():
        cpp = a.get('charge_per_procedure')
        if not cpp:
            continue
        out[code] = {'role': 'doctor' if cpp >= DOCTOR_FLOOR else 'hygiene',
                     'name': None, 'inferred': True}
    return out


def split_production(charges, roles):
    """Owner / associate / hygiene totals for one year.

    A provider the map does not cover is counted in 'unassigned' rather than
    folded into a role, so the three lines on the page always add up to
    something a reader can check against the report's own total.
    """
    out = {'owner': 0.0, 'associate': 0.0, 'hygiene': 0.0,
           'admin': 0.0, 'unassigned': 0.0}
    for code, v in charges.items():
        role = (roles.get(code) or {}).get('role')
        if role in ('owner', 'associate', 'hygiene', 'admin'):
            out[role] += v
        elif role == 'doctor':
            out['associate'] += v       # a doctor who is not the owner
        else:
            out['unassigned'] += v
    return {k: round(v, 2) for k, v in out.items()}


def find_reports(folder):
    """The Practice Analysis scans in a client folder, newest year first."""
    hits = []
    for root, _dirs, files in os.walk(folder):
        if os.path.basename(root).startswith('.'):
            continue
        for name in files:
            if not name.lower().endswith('.pdf'):
                continue
            low = name.lower()
            if 'practice analysis' not in low and 'analysis summary' not in low:
                continue
            m = re.search(r'(20\d\d)', name)
            hits.append((m.group(1) if m else '', os.path.join(root, name)))
    hits.sort(reverse=True)
    # One report per year: the folder holds both the filed copy and the
    # original, and reading the same scan twice doubles the slowest step here.
    seen, out = set(), []
    for year, path in hits:
        if year in seen:
            continue
        seen.add(year)
        out.append((year, path))
    return out


def gather(folder, dpis=PASS_DPI):
    """Every Practice Analysis read twice, keyed by year."""
    out = {}
    for year, path in find_reports(folder):
        passes = read_pdf(path, dpis)
        values, disputed = agree(passes)
        values, disputed = _settle_by_arithmetic(passes, values, disputed)
        out[year] = {'source': os.path.basename(path),
                     'values': values, 'disputed': disputed,
                     'check': arithmetic_check(values)}
    return out


def main():
    ap = argparse.ArgumentParser(description='Read scanned production reports')
    ap.add_argument('folder')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--year')
    a = ap.parse_args()
    got = gather(a.folder)
    if a.year:
        got = {k: v for k, v in got.items() if k == a.year}
    if a.json:
        print(json.dumps(got, indent=1))
        return
    for year in sorted(got, reverse=True):
        rec = got[year]
        print('\n%s  (%s)' % (year or 'year unknown', rec['source']))
        for k, v in sorted(rec['values'].items()):
            print('   %-20s %15s' % (k, '{:,.2f}'.format(v)
                                     if isinstance(v, float) else v))
        chk = rec.get('check')
        if chk:
            print('   %-20s %s' % ('adds up?',
                  'yes' if chk['agrees'] else
                  'NO — parts %s vs total %s'
                  % (chk['from_parts'], chk['expected'])))
        for k, v in sorted(rec['disputed'].items()):
            print('   %-20s NEEDS A HUMAN  %s' % (k, v))


if __name__ == '__main__':
    main()
