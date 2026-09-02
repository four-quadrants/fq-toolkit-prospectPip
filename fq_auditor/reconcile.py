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

def _eval_item(item, found, facts):
    """Return (status, note). `found` is every doc matching the item's types."""
    problems = []

    if not found:
        if item.get('confirmed_unavailable'):
            return 'satisfied', 'confirmed unavailable by the client'
        return 'missing', 'optional (if applicable)' if item.get('optional') else ''

    # ---- required tax years -------------------------------------------
    if item.get('years'):
        got = {str(d.get('year')) for d in found if d.get('year')}
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
        stamps = {month_index(d['year'], d['month']) for d in found
                  if d.get('month') and d.get('year')}
        if len(stamps) < item['count']:
            problems.append(f"{len(stamps) or len(found)} of the {item['count']} "
                            f"requested months provided")

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
        ask = item.get('client_ask') or item.get('label') or ''
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
}


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
            continue
        r['auto_status'] = r.get('auto_status', r['status'])
        r['status'] = rule['status']
        r['human'] = True
        r['chase'] = rule['chase']
        note = rule['note'] % who
        extra = ((v or {}).get('note') or '').strip()
        r['note'] = (note + ' — ' + extra) if extra else note
    return results
