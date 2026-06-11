#!/usr/bin/env bash
# Shipboard event emitter: emit.sh <phase|agent> <status> ["detail"] [agent_name] [model]
#   phases: 01..09 · status: running|pass|fail|skip
#   agents: emit.sh agent <active|done> "detail" <name> <model>
# Appends one JSON line to .shipboard/events.jsonl. Never fails the caller.
set -u
mkdir -p .shipboard
python3 - "$@" >> .shipboard/events.jsonl 2>/dev/null <<'EOF' || true
import sys, json, time
a = sys.argv[1:]
print(json.dumps({
    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "kind": "agent" if (a and a[0] == "agent") else "phase",
    "phase": None if (a and a[0] == "agent") else (a[0] if a else "?"),
    "status": a[1] if len(a) > 1 else "?",
    "detail": a[2] if len(a) > 2 else "",
    "agent": a[3] if len(a) > 3 else None,
    "model": a[4] if len(a) > 4 else None,
}))
EOF
exit 0
