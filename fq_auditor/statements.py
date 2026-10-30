#!/usr/bin/env python3
"""Read bank statements for the four figures the cash flow needs.

    python3 statements.py "<client folder>"
    python3 statements.py "<client folder>" --json

WHAT IT TAKES OFF A STATEMENT
Four things, and deliberately nothing else:

    account        bank, last four digits, and the holder named on it
    period         the dates the statement covers
    beginning      the opening balance
    additions      total deposits and credits
    ending         the closing balance

Expenses are not read. They are derived, as beginning + additions - ending,
which is how the firm's own workbooks do it. That matters more than it
sounds: it means no transaction line ever has to be parsed correctly for
the headline figure to be right, and the result reconciles by construction.
A missed debit cannot silently shrink someone's spending.

WHY LABEL-AND-WINDOW RATHER THAN A TEMPLATE PER BANK
Oyler alone has four layouts. Civista prints "Beginning Balance 7/27/26"
with the amount on the next line; US Bank prints "Beginning Balance on Aug
8" with the figure further down; Moonridge's bank puts label, amount and a
day count on one line. What they share is the wording. So each figure is
found by its label and then taken from a short window of following text,
which survives a bank changing its layout and does not need a new parser
for every institution.

THE FILENAME IS NEVER TRUSTED
Two of Oyler's Civista files are named "Statement-6" and "Statement-9"
where 6 is the later quarter. Reading the highest number as the most recent
gives a balance $1,740 wrong on that account. Every period here comes from
the dates printed inside the statement.
"""
import os
import re
import sys
import glob
import json
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MONEY = re.compile(r'-?\$?\s*([\d,]+\.\d{2})')
ACCT = re.compile(r'account\s*(?:number|#)?\s*:?\s*[X\*x-]*([\d]{4})\b', re.I)
ACCT_LONG = re.compile(r'account\s*(?:number|#)?\s*:?\s*([\d][\d-]{6,})', re.I)

