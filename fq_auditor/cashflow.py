#!/usr/bin/env python3
"""Turn a client's bank statements into the cash flow workbook.

    python3 cashflow.py "<client folder>" --out "Oyler Cash Flow 2026.numbers"

WHAT THIS DOES AND DOES NOT DO YET
It reads every statement, groups the accounts by entity, derives expenses
by reconciliation, and writes the workbook. Every figure in it comes from a
statement.

It does NOT yet identify transfers, because a transfer is a transaction and
this pipeline deliberately never reads transaction lines: expenses are
derived as beginning + additions - ending, which is correct by construction
and needs no line to be parsed. That trade is worth making for the headline
figure and cannot be made for transfers, which are individual movements.

So the adjustment columns come through as zero and the workbook says so,
loudly, rather than presenting an unadjusted figure as though it were
final. On Oyler the difference is large: his Civista x0054 shows $50,892 of
expenses in June of which $19,500 was money moved to his own accounts.

ENTITIES
The statements are grouped the way the firm's workbooks are: Personal, the
practice, and each property company on its own sheet. Which side an account
is on comes from where the document was filed and is cross-checked against
the holder printed on the statement.
"""
import re
import os
import sys
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import statements as _st                                     # noqa: E402
import transactions as _tx                                   # noqa: E402
import cashflow_workbook as _wb                              # noqa: E402

MONTHS = ('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec').split()
WINDOW = 4          # statement periods per account, as the template holds


def _period(row):
    # A statement running 7/01 to 8/02 is July's, not August's. Civista closes
    # a day or two into the next month, so Oyler's practice account read May,
    # Jun, Aug, Aug and July went missing.
    d, b = row['ends'], row.get('begins')
    if d and b and d.day <= 3 and (b.year, b.month) != (d.year, d.month):
        d = b
    return '%s %d' % (MONTHS[d.month - 1], d.year) if d else '?'


def _entity_of(side, key):
    """Which sheet an account belongs on.

    Personal is one sheet. On the business side each property company gets
    its own, matching how the firm already splits them, and anything left
    is the practice.
    """
    if side == 'Personal':
        return 'Personal'
    name = str(key)
    if name.isdigit() or re.match(r'x\d{3,}$', name, re.I):
        return 'Practice'      # an account number, not a company
    return name                # Moonridge, Eden, and friends, named by folder


