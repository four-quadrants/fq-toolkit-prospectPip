#!/usr/bin/env python3
"""FQ Intake Auditor - main entry point.

Reads a folder of a client's (redacted) documents, reconciles them against that
client's checklist, scans for residual PII, and writes:

  1. <Client> - Internal Audit.docx   full picture for the team, incl. PII
  2. <Client> - Client Email.txt      warm "here's what we still need" message

Runs fully locally and offline. Nothing touches the network.

Typical use:
    python3 audit.py "/path/to/client/folder" --checklist "Checklist.pdf" --client "Bassett"

Two-step use, when you want to correct the parsed checklist first:
    python3 audit.py <folder> --checklist <pdf> --client "Bassett" --review-only
    (edit the checklist_reviewed.json it writes, then re-run without --review-only)
"""
import os
import re
import sys
import json
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import extract                                                      # noqa: E402
from extract import extract_folder                                  # noqa: E402
from classify import classify, describe, MONTH_NAMES                # noqa: E402
from detectors import scan as scan_pii, summarise as pii_summary    # noqa: E402
from reconcile import reconcile                                     # noqa: E402
import series                                                       # noqa: E402


# --------------------------------------------------------------------------
# checklist loading
# --------------------------------------------------------------------------

def find_reviewed_checklist(folder, levels=3):
    """Walk up from the documents folder looking for checklist_reviewed.json.

    A client folder is normally laid out as

        Spaulding_Intake/
            checklist_reviewed.json         <- here
            Original_sourcedocs/            <- what gets passed on the command line
                _Audit/                     <- where the app points --outdir

    so the file can be one, two or three levels above whatever folder the caller
    happens to hand us. Searching only the folder itself meant the app and the
    command line found different checklists for the same client and produced
    different answers — the app fell through to the built-in Bassett list.
    """
    here = os.path.abspath(folder)
    for _ in range(levels + 1):
        cand = os.path.join(here, 'checklist_reviewed.json')
        if os.path.exists(cand):
            return cand
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return None


def load_checklist(checklist_path, folder, force_fallback=False):
    """Prefer a reviewed JSON, then a parsed PDF, then the hardcoded fallback.

    The reviewed JSON is looked for in the docs folder AND its parent, because a
    client folder is normally laid out as

        Spaulding_Intake/
            checklist_reviewed.json     <- here
            Original_sourcedocs/        <- the folder passed on the command line

    and only searching the docs folder meant Spaulding was silently graded
    against the built-in Bassett list — 25 of her items replaced by someone
    else's. A wrong checklist is worse than no checklist, so the fallback now
    announces itself instead of standing in quietly.
    """
    if checklist_path and checklist_path.lower().endswith('.json') and not force_fallback:
        return json.load(open(checklist_path)), f"reviewed checklist ({checklist_path})"

    # A reviewed JSON beats a freshly parsed PDF wherever it is found: it has been
    # corrected by a human, and the parser is guesswork against a layout that
    # varies per client.
    if not force_fallback:
        found = find_reviewed_checklist(folder)
        if found:
            return json.load(open(found)), f"reviewed checklist ({found})"

    if checklist_path and not force_fallback:
        from checklist_parse import parse_checklist
        return parse_checklist(checklist_path), f"parsed from {os.path.basename(checklist_path)}"

    from checklist_bassett import CHECKLIST
    return CHECKLIST, ("BUILT-IN FALLBACK checklist (checklist_bassett.py) — "
                       "this is Bassett's list, not this client's")


def print_checklist_for_review(items, out_path):
    """Write the parsed model out for a human to correct before the audit runs."""
    for it in items:
        it.setdefault('confirmed_unavailable', False)
    with open(out_path, 'w') as fh:
        json.dump(items, fh, indent=2)

    print("\n" + "=" * 74)
    print("PARSED CHECKLIST - please review before the audit runs")
    print("=" * 74)
    for it in items:
        flags = []
        if it.get('optional'):
            flags.append('optional')
        if it.get('confirmed_unavailable'):
            flags.append('confirmed unavailable')
        print(f"\n[{it['section']}] {it['id']}   ({it['kind']}"
              + (f", {', '.join(flags)}" if flags else "") + ")")
        print(f"   asks for : {', '.join(it.get('satisfied_by') or ['?'])}")
        rules = {k: v for k, v in it.items()
                 if k in ('years', 'optional_years', 'count', 'granularity', 'period',
                          'needs_both')}
        if rules:
            print(f"   rules    : {rules}")
        print(f"   client    : {it['client_ask'][:150]}")
        for f in it.get('review_flags', []):
            print(f"   >> CHECK : {f}")
    print("\n" + "-" * 74)
    print(f"Saved to: {out_path}")
    print("Edit that file if anything is wrong, then re-run without --review-only.")
    print("Set \"confirmed_unavailable\": true on an item the client has told us")
    print("they don't have, and it will stop appearing in their email.")
    print("-" * 74 + "\n")


# --------------------------------------------------------------------------
# the audit
# --------------------------------------------------------------------------

_ENTITY_RE = re.compile(
    r'\b([A-Z][A-Za-z&.\'-]+(?:\s+[A-Z][A-Za-z&.\'-]+){0,4}\s+'
    r'(?:PLLC|P\.?L\.?L\.?C|LLC|L\.?L\.?C|P\.?C|Inc\.?|Corp\.?))\b')

# Firms that appear ON the client's documents but are not the client: their CPA,
# their bank, their consultants. Matching these would file the client's personal
# statements as practice documents.
_NOT_THE_CLIENT = re.compile(
    r'\b(bank|insurance|advisors?|accounting|cpa|group|associates|'
    r'management|services|supply|dental supply|title|escrow|mortgage|'
    # Card networks and payment processors. Broadening the harvest pulled in
    # "Visa U.S.A. Inc" and "DEPOSITS CLEARENT LLC" — a card network and a
    # merchant processor. Either one appearing on a personal statement would have
    # filed it as a practice document.
    r'visa|mastercard|amex|american\s+express|discover|clearent|worldpay|'
    r'fiserv|elavon|tsys|stripe|square|paypal|payments?|processing|merchant|'
    r'deposits?|withdrawals?|transfers?|holdings|bancorp|credit\s+union|'
    r'systems|technologies|solutions)\b', re.I)

