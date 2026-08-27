"""Cross-document checks: statement series gaps, duplicates, and files whose
content contradicts their filename.

These run across the whole pile rather than document-by-document, and they catch
the things that actually bite in intake:

  * a client sends Jan / Feb / Apr and quietly omits March
  * the same statement arrives twice under two names
  * a file named "Homeowners Insurance" that is really a bank statement -- and,
    worse, is really the very month that looks missing from another series
"""
import re
from collections import defaultdict

from classify import MONTH_NAMES

# how a filename hints at its own content, used ONLY to report a contradiction
# between name and content -- never to classify
FILENAME_HINTS = [
    ('personal_tax_return', r'\b1040\b|individual'),
    ('business_tax_return', r'1120|s-?corp|scorp|corporate'),
    ('w2', r'\bw-?2\b'),
    ('paystub', r'pay\s?stub|paystub'),
    ('payroll_summary', r'payroll'),
    ('bank_statement', r'bank\s?stmt|bank statement|checking|savings|\bmm\b|money market'
                       r'|account[_ ]statement|cash[_ ]?app'),
    ('cc_statement', r'\bcc\b|credit card|visa|mastercard'),
    ('brokerage_statement', r'brokerage|\bira\b|roth|529|401|457|invest'),
    ('credit_report', r'credit report'),
    ('day_sheet', r'day\s?sheet'),
    ('provider_productivity', r'provider productivity|productivity'),
    ('pnl', r'p\s*&\s*l|profit and loss|profitandloss'),
    ('balance_sheet', r'balance\s?sheet|balancesheet'),
    ('life_insurance', r'life'),
    ('disability_insurance', r'disability'),
    ('property_insurance', r'homeowners?|property'),
    ('rental_lease', r'\bleases?\b'),
    ('staff_roster', r'staff roster|roster'),
    ('fee_schedule', r'fee schedule'),
]

# doc types that are near-synonyms; don't cry "mislabeled" across these
EQUIVALENT = [
    {'w2', 'paystub'}, {'bank_statement', 'cc_statement', 'brokerage_statement'},
    {'life_insurance', 'disability_insurance', 'insurance_policy', 'property_insurance',
     'overhead_insurance'},
    {'pnl', 'balance_sheet'},
]


def filename_claims(filename):
    low = filename.lower()
    for dt, pat in FILENAME_HINTS:
        if re.search(pat, low):
            return dt
    return None


def _equivalent(a, b):
    if a == b:
        return True
    return any(a in grp and b in grp for grp in EQUIVALENT)


def find_mislabeled(docs):
    """Files whose OCR'd content disagrees with what the filename claims."""
    out = []
    for d in docs:
        claim = filename_claims(d['file'])
        actual = d['doc_type']
        if not claim or actual == 'unknown':
            continue
        if not _equivalent(claim, actual):
            out.append(dict(file=d['file'], claimed=claim, actual=actual, doc=d))
    return out


def find_duplicates(docs):
    """Exact duplicates by content hash, plus near-duplicates that classify to
    the same type / issuer / account / month."""
    exact = defaultdict(list)
    for d in docs:
        exact[d.get('sha256')].append(d)
    groups = [dict(kind='identical', files=[x['file'] for x in v])
              for k, v in exact.items() if k and len(v) > 1]

    seen_hashes = {f for g in groups for f in g['files']}
    near = defaultdict(list)
    for d in docs:
        if d['file'] in seen_hashes or d['doc_type'] == 'unknown':
            continue
        key = (d['doc_type'], d.get('issuer'), d.get('account_tail'),
               d.get('month'), d.get('year'))
        # A shared year is far too weak to call two documents duplicates -- it
        # groups January and April statements together. Require a specific month.
        if key[3] and key[4]:
            near[key].append(d)
    for key, v in near.items():
        if len(v) > 1:
            groups.append(dict(kind='near-identical', files=[x['file'] for x in v],
                               detail=f"same {v[0]['label'].lower()}"
                                      + (f" · {key[1]}" if key[1] else '')
                                      + (f" · x{key[2]}" if key[2] else '')
                                      + (f" · {MONTH_NAMES[key[3]]} {key[4]}" if key[3] else '')))
    return groups


def _months_of(docs):
    out = set()
    for d in docs:
        if d.get('covers'):
            out |= {(int(y), int(m)) for y, m in d['covers']}
        elif d.get('month') and d.get('year'):
            out.add((int(d['year']), int(d['month'])))
    return out


