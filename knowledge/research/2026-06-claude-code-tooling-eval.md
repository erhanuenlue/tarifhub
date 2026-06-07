---
title: 2026-06 — Claude Code tooling evaluation (graphify, context7, skills, Obsidian)
type: research
status: verified
date: 2026-06-07
tags: [research, tooling, claude-code, mcp, knowledge-graph]
---

# Claude Code tooling evaluation — June 2026

Condensed, decision-oriented summary of the fuller evaluation (14 repos + features) in
`DevSetup/TarifHub_ClaudeCode_Setup_EN.md`. Star counts/dates are as reported in early June
2026; where unverified, they're marked. The lens: a determinism-strict monorepo built solo.

## Install now (the three pillars)

- **graphify** — codebase + docs → queryable knowledge graph; local tree-sitter extraction
  (28 grammars incl. Python/TS/Java), built-in MCP server (`query_graph`, `get_node`,
  `shortest_path`), post-commit auto-rebuild, confidence tags, `--obsidian` export. ~52.7k★,
  MIT, YC S26. *The structural brain of the repo.* Wired in `.mcp.json` (`graphify`).
- **context7** — up-to-date, version-specific library docs MCP (`resolve-library-id`,
  `query-docs`). ~56.3k★, MIT, free without a key (rate-limited). Kills hallucinated
  Quarkus/Jakarta/FHIR/Next.js APIs. Wired in `.mcp.json` (`context7`).
- **mattpocock/skills** — small, composable, model-agnostic skills (`grill-with-docs` →
  writes decisions into CONTEXT.md/ADRs; `tdd`; `diagnose`; `git-guardrails-claude-code`).
  ~97.7k★, MIT. Complements (does not replace) the spec-driven spine.

Pair the above with **Obsidian** as the human second brain → this `knowledge/` vault, with
graphify's `--obsidian` export bridging code nodes into notes. See [[README]].

## Deliberately skipped (and why)

- **arc-kit** — ~10k tokens/session + enterprise RFP machinery; lift individual arc42/Wardley
  skill files only if needed.
- **ECC** (243 skills) — un-auditable context surface for a determinism-strict project.
- **Superpowers / gstack** — strong, but they want to *own the whole process*; don't stack a
  second methodology on the spec-driven spine. Cherry-pick at most (e.g. `subagent-driven-development`).
- **mem0** — a product memory SDK (belongs inside an app like TarifGuard), not a dev brain.
- **ScrapeGraphAI / quarkdown / odysseus** — runtime ingestion lib / doc typesetting /
  self-hosted app; off-scope for the CLI setup. ScrapeGraphAI's LLM extraction would have to
  stay strictly pre-freeze.
- **claude-mem / context-mode / herdr** — *maybe later*, one at a time; vet claude-mem's data
  handling + token entanglement first.

## Notes that shaped the wiring

- Hooks support conditional filtering + `agent_id`/`agent_type` — exactly what makes a
  per-path determinism guard practical under parallel agents.
- Opus 4.8 Dynamic Workflows (parallel plan/execute/verify subagents) map onto per-source
  ingestion work — *provided a single orchestrator owns the determinism gate.*
- Keep a Postgres/Supabase MCP **read-only** against frozen tables if/when added, so a tool
  call can't cross the freeze line.

## Sources

`DevSetup/TarifHub_ClaudeCode_Setup_EN.md` (full eval, with per-repo source links), accessed
June 2026. Decision recorded in [[decisions/0001-adopt-claude-code-ultracode-codex-review]].
