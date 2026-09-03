"""Shared, typo-tolerant vocabulary for document kinds.

Two things need the same words and kept drifting apart: the CLASSIFIER decides
what a document is, and the CHECKLIST decides what was asked for. When they
disagree, a document that is sitting right there gets reported missing.

Everything here is written to survive humans. Request lists are typed by
different people at different times, and OCR mangles what it reads, so matching
is deliberately loose:

  * case, punctuation and spacing are normalised away
  * "&" reads as "and", "P&L" as "profit and loss"
  * each word is matched with a similarity threshold, so "ballance sheet",
    "balence sheet" and "Balance Sheets" all land on the same concept
  * a concept can require a second word ("tax" alone is not a tax return)

Short tokens that would collide if fuzzed — "ira"/"era", "hsa"/"has" — are held
to an exact match; everything else tolerates a near-miss.

Nothing here decides that an item can ONLY be answered one way. A client may
upload a spreadsheet, type the numbers into the portal, or do both — Spaulding
did both for her doctor days. See ALSO_ANSWERABLE.
"""
import re
import difflib
import unicodedata

# Longer words tolerate a near-miss freely. Short ones are riskier — but refusing
# them entirely meant "Feee Schedule" matched nothing, because "fee" is three
# letters. So short words get a stricter threshold instead of a flat ban, and the
# genuinely dangerous ones are listed out.
FUZZ_MIN_LEN = 5
FUZZ_RATIO = 0.84
SHORT_RATIO = 0.85

# Short tokens where a near-miss would be a real collision: ira/era, hsa/has,
# loc/lock, ffs/fees. These must match exactly.
EXACT_ONLY = {'ira', 'hsa', 'loc', 'ffs', 'w2', 'p', 'l', 'llc', 'plc', 'k1',
              'roth', 'sep', 'ytd'}


def normalise(text):
    """Lowercase, expand the shorthand people actually type, strip punctuation."""
    t = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text or '')   # TaxReturn -> Tax Return
    t = unicodedata.normalize('NFKC', t).lower()
    t = t.replace('&', ' and ')
    t = re.sub(r'\bp\s*and\s*l\b', ' profit and loss ', t)
    t = re.sub(r'\bp\s*/\s*l\b', ' profit and loss ', t)
    t = re.sub(r'\bw\s*-?\s*2s?\b', ' w2 ', t)
    t = re.sub(r'\b1099s?\b', ' 1099 ', t)
    t = re.sub(r'\bytd\b', ' year to date ', t)
    t = re.sub(r'\bloc\b', ' line of credit ', t)
    t = re.sub(r'\bqb\b', ' quickbooks ', t)
    # People write "Dr Days" on a file and "Doctor Days Worked" in the request.
    # Same thing; normalise so one vocabulary serves both.
    t = re.sub(r'\bdr\b', ' doctor ', t)
    t = re.sub(r'\bstmts?\b', ' statement ', t)
    t = re.sub(r'\bacct\b', ' account ', t)
    t = re.sub(r'\bins\b', ' insurance ', t)
    t = re.sub(r'\bbal\b', ' balance ', t)
    t = re.sub(r'[^a-z0-9]+', ' ', t)
    return ' ' + re.sub(r'\s+', ' ', t).strip() + ' '


def _words(t):
    return [w for w in t.split() if w]


def has_word(hay_words, word):
    """Is this word present, allowing for a misspelling?"""
    if word in hay_words:
        return True
    if word in EXACT_ONLY or len(word) <= 2:
        return False
    cutoff = FUZZ_RATIO if len(word) >= FUZZ_MIN_LEN else SHORT_RATIO
    return bool(difflib.get_close_matches(word, hay_words, n=1, cutoff=cutoff))


def has_phrase(text, phrase):
    """Every word of the phrase present, each allowed a near-miss.

    Word-set rather than substring, so "statements for all life insurance
    policies" still matches the phrase "life insurance statement".
    """
    hay = _words(normalise(text))
    return all(has_word(hay, w) for w in _words(normalise(phrase)))


def matches_any(text, phrases):
    return any(has_phrase(text, p) for p in phrases)