# Documents whose own face names the practice entity.
_ENTITY_SOURCES = ('business_tax_return', 'pnl', 'balance_sheet', 'payroll_summary',
                   'fee_schedule', 'provider_productivity', 'day_sheet')


def harvest_practice_names(raw, max_names=6):
    """The practice's own entity names, read off documents that state them.

    Deliberately conservative: only reads the first few thousand characters of
    documents whose type already tells us they belong to the practice, and drops
    anything that looks like a third-party firm. A false name here would misfile
    personal statements as practice ones, which is worse than leaving them for a
    human.
    """
    from collections import Counter
    from classify import classify as _classify
    counts, seen_in, issuers = Counter(), {}, set()
    for r in raw:
        try:
            _c = _classify(r['text'], r['file'])
            kind = _c['doc_type']
            # Institutions are already identified by the classifier as issuers.
            # Collecting them here means we do not have to blacklist every bank by
            # name: broadening the harvest pulled in "Cash App Investing LLC" and
            # "Citigroup Inc", which are whose statement it is, not whose money.
            if _c.get('issuer'):
                for w in re.findall(r'[A-Za-z]{3,}', str(_c['issuer'])):
                    issuers.add(w.lower())
        except Exception:
            kind = None
        # Practice-typed documents are read from the head, where the entity is
        # printed. Every OTHER document is read too, but a name found there only
        # counts if it recurs across several files — that is what picked up
        # "RRFD Properties LLC", the rental entity, which is named on its own bank
        # statements and on the lease but appears in no tax return or P&L.
        window = r['text'][:6000] if kind in _ENTITY_SOURCES else r['text'][:20000]
        for m in _ENTITY_RE.findall(window):
            name = ' '.join(m.split())
            if len(name) < 8 or _NOT_THE_CLIENT.search(name):
                continue
            # Drop leading noise words the OCR glued on ("Instructions Rose Rock…").
            name = re.sub(r'^(?:Instructions|Copy|Form|Filing|CPA)\s+', '', name).strip()
            if len(name) < 8:
                continue
            counts[name] += 1
            seen_in.setdefault(name, set()).add(r['file'])
    # From a practice document, one mention is enough. From anywhere else, the
    # name has to turn up in at least two separate files to be believed.
    keep = []
    for n, c in counts.most_common():
        if not (len(seen_in.get(n, ())) >= 2 or c >= 3):
            continue
        words = set(w.lower() for w in re.findall(r'[A-Za-z]{3,}', n))
        if words & issuers:          # names the institution, not the client
            continue
        keep.append(n)
    return keep[:max_names]


_STREET = (r'([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)\s+'
           r'(?:Dr|Drive|St|Street|Ave|Avenue|Blvd|Rd|Road|Ln|Lane|Ct|Court|Way|Pkwy)\b')


def harvest_home_tokens(docs, quiet=False):
    """The family's home street name, read off the personal tax return.

    Used to settle personal-vs-practice on statements that have nothing else to
    go on — savings and money-market statements carry almost no transactions, but
    they are all mailed to the house.

    The street NAME, not a full address: OCR renders "2624 S Black Oak Dr" as
    "2624 § Black Oak Dr", and a strict address pattern misses it entirely.
    """
    from collections import Counter
    hits = Counter()
    for d in docs:
        if d.get('doc_type') != 'personal_tax_return':
            continue
        for name in re.findall(_STREET, (d.get('text') or '')[:8000]):
            n = ' '.join(name.split())
            # Skip anything that is obviously a label rather than a street name.
            if len(n) < 5 or re.search(r'(?i)\b(?:box|suite|ste|apt|unit|no)\b', n):
                continue
            hits[n] += 1
    # ONE token, and only if it recurs. A tax return also carries the preparer's
    # address — taking the top three picked up "Cherry" from the CPA's
    # "501 S. Cherry Street" in Denver, which would have marked any statement
    # mentioning Cherry Street as personal. The client's own address is printed on
    # nearly every page; a preparer's appears once or twice.
    toks = [n for n, c in hits.most_common(1) if c >= 3]
    if toks and not quiet:
        print("  home address: " + "; ".join(toks)
              + "  (from %d mentions)" % hits[toks[0]])
    elif not quiet:
        print("  home address: not established — side inference will not use it")
    return toks


def harvest_household_names(docs, quiet=False):
    """First names of the household, read off the personal tax return.

    Used to put the right person in a filename ("Daniel W-2 2024"). Harvested
    rather than guessed: the return lists the filers and dependents together, so
    the names come from the client's own document.
    """
    from collections import Counter
    surnames = Counter()
    for d in docs:
        if d.get('doc_type') != 'personal_tax_return':
            continue
        for first, last in re.findall(r'\b([A-Z][a-z]{2,})\s+(?:[A-Z]\.?\s+)?([A-Z][a-z]{2,})\b',
                                      (d.get('text') or '')[:8000]):
            surnames[last] += 1
    if not surnames:
        return []
    surname, _ = surnames.most_common(1)[0]
    firsts = Counter()
    for d in docs:
        if d.get('doc_type') != 'personal_tax_return':
            continue
        for m in re.findall(r'\b([A-Z][a-z]{2,})\s+(?:[A-Z]\.?\s+)?' + re.escape(surname) + r'\b',
                            (d.get('text') or '')[:8000]):
            firsts[m] += 1
    people = [n for n, c in firsts.most_common(8) if n.lower() != surname.lower()]
    if people and not quiet:
        print("  household: " + ", ".join(people) + " " + surname)
    return people


def attach_person(docs, people, quiet=False):
    """Whose document is this? Only when exactly one household name appears.

    Ambiguity is left blank on purpose. Two names on a page means a joint document,
    and picking the first would put one spouse's name on the other's statement.
    """
    n = 0
    for d in docs:
        text = d.get('text') or ''
        hits = [p for p in people if re.search(r'\b' + re.escape(p) + r'\b', text)]
        if len(hits) == 1:
            d['person'] = hits[0]
            n += 1
        else:
            d['person'] = None
    if n and not quiet:
        print(f"  attributed {n} document(s) to a single household member")
    return n


STATEMENT_KINDS = ('bank_statement', 'cc_statement', 'brokerage_statement')


