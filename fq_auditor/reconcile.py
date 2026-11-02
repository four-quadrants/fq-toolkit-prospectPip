"""Reconcile classified documents against the reviewed checklist.

Four buckets:
  satisfied   - right type, present, and it meets the completeness rules
  missing     - nothing matching arrived
  mismatched  - right TYPE, wrong SCOPE: wrong granularity, wrong date range,
                short a required year, or an incomplete multi-part item.
                A mismatch always says specifically what is wrong.
  unexpected  - arrived but isn't on the checklist. Flagged, never silently kept.

One document can also confirm another is genuinely owed: a Schedule E listing
two rental properties means two rental leases are legitimately expected, so a
single lease becomes a mismatch rather than a satisfied item.
"""
import re
from collections import defaultdict

import classify
import vocab
from classify import MONTH_NAMES
from series import month_index

MONTH_LOOKUP = {n.lower(): i for i, n in enumerate(MONTH_NAMES) if n}


def _months_in_range(rng):
    lo = month_index(rng['start_year'], rng['start_month'])
    hi = month_index(rng['end_year'], rng['end_month'])
    return list(range(lo, hi + 1))


def _stamp(i):
    return f"{MONTH_NAMES[i % 12 or 12]} {(i - 1) // 12}"


# --------------------------------------------------------------------------
# corroboration: documents that prove another document is owed
# --------------------------------------------------------------------------

def corroborate(docs):
    """Facts learned from one document that change what we expect elsewhere."""
    facts = {}
    for d in docs:
        t = d.get('text', '') or ''
        if d['doc_type'] == 'debt_schedule':
            # A debt schedule is an INVENTORY: the client is asked to list every
            # facility they hold. That makes its silence informative — if no line
            # of credit appears on it, the answer to "if the practice has a LOC"
            # is no, and nobody should be chased for a statement that cannot exist.
            facts['debt_schedule_seen'] = True
            if re.search(r'line of credit|\bLOC\b', t, re.I):
                facts['debt_schedule_lists_loc'] = True
        if d['doc_type'] in ('personal_tax_return', 'schedule_e'):
            # Schedule E lists each rental property on its own lettered line
            props = set()
            for m in re.finditer(r'^\s*([ABC])\s+(\d+\s+\w[\w .,-]{4,40})', t, re.M):
                props.add(m.group(2).strip()[:40])
            if not props:
                m = re.search(r'Physical address of each property.{0,400}', t, re.S | re.I)
                if m:
                    props = {x for x in re.findall(r'\d+\s+[A-Z][\w .]{4,30}', m.group(0))}
            if len(props) >= 2:
                facts['rental_property_count'] = len(props)
                facts['rental_property_source'] = d['file']
    return facts


# --------------------------------------------------------------------------
# per-item evaluation
# --------------------------------------------------------------------------

# Words that sit in front of "clinic"/"location"/"building" without naming
# anything — the qualifier is the word before them, not these.
_ENTITY_STOP = {'the', 'a', 'an', 'and', 'or', 'of', 'for', 'each', 'all',
                'any', 'other', 'every', 'ytd', 'main', 'this', 'that'}

# "for the wellness clinic", "Memphis location Profit & Loss", "dental building"
_ENTITY_ASK = re.compile(
    r"\b([A-Za-z][A-Za-z'&.-]{2,})\s+(clinic|location|building)\b", re.I)


