#!/usr/bin/env bash
# switch_model.sh · one-command switch of the main Claude Code model.
#
#   bash tools/switch_model.sh opus     # Opus 5.5 (claude-opus-5-5): the committed pin
#   bash tools/switch_model.sh fable    # Fable 5.1 (claude-fable-5-1)
#
# Single source of truth: the "model" key in .claude/settings.json. Every agent in
# .claude/agents/ declares model: inherit, so subagents follow this key; no other file pins
# a model. Keep the "opus" target equal to the committed pin: a stale target here silently
# moves the repo back to an older model (this script used to write claude-opus-4-8).
# The historical tools/loop.sh reads the same key.

set -u
cd "$(git rev-parse --show-toplevel 2>/dev/null || dirname "$0")/." || exit 1

case "${1:-}" in
    opus)  M="claude-opus-5-5" ;;
    fable) M="claude-fable-5-1" ;;
    *) echo "usage: bash tools/switch_model.sh opus|fable"; exit 1 ;;
esac

python3 - "$M" <<'PY'
import json, sys, collections
m = sys.argv[1]
p = ".claude/settings.json"
d = json.load(open(p), object_pairs_hook=collections.OrderedDict)
old = d.get("model", "(none)")
d["model"] = m
json.dump(d, open(p, "w"), indent=2)
open(p, "a").write("\n")
print(f"main model: {old} -> {m}")
PY

echo
echo "Done. Verify:"
echo "  1. open a new session in this repo:  claude  ->  /status must show: $M"
echo "  2. review the change: git diff .claude/settings.json (commit only when Erhan asks)"
echo
echo "Subagents inherit $M at effort max (their frontmatter). Settings files cannot store"
echo "max effort for the main session: use /effort max or claude --effort max."
