---
title: 0001 — Adopt Claude Code (/ultracode) + Codex review + autonomous git
type: decision
status: accepted
date: 2026-06-07
tags: [adr, dev-setup, claude-code, codex, determinism]
---

# 0001 — Claude Code (/ultracode) + Codex review + autonomous git

> ADR-style note for the **dev setup**. (Product/architecture ADRs live in `docs/adr/`; this
> vault note records the *workflow* decision.)

## Status

Accepted — 2026-06-07.

## Context

TarifHub is a Python + Quarkus + Next.js monorepo with one hard promise: **no AI ever
computes or mutates a billing value.** AI harmonizes *before* the freeze (human-in-the-loop)
and powers search/explain *after* it; authoritative values are unaltered, versioned, hashed,
frozen records. The founder develops solo with two AI runtimes available — Claude Code (Claude
Max) and Codex (GPT Pro) — and wants to move fast without crossing that line, and without
hand-running git.

Verified tooling facts (mid-2026, cite with dates):
- **Claude Opus 4.8** (28 May 2026, `claude-opus-4-8`): 1M context, 88.6% SWE-bench Verified,
  parallel plan/execute/verify subagents.
- **`/ultracode`** (28 May 2026): session-only Claude Code mode — *xhigh* effort + Dynamic
  Workflows (parallel agents that stay until the suite passes).
- **Codex as reviewer:** OpenAI's official **codex-plugin-cc** (30 Mar 2026) runs a Codex
  review from inside Claude Code via a slash command.

## Decision

1. **Claude Code on Opus 4.8 is the primary dev environment**; `/ultracode` for big,
   test-gated tasks, normal mode for small edits. (See the matrix in [[ai-workflow]].)
2. **Codex reviews every PR before merge**, automated by `/ship` (which also runs the
   determinism-auditor and security-reviewer subagents). Cadence: **per PR / per logical
   task**, not per keystroke.
3. **Claude Code performs ALL git/gh operations** — branch, conventional commit, push, PR,
   review, merge — via `scripts/ship.sh` and `scripts/bootstrap-github.sh`. The founder never
   runs git by hand.
4. **The determinism boundary is enforced by hooks, not hope:** a PreToolUse guard blocks
   edits to `versioning/`, `audit/`, `services/intelligence/**/crosswalk/`, and `rules_frozen*`;
   Stop/SubagentStop run the determinism-boundary tests. This is what makes parallel `/ultracode`
   agents safe.
5. **Knowledge tooling:** graphify (codebase graph + MCP + Obsidian export) + this Obsidian
   vault + context7 (fresh library docs) + mattpocock/skills. Skip the heavyweight,
   process-owning methodologies; keep the surface auditable.

## Consequences

- **Good:** A single guarded gate keeps determinism intact even under heavy parallelism; an
  independent model (Codex) reviews every change; git is consistent and hands-off; the "why"
  is captured in this vault and graphify keeps the "how" fresh.
- **Costs / risks:** Two AI subscriptions (Claude Max + GPT Pro). Some plugin/marketplace
  install names may drift — `scripts/setup-claude-code.sh` treats them as best-effort. Branch
  protection requires the `devsecops gates` CI check name to match `ci.yml`.
- **Revisit if:** the determinism tests ever feel like theatre (tighten them), or `/ultracode`
  parallelism starts producing PRs too large to review well (shrink task scope).

## Links

- [[ai-workflow]] · [[research/2026-06-claude-code-tooling-eval]] · `docs/CLAUDE_CODE_SETUP.md`
  · `docs/START_GUIDE.md` · `AGENTS.md`