def agree_kind_within_account(docs, quiet=False):
    """Make every month of one account agree on what kind of account it is.

    An account does not change from a practice checking account into a personal
    brokerage account for one month and back again. But the classifier reads each
    statement alone, so a month whose header OCRs badly — or which happens to
    carry a page about a sweep fund — can come out differently from its
    neighbours. Fifth Third x8478 read as five months of practice bank statements
    and one month of a personal brokerage statement, which split the series and
    told the client May was missing when it was sitting in the folder.

    So the account decides, by weight of months, and only when the evidence is
    lopsided: a 5-1 split is a misread, a 3-3 split is two real accounts sharing
    a tail and must go to a human untouched.
    """
    from collections import Counter
    by_acct = {}
    for d in docs:
        if d.get('doc_type') not in STATEMENT_KINDS:
            continue
        key = '%s|%s' % ((d.get('issuer') or '').lower(),
                         str(d.get('account_tail') or '').lstrip('xX'))
        if key.strip('|'):
            by_acct.setdefault(key, []).append(d)

    fixed = 0
    for key, group in by_acct.items():
        if len(group) < 3:
            continue
        counts = Counter((d['doc_type'], d.get('owner_side')) for d in group)
        (kind, side), n = counts.most_common(1)[0]
        if n * 2 <= len(group):          # no clear majority — leave it alone
            continue
        for d in group:
            if (d['doc_type'], d.get('owner_side')) == (kind, side):
                continue
            was = d['doc_type']
            d['doc_type'], d['owner_side'] = kind, side
            d['confidence'] = 'medium'
            d.setdefault('notes', []).append(
                'read as %s, but the other %d month(s) of this account are %s '
                '— following the account' % (was.replace('_', ' '), n,
                                             kind.replace('_', ' ')))
            # The series key is built FROM doc_type and side, so it has to be
            # rebuilt or the corrected month stays in its old, lonely series and
            # the gap it caused is still reported.
            from classify import series_key as _series_key
            d['series_key'] = _series_key(d)
            fixed += 1
    if fixed and not quiet:
        print(f"  reconciled {fixed} statement(s) with the rest of their account")
    return fixed


def propagate_issuer_within_series(docs, quiet=False):
    """Fill a missing issuer or account kind from other months of the same account.

    OCR reads the bank's name on three statements out of four. Without this, the
    same account keys as "capital one|2284" one month and "|2284" the next, so a
    rule set on one does not apply to the other. Keying on the tail alone would
    fix the fragmentation but merge genuinely different accounts — Cap 1 HYSA and
    Arvest Platinum both end 5502 in this corpus. Backfilling the issuer keeps the
    key precise instead.
    """
    by_series = {}
    for d in docs:
        if d.get('series_key'):
            by_series.setdefault(d['series_key'], []).append(d)
    filled = 0
    for group in by_series.values():
        for field in ('issuer', 'account_kind', 'account_tail'):
            vals = {d.get(field) for d in group if d.get(field)}
            if len(vals) != 1:
                continue                      # unknown, or the series disagrees
            val = vals.pop()
            for d in group:
                if not d.get(field):
                    d[field] = val
                    d.setdefault('notes', []).append('%s taken from other months of this account' % field)
                    filled += 1
    if filled and not quiet:
        print(f"  filled {filled} missing issuer/kind field(s) from sibling statements")
    return filled


def propagate_side_within_series(docs, quiet=False):
    """Give a statement the side its own series already established.

    Statements for one account arrive as a run of months. If any single month is
    confidently Personal or Practice, the rest of that account is the same
    account — a savings statement with no transactions on it inherits the answer
    from the month that did have evidence.
    """
    by_series = {}
    for d in docs:
        key = d.get('series_key')
        if key:
            by_series.setdefault(key, []).append(d)
    filled = 0
    for key, group in by_series.items():
        sides = {d['owner_side'] for d in group if d.get('owner_side')}
        if len(sides) != 1:
            continue                      # unknown, or the series disagrees with itself
        side = sides.pop()
        for d in group:
            if not d.get('owner_side'):
                d['owner_side'] = side
                d.setdefault('notes', []).append(
                    'side inherited from other months of this account')
                filled += 1
    if filled and not quiet:
        print(f"  {filled} statement(s) took their side from other months of the same account")
    return filled