def entity_asked_for(item):
    """The specific entity a checklist item names, or None.

    WHY THIS IS READ FROM THE LABEL AND NOT STORED ON THE ITEM
    checklist_reviewed.json files already exist for every client processed so
    far. Adding a field would mean every one of them silently lacks it, and the
    check would appear to work while doing nothing on exactly the clients we
    already believe we have audited.

    ONE entity, or none. An ask that lists several — Prather's debt schedule
    wants "all locations where applicable (the main office, Wellness Clinic,
    Memphis Location)" — is a single document covering all of them. Demanding
    that it belong to the wellness clinic would replace the false green this
    function exists to prevent with an equally wrong false red.

    Returns (key, phrase) — the distinctive word to match on, and the wording
    to quote back to the reviewer — or (None, None).
    """
    # Nothing to check if the evidence could never carry an entity. A .qbb
    # backup and a "guesstimate of the building's value" name no company, so
    # enforcing on them turns a satisfied item into a question nobody can
    # answer from the document.
    if not any(t in classify.ENTITY_TYPES for t in (item.get('satisfied_by') or ())):
        return None, None

    label = item.get('label') or ''
    hits = []
    for m in _ENTITY_ASK.finditer(label):
        word = m.group(1).lower()
        # A list member, not a lone subject: "personal, practice, & dental
        # building" wants all three, and Rebol has five items shaped that way.
        # Reading the last one as THE entity marked his practice P&Ls wrong.
        before = label[:m.start()].rstrip().lower()
        if before.endswith(('&', 'and', ',', 'or', '+', 'e.g.', 'such as')):
            continue
        if word not in _ENTITY_STOP and word not in [h[0] for h in hits]:
            hits.append((word, ' '.join(m.group(0).split()).lower()))
    return hits[0] if len(hits) == 1 else (None, None)


# "ending in x3309", "account ending 4782", "x2045". Four digits or more, so a
# year or a month number cannot be mistaken for an account.
_ACCT_ASK = re.compile(
    r'(?:ending(?:\s+in)?|acct\.?|account)\s*#?\s*x?(\d{4,})\b|\bx(\d{4,})\b', re.I)


# Three consecutive months is enough to see a pattern in an account, which is
# what these statements are for. Asking for four and insisting on four meant a
# client who sent a clean, unbroken three was chased for a fourth nobody needed.
MIN_RUN = 3


def _longest_run(stamps):
    """Longest unbroken run of consecutive months in a set of month indexes."""
    if not stamps:
        return 0
    xs = sorted(stamps)
    best = run = 1
    for a, b in zip(xs, xs[1:]):
        run = run + 1 if b == a + 1 else 1
        best = max(best, run)
    return best


def _one_slip_apart(a, b):
    """True when two account numbers differ by a single human slip.

    Oyler's checklist asks for x4782 and every statement reads x4728 — the
    account really is 4728, and the ask was typed wrong. Reported as a flat
    mismatch, that reads as "the client sent the wrong account", which sends
    someone chasing an account that does not exist. Two digits swapped is the
    commonest typo there is, and saying so turns a dead end into a ten-second
    check.
    """
    a, b = str(a or ''), str(b or '')
    if a == b or len(a) != len(b) or not a:
        return False
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(diff) == 1:                      # one digit mistyped
        return True
    if len(diff) == 2 and diff[1] == diff[0] + 1:
        i, j = diff                         # two adjacent digits swapped
        return a[i] == b[j] and a[j] == b[i]
    return False


def account_asked_for(item):
    """The account number an item names, or None.

    Only where exactly ONE is named. An item asking for several accounts — "all
    personal and HSA accounts" — is not about a particular one, and an ask that
    happens to mention two should not be narrowed to whichever came first.
    """
    label = item.get('client_ask') or item.get('label') or ''
    tails = []
    for m in _ACCT_ASK.finditer(label):
        t = (m.group(1) or m.group(2) or '').lstrip('0') or (m.group(1) or m.group(2))
        t = (m.group(1) or m.group(2))
        if t not in tails:
            tails.append(t)
    return tails[0] if len(tails) == 1 else None


def contested_entity_types(checklist):
    """Document types that two or more DIFFERENT entities are asked for under.

    This is the condition that actually produces a false green. Prather's
    checklist asks for business tax returns for the wellness clinic AND for the
    Memphis location; one Paige M Prather PLLC return arrived and satisfied
    both. Neither item could have been confirmed from the documents, because
    nothing distinguishes them but the entity.

    Where only ONE entity is named for a type there is no such ambiguity, and
    demanding proof of identity does harm instead: Rebol's building entity is
    "69 McDowell Street LLC", which shares no word with the "practice building"
    the item asks for, so his lease would be marked wrong for a mismatch that
    exists only in the naming.
    """
    seen = defaultdict(set)
    for item in checklist:
        key, _ = entity_asked_for(item)
        if not key:
            continue
        for t in item.get('satisfied_by') or ():
            seen[t].add(key)
    return {t for t, keys in seen.items() if len(keys) > 1}