def build(folder):
    """Every account, grouped into entities ready for the workbook."""
    found = _st.gather(folder)
    # Transfers, and the rules that decide what each one does. Without
    # this every pound Brian moved between his own accounts counts as
    # spending: on Civista x0054 that is $59,000 over four months.
    sides, banks = _tx.sides_of(folder), _tx.banks_of(folder)
    moves = _tx.gather(folder)
    for key in moves:
        _tx.apply_rules(moves[key], sides, banks)
    # Then pair up what is still unexplained against what is: a credit
    # with no description can often be recognised by the debit that
    # created it on another account.
    _tx.match_across(moves)
    _mark_scheduled(folder, moves)
    entities = {}
    # The analyst’s review of the last workbook, read back before building
    # (cashflow_review.py) and applied at the end, so nothing downstream
    # uses the unreviewed reading.
    try:
        import cashflow_review as _review
        _review.harvest(folder)
    except Exception:                                        # noqa: BLE001
        _review = None

    for (side, key), rows in sorted(found.items()):
        # A decomposed statement is a real month and belongs in the
        # averages; only one that could not be decomposed is dropped.
        usable = [r for r in rows
                  if r['expenses'] is not None
                  and (r.get('decomposed') or not r.get('overlaps'))]
        if not usable:
            continue
        dropped = len(rows) - len(usable)
        # The four most recent periods, which is what the firm's template
        # holds and what every one of its workbooks uses. Rebol sent five and
        # six per account; the oldest of x9634's runs 17 December to 16
        # January and carries a $49,000 Amex payoff funded by a line of
        # credit, which on its own adds $11,000 a month to the average.
        older = usable[:-WINDOW] if len(usable) > WINDOW else []
        usable = usable[-WINDOW:]
        # Flag the one-offs before the account is assembled: the account
        # carries their total, and an earlier version detected them after
        # building it, so the list was always empty.
        _tx.find_one_offs(moves.get((side, key)) or [],
                          [r['expenses'] for r in usable if r['expenses']],
                          0.3)

        acct = {
            # Named the way the firm's workbooks name them: what the
            # account is, then the bank and last four. "Personal account
            # (x0054)" tells a reader nothing they did not already know
            # from the sheet they are looking at.
            'name': _label(key, usable),
            'balance': usable[-1]['ending'],
            # The institution on its own, and the date the balance is
            # good as of. Both are already inside the label, but a table
            # with an INSTITUTION column cannot dig them back out of a
            # string, and a balance printed without its date is the kind
            # of figure that gets quoted three months later.
            'bank': _bank_of(usable),
            'as_of': usable[-1].get('ends'),
            'periods': [_period(r) for r in usable],
            'beginning': [r['beginning'] for r in usable],
            'additions': [r['additions'] for r in usable],
            'ending': [r['ending'] for r in usable],
            'transfers_in': [_sum(moves.get((side, key)), r,
                                  'exclude_deposit') for r in usable],
            'transfers_out': [_sum(moves.get((side, key)), r,
                                   'exclude_expense') for r in usable],
            'adj_out': [_sum(moves.get((side, key)), r, 'exclude_expense')
                        + max(0.0, _card_gap(moves.get((side, key)),
                                             usable, r))
                        for r in usable],
            'adj_in': [max(0.0, -_card_gap(moves.get((side, key)),
                                           usable, r)) for r in usable],
            'surplus_expense': [
                r['expenses'] - _sum(moves.get((side, key)), r,
                                     'exclude_expense') for r in usable],
            # Whether any transaction on this account could be read at
            # all. Without it, "no transfers found" and "no transfers
            # exist" look identical downstream.
            # How many months the statements actually cover, which is not
            # the number of statements. Oyler's Civista x0222 has four,
            # but the first spans 2 April to 1 July: a quarter counted as
            # one month understates that account's rate threefold.
            'months': _months_of(usable),
            'stmt_months': _statement_months(usable),
            'transactions_read': bool(moves.get((side, key))),
            'one_offs': [t['amount'] or 0 for t in
                         (moves.get((side, key)) or ())
                         if t.get('one_off')],
        }
        name = _entity_of(side, key)
        ent = entities.setdefault(name, {'name': name, 'accounts': [],
                                         'liabilities': [],
                                         'adjustments': []})
        ent['accounts'].append(acct)

        # Single outflows large enough to distort the run rate, already
        # flagged above.
        for t in (moves.get((side, key)) or ()):
            if not t.get('one_off'):
                continue
            if not t.get('date'):
                continue
            t['effect'] = 'propose'
            t['why'] = ('Single outflow of %s, about %s times this '
                        'account\u2019s usual period. Real money, but it '
                        'looks like a one-off rather than a run rate. '
                        'Exclude it?'
                        % ('{:,.0f}'.format(t['amount'] or 0),
                           t.get('one_off')))

        # Every movement that still needs a human becomes a row on the
        # adjustments block, with the reason the rule gave.
        for t in (moves.get((side, key)) or ()):
            if not t.get('date'):
                continue
            if t.get('effect') not in ('propose',) and \
                    not t.get('note_only'):
                continue
            ent_name = _entity_of(side, key)
            entities.setdefault(ent_name, {'name': ent_name, 'accounts': [],
                                           'liabilities': [],
                                           'adjustments': []})
            entities[ent_name]['adjustments'].append(
                (_label(key, rows), t['date'].strftime('%b %Y'),
                 'Note' if t.get('note_only') else
                 ('Transfer %s' % ('in' if t['direction'] == 'credit'
                                   else 'out')),
                 t['amount'] or 0,
                 '%s  %s' % (t['why'], t['description'][:70]),
                 'By rule' if t.get('note_only') else 'For review'))

        for r in rows:
            for note in r['notes']:
                ent['adjustments'].append(
                    (_label(key, rows), _period(r), 'Note', 0, note,
                     'For review'))
        if older:
            ent['adjustments'].append(
                (_label(key, rows), 'All', 'Note', 0,
                 '%d older statement%s (%s) left out: the averages use the '
                 'four most recent periods.'
                 % (len(older), '' if len(older) == 1 else 's',
                    ', '.join(_period(r) for r in older)), 'By rule'))
        if dropped:
            ent['adjustments'].append(
                (_label(key, rows), 'All', 'Note', 0,
                 '%d statement%s on this account overlap an earlier one and '
                 'have been left out of the averages, because a cumulative '
                 'statement reports money already counted.'
                 % (dropped, '' if dropped == 1 else 's'), 'For review'))

    order = ['Personal', 'Practice']
    rest = sorted(k for k in entities if k not in order)
    built = [entities[k] for k in order + rest if k in entities]
    if _review:
        try:
            _review.apply(folder, built)
        except Exception:                                    # noqa: BLE001
            pass
    return built


