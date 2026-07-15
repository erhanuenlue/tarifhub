---
name: cas-audit
description: Periodic CAS grade estimate against the official anchors — run at each block end and at pre-flight. Pairs the deterministic floor (tools/cas_check.py) with the grade-auditor's judgment and files a dated report the board displays.
allowed-tools: Bash, Read, Grep, Glob, Agent
---

1. Run `python3 tools/cas_check.py` and show its table first — the structural floor and
   any ratchet regressions. Regressions get fixed before any auditing happens.
2. Dispatch the `grade-auditor` agent (Opus, pinned in its frontmatter) with the floor's `--json` output attached.
   It judges what the floor cannot (prose quality, consistency, roter Faden, honesty) and
   writes `vault/cas-audit/<date>.md` + `<date>.json`.
3. Present to Erhan: the per-criterion estimate table, the gap list **ranked by points at
   risk**, and the top three actions for the coming days.
4. The board's Project tab picks the JSON up automatically (estimate column + total).
   Frame every number as what it is: an estimate, not the grader.
