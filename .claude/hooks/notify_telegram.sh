#!/usr/bin/env bash
# Notification + Stop hook: push a Telegram message when the loop wants attention or finishes.
# Pure-additive and safe: a no-op if TG_BOT_TOKEN / TG_CHAT_ID are unset, never blocks, never
# fails the session (always exits 0). This is the "phase 1" notifications-only layer and can be
# enabled independently of the approval gate.
set -uo pipefail
: "${TG_BOT_TOKEN:=}"; : "${TG_CHAT_ID:=}"
[ -z "$TG_BOT_TOKEN" ] || [ -z "$TG_CHAT_ID" ] && exit 0

IN=$(cat 2>/dev/null || echo "{}")
evt=$(jq -r '.hook_event_name // "event"' <<<"$IN" 2>/dev/null)
msg=$(jq -r '.message // ""' <<<"$IN" 2>/dev/null)
[ -z "$msg" ] && msg="$evt"
proj=$(basename "${CLAUDE_PROJECT_DIR:-$(pwd)}")

curl -s --max-time 8 "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${TG_CHAT_ID}" \
  --data-urlencode "text=[${proj}] ${evt}: ${msg}" >/dev/null 2>&1 || true
exit 0