def qualifier_scope(ask):
    """Drop parentheticals that qualify a SUB-PART rather than the whole ask.

    "Total Doctor Days Worked (you and associate(s), if applicable)" is not an
    optional item. The days are always wanted; "if applicable" attaches to the
    associates, because not every practice has one. Reading it as a condition on
    the whole line made a required number into a yes/no question, and it dropped
    off the chase list entirely.

    The distinction is whether the bracket contains anything BUT the qualifier:

        "(where applicable)"                  -> the ask itself is conditional
        "(you and associate(s), if applicable)" -> the associates are

    So a bracket holding only the qualifier is kept and everything else is
    removed before the test. "(s)" is stripped first, or the naive bracket match
    ends at the wrong parenthesis.
    """
    if not ask:
        return ''
    s = re.sub(r'\(s\)', 's', ask, flags=re.I)
    return re.sub(r'\(([^()]*)\)',
                  lambda m: m.group(0)
                  if re.fullmatch(r'\s*(?:if|where)\s+applicable\s*', m.group(1), re.I)
                  else ' ',
                  s)


def _eval_item(item, found, facts):
    """Return (status, note). `found` is every doc matching the item's types."""
    problems = []

    if not found:
        if item.get('confirmed_unavailable'):
            return 'satisfied', 'confirmed unavailable by the client'
        return 'missing', 'optional (if applicable)' if item.get('optional') else ''

    # ---- the item names a particular account ---------------------------
    # An expanded request stops asking for "bank statements" and starts asking
    # for THIS account: "ending in x3309", "x4782", each its own item. Matching
    # on document type alone meant every practice statement satisfied all of
    # them at once, so three separate asks closed on one account's statements
    # and nobody noticed the other two were never sent.
    tail = account_asked_for(item)
    if tail:
        same = [d for d in found
                if str(d.get('account_tail') or '').lstrip('xX') == tail]
        if not same:
            seen = sorted({str(d.get('account_tail')).lstrip('xX')
                           for d in found if d.get('account_tail')})
            near = [s for s in seen if _one_slip_apart(tail, s)]
            if near:
                return 'mismatched', (
                    'this asks for x%s and x%s arrived — one digit apart, so it '
                    'is probably the same account and the ask has a typo. Check one '
                    'statement, then mark this satisfied' % (tail, near[0]))
            return 'mismatched', (
                'this asks for the account ending %s; what arrived is %s'
                % (tail, ('for ' + ', '.join('x' + s for s in seen)) if seen
                   else 'statements with no account number read'))
        found = same

    # ---- a birthdate item needs an actual birthdate --------------------
    # 'client_note' is the catch-all for anything short that classified as
    # nothing else, and the birthdate item accepts client notes because clients
    # usually type their birthdates rather than upload them. Together that meant
    # any unrecognised scrap answered it: Oyler's item was satisfied by a tax
    # extension. The document has to actually carry the date.
    if 'birthdates' in (item.get('satisfied_by') or ()):
        real = [d for d in found
                if d.get('doc_type') == 'birthdates'
                or vocab.looks_like_birthdates(d.get('text') or '')]
        if not real:
            return 'missing', ('%d document(s) were offered for this, none of them '
                               'carrying a date of birth' % len(found))
        found = real

    # ---- the item names a particular entity ----------------------------
    # An item asking for "the wellness clinic's returns" is not answered by the
    # main practice's return, but both are business_tax_return and the matcher
    # sees no difference. On Prather this marked BOTH the wellness-clinic and
    # the Memphis items satisfied off one Paige M Prather PLLC return — three
    # separate asks, one document, two of them wrongly closed.
    #
    # A false green is the worst outcome this tool can produce: it tells the
    # reviewer to stop chasing something the client never sent. So when the
    # entity cannot be confirmed the item is NOT satisfied, even though that
    # means occasionally asking a human about a document that was in fact right.
    # ---- answered only by something the client has taken down ----------
    # Not downgraded to missing: she may have replaced a bad export, or
    # misclicked, and chasing her for a document she just sent is its own kind
    # of wrong. But a green tick resting entirely on a file that is no longer
    # in the portal is a claim we cannot support, so it says so.
    if found and all(d.get('withdrawn') for d in found):
        problems.append(
            "the only document(s) answering this were removed from the portal "
            "by the client after uploading — confirm they meant to")

    want, phrase = entity_asked_for(item)
    if want and any(t in facts.get('contested_types', ())
                    for t in item.get('satisfied_by') or ()):
        seen = {(d.get('entity') or '').strip() for d in found if d.get('entity')}
        if not any(want in classify.entity_key(e) for e in seen):
            if seen:
                return 'mismatched', (
                    "this asks for the %s specifically; what arrived belongs to "
                    "%s — confirm whether the %s files separately"
                    % (phrase, ', '.join(sorted(seen)), phrase))
            return 'mismatched', (
                "this asks for the %s specifically, and no entity name could be "
                "read off what arrived — open it and confirm which it is"
                % phrase)

    # ---- required tax years -------------------------------------------
    if item.get('years'):
        # Every year a document covers, not just its headline one. A comparative
        # balance sheet answers three years at once and used to answer one.
        got = set()
        for d in found:
            got.update(str(y) for y in (d.get('years') or []))
            if d.get('year'):
                got.add(str(d['year']))
        absent = [y for y in item['years'] if y not in got]
        if absent:
            problems.append(f"provided {', '.join(sorted(got)) or 'no readable year'}; "
                            f"still need {', '.join(absent)}")
        else:
            opt = [y for y in item.get('optional_years', []) if y not in got]
            if opt:
                return 'satisfied', (f"{', '.join(item['years'])} present; "
                                     f"{', '.join(opt)} not included (optional)")

    # ---- multi-part items: every named report must be present ----------
    if item.get('needs_both'):
        present = {d['doc_type'] for d in found}
        absent = [t for t in item['needs_both'] if t not in present]
        if absent:
            pretty = {'provider_productivity': 'Provider Productivity',
                      'day_sheet': 'Day Sheet'}
            problems.append("no " + " or ".join(pretty.get(a, a) for a in absent)
                            + " report was included")

    # ---- monthly coverage of an explicit date range -------------------
    if item.get('range'):
        wanted = _months_in_range(item['range'])
        have, annual_years = set(), set()
        for d in found:
            if d.get('covers'):
                have |= {month_index(y, m) for y, m in d['covers']}
            elif d.get('month') and d.get('year'):
                have.add(month_index(d['year'], d['month']))
            elif d.get('granularity') in ('annual', 'ytd') and d.get('year'):
                # An annual or year-to-date summary is NOT a month-by-month
                # breakdown. Crediting it with twelve months would turn the
                # exact thing we're supposed to catch into a satisfied item.
                annual_years.add(str(d['year']))
        absent = [i for i in wanted if i not in have]
        if annual_years:
            problems.append(
                f"an annual/year-to-date summary was provided for "
                f"{', '.join(sorted(annual_years))} rather than monthly detail")
        if absent and not have:
            problems.append(f"no month-by-month data for {item['range']['label']}")
        elif absent:
            problems.append(f"missing {len(absent)} month(s): {_runs(absent)}")

    # ---- "previous N months" depth ------------------------------------
    elif item.get('count') and item.get('granularity') == 'monthly':
        # An unbroken run is what the analysis needs, not the specific months we
        # happened to name. Asking for "March, April, May and June" and getting
        # May, June, July and August is a complete picture; counting distinct
        # months without checking they join up would equally pass March, May,
        # July and September, which is not.
        #
        # Judged per ACCOUNT. Four statements across four different accounts is
        # four first months, and adding them up read as a full run.
        by_acct = defaultdict(set)
        for d in found:
            if d.get('month') and d.get('year'):
                key = d.get('account_tail') or d.get('issuer') or ''
                by_acct[key].add(month_index(d['year'], d['month']))
        want = min(int(item['count']), MIN_RUN)
        short = []
        for key, stamps in sorted(by_acct.items()):
            if _longest_run(stamps) < want:
                short.append((key, _longest_run(stamps)))
        if not by_acct:
            problems.append('no month could be read from the statements provided')
        elif short:
            problems.append('; '.join(
                '%s has %d month(s) in a row, we need %d'
                % (('x' + k) if k else 'one account', n, want) for k, n in short))

    # ---- plain count of separate documents ----------------------------
    elif item.get('count'):
        expected = item['count']
        if item['satisfied_by'] == ['rental_lease'] and facts.get('rental_property_count'):
            expected = max(expected, facts['rental_property_count'])
        if len(found) < expected:
            extra = ''
            if facts.get('rental_property_source') and item['satisfied_by'] == ['rental_lease']:
                extra = (f" ({facts['rental_property_count']} rental properties appear on "
                         f"{facts['rental_property_source']}, so both are expected)")
            problems.append(f"{len(found)} of {expected} provided{extra}")

    # ---- granularity when no explicit range --------------------------
    if item.get('granularity') == 'monthly' and not item.get('range') and not problems:
        grans = {d.get('granularity') for d in found}
        if grans and 'monthly' not in grans and grans != {None}:
            problems.append(f"received {', '.join(sorted(g for g in grans if g))} data; "
                            f"a monthly breakdown is needed")

    if problems:
        return 'mismatched', '; '.join(problems)
    return 'satisfied', ''