# ---------------------------------------------------------------------------
# concepts
# ---------------------------------------------------------------------------
# any:  any one phrase is enough
# with: at least one of these must ALSO appear (disambiguates broad words)
# not:  if any of these appear, it is not this concept
CONCEPTS = {
    'personal_tax_return': {
        'any': ['personal tax return', 'individual tax return', 'form 1040',
                'tax returns personal', 'income tax return'],
        'not': ['practice', 'business', 'corporate', 's corp', 'entity'],
        'unless_also': ['personal'],
    },
    'business_tax_return': {
        'any': ['business tax return', 'practice tax return', 'form 1120',
                'corporate tax return', 's corporation', 'entity tax return',
                'tax returns for any other entities'],
    },
    'tax_return_any': {
        'any': ['tax return', 'completed tax returns'],
    },
    'pnl': {
        'any': ['profit and loss', 'income statement', 'p and l statement'],
    },
    'balance_sheet': {'any': ['balance sheet']},
    'bank_statement': {
        'any': ['bank statement', 'bank account statement', 'checking statement',
                'savings statement', 'operating account statement'],
    },
    'cc_statement': {'any': ['credit card statement', 'card statement']},
    'brokerage_statement': {
        'any': ['investment statement', 'brokerage statement', 'investment account',
                'retirement account statement', 'annuity statement', 'crypto statement'],
    },
    'hsa_statement': {'any': ['hsa statement', 'health savings statement',
                              'hsa account', 'health savings account']},
    'credit_report': {
        'any': ['credit report', 'full credit report'],
        'not': ['credit card'],
    },
    'w2': {'any': ['w2', 'wage and tax statement']},
    'form_1099': {'any': ['1099']},
    # "year to date income" was here and matched "2026 YTD Production and Income
    # Report" — YTD expands to "year to date", and the words are all present in a
    # request that has nothing to do with a paystub. Anything this generic has to
    # name the pay.
    'paystub': {
        'any': ['pay stub', 'paystub', 'earnings statement', 'pay statement',
                'year to date pay', 'income information for'],
    },
    'payroll_summary': {'any': ['payroll summary', 'payroll register', 'payroll journal']},
    'debt_schedule': {
        'any': ['debt schedule', 'spreadsheet of all practice and personal debt',
                'list of all debt', 'debt sheet', 'schedule of debt'],
    },
    'line_of_credit': {'any': ['line of credit']},
    'fee_schedule': {'any': ['fee schedule', 'procedure codes fee', 'fee study']},
    # An estimate of what a building is worth. Usually a one-line spreadsheet
    # or a typed number, never a formal document — the request itself says "a
    # guesstimate is fine".
    'building_value': {'any': ['building value', 'value of the building',
                               'commercial building', 'building appraisal',
                               'appraised value', 'property value',
                               'real estate value', 'estimated value of']},
    'production_report': {
        # The last three are Dentrix's names for the same thing. Oyler's request
        # asks for "Analysis Summary (Provider) Reports", which matched nothing,
        # so that item could never be satisfied no matter what he sent — and he
        # had sent nine of them.
        'any': ['production and income report', 'production report',
                'provider productivity', 'day sheet', 'production by provider',
                'annual production',
                'analysis summary', 'practice analysis', 'provider report'],
    },
    # Phrased as "Doctor Days Worked" in a request and "Total Dr Days" on a file.
    'dr_days_worked': {'any': ['doctor days worked', 'days worked', 'doctor days']},
    'total_patients': {
        'any': ['total patients', 'patients seen'],
        'not': ['new patients'],
    },
    'new_patients': {'any': ['new patients']},
    'ffs_percentage': {'any': ['fee for service', 'ffs patients', 'percentage of ffs']},
    'insurance_carriers': {'any': ['in network insurance carriers', 'insurance carriers',
                                   'carrier list', 'insurance plan mix']},
    'life_insurance': {
        'any': ['life insurance', 'term life', 'whole life', 'life policy'],
    },
    'disability_insurance': {'any': ['disability insurance', 'disability policy']},
    'overhead_insurance': {'any': ['business overhead insurance', 'overhead expense insurance']},
    'property_insurance': {'any': ['homeowners insurance', 'property insurance',
                                   'dwelling coverage']},
    'quickbooks_file': {
        # A bare mention counts. Rebol's client answered this item by granting
        # read access rather than sending a file — "Sent email invite ... for
        # Read access", "sign in to Quickbooks" — and none of the phrases below
        # appear in those words, so the item had nothing attached to it at all
        # and the reviewer never saw that it had been dealt with.
        'any': ['quickbooks backup', 'quickbooks desktop backup', 'quickbooks online access',
                'quickbooks file', 'quickbooks', 'quick books', 'qbo'],
    },
    'engagement_letter': {'any': ['engagement letter', 'service agreement',
                                  'signed engagement']},
    'financial_plan': {'any': ['written financial plan', 'financial plan']},
    'rental_lease': {'any': ['signed lease', 'rental lease', 'lease agreement']},
    'staff_roster': {'any': ['staff roster', 'roster by position', 'list of staff']},
    'practice_hours': {'any': ['hours of the practice', 'practice hours', 'office hours']},
    'provider_schedule': {'any': ['schedule for each provider', 'schedule for each dentist',
                                  'provider schedule', 'hygienist schedule']},
    'bonus_structure': {'any': ['bonus structure', 'bonus plan']},
    'birthdates': {'any': ['birthdates', 'birth dates', 'date of birth', 'birthday',
                           'dob', 'born']},
}