def _bank_of(rows):
    """The bank, from these statements only.

    Scoped to the account's own statements. An earlier version searched
    every statement the client had, so an account whose own documents name
    no bank inherited whichever one happened to be found first: Bassett's
    Capital One account was labelled Arvest because its siblings were.
    Better to name no bank than the wrong one.
    """
    for r in rows:
        if r.get('bank'):
            return r['bank']
    for r in rows:
        low = (r.get('file') or '').lower()
        # Bank names only. An entity name is not evidence of who banks
        # them: "moonridge" was mapped to Wells Fargo here, and the
        # statement names no bank at all, so the label was asserting
        # something no document says.
        for word, name in (('civista', 'Civista'), ('usb', 'US Bank'),
                           ('us bank', 'US Bank'), ('wells', 'Wells Fargo'),
                           ('boa', 'BoA'), ('chase', 'Chase'),
                           ('huntington', 'Huntington'),
                           ('fifth', 'Fifth Third')):
            if word in low:
                return name
    return None


def _kind_of(rows):
    """Checking, savings or money market, from the statement file name."""
    for r in rows:
        low = (r.get('file') or '').lower()
        for word, name in (('money market', 'Money Market'),
                           ('savings', 'Savings'), ('checking', 'Checking'),
                           ('cking', 'Checking')):
            if word in low:
                return name
    return None


_CARD_CACHE = {}


def _card_gap(moves, periods, row):
    """How far this period's card payments sit from the average.

    Positive means the period paid more than usual, so the excess comes
    out of expenses; negative means it paid less, and the shortfall is
    added back.
    """
    if not moves or not (row['begins'] and row['ends']):
        return 0.0
    key = id(moves)
    if key not in _CARD_CACHE:
        cards = _tx.card_payments(moves)
        by_period = []
        for p in periods:
            if not (p['begins'] and p['ends']):
                by_period.append(0.0)
                continue
            by_period.append(sum(
                c['amount'] or 0 for c in cards
                if c.get('date') and p['begins'] <= c['date'] <= p['ends']))
        average = (sum(by_period) / len(by_period)) if by_period else 0.0
        _CARD_CACHE[key] = (by_period, average)
    by_period, average = _CARD_CACHE[key]
    for i, p in enumerate(periods):
        if p is row:
            return round(by_period[i] - average, 2)
    return 0.0


def _statement_months(rows):
    """How many months the statements stand for, the way the firm counts.

    One per monthly statement, whatever its exact days (the lead advisor divides
    Oyler's x0054 by four statements, not 3.98 months), but a quarterly
    statement is three: x0222's first statement runs 2 April to 1 July,
    and counting it as one month put $27,000 of premiums into one period.
    """
    total = 0
    for r in rows:
        b, e = r.get('begins'), r.get('ends')
        days = (e - b).days if (b and e) else 30
        total += max(1, int(round(days / 30.44)))
    return total or 1


def _months_of(rows):
    """Months the statements cover, from the dates printed on them.

    RULES.md: sum the window, divide by the months it spans. Dividing by
    the number of statements instead assumes each one covers a month, and
    banks do not oblige.
    """
    spans = [(r['begins'], r['ends']) for r in rows
             if r.get('begins') and r.get('ends')]
    if not spans:
        return float(len(rows) or 1)
    days = sum((e - b).days for b, e in spans)
    return max(round(days / 30.44, 2), 1.0)


def _sum(moves, row, effect):
    """Total of one kind of adjustment inside a statement period."""
    if not moves or not (row['begins'] and row['ends']):
        return 0
    total = 0.0
    for t in moves:
        if not t.get('date') or t.get('effect') != effect:
            continue
        # Inclusive at both ends. U.S. Bank's period opens on the day of the
        # first transaction ("Jun 25 ... through Jul 23", first entry Jun 25),
        # and a strict start dropped Oyler's $5,000 to himself that day.
        if row['begins'] <= t['date'] <= row['ends']:
            total += t.get('amount') or 0
    return round(total, 2)


def _label(key, rows):
    """How the account is named on the page.

    The number printed on the statement wins over the folder it was filed
    in. On Oyler the practice account is filed under 4782 and the statement
    says 4728; one of the two is a transposition and the statement is the
    document of record.
    """
    printed = next((r['account'] for r in rows if r.get('account')), None)
    number = 'x%s' % (printed or key)
    if printed and str(key).isdigit() and printed != str(key):
        number = 'x%s (filed as %s)' % (printed, key)
    bank, kind = _bank_of(rows), _kind_of(rows)
    # An entity-named folder already says what the account is, so repeating
    # the folder name inside its own brackets ("x9700 (x9700)") adds
    # nothing, and a folder with no number should not invent one.
    if not str(key).isdigit():
        plain = str(key).lstrip('xX')
        inner = ' '.join(x for x in (bank, number)
                         if x and x.lstrip('xX') != plain)
        return '%s (%s)' % (key, inner) if inner else str(key)
    bits = ' '.join(x for x in (bank, number) if x)
    return '%s (%s)' % (kind, bits) if kind else bits


