# CLAUDE.md — TarifHub (Fable 5)

@AGENTS.md

Project facts, layout, commands and the determinism rule are in AGENTS.md above. This file is the Claude-Code workflow, tuned for Fable 5 — deliberately short. When Erhan corrects you, add one short rule here (or in auto memory), don't grow paragraphs.

## How to work

- Take tasks whole (spec → implement → verify); don't pre-chop. State the why when delegating. Do the simplest thing that works — no speculative abstractions, no future-proofing, validate at system boundaries only.
- Before claiming progress, check each claim against a tool result from this session. Failing test → say so with output. Skipped step → say so.
- Plan mode for anything multi-file; skip it when the diff fits one sentence. For long unattended runs use `/goal "<verifiable condition>"`.
- **Maintain your todo list during multi-step work** (statuses kept current) — Shipboard's kanban mirrors it live; an untracked plan is invisible to Erhan's board.
- When Erhan is thinking out loud, deliver an assessment, not a patch. Pause only for: destructive/irreversible actions, real scope changes, or input only he has.
- Effort — **Erhan's policy (owner decision):** build/ship sessions run **`/effort ultracode`** (xhigh baseline + auto-orchestration). Within the pipeline, **allocate effort per task by complexity, medium ↔ xhigh**: xhigh where reasoning compounds (the plan on complex scope, disputed review findings, the merge-gate read), high for normal orchestration and writing, medium for mechanical inline steps. Two invariants no orchestration mode may touch: **gates 01 and 09 are hard human stops — never auto-skipped**, and **worker model pins are never overridden** (effort governs your reasoning, not theirs). Outside build sessions: `medium` for chores; `max` never by default.

## The pipeline — you orchestrate, workers produce

You (Fable 5) do the three jobs where quality compounds: **the plan, the orchestration, the merge-gate review**. The volume is delegated to model-pinned workers — never override an agent's pinned model, never switch models mid-task (caches are model-scoped):

- `implementer` (**Opus 4.8**) — TDD implementation of approved-plan tasks; parallel dispatch when tasks are independent. You write code yourself only for glue too small to dispatch, and in quick interactive sessions where pipeline overhead isn't worth it.
- `e2e-tester` (**Sonnet**) — mechanical runtime verification: compose-up, integration runs, API/console smoke, log scans. Evidence collector, not a fixer.
- Reviewers: `verifier` (fresh-context diff-vs-spec — self-critique is not verification) · `determinism-auditor` (Sonnet, mandatory for `services/`) · `security-reviewer` (Opus — also covers what Fable's safety classifiers decline) · `codex-reviewer` (independent second model family; CAS evidence of multi-tool use — journal it).
- Built-in Explore handles codebase search. Launch independent agents in one parallel batch and keep working.

**`/ship` runs the whole 9-phase pipeline** (plan-approval → implement → gates → reviews → fix → PR/CI → runtime verification → report → merge-confirmation) with two human gates that are never skipped: Erhan approves the plan, Erhan confirms the merge. Live board: `python3 tools/shipboard/shipboard.py` → http://localhost:8787.

## Git & GitHub — you do all of it

Erhan never runs git by hand. Branch → small Conventional Commits → `gh pr create` → reviews (verifier + determinism + security as applicable) → address → squash-merge green. `/ship` runs the whole loop. First time only: `gh repo create tarifhub --private --source=. --push`.

## Memory & CAS evidence (two different things)

- **Auto memory is yours** — record corrections, gotchas, confirmed approaches there; keep it current; delete what proves wrong.
- **`vault/` is Erhan's graded evidence, not your memory.** The SessionEnd hook drafts `vault/daily/` journal entries; end each session by curating the draft into 3–6 honest lines: what was delegated, what AI got wrong and what caught it (hook? review? test?), one concrete prompt→diff example. Never backfill journal entries — contemporaneity is the point.

## Definition of done

Code works → `pytest -q` green (offline) → ruff clean → relevant reviewers addressed → PR squash-merged → ADR if a decision was made → journal entry curated. Nothing below the freeze line touched by AI — `guard_frozen` enforces this; don't work around it, flag it.
