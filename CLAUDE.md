# CLAUDE.md — Claude Code project memory

@AGENTS.md

The non-negotiable rules and repo conventions live in `AGENTS.md` (imported above).
This file adds Claude-Code-specific workflow. Do not duplicate the rules here; if they
ever diverge, `AGENTS.md` wins and CLAUDE.md must be re-synced.

## Claude Code workflow

- **Four layers (one platform).** L0 `services/ingestion` (pre-freeze, Python); L1
  `services/serving` (deterministic, Quarkus) + `services/mcp` (read-only MCP tools, Python);
  L2 `services/intelligence` — **TarifIQ** (deterministic combinability/cumulation rules +
  TARMED↔TARDOC cross-walk + validation, Python); L3 `apps/tarifguard`, `apps/kassenflow`,
  `apps/meldepilot` (Next.js). Everything downstream of the freeze line only READS frozen
  records (and L2 verdicts) and never computes a value. TarifIQ *evaluates* deterministically;
  AI only *suggests* a rule pre-freeze (the `ai_rule_suggest` seam — no live call at eval/test).
- **Plan mode for multi-module changes.** Any change that spans more than one sub-system,
  the DB schema, the Helm chart, or the canonical model must start in plan mode. Produce
  the plan, get it approved, then implement as minimal incremental diffs (rule 3).
- **Codex reviews every PR; Claude does all git/gh.** Ship with **`/ship`** — Claude branches,
  makes a Conventional Commit, pushes, opens the PR, runs the **codex-reviewer**,
  **determinism-auditor**, and **security-reviewer** subagents, addresses findings, then merges
  (the user never runs git by hand; see `scripts/ship.sh` + `scripts/bootstrap-github.sh`).
  The review confirms: (a) no LLM client imported on a value path (`services/ingestion`
  `main.py`/`storage` and everything outside `serving.search`; `services/intelligence`
  `main.py`/`rules`/`crosswalk`/`validators`/`store`), (b) no AI computes/mutates a billing
  value, (c) tests green (rule 5). Cadence: **per PR / per logical task**, not per keystroke.
- **`/ultracode` for big tasks, normal mode for small edits.** `/ultracode` (Opus 4.8 Dynamic
  Workflows) runs parallel plan/execute/verify subagents until the suite passes — ideal for
  per-source ingestion work and cross-service refactors. Keep one orchestrator that owns the
  determinism gate; the hooks below are what keep parallel agents off the freeze line.
- **Protected / frozen paths.** A PreToolUse hook (`.claude/hooks/guard_frozen.sh`) blocks
  edits to `versioning/`, `audit/`, `services/intelligence/**/crosswalk/`, and `rules_frozen*`
  (exit 2). Editing them needs explicit human confirmation + a re-freeze/version bump where
  relevant; do not try to bypass the hook.
- **Hooks (see `.claude/settings.json`).** Stop → `pytest -q` in ingestion *and* intelligence
  plus the determinism-boundary tests; SubagentStop → the determinism-boundary tests (so a
  parallel `/ultracode` subagent can't finish across a broken freeze line); PreToolUse on
  Edit/Write/MultiEdit → the frozen-path guard. Let the hooks run; if a hook fails, the work
  is not done.
- **Contracts are frozen.** The canonical fields, DB columns, and REST routes are
  contracts. Extend additively; never rename or remove without an explicit request and
  an ADR.

## TarifGuard de-identification boundary (enforced)

`AGENTS.md` rule 7 is non-negotiable and Claude Code must enforce it on every change:

> Patient identifiers never leave Swiss infrastructure; only de-identified coding context (tariff/diagnosis codes, encounter structure) may be sent to an LLM; route via AWS Bedrock EU or Google Vertex AI EU; the only code allowed to build LLM payloads is apps/tarifguard/lib/deident.ts and the ingestion mapper's ai_map().

Before any PR that touches `apps/tarifguard` or the AI seams, confirm: no LLM-bound
payload is constructed outside `apps/tarifguard/lib/deident.ts` or
`services/ingestion/.../tariff_mapper.py::ai_map`; `apps/tarifguard` and `services/mcp`
remain read-only over serving and compute no value; `SERVING_BASE_URL` is read only in
server-side code (route handlers / `lib/api.ts`), never in browser bundles.

## Quick commands

- Ingestion tests: `cd services/ingestion && pytest -q`
- Intelligence (TarifIQ) tests: `cd services/intelligence && pytest -q`
- MCP tests: `cd services/mcp && pytest -q`
- Serving build: `cd services/serving && mvn verify`
- App dev: `cd apps/tarifguard && npm install && npm run dev` (also `apps/kassenflow`, `apps/meldepilot`)
- Local stack: `docker-compose up` (Postgres+pgvector, MinIO); add `--profile apps` for the apps+MCP, `--profile services` for intelligence
- Docs preview: `mkdocs serve -f docs/mkdocs.yml`
- **Ship a change:** `/ship "feat(scope): summary"` (Claude does branch→commit→push→PR→Codex review→merge)
- Dev setup details: `docs/START_GUIDE.md` · `docs/CLAUDE_CODE_SETUP.md` · `knowledge/ai-workflow.md`
