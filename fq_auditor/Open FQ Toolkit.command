#!/bin/bash
# FQ Toolkit — double-click to open. Both tools, one window.
#
# Starts the local app and opens it in your browser. Leave this Terminal window
# open while you work; closing it shuts the app down.

cd "$(dirname "$0")" || exit 1
B=$'\033[1m'; P=$'\033[0m'; R=$'\033[31m'; Y=$'\033[33m'

clear
echo "${B}Four Quadrants — FQ Toolkit${P}"
echo "Starting…"
echo ""

command -v python3 >/dev/null 2>&1 || {
    echo "${R}Python 3 isn't installed.${P} Open SETUP.md for the one-time install."
    read -r -p "Press return to close. "; exit 1; }

# tesseract lives in one of the Homebrew locations depending on the Mac
if ! command -v tesseract >/dev/null 2>&1; then
    for d in /opt/homebrew/bin /usr/local/bin; do
        [ -x "$d/tesseract" ] && export PATH="$d:$PATH"
    done
fi
if ! command -v tesseract >/dev/null 2>&1; then
    echo "${Y}The text reader (tesseract) isn't installed.${P}"
    read -r -p "Install it now? [y/n] " yn
    case "$yn" in
        y|Y|yes|YES)
            command -v brew >/dev/null 2>&1 || {
                echo "${R}Homebrew isn't installed.${P} Open SETUP.md."
                read -r -p "Press return to close. "; exit 1; }
            brew install tesseract || { read -r -p "Press return to close. "; exit 1; } ;;
        *) echo "Scanned documents can't be read without it." ;;
    esac
fi

python3 - <<'PYCHECK' >/dev/null 2>&1
import pymupdf, pytesseract, docx, PIL
PYCHECK
if [ $? -ne 0 ]; then
    echo "Installing the Python pieces (one time only, about a minute)…"
    python3 -m pip install --quiet --break-system-packages \
        pymupdf pytesseract pillow python-docx openpyxl >/dev/null 2>&1 \
      || python3 -m pip install --quiet --user pymupdf pytesseract pillow python-docx openpyxl \
      || { echo "${R}Couldn't install the Python packages.${P} Open SETUP.md."
           read -r -p "Press return to close. "; exit 1; }
    echo "Done."
fi

python3 fq_app.py
echo ""
read -r -p "Press return to close this window. "