def _runs(indices):
    """Compress [Jan,Feb,Mar,Jul] into 'January-March 2025, July 2025'."""
    out, start, prev = [], None, None
    for i in indices + [None]:
        if start is None:
            start, prev = i, i
            continue
        if i is not None and i == prev + 1:
            prev = i
            continue
        out.append(_stamp(start) if start == prev else f"{_stamp(start)} - {_stamp(prev)}")
        start, prev = i, i
    return ", ".join(out)


# --------------------------------------------------------------------------

# Words that follow "for" but are not a person.
_NOT_A_NAME = {'the', 'all', 'any', 'both', 'each', 'your', 'their', 'you',
               'tax', 'taxes', 'year', 'years', 'ytd', 'total', 'practice',
               'personal', 'business', 'entities', 'entity', 'previous', 'most'}


def via_portal_pending(item):
    """Placeholder hook: portal answers are evaluated later in the loop."""
    return False


def people_named(ask):
    """First names a request asks about: "for Jon & Kelly & Isla" -> 3 names."""
    out = []
    for m in re.finditer(r'\bfor\s+((?:[A-Z][a-z]+)(?:\s*(?:&|and)\s*[A-Z][a-z]+)*)', ask or ''):
        for name in re.split(r'\s*(?:&|and)\s*', m.group(1)):
            name = name.strip()
            if name and name.lower() not in _NOT_A_NAME and name not in out:
                out.append(name)
    return out


