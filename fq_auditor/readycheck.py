#!/usr/bin/env python3
"""Is this workspace ready to run the pipeline?

    python3 readycheck.py ["<Prospects folder>"]

Run by Claude when someone says "check the FQ toolkit is ready" on a new Mac.
It checks the libraries the code imports and the command-line tools it calls,
and that the Prospects folder can be found. Whatever is missing is printed
with the one command that installs it, so Claude can install it there and then.
"""
import importlib
import os
import shutil
import sys

# (import name, pip package, what it is for)
LIBS = [
    ('openpyxl', 'openpyxl', 'the initial notes workbook'),
    ('pptx', 'python-pptx', 'the consult deck'),
    ('fitz', 'pymupdf', 'reading PDFs'),
    ('pytesseract', 'pytesseract', 'reading scanned pages'),
    ('PIL', 'pillow', 'page images'),
    ('docx', 'python-docx', 'Word reports'),
    ('numbers_parser', 'numbers-parser', 'the cash flow .numbers file'),
    ('reportlab', 'reportlab', 'PDFs on request'),
]
TOOLS = [
    ('pdftotext', 'poppler-utils', 'PDF text'),
    ('pdftoppm', 'poppler-utils', 'PDF pages as pictures'),
    ('tesseract', 'tesseract-ocr', 'scanned pages'),
]


def main():
    missing_pip, missing_tools = [], []
    print('Libraries:')
    for mod, pkg, why in LIBS:
        try:
            importlib.import_module(mod)
            print('  ok       %-15s %s' % (pkg, why))
        except Exception:                                    # noqa: BLE001
            print('  MISSING  %-15s %s' % (pkg, why))
            missing_pip.append(pkg)
    print('Tools:')
    for cmd, pkg, why in TOOLS:
        if shutil.which(cmd):
            print('  ok       %-15s %s' % (cmd, why))
        else:
            print('  MISSING  %-15s %s' % (cmd, why))
            if pkg not in missing_tools:
                missing_tools.append(pkg)
    here = os.path.dirname(os.path.abspath(__file__))
    print('Toolkit:   %s' % here)
    if len(sys.argv) > 1:
        p = sys.argv[1]
        print('Prospects: %s (%s)' % (p, 'found' if os.path.isdir(p) else 'NOT FOUND'))
    if missing_pip:
        print('\nInstall: pip install --break-system-packages %s'
              % ' '.join(sorted(set(missing_pip))))
    if missing_tools:
        print('Install: apt-get install -y %s' % ' '.join(missing_tools))
    if not (missing_pip or missing_tools):
        print('\nReady.')


if __name__ == '__main__':
    main()
