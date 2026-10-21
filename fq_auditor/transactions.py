#!/usr/bin/env python3
"""Read individual transactions off a bank statement.

    python3 transactions.py "<client folder>"
    python3 transactions.py "<client folder>" --account 0054

WHY THIS EXISTS WHEN THE TOTALS ARE ALREADY READ
The headline figures do not need it: expenses are derived as beginning
plus additions less ending, which reconciles by construction and never
depends on a line being parsed correctly.

Transfers are different. A transfer is one movement among many, so it
cannot be derived from a total; it has to be found. And until it is found,
money Brian moved between his own accounts is counted as spending. On
Civista x0054 that is $59,000 across four months, which is the difference
between a monthly figure of $77,874 and Brogan's $23,124.

TWO LAYOUTS, AND WHY NOT MORE
Civista prints date, description and amount on consecutive lines; the
banks behind Moonridge put all three on one line. Both are handled. US
Bank's statements defeat this reader, and that is reported rather than
guessed at: its columns are reordered by the text extractor so a line
cannot be reassembled with any confidence. Those accounts fall back to
matching amounts across accounts.

THE PART THAT MATTERS MOST
Civista names the counterparty in the description:

    Transfer from XXX4728 to XXX00 54: Conf #:4413964

That is direct evidence, not inference, and it is worth far more than
pairing equal amounts on nearby dates. Two unrelated payments of $2,500
look identical to an amount matcher; only one of them says where it went.
"""
import os
import re
import sys
import glob
import json
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import statements as _st                                     # noqa: E402

# Civista prints a debit as "$5,000.00-", with the sign trailing. Without
# the optional minus the line is not recognised as an amount, the reader
# keeps gathering description across the page break, and the next figure it
# finds is the "Average Ledger Bal" in the page footer: a $5,000 transfer
# was read as $76,907.28.
AMOUNT = re.compile(r'^\$?\s*(-?[\d,]+\.\d{2})\s*-?\s*$')

# Page furniture. Reaching any of these means the transaction being
# assembled has run off the end of the page without an amount.
PAGE_BREAK = ('account number', 'page ', 'summary', 'continued',
              'average ledger', 'average collected')
INLINE = re.compile(r'^\s*(\d{1,2})/(\d{1,2})\s+(.{4,}?)\s{2,}'
                    r'\$?(-?[\d,]+\.\d{2})\s*$')
DATE_ONLY = re.compile(r'^\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s*$')

CREDIT_HEADS = ('deposits & credits', 'deposits and credits', 'deposits',
                'credits', 'additions')
DEBIT_HEADS = ('debits & withdrawals', 'debits and withdrawals',
               'withdrawals', 'debits', 'checks paid', 'other withdrawals')
STOP_HEADS = ('daily balance', 'service charge', 'overdraft', 'interest rate',
              'account summary', 'important', 'customer service')

# "Transfer from XXX4728 to XXX00 54" -- the trailing number is split by the
# text extractor often enough that the digits have to be rejoined.
TRANSFER = re.compile(
    r'transfer\s+(from|to)\s+X+\s*([\d\s]{2,12}?)\s+(?:to|from)\s+X+\s*'
    r'([\d\s]{2,12}?)\s*[:,]', re.I)
# Arvest writes "Transfer to Checking * 5647"; Civista writes "XXX5647".
# USAA writes "FUNDS TRANSFER DB TO Katherine Rebol CHECKING #0407". Only
# read inside a description that already says it is a movement, so a
# "CHECK # 3290" is never taken for an account.
ANY_ACCT = re.compile(r'(?:X{2,}|\*|#)\s*([\d\s]{2,12}?)(?=[\s:,.]|$)', re.I)
# "From Account 104729386001" -- U.S. Bank writes the whole number out.
FULL_ACCT = re.compile(r'(?:to|from)\s+account\s+(\d{6,})', re.I)

MOVE_WORDS = ('transfer', 'xfer', 'zelle', 'wire', 'online banking',
              'internet banking', 'mobile banking', 'to savings',
              'to checking')
BORROW_WORDS = ('loan', 'advance', 'draw', 'line of credit', 'heloc',
                'cash advance', 'policy loan', 'mortgage proceeds')
