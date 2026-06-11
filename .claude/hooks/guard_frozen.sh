#!/usr/bin/env bash
# PreToolUse gate: block AI edits below the freeze line.
# The determinism promise is enforced, not requested. Matching paths require
# Erhan to edit manually (or to consciously lift the guard for one change).
set -euo pipefail

INPUT=$(cat)
FILE=$(echo "$INPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('tool_input', {}).get('file_path', ''))" 2>/dev/null || echo "")

[ -z "$FILE" ] && exit 0

PROTECTED='(services/ingestion/.*/(versioning|audit)/|services/ingestion/(versioning|audit)/|db/migrations/applied/|tests/test_determinism_boundary\.py)'

if echo "$FILE" | grep -qE "$PROTECTED"; then
  echo "BLOCKED by guard_frozen: '$FILE' is below the freeze line (versioning/, audit/, applied migrations, or the boundary test itself)." >&2
  echo "If this change is genuinely needed: explain why to Erhan, get his explicit OK in chat, and he edits it or lifts the guard for one commit." >&2
  exit 2
fi
exit 0
