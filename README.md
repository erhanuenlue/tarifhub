# tarifhub — development workspace (Opus 4.8)

Swiss ambulatory tariff data platform: AI-assisted harmonisation above a deterministic freeze line, one versioned API below it, a thin TarifGuard demo on top. CAS capstone (FFHS, due 6 Jul 2026) and the seed of the commercial platform — same codebase.

**Read order for a new session:** `AGENTS.md` (facts) → `CLAUDE.md` (workflow) → `vault/` (CAS evidence status). Strategy/architecture documents live in the `tarifhub-fable5` folder this workspace ships inside (`../../`): CAS Dossier, Architecture v2, Feasibility v3, Business Plan v3.

## Quick start

```bash
./SETUP.md  # read it — one-time machine setup (uv, docker, k3d, gh, claude)
claude      # then paste FIRST_PROMPT.md for session 1
```

## What's deliberately NOT here

This setup was rebuilt lean for an orchestrator-plus-workers pipeline (June 2026; orchestrator now Opus 4.8, Fable 5 in the early blocks). Removed vs the earlier environments, on purpose:

- **No agent zoo** — 6 custom agents, each with one pinned job: two pipeline workers (`implementer` and `e2e-tester`, both Opus 4.8) and reviewers (verifier, determinism-auditor, security-reviewer, all Opus; codex-reviewer on gpt-5.5). The orchestrator (Opus 4.8) keeps the jobs where quality compounds: plan, orchestration, merge-gate. Built-in Explore covers search.
- **A phased shipping pipeline with a live board** — `/ship` runs 9 phases (plan-approval → TDD implement → gates → reviews → fix → PR/CI → runtime E2E+logs → report → merge-confirmation) with exactly two human gates. **Shipboard** (`tools/shipboard/shipboard.py`, stdlib one-filer on :8787) visualises phases and active agents live, fed by the emit script + Task hooks — plus a **session/context/usage monitor**: session status, context gauge against the 1M window (with compaction warnings), cumulative tokens in/out, cache-hit rate, turns/prompts/tool-calls, and estimated cost per model (editable price table in the file), all parsed incrementally from the Claude Code transcript via the `session_track` hook. CAS-fit: phase 7 verifies against local compose instead of cloud staging, and every run generates journal-ready multi-model evidence (criterion 15).
- **No graphify / knowledge-graph MCP** — context cost without payoff at this repo size. `.mcp.json` carries Context7 only; `gh` CLI covers GitHub; Playwright runs as a plain dev dependency.
- **No hand-rolled memory system for Claude** — native auto memory handles its learnings. `vault/` exists for **graded CAS evidence** (journal, decision matrix, Fazit notes) — human-curated, contemporaneous.
- **A living second brain instead of a static one** — the `brain_sync` SessionEnd hook regenerates `vault/00-index.md` (current map of every ADR, journal day, learning) and optionally mirrors the knowledge set into your Obsidian vault (`OBSIDIAN_VAULT` in `.env`). Open the repo in Obsidian and the architecture documents itself as you work. Publishing: `docs/mkdocs.yml` → GitHub Pages via `.github/workflows/docs.yml`, PDF via the print-site page. SETUP.md §4–5.
- **No commands/ directory** — skills replaced commands (`/ship`, `/new-source`, `/cas-status`).
- **A prompt library that respects the model** — `prompts/01–07` cover the road to submission as **outcome prompts** (goal, constraints, verification), one per block milestone. What's deliberately absent is the old style of prescriptive step-scripts, which degrade the orchestrator's output. `prompts/README.md` has the usage rules.

Three hooks only, each enforcing what instructions can't: `guard_frozen` (PreToolUse — the freeze line), `format` (PostToolUse — ruff/prettier), `journal_draft` (SessionEnd — CAS evidence skeleton).

## The one rule

**No AI computes or mutates a billing value at serve time.** Everything else is negotiable; this is not. `tests/test_determinism_boundary.py` + `guard_frozen.sh` + the determinism-auditor agent enforce it at three layers.
