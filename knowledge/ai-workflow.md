---
title: AI-Tooling Workflow Journal
type: journal
updated: 2026-06-07
tags: [ai, workflow, claude-code, codex, ultracode]
---

# AI-Tooling Workflow Journal

A running log of *how* TarifHub is built with AI tools — what worked, what didn't, and which
mode fits which task. Append a dated entry whenever a tool, prompt pattern, or mode changes
the outcome. The goal is an honest, evolving playbook (and useful raw material for the CAS
write-up). Keep it factual; mark anything unverified.

## How we build, in one line

Claude Code (Opus 4.8) writes; **Codex reviews every PR** before merge; **Claude performs all
git/gh** (the founder never runs git by hand); big tasks run under **`/ultracode`** behind the
determinism hooks. See [[decisions/0001-adopt-claude-code-ultracode-codex-review]].

## Decision matrix — Vibe vs Spec-Driven vs Agentic

Pick the mode that matches the change. The hard constraint is the same in all three: nothing
crosses the freeze line (no AI computes/mutates a billing value; `versioning/`, `audit/`,
`crosswalk/`, `rules_frozen*` stay frozen).

| Dimension | **Vibe coding** | **Spec-Driven** | **Agentic (/ultracode)** |
|---|---|---|---|
| What it is | Converse + iterate, minimal upfront spec | Write spec → plan → tasks → implement | Orchestrator spawns parallel plan/execute/verify subagents |
| Human control | High, moment-to-moment | High, front-loaded into the spec | Lower per-step; high at the gate (you own the merge) |
| Best for | Small edits, spikes, throwaway prototypes, UI tweaks | Features touching a contract, the canonical model, or >1 layer | Codebase-scale refactors, migrations, fan-out work (e.g. one adapter per source) |
| Worst for | Anything touching the freeze line or DB schema | Tiny one-line fixes (overhead) | Vague goals with no tests to converge on |
| Artifacts produced | Code + chat history | Spec, plan, tasks, ADRs, tests | Many diffs + a verify report per subagent |
| Review cadence | Per logical change | Per task / per PR | **Per PR** (one PR per orchestrated task) |
| Determinism risk | Medium (easy to drift) | Low (spec pins intent) | **Highest surface** — many agents at once → the PreToolUse guard + determinism tests are the safety net |
| Tests | After, lightly | Test-first where it matters | Suite-gated: agents stay until tests pass |
| TarifHub default | Quick fixes, docs, copy | New endpoints, rules, crosswalk *suggestion* seams, schema-adjacent work | Multi-adapter ingestion, cross-service refactors, large arc42/code sync |
| Codex review | Still required on the PR | Required on the PR | Required on the PR (orchestrator opens one) |

**Rule of thumb:** if the change touches a *contract* (canonical fields, DB columns, REST
routes) or more than one layer → at least Spec-Driven. If it's *embarrassingly parallel* and
test-gated → `/ultracode`. If it's small and reversible → Vibe. When unsure, go more
structured, not less — and let Codex + the determinism-auditor catch drift on the PR.

## Why determinism hooks matter under parallel agents

`/ultracode` runs many subagents concurrently. Any one of them could, in principle, edit a
frozen path or import an LLM client onto a value path. Three guardrails make parallelism safe:

1. **PreToolUse guard** (`.claude/hooks/guard_frozen.sh`) — blocks edits to `versioning/`,
   `audit/`, `services/intelligence/**/crosswalk/`, and `rules_frozen*` for *every* agent.
2. **Stop / SubagentStop hooks** — run the determinism-boundary tests; an agent can't declare
   "done" across a broken freeze line.
3. **determinism-auditor subagent + Codex review** on the PR — independent confirmation before
   merge.

---

## Journal entries

> Template — copy for each new entry:
>
> ```
> ### YYYY-MM-DD — <short title>
> - **Task / mode:** <what + Vibe | Spec-Driven | /ultracode>
> - **Tools used:** <Claude Opus 4.8, Codex, graphify, context7, skills, MCP…>
> - **What worked:**
> - **What didn't / friction:**
> - **Determinism check:** <guard fired? tests green? anything near the freeze line?>
> - **Change to the playbook:** <if any>
> ```

### 2026-06-07 — Wired the Claude Code dev setup
- **Task / mode:** Stand up `.mcp.json`, hooks, subagents, slash commands, scripts, this vault — Spec-Driven (followed BUILD_BRIEF v4).
- **Tools used:** Claude Opus 4.8 (the wiring), Codex (designated PR reviewer going forward), graphify/context7/obsidian (configured in `.mcp.json`).
- **What worked:** The determinism boundary maps cleanly onto a PreToolUse guard + Stop/SubagentStop tests; `/ship` makes the Codex-review-before-merge loop one command.
- **What didn't / friction:** Some plugin/marketplace install names need confirming against upstream READMEs (handled as best-effort warnings in `scripts/setup-claude-code.sh`).
- **Determinism check:** Guard extended to cover the TarifIQ crosswalk + `rules_frozen*`; determinism tests run on Stop and SubagentStop.
- **Change to the playbook:** Default to `/ship` for every logical task; reserve `/ultracode` for big, test-gated work.