def main():
    ap = argparse.ArgumentParser(description='Build the cash flow workbook')
    ap.add_argument('folder')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    entities = build(a.folder)
    if not entities:
        print('No readable bank statements in this client folder.')
        return
    out = a.out or 'Cash Flow.numbers'
    path, overflow, spare = _wb.write(entities, out)
    print(path)
    if overflow:
        print('  %d entit%s did not fit: the template holds four sheets.'
              % (overflow, 'y' if overflow == 1 else 'ies'))
    for e in entities:
        n = sum(len(x['periods']) for x in e['accounts'])
        print('  %-12s %d account%s, %d statement periods'
              % (e['name'], len(e['accounts']),
                 '' if len(e['accounts']) == 1 else 's', n))
    n = sum(len(e['adjustments']) for e in entities)
    if n:
        print('\n%d movement%s need a decision; they are on the adjustments '
              'block of each sheet.' % (n, '' if n == 1 else 's'))


if __name__ == '__main__':
    main()


# ------------------------------------------------------ for the Assumptions

def _trend(each, half):
    """Which way an account is moving, or nothing at all.

    Two periods cannot show a trend and four can barely. So the answer is
    one of three words rather than a slope, and an account with fewer than
    four periods is given no word at all. A direction printed off two
    numbers would be read as a finding, and it is not one.
    """
    if len(each) < 4 or not half:
        return None
    first = sum(each[:half]) / half
    second = sum(each[half:]) / (len(each) - half)
    move = second - first
    # A tenth of the account's own scale, so a large account is not called
    # falling over a rounding difference and a small one is not called flat
    # over a move that matters to it.
    floor = max(abs(first), abs(second)) * 0.10
    if abs(move) < floor:
        return 'flat'
    return 'improving' if move > 0 else 'worsening'


def for_assumptions(folder):
    """The two figures the Assumptions needs, from the same build.

    Section 5 wants a line per non-qualified account: its balance, its
    average adjusted deposit and expense, and the difference. Section 12
    wants household spending, stated twice: with the liabilities,
    insurance and savings payments in, and with them out.

    Derived here rather than in the plan, so the published sentence and
    the workbook cannot disagree. Everything comes from the entity
    structure the workbook is built from.
    """
    entities = build(folder)
    accounts, monthly = [], 0.0
    for entity in entities:
        personal = entity['name'] == 'Personal'
        for acct in entity['accounts']:
            periods = len(acct['periods'])
            if not periods:
                continue
            # Per statement, as the firm averages (the lead advisor’s Assumptions divide
            # by the number of statements, not the days they span): Oyler's
            # x0054 deposits read $47,598 over 3.98 months against his
            # $47,359 over four statements.
            months = acct.get('stmt_months') or periods
            exp = [b + d - e for b, d, e in
                   zip(acct['beginning'], acct['additions'], acct['ending'])]
            adj = [x - o + i for x, o, i in
                   zip(exp, acct['adj_out'], acct['adj_in'])]
            dep = [d - i for d, i in
                   zip(acct['additions'], acct['transfers_in'])]
            spend = [x - o for x, o in zip(exp, acct['transfers_out'])]
            # An account whose transactions could not be read has no
            # transfers detected, so its deposits and expenses still
            # contain money that merely moved. Publishing those as the
            # client's spending would be worse than publishing nothing:
            # Oyler's x1145 reads $21,161 a month against a true $661,
            # the difference being one $82,000 transfer to his own
            # account. US Bank's statements fragment under extraction and
            # are the known case.
            seen = acct.get('transactions_read')
            row = {
                'entity': entity['name'],
                'name': acct['name'],
                'balance': acct['balance'],
                'bank': acct.get('bank'),
                'as_of': acct.get('as_of'),
                'periods': periods,
                'readable': bool(seen),
            }
            if seen:
                # One-off outflows come out of the account's expense line too,
                # as the lead advisor takes them out: Oyler's x0054 read $49,749 a month
                # with the $100,000 in it, against his $23,785.
                once = sum(acct.get('one_offs') or ())
                if once:
                    spend = list(spend)
                    spend[-1] -= once
                # Per period as well as on average. An account averaging a
                # surplus can still have run dry in three months out of
                # four, and the average is the one figure that cannot show
                # it. The Prospect Summary prints the count beside the
                # average for exactly that reason.
                each = [d - s for d, s in zip(dep, spend)]
                half = len(each) // 2
                row.update({
                    'deposit': round(sum(dep) / months, 2),
                    'expense': round(sum(spend) / months, 2),
                    'surplus': round((sum(dep) - sum(spend)) / months, 2),
                    'by_period': [round(x, 2) for x in each],
                    'negatives': sum(1 for x in each if x < 0),
                    'trend': _trend(each, half),
                })
            else:
                row['why'] = ('Transactions on this statement could not be '
                              'read, so transfers have not been found and '
                              'the averages would include money that only '
                              'moved between accounts.')
            accounts.append(row)
            if personal and seen:
                monthly += sum(adj) / months
                # One-off outflows come out of the published run rate.
                # They are real money and they stay on the adjustments
                # block for the analyst to put back, but a divorce
                # settlement is not what the household spends each month,
                # and leaving Oyler's $100,000 in raises his monthly
                # figure by $25,000.
                for t in (acct.get('one_offs') or ()):
                    monthly -= (t or 0) / months

    fixed_rows = _liabilities(folder)
    fixed = sum(a for _n, a, _w in fixed_rows)
    return {
        'accounts': accounts,
        'fixed_rows': fixed_rows,
        'one_offs': [t for e in entities for a in e['accounts']
                     for t in (a.get('one_offs') or ())],
        'monthly_including': round(monthly, 2),
        'fixed': round(fixed, 2),
        'monthly_excluding': round(monthly - fixed, 2),
        'annual_including': round(monthly * 12, 2),
        'annual_excluding': round((monthly - fixed) * 12, 2),
    }


