#!/usr/bin/env bash
# PreToolUse gate: block AI edits below the freeze line.
# The determinism promise is enforced, not requested. Matching paths require
# Erhan to edit manually (or to consciously lift the guard for one change).
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}" || exit 0

INPUT=$(cat)
FILE=$(echo "$INPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('tool_input', {}).get('file_path', ''))" 2>/dev/null || echo "")

[ -z "$FILE" ] && exit 0

PROTECTED='(services/ingestion/.*/(versioning|audit)/|services/ingestion/(versioning|audit)/|tests/test_(determinism|serving)_boundary\.py)'

if echo "$FILE" | grep -qE "$PROTECTED"; then
  echo "BLOCKED by guard_frozen: '$FILE' is below the freeze line (versioning/, audit/, or a frozen boundary-test basename)." >&2
  echo "If this change is genuinely needed: explain why to Erhan, get his explicit OK in chat, and he edits it or lifts the guard for one commit." >&2
  exit 2
fi

# Applied (existing) migrations are frozen; creating a NEW forward-only NNN_*.sql is allowed.
if echo "$FILE" | grep -qE 'db/migrations/[^/]+\.sql' && [ -f "$FILE" ]; then
  echo "BLOCKED by guard_frozen: '$FILE' is an applied migration; append a new forward-only db/migrations/NNN_*.sql instead." >&2
  echo "If this change is genuinely needed: explain why to Erhan, get his explicit OK in chat, and he edits it or lifts the guard for one commit." >&2
  exit 2
fi
exit 0
