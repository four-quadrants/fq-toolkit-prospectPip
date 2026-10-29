#!/usr/bin/env python3
"""Step 4: the due diligence questions, drafted from what the documents show.

    python3 duediligence.py "<client folder>"

WHAT IT MAKES
  _Audit/Due diligence - <Surname>.numbers   one row per question, with why
      it is being asked and the document behind it, for the ANALYST first:
      the Decision column says Send, Strike (not needed) or Answered (the
      analyst settled it from the file). Edit it in Numbers and save.
  _Audit/Follow-up email - <Surname>.txt     the lead advisor’s follow-up email with
      every question still marked Send, numbered, in his wording, ready to
      paste into Outlook.

Rebuilding keeps the analyst’s decisions and any rewording of a question:
they are read back from the saved workbook by the question's key.

WHERE THE QUESTIONS COME FROM (see _spec/FOLLOWUPS.md, the lead advisor’s five emails)
  accounts not on file      transfers to or from an account with no statements
  new borrowing             a loan landing in a personal account
  loans without details     a loan being paid that no schedule describes
  other income on an LLC    a recurring deposit that is not rent from the
                            practice (Oyler: $2,928.13 from American Pacific)
  one-off movements         large single outflows; CHECK FIRST, often known
  documents still missing   Claude's reading of the checklist
  capacity                  always asked, in the lead advisor’s words
  retirement savings        always last, with the figure the plan uses
"""
import os
import re
import sys
import json
import datetime
import argparse
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SEND, STRIKE, ANSWERED, CHECK = 'Send', 'Strike', 'Answered', 'Check first'


def _money(v):
    return '${:,.0f}'.format(v) if abs(v) >= 100 else '${:,.2f}'.format(v)


def _surname(folder):
    base = os.path.basename(folder.rstrip('/'))
    return base.split(',')[0].strip() if ',' in base else base.split()[0]


def _first(folder):
    base = os.path.basename(folder.rstrip('/'))
    if ',' in base:
        rest = base.split(',', 1)[1].replace('- TEST', '').strip()
        return rest.split()[0] if rest else 'there'
    return 'there'


def _moves(folder):
    import transactions as T
    import cashflow
    g = T.gather(folder)
    sides, banks = T.sides_of(folder), T.banks_of(folder)
    for k in g:
        T.apply_rules(g[k], sides, banks)
    T.match_across(g)
    cashflow._mark_scheduled(folder, g)
    return g, sides


