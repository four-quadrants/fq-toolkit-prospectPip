"""Parse a Client File Checklist PDF into the structured item model.

The checklists FQ sends are typed documents with a real text layer, so we read
layout geometry (indent depth, font weight/size) rather than guessing from prose:

    bold, larger font          -> section header ("Personal Financial Info:")
    left-most body indent      -> a checklist ITEM
    deeper indent              -> a SUB-DETAIL of the item above
    line at item indent whose
    predecessor ran to the
    right margin               -> a wrapped continuation, not a new item

From the parsed tree we derive the fields the reconciler needs (kind,
satisfied_by, counts, date ranges, optional flags) and a polite `client_ask`.

Checklists vary by client, so NOTHING here runs an audit on its own. The parsed
model is written out for a human to review and correct first -- see
`review.py`. `checklist_bassett.py` remains the hardcoded fallback.
"""
import re, os, json, hashlib, unicodedata

import pymupdf

MONTHS = {m: i for i, m in enumerate(
    ['january', 'february', 'march', 'april', 'may', 'june', 'july',
     'august', 'september', 'october', 'november', 'december'], start=1)}


# --------------------------------------------------------------------------
# layout reading
# --------------------------------------------------------------------------

def _lines(pdf_path):
    doc = pymupdf.open(pdf_path)
    out = []
    for pno, page in enumerate(doc):
        width = page.rect.width
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = "".join(s["text"] for s in spans)
                text = unicodedata.normalize('NFKC', text).strip()
                if not text:
                    continue
                out.append(dict(
                    page=pno, text=text,
                    x0=round(line["bbox"][0], 1), x1=round(line["bbox"][2], 1),
                    size=round(spans[0]["size"], 1),
                    bold='bold' in spans[0]["font"].lower(),
                    page_width=width))
    doc.close()
    return out


# A numbered or bulleted marker at the start of a line. Some checklists lead every
# item with one, some use indentation alone.
MARKER = re.compile(r'^\s*(?:\(?\d{1,2}[\).]|[•▪◦\-–—*])\s+')


def _is_header(l, body_size, seen_any):
    """Is this line a section heading?

    Written against two real checklists that agree on almost nothing. Bassett's
    headings are bold 14pt ending in a colon ("Personal Financial Info:").
    Spaulding's are bold 12pt ALL CAPS with no colon ("PRACTICE INFO") — the same
    size as the body text, so a size test alone finds nothing and the whole
    document parses to zero items.
    """
    txt = l['text'].strip()
    if not l['bold'] or len(txt) > 60:
        return False
    letters = [c for c in txt if c.isalpha()]
    all_caps = letters and all(c.isupper() for c in letters)
    return bool(txt.endswith(':') or all_caps or l['size'] > body_size + 0.5)