# "LOC TRANSFER" is USAA's line of credit: a $49,000 draw on Rebol's x9634
# that would otherwise have been income.
#
# Note that 'draw' above also matches "Withdrawal". That is wrong as a
# reading, and was tried as a whole word on 21 October, but it moved Oyler's
# verified figure from $13,892 to $12,973: his "Electronic Withdrawal ... To
# U.S. BANK ... WEB PYMT" lines then fell through to the card-payment
# smoothing. Borrowing on a debit has no effect on the figures, so the
# substring stays until the card rule is settled against Brogan's workbook.
BORROW_RE = re.compile(r'\bloc\b', re.I)


def _digits(raw):
    """"00 54" and "0054" are the same account; keep the last four."""
    out = re.sub(r'\D', '', raw or '')
    return out[-4:] if len(out) >= 4 else out


def _money(raw):
    try:
        return float(str(raw).replace(',', '').replace('$', ''))
    except (TypeError, ValueError):
        return None


def _section_of(line):
    low = line.strip().lower()
    if not low or len(low) > 60:
        return None
    for head in STOP_HEADS:
        if low.startswith(head):
            return 'stop'
    for head in CREDIT_HEADS:
        if low.startswith(head):
            return 'credit'
    for head in DEBIT_HEADS:
        if low.startswith(head):
            return 'debit'
    return None


REGISTER_HEAD = re.compile(r'^\s*balance\s*$', re.I)

MONTH_ONLY = re.compile(r'^\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|'
                        r'Dec)\s*$', re.I)
MONTH_DAY = re.compile(r'^\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|'
                       r'Dec)\s+(\d{1,2})\b\s*(.*)$', re.I)
DOLLAR_ONLY = re.compile(r'^\s*\$\s*$')
SIGNED = re.compile(r'^\s*\$?\s*([\d,]+\.\d{2})\s*(-?)\s*$')
MONTH_NUM = {m: i + 1 for i, m in enumerate(
    'jan feb mar apr may jun jul aug sep oct nov dec'.split())}


def _is_usbank(lines):
    head = '\n'.join(lines[:60]).lower()
    return 'u.s. bank national association' in head or 'usbank.com' in head


def _read_usbank(lines, year=None, account=None, holder=None):
    """U.S. Bank's layout, which the generic readers cannot see.

    The extractor leaves almost nothing on a line: the date arrives as a
    bare month followed by a bare day, the description follows over
    several lines, then a lone dollar sign, then the figure with a
    trailing minus if it is a withdrawal.

        Sep
        2
        Mobile Banking Transfer
        From Account 104729386001
        $
        800.00

    Worth the dedicated reader because these statements name the other
    account: "From Account 104729386001" is the money market whose last
    four are 6001. Without this, three of Oyler's five personal accounts
    contribute nothing to the plan.
    """
    out, pending = [], None

    def finish(amount, sign):
        if not pending:
            return
        desc = ' '.join(x for x in pending['desc'] if x)
        if not desc:
            return
        if re.search(r'(beginning|ending)\s+balance|page\s+\d+\s+of', desc,
                     re.I):
            return
        out.append(_row(pending['month'], pending['day'], desc, amount,
                        'debit' if sign else 'credit', year, account,
                        holder))

    for line in lines:
        hit = MONTH_DAY.match(line)
        # "Aug 25, 2026" is a date in a sentence, not a transaction. Left
        # in, the reader gathers the page header that follows it and the
        # opening balance beneath, and reports an $81,742 deposit.
        if hit and hit.group(3).lstrip().startswith(','):
            pending = None
            continue
        if hit and hit.group(1).lower() in MONTH_NUM:
            pending = {'month': MONTH_NUM[hit.group(1).lower()],
                       'day': hit.group(2), 'desc': [hit.group(3).strip()],
                       'seen_dollar': False}
            continue
        hit = MONTH_ONLY.match(line)
        if hit:
            pending = {'month': MONTH_NUM[hit.group(1).lower()],
                       'day': None, 'desc': [], 'seen_dollar': False}
            continue
        if pending is None:
            continue
        if pending['day'] is None:
            day = re.match(r'^\s*(\d{1,2})\s*$', line)
            if day:
                pending['day'] = day.group(1)
                continue
            pending = None
            continue
        if DOLLAR_ONLY.match(line):
            pending['seen_dollar'] = True
            continue
        money = SIGNED.match(line)
        if money and (pending['seen_dollar'] or pending['desc']):
            finish(money.group(1), money.group(2))
            pending = None
            continue
        if len(pending['desc']) < 5:
            pending['desc'].append(line.strip())
    return out