def findings(folder):
    """[(key, question, why, source, priority, default)]"""
    out = []
    try:
        g, sides = _moves(folder)
    except Exception:                                        # noqa: BLE001
        g, sides = {}, {}

    # Accounts not on file ---------------------------------------------------
    unknown = collections.defaultdict(list)
    for (side, key), rows in g.items():
        for r in rows:
            c = re.sub(r'\D', '', str(r.get('counterparty') or ''))
            if len(c) == 4 and c not in sides and r.get('kind') == 'transfer':
                unknown[c].append(r)
    if unknown:
        accts = sorted(unknown)
        why = '; '.join('x%s: %d movement%s, e.g. %s on %s'
                        % (c, len(unknown[c]), '' if len(unknown[c]) == 1 else 's',
                           _money(unknown[c][0]['amount']),
                           unknown[c][0].get('date'))
                        for c in accts)
        out.append(('accounts|' + ','.join(accts),
                    'It appears that there %s %d additional account%s that we '
                    'are missing (based on transfers in/out of accounts). '
                    '%s end%s in %s. Can you provide the last 4 statements for '
                    '%s?' % ('is' if len(accts) == 1 else 'are', len(accts),
                             '' if len(accts) == 1 else 's',
                             'This account' if len(accts) == 1 else 'These accounts',
                             's' if len(accts) == 1 else '',
                             ', '.join('x' + c for c in accts),
                             'it' if len(accts) == 1 else 'each of these accounts'),
                    why, 'bank statements (transfers)', 'High', SEND))

    # New borrowing -----------------------------------------------------------
    for (side, key), rows in g.items():
        for r in rows:
            if r.get('kind') == 'borrowing' and r.get('direction') == 'credit' \
                    and (r.get('amount') or 0) >= 5000:
                desc = ' '.join((r.get('description') or '').split())
                lender = ('Amex' if 'amex' in desc.lower() else
                          'MassMutual policy' if 'mass' in desc.lower() else
                          desc.split()[0].title() if desc else 'a lender')
                month = r['date'].strftime('%B') if r.get('date') else 'recently'
                out.append(('borrow|%s|%s' % (key, r.get('date')),
                            'It looks like there is a new %s loan for %s that was '
                            'taken in %s. Can you tell us the interest rate, term '
                            '(in months/years), and monthly payment for this loan?'
                            % (lender, _money(r['amount']), month),
                            'Credit of %s on x%s, %s: "%s"'
                            % (_money(r['amount']), key, r.get('date'), desc[:70]),
                            'bank statement', 'Normal', SEND))

    # Loans paid with no details ---------------------------------------------
    try:
        import cashflow
        import debt as _debt
        fixed = cashflow._liabilities(folder)
        known = []
        dg = _debt.gather(folder)
        for r in (dg.get('personal') or []) + (dg.get('practice') or []):
            if r.get('payment'):
                known.append(float(r['payment']))
        for payee, monthly, kind in fixed:
            if kind != 'Liability' or any(abs(monthly - k) <= 2 for k in known):
                continue
            low = payee.lower()
            what = ('mortgage' if re.search(r'\bmtge?\b|mortgage|\bmort\b', low)
                    else 'HELOC' if 'heloc' in low else 'loan')
            out.append(('loan|' + payee,
                        'What is the term (months/years), rate, original amount '
                        'and month/year, and current balance of the %s you pay '
                        '%s/month to (%s)?' % (what, _money(monthly), payee.title()),
                        'Paid every month on the bank statements; no statement '
                        'or schedule for it is on file.',
                        'bank statements', 'Normal', SEND))
    except Exception:                                        # noqa: BLE001
        pass

    # Other income on an LLC or building account -----------------------------
    for (side, key), rows in g.items():
        if side != 'Business' or key.isdigit():
            continue
        by = collections.defaultdict(list)
        for r in rows:
            if r.get('direction') == 'credit' and r.get('kind') is None:
                by[round(r.get('amount') or 0, 2)].append(r)
        for amt, hits in by.items():
            if len(hits) >= 3 and amt >= 500:
                desc = ' '.join((hits[0].get('description') or '').split())
                payer = re.sub(r'^(direct-?pay|ach|deposit)\s+', '', desc,
                               flags=re.I).title()[:40]
                out.append(('income|%s|%s' % (key, amt),
                            'We noticed that %s has a monthly deposit of %s from '
                            '"%s". This appears to be income above and beyond the '
                            'dental practice. Can you give us more information '
                            'regarding this payment? If it is a renter, do you '
                            'have a lease you could send us?'
                            % (key, _money(amt), payer),
                            '%d deposits of %s on the %s statements.'
                            % (len(hits), _money(amt), key),
                            'bank statements', 'Normal', SEND))

    # One-off movements: personal accounts only, and only what is big
    # against the account's own month. The practice account pays payroll
    # and suppliers in five figures every week; flagging those produced 25
    # "check first" rows on Oyler. The lead advisor asks about one or two at most.
    for (side, key), rows in g.items():
        if side != 'Personal':
            continue
        debits = [x for x in rows if x.get('direction') == 'debit']
        if not debits:
            continue
        months = max(1, len({(x['date'].year, x['date'].month)
                             for x in debits if x.get('date')}))
        monthly = sum(x.get('amount') or 0 for x in debits) / months
        for r in debits:
            amt = r.get('amount') or 0
            if amt >= 25000 and amt >= 1.5 * monthly and r.get('kind') is None \
                    and not r.get('scheduled'):
                desc = ' '.join((r.get('description') or '').split())
                out.append(('oneoff|%s|%s|%s' % (key, r.get('date'), amt),
                            'We noticed a %s payment on %s ("%s"). Can you tell '
                            'us what this was for, and whether it will recur?'
                            % (_money(amt), r.get('date'), desc[:50]),
                            'A single outflow far above the account\'s usual '
                            'month. Often already known from the calls; strike '
                            'it if so.', 'bank statement', 'Normal', CHECK))

    # Documents still missing, from Claude's reading of the checklist --------
    try:
        with open(os.path.join(folder, '_Audit', 'claude_checklist.json')) as fh:
            verdicts = json.load(fh)
    except (OSError, ValueError):
        verdicts = {}
    seen_words = []

    def _dupe(text):
        # Two checklist items can ask for the same thing ("the 2025 personal
        # return" under both the returns item and the 2025-taxes item).
        w = set(re.findall(r'[a-z0-9]{3,}', text.lower()))
        for o in seen_words:
            if w and len(w & o) / float(len(w | o)) >= 0.3:
                return True
        seen_words.append(w)
        return False

    for item, v in verdicts.items():
        if v.get('verdict') == 'satisfied':
            continue
        for ask in v.get('asks') or ():
            text = (ask.get('text') if isinstance(ask, dict) else str(ask)).strip()
            if not text or _dupe(text):
                continue
            hi = bool(re.search(r'return|decree|credit report|statement',
                                text, re.I))
            out.append(('doc|%s|%s' % (item, text[:40]), text,
                        'Checklist: "%s" read as %s.'
                        % ((v.get('label') or '')[:80], v.get('verdict')),
                        'request checklist', 'High' if hi else 'Normal', SEND))

    # Capacity, always ------------------------------------------------------
    names = []
    try:
        import production as _prod
        for code, r in (_prod.load_roles(folder) or {}).items():
            if r.get('role') == 'associate' and r.get('name'):
                names.append(r['name'].replace('Dr. ', '').split()[0])
    except Exception:                                        # noqa: BLE001
        pass
    who = (' What about %s?' % ' and '.join(names)) if names else ''
    out.append(('capacity',
                'How far are you currently booked out right now at 90%%+ capacity '
                'on the operative side?%s Can you tell us how far hygiene is '
                'booked out at the same 90%%+ capacity? Does the practice have '
                'issues trying to get in perio patients due to the hygiene '
                'schedule fullness? Lastly, how fast is a new patient typically '
                'seen if it\'s not an emergency? These don\'t have to be exact, '
                'just guesstimates.' % who,
                'Asked on every consult: the capacity levers depend on it.',
                'standard', 'Normal', SEND))

    # Retirement savings, always last ----------------------------------------
    saved = None
    try:
        import intake_form as _ic
        f = _ic.find_form_near(folder)
        saved = (_ic.parse(f) or {}).get('saved_last_year') if f else None
    except Exception:                                        # noqa: BLE001
        pass
    out.append(('savings',
                'Lastly from a personal retirement savings standpoint, it appears '
                'that %s. Does this appear correct to you?'
                % ('your savings are "%s" per the intake form; [ADVISOR: state '
                   'the deferrals, matches and contributions the plan uses]'
                   % saved if saved else
                   '[ADVISOR: state what the plan assumes is saved each year]'),
                'The plan\'s current-savings figure; confirmed with the client '
                'every time.', 'standard', 'High', SEND))
    return out


