#!/bin/bash
# Maintainer only. Builds the zip to send to someone who needs the toolkit.
#
# Code only — never client documents. Writes the zip to your Desktop, ready to
# drag into an email or AirDrop. Run it after you have committed and pushed, so
# the zip and GitHub agree.
#
# This file is deliberately NOT included in the zip: the person you send it to
# gets Install, Check and Start, but no way to package and pass it on again.

HERE="$(cd "$(dirname "$0")" && pwd)"
for d in /opt/homebrew/bin /usr/local/bin; do [ -d "$d" ] && export PATH="$d:$PATH"; done
clear
echo "Building the FQ Toolkit handover zip…"
python3 "$HERE/fq_auditor/deploy.py" package
echo ""
read -r -p "Press return to close this window. "
