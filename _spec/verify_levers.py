#!/usr/bin/env python3
"""Rerun levers.py on the analyst’s Kinsler inputs and check it against his sheet.

    python3 _spec/verify_levers.py

Reads the inputs and the cached results from `initial notes-kinsler.xlsx`
itself, so nothing is typed in here, and prints each lever beside his value.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'fq_auditor'))
import openpyxl                                              # noqa: E402
import levers as L                                           # noqa: E402

BOOK = os.path.join(HERE, 'initial notes-kinsler.xlsx')

# His cell for each lever's dollars on the practice improvements tab.
HIS = {'overhead': 'H18', 'adjustment': 'H19', 'pull_through': 'H20',
       'hygiene': 'H21', 'new_patients': 'H22', 'fees': 'H23',
       'collections': 'H24', 'per_patient': 'H25'}


def main():
    wb = openpyxl.load_workbook(BOOK, data_only=True)
    p, n = wb['practice improvements'], wb['initial notes']
    x = {
        'overhead': p['E17'].value,
        'net_collections': p['E16'].value,
        'adjust_pct': p['E2'].value,
        'net_production': p['E13'].value,
        'gross_production': p['E8'].value,
        'hygiene_share': p['E6'].value,
        'hygiene_days': p['B26'].value,
        'doctor_days': p['B25'].value,
        'hygiene_rooms_free': p['B29'].value == 'Yes',
        'hygiene_booked_6mo': p['B30'].value == 'Yes',
        'doctor_per_hygiene_dollar': p['B40'].value,
        'np_pct': p['E10'].value,
        'np_pct_prior': p['E11'].value,
        'patients': p['E9'].value,
        'net_per_patient_prior': p['E14'].value,
        'net_per_patient': p['E4'].value,
        'fees_off': p['E12'].value,
        'ffs_share': p['E15'].value,
        # His J23: "hold - needs FFS %". The 20% is his assumption.
        'ffs_share_assumed': True,
        'collection_pct': n['M43'].value,
        # His sheet sizes every block at a 50% goal; the module's default
        # moved to 60% for the newer decks, so pass his.
        'target_overhead': 0.50,
    }
    got = L.compute(x)
    bad = 0
    for k, cell in HIS.items():
        his = p[cell].value or 0
        ours = got[k]['value'] or 0
        ok = abs(his - ours) < 0.01
        bad += not ok
        print('%-14s his %12s  ours %12s  %s' % (
            k, '{:,.2f}'.format(his), '{:,.2f}'.format(ours),
            'ok' if ok else 'DIFFERENT'))
    r = L.ranked(got)
    print('top five      his %12s  ours %12s' % (
        '{:,.2f}'.format(p['H26'].value), '{:,.2f}'.format(r['top_subtotal'])))
    print('worst case    his %12s  ours %12s' % (
        '{:,.2f}'.format(p['H27'].value), '{:,.2f}'.format(r['worst_case'])))
    print('\n%s' % ('All levers match.' if not bad else '%d differ.' % bad))


if __name__ == '__main__':
    main()