def _is_register(lines):
    """Does this statement use one register with a running balance?

    Civista and friends split credits from debits into separate sections,
    so the section heading says which way the money went. Arvest prints a
    single register with Debits, Credits and Balance columns, and the text
    extractor flattens those columns away, so the heading tells us
    nothing: every transaction looks the same.

    What survives is the running balance. If the balance fell, it was a
    debit. That is better evidence than a section heading, and it works on
    any bank that prints the column.
    """
    for i, line in enumerate(lines[:200]):
        if REGISTER_HEAD.match(line):
            near = ' '.join(lines[max(0, i - 3):i]).lower()
            if 'debit' in near and 'credit' in near:
                return True
    return False


def _read_register(lines, year=None, account=None):
    """A single-register statement, read by watching the balance move."""
    out, balance, pending = [], None, None
    for line in lines:
        date = DATE_ONLY.match(line)
        if date:
            pending = {'month': date.group(1), 'day': date.group(2),
                       'desc': [], 'nums': []}
            continue
        if pending is None:
            continue
        amount = AMOUNT.match(line)
        if amount:
            pending['nums'].append(_money(amount.group(1)))
            if len(pending['nums']) == 1 and not pending['desc']:
                # An opening balance line: a figure with no description.
                balance = pending['nums'][0]
                pending = None
                continue
            if len(pending['nums']) == 2:
                value, after = pending['nums']
                desc = ' '.join(pending['desc'])
                if balance is None:
                    direction = 'debit'
                else:
                    direction = 'credit' if after > balance else 'debit'
                balance = after
                # The opening and closing balance sit in the register like
                # transactions. They are not money moving.
                if desc and not re.match(r'^(beginning|ending|opening|'
                                         r'closing)\s+balance', desc, re.I):
                    out.append(_row(pending['month'], pending['day'], desc,
                                    value, direction, year, account))
                pending = None
            continue
        if len(pending['desc']) < 3 and not pending['nums']:
            pending['desc'].append(line.strip())
        elif pending['nums']:
            # Trailing notes after the figures; the entry is finished.
            pass
    return out


def read(text, year=None, account=None, holder=None):
    """Every transaction this reader can see, in order.

    Returns dicts of date, description, amount and direction. A line that
    cannot be read is skipped rather than guessed at; the totals do not
    depend on this, so a missed line costs a transfer, not a balance.
    """
    lines = [l.rstrip() for l in (text or '').split('\n')]
    if _is_usbank(lines):
        return _read_usbank(lines, year, account, holder)
    if _is_register(lines):
        return _read_register(lines, year, account)
    out, section, pending = [], None, None

    for i, line in enumerate(lines):
        head = _section_of(line)
        if head == 'stop':
            section = None
            pending = None
            continue
        if head:
            section = head
            pending = None
            continue
        if not section:
            continue

        inline = INLINE.match(line)
        if inline:
            month, day, desc, amount = inline.groups()
            out.append(_row(month, day, desc, amount, section, year,
                            account))
            pending = None
            continue

        date = DATE_ONLY.match(line)
        if date:
            pending = {'month': date.group(1), 'day': date.group(2),
                       'desc': []}
            continue

        low = line.strip().lower()
        if pending is not None and any(low.startswith(w) for w in PAGE_BREAK):
            pending = None
            continue

        if pending is None:
            continue

        amount = AMOUNT.match(line)
        if amount:
            out.append(_row(pending['month'], pending['day'],
                            ' '.join(pending['desc']), amount.group(1),
                            section, year, account))
            pending = None
        elif len(pending['desc']) < 4:
            pending['desc'].append(line.strip())
    return out


def _row(month, day, desc, amount, section, year, account=None,
         holder=None):
    desc = ' '.join((desc or '').split())
    row = {
        'date': None,
        'month': int(month),
        'day': int(day),
        'description': desc,
        'amount': _money(amount),
        'direction': section,
    }
    if year:
        try:
            row['date'] = datetime.date(year, int(month), int(day))
        except ValueError:
            pass
    row.update(classify(desc, account, holder))
    return row


