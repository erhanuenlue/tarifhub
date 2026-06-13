#!/usr/bin/env bash
# Auto-emit agent activity to the Shipboard from Claude Code hook events.
# Registered for: PreToolUse + PostToolUse (matcher: Task — subagent launches) and SubagentStop.
# Quiet, never blocks.
set -u
cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}" || exit 0
mkdir -p .shipboard
cat | python3 -c '
import json, time, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
event = d.get("hook_event_name", "")
agent = status = None
if d.get("tool_name") in ("Task", "Agent"):   # subagent tool name varies by Claude Code version
    agent = (d.get("tool_input") or {}).get("subagent_type", "subagent")
    status = "active" if event == "PreToolUse" else "done"
elif event == "SubagentStop":
    agent = d.get("agent_name", "subagent"); status = "done"
if agent:
    pins = {"implementer": "Opus 4.8", "e2e-tester": "Opus 4.8",
            "determinism-auditor": "Opus 4.8", "security-reviewer": "Opus 4.8",
            "codex-reviewer": "gpt-5.5", "verifier": "Opus 4.8"}
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "agent",
                      "phase": None, "status": status, "detail": "",
                      "agent": agent, "model": pins.get(agent, "")}))
' >> .shipboard/events.jsonl 2>/dev/null || true
exit 0