def compound_gap(item, found):
    """What is still missing from an ask that names TWO things.

    A single checklist line often asks for two deliverables — "all practice and
    personal debt", "paystubs for Kelly & YTD income for Jon", "W-2/1099s for
    Jon & Kelly & Isla". One document arriving turned the whole line green, so
    Oyler read as complete while his team was still chasing his personal debt
    schedule, and Kelly's missing paystubs vanished behind her husband's income.

    A confident all-clear that stops you asking is the worst thing this tool can
    produce, so a half-answered line is reported as half-answered.

    Returns a description of the gap, or None when nothing is obviously missing.
    """
    ask = item.get('client_ask') or item.get('label') or ''
    if not found:
        return None

    # "personal and practice" — needs something from each side of the house.
    if re.search(r'personal\s*(?:and|&)\s*practice|practice\s*(?:and|&)\s*personal',
                 ask, re.I):
        sides = {d.get('owner_side') for d in found if d.get('owner_side')}
        if sides == {'Practice'}:
            return 'only the practice side has arrived — the personal one is still missing'
        if sides == {'Personal'}:
            return 'only the personal side has arrived — the practice one is still missing'
        # Nothing here says which side it belongs to. Oyler's single debt
        # spreadsheet came through with no side at all, so a check that only
        # looked at KNOWN sides let the exact case that prompted this work sail
        # through green. Silence is not evidence of coverage: say we cannot
        # tell, and let the reviewer look. Worded as a prompt rather than an
        # accusation because one spreadsheet genuinely can hold both.
        if not sides and len(found) == 1:
            return ('one document arrived for an ask covering both sides — check it '
                    'holds the personal debts too, or chase the missing half')

    # "for Jon & Kelly & Isla" — needs one per person named.
    names = people_named(ask)
    if len(names) >= 2:
        got = {str(d.get('person') or '').strip() for d in found}
        got = {g for g in got if g}
        missing = [n for n in names if not any(n.lower() in g.lower() for g in got)]
        if missing and len(missing) < len(names):
            return 'nothing yet for %s' % ' and '.join(missing)
    return None


