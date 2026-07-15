#!/usr/bin/env bash
# PreToolUse gate: block AI edits below the freeze line.
# The determinism promise is enforced, not requested. Matching paths require
# Erhan to edit manually (or to consciously lift the guard for one change).
# Best-effort defense-in-depth: fires on Edit/Write tool calls only (see AGENTS.md).
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}" || exit 0

INPUT=$(cat)
FILE=$(echo "$INPUT" | python3 -c "
import sys, json, os
p = json.load(sys.stdin).get('tool_input', {}).get('file_path', '')
print(os.path.normpath(p) if p else '')" 2>/dev/null || echo "")

[ -z "$FILE" ] && exit 0

deny() {
  echo "BLOCKED by guard_frozen: '$FILE' $1" >&2
  echo "If this change is genuinely needed: explain why to Erhan, get his explicit OK in chat, and he edits it or lifts the guard for one commit." >&2
  exit 2
}

# Frozen ingestion directories.
if echo "$FILE" | grep -qE '(^|/)services/ingestion/([^/]+/)*(versioning|audit)/'; then
  deny "is below the freeze line (services/ingestion versioning/ or audit/)."
fi

# The two frozen boundary-test basenames, in ANY directory.
if echo "$FILE" | grep -qE '(^|/)test_(determinism|serving)_boundary\.py$'; then
  deny "is a frozen boundary-test basename."
fi

# Applied (existing) migrations are frozen; a NEW migration must be forward-only NNN_*.sql.
if echo "$FILE" | grep -qE '(^|/)db/migrations/[^/]+\.sql$'; then
  if [ -f "$FILE" ]; then
    deny "is an applied migration; append a new forward-only db/migrations/NNN_*.sql instead."
  fi
  if ! basename "$FILE" | grep -qE '^[0-9]{3}_[^/]+\.sql$'; then
    deny "is a new migration with a non-conforming name; use db/migrations/NNN_<description>.sql."
  fi
fi
exit 0
