"""Residual-PII detection: what survived the redactor.

This is the section of the report that protects the firm, so precision matters
as much as recall. An analyst who is shown fifty findings per file, most of them
junk, will stop reading the section entirely.

The hard-won lesson from the Bassett batch: OCR'd tax forms are full of things
that look like nine-digit numbers and aren't. A row reading

    Total deductions (add lines 1 through 21) ..........  123,456.

collapses under OCR into a digit-and-dot soup that matches any naive
"nine digits in a row" rule. Meanwhile a genuine leak -- a dependent's SSN --
appears as nine bare digits between a name and a date of birth, with nothing
labelling it at all.

So every finding carries:

  digits_seen  how many digits are actually in the document. A finding can only
               fire on 6+ digits, so it always means MORE than a last-four is
               present. (A document showing only "XXXX6840" produces no finding.)
  confidence   high   = unambiguous, or explicitly labelled, or sitting in a
                       known form position
               medium = a clean isolated nine-digit token, no supporting context
               low    = almost certainly OCR noise from a numeric table
  context      the surrounding text with every digit replaced by '#', so the
               report can show WHY something was flagged without reprinting the
               number it is warning about.

Display is always masked to the last four. The full value is never written to
the report, and never leaves this module.
"""
import re

SSN_DASHED = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
EIN_DASHED = re.compile(r'\b\d{2}-\d{7}\b')

# things that name an identifier outright
ID_KEYWORDS = (r'social security|\bSSN\b|\bS\.S\.N\b|\bTIN\b|taxpayer identification'
               r'|employer identification|\bEIN\b|\bFEIN\b|routing|\bABA\b'
               r'|account number|acct\.? no|member (?:id|number)|policy number'
               r'|file number|identification number|code number')

COMPANY_SUFFIX = r'\b(?:PLLC|LLC|L\.L\.C|INC|INCORPORATED|CORP|CORPORATION|P\.?C\.?|LTD|LLP)\b'


def _mask(value):
    d = re.sub(r'\D', '', value)
    return ('*' * (len(d) - 4) + d[-4:]) if len(d) > 4 else value


def _ctx(text, start, end, width=55):
    raw = text[max(0, start - width):min(len(text), end + width)]
    return re.sub(r'\d', '#', ' '.join(raw.split()))


def _looks_like_table_noise(text, start, end):
    """Is this match sitting inside a numeric table or a dot leader?

    Note what is deliberately NOT a signal here: the presence of '|' characters.
    An earlier version treated a couple of pipes as evidence of a ruled table,
    which suppressed the taxpayer's and spouse's SSNs on an Oklahoma Form 511 --
    tax forms are made of ruled boxes, so pipes are everywhere on exactly the
    pages we care most about.
    """
    seg = text[start:end]
    if '.' in seg:
        return True
    window = text[max(0, start - 70):end + 70]
    if re.search(r'\.{4,}', window):                 # dot leader
        return True
    # a dense run of other numbers around it: a column of figures
    others = re.findall(r'\d[\d,./-]{2,}', window.replace(seg, ' '))
    return len(others) >= 6


def _positional_hit(text, start, end):
    """Known form positions where a bare nine-digit number is an identifier."""
    before = text[max(0, start - 60):start]
    after = text[end:end + 30]

    # 1040 dependents: "Relationship to You  JANE DOE  123456789  01/02/2010  DAUGHTER"
    if (re.search(r'\b[A-Z][A-Z\'-]{2,}\s+[A-Z][A-Z\'-]{2,}\s*$', before)
            and re.search(r'^\s*\d{1,2}/\d{1,2}/\d{2,4}', after)):
        return 'in the dependent SSN position, between a name and a date of birth'
    if re.search(r'relationship to you', before, re.I):
        return 'in the dependent SSN position on Form 1040'

    # EIN sits just after the entity name on business returns
    if re.search(COMPANY_SUFFIX + r'[^\w]{0,4}$', before):
        return 'in the EIN position, immediately after the company name'
    return None


def _keyword_near(text, start, end, width=300):
    """Is an identifier caption near this number?

    The window is deliberately wide. OCR reads a form's boxes in its own order,
    so a caption printed directly above a value can land a long way from it in
    the extracted text. On the Bassett Form 511, "Your Social Security Number"
    ends up roughly 150 characters from the digits it labels, and a narrow window
    missed both the taxpayer's and the spouse's SSN.
    """
    window = text[max(0, start - width):end + width]
    m = re.search(ID_KEYWORDS, window, re.I)
    return m.group(0) if m else None


class _Seen:
    """Suppresses repeats of the same value when deduping; when not deduping,
    still stops two different patterns reporting the identical span twice."""

    def __init__(self, dedupe):
        self.dedupe = dedupe
        self.values = set()
        self.spans = set()

    def add_value(self, v):
        if self.dedupe:
            self.values.add(v)

    def has_value(self, v):
        return self.dedupe and v in self.values

    def __contains__(self, v):
        return self.has_value(v)

    def add(self, v):
        self.add_value(v)


def _add(out, kind, value, text, start, end, confidence, why):
    out.append(dict(kind=kind, masked=_mask(value),
                    digits_seen=len(re.sub(r'\D', '', value)),
                    confidence=confidence, why=why, context=_ctx(text, start, end),
                    offset=start))