# ------------------------------------------------------------------- workbook
HEADS = ('#', 'Question (edit freely)', 'Why we are asking', 'Source',
         'Priority', 'Decision', 'Key')


def read_back(path):
    """{key: (question, decision, priority)} from a saved workbook."""
    from numbers_parser import Document
    try:
        t = Document(path).sheets[0].tables[0]
    except Exception:                                        # noqa: BLE001
        return {}
    out = {}
    for r in range(4, t.num_rows):
        key = t.cell(r, 6).value
        if key:
            out[str(key)] = (t.cell(r, 1).value, t.cell(r, 5).value,
                             t.cell(r, 4).value)
    return out


def write(folder, outdir=None):
    import cashflow_book as _book
    outdir = outdir or os.path.join(folder, '_Audit')
    name = _surname(folder)
    path = os.path.join(outdir, 'Due diligence - %s.numbers' % name)
    kept = read_back(path) if os.path.exists(path) else {}
    rows = []
    try:
        import review_page as _rp
        page = _rp.decisions(folder)       # the lead advisor’s choices on the review page
    except Exception:                                        # noqa: BLE001
        page = {}
    for key, q, why, src, pri, dec in findings(folder):
        if key in kept:
            q2, d2, p2 = kept[key]
            q, dec, pri = (q2 or q), (d2 or dec), (p2 or pri)
        if key in page:
            d3, t3 = page[key]
            dec, q = (d3 or dec), (t3 or q)
        rows.append([key, q, why, src, pri, dec])
    order = {'High': 0, 'Normal': 1}
    # Documents and accounts first, savings last, as the lead advisor orders them.
    rows.sort(key=lambda r: (r[0] == 'savings', r[0] == 'capacity',
                             order.get(r[4], 1)))

    book = _book.Book(path)
    t = book.table('Due diligence', len(rows) + 6, len(HEADS))
    t.write(0, 0, 'Due diligence: %s' % name, style=book.s_title)
    t.write(2, 0, 'Decide each one: Send (goes in the email), Strike (not '
                  'needed) or Answered (settled from the file). Edit the '
                  'wording freely. Save, then rebuild for the email.',
            style=book.s_note)
    for c, h in enumerate(HEADS):
        t.write(3, c, h, style=book.s_head)
    t.col_width(0, 30)
    t.col_width(1, 420)
    t.col_width(2, 300)
    t.col_width(3, 130)
    t.col_width(4, 70)
    t.col_width(5, 90)
    t.col_width(6, 120)
    for i, (key, q, why, src, pri, dec) in enumerate(rows):
        r = 4 + i
        t.write(r, 0, i + 1)
        t.write(r, 1, q, style=book.s_wrap)
        t.write(r, 2, why, style=book.s_wrap)
        t.write(r, 3, src)
        t.write(r, 4, pri)
        t.write(r, 5, dec, style=book.s_edit)
        t.write(r, 6, key, style=book.s_note)
        t.row_height(r, max(36, 16 * (1 + max(len(q) // 70, len(why) // 50))))
    book.finish()

    email = os.path.join(outdir, 'Follow-up email - %s.txt' % name)
    send = [r for r in rows if (r[5] or '').strip().lower() == 'send']
    hi = [str(i + 1) for i, r in enumerate(send) if r[4] == 'High']
    today = datetime.date.today()
    due = today + datetime.timedelta(days=7)
    lines = ['Hi %s,' % _first(folder), '',
             'Happy %s; our team has been going through all of the information '
             'that you have provided for the consultation with a fine toothed '
             'comb over the past weeks/days.  In doing so, they have developed '
             'some questions/items that they wanted to have me follow up on.  '
             'I’ve cut/paste their questions below:' % today.strftime('%A'),
             '']
    for i, r in enumerate(send, 1):
        lines += ['%d. %s' % (i, r[1]), '']
    lines += ['I think this is all the clarity we have on my end for now; as '
              'you can see, we’ve gone over everything pretty detailed so '
              'far, but still may have a few minor clarifications in the near '
              'future depending on the answers. Please feel free to piecemeal '
              'the information as you get it instead of waiting and sending all '
              'at once (you can either use the portal or just email them to me '
              'directly, whatever is easiest/quickest).  From a priority '
              'standpoint, we’re most concerned about #%s first and '
              'foremost.  Lastly, please email this information by %s, %d/%d, '
              'at 5:00pm EST if not sooner so my team can continue their '
              'research and stay on schedule for the [CONSULT DATE] '
              'consultation.  Additionally, if you think there will be a '
              'problem with getting this back to us by then, please let me know '
              'ASAP.  Thanks in advance and don’t hesitate to reach out if '
              'you have further clarifications.'
              % (', '.join(hi) if hi else '1', due.strftime('%A'), due.month,
                 due.day)]
    with open(email, 'w') as fh:
        fh.write('\n'.join(lines) + '\n')
    checks = sum(1 for r in rows if r[5] == CHECK)
    print('   %d questions drafted: %d to send, %d to check first'
          % (len(rows), len(send), checks))
    return path, email


def main():
    ap = argparse.ArgumentParser(description='Draft the due diligence questions')
    ap.add_argument('folder')
    ap.add_argument('--outdir')
    a = ap.parse_args()
    for p in write(a.folder, a.outdir):
        print('OUTPUT\t%s' % p)


if __name__ == '__main__':
    main()