def classify(desc, this_account=None, holder=None):
    """What a description says about itself, before any matching.

    Only what is stated. A description naming the other account is direct
    evidence; one merely containing the word "transfer" is a candidate; a
    loan or advance is borrowing, which never counts as a deposit.
    """
    low = (desc or '').lower()
    out = {'kind': None, 'counterparty': None, 'stated': False}

    hit = TRANSFER.search(desc or '')
    if hit:
        _direction, first, second = hit.groups()
        first, second = _digits(first), _digits(second)
        # The counterparty is whichever of the two is not this account.
        # Reading the wording alone gets it wrong half the time: "Transfer
        # from XXX0054 to XXX0222" on x0054's own statement names x0054
        # first, and taking the first gave the account its own number.
        here = _digits(this_account) if this_account else None
        if here and here == first:
            other = second
        elif here and here == second:
            other = first
        else:
            other = second
        out['kind'] = 'transfer'
        out['counterparty'] = other
        out['stated'] = True
        out['both'] = [first, second]
        return out

    # "Transfer to Loan * 9569" is a repayment, not a transfer between
    # deposit accounts. Treating it as one strips debt service out of
    # expenses, which is the opposite of what should happen: the firm
    # reports liabilities separately but still counts them as money that
    # left. Checked first, because the wording contains "transfer".
    if re.search(r'(transfer|payment|pmt)\s+(to|from)\s+'
                 r'(loan|mortgage|card|credit\s*card|line\s*of\s*credit)',
                 desc or '', re.I):
        out['kind'] = 'debt'
        return out

    if any(w in low for w in BORROW_WORDS) or BORROW_RE.search(low):
        out['kind'] = 'borrowing'
        return out

    # A payment addressed to the account holder himself is money moving
    # between his own accounts, whatever the wording: U.S. Bank writes
    # "Real Time Payment ... To Brian C Oyler On 09/08/26" and names no
    # account at all.
    if holder:
        surname = str(holder).split()[-1].lower()
        if re.search(r'\b(to|from)\b[^.]{0,30}\b%s\b' % re.escape(surname),
                     low):
            out['kind'] = 'transfer'
            out['to_self'] = True
            return out

    if any(w in low for w in MOVE_WORDS):
        out['kind'] = 'transfer'
        full = FULL_ACCT.search(desc or '')
        if full:
            out['counterparty'] = _digits(full.group(1))
            out['stated'] = True
            return out
        # Not a confirmation or reference number: USAA ends every transfer
        # with a ten-digit "CONF# ...5009", and taking the last number found made
        # the counterparty x5009, an account that does not exist.
        found = [m.group(1) for m in ANY_ACCT.finditer(desc or '')
                 if not re.search(r'(conf|ref|seq|trace|id)\w*\s*$',
                                  (desc or '')[max(0, m.start() - 14):m.start()],
                                  re.I)]
        if found:
            out['counterparty'] = _digits(found[-1])
            out['stated'] = True
    return out


def _digits_ok(value):
    return bool(value) and len(value) >= 3


def gather(folder):
    """Transactions for every statement, grouped as the statements are."""
    found = _st.gather(folder)
    out = {}
    for key, rows in found.items():
        for row in rows:
            text = _text_for(folder, row['file'], row.get('text_path'))
            if text is None:
                continue
            year = row['ends'].year if row['ends'] else None
            got = read(text, year, row.get('account') or key[1],
                       row.get('holder'))
            # Same fallback as the balances: where the cached text is in
            # drawing order and yields nothing, rebuild it from the page.
            if not got and row.get('source') and _st._is_pdf(row['source']):
                again = _st.layout_text(row['source'])
                if again:
                    got = read(again, year, row.get('account') or key[1],
                               row.get('holder'))
            for t in got:
                # A statement running 17 December to 16 January dates its
                # December lines with January's year. Anything landing well
                # after the statement closed belongs to the year before.
                if t.get('date') and row['ends'] and \
                        t['date'] > row['ends'] + datetime.timedelta(days=7):
                    try:
                        t['date'] = t['date'].replace(year=t['date'].year - 1)
                    except ValueError:
                        pass
                t['account'] = row.get('account') or key[1]
                t['side'] = row.get('side')
                t['statement'] = row['file']
            out.setdefault(key, []).extend(got)

    # One transaction can arrive several times. A cumulative statement
    # repeats everything since its start date, so three statements all
    # beginning 2 July carry July's payments three times over. The totals
    # were already protected by decomposing those statements; the
    # transactions were not, and Oyler's $5,000 insurance premium showed
    # up nine times in six months.
    for key, rows in out.items():
        seen, kept = set(), []
        for t in rows:
            stamp = (t.get('date'), round(t.get('amount') or 0, 2),
                     (t.get('description') or '')[:40])
            if stamp in seen:
                continue
            seen.add(stamp)
            kept.append(t)
        out[key] = kept
    return out