def audit_folder(folder, checklist, cache_dir=None, workers=None, quiet=False):
    if not quiet:
        print(f"Reading documents in {folder} ...")
    raw = extract_folder(folder, cache_dir=cache_dir, workers=workers, progress=not quiet)

    # classify.infer_side() takes the practice's own entity names as its strongest
    # test, and nothing was ever passing them. Harvest them from the documents we
    # already classify with high confidence — a tax return or P&L names the entity
    # on its face — then use them on the statements that are ambiguous.
    practice_names = harvest_practice_names(raw)
    if practice_names and not quiet:
        print("  practice entities: " + "; ".join(practice_names))

    # The home address needs the personal return classified first, so this is a
    # cheap pre-pass over just the returns.
    _pre = []
    for r in raw:
        try:
            k = classify(r['text'], r['file'])
        except Exception:
            continue
        if k['doc_type'] == 'personal_tax_return':
            _pre.append(dict(doc_type=k['doc_type'], text=r['text']))
    home_tokens = harvest_home_tokens(_pre, quiet=quiet)
    household = harvest_household_names(_pre, quiet=True)

    docs, leaks = [], {}
    for r in raw:
        info = classify(r['text'], r['file'], practice_names=practice_names,
                        home_tokens=home_tokens, household=household)
        info.update(file=r['file'], path=r['path'], sha256=r['sha256'],
                    n_pages=r['n_pages'], n_ocr_pages=r['n_ocr_pages'],
                    text=r['text'])
        docs.append(info)
        findings = scan_pii(r['text'], dedupe=False)
        if not any(f['confidence'] != 'low' for f in findings):
            # nothing but OCR artifacts from numeric tables
            info['pii_noise'] = len(findings)
            continue
        real = findings

        # Tell the reviewer which page. Without this, "there's an SSN in this
        # file" sends someone hunting through a 29-page tax return by hand --
        # and the leak on the Bassett return was on page 26 of 29.
        starts = r.get('page_starts')
        if starts is None and r['n_pages'] > 1:
            # Backfill for caches written before page offsets were recorded. Only
            # for files with findings, and not for ones that would mean a long
            # re-OCR -- a coworker shouldn't hit a silent fifteen-minute pause.
            if r['n_ocr_pages'] <= 40:
                upgraded = extract.add_page_index(
                    r['path'], cache_dir or os.path.join(folder, '.fq_cache'))
                if upgraded:
                    starts = upgraded['page_starts']
                    if len(upgraded['text']) != len(r['text']):
                        real = scan_pii(upgraded['text'], dedupe=False)
            elif not quiet:
                print(f"    ({r['file']}: page numbers need a re-read of "
                      f"{r['n_ocr_pages']} scanned pages - skipped for now)")
        for f in real:
            f['page'] = extract.page_of(f['offset'], starts) if starts else None
            f['n_pages'] = r['n_pages']
        # Merge across occurrences BEFORE discarding noise, so a value that is
        # obvious on one page still contributes the other pages it appears on --
        # otherwise someone re-redacts page 26 and leaves the same SSN on page 24.
        merged = merge_occurrences(escalate_by_page(real))
        keep = [f for f in merged if f['confidence'] != 'low']
        info['pii_noise'] = len(merged) - len(keep)
        if keep:
            leaks[r['file']] = keep

    # Must run after every document is classified, so a month with evidence can
    # lend its side to the months without any. Before reconcile(), which uses side
    # to decide whether a document satisfies a side-scoped checklist item.
    propagate_issuer_within_series(docs, quiet=quiet)
    # After issuers are backfilled, so accounts key correctly first.
    agree_kind_within_account(docs, quiet=quiet)
    propagate_side_within_series(docs, quiet=quiet)
    attach_person(docs, harvest_household_names(docs, quiet=quiet), quiet=quiet)

    cross = series.run_all(docs)
    results, unexpected, facts = reconcile(docs, checklist)
    # Names that contradict their contents drive the rename rules downstream.
    mislabeled = {m['file'] for m in (cross.get('mislabeled') or [])}
    return dict(docs=docs, leaks=leaks, cross=cross, results=results,
                unexpected=unexpected, facts=facts, mislabeled=mislabeled)


def page_list(pages):
    """'11, 12, 13, 14, 15, 18' -> '11-15, 18'. Some of these run to 25 pages."""
    if not pages:
        return ''
    runs, start, prev = [], pages[0], pages[0]
    for p in pages[1:] + [None]:
        if p is not None and p == prev + 1:
            prev = p
            continue
        runs.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = p
    return ", ".join(runs)


def merge_occurrences(findings):
    """One row per distinct value, keeping its most diagnostic occurrence.

    The same SSN typically appears on several pages of a return, and confidence
    depends on which page you judge it from. We keep the best-evidenced sighting
    and list every page the value appears on, so a reviewer can go re-redact all
    of them rather than just the first.
    """
    order = {'high': 0, 'medium': 1, 'low': 2}

    def family(f):
        """The same number gets different labels on different pages -- captioned
        on one, anonymous on another. Group by what it IS, not how it read."""
        if f['digits_seen'] == 9:
            return '9-digit ID'
        return f['kind']

    best = {}
    for f in findings:
        key = (family(f), f['masked'])
        cur = best.get(key)
        if cur is None or order[f['confidence']] < order[cur['confidence']]:
            f = dict(f)
            f['pages'] = set()
            if cur is not None:
                f['pages'] |= cur['pages']
            best[key] = f
            cur = f
        if f.get('page'):
            cur['pages'].add(f['page'])
    out = []
    for f in best.values():
        f['pages'] = sorted(p for p in f['pages'] if p)
        out.append(f)
    return sorted(out, key=lambda f: (order[f['confidence']],
                                      f['pages'][0] if f['pages'] else 0))


def escalate_by_page(findings):
    """If one identifier is confirmed on a page, promote the others on that page.

    Confidence otherwise depends on the CAPTION being legible, which is a weak
    thing to rely on: the Oklahoma Form 511 holds three SSNs, and at one OCR
    resolution "Your Social Security Number" came through as "Seon ae zis",
    leaving two of the three looking like anonymous nine-digit numbers.

    A page that demonstrably leaks one SSN is not a page where the other
    nine-digit numbers deserve the benefit of the doubt.
    """
    pages_with_high = {f.get('page') for f in findings
                       if f['confidence'] == 'high' and f.get('page')}
    if not pages_with_high:
        return findings
    for f in findings:
        if (f['confidence'] == 'medium' and f.get('page') in pages_with_high
                and f['digits_seen'] == 9):
            f['confidence'] = 'high'
            f['why'] = (f['why'] + '; promoted because another identifier is '
                        'confirmed on this same page')
    order = {'high': 0, 'medium': 1, 'low': 2}
    return sorted(findings, key=lambda f: (order[f['confidence']], f.get('page') or 0))


# --------------------------------------------------------------------------
# renderers
# --------------------------------------------------------------------------

# plain-English names for the client's eyes; internal labels are too clinical
FRIENDLY = {
    'bank_statement': 'bank statements',
    'cc_statement': 'credit card statements',
    'brokerage_statement': 'investment account statements',
    'payroll_summary': 'payroll summaries',
    'provider_productivity': 'EagleSoft Provider Productivity reports',
    'day_sheet': 'EagleSoft Day Sheet reports',
    'pnl': 'profit & loss statements',
    'balance_sheet': 'balance sheets',
}