def scan(text, dedupe=True):
    """Return a list of findings, most serious first.

    With dedupe=False every OCCURRENCE is returned, not one per distinct value.
    That matters because the same SSN often appears on several pages of a tax
    return, and its confidence depends entirely on which page you look at: on the
    Bassett return two SSNs appear on a filing-instructions page with no legible
    caption AND on the Form 511 page where they're clearly labelled. Keeping only
    the first occurrence judged them on their least informative appearance.

    Callers that can map offsets to pages should pass dedupe=False and merge
    afterwards, keeping the most diagnostic occurrence of each value.
    """
    out = []
    if not text:
        return out
    seen = _Seen(dedupe)

    # ---- unambiguous formats ------------------------------------------
    for m in SSN_DASHED.finditer(text):
        if m.group(0) in seen:
            continue
        seen.add(m.group(0))
        _add(out, 'SSN', m.group(0), text, m.start(), m.end(), 'high',
             'formatted as a Social Security number (###-##-####)')

    for m in EIN_DASHED.finditer(text):
        if m.group(0) in seen:
            continue
        seen.add(m.group(0))
        _add(out, 'EIN', m.group(0), text, m.start(), m.end(), 'high',
             'formatted as an EIN (##-#######)')

    # ---- labelled account numbers -------------------------------------
    for m in re.finditer(r'(?:acc(?:oun)?t\.?\s*(?:number|no\.?|#)|routing(?:\s*number)?)'
                         r'\s*[:#]?\s*([0-9][0-9 .-]{4,20}[0-9])', text, re.I):
        digits = re.sub(r'\D', '', m.group(1))
        if not (6 <= len(digits) <= 17) or digits in seen:
            continue
        seen.add(digits)
        _add(out, 'Account / routing number', m.group(1), text, m.start(1), m.end(1),
             'high', 'explicitly labelled as an account or routing number')

    # ---- bare nine-digit numbers: the hard case ------------------------
    for m in re.finditer(r'(?<![\d.-])(\d{9})(?![\d.-])', text):
        val = m.group(1)
        if val in seen:
            continue
        seen.add(val)
        near_kw = _keyword_near(text, m.start(), m.end(), width=60)
        kw = near_kw or _keyword_near(text, m.start(), m.end(), width=300)
        pos = _positional_hit(text, m.start(), m.end())
        noisy = _looks_like_table_noise(text, m.start(), m.end())
        if kw and (near_kw or not noisy):
            # immediately beside a caption, or somewhere near one and not buried
            # in a column of figures
            _add(out, 'SSN / EIN / 9-digit ID', val, text, m.start(), m.end(),
                 'high', f'nine digits on the same part of the page as "{kw}"')
        elif kw:
            _add(out, 'Possible 9-digit ID', val, text, m.start(), m.end(),
                 'medium', f'nine digits near "{kw}", but inside a column of figures')
        elif pos:
            _add(out, 'SSN / EIN / 9-digit ID', val, text, m.start(), m.end(),
                 'high', pos)
        elif _looks_like_table_noise(text, m.start(), m.end()):
            _add(out, 'Possible 9-digit ID', val, text, m.start(), m.end(),
                 'low', 'nine digits inside a numeric table or dot leader - '
                        'usually an OCR artifact, not a real number')
        else:
            _add(out, 'Unlabelled 9-digit number', val, text, m.start(), m.end(),
                 'medium', 'an isolated nine-digit number with nothing identifying it')

    # ---- digit runs joined by dots or dashes --------------------------
    for m in re.finditer(r'\d[\d.-]{7,}\d', text):
        seg = m.group(0)
        digits = re.sub(r'\D', '', seg)
        if not re.search(r'[.-]', seg):
            continue            # a plain 9-digit token: the loop above owns it
        if len(digits) != 9 or digits in seen:
            continue
        seen.add(digits)
        if SSN_DASHED.match(seg) or EIN_DASHED.match(seg):
            continue
        conf = 'low' if _looks_like_table_noise(text, m.start(), m.end()) else 'medium'
        why = ('nine digits split by dots or dashes inside a table - usually a '
               'dot leader in an OCR\'d form' if conf == 'low'
               else 'nine digits split by dots or dashes')
        _add(out, 'Possible 9-digit ID', seg, text, m.start(), m.end(), conf, why)

    # ---- email addresses ----------------------------------------------
    for m in re.finditer(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', text):
        val = m.group(0)
        if val.lower() in seen:
            continue
        seen.add(val.lower())
        # institutional addresses aren't the client's PII
        conf = 'low' if re.search(r'@(?:\w+\.)?(?:irs|arvest|citi|fidelity|capitalone|'
                                  r'bancfirst|transunion|equifax|experian)\.', val, re.I) else 'medium'
        out.append(dict(kind='Email address', masked=val, digits_seen=0,
                        confidence=conf,
                        why=('an institution\'s own address, not the client\'s'
                             if conf == 'low' else 'a personal email address'),
                        context=_ctx(text, m.start(), m.end()), offset=m.start()))

    order = {'high': 0, 'medium': 1, 'low': 2}
    out.sort(key=lambda f: (order[f['confidence']], f['kind']))
    return out


def summarise(findings):
    """Counts by confidence, for the report header."""
    c = {'high': 0, 'medium': 0, 'low': 0}
    for f in findings:
        c[f['confidence']] += 1
    return c


def scan_residual_pii(text):
    """Legacy shape: {kind: [masked, ...]}. Only real findings, noise excluded.

    Kept because the client-email guard wants a plain "is there anything in here"
    answer and shouldn't have to reason about confidence.
    """
    out = {}
    for f in scan(text):
        if f['confidence'] == 'low':
            continue
        out.setdefault(f['kind'], []).append(f['masked'])
    return out
