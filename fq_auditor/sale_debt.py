"""The practice and building debt still owed when the practice sells.

The sale at retirement is worked out net of what is still owed on the
practice and the building then (the lead advisor's worksheet: 70% of the
practice and building, less the building loan). Each loan is run forward
month by month from today's balance with its payment and rate:

  - the rate from the reading, else one written in its description
    ("about 8%", "rate column reads 5.74"), else ASSUMED_RATE, said so;
  - the payment from the reading, else, for building notes, the monthly
    amounts written in a building note's description, shared across the
    building notes by balance;
  - "N left" / "N payments left" in a description caps the months;
  - a loan with no payment at all is carried at today's balance, said so.

Personal debt never comes off the sale. Everything here is a starting
figure: the lead advisor can type the debt at sale on the review page.

    python3 sale_debt.py "<client folder>" [years]
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ASSUMED_RATE = 0.05


def _rate_in(text):
    t = str(text or '')
    m = re.search(r'(\d{1,2}(?:\.\d+)?)\s*%', t) or \
        re.search(r'rate[^.]*?(\d{1,2}\.\d+)', t, re.I)
    if m:
        v = float(m.group(1))
        if 0 < v < 25:
            return v / 100.0
    return None


def _left_in(text):
    m = re.search(r'(\d{1,3})\s+(?:payments\s+)?left', str(text or ''), re.I)
    return int(m.group(1)) if m else None


def loans(folder):
    """Practice and building loans as [{label, side, balance, payment, rate,
    rate_assumed, months_left}] from the verified readings."""
    try:
        import doc_readings as _dr
        d = (_dr.check(folder)[0] or {}).get('debts') or {}
    except Exception:                                        # noqa: BLE001
        d = {}
    if not d:
        try:
            import debt as _debt
            g = _debt.gather(folder)
            d = {'practice': g.get('practice') or []}
        except Exception:                                    # noqa: BLE001
            d = {}
    out = []
    for side in ('practice', 'building'):
        for r in d.get(side) or ():
            bal = r.get('balance')
            if not bal:
                continue
            desc = ' '.join(str(r.get(k) or '') for k in ('what', 'description'))
            rate = r.get('rate') or _rate_in(desc)
            out.append({'label': ('%s %s' % (r.get('creditor') or '', r.get('what') or '')).strip(),
                        'side': side, 'balance': float(bal),
                        'payment': float(r['payment']) if r.get('payment') else None,
                        'rate': rate if rate else ASSUMED_RATE,
                        'rate_assumed': not rate,
                        'months_left': _left_in(desc), 'desc': desc})
    # Building notes with no payment: the payments written in any building
    # note's description ("paid $2,100.00 and $900.00 a month"), shared by
    # balance across the notes that have none.
    bld = [x for x in out if x['side'] == 'building']
    if bld and any(x['payment'] is None for x in bld):
        pays = []
        for x in bld:
            if re.search(r'a month|/mo', x['desc']):
                pays += [float(v.replace(',', '')) for v in
                         re.findall(r'\$([\d,]+\.\d{2})', x['desc'])]
        known = sum(x['payment'] for x in bld if x['payment'])
        spare = sum(pays) - known
        missing = [x for x in bld if x['payment'] is None]
        tot = sum(x['balance'] for x in missing)
        if spare > 0 and tot:
            for x in missing:
                x['payment'] = spare * x['balance'] / tot
                x['payment_shared'] = True
    return out


def balance_after(loan, months):
    b, p, r = loan['balance'], loan['payment'], loan['rate'] / 12.0
    if not p:
        return b
    if loan.get('months_left') is not None and months >= loan['months_left']:
        return 0.0
    for _ in range(int(months)):
        b = b * (1 + r) - p
        if b <= 0:
            return 0.0
    return b


def at_sale(folder, years):
    """(total still owed after `years`, [items with basis])."""
    items, total = [], 0.0
    for x in loans(folder):
        left = balance_after(x, max(0, years) * 12)
        bits = []
        if x['payment'] is None:
            bits.append('no payment on file, carried at today’s balance')
        elif x.get('payment_shared'):
            bits.append('payment shared from the building notes, $%s a month' % '{:,.0f}'.format(x['payment']))
        if x['rate_assumed'] and x['payment']:
            bits.append('rate not on file, %.0f%% assumed' % (ASSUMED_RATE * 100))
        items.append({'label': x['label'], 'side': x['side'],
                      'today': round(x['balance']), 'at_sale': round(left),
                      'basis': '; '.join(bits)})
        total += left
    return round(total), items


if __name__ == '__main__':
    yrs = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    t, it = at_sale(sys.argv[1], yrs)
    print(json.dumps(it, indent=1))
    print('owed at sale after %d years: $%s' % (yrs, '{:,.0f}'.format(t)))
