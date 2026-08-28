#!/bin/bash
# Double-click this FIRST on a new Mac.
#
# It installs nothing and touches no client files. It looks at what this machine
# has and prints, in plain English, anything that would stop the toolkit running
# — along with the exact command that fixes each one.
#
# Safe to run any time. If something stops working later, run this before
# anything else: it rules out the boring causes in about two seconds.

HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/fq_auditor/preflight.py"

if [ ! -f "$CHECK" ]; then
    echo "Can't find the checker at:"
    echo "  $CHECK"
    echo ""
    echo "The folder may have been moved or only partly copied."
    read -r -p "Press return to close. "
    exit 1
fi

# Homebrew installs to different places on Intel and Apple Silicon, and a
# double-clicked script does not get the PATH a Terminal window would.
for d in /opt/homebrew/bin /usr/local/bin; do
    [ -d "$d" ] && export PATH="$d:$PATH"
done

if ! command -v python3 >/dev/null 2>&1; then
    echo ""
    echo "  Python 3 is not installed on this Mac."
    echo ""
    echo "  That is the first thing to fix, and the checker itself needs it."
    echo "  Open SETUP.md in the fq_auditor folder and follow step 1."
    echo ""
    read -r -p "Press return to close. "
    exit 1
fi

python3 "$CHECK"
STATUS=$?

echo ""
if [ $STATUS -eq 0 ]; then
    echo "You can now double-click 'Start FQ Toolkit.command'."
else
    echo "Fix the items marked STOP above, then run this check again."
fi
echo ""
read -r -p "Press return to close this window. "