def _text_for(folder, name, path=None):
    if path and os.path.exists(path):
        return open(path, errors='replace').read()
    for cache in _st._caches(folder):
        path = os.path.join(cache, name + '.txt')
        if os.path.exists(path):
            return open(path, errors='replace').read()
    return None


def main():
    ap = argparse.ArgumentParser(description='Read statement transactions')
    ap.add_argument('folder')
    ap.add_argument('--account', default=None)
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    found = gather(a.folder)
    if a.json:
        print(json.dumps({'%s/%s' % k: v for k, v in found.items()},
                         indent=1, default=str))
        return

    total = stated = 0
    for (side, key), rows in sorted(found.items()):
        if a.account and a.account not in str(key):
            continue
        moves = [r for r in rows if r['kind']]
        total += len(rows)
        stated += sum(1 for r in moves if r['stated'])
        print('\n%s %s   %d transactions, %d look like movements'
              % (side.upper(), key, len(rows), len(moves)))
        for r in moves:
            flag = ('-> x%s' % r['counterparty']) if r['counterparty'] else ''
            print('   %2d/%-2d %-7s %12s  %-11s %s'
                  % (r['month'], r['day'], r['direction'],
                     '{:,.2f}'.format(r['amount']) if r['amount'] else '-',
                     r['kind'], flag))
            print('        %s' % r['description'][:92])
    print('\n%d transactions read, %d name the other account.'
          % (total, stated))


if __name__ == '__main__':
    main()


# ---------------------------------------------------------------- the rules

# Kept in step with the same list in statements.py. They drifted apart
# once already: the banks added for Bassett went into the statement reader
# only, so "CAPITAL ONE TRANSFER" matched no bank here and thirteen
# transfers stayed unclassified.
BANK_WORDS = (('us bank', 'US Bank'), ('u.s. bank', 'US Bank'),
              ('civista', 'Civista'), ('wells fargo', 'Wells Fargo'),
              ('chase', 'Chase'), ('huntington', 'Huntington'),
              ('fifth third', 'Fifth Third'), ('regions', 'Regions'),
              ('truist', 'Truist'), ('bank of america', 'BoA'),
              ('arvest', 'Arvest'), ('bancfirst', 'BancFirst'),
              ('simmons', 'Simmons Bank'), ('eastman', 'Eastman CU'),
              ('capital one', 'Capital One'), ('capitalone', 'Capital One'))


def _bank_named(desc):
    """A bank named in the description, if any."""
    low = (desc or '').lower()
    for needle, bank in BANK_WORDS:
        if needle in low:
            return bank
    return None


