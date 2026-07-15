# tarifhub: Project Facts (read first)

Swiss ambulatory tariff data platform. Four layers: L0 harmonisation (AI-assisted, pre-freeze) → L1 deterministic serving API + MCP → L2 rules (TarifIQ skeleton in-repo; graded scope stays L0/L1 + console) → L3 apps (demo now).

**Status: the CAS capstone was submitted 3 July 2026 (tip 530f850); the graded deliverable was the public repo https://github.com/erhanuenlue/tarifhub plus the GitHub Pages docs site. The project is now in product-build mode (owner decision, 15 Jul 2026): git is fully autonomous on all paths through the normal pipeline (branch → PR → reviews → squash-merge green; /ship gates unchanged), no special approval for touching pre-submission files. Two things stay protected: never rewrite pre-submission history, and never backfill or edit past vault/ journal entries (contemporaneity is the point).** Grading strategy lives in Erhan's corpus (CAS Dossier v3.1, owner-held, not in the repo). The in-repo grading authority is the git-ignored local copy under `docs/cas/` (bewertungskriterien-anker.md + grading-anchors-operative.md); consult those when a criterion's exact conditions matter, and ask Erhan only if they are missing locally.

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
                         001..020 + legacy/) + method/ (AI-tools chapter) + evidence/ + criterion-map.md
tools/                   cas_check.py (CI ratchet) + curate.sh + switch_model.sh + loop.sh +
                         shipboard/ (the :8787 board) + hooks/ (git-hook installer) + bench/search_latency.py
                         + search_eval/ (latency + quality harnesses: use these for any search
                         performance question before hand-rolling measurement)
vault/                   CAS evidence: daily/ journal, decision-matrix.md, fazit-notes.md
```

## Stack

Python 3.12 + FastAPI + Pydantic v2 (one canonical `TariffRecord` end-to-end) · PostgreSQL 16 + pgvector (HNSW, cosine; multilingual-e5-large 1024-dim) · Claude schema-constrained structured output (pre-freeze only) · Next.js App Router (demo) · Docker + Helm/k3d · GitHub Actions (ruff, pytest, gitleaks, Trivy, Syft SBOM, CI image builds, GHCR push decided but not yet wired, ADR-010; docs.yml builds the Pages site on any docs/** push to main and publishes when the DEPLOY_PAGES=true repo variable is set; it also offers workflow_dispatch) · OpenTelemetry instrumented in serving (FastAPI request traces + a custom search span and duration histogram; OTLP export opt-in via `OTEL_EXPORTER_OTLP_ENDPOINT`, a true no-op when unset; ADR-011), with Prometheus/Grafana + Sentry as intended backends, not yet wired.

ADR register: `docs/adr/` 001..020, three-digit numbering (ADR-001 Python-first, ADR-013 demo scope, ADR-020 Codex seat). `docs/adr/legacy/` preserves the pre-2026-06-11 register under DIFFERENT, colliding numbers: never cite a legacy number in new text; resolve old citations via `docs/adr/legacy/README.md`.

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
docker compose up -d db                  # Postgres+pgvector; the PG test legs stay SKIPPED until you also
                                         # export TARIFHUB_PG_TEST_URL=postgresql://tarifhub:tarifhub@localhost:5432/tarifhub
cd apps/tarifguard && npm install && npm run dev
                                         # console on :3000 (fresh clone: npm install once); npm test = Vitest +
                                         # Playwright smoke. CI additionally gates npm run lint AND npm run build
                                         # (Playwright browsers: npx playwright install --with-deps chromium, once)
python3 tools/shipboard/shipboard.py     # live /ship pipeline board on 127.0.0.1:8787 (--demo seeds, --reset clears)
bash tools/hooks/install.sh              # fresh clone only: git hooks are not versioned; installs them
                                         # (verify .git/hooks/post-commit exists; graphify code-node sync needs it)
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
- `TARIFHUB_PG_TEST_URL`: unset = the Postgres parity/integration test legs skip silently; set it to enable them.
- `ANTHROPIC_API_KEY`: unset = `ai_map` returns the deterministic `map_raw` result (`mappers/tariff_mapper.py`); the offline tests rely on this fallback.
- `OTEL_EXPORTER_OTLP_ENDPOINT`: opt-in serving telemetry; unset = true no-op.
- `SERVING_BASE_URL`: L1 base URL for the console BFF (REQUIRED there, `apps/tarifguard/lib/api.ts` throws without it), MCP and TarifIQ (default `http://localhost:8000` for those two). TarifIQ also accepts `TARIFIQ_SERVING_BASE_URL`, which takes precedence.
- `INGEST_BASE_URL`: console review proxy target (ingestion review API); unset = the console serves a bundled demo queue and review decisions are NOT persisted.
- `TARIFIQ_OFFLINE`: default true (bundled frozen tables, hermetic tests); truthy values are 1/true/yes/on. Set `0` plus a reachable `SERVING_BASE_URL` to read live frozen records.

All `.env*` files are read-denied to AI everywhere, and root-level `.env*` writes are denied (`.claude/settings.json`; includes `.env.example`): no AI, in any harness, reads or writes a `.env*` file. When a `.env*` change is needed, hand Erhan the exact command to run himself; AI may then stage and commit the result on his behalf. For live runs load secrets with `uv run --env-file ../../.env ...` from the service dir; assert presence only, never print key material.

## Conventions

- **Grounding: never speculate about code you have not opened. If a file is referenced, read it before answering or editing. A claim must trace to a tool result from this session.**
- **Long runs: context auto-compacts as it fills, so do not stop early for token-budget reasons. As you approach the limit, save progress and state to a scratchpad (`.shipboard/loop-checkpoint.md` in loop runs) before the window refreshes, then continue.**
- **Quality before cost (owner law, 13 Jun): the orchestrator seat is pinned once in `.claude/settings.json` "model" and switched only with `tools/switch_model.sh` (ADR-018; check the file, do not assume which model). Every seat that exercises judgment or writes anything runs Opus-class or better; Sonnet and Haiku are banned from every seat. Worker pins live in `.claude/agents/*.md` frontmatter (exact model ids, not floating aliases, + `effort: ultracode`; the one deliberate exception is verifier's `model: inherit`); treat frontmatter as the pin, never override it, never switch models mid-task (caches are model-scoped). The independent second model family is OpenAI Codex (gpt-5.6-sol via the owner's Codex Pro login, ADR-020): every PR review, the final document review, journal curation, and a second opinion on each grade estimate. Never downgrade a model seat, an effort level or a review step to save tokens. Cost is reported on the board; it is never an argument. Non-Claude agents: never modify `.claude/settings.json` or `.claude/agents/*`; run your own harness at its strongest available model/reasoning and state which Claude worker steps you could not perform.**
- Conventional Commits; branch `feat/…|fix/…`; squash-merge green PRs only. Commit SHAs cited in graded evidence (docs/, vault/, LEARNINGS.md) must be squash-merge SHAs: verify with `git merge-base --is-ancestor <sha> main` before citing; pre-squash branch commits are unreachable from main.
- GitHub skips Actions when `[skip ci]`/`[ci skip]` appears ANYWHERE in the head commit message (title or body): never quote the bracketed token in a CI re-trigger commit. `ci.yml` has no `workflow_dispatch`. The SessionEnd hook auto-pushes a `[skip ci]` vault commit, so a trailing vault tip after session end is expected; the rule binds pushes YOU make: land content via squash-merged PRs, never end an in-session push sequence on a `[skip ci]` commit, and when a green public HEAD matters (release, grading link) tell Erhan rather than force-pushing (denied).
- The canonical model's field set is **locked, additive-only** (ADR-003). A breaking change needs a new ADR before code. Any NEW content field must also enter `HASHED_FIELDS` in `versioning/freeze_record.py`, which is below the freeze line: a canonical-field addition is therefore ALWAYS a frozen-path change. Flag it to Erhan at plan time; never ship a content field absent from the hash tuple (records differing only in that field would collide as unchanged content).
- German is the canonical designation language; FR/IT optional (enforced in `models/tariff_model.py`: `de` required, `fr`/`it` Optional).
- **Documentation style (owner law, 13 Jun): no em-dashes in any documentation or report text.** Use commas, colons, periods or parentheses; rewrite the sentence rather than substituting a hyphen.
- Any new non-chapter page added to `nav` in `docs/mkdocs.yml` MUST also be added to the enumerate-headings `exclude` list in the same change, or it silently shifts every arc42 chapter number. Verify with the `--strict` build.
- Console scope guards (ADR-013): the master-detail + review form + explain panel surfaces plus a coding-check page, over server-side BFF routes, no auth, no patient data, no benchmarking. Reject scope creep in review.
- **Graders review code and documentation only; nothing gets deployed or executed by them.** Evidence that exists only at runtime must be captured into `docs/` (screenshots, CI links, coverage figures, report tables). Distribution (criterion 17) is proven by Dockerfiles/compose/Helm + CI builds + captured screenshots, not by a live cluster.
- **No Java, no JVM, anywhere: owner's decision, final.** The stack is Python + TypeScript (console) only; the operative rubric copy in `docs/cas/` contains no Java-specific criteria. The docs keep a "Modern application concepts" page (arc42 §8: DI, validation, persistence abstraction, observability, container-first, as implemented in Python, citing Modulplan Lehrmittel [5]). Never propose Quarkus/Java components for any reason, including rubric optics.
- A merged change that decides something architectural → 5-line ADR in `docs/adr/` (register numbering, never legacy). A working session → journal entry in `vault/daily/` (the SessionEnd hook drafts it; `bash tools/curate.sh` rewrites it via Codex (the CLI default model, gpt-5.6-sol since ADR-020) and appends fazit-note candidates; automated inside `tools/loop.sh` runs, run it manually in interactive sessions; the pipeline is disclosed in the AI-tools chapter; the owner edits at his discretion, the vault remains graded CAS evidence). Non-Claude sessions have no SessionEnd hook: create or update `vault/daily/YYYY-MM-DD.md` yourself (template in `.claude/hooks/journal_draft.sh`), then run `bash tools/curate.sh YYYY-MM-DD`; if you cannot write or commit it, say so explicitly.

## Definition of done (all agents, any harness)

Run these before calling any work finished; report each result honestly (failing test = say so with output; skipped step = say so):

1. Per touched service: `cd services/<svc> && uv run --no-sync pytest -q` green (offline).
2. `uvx ruff check .` inside each touched service dir, clean (never `ruff format .`, see Commands).
3. If `docs/` changed: `mkdocs build -f docs/mkdocs.yml --strict` green AND `python3 tools/cas_check.py --ci` green (ratchet). If `apps/tarifguard/` changed: `npm run lint && npm run build && npm test` (all three are CI gates).
4. `git diff --name-only main...HEAD` and `git status --porcelain` contain no freeze-line path (see The one inviolable rule).
5. Reviews per the routing matrix: determinism-auditor for any `services/` diff, security-reviewer when the diff touches secrets, input parsing, the de-identification seam, or anything internet-facing, codex-reviewer for every PR. The Claude harness dispatches the agents in `.claude/agents/`; other harnesses perform the equivalent reviews themselves and state which seats were unavailable.
6. PR squash-merged green only. Architectural decision made → 5-line ADR in `docs/adr/` (register numbering, never legacy).
7. Journal entry in `vault/daily/` curated (see Conventions, last bullet).
8. A task ending with "then /ship" means the 9-phase pipeline in `.claude/skills/ship/SKILL.md` (follow the file manually if your harness lacks Claude skills). Gate 01, Erhan's plan approval, is a hard human stop. Phase 09 auto-merges ONLY under its green-contract (ALL FOUR: CI fully green incl. the security job, every finding dispositioned, no unauthorized frozen-path change, working tree clean AND branch current with `main`); anything less stops for Erhan.
