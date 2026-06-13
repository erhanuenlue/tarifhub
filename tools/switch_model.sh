#!/usr/bin/env bash
# switch_model.sh · one-command orchestrator switch (ADR-018).
#
#   bash tools/switch_model.sh opus     # on/after 22 Jun 2026: Opus 4.8 orchestrates
#   bash tools/switch_model.sh fable    # rollback if Fable access returns
#
# Single source of truth: the "model" key in .claude/settings.json.
# Interactive sessions in this repo and tools/loop.sh both read it.
# Worker/review agent seats are pinned separately (all Opus 4.8) and never change.

set -u
cd "$(git rev-parse --show-toplevel 2>/dev/null || dirname "$0")/." || exit 1

case "${1:-}" in
    opus)  M="claude-opus-4-8" ;;
    fable) M="claude-fable-5" ;;
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
print(f"orchestrator: {old} -> {m}")
PY

echo
echo "Done. Verify:"
echo "  1. open a session in this repo:  claude  ->  /status must show: $M"
echo "  2. loop resolves the same key:   bash tools/loop.sh prints 'model: $M' at start"
echo "  3. commit it: git add .claude/settings.json && git commit -m 'chore: orchestrator -> $M (ADR-018)' && git push"
echo
echo "Notes for the opus orchestrator (ADR-018): /effort ultracode is a Fable command,"
echo "skip it; the loop's standing max-effort order (ultrathink) covers both models."