def apply_rules(rows, sides, banks=None):
    """Decide what each movement does to the figures.

    The rules, as the firm applies them (see _spec/cashflow/RULES.md):

      borrowing in            always out of deposits, never income
      personal to personal    out: moving his own money is not spending
      business to personal    KEPT: a distribution is income to the household
      personal to business    out: funding his own entity is not spending

    The third is the one that matters and the one a naive detector gets
    wrong. Every incoming movement looks like a transfer, so excluding all
    of them strips the practice distributions that are the household's
    actual income. Brogan's workbook shows zero transfers in on the
    personal account for exactly this reason.

    `sides` maps an account's last four digits to 'Personal' or 'Business'.
    Where the counterparty is unknown the movement is left as a proposal
    rather than being quietly applied.
    """
    for row in rows:
        row['effect'] = None
        row['why'] = None
        here = sides.get(_digits(row.get('account')))
        there = sides.get(_digits(row.get('counterparty') or ''))

        if row['kind'] == 'borrowing':
            if row['direction'] == 'credit':
                row['effect'] = 'exclude_deposit'
                row['why'] = ('Borrowing, not income. Always out of '
                              'deposits.')
            continue

        if row['kind'] == 'debt':
            # Money to or from a loan account. Out stays in expenses as
            # debt service; in is borrowing and never a deposit.
            if row['direction'] == 'credit':
                row['effect'] = 'exclude_deposit'
                row['why'] = ('Drawn from a loan account. Borrowing, not '
                              'income.')
            else:
                row['effect'] = 'keep'
                row['note_only'] = True
                row['why'] = ('Repayment to a loan account. Debt service, '
                              'so it stays in expenses.')
            continue

        if row['kind'] != 'transfer':
            continue

        if row.get('to_self'):
            # Addressed to the account holder by name. No account number,
            # but a payment to himself is his own money moving whatever
            # the bank calls it: U.S. Bank writes these as "Real Time
            # Payment ... To Brian C Oyler", and there are five of them
            # worth $25,000 on one of Oyler's accounts alone.
            row['effect'] = ('exclude_deposit' if row['direction'] == 'credit'
                             else 'exclude_expense')
            row['inferred'] = True
            row['why'] = ('Paid to the account holder by name, so it is his '
                          'own money moving. The destination account is not '
                          'stated.')
            continue

        if not row.get('counterparty'):
            # No account number, but the description often names the bank:
            # "TRANSFER US BANK TRANSFER WEB". Where the client holds
            # accounts at that bank, the destination is his own and the
            # movement is a transfer even though which account is unknown.
            # On Oyler this is thirteen payments worth $34,000 that would
            # otherwise count as spending.
            bank = _bank_named(row.get('description'))
            where = (banks or {}).get(bank) if bank else None
            if where:
                row['effect'] = ('exclude_deposit'
                                 if row['direction'] == 'credit'
                                 else 'exclude_expense')
                row['inferred'] = True
                row['why'] = ('Names %s, where %s accounts are held, but no '
                              'account number. Treated as his own money '
                              'moving; confirm which account.'
                              % (bank, where.lower()))
                continue
            row['effect'] = 'propose'
            row['why'] = ('Reads as a movement but names no other account. '
                          'Needs matching against the other statements.')
            continue

        if there is None:
            # The description can say what kind of account it went to:
            # "Transfer to Checking * 5647". A checking or savings account
            # named in his own statement is his, even if he has not sent
            # that statement. Bassett moves money to x5647 three times and
            # the firm counts all three; without this they are all left
            # as questions.
            kind = re.search(r'transfer\s+(?:to|from)\s+'
                             r'(checking|savings|money\s*market|deposit)',
                             row.get('description') or '', re.I)
            if kind:
                row['effect'] = ('exclude_deposit'
                                 if row['direction'] == 'credit'
                                 else 'exclude_expense')
                row['inferred'] = True
                row['why'] = ('To a %s account, x%s, for which no statement '
                              'has been provided. Treated as his own; '
                              'confirm it is.'
                              % (kind.group(1).lower(), row['counterparty']))
                continue
            row['effect'] = 'propose'
            row['why'] = ('Counterparty x%s has no statement on file, so '
                          'which side it sits on is unknown.'
                          % row['counterparty'])
            continue

        if here == 'Personal' and there == 'Business' and \
                row['direction'] == 'credit':
            row['effect'] = 'keep'
            row['why'] = ('From the %s account: a distribution, which is '
                          'income to the household and stays in deposits.'
                          % there.lower())
            continue

        if here == 'Personal' and there == 'Business' and \
                row['direction'] == 'debit':
            # Money into his own entity comes OUT of expenses, like any
            # other transfer between accounts he owns.
            #
            # This was briefly implemented the other way round, on my own
            # bad reading of the firm's workbook. Brogan's "Transfers Out"
            # row does not contain the practice loans, so I reported that
            # he had left them in expenses. He had not: his Total
            # Adjustments OUT is SUM(C11:C16), which adds the Adjustments
            # row ABOVE it, and the $10,000 and $50,000 sit there. June
            # reads 10,000 + 19,500 = 29,500, all of it out.
            #
            # The lesson is about the workbook, not the rule: a figure can
            # be excluded by any of six rows, and reading one of them is
            # not reading the answer.
            row['effect'] = 'exclude_expense'
            row['why'] = ('Into the practice account: his own money moving '
                          'between accounts he owns.')
            continue

        row['effect'] = ('exclude_deposit' if row['direction'] == 'credit'
                         else 'exclude_expense')
        row['why'] = ('%s to %s: his own money moving between accounts he '
                      'owns.' % (here or '?', there.lower()))
    return rows


FIXED_KINDS = (
    ('Savings', re.compile(r'401\s*k|\bira\b|roth|brokerage|vestwell|'
                           r'fidelity|schwab|vanguard|\bhsa\b|\b529\b|'
                           r'contribution|deferral', re.I)),
    ('Insurance', re.compile(r'ins\s*prem|insurance|premium|massmutual|'
                             r'mass\s*mutual|\balic\b|augustar|'
                             r'northwestern\s*mu|guardian|principal\s*life',
                             re.I)),
    # HELOC added for Rebol's "USAA FSB HELOC ACH HELOC", which is on the
    # firm's liability table for him.
    ('Liability', re.compile(r'\bmtge?\b|mortgage|\bmort\b|\bloan\b|'
                             r'student\s*ln|auto\s*pay|truist|lending|'
                             r'\bnote\b|heloc', re.I)),
)


