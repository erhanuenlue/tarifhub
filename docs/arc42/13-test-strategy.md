# 13 · test strategy

How TarifHub is tested, as actually implemented. The strategy serves one architectural
promise above all: **no AI computes or mutates a billing value at serve time**, and a
served value is provably the value that was reviewed and frozen. The tests are therefore
arranged as a pyramid whose apex is not a UI click-test but an *architectural* AST guard,
and whose foundation is an offline-by-default contract suite that needs no network, no
container and no API key. The per-use-case acceptance criteria these tests satisfy are in
[§10](10-quality-requirements.md#acceptance-criteria).

> **No AI computes or mutates a billing value at serve time.**

## The test pyramid

From the broad, fast base to the narrow, high-leverage apex:

1. **Unit / mapping helpers.** Pure functions — `freeze` (hash over sorted canonical
   content), the deterministic `map_raw`, validators, the confidence scorer, the
   canonical-Decimal scale normalisation — are tested in isolation with fixed inputs.
   No I/O, no clock branching, no randomness; the pipeline is a pure function of sorted
   inputs by design ([§6](06-runtime-view.md)).
2. **API contract (offline).** The serving REST surface is exercised through FastAPI's
   `TestClient` against a temp SQLite database seeded with frozen records
   (`services/serving/tests/test_api.py`, `conftest.py`): health, latest-version list,
   system filter, pagination edges, 404 on unknown keys, input-validation 422s, and the
   search ranking and dimension-guard paths. The client reads the seeded DB via `TARIFHUB_DB_URL`
   — the same env-only config production uses.
3. **Cross-engine read parity.** Every read endpoint is run against **both** SQLite and
   Postgres via the `engine` fixture, and each test asserts the endpoint's **full JSON
   body** equals an engine-independent expected snapshot
   (`services/serving/tests/test_read_parity.py`, mirrored for ingestion). Because both
   engines must match the *same* snapshot, they match each other — SQLite-only blindness
   becomes impossible to pass silently. This layer exists because Block-0 was burned twice
   by Postgres-vs-SQLite drift (a JSONB dict crashed `json.loads`; an `int` for a BOOLEAN
   column was rejected by psycopg), so the snapshots deliberately stress non-ASCII
   designations (ü, é, ç), nested metadata dicts, `requires_review` booleans,
   trailing-zero Decimals at the exact `NUMERIC` scale, dates, multi-version keys and
   pagination windows.
4. **MCP proxy contract.** The MCP tools (`get_tariff`, `search_tariffs`,
   `explain_crosswalk`) are tested with the serving backend mocked via
   `httpx.MockTransport` (`services/mcp/tests/test_tools.py`): each tool returns the
   backend JSON **verbatim**, forwards the right path and query params, and a backend 404
   raises `httpx.HTTPStatusError` rather than fabricating a record. **MCP↔serving
   integration tests** (`services/mcp/tests/test_integration.py`) additionally drive the
   real serving ASGI app in-process via `httpx.ASGITransport` — each tool proven against
   real responses under the same offline doctrine (SQLite mirror, stub embedder), no
   socket.
5. **Architectural AST boundary test (the apex).** A static AST scan asserts no LLM client
   is importable on the value path. This is the mechanical enforcement of the inviolable
   rule and is described as its own gate below.

## Offline by default

`uv run pytest -q` in any service runs **fully offline**: a **SQLite mirror** of the
canonical Postgres schema stands in for the database, and a deterministic **16-dim
`HashingEmbedder` stub** stands in for multilingual-e5 — **zero network, no containers,
no `ANTHROPIC_API_KEY`**. Without an API key the AI seam (`ai_map`) falls back to
deterministic `map_raw`, and the offline tests rely on exactly that fallback. Semantic
search stays fully testable offline: on SQLite the serving layer ranks by an in-process
deterministic cosine over the stored stub embeddings (same query path, same response
shape as pgvector — ties broken by `(tariff_system, tariff_code)`), so the offline suite
exercises real ranked results without pgvector. The dimension-guard still applies on
Postgres: an embedder whose dimension does not match the `vector(1024)` column makes
search **fail closed with HTTP 501** rather than issue a doomed query — honest
unavailability, never a faked result.

## Postgres opt-in parity harness

The real engine is opt-in. Setting `TARIFHUB_PG_TEST_URL` adds a `postgres` parameter to
the `engine` fixture; its setup connects to that server **only** to `CREATE` a
uniquely-named scratch database (`tarifhub_parity_<uuid>`), applies `db/schema.sql` into
it, yields it to the test, and **drops it on teardown** — the shared dev `tarifhub`
database is never written to. This is our **purpose-built equivalent of Testcontainers**
— a per-run, throwaway, schema-provisioned database with deterministic teardown — built
directly on `psycopg` and `db/schema.sql`. **We do not use Testcontainers**; the harness
is hand-rolled to keep the offline default container-free and the dependency surface
minimal. In CI the `python-parity` job supplies the URL via a `pgvector/pgvector:pg16`
service container, so the identical read tests run against a real Postgres 16 + pgvector
on every push and PR.

## The determinism acceptance gate (AST boundary test)

The architectural guard is the apex test and the determinism acceptance from
[§10](10-quality-requirements.md#acceptance-criteria). It parses each value-path module's
AST and asserts that none imports `anthropic`, `openai`, `cohere`, `langchain` or
`llama_index` — module level **or** inside a function:

- `services/serving/tests/test_serving_boundary.py` scans the **entire** `tarifhub_serving`
  package, and additionally asserts the only `tarifhub_ingest` submodules it imports are
  `models` and `embeddings` — never a mapper that could transitively pull an LLM client.
  (It is named `test_serving_boundary`, not `test_determinism_boundary`, because the latter
  filename is frozen by the `guard_frozen` hook.)
- `services/ingestion/tests/test_determinism_boundary.py` scans the ingestion value path
  (`main.py`, `storage/db.py`, `storage/tariff_repository.py`).
- `services/intelligence/tests/test_determinism_boundary.py` scans the TarifIQ rule-
  evaluation path (`main.py`, rules, crosswalk, validators, store).

These run in the offline suite and again, **visibly**, as a dedicated CI step that prints
the boundary tests with `-v`; CI fails if any LLM client appears on a value path. Because
the guarantee is structural (the import graph cannot reach a model), the boundary stays
green by construction, not by reviewer discipline.

## What CI runs per PR

From `.github/workflows/ci.yml`, on every push to `main` and every pull request:

| Job | What it does |
|---|---|
| `python` | Per service: `uv sync --frozen` → `uvx ruff check .` → `uv run pytest -q` (offline). Then a dedicated step re-runs the ingestion + serving boundary tests with `-v` so the determinism gate is visible in the log. |
| `python-parity` | Spins a `pgvector/pgvector:pg16` service container and runs the ingestion + serving read-parity suites against real Postgres 16 + pgvector (`TARIFHUB_PG_TEST_URL` set). |
| `console` | When `apps/tarifguard/package.json` exists: `npm ci` → `npm run lint` → `npm run build` → `npm run test --if-present`. |
| `security` | `gitleaks` (secrets) → `Trivy` (fs scan, fail on HIGH/CRITICAL) → `Syft` SBOM (`spdx-json`, uploaded as an artifact). |
| `docs` | `mkdocs build -f docs/mkdocs.yml --strict` — a broken link or nav entry fails the build. |
| `images` | On `main` only, after `python` + `security`: builds every sub-system Docker image (criterion 17 distribution evidence). |

Lockfiles are committed and CI never re-resolves (`UV_FROZEN=1`, owner decision).

## Coverage

Target: **core modules (model, freeze, pipeline, mapper) > 80 % line coverage**
([§10](10-quality-requirements.md)). Measured 2026-06-12 (offline suite, `pytest-cov`,
line coverage; re-measured on every CI run in the `python` job's coverage step):

| Service | Core modules in scope | Measured |
|---|---|---|
| `services/serving` | `main` 100 %, `repository` 90 %, `models` 100 % (also `fhir` 99 %, `explain` 100 %) | **95 % total** |
| `services/ingestion` | `tariff_model` 100 %, `freeze_record` 92 %, `pipeline` 100 %, `tariff_mapper` 92 % | **89 % total** |
| `services/mcp` | proxy tools (`server` 86 %, `config` 100 %) | **91 % total** |

Every core module is above the 80 % target. The figures are evidence, not a gate: CI
prints them on every run (report-only by owner decision at gate 01); a hard
`--cov-fail-under` floor is deliberately deferred until the figures have a few weeks of
history.

## Console component tests

The TarifGuard console currently has lint, build and typecheck wired in CI; it ships **no
automated component or Playwright smoke test yet** (`apps/tarifguard/package.json` defines
no `test` script, so the CI `console` job's `npm run test --if-present` is a no-op today).
Component tests are **planned**: they will assert the brand visual law — frozen values
render in navy mono with version + truncated `record_hash` provenance chips, and every AI
output renders inside its `.ai-content` "AI-generated — not a billing value" label, never
restyled as a frozen value (ADR-013 scope). Until then the console is covered by the
serving API contract tests it consumes plus manual smoke captured into `docs/evidence/`.