def _as_question(item):
    """Turn a conditional checklist line into something a client can answer.

    "If the practice has a line of credit (LOC), provide bank, limit, rate,
    balance, minimum payment, original date"
        -> "Does the practice have a line of credit? If so, we'll need the bank,
            limit, rate, balance, minimum payment and original date."

    Falls back to the original wording rather than mangling anything it does not
    recognise — a slightly stiff question beats a garbled one.
    """
    ask = (item.get('client_ask') or item.get('label') or '').strip()

    m = re.match(r'\s*if\s+(the\s+practice|you|there)\s+(has|have|is|are)\s+'
                 r'(?:an?\s+)?(.+?)\s*(?:,|\.|;)\s*(.+)$', ask, re.I)
    if m:
        subject = 'the practice' if m.group(1).lower().startswith('the') else 'you'
        verb = 'Does' if subject == 'the practice' else 'Do'
        thing = m.group(3).strip()
        rest = m.group(4).strip().rstrip('.')
        rest = re.sub(r'^(?:please\s+)?provide\s+', '', rest, flags=re.I)
        lead = '' if re.match(r'the\b', rest, re.I) else 'the '
        return f"{verb} {subject} have {_article(thing)}{thing}? If so, we'll need {lead}{rest}."

    # "Most recent written financial plan, if any" -> "Do you have a ...?"
    trimmed = re.sub(r'\s*[,(]?\s*if (?:any|applicable)\.?\)?\s*$', '', ask, flags=re.I)
    if trimmed and trimmed != ask:
        # "Most recent" / "Copy of" belong to a request, not to a question about
        # whether the thing exists at all.
        trimmed = re.sub(r'^(?:a\s+)?(?:copy of|most recent|current)\s+', '',
                         trimmed, flags=re.I).strip()
        low = trimmed[0].lower() + trimmed[1:]
        return f"Do you have {_article(low)}{low}? If so, please send it."
    return ask


def _article(phrase):
    """"a "/"an "/"" for a noun phrase that may already carry a determiner."""
    if re.match(r'(the|a|an|any|your|their)\b', phrase or '', re.I):
        return ''
    return 'an ' if (phrase[:1].lower() in 'aeiou') else 'a '


def render_email(results, cross, client, greeting=None):
    """Warm, paste-ready. Missing + mismatched only.

    Deliberately excludes: satisfied items, anything optional or marked "if
    applicable", every residual-PII finding, account numbers, and any internal
    filename. `guard_email` below enforces that rather than trusting this code.
    """
    wanted = [r for r in results
              if r['status'] in ('mismatched', 'partly satisfied')
              or (r['status'] == 'missing' and not r['item'].get('optional'))]

    # a checklist item we're already asking about shouldn't be repeated as a gap
    asked_types = set()
    for r in wanted:
        asked_types |= set(r['item'].get('satisfied_by') or [])

    L = []
    W = L.append
    W("Subject: A few remaining items for your file\n")
    W(f"Hi {greeting or client},\n")
    W("Thank you for sending everything over - we've been through it all. There "
      "are just a few items still outstanding before we can finish putting your "
      "file together. When you get a chance, could you send:\n")

    for sec in ('Personal', 'Practice'):
        rows = [r for r in wanted if r['item']['section'] == sec]
        if not rows:
            continue
        W(sec)
        for r in rows:
            ask = r['item']['client_ask']
            if r['status'] == 'mismatched':
                ask = _politely_correct(ask, r)
            W(f"  - {ask}")
        W("")

    # Conditional items get a question, not a demand. Asking a client to send a
    # line-of-credit statement they have never had reads as though we have not
    # looked at their file. One yes/no settles each of these permanently.
    asks = [r for r in results if r.get('needs_yes_no')]
    if asks:
        W("And a couple of quick yes/no questions - no documents needed unless "
          "the answer is yes:\n")
        for r in asks:
            W(f"  - {_as_question(r['item'])}")
        W("")

    # count institutions so we can be specific without naming account numbers
    per_issuer = {}
    for g in cross.get('gaps', []):
        key = (g['series_key'].split('|')[0], g.get('issuer'))
        per_issuer[key] = per_issuer.get(key, 0) + 1

    gap_lines = []
    for g in cross.get('gaps', []):
        doc_type = g['series_key'].split('|')[0]
        if doc_type in asked_types:
            continue                        # already asked for above
        what = FRIENDLY.get(doc_type, 'statements')
        if g.get('issuer'):
            what = f"{g['issuer']} {what}"
        elif g.get('side'):
            what = f"{g['side'].lower()} {what}"      # "practice bank statements"
        line = (f"  - Your {what}: we have {_and_list(g['present'])}, "
                f"but not {_and_list(g['missing'])}")
        if per_issuer.get((doc_type, g.get('issuer')), 0) > 1:
            line += " (this is one of two accounts there - happy to confirm which)"
        gap_lines.append(line)

    if gap_lines:
        W("Also, a few statement months look like they didn't come through:")
        L.extend(gap_lines)
        W("")

    W("If any of these don't apply to you, just let us know and we'll take them "
      "off the list. Thanks so much for your help with this.")
    return "\n".join(L) + "\n"


