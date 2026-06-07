#!/usr/bin/env bash
#
# PreToolUse guard for Edit|Write|MultiEdit.
#
# Blocks any tool call that would modify a PROTECTED / FROZEN path. These paths carry the
# determinism, versioning and audit guarantees that are the architectural backbone of
# TarifHub, so they may change ONLY with explicit human confirmation (and, where relevant,
# a fresh freeze + version bump + pinned-hash update).
#
# Under /ultracode this matters MORE, not less: many parallel agents run at once, and this
# single PreToolUse gate is what stops ANY of them — the orchestrator or a subagent — from
# crossing the freeze line. See AGENTS.md (non-negotiable rules 1, 2, 6) and
# docs/CLAUDE_CODE_SETUP.md.
#
# Protected zones:
#   */versioning/*                          immutable version assignment        (rule 6)
#   */audit/*                               append-only lineage / audit trail   (rule 6)
#   services/intelligence/**/crosswalk/*    the FROZEN TARMED<->TARDOC tables    (rules 1, 2)
#   **/rules_frozen*                        any frozen rule table                (rules 1, 2)
#
# Claude Code passes the tool input as JSON on stdin (tool_input.file_path). Exit code 2
# blocks the tool call and surfaces the stderr message back to the model.

set -euo pipefail

input="$(cat)"

# Best-effort, dependency-free extraction of the target file path.
path="$(printf '%s' "$input" \
  | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
  | head -n1)"

# No path in the payload (e.g. a non-file tool slipped through the matcher): nothing to do.
[ -z "$path" ] && exit 0

block() {
  # $1 = zone label, $2 = zone-specific reason
  echo "BLOCKED: '$path' is in a PROTECTED / FROZEN zone ($1)." >&2
  echo "$2" >&2
  echo "Per the determinism boundary (AGENTS.md rules 1, 2, 6) this changes only with" >&2
  echo "explicit human confirmation — and a re-freeze + version bump where required." >&2
  echo "Drop this path from the edit, or obtain sign-off and bypass the hook deliberately." >&2
  exit 2
}

if printf '%s' "$path" | grep -Eq '(^|/)versioning/'; then
  block "versioning/" "Version assignment is immutable and append-only; it must not be rewritten."
fi

if printf '%s' "$path" | grep -Eq '(^|/)audit/'; then
  block "audit/" "The audit / lineage trail is append-only; it must not be rewritten."
fi

if printf '%s' "$path" | grep -Eq 'services/intelligence/.*crosswalk/'; then
  block "TarifIQ crosswalk" "The TARMED<->TARDOC cross-walk is a FROZEN, content-hashed table; editing it breaks the pinned CROSSWALK_HASH. AI may only *suggest* a mapping pre-freeze (ai_rule_suggest), for a human to validate via POST /v1/validate."
fi

if printf '%s' "$path" | grep -Eq '(^|/)rules_frozen'; then
  block "frozen rules" "Frozen rule tables are authoritative; AI may only *suggest* candidates pre-freeze, never mutate a frozen rule."
fi

exit 0
