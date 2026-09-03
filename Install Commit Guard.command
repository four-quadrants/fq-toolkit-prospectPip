#!/bin/bash
# Installs the pre-commit guard into this clone. Run once per machine.
#
# Git hooks live in .git/hooks, which is not version controlled, so a fresh
# clone starts without one. This puts it back.

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/.git/hooks/pre-commit"
mkdir -p "$HERE/.git/hooks"
cat > "$HOOK" <<'HOOKEOF'
#!/bin/sh
# Refuses a commit carrying real client data. See fq_auditor/precommit_check.py.
exec python3 "$(git rev-parse --show-toplevel)/fq_auditor/precommit_check.py"
HOOKEOF
chmod +x "$HOOK"
echo "Commit guard installed."
echo "Test it:  python3 fq_auditor/precommit_check.py"
echo ""
read -r -p "Press return to close. "
