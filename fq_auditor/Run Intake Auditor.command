#!/bin/bash
# FQ Intake Auditor — double-click launcher.
#
# Designed so nobody has to type a command or remember a flag. Everything the
# tool needs, it looks for; anything it has been told once, it remembers.
#
# If double-clicking does nothing, right-click this file and choose Open.

cd "$(dirname "$0")" || exit 1

B=$'\033[1m'; P=$'\033[0m'; R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; D=$'\033[2m'

say()  { echo "$@"; }
step() { echo ""; echo "${B}$1${P}"; }
ok()   { echo "${G}$1${P}"; }
warn() { echo "${Y}$1${P}"; }
die()  { echo "${R}$1${P}"; echo ""; read -r -p "Press return to close. "; exit 1; }

clear
say "${B}Four Quadrants — Document Intake Auditor${P}"
say "${D}Reads a client's documents, checks them against the checklist,${P}"
say "${D}and works out where each one should be filed.${P}"
say "${D}Everything happens on this Mac. Nothing is uploaded.${P}"
say "------------------------------------------------------------"

# ---------------------------------------------------------------- prerequisites
command -v python3 >/dev/null 2>&1 || die "Python 3 isn't installed. Open SETUP.md — it walks through the one-time install."

if ! command -v tesseract >/dev/null 2>&1; then
    for d in /opt/homebrew/bin /usr/local/bin; do
        [ -x "$d/tesseract" ] && export PATH="$d:$PATH"
    done
fi
if ! command -v tesseract >/dev/null 2>&1; then
    say ""
    warn "The text reader (tesseract) isn't installed."
    say "It's a one-time install. Shall I do it now? (needs Homebrew)"
    read -r -p "  Install tesseract? [y/n] " yn
    case "$yn" in
        y|Y|yes|YES)
            command -v brew >/dev/null 2>&1 || die "Homebrew isn't installed either. Open SETUP.md for the install steps."
            brew install tesseract || die "That didn't work. Open SETUP.md for the manual steps."
            ;;
        *) die "Can't read scanned documents without it. Open SETUP.md when you're ready." ;;
    esac
fi

python3 - <<'PYCHECK' >/dev/null 2>&1
import pymupdf, pytesseract, docx, PIL
PYCHECK
if [ $? -ne 0 ]; then
    say ""
    say "Installing the Python pieces (one time only, about a minute)…"
    python3 -m pip install --quiet --break-system-packages \
        pymupdf pytesseract pillow python-docx openpyxl >/dev/null 2>&1 \
      || python3 -m pip install --quiet --user pymupdf pytesseract pillow python-docx openpyxl \
      || die "Couldn't install the Python packages. Open SETUP.md."
    ok "Done."
fi

# ---------------------------------------------------------------- the folder
step "Which client?"
say "Drag the client's folder into this window and press return."
read -r -p "  Folder: " FOLDER
FOLDER="${FOLDER%\'}"; FOLDER="${FOLDER#\'}"; FOLDER="$(echo "$FOLDER" | xargs)"
[ -d "$FOLDER" ] || die "That isn't a folder."

SETTINGS="$FOLDER/.fq_settings"
CLIENT=""; GREETING=""; CHECKLIST=""
# Anything we were told last time for this client, we reuse without asking again.
[ -f "$SETTINGS" ] && . "$SETTINGS"

# ---------------------------------------------------------------- the checklist
if [ -z "$CHECKLIST" ] || [ ! -f "$CHECKLIST" ]; then
    FOUND="$(find "$FOLDER" "$FOLDER/.." -maxdepth 1 -iname '*checklist*.pdf' 2>/dev/null | head -1)"
    if [ -n "$FOUND" ]; then
        CHECKLIST="$FOUND"
        say ""
        ok "Found the checklist: $(basename "$CHECKLIST")"
    else
        step "Where's the checklist?"
        say "Drag the checklist PDF in, or press return to use the standard one."
        read -r -p "  Checklist: " CHECKLIST
        CHECKLIST="${CHECKLIST%\'}"; CHECKLIST="${CHECKLIST#\'}"; CHECKLIST="$(echo "$CHECKLIST" | xargs)"
    fi
