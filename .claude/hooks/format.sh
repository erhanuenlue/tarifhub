#!/usr/bin/env bash
# PostToolUse: format the file that was just edited. Quiet on success, never blocks.
set -uo pipefail

INPUT=$(cat)
FILE=$(echo "$INPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('tool_input', {}).get('file_path', ''))" 2>/dev/null || echo "")

[ -z "$FILE" ] || [ ! -f "$FILE" ] && exit 0

case "$FILE" in
  *.py)
    command -v uv >/dev/null && { uv run ruff format -q "$FILE" 2>/dev/null; uv run ruff check -q --fix "$FILE" 2>/dev/null; } ;;
  *.ts|*.tsx|*.js|*.jsx|*.css)
    [ -f apps/tarifguard-demo/node_modules/.bin/prettier ] && apps/tarifguard-demo/node_modules/.bin/prettier --write --log-level silent "$FILE" 2>/dev/null ;;
esac
exit 0
