# AGENTS.md — TarifHub working agreement

Open-standard agent guide (read by Codex and other tools). `CLAUDE.md` imports this
file so Claude Code and Codex share one source of truth. Keep both in sync.

TarifHub is an AI-assisted harmonization platform for Swiss ambulatory tariff data —
**one platform, four layers** around the freeze line. The sub-systems, each independently
containerized:

- **L0 — Harmonization Engine** (`services/ingestion`, Python) — pre-freeze, AI-assisted.
- **L1 — TarifCore API** (`services/serving`, Java 21 / Quarkus) — post-freeze, deterministic —
  plus **TarifMCP** (`services/mcp`, Python) — read-only MCP tools over serving, for AI agents.
- **L2 — TarifIQ** (`services/intelligence`, Python / FastAPI) — deterministic
  combinability/cumulation rules, the **TARMED↔TARDOC cross-walk**, and rule validation over
  frozen data. AI only *suggests* a candidate rule pre-freeze (the replaceable
  `ai_rule_suggest` seam — no live call at eval/test time); a human validates via
  `POST /v1/validate` before freeze.
- **L3 — Apps** (`apps/`, Next.js): **TarifGuard** (practice), **KassenFlow** (payer
  correspondence / Kostengutsprache), **MeldePilot** (mandatory reporting / quality data).
  Read-only over L1 + L2; each carries the de-identification boundary (`lib/deident.ts`).

The architectural backbone is the freeze line: AI before it, deterministic facts after it.
TarifMCP, TarifIQ's evaluation path, and the L3 apps all sit downstream of the line — they
only READ frozen records (and L2 verdicts) and never compute or mutate a value.

## Non-negotiable engineering rules

1. AI ONLY pre-freeze, plus search/discovery/explanation in serving — but AI NEVER computes or mutates a billing-relevant value.
2. Authoritative tariff values are always unaltered frozen, versioned records served deterministically.
3. Never rewrite whole files; minimal incremental diffs; never rename files/functions/routes/DB columns unless asked.
4. Preserve the canonical model (fields/columns/routes are frozen contracts — extend, never break).
5. Tests before done (pytest / mvn verify green).
6. versioning/ and audit/ modules are protected: change only with explicit human confirmation.
7. **TarifGuard de-identification.** Patient identifiers never leave Swiss infrastructure; only de-identified coding context (tariff/diagnosis codes, encounter structure) may be sent to an LLM; route via AWS Bedrock EU or Google Vertex AI EU; the only code allowed to build LLM payloads is apps/tarifguard/lib/deident.ts and the ingestion mapper's ai_map(). (The same boundary applies to the KassenFlow and MeldePilot apps via their own `lib/deident.ts`.)

## Dev-loop workflow (non-negotiable)

These govern *how* changes land. They do not override rules 1–7; they enforce them.

- **Codex reviews every PR before merge.** Driven by `/ship`: Claude opens the PR, Codex (a
  different model family, via codex-plugin-cc / `codex exec`) reviews the diff, Claude
  addresses findings, then merges. Cadence is **per PR / per logical task**, not per keystroke.
  The determinism-auditor and security-reviewer subagents run alongside Codex.
- **Claude Code performs ALL git/gh operations — the user never runs git manually.** Branch,
  Conventional Commit, push, PR, review, merge all go through `scripts/ship.sh` and
  `scripts/bootstrap-github.sh`. (gh/codex/claude run on the user's machine, not in CI/sandbox.)
- **`/ultracode` + determinism under parallel agents.** Use `/ultracode` (Opus 4.8 Dynamic
  Workflows: parallel plan/execute/verify subagents) for big, test-gated tasks; normal mode for
  small edits. Under parallelism the freeze line matters MORE: the PreToolUse guard
  (`.claude/hooks/guard_frozen.sh`, blocking `versioning/`, `audit/`,
  `services/intelligence/**/crosswalk/`, `rules_frozen*`) and the Stop/SubagentStop determinism
  tests are what stop any agent from crossing it. Keep a single orchestrator that owns the gate.
  See `docs/CLAUDE_CODE_SETUP.md` and `knowledge/ai-workflow.md`.

## Repo conventions

- Monorepo. `services/ingestion` (Python 3.12), `services/serving` (Java 21 / Quarkus 3.x),
  `services/mcp` (Python), `services/intelligence` (Python 3.12), and the `apps/*` (Next.js)
  are independent builds; `db/`, `deploy/`, `docs/`, `scripts/` are shared.
- The ingestion suite MUST run fully offline: SQLite by default, no live LLM, no network.
  The optional `ai` extra (anthropic, sentence-transformers) is never required for tests.
- Canonical model (LOCKED field set): `tariff_code, tariff_system, designation (de/fr/it),
  category, tax_points, price_chf, unit, valid_from, valid_to, source_url, source_version,
  harmonization_confidence, requires_review, metadata, record_hash, version, created_at`.
- `record_hash` is a deterministic SHA-256 over the sorted canonical content fields
  (excludes `record_hash`, `created_at`, `version`). Do not change the hashing rule
  without bumping the pinned test and getting explicit human sign-off.
- The only place a live LLM may be invoked in ingestion is `mappers/tariff_mapper.py::ai_map`
  (pre-freeze, non-billing fields). In serving, only the `...serving.search` package may
  reference langchain4j, and it returns persisted/frozen records — it never invents values.
- `apps/tarifguard` (Next.js) and `services/mcp` (Python/FastMCP) are READ-ONLY consumers
  of the serving API: they relay frozen records verbatim and never compute a value. The
  only TarifGuard code allowed to build an LLM-bound payload is `lib/deident.ts` (rule 7);
  its server-side route handlers under `app/api/*` keep `SERVING_BASE_URL` off the browser.
- Style: Python = ruff, line length 100, type hints, small pure functions. Java = standard
  Quarkus layout, constructor injection, no business logic in resources.
- Tests-before-done: `cd services/ingestion && pytest -q`, `cd services/intelligence && pytest -q`,
  `cd services/mcp && pytest -q`, and `cd services/serving && mvn verify`; for the apps,
  `npm run lint && npm run build`. The Stop/SubagentStop hooks run the Python suites + the
  determinism-boundary tests automatically (see `.claude/settings.json`).