# ANY item can be answered in the portal instead of uploaded — a client might type
# their birthdates, or paste their debt schedule, or write out a bank balance.
# There is no useful subset, so there is no list: every item is checked against
# comments as a fallback after documents.
#
# Documents always win. Spaulding both uploaded three doctor-days spreadsheets AND
# typed the numbers in a comment; preferring the comment would have ignored real
# files and left them looking unfiled.
#
# Kept only as a hint for the REVIEW page — these are the ones most often typed,
# so a reviewer seeing "missing" on one of them should check the portal first.
OFTEN_TYPED = {
    'dr_days_worked', 'total_patients', 'new_patients', 'ffs_percentage',
    'birthdates', 'practice_hours', 'provider_schedule', 'staff_roster',
    'bonus_structure', 'insurance_carriers', 'line_of_credit',
}


DOB_RE = re.compile(r'\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](19\d{2}|20[0-2]\d)\b')


def looks_like_birthdates(text, today_year=None):
    """Two or more dates that can only be dates of birth.

    A client answered this item with nothing but "Item 11 - AB 03/09/1971,
    CD 11/22/1974" (dates invented here; never paste a client's own) — no word
    saying what those numbers are, so nothing matched and the item showed as
    unanswered with the answer sitting in the thread.

    Deliberately narrow: at least two full dates, every year old enough to
    belong to an adult, and a short message. A bank statement mentions dates
    constantly, which is why length and age both have to hold.
    """
    import datetime
    today_year = today_year or datetime.date.today().year
    if len(text or '') > 300:
        return False
    years = [int(m.group(1)) for m in DOB_RE.finditer(text or '')]
    return len(years) >= 2 and all(1900 < y <= today_year - 18 for y in years)


def concepts_in(text):
    """Every concept this text refers to, best-first."""
    found = []
    for name, rule in CONCEPTS.items():
        if not matches_any(text, rule['any']):
            continue
        if rule.get('with') and not matches_any(text, rule['with']):
            continue
        # An exclusion should not fire when the item asks for BOTH. "Last two
        # years of completed tax returns (all pages, personal and practice)"
        # wants each kind, and excluding the personal one on the word "practice"
        # dropped half the request.
        if rule.get('not') and matches_any(text, rule['not']):
            if not (rule.get('unless_also')
                    and matches_any(text, rule['unless_also'])):
                continue
        found.append(name)

    if 'birthdates' not in found and looks_like_birthdates(text):
        found.append('birthdates')

    # A specific reading beats a general one: an item naming the practice's return
    # should not also count as the generic "some tax return".
    if 'tax_return_any' in found and len(found) > 1:
        found.remove('tax_return_any')
    return found


def satisfied_by(text):
    """Document types that would satisfy a checklist item phrased like this."""
    found = concepts_in(text)
    if not found:
        return []
    out = []
    for c in found:
        if c == 'tax_return_any':
            out += ['personal_tax_return', 'business_tax_return']
        elif c == 'form_1099':
            out += ['form_1099', 'w2']         # usually requested together
        elif c == 'hsa_statement':
            out += ['hsa_statement', 'bank_statement']
        elif c == 'line_of_credit':
            # An LOC is debt. A complete debt schedule is where a practice's
            # credit facilities are inventoried, so it answers the question —
            # including by showing there is no LOC at all. See reconcile's
            # handling of conditional items.
            out += ['line_of_credit', 'debt_schedule']
        elif c == 'birthdates':
            # Almost always typed, not uploaded. Accept a client note so a
            # scrap carrying them counts.
            out += ['birthdates', 'client_note']
        elif c == 'dr_days_worked':
            # A day sheet is where doctor days come from. Spaulding's
            # "2024 144 Total Dr Days.xlsx" carries day-sheet columns, so the
            # classifier calls it a day sheet — correctly. Accepting it here
            # stops the item reading missing while the answer sits in the folder.
            out += ['dr_days_worked', 'day_sheet', 'production_report']
        elif c == 'production_report':
            # "Day Sheet & Provider Productivity Reports" is one ask, and both
            # named documents answer it. Rebol sent three of each, correctly
            # classified, and the item still read missing because the concept
            # only accepted a report literally called a production report.
            # These are the same information under the names the practice
            # management systems actually print.
            out += ['production_report', 'day_sheet', 'provider_productivity']
        else:
            out.append(c)
    seen, uniq = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq
