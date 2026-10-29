# tarifhub: Project Facts (read first)

Swiss ambulatory tariff data platform. Four layers: L0 harmonisation (AI-assisted, pre-freeze) → L1 deterministic serving API + MCP → L2 rules (TarifIQ skeleton in-repo) → L3 apps (demo now).

**Status: the earlier CAS capstone (AI-Assisted Software Engineering) was submitted 3 July 2026 (tip 530f850) as the public repo https://github.com/erhanuenlue/tarifhub plus its GitHub Pages docs site. Its grading material (the git-ignored `docs/cas/` anchors, `docs/criterion-map.md`, the `vault/` journals and audits) is historical evidence, not the requirement set for the current CAS AI Engineering project. Pre-submission files may be edited normally; two things stay protected: never rewrite pre-submission history, and never backfill or edit past `vault/` journal entries (contemporaneity is the point).**

## The one inviolable rule

**No AI computes or mutates a billing value at serve time.** AI may run only (a) pre-freeze in `ai_map` (non-billing fields, schema-constrained structured output) and (b) in explain/search seams that never alter values. Frozen records are immutable: SHA-256 `record_hash` over a sorted canonical field tuple (`versioning/freeze_record.py`; excludes hash/created_at/version); updates insert at MAX(version)+1, never UPDATE (`storage/tariff_repository.py`); `audit_log` is append-only by construction (`audit/audit_logger.py`, INSERT-only; no DB-level trigger enforces it).

Boundary tests (all run in CI's per-service suites; red = CI fails, ADR-010. Ingestion's determinism test and the serving twin additionally re-run in a named, log-visible CI step):
- `services/ingestion/tests/test_determinism_boundary.py` and `services/intelligence/tests/test_determinism_boundary.py`
- `services/serving/tests/test_serving_boundary.py` (the serving twin)
- siblings `test_value_path_boundary.py` and `test_review_boundary.py` (ingestion) extend the same guard

The freeze line (paths NO agent may edit, in any harness) is this list; the machine copy is the regex in `.claude/hooks/guard_frozen.sh` (a Claude PreToolUse Edit|Write hook wired in `.claude/settings.json`; one enforcement implementation, not the rule itself):
- `services/ingestion/**/versioning/` and `services/ingestion/**/audit/`
- applied (existing) `db/migrations/*.sql`: the hook blocks Edit/Write on any existing migration file; new migrations must be forward-only `NNN_<description>.sql` (the hook enforces the name)
- the basenames `tests/test_determinism_boundary.py` and `tests/test_serving_boundary.py` in ANY directory

Consequences:
- The hook fires only on Claude Edit/Write tool calls. Bash writes (sed, tee, redirect, heredoc) and non-Claude harnesses bypass it; the ban binds regardless. Before editing and again before completion, check the FULL change set against the list above: `git diff --name-only main...HEAD` plus `git status --porcelain` (a bare `git diff` misses committed and staged changes).
- New boundary tests must NOT reuse the frozen basenames; name them `test_<service>_boundary.py` (e.g. `test_value_path_boundary.py`).
- Never work around the guard; flag any needed frozen-path change to Erhan.

## Layout

```
services/ingestion/      L0: adapters → parsers → map_raw → ai_map → validate → score → flag → freeze
                         (review is post-freeze: console approve/correct re-freezes a successor version)
services/serving/        L1 TarifCore: REST + FHIR R4, point-in-time + diff, pgvector search (read-only)
services/mcp/            L1 TarifMCP: search_tariffs, get_tariff, explain_record (read-only proxies)
services/intelligence/   L2 TarifIQ: combinability rules + TARMED-TARDOC crosswalk + rule validation
                         (deterministic, offline; AI suggestion seam stubbed)
apps/tarifguard/         L3 TarifGuard Console: master-detail + review form + labelled AI explain panel
                         + coding-check page, over server-side BFF routes (app/api/*)
apps/kassenflow/         L3 Next.js stub (out of scope, ADR-013): future-work scaffolding, not wired
apps/meldepilot/         L3 Next.js stub (out of scope, ADR-013): future-work scaffolding, not wired
db/                      schema.sql + migrations (Postgres 16 + pgvector). Schema change = edit schema.sql
                         + add a NEW forward-only migrations/NNN_*.sql (applied ones are frozen, never
                         edited) + update the inline _SQLITE_SCHEMA offline mirror in
                         services/ingestion/src/tarifhub_ingest/storage/db.py (the mirror lives there, not in db/)
deploy/                  docker-compose.yml (wired review-loop + batch stack) + docker-compose.e5.yml
                         (real-e5 vector recording) + helm/ (k3d, the CAS K8s proof); the root
                         docker-compose.yml is the light read-side dev stack
docs/                    arc42/ (13 chapters, MkDocs Material → the deliverable site) + adr/ (register
                         001..021 + legacy/) + method/ (AI-tools chapter) + evidence/ + criterion-map.md
tools/                   cas_check.py (CI ratchet) + switch_model.sh (main-model pin) + bench/search_latency.py
                         + search_eval/ (latency + quality harnesses: use these for any search
                         performance question before hand-rolling measurement). Historical, not part of
                         the workflow: curate.sh, loop.sh, shipboard/, hooks/ (legacy git hooks: do not install)
vault/                   earlier-CAS evidence: daily/ journal, decision-matrix.md, fazit-notes.md (preserved)
aise-harness/, prompts/, knowledge/, docs/cockpit/, scripts/setup-claude-code.sh
                         earlier-CAS harness tour, session prompts, knowledge vault, cockpit spec and
                         tooling installer: historical, not instructions
```

