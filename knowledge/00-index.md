---
title: TarifHub Knowledge Vault — Index
type: index
updated: 2026-06-07
---

# TarifHub Knowledge Vault

The founder-owned **second brain** for TarifHub: the things that do *not* live in code —
decisions, research, the running AI-tooling journal, daily logs. Code structure lives in the
[[README|repo]] and in the **graphify** knowledge graph (see [[README#graphify-to-obsidian|README]]);
*why we decided things* lives here. The two never pretend to be each other.

> Open this folder as an Obsidian vault (point Obsidian at `knowledge/`). Claude Code also
> reads/writes these notes directly, and the **obsidian** MCP server in `.mcp.json` is pointed
> here (`TARIFHUB_VAULT`, default `./knowledge`).

## Map of content

- **[[ai-workflow]]** — the running AI-tooling journal + the Vibe vs Spec-Driven vs Agentic
  decision matrix. Start here when deciding *how* to build a given change.
- **decisions/** — ADR-style notes for choices that shape the product/dev setup.
  - [[decisions/0001-adopt-claude-code-ultracode-codex-review|0001 — Claude Code + /ultracode + Codex review]]
- **research/** — verified notes, tool evaluations, market/regulatory findings.
  - [[research/2026-06-claude-code-tooling-eval|2026-06 — Claude Code tooling evaluation]]
- **daily/** — dated working logs (what I did, what's next, open questions).
  - [[daily/2026-06-07|2026-06-07]]

## The one rule that constrains everything

AI assists **before the freeze** (harmonization, rule *suggestion*) and for
**search/explain** — but **AI never computes or mutates a billing value**. Authoritative
values are unaltered, frozen, versioned, hashed records. Every note, decision, and experiment
here respects that boundary. See `AGENTS.md` (the seven non-negotiable rules) and
[[decisions/0001-adopt-claude-code-ultracode-codex-review]].

## Conventions

- Notes are plain Markdown with `[[wikilinks]]` and a small YAML frontmatter block
  (`title`, `type`, `updated`, optional `tags`).
- ADR-style notes in `decisions/` are numbered `NNNN-kebab-title.md`.
- Daily notes are `YYYY-MM-DD.md`.
- Keep claims sourced. If a fact is unverified, mark it so (don't invent figures).