def reconcile(docs, checklist):
    by_type = defaultdict(list)
    for d in docs:
        by_type[d['doc_type']].append(d)
        # A document can honestly answer more than one ask. One client sent a
        # single table headed Dr Days / Total Patients / New Patients and said
        # so in the portal; indexing only its primary label meant it answered
        # one item while the other two were chased from someone who had
        # already sent them.
        #
        # The document's identity does not change — everywhere else still reads
        # doc_type, so filing and naming are unaffected. This only widens what
        # it can be found under.
        for extra in d.get('also_types') or ():
            if extra != d['doc_type']:
                by_type[extra].append(d)

    facts = corroborate(docs)
    facts['contested_types'] = contested_entity_types(checklist)
    matched, results = set(), []

    for item in checklist:
        found = []
        for dt in item.get('satisfied_by', []):
            found += by_type.get(dt, [])
        # An item scoped to one side must not be satisfied by the other side's
        # documents: the practice credit cards do not satisfy "personal credit
        # card statements", even though both are credit card statements.
        # A debt schedule answers "if the practice has a line of credit, provide
        # bank, limit, rate, balance" only when it actually lists one — a row on
        # that sheet carries every field the item asks for. When it lists none,
        # the sheet is evidence of ABSENCE, not a submission, and is handled by
        # the conditional branch below.
        if ('line_of_credit' in (item.get('satisfied_by') or [])
                and not facts.get('debt_schedule_lists_loc')):
            found = [d for d in found if d['doc_type'] != 'debt_schedule']

        # ...unless the item asks for BOTH. "Last two years of completed tax
        # returns (all pages, personal and practice)" is one line covering two
        # sides; filtering it to the section heading threw away the personal
        # returns that were sitting right there and called them a mismatch.
        asks_both = bool(re.search(
            r'personal', item.get('client_ask') or item.get('label') or '', re.I)
            and re.search(r'practice|business|entit',
                          item.get('client_ask') or item.get('label') or '', re.I))

        wrong_side = []
        if item['section'] in ('Personal', 'Practice') and found and not asks_both:
            sided = [d for d in found if d.get('owner_side') in (None, item['section'])]
            wrong_side = [d for d in found if d not in sided]
            found = sided

        status, note = _eval_item(item, found, facts)
        if not found and wrong_side:
            other = 'practice' if item['section'] == 'Personal' else 'personal'
            status = 'mismatched'
            note = (f"the {len(wrong_side)} statement(s) provided look like {other} "
                    f"accounts, not {item['section'].lower()} ones")
            found = wrong_side
        # A client may answer by typing rather than uploading. Kelly Spaulding
        # typed her doctor days and patient counts into LaunchBay:
        #
        #   "Total Dr. Days worked: 2024: 144  2025: 193  Jan 1-June 30 2026: 94"
        #
        # That IS the deliverable for those items, and an auditor that only hunts
        # files reports them missing forever. Checked LAST, so a real document
        # always wins and never gets left looking unfiled.
        # Conditional asks. A great many checklist lines are "if applicable" by
        # nature — a line of credit, a 529, rental property, a written financial
        # plan, returns for other entities. Most clients do not have most of
        # them, and calling every one MISSING turns a healthy file into a wall of
        # red and sends the client a list demanding documents that cannot exist.
        #
        # These need a yes/no, not a chase. They are reported separately so the
        # reviewer asks "do you have one?" once and it is then settled for good
        # via confirmed_unavailable.
        ask = qualifier_scope(item.get('client_ask') or item.get('label') or '')
        conditional = bool(item.get('optional')) or bool(re.search(
            r'\bif applicable\b|\bif any\b|\bif you (?:have|own)\b|'
            r'\bif the \w+ has\b|\bif there (?:is|are)\b|^\s*if\b',
            ask, re.I))

        # A line asking for two things is not done when one arrives.
        if status == 'satisfied' and not via_portal_pending(item):
            gap = compound_gap(item, found)
            if gap:
                status = 'partly satisfied'
                note = (note + '; ' if note else '') + gap

        needs_yes_no = False
        if status == 'missing' and item.get('confirmed_unavailable'):
            status, note = 'not_applicable', 'the client has confirmed they have none'
        elif status == 'missing' and conditional:
            status = 'not_applicable'
            note = 'conditional item — needs a yes/no from the client, not a document'
            needs_yes_no = True
            # Sometimes another document already answers it. A debt schedule is a
            # complete inventory of what the client owes, so its silence about a
            # line of credit IS the answer — no need to ask at all.
            if ('line_of_credit' in (item.get('satisfied_by') or [])
                    and facts.get('debt_schedule_seen')
                    and not facts.get('debt_schedule_lists_loc')):
                note = ('the debt schedule inventories every facility and lists no '
                        'line of credit, so there is nothing to collect')
                needs_yes_no = False
            found = []

        via_portal = None
        if status == 'missing' and item.get('answered_in_portal'):
            via_portal = item['answered_in_portal']
            status = 'satisfied'
            who = via_portal.get('who') or 'the client'
            note = f"answered in the portal by {who} rather than uploaded"

        for d in found:
            matched.add(d['file'])
        results.append(dict(item=item, status=status, note=note, docs=found,
                            via_portal=via_portal, needs_yes_no=needs_yes_no))

    unexpected = [d for d in docs if d['file'] not in matched]
    return results, unexpected, facts


