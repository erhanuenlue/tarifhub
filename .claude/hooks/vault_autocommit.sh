#!/usr/bin/env bash
# SessionEnd: auto-commit + push the contemporaneous evidence trail so journal/index/
# fazit never sit uncommitted (owner decision 2026-06-11: zero-friction evidence).
# SCOPE IS HARD-LIMITED to vault/ and LEARNINGS.md — code NEVER travels through this
# hook; it belongs to the /ship pipeline. Quiet, idempotent, never blocks.
set -uo pipefail

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
# never act mid-merge/rebase
if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ] || [ -f .git/MERGE_HEAD ]; then
  exit 0
fi

git add -- vault 2>/dev/null
git add -- LEARNINGS.md 2>/dev/null
git diff --cached --quiet && exit 0

# paranoia: if anything outside the allowed scope is staged, back off entirely
if git diff --cached --name-only | grep -qvE '^(vault/|LEARNINGS\.md$)'; then
  git reset -q
  exit 0
fi

git commit -q -m "chore(vault): journal + index (auto, session end) [skip ci]" || exit 0
git push -q >/dev/null 2>&1 || true   # offline is fine; next push carries it
exit 0