def _merge_close_series(buckets):
    """Merge sub-series that are really one account read inconsistently.

    The account number is the least reliable thing we extract: some banks print
    it in a table where label and value are far apart, some mask it, and OCR
    mangles digits. BancFirst's three statements came out as two different
    accounts, which manufactured a missing month.

    The tell is overlap. A single account never has two statements covering the
    same month, so two sub-series under one institution with DISJOINT months are
    almost certainly the same account. Two sub-series that both contain January
    are genuinely different accounts -- the Bassetts hold three separate Arvest
    accounts -- and must stay apart.
    """
    def compatible(a, b):
        """Could these two sub-series be the same account?"""
        (_, ia, ta, sa), (_, ib, tb, sb) = a, b
        if ia and ib and ia != ib:          # two named institutions: no
            return False
        if sa and sb and sa != sb:          # explicitly opposite sides: no
            return False
        return True

    groups = defaultdict(list)
    for key, docs in buckets.items():
        groups[key.split('|')[0]].append((key, docs))

    merged = {}
    for _, members in groups.items():
        if len(members) == 1:
            merged[members[0][0]] = members[0][1]
            continue
        clusters = []                       # [(key, parts, docs, months)]
        for key, docs in sorted(members, key=lambda kv: -len(kv[1])):
            months = _months_of(docs)
            parts = key.split('|')
            for i, (ck, cparts, cdocs, cmonths) in enumerate(clusters):
                if not (months & cmonths) and compatible(parts, cparts):
                    # keep whichever key carries the most identifying detail
                    best = ck if sum(bool(x) for x in cparts) >= sum(bool(x) for x in parts) else key
                    bestparts = cparts if best == ck else parts
                    clusters[i] = (best, bestparts, cdocs + docs, cmonths | months)
                    break
            else:
                clusters.append((key, parts, list(docs), months))
        for key, _, docs, _ in clusters:
            merged[key] = docs
            tails = {d.get('account_tail') or '?' for d in docs}
            if len(tails) > 1:
                for d in docs:
                    d.setdefault('notes', []).append(
                        "account number read inconsistently across this series ("
                        + ", ".join(sorted(tails))
                        + ") - treated as one account, worth an eyeball")
    return merged


def month_index(year, month):
    return int(year) * 12 + int(month)


# What fraction of the months spanned must actually be present before we believe
# the client is sending a monthly series. Half is deliberately lenient: it passes
# "3 of 5 months" and rejects "7 of 59".
DENSITY = 0.5


def find_series_gaps(docs, min_len=3, exclude_files=()):
    """For every recurring statement series, report months missing between the
    earliest and latest month actually provided.

    Files whose contents contradict their filename are held out. A statement
    hiding under an insurance declaration's name has not really been "provided"
    until a human confirms what it is, so we still report the month as missing
    and separately point at the file that probably fills it.

    Note this only finds INTERIOR gaps -- months between the first and last
    statement given. A series that simply stops early can't be detected here;
    that's the checklist's "previous 4 months" rule's job.
    """
    buckets = defaultdict(list)
    for d in docs:
        if d['file'] in exclude_files:
            continue
        # An annual or year-to-date document is not one month of a monthly
        # series. Three yearly P&Ls dated December 2024, December 2025 and June
        # 2026 were being read as a monthly run with sixteen months missing, and
        # the client was asked to send them.
        if (d.get('granularity') or 'monthly') != 'monthly':
            continue
        if d.get('series_key') and d.get('month') and d.get('year'):
            buckets[d['series_key']].append(d)
    buckets = _merge_close_series(buckets)

    out = []
    for key, group in buckets.items():
        pts = sorted(_months_of(group))
        if len(pts) < min_len:
            continue                     # too short to infer an expected cadence
        lo, hi = month_index(*pts[0]), month_index(*pts[-1])
        have = {month_index(y, m) for y, m in pts}
        missing = [i for i in range(lo, hi + 1) if i not in have]
        if not missing:
            continue

        # Sparse points do not imply a monthly cadence. Seven brokerage
        # statements scattered between August 2021 and June 2026 are not a
        # monthly series with fifty-two gaps — they are whatever the client
        # happened to keep. Demanding the difference produces an email that
        # reads as though nobody looked at the file. Real gaps are dense:
        # "we have Feb, Mar and June but not April or May" is 3 of 5.
        if len(have) < DENSITY * (hi - lo + 1):
            continue
        d0 = group[0]
        out.append(dict(
            series_key=key,
            label=d0['label'],
            issuer=d0.get('issuer'),
            account_tail=d0.get('account_tail'),
            side=d0.get('owner_side'),
            present=[f"{MONTH_NAMES[m]} {y}" for y, m in pts],
            missing=[f"{MONTH_NAMES[i % 12 or 12]} {(i - 1) // 12}" for i in missing],
            files=sorted(d['file'] for d in group)))
    return out


def match_gaps_to_mislabeled(gaps, mislabeled):
    """The nastiest real case: the month that looks missing from one series is
    sitting in the folder under a filename that claims to be something else.
    Point the reviewer straight at it."""
    hits = []
    for g in gaps:
        for m in mislabeled:
            d = m['doc']
            if d.get('doc_type') != g['label'] and d.get('series_key') != g['series_key']:
                # compare on what we know: same type family and the missing month
                pass
            if not (d.get('month') and d.get('year')):
                continue
            stamp = f"{MONTH_NAMES[d['month']]} {d['year']}"
            same_family = _equivalent(d['doc_type'], g['series_key'].split('|')[0])
            if stamp in g['missing'] and same_family:
                hits.append(dict(gap=g, month=stamp, file=d['file'],
                                 claimed=m['claimed'], actual=d['doc_type']))
    return hits


def run_all(docs):
    mis = find_mislabeled(docs)
    gaps = find_series_gaps(docs, exclude_files={m['file'] for m in mis})
    return dict(mislabeled=mis,
                duplicates=find_duplicates(docs),
                gaps=gaps,
                gap_fillers=match_gaps_to_mislabeled(gaps, mis))