# --------------------------------------------------------------------------
# human verdicts
# --------------------------------------------------------------------------
# What a reviewer can say about an item, and what it means for the client.
# "chase" decides whether the item appears in the email: the whole reason for
# letting someone overrule the auditor is that they have opened the document and
# know something it does not.
VERDICTS = {
    'satisfied':   {'status': 'satisfied',        'chase': False,
                    'note': 'confirmed by %s'},
    'practice':    {'status': 'partly satisfied', 'chase': True,
                    'note': '%s checked: this is the practice side only — '
                            'the personal one is still outstanding'},
    'personal':    {'status': 'partly satisfied', 'chase': True,
                    'note': '%s checked: this is the personal side only — '
                            'the practice one is still outstanding'},
    'not_applicable': {'status': 'not_applicable', 'chase': False,
                    'note': "%s marked this not applicable — the client does not have one"},
    'missing':     {'status': 'missing',          'chase': True,
                    'note': '%s checked: what arrived does not answer this'},
    # Some of it came, not all. The human dropdown never offered this because a
    # person reviewing an item tends to know which half is outstanding and
    # picks 'practice' or 'personal'. Claude answers in these terms constantly
    # -- three of four months, two accounts of three -- and without this entry
    # ten of its thirty-one verdicts were dropped on the floor.
    'partly satisfied': {'status': 'partly satisfied', 'chase': True,
                    'note': '%s checked: some of this arrived, not all'},
}


def apply_claude_verdicts(results, verdicts):
    """Overlay Claude's reading of the checklist on the rules'.

    Three layers, in order: the rules, then Claude, then a person. Each wins
    over the one before it, and this must run before apply_item_verdicts so
    that a person's decision still beats everything.

    Claude is better at this than the rules because the question is whether the
    evidence is SUFFICIENT, not whether it matches. On Oyler the rules called
    nineteen items satisfied; Claude called twelve, and the seven it withheld
    were real: an August statement that belonged to a different account, a
    year-to-date P&L that covers one month, a pay stub whose own header says
    "Page 1 of 1" against a request for two.

    The rules' answer is kept beside it. When the two disagree, that is worth
    showing a person rather than quietly replacing.
    """
    if not verdicts:
        return results
    for r in results:
        v = verdicts.get(str(r['item'].get('id')))
        if not v:
            continue
        rule = VERDICTS.get((v or {}).get('verdict'))
        if not rule:
            continue
        r['rule_status'] = r.get('rule_status', r['status'])
        r['status'] = rule['status']
        r['claude_verdict'] = v.get('verdict')
        r['claude_notes'] = [n for n in (v.get('team_notes') or []) if n]
        r['claude_reasoning'] = v.get('reasoning')
        r['claude_confidence'] = v.get('confidence')
        # What the client will actually be asked for, written as they will
        # read it. A list, because one checklist line can be two chases: "last
        # two years of returns, personal and practice" is one item to us and
        # two different requests to them, and the personal half kept appearing
        # under a Practice heading.
        asks = v.get('asks')
        if isinstance(asks, list) and asks:
            r['claude_asks'] = [a for a in asks if (a or {}).get('text')]
            r['client_ask_override'] = asks[0].get('text')
        elif v.get('still_needed'):
            r['claude_asks'] = [{'section': r['item'].get('section'),
                                 'text': v['still_needed']}]
            r['client_ask_override'] = v['still_needed']
        r['disagrees_with_rules'] = (r['rule_status'] != r['status'])
    return results


