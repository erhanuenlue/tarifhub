#!/usr/bin/env bash
# PreToolUse policy gate for the approval bridge.
# SAFETY: a hard no-op unless APPROVALS_ON=1 is exported. With approvals off (the default,
# and how the unattended loop runs) it allows every tool instantly, so committing and
# registering this hook cannot change the loop's behavior or introduce a halt. Turn it on
# only when you want human-in-the-loop approval, and run the loop in the default permission
# mode so the decision is authoritative (see NEXT_STEPS).
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"
Q="$ROOT/.shipboard/approvals"

allow(){ echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'; exit 0; }
deny(){  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$1"; exit 0; }

# OFF by default: instant allow, zero behavior change.
[ "${APPROVALS_ON:-0}" = "1" ] || allow

mkdir -p "$Q/pending" "$Q/decided"
IN=$(cat); tool=$(jq -r '.tool_name' <<<"$IN" 2>/dev/null || echo "")
cmd=$(jq -r '.tool_input.command // ""' <<<"$IN" 2>/dev/null || echo "")

# Sensitivity policy. Tune freely. The freeze line is already hard-blocked by guard_frozen.sh,
# so this only governs side-effectful actions, not the protected billing code.
sensitive=0; risk="action"
case "$tool" in
  Bash)
    case "$cmd" in
      *"git push"*main*|*"gh pr merge"*|*"git merge "*)      sensitive=1; risk="merge-to-main";;
      *"git reset --hard"*|*"git clean -"*|*"git push --force"*|*"rm -rf "*) sensitive=1; risk="destructive-git";;
      *"gh repo edit"*visibility*|*DEPLOY_PAGES*|*"gh release"*) sensitive=1; risk="publish";;
    esac;;
esac
[ "$sensitive" = 0 ] && allow

id="$(date -u +%Y-%m-%dT%H-%M-%S)_$$_$RANDOM"
sid=$(jq -r '.session_id // ""' <<<"$IN" 2>/dev/null)
sum=$(printf '%s: %s' "$tool" "${cmd:0:140}")
jq -n --arg id "$id" --arg ts "$(date -u +%FT%TZ)" --arg sid "$sid" --arg tn "$tool" \
   --arg sum "$sum" --arg risk "$risk" --argjson ti "$(jq '.tool_input' <<<"$IN" 2>/dev/null || echo '{}')" \
   '{id:$id,ts:$ts,session_id:$sid,tool_name:$tn,summary:$sum,risk:$risk,tool_input:$ti,status:"pending"}' \
   > "$Q/pending/$id.json" 2>/dev/null
printf '{"ts":"%s","event":"requested","id":"%s","risk":"%s","summary":%s}\n' \
   "$(date -u +%FT%TZ)" "$id" "$risk" "$(jq -Rn --arg s "$sum" '$s')" >> "$Q/log.jsonl" 2>/dev/null

# Sleep-poll for a decision, under the 600s hook timeout. Deny-safe at ~9 minutes.
for _ in $(seq 1 270); do
  if [ -f "$Q/decided/$id.json" ]; then
    d=$(jq -r '.decision' "$Q/decided/$id.json" 2>/dev/null)
    via=$(jq -r '.via // "?"' "$Q/decided/$id.json" 2>/dev/null)
    mv -f "$Q/pending/$id.json" "$Q/pending/.$id.done" 2>/dev/null || true
    printf '{"ts":"%s","event":"%s","id":"%s","via":"%s"}\n' "$(date -u +%FT%TZ)" "$d" "$id" "$via" >> "$Q/log.jsonl" 2>/dev/null
    [ "$d" = "allow" ] && allow || deny "denied via $via"
  fi
  sleep 2
done
printf '{"ts":"%s","event":"timeout","id":"%s"}\n' "$(date -u +%FT%TZ)" "$id" >> "$Q/log.jsonl" 2>/dev/null
deny "approval timeout (no decision within 9 minutes), fail-safe"
