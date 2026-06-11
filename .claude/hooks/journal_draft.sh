#!/usr/bin/env bash
# SessionEnd: draft a CAS journal entry skeleton for today (idempotent).
# This produces the *raw material* for the rubric's 12-point "AI tools used and
# described" criterion. Claude curates it at session end; Erhan owns the final text.
set -uo pipefail

DIR="vault/daily"
mkdir -p "$DIR"
TODAY=$(date +%F)
FILE="$DIR/$TODAY.md"

if [ ! -f "$FILE" ]; then
  cat > "$FILE" <<EOF
# $TODAY — AI workflow journal

> Draft created by SessionEnd hook — CURATE before counting it as evidence.
> 3–6 honest lines. Contemporaneous or worthless.

- Delegated:
- AI got wrong → caught by:
- One concrete prompt → diff example:
- Decision made (→ ADR?):

↩ [[00-index]] · [[fazit-notes]]
EOF
fi

# Append session marker with git state for traceability
{
  echo ""
  echo "<!-- session ended $(date '+%H:%M') · branch: $(git branch --show-current 2>/dev/null || echo n/a) · last commit: $(git log -1 --oneline 2>/dev/null || echo none) -->"
} >> "$FILE"
exit 0