def _schedule_payments(folder):
    """[(label, monthly payment)] from the client's own debt schedule."""
    try:
        import debt as _debt
        got = _debt.gather(folder)
    except Exception:                                        # noqa: BLE001
        return []
    out = []
    for r in (got.get('personal') or []) + (got.get('practice') or []):
        if r.get('payment') and r.get('side') == 'Personal':
            label = ' '.join(x for x in (r.get('creditor'), r.get('description'))
                             if x)
            out.append((label, float(r['payment'])))
    return out


def _mark_scheduled(folder, moves):
    """A debit that pays a loan on the client's own debt schedule is debt
    service, whatever the bank calls it.

    USAA prints Rebol's boat and Tesla payments as "ACH PAYMENT TRANSFER",
    $679.22 and $892.93, the exact figures on his Personal Debt sheet. Read
    as transfers they were taken out of his spending AND missed as fixed
    payments, so both of the published figures were wrong.
    """
    sched = _schedule_payments(folder)
    if not sched:
        return
    for (side, _key), rows in moves.items():
        if side != 'Personal':
            continue
        for t in rows:
            if t.get('direction') != 'debit':
                continue
            for label, pay in sched:
                if abs((t.get('amount') or 0) - pay) <= 1.0:
                    t['kind'] = 'debt'
                    t['effect'] = 'keep'
                    t['scheduled'] = label
                    break


def _liabilities(folder):
    """Fixed payments the plan reports apart: liabilities, insurance, savings.

    Found in the transactions by who is being paid, then anything the
    analyst has recorded by hand on top. An earlier version read only the
    input store, so a client with nothing typed in had no fixed payments
    at all and the two published figures came out identical.
    """
    rows, periods = [], []
    moves = _tx.gather(folder)
    for (side, _key), got in moves.items():
        if side == 'Personal':
            rows.extend(got)
    dates = [t['date'] for t in rows if t.get('date')]
    span = (round((max(dates) - min(dates)).days / 30.44) + 1
            if len(dates) >= 2 else 1)
    out = [(f['payee'], f['monthly'], f['kind'])
           for f in _tx.find_fixed(rows, range(span))]
    # Payments matching the client's debt schedule, when the bank's wording
    # gave no hint (see _mark_scheduled). One line per loan, at the
    # schedule's own payment, unless a payee above already carries it.
    for label, pay in _schedule_payments(folder):
        hits = [t for t in rows if t.get('direction') == 'debit'
                and abs((t.get('amount') or 0) - pay) <= 1.0]
        if len(hits) >= 2 and not any(abs(a - pay) <= 1.0 for _n, a, _k in out):
            out.append((label, round(pay, 2), 'Liability'))
    try:
        import inputs as _inputs
        got = (_inputs.get(folder, 'fixed_payments') or {}).get('value') or []
        for row in got:
            out.append((row.get('label'), row.get('amount') or 0,
                        row.get('kind') or row.get('paid_from')))
    except Exception:
        pass
    return out
