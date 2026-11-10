#!/usr/bin/env python3
"""Install the deck's fonts (Barlow, Barlow Condensed) in a Claude workspace,
so a deck rendered there to check a change looks as it will in Keynote.
Without them LibreOffice substitutes a wider font and headings wrap that will
not wrap on a Mac.

    python3 fq_auditor/preview_fonts.py

Fetches the open-source fonts from npm (@fontsource), converts them to TTF
in ~/.fonts and refreshes the font cache. Safe to run again.
"""
import glob
import os
import subprocess
import tarfile
import tempfile


def main():
    out = os.path.expanduser('~/.fonts')
    os.makedirs(out, exist_ok=True)
    if len(glob.glob(os.path.join(out, 'Barlow*.ttf'))) >= 8:
        print('Barlow fonts already installed.')
        return
    subprocess.run(['pip', 'install', '-q', 'fonttools', 'brotli', '--break-system-packages'],
                   check=False)
    from fontTools.ttLib import TTFont
    tmp = tempfile.mkdtemp()
    for pkg in ('@fontsource/barlow', '@fontsource/barlow-condensed'):
        subprocess.run(['npm', 'pack', pkg], cwd=tmp, check=True, capture_output=True)
    for tgz in glob.glob(os.path.join(tmp, '*.tgz')):
        with tarfile.open(tgz) as t:
            t.extractall(os.path.join(tmp, os.path.basename(tgz) + '_x'))
    for fam, key in (('Barlow', 'fontsource-barlow-5'), ('Barlow Condensed', 'fontsource-barlow-condensed')):
        base = [d for d in glob.glob(os.path.join(tmp, '*.tgz')) if os.path.basename(d).startswith(key)]
        if not base:
            continue
        files = os.path.join(tmp, os.path.basename(base[0]) + '_x', 'package', 'files')
        for w, sub in ((400, 'Regular'), (500, 'Medium'), (600, 'SemiBold'), (700, 'Bold')):
            hits = [f for f in glob.glob(os.path.join(files, '*-latin-%d-normal.woff' % w))
                    if 'latin-ext' not in f]
            if not hits:
                continue
            font = TTFont(hits[0])
            font.flavor = None
            for rec in font['name'].names:
                if rec.nameID == 1:
                    rec.string = fam if w in (400, 700) else '%s %s' % (fam, sub)
                if rec.nameID == 2:
                    rec.string = 'Bold' if w == 700 else 'Regular'
            font.save(os.path.join(out, '%s-%s.ttf' % (fam.replace(' ', ''), sub)))
    subprocess.run(['fc-cache', '-f'], check=False)
    print('Installed %d Barlow fonts in %s' % (len(glob.glob(os.path.join(out, 'Barlow*.ttf'))), out))


if __name__ == '__main__':
    main()