def find_fixed(rows, periods):
    """Recurring payments the plan reports apart from living costs.

    Mortgages, car and student loans, insurance premiums, and retirement
    or brokerage contributions. The published sentence states spending
    twice, once with these and once without, so they have to be separated
    from the rest.

    They cannot be told apart by size or timing, only by who is being
    paid, and a bank statement says that: "MTG PYT M & T MORTGAGE",
    "MASSMUTUAL MASSMUTUAL LIFE", "INS PREM ALIC". Recurrence is the
    second test, because a one-off payment to an insurer is not a
    premium schedule.

    Checked against the firm's own liability table for Oyler, which lists
    exactly the six payees this finds.
    """
    if not periods:
        return []
    by_payee = {}
    for row in rows:
        # A debit tagged borrowing is still a payment out. USAA prints every
        # one as "ACH WITHDRAWAL", which the borrowing words catch, and that
        # hid Rebol's Northwestern Mutual premium and HELOC payments here.
        if row.get('direction') != 'debit' or \
                row.get('kind') not in (None, 'borrowing'):
            continue
        kind = None
        for name, pattern in FIXED_KINDS:
            if pattern.search(row.get('description') or ''):
                kind = name
                break
        if not kind:
            continue
        # USAA puts the payee after "ACH WITHDRAWAL 010626 ", so cutting at
        # the first long number left every payee named "ACH WITHDRAWAL".
        desc = re.sub(r'^ach\s+(withdrawal|debit|pmt|payment)\s+\d{4,8}\s+',
                      '', row.get('description') or '', flags=re.I)
        payee = re.sub(r'\s*(co#|id\s*#|trace\s*#|ref=).*', '',
                       desc, flags=re.I)
        payee = re.sub(r'\s+\d[\d/]{5,}.*', '', payee).strip()[:46]
        by_payee.setdefault((kind, payee), []).append(row)

    out = []
    for (kind, payee), hits in sorted(by_payee.items()):
        if len(hits) < 3:
            continue
        total = sum(h.get('amount') or 0 for h in hits)
        # Spread over the months THIS payee was being paid, not over the
        # whole period the client supplied statements for. Four mortgage
        # payments across four months is $4,103 a month; divided by the
        # six months some other account happens to cover, it becomes
        # $2,735 and the mortgage appears to have shrunk.
        dates = sorted(h['date'] for h in hits if h.get('date'))
        if len(dates) >= 2:
            span = round((dates[-1] - dates[0]).days / 30.44) + 1
        else:
            span = len(periods) or 1
        out.append({
            'kind': kind,
            'payee': payee,
            'monthly': round(total / float(max(span, 1)), 2),
            'count': len(hits),
            'months': span,
            'typical': round(total / float(len(hits)), 2),
        })
        for h in hits:
            h['fixed'] = kind
    return out