## Stack

Python 3.12 + FastAPI + Pydantic v2 (one canonical `TariffRecord` end-to-end) · PostgreSQL 16 + pgvector (HNSW, cosine; multilingual-e5-large 1024-dim) · Claude schema-constrained structured output (pre-freeze only) · Next.js App Router (demo) · Docker + Helm/k3d · GitHub Actions (ruff, pytest, gitleaks, Trivy, Syft SBOM, CI image builds, GHCR push decided but not yet wired, ADR-010; docs.yml builds the Pages site on any docs/** push to main and publishes when the DEPLOY_PAGES=true repo variable is set; it also offers workflow_dispatch) · OpenTelemetry instrumented in serving (FastAPI request traces + a custom search span and duration histogram; OTLP export opt-in via `OTEL_EXPORTER_OTLP_ENDPOINT`, a true no-op when unset; ADR-011), with Prometheus/Grafana + Sentry as intended backends, not yet wired.

ADR register: `docs/adr/` 001..021, three-digit numbering (ADR-001 Python-first, ADR-013 demo scope, ADR-020 Codex seat; ADR-018 and ADR-020 record the earlier model-seat setup, the current one is CLAUDE.md plus `.claude/`). `docs/adr/legacy/` preserves the pre-2026-06-11 register under DIFFERENT, colliding numbers: never cite a legacy number in new text; resolve old citations via `docs/adr/legacy/README.md`.

## Commands

```bash
cd services/<svc> && uv sync --extra dev # per service (no root pyproject); the dev extra holds pytest+ruff,
                                         # plain 'uv sync' drops them (CI: uv sync --frozen --extra dev)
cd services/<svc> && uv run --no-sync pytest -q
                                         # offline: SQLite mirror + stub embedder, no containers; --no-sync or
                                         # the implicit re-sync drops the dev extra (~410 tests total as of
                                         # 2026-07-15: 208 ingestion, 122 serving, 17 mcp, 63 intelligence)
cd services/<svc> && uvx ruff check .    # the CI lint gate (non-mutating; CI runs it INSIDE each service dir;
                                         # tools/ and the repo root are not gated and carry pre-existing noise).
                                         # Apply fixes only with 'uvx ruff check --fix <touched paths>'.
                                         # NEVER run 'ruff format .': pre-existing format drift incl. frozen
                                         # boundary tests; CI does not gate format
mkdocs build -f docs/mkdocs.yml --strict # the CI docs gate (mkdocs<2 pinned); 'mkdocs serve' is preview only.
                                         # Binary is a uv tool at ~/.local/bin/mkdocs; python3 -m mkdocs FAILS.
                                         # Missing? uv tool install 'mkdocs<2' --with 'mkdocs-material>=9,<10' \
                                         #   --with 'mkdocs-enumerate-headings-plugin<1'
python3 tools/cas_check.py               # CAS structural floor; CI runs '--ci' as a ratchet vs
                                         # tools/cas_baseline.json: run it before pushing doc changes
docker compose up -d db                  # dev Postgres+pgvector (named volume), not a test database: the PG
                                         # test legs stay SKIPPED until TARIFHUB_PG_TEST_URL names a disposable
                                         # one (see Environment)
cd apps/tarifguard && npm install && npm run dev
                                         # console on :3000 (fresh clone: npm install once); npm test = Vitest +
                                         # Playwright smoke. CI additionally gates npm run lint AND npm run build
                                         # (Playwright browsers: npx playwright install --with-deps chromium, once)
```

Command gotchas (each one has burned a session):
- After any `uv run --extra ai` step (e5 recording), re-sync with `uv sync --frozen --extra dev` before running the offline suite: a polluted venv masks the e5-to-stub fallback. CI never installs the ai extra.
- Compose interpolates `TARIFHUB_DB_URL` from `.env` into containers (docker-compose.yml): a `.env` carrying the host form `@localhost` breaks the serving container, which needs `@db:5432`. Recreate with `TARIFHUB_DB_URL='postgresql://tarifhub:tarifhub@db:5432/tarifhub' docker compose up -d --force-recreate serving`.
- When capturing test counts or coverage for docs, re-derive from a fresh run with `uv run --no-sync pytest -q --junitxml=out.xml` and read the testsuite attributes: the piped `-q` summary line is swallowed in this repo's services. Never trust committed doc numbers.

## Environment

Env-only config. Core set below; the full per-service inventory with defaults is each service's `src/*/config.py` (BaseSettings) and `services/ingestion/README.md`.

- `TARIFHUB_DB_URL`: default `sqlite:///./tarifhub_dev.db` (CWD-relative). Postgres form `postgresql://tarifhub:tarifhub@localhost:5432/tarifhub` from the host, `@db:5432` inside compose.
- `TARIFHUB_REVIEW_THRESHOLD`: default 0.85; confidence below it, or any validation failure, stamps `requires_review` on the record. The record still freezes and is stored (review is post-freeze); a console approve/correct decision then re-freezes an immutable successor version.
- `TARIFHUB_EMBEDDINGS`: `stub|e5`, default stub (16-dim, fits only the SQLite mirror); `e5` needs the ai extra and is required for Postgres pgvector writes. Read by ingestion AND serving search via the shared embedder.
- `TARIFHUB_PG_TEST_URL`: unset = the Postgres parity/integration test legs skip silently; set it to enable them, only ever to a disposable database (CI's service container; locally the tmpfs stack of `deploy/docker-compose.verify.yml`, commands in its header). Never point it at a development stack's `tarifhub-db`: the legs create and drop scratch databases on that server, and `services/ingestion/tests/test_audit_pg_roundtrip.py` writes into the database the URL names.
- `ANTHROPIC_API_KEY`: unset = `ai_map` returns the deterministic `map_raw` result (`mappers/tariff_mapper.py`); the offline tests rely on this fallback.
- `OTEL_EXPORTER_OTLP_ENDPOINT`: opt-in serving telemetry; unset = true no-op.
- `SERVING_BASE_URL`: L1 base URL for the console BFF (REQUIRED there, `apps/tarifguard/lib/api.ts` throws without it), MCP and TarifIQ (default `http://localhost:8000` for those two). TarifIQ also accepts `TARIFIQ_SERVING_BASE_URL`, which takes precedence.
- `INGEST_BASE_URL`: console review proxy target (ingestion review API); unset = the console serves a bundled demo queue and review decisions are NOT persisted.
- `TARIFIQ_OFFLINE`: default true (bundled frozen tables, hermetic tests); truthy values are 1/true/yes/on. Set `0` plus a reachable `SERVING_BASE_URL` to read live frozen records.

All `.env*` files at any depth (including `.env.example`) are read- and edit-denied in `.claude/settings.json`: `Read(...)` and `Edit(...)` rules, and Claude Code applies `Edit` rules to every file-writing tool (a `Write(...)` path rule would never match). The rule binds every harness: no AI reads or writes a `.env*` file. When a `.env*` change is needed, hand Erhan the exact command to run himself; when he asks, AI may stage and commit the result. For live runs load secrets with `uv run --env-file ../../.env ...` from the service dir; assert presence only, never print key material.

## Conventions

- **Grounding: never speculate about code you have not opened. If a file is referenced, read it before answering or editing. A claim must trace to a tool result from this session.**
- **Git: commit, push, open PRs and merge only when Erhan explicitly asks in the current session.** When asked: branch `feat/…|fix/…`, Conventional Commits, `gh pr create`. Squash-merge only when all of these hold: CI fully green (security job included), every review finding resolved or explicitly dispositioned (no open P1/P2; a determinism violation always blocks), no freeze-line path Erhan did not authorize this session, working tree clean and branch current with `main`. Never force-push (denied) or rewrite history. The repo is public: never change its visibility or re-create it.
- Commit SHAs cited in docs/, vault/ or LEARNINGS.md must be squash-merge SHAs: verify with `git merge-base --is-ancestor <sha> main` before citing; pre-squash branch commits are unreachable from main.
- GitHub skips Actions when `[skip ci]`/`[ci skip]` appears ANYWHERE in the head commit message (title or body): never quote the bracketed token in a commit you push, and never end a push sequence on such a commit. `ci.yml` has no `workflow_dispatch`.
- **Quality before cost (owner law): never downgrade a model, an effort level or a review step to save tokens; Sonnet and Haiku are not used.** Claude's setup (one model pin in `.claude/settings.json`, every subagent `model: inherit` with `effort: max`) is described in CLAUDE.md. Non-Claude agents: never modify `.claude/settings.json` or `.claude/agents/*`; run your own harness at its strongest available model and reasoning, and state which Claude-specific steps you could not perform.
- The canonical model's field set is **locked, additive-only** (ADR-003). A breaking change needs a new ADR before code. Any NEW content field must also enter `HASHED_FIELDS` in `versioning/freeze_record.py`, which is below the freeze line: a canonical-field addition is therefore ALWAYS a frozen-path change. Flag it to Erhan at plan time; never ship a content field absent from the hash tuple (records differing only in that field would collide as unchanged content).
- German is the canonical designation language; FR/IT optional (enforced in `models/tariff_model.py`: `de` required, `fr`/`it` Optional).
- **Documentation style (owner law, 13 Jun): no em-dashes in any documentation or report text.** Use commas, colons, periods or parentheses; rewrite the sentence rather than substituting a hyphen.
- Any new non-chapter page added to `nav` in `docs/mkdocs.yml` MUST also be added to the enumerate-headings `exclude` list in the same change, or it silently shifts every arc42 chapter number. Verify with the `--strict` build.
- Console scope guards (ADR-013): the master-detail + review form + explain panel surfaces plus a coding-check page, over server-side BFF routes, no auth, no patient data, no benchmarking. Reject scope creep in review.
- **No Java, no JVM, anywhere: owner's decision, final.** The stack is Python + TypeScript (console) only. Never propose Quarkus/Java components for any reason.
- A merged change that decides something architectural → 5-line ADR in `docs/adr/` (register numbering, never legacy).
- Skill conventions: `docs/agents/issue-tracker.md` (issue tracker and labels) and `docs/agents/domain.md` (vocabulary and ADRs) are authoritative for the skills in `.claude/skills/`; read the relevant one before running a skill.

## Definition of done (all agents, any harness)

Run the checks that apply before calling any work finished; report each result honestly (failing test = say so with output; skipped step = say so and why):

1. Per touched service: `cd services/<svc> && uv run --no-sync pytest -q` green (offline).
2. `uvx ruff check .` inside each touched service dir, clean (never `ruff format .`, see Commands).
3. If `docs/` changed: `mkdocs build -f docs/mkdocs.yml --strict` green AND `python3 tools/cas_check.py --ci` green (ratchet). If `apps/tarifguard/` changed: `npm run lint && npm run build && npm test` (all three are CI gates).
4. `git diff --name-only main...HEAD` and `git status --porcelain` contain no freeze-line path (see The one inviolable rule).
5. Review the full diff. Any `services/` diff: check the determinism boundary (checklist in `.claude/agents/determinism-auditor.md`). A diff touching secrets, input parsing, the de-identification seam or anything internet-facing: security review (focus list in `.claude/agents/security-reviewer.md`). An independent review by a second model family when it adds value (from Claude: Codex, read-only commands in `.claude/agents/codex-reviewer.md`). Claude does them inline by default and runs them as the agents in `.claude/agents/` only when Erhan has authorized delegation for the task (CLAUDE.md); other harnesses do them inline and say which they skipped.
6. Report: changed files, the checks actually run with their results, anything skipped and why.
7. Commit, push, PR and merge only on Erhan's explicit request; a merged architectural decision gets an ADR (both in Conventions).
8. A prompt ending in "then /ship" means the steps in `.claude/skills/ship/SKILL.md` (any harness can follow the file): confirm scope, run checks, review, PR and CI only on explicit request, report.

Reusing results: a check result already obtained may stand in for a re-run only while its tested content, the relevant configuration, dependencies and environment, and its coverage all still apply; name each reused result and why it still applies. Re-run the affected checks after a relevant change, a failure or an unresolved concern. Reuse never waives a required check: CI must pass on the latest pushed revision before any merge, and the determinism-boundary check and any required security review must cover the diff as it will land. Postgres legs run only against a disposable database (`TARIFHUB_PG_TEST_URL` under Environment).