def _and_list(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def guard_email(text, docs):
    """Refuse to emit a client email that leaks anything it shouldn't.

    The PII rule is the one constraint in this tool where a silent failure is
    genuinely costly, so it is enforced on the finished text rather than trusted
    to the code that built it. Returns a list of problems; empty means clean.
    """
    from detectors import scan_residual_pii
    problems = []

    # any confidence level counts here: a client email is short and clean, so
    # there is no benign reason for a nine-digit number to appear in one
    for kind, hits in scan_residual_pii(text).items():
        problems.append(f"{kind} present in the client email: {', '.join(hits[:3])}")

    for d in docs:
        stem = os.path.splitext(d['file'])[0]
        if len(stem) > 6 and stem.lower() in text.lower():
            problems.append(f"internal filename '{d['file']}' appears in the client email")

    if re.search(r'account (?:ending|number|no\.?|#)\s*[:#]?\s*\d', text, re.I):
        problems.append("an account number reference appears in the client email")
    if re.search(r'\bx\d{4}\b', text):
        problems.append("a masked account tail appears in the client email")
    return problems


def _politely_correct(ask, r):
    """Turn a mismatch note into a courteous correction, never a scolding.

    Internal notes cite source filenames ("2 rentals appear on Cash_App_...pdf").
    Those must never reach the client, so the note is rewritten, not appended.
    """
    raw = r['note']
    if 'rental properties appear' in raw:
        return (ask + ". Your tax return shows two rental properties, so we'd need "
                      "the signed lease for each of them")
    # strip any filename the internal note may cite before going near a client
    note = re.sub(r'\s*\([^()]*\.(?:pdf|docx|xlsx|PDF)[^()]*\)', '', raw)
    note = re.sub(r'\s*appear on \S+', ' appear on your tax return', note)
    if 'look like practice accounts' in note:
        return (ask + ". The statements we received look like the practice cards, "
                      "so we're still missing the personal ones")
    if 'look like personal accounts' in note:
        return (ask + ". The statements we received look like personal cards, "
                      "so we're still missing the practice ones")
    if 'annual' in note and 'rather than monthly' in note:
        gap = re.search(r'missing \d+ month\(s\): (.+)$', note)
        extra = f", so we're short {gap.group(1)}" if gap else ""
        return (ask + ". What came through was an annual summary rather than the "
                      "month-by-month detail" + extra)
    if 'not a month-by-month' in note:
        return (ask + ". We received an annual summary rather than the monthly "
                      "detail, so we'd need the month-by-month version")
    if note.startswith('missing') and 'month(s)' in note:
        detail = note.split(':', 1)[1].strip() if ':' in note else ''
        return ask + f". We have most of these already - the gap is {detail}"
    if 'no Day Sheet' in note or 'no Provider Productivity' in note:
        return ask + f". {note[0].upper()}{note[1:]}, so we're just missing that half"
    if 'still need' in note:
        return ask + f" ({note})"
    if 'of the' in note and 'requested months' in note:
        return ask + f" - {note}"
    if 'provided' in note:
        return ask + f" ({note})"
    return ask + (f" ({note})" if note else "")


def render_internal_md(res, client, checklist_source):
    docs, results = res['docs'], res['results']
    cross, leaks = res['cross'], res['leaks']
    L = []
    W = L.append
    counts = {}
    for r in results:
        counts[r['status']] = counts.get(r['status'], 0) + 1

    W(f"# Intake Audit - {client}")
    W(f"_{datetime.date.today().isoformat()} · {len(docs)} documents · "
      f"{sum(d['n_pages'] for d in docs)} pages "
      f"({sum(d['n_ocr_pages'] for d in docs)} OCR'd) · checklist: {checklist_source}_\n")
    W(f"**{counts.get('satisfied', 0)} satisfied · {counts.get('mismatched', 0)} mismatched · "
      f"{counts.get('missing', 0)} missing · {len(res['unexpected'])} unexpected · "
      f"{len(cross['gaps'])} series with gaps · {len(leaks)} files with residual PII**\n")

    for title, statuses in (("Satisfied", ['satisfied']),
                            ("Mismatched - arrived, but wrong scope", ['mismatched']),
                            ("Missing", ['missing'])):
        W(f"\n## {title}")
        rows = [r for r in results if r['status'] in statuses]
        if not rows:
            W("- (none)")
        for sec in ('Personal', 'Practice'):
            srows = [r for r in rows if r['item']['section'] == sec]
            if not srows:
                continue
            W(f"\n**{sec}**")
            for r in srows:
                note = f" — {r['note']}" if r['note'] else ""
                src = ("  [" + ", ".join(d['file'] for d in r['docs']) + "]") if r['docs'] else ""
                W(f"- {r['item']['label']}{note}{src}")

    W("\n## Statement series with missing months")
    if cross['gaps']:
        for g in cross['gaps']:
            head = g['label'] + (f" · {g['issuer']}" if g['issuer'] else '')
            head += f" · x{g['account_tail']}" if g['account_tail'] else ''
            W(f"- **{head}** — have {', '.join(g['present'])}; "
              f"**missing {', '.join(g['missing'])}**")
    else:
        W("- (none)")

    if cross['gap_fillers']:
        W("\n### A missing month may already be here under a wrong name")
        for h in cross['gap_fillers']:
            W(f"- {h['month']} of {h['gap']['label']} — `{h['file']}` is named like a "
              f"{h['claimed'].replace('_', ' ')} but its contents are a "
              f"{h['actual'].replace('_', ' ')} for that month")

    W("\n## Content does not match the filename")
    if cross['mislabeled']:
        for m in cross['mislabeled']:
            W(f"- `{m['file']}` — filename suggests {m['claimed'].replace('_', ' ')}, "
              f"contents are **{m['actual'].replace('_', ' ')}**")
    else:
        W("- (none)")

    W("\n## Duplicates")
    if cross['duplicates']:
        for d in cross['duplicates']:
            W(f"- {d['kind']}: {', '.join('`%s`' % f for f in d['files'])}"
              + (f" — {d['detail']}" if d.get('detail') else ''))
    else:
        W("- (none)")

    W("\n## Unexpected - provided but not on the checklist")
    if res['unexpected']:
        for d in sorted(res['unexpected'], key=lambda x: x['doc_type']):
            W(f"- `{d['file']}` — {describe(d)}")
    else:
        W("- (none)")

    if res['facts']:
        W("\n## Cross-checks")
        if res['facts'].get('rental_property_count'):
            W(f"- {res['facts']['rental_property_source']} shows "
              f"{res['facts']['rental_property_count']} rental properties, so that many "
              f"leases are genuinely expected.")

    W("\n## Residual PII — INTERNAL ONLY")
    W("_Never send this section, or anything derived from it, to a client. "
      "Re-redact any file listed here before it leaves the firm._\n")
    W("_Values are shown masked to the last four digits. A finding only fires on "
      "six or more digits, so it always means the document contains more than a "
      "last-four. Low-confidence matches (OCR artifacts from numeric tables) are "
      "counted but not listed._\n")
    n_high = sum(1 for v in leaks.values() for f in v if f['confidence'] == 'high')
    hi_files = sum(1 for v in leaks.values() if any(f['confidence'] == 'high' for f in v))
    noise = sum(d.get('pii_noise', 0) for d in docs)
    W(f"**{n_high} high-confidence finding(s) in {hi_files} file(s)** — start here. "
      f"A further {len(leaks) - hi_files} file(s) have lower-confidence matches only; "
      f"{noise} likely OCR artifact(s) suppressed.\n")
    if leaks:
        for fname, findings in sorted(leaks.items()):
            hi = [f for f in findings if f['confidence'] == 'high']
            med = [f for f in findings if f['confidence'] == 'medium']
            W(f"\n**{fname}**")
            for f in hi:
                pages = f.get('pages') or ([f['page']] if f.get('page') else [])
                where = (f"**page{'s' if len(pages) > 1 else ''} "
                         f"{page_list(pages)} of {f['n_pages']}**"
                         if pages else "page not recorded")
                W(f"- {where} — **{f['kind']}** `{f['masked']}` "
                  f"({f['digits_seen']} digits present) — {f['why']}")
                W(f"    - context: `{f['context']}`")
            if med:
                W(f"- {len(med)} lower-confidence match(es): "
                  + ", ".join(f"{f['kind']} `{f['masked']}`" for f in med[:6])
                  + (" ..." if len(med) > 6 else ""))
    else:
        W("- None detected.")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="FQ document intake auditor (offline)")
    ap.add_argument('folder', help="folder of the client's redacted documents")
    ap.add_argument('--checklist', help="that client's checklist PDF")
    ap.add_argument('--client', default='the client', help="client name, for the report and email")
    ap.add_argument('--greeting', default=None,
                    help='how to address them in the email, e.g. "Dr. Bassett" or "Sara and Daniel"'
                         ' (defaults to --client, which is usually a surname and reads oddly)')
    ap.add_argument('--outdir', default=None, help="where to write outputs (default: the folder)")
    ap.add_argument('--cache', default=None, help="OCR cache dir (default: <folder>/.fq_cache)")
    ap.add_argument('--redacted-dir', default=None,
                    help="folder of redacted copies, used for the review page's preview "
                         "images (default: a sibling folder starting 'redacted-batch')")
    ap.add_argument('--previews', choices=['redacted', 'none', 'originals'], default='redacted',
                    help="what the review page's previews show. 'redacted' (default) never "
                         "puts an identifier in the page; 'originals' does and is unsafe to share")
    ap.add_argument('--file-them', action='store_true',
                    help="actually move the redacted copies into Personal/ and Business/. "
                         "Without this the filing plan is only reported.")
    ap.add_argument('--decisions', default=None,
                    help="decisions.json exported from a previous Intake Review page; "
                         "human filing calls, keyed by file content hash")
    ap.add_argument('--workers', type=int, default=None, help="parallel OCR workers")
    ap.add_argument('--review-only', action='store_true',
                    help="parse the checklist, print it for review, and stop")
    ap.add_argument('--fallback-checklist', action='store_true',
                    help="ignore the PDF and use the built-in hardcoded checklist")
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()

    if not os.path.isdir(a.folder):
        sys.exit(f"Not a folder: {a.folder}")
    # Point at the client folder and we look inside it for the documents.
    #
    # The documents live in Original_sourcedocs; the client folder is what a
    # person naturally picks, and it is also what the filing tree gets built in.
    # Reading a folder is non-recursive, so choosing the client folder used to
    # produce "0 of 0 already cached" followed by a confident "5 satisfied · 17
    # missing" — a completely empty run that looked like a real answer. Silently
    # wrong is the worst outcome available here.
    if not a.folder.rstrip('/').lower().endswith('original_sourcedocs'):
        inner = os.path.join(a.folder, 'Original_sourcedocs')
        if os.path.isdir(inner):
            print("Documents are in Original_sourcedocs — reading those.")
            a.folder = inner

    outdir = a.outdir or a.folder
    os.makedirs(outdir, exist_ok=True)

    checklist, source = load_checklist(a.checklist, outdir, a.fallback_checklist)
    if 'BUILT-IN FALLBACK' in source and not a.fallback_checklist:
        # Grading one client against another's checklist produces a confident,
        # completely wrong answer. Say so where it cannot be missed.
        print("\n" + "!" * 74)
        print("  No checklist found for this client — using the built-in Bassett list.")
        print("  Every 'missing' and 'unexpected' below is measured against the")
        print("  WRONG list. Build this client's checklist first:")
        print("      python3 lb_checklist.py <client folder>")
        print("  ...or pass one with --checklist <path to .json or .pdf>.")
        print("!" * 74 + "\n")

    if a.review_only:
        print_checklist_for_review(checklist, os.path.join(outdir, 'checklist_reviewed.json'))
        return

    res = audit_folder(a.folder, checklist, cache_dir=a.cache,
                       workers=a.workers, quiet=a.quiet)

    safe = "".join(c for c in a.client if c.isalnum() or c in " -_").strip() or "Client"
    md_path = os.path.join(outdir, f"{safe} - Internal Audit.md")
    docx_path = os.path.join(outdir, f"{safe} - Internal Audit.docx")
    eml_path = os.path.join(outdir, f"{safe} - Client Email.txt")

    md = render_internal_md(res, a.client, source)
    open(md_path, 'w').write(md)

    email = render_email(res['results'], res['cross'], a.client, a.greeting)
    problems = guard_email(email, res['docs'])
    if problems:
        # never write a leaky email to disk where someone might paste it
        print("\n!! The client email was NOT written - it would have leaked:")
        for p in problems:
            print(f"   - {p}")
        print("   (this is a bug in the email renderer; the internal report is still fine)")
    else:
        open(eml_path, 'w').write(email)
    try:
        from render_docx import build_docx
        build_docx(res, a.client, source, docx_path)
    except Exception as e:
        print(f"(docx render failed: {e})")

    red_dir = a.redacted_dir
    decisions = {}
    if a.decisions:
        try:
            import json as _json
            with open(a.decisions) as fh:
                decisions = _json.load(fh) or {}
            n_files = len((decisions.get('files') if isinstance(decisions, dict) else None)
                          or (decisions if 'accounts' not in (decisions or {}) else {}) or {})
            n_accts = len((decisions.get('accounts') if isinstance(decisions, dict) else None) or {})
            print(f"  carried your decisions from {a.decisions}"
                  f" — {n_files} document(s), {n_accts} account rule(s)")
        except Exception as e:
            print(f"(could not read --decisions {a.decisions}: {e})")

    html_path = os.path.join(outdir, f"{safe} - Intake Review.html")
    memo_path = os.path.join(outdir, f"{safe} - Needs Clarification.docx")
    log_path = None
    try:
        from render_html import (build_html, build_plan, build_clarification,
                                 write_clarification_docx)
        if red_dir is None and a.previews == 'redacted':
            # Look for a sibling redacted batch next to the folder being audited.
            parent = os.path.dirname(os.path.abspath(a.folder)) or '.'
            cands = sorted(d for d in os.listdir(parent)
                           if d.lower().startswith('redacted-batch')
                           and os.path.isdir(os.path.join(parent, d)))
            if cands:
                red_dir = os.path.join(parent, cands[-1])
                print(f"  previews from redacted copies in: {cands[-1]}")
            else:
                print("  no redacted batch found — review page will show text snippets only")
        if a.previews == 'originals':
            print("  !! --previews originals: the review page will embed unredacted pages")
        build_html(res, a.client, source, html_path,
                   decisions=decisions, cache_dir=a.cache,
                   redacted_dir=red_dir, previews=a.previews)
        plan = build_plan(res['docs'], decisions, res.get('mislabeled') or ())

        # The ledger is what makes a second batch cheap to handle: it remembers
        # which documents have been seen and filed, so a re-run reports the delta
        # instead of re-litigating everything the client already sent.
        import ledger as _ledger
        led = _ledger.load(outdir)
        new_hashes = _ledger.observe(led, res['docs'])
        newly_sat, outstanding, since = _ledger.update_checklist(led, res['results'])
        for p in plan:
            was = _ledger.filed_where(led, p.get('sha'))
            if was:
                # Already filed on an earlier pass. Say where it went rather than
                # proposing to file it again.
                p['already_filed'] = was
                p['review'] = False
                p['dest'] = was['to']
                p['why'] = 'filed on %s as %s' % (was['on'], was['as'] or p['file'])
                p['new_name'] = None
        res['ledger'] = led
        res['new_hashes'] = new_hashes

        memo = build_clarification(res, plan, a.client)
        # The rename log is the only record tying a filed document back to the
        # name the client sent it under, so it is written on every run.
        from render_html import build_rename_log
        log_path = os.path.join(outdir, f"{safe} - Rename Log.csv")
        with open(log_path, 'w') as fh:
            fh.write(build_rename_log(plan, a.client))
        n_ren = len([p for p in plan if p.get('new_name')])
        n_tbd = len([p for p in plan if p.get('needs_confirmation')])
        print(f"  {n_ren} rename(s) proposed"
              + (f", {n_tbd} needing the period confirmed" if n_tbd else ""))
        try:
            write_clarification_docx(memo, a.client, memo_path)
        except Exception as e2:
            # Word is the deliverable; only fall back if python-docx is unavailable.
            print(f"(clarification docx failed, writing .html instead: {e2})")
            memo_path = os.path.join(outdir, f"{safe} - Needs Clarification.html")
            with open(memo_path, 'w') as fh:
                fh.write('<!DOCTYPE html><meta charset="utf-8">'
                         '<style>body{font:14px/1.65 -apple-system,sans-serif;max-width:760px;'
                         'margin:40px auto;padding:0 24px}pre{white-space:pre-wrap;font:inherit}'
                         '</style><pre>' + memo.replace('&', '&amp;').replace('<', '&lt;') + '</pre>')
    except Exception as e:
        print(f"(html render failed: {e})")
        html_path = memo_path = None

    # ---- filing -----------------------------------------------------------
    # Documents are COPIED into the tree; Original_sourcedocs is left exactly as
    # the client sent it, so a misfiling is never destructive and there is always
    # a record of what actually arrived.
    try:
        import filing as _filing
        src_folder = os.path.abspath(a.folder.rstrip('/'))
        client_folder = os.path.dirname(src_folder) \
            if os.path.basename(src_folder).lower().startswith('original') \
            else src_folder
        moves, skipped = _filing.plan_moves(plan, client_folder, src_folder,
                                            res.get('ledger'))
        done, refused = _filing.execute(moves, res.get('ledger'),
                                        dry_run=not a.file_them,
                                        client_folder=client_folder)

        print("\nFiling" + ("" if a.file_them else " (dry run)") + ":")
        for line in _filing.report(moves, skipped, done, refused, dry_run=not a.file_them):
            print("  " + line)

        move_log = os.path.join(outdir, f"{safe} - Filing Log.csv")
        with open(move_log, 'w') as fh:
            fh.write(_filing.build_move_log(done, refused))
    except Exception as e:
        print(f"(filing step skipped: {e})")
        move_log = None

    # Save the ledger last, so a failure earlier in the run does not record a pass
    # that did not finish.
    try:
        import ledger as _ledger
        counts_now = {}
        for r in res['results']:
            counts_now[r['status']] = counts_now.get(r['status'], 0) + 1
        _ledger.record_run(res['ledger'], len(res['docs']),
                           len(res.get('new_hashes') or []), counts_now)
        _ledger.save(outdir, res['ledger'])
    except Exception as e:
        print(f"(ledger not updated: {e})")

    print("\nWrote:")
    for p in [html_path, memo_path, log_path, move_log, docx_path, eml_path, md_path]:
        if p:
            print(f"  {p}")
    counts = {}
    for r in res['results']:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    print(f"\n{counts.get('satisfied', 0)} satisfied · {counts.get('mismatched', 0)} mismatched"
          f" · {counts.get('missing', 0)} missing · {len(res['unexpected'])} unexpected"
          f" · {len(res['cross']['gaps'])} series gaps")
    # Spell out which set was scanned. "60 files with PII" reads like a leak
    # report; run against the originals it only means the originals are
    # unredacted, which they are by definition. Run against a redacted batch the
    # same number is a genuine finding.
    # What CHANGED since last time — the only part that matters on a re-run.
    try:
        import ledger as _ledger
        lines = _ledger.summarise(res['ledger'], res.get('new_hashes') or [],
                                  *_ledger.update_checklist(res['ledger'], res['results']))
        if lines:
            print("\nSince last time:")
            for l in lines:
                print("  " + l)
    except Exception:
        pass

    looks_redacted = sum(1 for d in res['docs'] if '(redacted)' in (d.get('file') or '').lower())
    if looks_redacted > len(res['docs']) / 2:
        print(f"\nPII: {len(res['leaks'])} of {len(res['docs'])} REDACTED files still contain "
              f"identifiers. Anything listed here is a leak — re-redact before it leaves.")
    else:
        print(f"\nPII: {len(res['leaks'])} of {len(res['docs'])} files contain identifiers. "
              f"These look like source documents, so that is expected — it is not a leak report. "
              f"Point this at the redacted batch to check the redactor.")


if __name__ == '__main__':
    main()