DATE_PATS = (
    re.compile(r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b'),
    # "Feb 1, 2026", and Citizens' "February 1 , 2026": the full month name,
    # with a space before the comma. Only the first three letters are kept.
    re.compile(r'\b([A-Z][a-z]{2})[a-z]*\.?\s+(\d{1,2})\s*,?\s+(\d{4})\b'),
)
MONTHS = {m: i + 1 for i, m in enumerate(
    'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split())}

# Lines that are transactions rather than page furniture. Used to keep a
# bank named inside a transaction from being mistaken for the bank whose
# statement this is.
TXN_WORDS = re.compile(
    r'\b(deposit|transfer|payment|withdrawal|debit|credit|purchase|'
    r'check\s*#|ach|pos)\b', re.I)

BEGIN_WORDS = ('beginning balance', 'opening balance', 'previous balance',
               'balance forward')
END_WORDS = ('ending balance', 'closing balance', 'new balance',
             'current balance')
# Ordered: the most specific wording first, because a bare "Credits" is
# also the column header of the transaction table. Taking the first match
# in document order picked that header and then read the figure beneath
# it, which on Arvest's layout is the beginning balance. Deposits came out
# equal to the opening balance on three of Bassett's accounts.
ADD_PATTERNS = (
    re.compile(r'\d+\s+credit\(?s\)?\s+this\s+period', re.I),
    # "1 Deposits/Credits   3,000.00" -- a count, the label, then the
    # figure on the same line.
    # Huntington's summary: "Credits (+) 15,447.95". Its transaction block
    # is headed "Deposit / Credit Activity (+)", which the looser patterns
    # below would take, reading the first deposit as the month's total.
    re.compile(r'^(?:.*\s)?credits?\s*\(\+\)\s*\$?[\d,]+\.\d{2}', re.I),
    re.compile(r'\d+\s+deposits?\s*/\s*credits?', re.I),
    re.compile(r'\d+\s+credits?\s*/\s*deposits?', re.I),
    # BancFirst: "Deposits / Misc Credits   3   1,195.12". The count comes
    # after the label rather than before it, and a word can sit between
    # the two halves.
    re.compile(r'deposits?\s*/\s*(?:\w+\.?\s*)?credits?', re.I),
    re.compile(r'credits?\s*/\s*(?:\w+\.?\s*)?deposits?', re.I),
    re.compile(r'total\s+deposits?\s*(?:/|and)?\s*credits?', re.I),
    re.compile(r'deposits?\s+and\s+other\s+credits?', re.I),
    re.compile(r'total\s+(?:deposits?|credits?|additions?)', re.I),
    # Civista heads the summary "Credits (5)"; the bank behind Moonridge
    # writes "7 Credits". Both carry a count, which is what separates a
    # summary line from the transaction column header of the same name.
    re.compile(r'(?:deposits?|credits?)\s*\(\s*\d+\s*\)', re.I),
    re.compile(r'\d+\s+(?:deposits?|credits?)\b', re.I),
    re.compile(r'^\s*deposits?\s*$', re.I),
    re.compile(r'^\s*credits?\s*$', re.I),
)


def _money_after(lines, i, window=6):
    """The first money-looking figure at or shortly after line i.

    A window rather than the same line, because the three layouts put the
    amount in three different places relative to its label, and a window
    covers all of them without knowing which bank this is.
    """
    for j in range(i, min(i + window, len(lines))):
        m = MONEY.search(lines[j])
        if m:
            try:
                return float(m.group(1).replace(',', ''))
            except ValueError:
                continue
    return None


def _date_in(text):
    """The first date in a string, as a date, or None."""
    m = DATE_PATS[0].search(text)
    if m:
        a, b, c = m.groups()
        year = int(c) + (2000 if len(c) == 2 else 0)
        try:
            return datetime.date(year, int(a), int(b))
        except ValueError:
            return None
    m = DATE_PATS[1].search(text)
    if m:
        mon, day, year = m.groups()
        if mon in MONTHS:
            try:
                return datetime.date(int(year), MONTHS[mon], int(day))
            except ValueError:
                return None
    return None


def _label_hit(low, words):
    for w in words:
        if w in low:
            return True
    return False


def read(text, name=''):
    """One statement as a dict, or None when it carries no balances."""
    lines = [l.strip() for l in (text or '').split('\n')]
    got = {'file': name, 'bank': None, 'holder': None,
           'beginning': None, 'ending': None,
           'additions': None, 'begins': None, 'ends': None,
           'account': None, 'holder': None, 'notes': []}

    for i, line in enumerate(lines):
        low = line.lower()
        if got['beginning'] is None and _label_hit(low, BEGIN_WORDS):
            got['beginning'] = _money_after(lines, i)
            got['begins'] = _date_in(line) or _date_in(
                ' '.join(lines[i:i + 3]))
        if got['ending'] is None and _label_hit(low, END_WORDS):
            got['ending'] = _money_after(lines, i)
            got['ends'] = _date_in(line) or _date_in(' '.join(lines[i:i + 3]))


    # The bank, read off the statement rather than guessed from the file
    # name. Civista's statements are filed as "Statement 8:26" and say
    # nothing about the bank in their name, so a file-name guess leaves the
    # account labelled by its number alone.
    # The bank owns its own statement, but it can say so anywhere: in the
    # letterhead ("capitalone.com"), or in a footer ninety lines down
    # ("Thank you for banking with Simmons Bank"). So position is no help.
    #
    # What does distinguish them is that the OTHER banks named in a
    # statement are named inside transactions: "Preauthorized Deposit from
    # ARVEST BANK". Reading the whole document labelled Bassett's Capital
    # One account as Arvest for exactly that reason. So transaction lines
    # are skipped and everything else is fair game.
    #
    # Whole words too: "chase" matched inside "purchase" and turned an
    # Arvest account into a Chase one.
    body = '\n'.join(
        l for l in (text or '').split('\n')[:400]
        if not TXN_WORDS.search(l)).lower()
    got['bank'] = None
    for needle, bank in (('civista', 'Civista'), (r'u\.s\. bank', 'US Bank'),
                         ('usbank', 'US Bank'), ('us bank', 'US Bank'),
                         ('wells fargo', 'Wells Fargo'),
                         ('bank of america', 'BoA'), ('chase', 'Chase'),
                         ('arvest', 'Arvest'), ('bancfirst', 'BancFirst'),
                         ('simmons', 'Simmons Bank'),
                         ('eastman', 'Eastman CU'),
                         ('capital one', 'Capital One'),
                         ('capitalone', 'Capital One'),
                         ('huntington', 'Huntington'),
                         ('fifth third', 'Fifth Third'),
                         ('regions', 'Regions'), ('truist', 'Truist')):
        if re.search(r'\b%s\b' % needle, body):
            got['bank'] = bank
            break

    # Deposits, by the most specific wording present anywhere in the
    # document rather than the first thing that looks like a label.
    for pattern in ADD_PATTERNS:
        for i, line in enumerate(lines):
            if pattern.search(line):
                value = _money_after(lines, i)
                if value is not None:
                    got['additions'] = value
                    break
        if got['additions'] is not None:
            break
    # Citizens splits what came in across two summary lines, "0 Deposits"
    # and "2 Other Credits", each with its own count. Only when the deposits
    # line was the one taken, and only a counted Other Credits line, so a
    # transaction column headed "Other Credits" is never added in.
    if got['additions'] is not None and any(
            re.match(r'^\d+\s+deposits?\b', l, re.I) for l in lines):
        for i, line in enumerate(lines):
            if re.match(r'^\d+\s+other\s+credits?\b', line, re.I):
                extra = _money_after(lines, i, window=1)
                if extra:
                    got['additions'] = round(got['additions'] + extra, 2)
                break

    head = '\n'.join(lines[:60])
    # The period can sit below the account block, and on US Bank's layout
    # it sits on line 61 of 2 pages. Account numbers are near the top;
    # dates are not reliably so.
    wide = '\n'.join(lines[:220])
    # The account holder, from the address block: a line of capitals that
    # is a person's name rather than a bank's. Used to spot a payment
    # addressed to the client himself, which is a transfer however the
    # bank words it.
    # The holder is the capitalised name sitting at the top of an address
    # block, so it is followed within a line or two by something with a
    # state and a postcode. Taking the first block of capitals instead
    # picked up marketing headers: "News For You".
    zipline = re.compile(r'\b[A-Z]{2}\s+\d{5}(-\d{4})?\b')
    for i, line in enumerate(lines[:80]):
        bare = line.strip()
        if not (2 <= len(bare.split()) <= 4 and bare.isupper()
                and bare.replace(' ', '').isalpha()):
            continue
        if any(w in bare.lower() for w in
               ('bank', 'association', 'credit union', 'llc', 'trust',
                'inc', 'news', 'information', 'statement', 'account')):
            continue
        if any(zipline.search(l) for l in lines[i + 1:i + 5]):
            got['holder'] = bare.title()
            break

    m = ACCT_LONG.search(head) or ACCT.search(head)
    if m:
        got['account'] = m.group(1)[-4:]

    # "Statement Dates 7/01/26 thru 8/02/26" style, when the balance lines
    # carried no date of their own.
    if not (got['begins'] and got['ends']):
        # Every one of these statements also contains the sentence "during
        # this statement period", which matches the label and yields no
        # dates. So every occurrence is tried and the first that actually
        # produces two dates wins, rather than the first that matches.
        # Arvest heads it "Statement Ending 12/23/2025", with no start
        # date at all; the opening balance line carries the start.
        one = re.search(r'statement\s+ending\s*:?\s*(.{0,24})', wide, re.I)
        if one and not got['ends']:
            got['ends'] = _date_in(one.group(1))

        for m in re.finditer(r'statement\s+(?:dates?|period)\s*:?(.{0,160})',
                             wide, re.I | re.S):
            found = [d for d in (_date_in(p) for p in
                                 # Citizens capitalises it: "Thru".
                                 re.split(r'thru|through|\bto\b|\n|-',
                                          m.group(1), flags=re.I)) if d]
            if len(found) >= 2:
                got['begins'] = got['begins'] or found[0]
                got['ends'] = got['ends'] or found[-1]
                break

    if got['beginning'] is None and got['ending'] is None:
        return None

    if (got['additions'] is None and got['beginning'] is not None
            and got['ending'] == got['beginning']):
        got['additions'] = 0.0
        got['notes'].append('No deposits line found, but the balance did not '
                            'move, so nothing came in or went out.')

    # The reconciliation. Expenses are what has to have left for the
    # statement to balance.
    if None not in (got['beginning'], got['ending'], got['additions']):
        got['expenses'] = round(got['beginning'] + got['additions']
                                - got['ending'], 2)
        if got['expenses'] < 0:
            got['notes'].append(
                'Derived expenses are negative, which means additions were '
                'under-read. Check the deposits total on this statement.')
    else:
        got['expenses'] = None
        missing = [k for k in ('beginning', 'additions', 'ending')
                   if got[k] is None]
        got['notes'].append('Could not derive expenses: no %s found.'
                            % ' or '.join(missing))

    if got['begins'] and got['ends']:
        got['days'] = (got['ends'] - got['begins']).days
        if got['days'] <= 0:
            got['notes'].append('Statement dates do not run forwards.')
    else:
        got['days'] = None
        got['notes'].append('No statement period found; cannot place this '
                            'statement in time.')
    return got


def _decompose(row, prev):
    """Turn a cumulative statement back into the month it adds.

    Some banks reissue the same statement with a later end date, so three
    documents all begin on the same day with deposits of 10,000, 19,000 and
    29,000. Taken at face value that triple-counts July. Dropping the later
    two throws away August and September.

    Neither is necessary, because the difference between consecutive
    cumulative statements IS the month. The period opens where the last one
    closed, and its additions are this total less the previous total. This
    is what the firm does by hand: on Civista x0222 it recovers
    10,000 / 9,000 / 10,000 from 10,000 / 19,000 / 29,000, and monthly
    expenses of 9,088 / 9,086 / 9,086.

    The statement's own beginning balance is wrong for the decomposed month
    and is replaced. The ending balance is right, being the balance on the
    day the statement closes.
    """
    # Difference against what the PREVIOUS statement originally reported,
    # not against what it was reduced to. Three cumulative statements of
    # 10,000 / 19,000 / 29,000 are months of 10,000 / 9,000 / 10,000; using
    # the reduced 9,000 for the third gives 20,000 and overstates it.
    prev_total = prev.get('cumulative_additions', prev['additions'])
    if row['additions'] is None or prev_total is None:
        row['notes'].append(
            'Overlaps the previous statement but carries no deposits total, '
            'so the overlapping month cannot be separated out.')
        return
    if prev['ending'] is None:
        return
    before = row['additions']
    row['cumulative_additions'] = before
    row['beginning'] = prev['ending']
    row['additions'] = round(row['additions'] - prev_total, 2)
    row['begins'] = prev['ends']
    row['expenses'] = round(row['beginning'] + row['additions']
                            - row['ending'], 2)
    row['decomposed'] = True
    row['notes'].append(
        'Cumulative statement, reduced to the month it adds. Deposits %s '
        'less the previous statement\u2019s %s leaves %s, opening at the '
        'previous closing balance of %s.'
        % ('{:,.2f}'.format(before), '{:,.2f}'.format(prev_total),
           '{:,.2f}'.format(row['additions']),
           '{:,.2f}'.format(row['beginning'])))
    if row['additions'] < 0:
        row['notes'].append(
            'The deposits total went backwards, so these two statements are '
            'not the cumulative pair they appear to be.')


def _caches(folder):
    """Both cache directories, descriptive names first.

    The audit cache names files by content hash, which is fine for finding
    text but throws away the folder a document was filed into, and that
    folder is the best evidence of whether an account is personal or
    business. The extraction cache keeps the path in the filename. So both
    are read and the descriptive one wins on ties.
    """
    nested = os.path.join(folder, 'Original_sourcedocs', '.fq_cache')
    direct = os.path.join(folder, '.fq_cache')
    return [d for d in (nested, direct) if os.path.isdir(d)]


def _filed_names(folder):
    """{content hash: "Business - Banking - x3354 - <file>"} for every
    statement filed under Documents/<Side>/Banking/<account>/.

    The filing is the best evidence there is of which side of the house an
    account is on and which account a statement belongs to, and it is the
    one thing the hash-named cache throws away.
    """
    try:
        from extract import file_hash
    except Exception:                                        # pragma: no cover
        return {}
    out = {}
    # Statements still sitting unfiled in Original_sourcedocs, named the way
    # the bank's portal names them: "20260131_BANK_USAA SAVINGS_1332". No
    # side can be read off these, so they take the default (personal), and
    # any that were also filed are overwritten by their filed name below.
    raw = os.path.join(folder, 'Original_sourcedocs')
    if os.path.isdir(raw):
        for f in sorted(os.listdir(raw)):
            p = os.path.join(raw, f)
            if f.startswith('.') or not os.path.isfile(p):
                continue
            stem = os.path.splitext(f)[0]
            if not BANKISH.search(stem) or NOT_BANK.search(stem):
                continue
            # A trailing four digits is the account ("..._SAVINGS_1332"). A
            # year is not, and "Statment_01_31_2026" has no account in its
            # name at all; those get '?' and take the number printed on the
            # statement instead, in gather().
            m = re.search(r'(?<!\d)(\d{4})$', stem)
            acct = m.group(1) if m and not re.match(r'(19|20)\d\d$',
                                                    m.group(1)) else None
            try:
                digest = file_hash(p)
            except OSError:
                continue
            side = 'Business' if BUSINESSY.search(stem) else 'Personal'
            out[digest] = ('%s - Banking - %s - %s'
                           % (side, 'x' + acct if acct else '?', stem), p)
    docs = os.path.join(folder, 'Documents')
    for side in ('Business', 'Personal'):
        bank = os.path.join(docs, side, 'Banking')
        if not os.path.isdir(bank):
            continue
        for root, _dirs, files in os.walk(bank):
            rel = os.path.relpath(root, bank)
            account = rel.split(os.sep)[0] if rel != '.' else None
            for f in files:
                if f.startswith('.'):
                    continue
                p = os.path.join(root, f)
                try:
                    digest = file_hash(p)
                except OSError:
                    continue
                out[digest] = ('%s - Banking - %s - %s' % (
                    side, account or '?', os.path.splitext(f)[0]), p)
    return out


BANKISH = re.compile(r'bank|statement|statment|stmt|checking|savings|'
                     r'\bchk\b|\bsav\b', re.I)
# Investment and retirement statements also say "statement". They are read
# by the assets side, not here.
NOT_BANK = re.compile(r'\bira\b|schwab|401k|403b|brokerage|fidelity|vanguard|'
                      r'\broth\b|\bsep\b|edward jones|-edj-|'
                      r'mortgage|loan|credit card|visa|amex|tax return',
                      re.I)
# An unfiled statement's side, from its name. Only a guess, and said so on
# the sheet: "DDS Income Acct", "Op Reserves", "Hidden Hollow Rentals",
# "69 McDowell St" are Rebol's practice and LLC accounts, sitting unfiled.
BUSINESSY = re.compile(r'\bdds\b|\bllc\b|\bpllc\b|\bpa\b|\binc\b|rentals?\b|'
                       r'reserves?\b|payroll|operating|\bop\b|practice|'
                       r'income acct', re.I)


def layout_text(pdf):
    """The statement's text rebuilt line by line from word positions.

    The cached text is in the PDF's drawing order, which on some banks'
    layouts puts every label in one run and every figure in another:
    Rebol's Citizens statements read "Beginning Balance / Ending Balance /
    ... / 47,888.05 / 35,988.38", so no figure sits near its label. Grouping
    words by their height on the page puts "Beginning Balance 47,888.05"
    back on one line, which is what read() expects.
    """
    try:
        import pymupdf
    except ImportError:                                      # pragma: no cover
        try:
            import fitz as pymupdf
        except ImportError:
            return None
    try:
        doc = pymupdf.open(pdf)
    except Exception:                                        # noqa: BLE001
        return None
    pages = []
    for page in doc:
        rows = {}
        for x0, y0, x1, y1, w, *_ in page.get_text('words'):
            rows.setdefault(round((y0 + y1) / 6.0), []).append((x0, w))
        pages.append('\n'.join(' '.join(w for _, w in sorted(rows[k]))
                               for k in sorted(rows)))
    return '\n'.join(pages)


def _period_from_name(got, name):
    """Place a statement in time from its file name, when its own dates did
    not read.

    Rebol's Citizens statements are scans, and the OCR turns "Thru May 31"
    into "Thru May 34", which is no date at all. The portal named the file
    "..._05_31_2026", which is. Only used when the statement's own end date
    is missing, and said so on the sheet. A start date is inferred only when
    the end is the last day of a month, as the first of that month.
    """
    if got.get('ends'):
        return
    stem = re.sub(r'\.(pdf|txt)$', '', name, flags=re.I)
    m = (re.search(r'(?<!\d)(\d{2})_(\d{2})_(20\d\d)(?!\d)', stem)
         or re.search(r'(?<!\d)(20\d\d)(\d{2})(\d{2})(?!\d)', stem))
    if not m:
        return
    a, b, c = m.groups()
    try:
        if len(a) == 4:
            end = datetime.date(int(a), int(b), int(c))
        else:
            end = datetime.date(int(c), int(a), int(b))
    except ValueError:
        return
    got['ends'] = end
    nxt = end + datetime.timedelta(days=1)
    if not got.get('begins') and nxt.day == 1:
        got['begins'] = end.replace(day=1)
    if got.get('begins'):
        got['days'] = (got['ends'] - got['begins']).days
        got['notes'] = [n for n in got['notes']
                        if not n.startswith('No statement period found')]
    got['notes'].append('Period taken from the file name; the dates on the '
                        'statement itself did not read.')


def _is_pdf(path):
    """Spaulding's Huntington statements are PDFs with no extension."""
    try:
        with open(path, 'rb') as fh:
            return fh.read(5) == b'%PDF-'
    except OSError:
        return False


def _complete(got):
    return bool(got and got.get('ending') is not None
                and got.get('beginning') is not None and got.get('ends'))


def gather(folder):
    """Every bank statement, grouped by account: Claude's reading where it
    ties out (bank_claude), the toolkit's own reading for the rest."""
    code = _gather_code(folder)
    try:
        import bank_claude as _bc
        claude, used = _bc.as_statements(folder)
    except Exception:                                        # noqa: BLE001
        return code
    if not claude:
        return code
    out = {}
    for key, rows in code.items():
        keep = []
        for r in rows:
            src = r.get('source')
            try:
                sha = _bc._sha(src) if src and os.path.isfile(src) else None
            except OSError:
                sha = None
            if sha not in used:
                keep.append(r)
        if keep:
            out[key] = keep
    for key, rows in claude.items():
        have = out.setdefault(key, [])
        for r in rows:
            if not any((r['ends'], r['ending']) == (o.get('ends'), o.get('ending'))
                       for o in have):
                have.append(r)
        have.sort(key=lambda r: (r['ends'] or r['begins'] or datetime.date(1900, 1, 1)))
    return out


def _gather_code(folder):
    """Every bank statement in a client's cache, grouped by account.

    Statements are ordered by the date printed inside them, never by file
    name, and a duplicate period on one account is reported rather than
    silently kept, because the same statement filed twice would otherwise
    be averaged in twice.
    """
    out, seen_doc = {}, set()
    paths = []
    for cache in _caches(folder):
        paths += glob.glob(os.path.join(cache, '*.txt'))
    # Descriptive names first. The same statement sits in the cache under
    # two names: its original ("03 Mar 31 2026 CiVista Bank Account Stmt")
    # and its filed path ("Business - Banking - 4782 - ..."). Only the
    # second says which side of the house the account is on. Sorted
    # alphabetically the bare one wins, takes the slot, and the account
    # silently becomes personal.
    paths.sort(key=lambda p: (0 if ' - Banking - ' in p else 1, p))
    filed = _filed_names(folder)
    for path in paths:
        name = os.path.basename(path)[:-4]
        # The audit cache names a file by its content hash. Where that hash
        # is a statement filed under Documents, take the name its filing
        # gives it, which carries the side and the account. Without this
        # only a folder with Oyler's descriptive extraction cache had any
        # statements at all: Rebol and Spaulding came back with none.
        digest = name.split('.')[0]
        source = None
        if digest in filed:
            name, source = filed[digest]
        low = name.lower()
        if 'banking' not in low and 'stmt' not in low and \
                'statement' not in low:
            continue
        # Spaulding's Edward Jones Roth and SEP were filed under Banking.
        # They are investment accounts; counting them here would put their
        # contributions into the household's spending.
        if NOT_BANK.search(name.split(' - ')[-1]):
            continue
        got = read(open(path, errors='replace').read(), name)
        if not _complete(got) and source and _is_pdf(source):
            again = read(layout_text(source) or '', name)
            if again and (not got or sum(again.get(k) is not None for k in
                                         ('beginning', 'ending', 'ends',
                                          'additions'))
                          > sum(got.get(k) is not None for k in
                                ('beginning', 'ending', 'ends', 'additions'))):
                again['notes'].append('Read from the page layout; the cached '
                                      'text had its figures out of order.')
                got = again
        if not got:
            continue
        # Where the text came from, so the transaction reader opens the same
        # document. It used to look the file up by name, and a statement
        # named from its filing has no cache file by that name.
        got['text_path'] = path
        got['source'] = source
        _period_from_name(got, name)
        # The same statement reaches us from both caches under two names.
        # Identify it by what is printed on it, not by the file.
        # Identified by the closing date and closing balance, not by every
        # figure on it. The same statement is extracted twice at different
        # resolutions, so the two readings can differ in a cent or a date
        # the OCR mangled; the ending balance and date are the two things
        # that are always legible and together are unique per account.
        stamp = (got['ends'], None if got['ending'] is None
                 else round(got['ending'], 0))
        # With neither figure read, the stamp says nothing, and every such
        # statement would collapse into the first one. Fall back to the file.
        if stamp == (None, None):
            stamp = digest
        if stamp in seen_doc:
            continue
        seen_doc.add(stamp)
        # The folder the document was filed into names the account better
        # than the statement does, and also sides it.
        bits = [b.strip() for b in name.split(' - ')]
        got['side'] = 'Business' if low.startswith('business') else 'Personal'
        folder_key = bits[2] if len(bits) > 2 else (got['account'] or '?')
        if folder_key == '?' and got['account']:
            folder_key = 'x' + got['account']
        if source and os.sep + 'Original_sourcedocs' + os.sep in source:
            got['notes'].append('Not filed yet, so personal or business was '
                                'guessed from the file name. Check the side.')
        # What is printed on the statement beats where it was filed when the
        # two disagree. Spaulding's Huntington statements were filed under
        # Business, in folders named for the wrong accounts (x3905 holding
        # x5130's statement), with Jonathan Spaulding as the holder: personal
        # accounts, which left the household with no bank accounts at all.
        printed = got.get('account')
        if printed and folder_key != 'x' + printed and (
                not re.match(r'x?\d{4}$', folder_key or '') or
                (folder_key or '')[-4:] != printed):
            got['notes'].append('Filed under %s; the statement itself is account '
                                'x%s.' % (folder_key, printed))
            folder_key = 'x' + printed
        holder = (got.get('holder') or '').strip()
        if got['side'] == 'Business' and holder and not BUSINESSY.search(holder) \
                and not re.search(r'dental|dentistry|orthodont|oral|surgery|'
                                  r'associates|group|corp|company|\bco\b|ltd',
                                  holder, re.I) \
                and re.search(r'^[A-Za-z]+\.?( [A-Za-z]\.?)?( [A-Za-z\-\']+)+$|custodian',
                              holder, re.I):
            got['notes'].append('Filed as business, but the statement is in the '
                                'name of %s: counted as personal.' % holder)
            got['side'] = 'Personal'
        key = (got['side'], folder_key)
        out.setdefault(key, []).append(got)

    # One account, two sides. An unfiled statement's side is a guess from its
    # name; where the same account number was also filed, the filing wins and
    # the guessed statements join it. Rebol's 69 McDowell account came back
    # as two accounts, February and April filed as business, January, March
    # and May unfiled and guessed personal.
    def _guessed(rows):
        return all(any('guessed from the file name' in n for n in r['notes'])
                   for r in rows)
    for key in list(out):
        side, acct = key
        other = ('Business' if side == 'Personal' else 'Personal', acct)
        if acct != '?' and other in out and _guessed(out[key]) \
                and not _guessed(out[other]):
            for r in out.pop(key):
                r['side'] = other[0]
                if not any((r['ends'], r['ending']) == (o['ends'], o['ending'])
                           for o in out[other]):
                    out[other].append(r)

    for key, rows in out.items():
        # Ordered by whichever date is known. Sorting on the end date
        # alone put every statement with no end date first, in file order,
        # and the balance-chain check then reported breaks that were not
        # real.
        rows.sort(key=lambda r: (r['ends'] or r['begins']
                                 or datetime.date(1900, 1, 1)))
        seen = {}
        for i, r in enumerate(rows):
            if r['ends'] and r['ends'] in seen:
                r['notes'].append('Same ending date as %s; one of the two is '
                                  'a duplicate.' % seen[r['ends']])
            elif r['ends']:
                seen[r['ends']] = r['file']
            if not i:
                continue
            prev = rows[i - 1]

            # Statements on one account should run end to end. Where one
            # begins before the last one finished, they overlap, and the
            # later one is cumulative rather than a fresh period. Averaging
            # both counts the same money twice. Oyler's Civista x0222 does
            # exactly this: three statements all beginning 2 July, with
            # deposits of 10,000, 19,000 and 29,000, which is one period
            # reported three times, not three periods.
            if r['begins'] and prev['ends'] and r['begins'] <= prev['ends']:
                r['overlaps'] = prev['file']
                _decompose(r, prev)

            # The closing balance of one statement is the opening balance
            # of the next. Where it is not, either a statement is missing
            # from the run or a figure was misread, and both matter more
            # than any single number on the page.
            if (r['beginning'] is not None and prev['ending'] is not None
                    and abs(r['beginning'] - prev['ending']) > 0.01
                    and not r.get('overlaps')):
                r['notes'].append(
                    'Opens at %s but the previous statement closed at %s. '
                    'A statement is missing from the run, or one of the two '
                    'figures was misread.'
                    % ('{:,.2f}'.format(r['beginning']),
                       '{:,.2f}'.format(prev['ending'])))
    return out


def main():
    ap = argparse.ArgumentParser(description='Read bank statements')
    ap.add_argument('folder')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    found = gather(a.folder)

    if a.json:
        print(json.dumps({'%s/%s' % k: v for k, v in found.items()},
                         indent=1, default=str))
        return

    total, clean = 0, 0
    for (side, acct), rows in sorted(found.items()):
        print('\n%s  %s   (%d statements)' % (side.upper(), acct, len(rows)))
        for r in rows:
            total += 1
            ok = r['expenses'] is not None and not r['notes']
            clean += 1 if ok else 0
            print('   %-10s to %-10s  begin %12s  add %12s  end %12s  '
                  'exp %12s'
                  % (r['begins'] or '?', r['ends'] or '?',
                     _fmt(r['beginning']), _fmt(r['additions']),
                     _fmt(r['ending']), _fmt(r['expenses'])))
            for note in r['notes']:
                print('        %s' % note)
    print('\n%d of %d statements read cleanly.' % (clean, total))


def _fmt(v):
    return '{:,.2f}'.format(v) if isinstance(v, float) else '-'


if __name__ == '__main__':
    main()
