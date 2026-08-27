#!/bin/bash
# Double-click this to start the FQ Toolkit.
#
# It sits at the top of the repo rather than down beside the code, so it is easy
# to find AND gets backed up with everything else. The real launcher — the one
# that checks Python and tesseract are installed — lives next to the code; this
# just finds it and runs it, so there is only ever one of those to maintain.
#
# For one-click access, drag this to the Dock rather than moving it: moving it
# out of the repo takes it out of the backup, which is how the previous copy
# ended up living only on one Mac.
#
# Leave the Terminal window it opens alone while you work — closing it stops
# the app.

HERE="$(cd "$(dirname "$0")" && pwd)"
REAL="$HERE/fq_auditor/Open FQ Toolkit.command"

if [ ! -f "$REAL" ]; then
    echo "Can't find the app."
    echo "Expected it at: $REAL"
    echo ""
    echo "If you moved or renamed the folder, tell Claude and it will re-point this."
    read -r -p "Press return to close. "
    exit 1
fi

exec "$REAL"