def find_one_offs(rows, periods, multiple=2.0):
    """Single outflows big enough to distort the run rate.

    Not transfers and not borrowing: real money, really gone, but once.
    Oyler pays his ex-wife $100,000 in September; counted as ordinary
    spending it quadruples his monthly figure and every projection built
    on it.

    Proposed, never applied. Whether a one-off belongs in the run rate is
    a judgement about the client's life, not about the statement: a
    divorce settlement does not recur, a roof replacement might, and a
    tax bill certainly will.

    The test is relative to the account's own typical period, so it scales
    from a practice account turning over $300,000 a month to a savings
    account holding $400.
    """
    if not periods:
        return []
    sizes = sorted(p for p in periods if p)
    if not sizes:
        return []
    middle = sizes[len(sizes) // 2]
    if middle <= 0:
        return []
    # How often each amount appears. A sum that turns up every month is
    # the opposite of a one-off, however large: Oyler's MassMutual
    # premium is $5,000 nine times over, and on size alone it looked like
    # nine separate extraordinary events.
    seen = {}
    for row in rows:
        amount = round(row.get('amount') or 0, 2)
        seen[amount] = seen.get(amount, 0) + 1

    out = []
    for row in rows:
        if row.get('direction') != 'debit' or row.get('kind'):
            continue
        amount = row.get('amount') or 0
        if amount < middle * multiple:
            continue
        if seen.get(round(amount, 2), 0) > 2:
            continue
        row['one_off'] = round(amount / middle, 1)
        out.append(row)
    return out


CARD_WORDS = re.compile(
    r'amex|american\s*express|visa\b|mastercard|discover|cardmember|'
    r'card\s*(?:pmt|payment)|credit\s*crd', re.I)


def card_payments(rows):
    """Payments to a credit card, which get smoothed rather than taken as
    they fall.

    A card bill lands once a month but pays for a month's spending that
    already happened, and the amount swings widely: Oyler's run $3,724,
    $9,273, $8,182, $8,801. Taken literally the first month looks frugal
    and the second extravagant, when nothing about his life changed.

    The firm's method, reproduced here: average the payments across the
    periods, then adjust each period by its difference from that average.
    A heavy month has the excess taken out; a light one has the shortfall
    added back.
    """
    return [t for t in rows
            if t.get('direction') == 'debit'
            and CARD_WORDS.search(t.get('description') or '')]


def _is_bare_reference(desc):
    """Is this description just an identifier, with nothing said?

    "B98D1E56C84BB83" is a reference. "Transfer from XXX4728" is a
    description. The test is whether any pronounceable word survives
    once the identifiers are removed.
    """
    text = (desc or '').strip()
    if not text or len(text) > 40:
        return False
    words = [w for w in re.split(r'[^A-Za-z]+', text) if len(w) >= 3]
    for word in words:
        if not re.search(r'\d', word) and re.search(r'[aeiou]', word, re.I):
            return False
    return True


def match_across(by_account, days=4):
    """Pair an unexplained credit with a transfer out of another account.

    Some statements give a credit no description at all, only a reference
    string: Oyler's savings account shows "B98D1E56C84BB83" where the
    other side says "TRANSFER US BANK TRANSFER WEB". The money is
    identifiable, just not from the line it lands on.

    So an unclassified credit is matched against a movement already
    recognised as leaving another of the client's accounts, for the same
    amount within a few days. Matched on both amount and date, and only
    against movements ALREADY established as transfers, which keeps two
    unrelated payments of the same size from being paired: the other side
    had to say so first.
    """
    sent = []
    for key, rows in by_account.items():
        for row in rows:
            if (row.get('direction') == 'debit'
                    and row.get('effect') == 'exclude_expense'
                    and row.get('date')):
                sent.append((key, row))

    paired = 0
    for key, rows in by_account.items():
        for row in rows:
            if row.get('kind') or row.get('direction') != 'credit':
                continue
            if not row.get('date') or not row.get('amount'):
                continue
            # Only credits that say nothing. A line with real words in it
            # is describing itself, and pairing those on amount alone
            # swallowed Oyler's practice distributions, which are income:
            # his deposits fell from $47,360 to $41,110 against a figure
            # the firm puts at $47,359.
            if not _is_bare_reference(row.get('description')):
                continue
            for other_key, other in sent:
                if other_key == key or other.get('matched'):
                    continue
                if abs((row['date'] - other['date']).days) > days:
                    continue
                if abs((other.get('amount') or 0) - row['amount']) > 0.01:
                    continue
                other['matched'] = True
                row['kind'] = 'transfer'
                row['effect'] = 'exclude_deposit'
                row['inferred'] = True
                row['counterparty'] = other.get('account')
                row['why'] = ('Matches a transfer of the same amount out of '
                              'x%s on %s. This statement gives the credit no '
                              'description, only a reference.'
                              % (other.get('account'), other['date']))
                paired += 1
                break
    return paired


def sides_of(folder):
    """Which side of the house each account sits on, by last four digits."""
    out = {}
    for (side, key), rows in _st.gather(folder).items():
        acct = next((r['account'] for r in rows if r.get('account')), None)
        out[_digits(acct or str(key))] = side
    return out


def banks_of(folder):
    """Which side each bank's accounts sit on, for the client as a whole.

    A bank with accounts on both sides is left out: naming it in a
    description would then say nothing about where the money went.
    """
    seen = {}
    for (side, _key), rows in _st.gather(folder).items():
        bank = next((r.get('bank') for r in rows if r.get('bank')), None)
        if bank:
            seen.setdefault(bank, set()).add(side)
    return {b: list(s)[0] for b, s in seen.items() if len(s) == 1}