def _tree(lines):
    """Group lines into [{section, text, subs:[...]}] using indent geometry."""
    body = [l for l in lines if not l['bold']] or lines
    body_size = min((l['size'] for l in body), default=12)
    indents = sorted({l['x0'] for l in body})
    item_x = indents[0] if indents else 0
    right_edge = max((l['x1'] for l in lines), default=0)

    # Where a document marks its items ("1)", "•"), the marker is a far better
    # signal than indentation: Spaulding's wrapped continuation lines sit at 91.6,
    # between the item column (72) and the real sub-items (108), so an indent-only
    # rule files half of every long sentence as a sub-detail.
    marked = [l for l in body if MARKER.match(l['text'])]
    use_markers = len(marked) >= max(3, len(body) // 4)
    if use_markers:
        marker_x = sorted({l['x0'] for l in marked})
        item_x = marker_x[0]
        sub_x = next((x for x in marker_x if x > item_x + 8), None)
    else:
        sub_x = next((x for x in indents if x > item_x + 8), None)

    sections, cur_section, cur_item, prev = [], None, None, None
    for l in lines:
        txt = l['text']
        if _is_header(l, body_size, bool(sections)):
            if MARKER.match(txt):
                pass                      # a bold item, not a heading
            else:
                cur_section = re.sub(r'\s*(Financial\s*)?Info:?\s*$', '', txt,
                                     flags=re.I).strip()
                cur_item = None
                prev = None
                continue
        if cur_section is None:
            continue

        # With markers, an UNMARKED line is a wrapped continuation whatever its
        # indent — that is what stops "…for the dental practice / and rental LLC
        # entities." from being filed as a sub-detail of itself.
        if use_markers and not MARKER.match(txt):
            depth = 'wrap'
        elif sub_x is not None and l['x0'] >= sub_x - 2:
            depth = 'sub'
        else:
            depth = 'item'

        if depth == 'wrap':
            if cur_item is None:
                continue
            if prev is not None and prev['depth'] == 'sub' and cur_item['subs']:
                cur_item['subs'][-1] += ' ' + txt
            else:
                cur_item['text'] += ' ' + txt
            continue

        txt = MARKER.sub('', txt).strip() if use_markers else txt

        # wrapped continuation: same depth as the previous line, and that line
        # ran to the right margin or left a bracket / conjunction open
        if prev is not None and depth == prev['depth']:
            p = prev['line']
            wrapped = (p['x1'] >= right_edge - 12                      # ran to margin
                       or p['text'].count('(') > p['text'].count(')')  # bracket left open
                       or re.match(r'[a-z]', txt))                     # starts lowercase
            if wrapped:
                if prev['depth'] == 'sub':
                    cur_item['subs'][-1] += ' ' + txt
                else:
                    cur_item['text'] += ' ' + txt
                prev['line'] = l
                continue

        if depth == 'sub' and cur_item is not None:
            cur_item['subs'].append(txt)
        else:
            cur_item = dict(section=cur_section, text=txt, subs=[])
            sections.append(cur_item)
        prev = dict(depth=depth, line=l)
    return sections


# --------------------------------------------------------------------------
# semantics: raw item -> structured checklist entry
# --------------------------------------------------------------------------

TYPE_MAP = [
    (r'\btaxes?\b.*practice|practice.*\btaxes?\b', ['business_tax_return', 'k1']),
    (r'\btaxes?\b', ['personal_tax_return']),
    (r'practice credit card|business credit card', ['cc_statement']),
    (r'personal credit card', ['cc_statement']),
    (r'business overhead', ['overhead_insurance']),
    (r'disability insurance', ['disability_insurance']),
    (r'life\b.*(policy|insurance)|farmer', ['life_insurance']),
    (r'staff roster', ['staff_roster']),
    # \blease\b matters: an unbounded "lease" also matches "pLEASE list out names"
    (r'\bleases?\b', ['rental_lease']),
    (r'provider productivity|day sheet|eaglesoft', ['provider_productivity', 'day_sheet']),
    (r'days worked', ['dr_days_worked']),
    (r'new patients', ['new_patients']),
    (r'bonus structure', ['bonus_structure']),
    (r'hours of the practice|practice hours', ['practice_hours']),
    (r'schedule for each', ['provider_schedule']),
    (r'fee-?for-?service', ['ffs_percentage']),
    (r'bank statement|checking|savings', ['bank_statement']),
    (r'paystub|w-?2|wage', ['w2', 'paystub']),
    (r'profit and loss|p\s*&\s*l|income statement', ['pnl']),
    (r'balance sheet', ['balance_sheet']),
]

# items that are answers/confirmations rather than documents
INFO_PAT = (r'^(confirm|description of|current hours|approximate|current schedule'
            r'|dr\.? days worked|new patients)')

# doc types that are really "the client writes us an answer", not a file
INFO_TYPES = {'staff_roster', 'practice_hours', 'provider_schedule', 'ffs_percentage',
              'bonus_structure', 'dr_days_worked', 'new_patients'}


STOP = {'the', 'of', 'a', 'an', 'for', 'and', 'to', 'in', 'any', 'all', 'each',
        'please', 'current', 'that', 'as', 'by', 'with', 'is', 'are', 'be'}


def _slug(section, text, seen=None):
    """A stable id for one checklist item. Must be UNIQUE within a checklist.

    This used to be the first three meaningful words, and every request task
    opens the same way: "2024, 2025, & 2026 YTD Profit & Loss", "…Balance
    Sheet", "…Total Patients". All of them slugged to b_2024_2025_2026 — eight
    items sharing one id on Prather, six each on Rebol, Oyler and Spaulding.

    Verdicts and notes are keyed by this id, so marking Total Patients satisfied
    also marked the P&L, the balance sheet, the production report, doctor days,
    new patients and both location P&Ls satisfied. On screen every one of those
    dropdowns carried the same data-item, so changing one wrote to whichever the
    browser matched first. Nothing about it looked wrong.

    So: more words, plus a short digest of the whole label. The digest is what
    guarantees uniqueness — words alone still collide on labels that differ only
    at the end. It is derived from the text, so it is the same on every run and
    saved decisions keep matching.
    """
    words = [w for w in re.findall(r'[a-z0-9]+', text.lower()) if w not in STOP]
    base = '_'.join(words[:5]) or 'item'
    digest = hashlib.sha1(' '.join(text.lower().split()).encode('utf-8')).hexdigest()[:6]
    out = ('p_' if section.lower().startswith('personal') else 'b_') + base + '_' + digest
    # Two items whose text is genuinely identical — Rebol's checklist carries
    # the same Quickbooks line twice — cannot be told apart by their text, so
    # they get a counter. Order within one checklist is stable, so this is too.
    if seen is not None:
        n, uniq = 1, out
        while uniq in seen:
            n += 1
            uniq = '%s_%d' % (out, n)
        seen.add(uniq)
        return uniq
    return out


def _satisfied_by(text):
    """What kind of document would satisfy an item phrased like this.

    The shared vocabulary goes first: it is typo-tolerant and knows both clients'
    wording, so "Ballance Sheet" and "Feee Schedule" land correctly and a request
    for "Production and Income Report" resolves at all. TYPE_MAP stays underneath
    as a fallback — it carries a few Bassett-specific readings, notably that
    "pLEASE list out names" must not be read as a lease.
    """
    try:
        from vocab import satisfied_by as _vocab_satisfied
        got = _vocab_satisfied(text)
        if got:
            return got
    except Exception:
        pass

    low = text.lower()
    for pat, types in TYPE_MAP:
        if re.search(pat, low):
            return list(types)
    return []


def _date_range(blob):
    m = re.search(r'([A-Za-z]+)\s*(20\d\d)\s*(?:-|–|to|through)\s*([A-Za-z]+)\s*(20\d\d)', blob)
    if not m:
        return None
    a, ay, b, by = m.groups()
    if a.lower() not in MONTHS or b.lower() not in MONTHS:
        return None
    return dict(start_month=MONTHS[a.lower()], start_year=int(ay),
                end_month=MONTHS[b.lower()], end_year=int(by),
                label=f"{a.title()} {ay} - {b.title()} {by}")


def _client_ask(text, subs, kind, rng, months, years, optional_years):
    """Polite, paste-ready phrasing.

    Sub-details are expanded inline, so a compressed checklist line ('policy
    statements or details') turns into the full list the client actually has to
    go find -- carrier, policy number, monthly benefit, and so on.
    """
    ask = re.sub(r'\s*\(see sample reports of what is needed\)', '', text).strip()
    ask = re.sub(r'\s*\(if applicable\)|,?\s*if any\b', '', ask, flags=re.I).strip()
    ask = re.sub(r'\s*[—-]\s*provide\s*', ' — please provide ', ask)
    ask = ask.rstrip(':').rstrip()

    # sub-lines that are structural (years, month counts, ranges) are handled
    # separately; everything else is a real detail the client must supply
    detail_subs = [s for s in subs
                   if not re.match(r'^\d{4}\s*\(if avail', s, re.I)
                   and not re.match(r'^previous \d+ month', s, re.I)
                   and not re.match(r'^provide these if', s, re.I)
                   and not _date_range(s)]
    if detail_subs:
        joined = ", ".join(s.rstrip('.').strip() for s in detail_subs)
        joined = re.sub(r'\s*\(listed in [^)]*\)', '', joined)
        joined = joined[0].lower() + joined[1:] if joined else joined
        ask = f"{ask}: {joined}"

    if years:
        yr = ", ".join(years)
        opt = f", plus {', '.join(optional_years)} if it's available" if optional_years else ""
        ask += f" — {yr}{opt}, all pages and schedules"
    if months:
        ask += (f" — the last {months} months, full statements with every page "
                f"including the transaction detail")
        if any(re.match(r'^provide these if', s, re.I) for s in subs):
            ask += " (we need these even if the card is paid in full each month)"
    if rng:
        ask += f" — a month-by-month breakdown covering {rng['label']}"
    return ask


def build_item(raw, seen=None):
    text, subs, section = raw['text'], raw['subs'], raw['section']
    blob = " ".join([text] + subs)
    low = blob.lower()

    optional = bool(re.search(r'\(if applicable\)|,\s*if any\b|if you have', blob, re.I))

    rng = None
    for s in subs + [text]:
        rng = rng or _date_range(s)

    # "previous 4 months" is a time depth; "both rental properties" is a count of
    # separate documents. They are different rules and must not be conflated.
    m = re.search(r'previous\s+(\d+)\s+months?', low)
    months = int(m.group(1)) if m else None
    count = months
    if re.search(r'\bboth\b', low):
        count = 2

    monthly = bool(re.search(r'monthly breakdown|previous \d+ months?', low))

    years, optional_years, review_flags = [], [], []
    for s in subs:
        m = re.match(r'^(\d{4})\s*\(if avail', s, re.I)
        if m:
            optional_years.append(m.group(1))
            years.append(str(int(m.group(1)) - 1))
            review_flags.append(
                f"required tax year inferred as {years[-1]} because the checklist "
                f"only names {m.group(1)} as optional — confirm")

    # NOT extracting years from the ask, deliberately. "2024 taxes" and "2025
    # taxes" plainly name a year, and reading them made four Rebol items stop
    # pointing at the same undifferentiated pile — but enforcing it made things
    # worse overall, because year DETECTION on documents cannot carry the
    # weight:
    #
    #   - a document spanning a range gets one year. Oyler's "2024 thru 2026"
    #     balance sheet is tagged 2026, so a 2024-2025 requirement reads unmet
    #     while the answer sits in the folder.
    #   - four of six W-2s were classified as personal tax returns, because the
    #     client bundled each W-2 with pages of its return and the tax rules ran
    #     first. So the W-2 item genuinely held only two documents. (Fixed since,
    #     by position: see leads_with in classify.py. An earlier version of this
    #     comment blamed items claiming documents from each other — that does not
    #     happen; reconcile's `matched` set only feeds the "unexpected" list, and
    #     every item searches the full pool independently.)
    #
    # Measured: Oyler fell from 10 satisfied to 8, Rebol gained two and lost
    # two. Fixing the detection first, then enforcing, is the right order.

    satisfied_by = _satisfied_by(text)

    # A tax item naming an entity is not asking for a 1040. Rebol's "2024 taxes
    # for 69 McDowell Street LLC" mapped to personal_tax_return, so his LLC
    # return could never satisfy it and his personal returns always did.
    ENTITY = re.compile(r'\b(LLC|L\.L\.C|PLLC|P\.?A\b|P\.?C\b|Inc\.?|Corp\.?|'
                        r'corporation|partnership|practice|building entity)\b', re.I)
    if (satisfied_by == ['personal_tax_return']
            and ENTITY.search(text) and not re.search(r'\bpersonal\b', text, re.I)):
        satisfied_by = ['partnership_tax_return', 'business_tax_return']
        review_flags.append("read as an entity return rather than a personal one "
                            "because the ask names a company — confirm")

    if not satisfied_by:
        review_flags.append("no document type mapped — confirm what satisfies this")

    # a dated range wins: it drives the month-by-month completeness check
    if rng:
        kind = 'time_range'
    elif re.search(r'statements? all pages or|or following details|or details', low):
        kind = 'either_or'
    elif (re.search(INFO_PAT, text.strip(), re.I)
          or set(satisfied_by) & INFO_TYPES):
        kind = 'info'
    else:
        kind = 'document'

    needs_both = satisfied_by if (len(satisfied_by) > 1 and
                                  re.search(r'"[^"]+"\s*and\s*"', text)) else None

    item = dict(
        id=_slug(section, text, seen),
        section='Personal' if section.lower().startswith('personal') else 'Practice',
        label=text,
        raw_subs=subs,
        kind=kind,
        satisfied_by=satisfied_by,
        optional=optional,
        client_ask=_client_ask(text, subs, kind, rng, months, years, optional_years),
        review_flags=review_flags,
    )
    if years:
        item['years'] = years
    if optional_years:
        item['optional_years'] = optional_years
    if count:
        item['count'] = count
    if monthly:
        item['granularity'] = 'monthly'
    if rng:
        item['range'] = rng
        item['period'] = rng['label']
    if needs_both:
        item['needs_both'] = needs_both
    return item


def parse_checklist(pdf_path):
    raws = _tree(_lines(pdf_path))
    seen = set()
    return [build_item(r, seen) for r in raws]


def save(items, path):
    with open(path, 'w') as fh:
        json.dump(items, fh, indent=2)
    return path


def load(path):
    return json.load(open(path))


if __name__ == '__main__':
    import sys
    items = parse_checklist(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else 'checklist_parsed.json'
    save(items, out)
    print(json.dumps(items, indent=2))
    print(f"\n{len(items)} items -> {out}", file=sys.stderr)