fi

# ---------------------------------------------------------------- who they are
if [ -z "$CLIENT" ]; then
    step "Who is this?"
    read -r -p "  Client surname (e.g. Bassett): " CLIENT
    read -r -p "  How should the email greet them? (e.g. Dr. and Mrs. Bassett): " GREETING
fi
CLIENT="${CLIENT:-the client}"

cat > "$SETTINGS" <<EOF
CLIENT="$CLIENT"
GREETING="$GREETING"
CHECKLIST="$CHECKLIST"
EOF

# ---------------------------------------------------------------- what we found
OUTDIR="$FOLDER/_Audit"
CACHE="$FOLDER/.fq_cache"
mkdir -p "$OUTDIR"

# Decisions exported from a previous review page. Looked for in the client folder
# first, then Downloads, because that is where a browser puts it.
DECISIONS=""
for c in "$FOLDER/decisions.json" "$OUTDIR/decisions.json" "$HOME/Downloads/decisions.json"; do
    [ -f "$c" ] && { DECISIONS="$c"; break; }
done

# The redacted batch, used for preview images in the review page.
REDACTED="$(find "$FOLDER" "$FOLDER/.." -maxdepth 1 -type d -iname 'redacted-batch*' 2>/dev/null | head -1)"

step "Ready"
say "  Client     : $CLIENT"
say "  Documents  : $FOLDER"
[ -n "$CHECKLIST" ] && say "  Checklist  : $(basename "$CHECKLIST")" || say "  Checklist  : the standard one"
[ -n "$DECISIONS" ] && ok "  Decisions  : found from your last review — they'll be applied"
[ -n "$REDACTED" ]  && say "  Previews   : $(basename "$REDACTED")"
say "  Results go : $FOLDER/_Audit"
say ""
say "${D}First run on a new client reads every page and takes a few minutes.${P}"
say "${D}After that it's quick, because the reading is remembered.${P}"
read -r -p "Press return to start (or Ctrl+C to stop). "

# ---------------------------------------------------------------- run
ARGS=("$FOLDER" --client "$CLIENT" --outdir "$OUTDIR" --cache "$CACHE")
[ -n "$CHECKLIST" ] && ARGS+=(--checklist "$CHECKLIST")
[ -n "$GREETING" ]  && ARGS+=(--greeting "$GREETING")
[ -n "$DECISIONS" ] && ARGS+=(--decisions "$DECISIONS")
[ -n "$REDACTED" ]  && ARGS+=(--redacted-dir "$REDACTED")

echo ""
python3 audit.py "${ARGS[@]}"
STATUS=$?
echo ""

if [ $STATUS -ne 0 ]; then
    warn "Something went wrong. The message above says what."
    say "If it mentions a missing module or tesseract, open SETUP.md."
    read -r -p "Press return to close. "; exit 1
fi

# ---------------------------------------------------------------- what next
ok "Done."
say ""
say "${B}What to do now${P}"
say "  1. The review page just opened. Work down the 'Needs a filing decision'"
say "     list — each one has a preview so you can see what it is."
say "  2. When you've chosen, click ${B}Download decisions${P} at the top."
say "  3. Run this launcher again. It finds that file by itself and applies"
say "     your choices — you don't have to type anything."
say ""
say "  The other files in _Audit:"
say "    Intake Review.html        the page you're about to look at"
say "    Needs Clarification.docx  what to chase, in plain English"
say "    Client Email.txt          a draft asking for what's missing"
say "    Rename Log.csv            every rename, and what it used to be called"
say ""

open "$OUTDIR"/*"Intake Review.html" 2>/dev/null
read -r -p "Press return to close this window. "
