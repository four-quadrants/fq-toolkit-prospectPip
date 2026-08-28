#!/bin/bash
# Right-click this and choose Open to put the FQ Toolkit on your Mac, or to
# update it later. (macOS blocks a plain double-click on anything that arrived
# from somewhere else — right-click, Open, then Open again.)
#
# It copies the toolkit to your Desktop, keeping any settings you already had.
# It never touches client documents: those stay on the Analysis share where
# they belong. Run it from inside the folder the zip unpacks to.

HERE="$(cd "$(dirname "$0")" && pwd)"
for d in /opt/homebrew/bin /usr/local/bin; do [ -d "$d" ] && export PATH="$d:$PATH"; done
clear
echo "Four Quadrants — FQ Toolkit"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
    echo "  Python 3 is not installed on this Mac yet."
    echo ""
    echo "  Open fq_auditor/SETUP.md in this folder and follow step 1,"
    echo "  then run this again."
    echo ""
    read -r -p "Press return to close. "
    exit 1
fi

# Installing FROM the share copy: this script ships inside it, so the folder it
# sits in is the source.
python3 "$HERE/fq_auditor/deploy.py" install --from "$HERE"
STATUS=$?
echo ""
[ $STATUS -eq 0 ] && open ~/Desktop/FQ_Toolkit 2>/dev/null
read -r -p "Press return to close this window. "