def apply_item_verdicts(results, verdicts, who='reviewer'):
    """Overlay a person's decisions on the auditor's.

    The auditor reads documents; it cannot open a debt schedule and judge
    whether the rows below the practice loans are the doctor's car. When
    someone has looked and knows, their answer wins — and it has to survive
    into the client email, or overruling the machine achieves nothing except a
    nicer-looking screen.

    Idempotent, and safe to call with nothing: an item with no verdict is left
    exactly as the auditor left it. The original status is kept so the page can
    show that a human moved it.
    """
    if not verdicts:
        return results
    for r in results:
        v = verdicts.get(str(r['item'].get('id')))
        if not v:
            continue
        rule = VERDICTS.get((v or {}).get('verdict'))
        if not rule:
            # A note with no verdict. That is the commonest thing anyone writes
            # against a MISSING item — "she is sending this Monday", "asked on
            # the call, they don't have one" — and it used to be dropped here,
            # because this loop only ever looked for a verdict. The note saved,
            # reappeared in the box, and reached nothing else: not the tile, not
            # the writeup, not the chase list someone else has to work from.
            #
            # It does not change the status. Nobody said it was answered; they
            # said something about it, and that belongs beside it.
            extra = ((v or {}).get('note') or '').strip()
            if extra:
                r['note'] = (r['note'] + ' — ' + extra) if r.get('note') else extra
                r['human_note'] = True
            continue
        r['auto_status'] = r.get('auto_status', r['status'])

        # A verdict is a judgement about the evidence as it stood when it was
        # made. Evidence moves. On Rebol the investment statements were marked
        # "still missing" during the initial request — correct then — and the
        # client sent them a week later. The verdict kept winning silently, so
        # the item stayed red with five matching documents sitting in the
        # folder, and nothing on the page suggested the instruction was old.
        #
        # The person's call still wins: they may have opened the documents and
        # found them wrong, which no amount of matching can see. But when the
        # auditor's own reading has since moved the other way, that has to be
        # visible, or a stale instruction quietly outlives the situation that
        # produced it.
        # Only ONE direction is staleness. If you said an item was still missing
        # and the auditor now finds it answered, documents arrived after you
        # decided and your instruction has outlived the situation — worth
        # saying.
        #
        # The other direction is not stale, it is the whole point. Marking a
        # mismatched item satisfied means you opened the documents and know
        # something the matcher cannot see. Flagging that put the item straight
        # back into "needs you" the instant it was answered, so overruling the
        # auditor looked like the click had failed.
        auto = r['auto_status']
        want = rule['status']
        if auto == 'satisfied' and want in ('missing', 'partly satisfied'):
            r['verdict_stale'] = {
                'said': want, 'now': auto, 'docs': len(r.get('docs') or [])}

        r['status'] = rule['status']
        r['human'] = True
        r['chase'] = rule['chase']
        note = rule['note'] % who
        extra = ((v or {}).get('note') or '').strip()
        r['note'] = (note + ' — ' + extra) if extra else note
        if r.get('verdict_stale'):
            st = r['verdict_stale']
            if st['now'] == 'satisfied':
                r['note'] += ('. Worth a second look: %d document(s) now match this, '
                              'so the answer may have arrived since you marked it.'
                              % st['docs'])
            else:
                r['note'] += ('. Worth a second look: the auditor no longer finds '
                              'this answered.')
    return results
