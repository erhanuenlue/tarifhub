#!/usr/bin/env bash
# Session lifecycle tracker for the Shipboard.
# Registered for: SessionStart, UserPromptSubmit, PreCompact, SessionEnd.
# Maintains .shipboard/session.json (latest session wins). Quiet, never blocks.
set -u
cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}" || exit 0
mkdir -p .shipboard
cat | python3 -c '
import json, time, sys, os
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
path = ".shipboard/session.json"
try:
    s = json.load(open(path))
except Exception:
    s = {}
event = d.get("hook_event_name", "")
sid = d.get("session_id") or s.get("session_id")
now = time.strftime("%Y-%m-%dT%H:%M:%S")
if sid and s.get("session_id") not in (None, sid):
    s = {}  # a different session takes over the board
s["session_id"] = sid
if d.get("transcript_path"):
    s["transcript_path"] = d["transcript_path"]
if event == "SessionStart":
    s.update({"started": now, "status": "active", "prompts": 0, "compactions": s.get("compactions", 0)})
elif event == "UserPromptSubmit":
    s.setdefault("started", now)
    s["status"] = "active"
    s["prompts"] = int(s.get("prompts", 0)) + 1
elif event == "PreCompact":
    s["compactions"] = int(s.get("compactions", 0)) + 1
    s["last_compact"] = now
elif event == "SessionEnd":
    s["status"] = "ended"
    s["ended"] = now
s["last_activity"] = now
json.dump(s, open(path, "w"))
' 2>/dev/null || true
exit 0
