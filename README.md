# TarifHub

TarifHub is a Swiss ambulatory tariff data platform. It harmonises tariff sources once with AI assistance above a deterministic freeze line, then serves immutable, versioned records through a read-only API below it, with a thin demo console on top. It is the capstone project for the FFHS CAS (due 6 July 2026) and the seed of a commercial platform, on one codebase.

## The one inviolable rule

**No AI computes or mutates a billing value at serve time.** AI runs only pre-freeze (filling non-billing fields with schema-constrained structured output) and in explain/search seams that never alter a value. Frozen records are immutable: a SHA-256 `record_hash` over sorted canonical content, updates are new versions, and the audit log is append-only. A determinism boundary test (no LLM client is importable on the value path) keeps CI honest.

## Architecture

Four layers, decoupled by the freeze line:

| Layer | What | Where |
|-------|------|-------|
| L0 ingestion | AI-assisted harmonisation: load, parse, map, validate, score, flag, freeze | `services/ingestion/` |
| L1 serving (TarifCore) | Deterministic read API: REST + FHIR R4, point-in-time + diff, semantic search | `services/serving/` |
| L1 MCP (TarifMCP) | Read-only tools (`search_tariffs`, `get_tariff`, `explain_crosswalk`) for AI agents | `services/mcp/` |
| L3 console (TarifGuard) | Master-detail search, frozen-record detail, human review form, labelled AI explain panel | `apps/tarifguard/` |

The database (`db/`, PostgreSQL 16 + pgvector, mirrored in SQLite for offline tests) is the only contract between L0 and L1. Deployment manifests (Docker Compose, Helm) live in `deploy/`.

## Quick start (offline)

The Python services run fully offline by default: a SQLite mirror plus a deterministic stub embedder, no containers, no network, no API key required.

```bash
# Per service: install and run the test suite
cd services/serving && uv sync && uv run pytest -q
cd ../ingestion    && uv sync && uv run pytest -q
cd ../mcp          && uv sync && uv run pytest -q
cd ../intelligence && uv sync && uv run pytest -q

# The demo console (needs a running serving API; the offline smoke is self-contained)
cd apps/tarifguard && npm install && npm test       # Vitest + offline Playwright smoke
npm run dev                                          # http://localhost:3000

# The documentation site
mkdocs serve -f docs/mkdocs.yml                      # http://localhost:8000
```

`uv` is the package manager (not pip or poetry). To run against the real Postgres engine instead of the SQLite mirror, `docker compose -f deploy/docker-compose.yml up -d db` and set `TARIFHUB_DB_URL`.

## Configuration

Config is environment-only. Copy the example and fill in your own values:

```bash
cp .env.example .env
```

| Variable | Purpose |
|----------|---------|
| `TARIFHUB_DB_URL` | Database URL. Defaults to a local SQLite mirror used by the offline tests. |
| `TARIFHUB_REVIEW_THRESHOLD` | Confidence below which a record is flagged for human review (default `0.85`). |
| `ANTHROPIC_API_KEY` | Enables the pre-freeze `ai_map` seam. Absent, ingestion falls back to the deterministic `map_raw` mapper (the tests rely on this fallback). |
| `TARIFHUB_EMBEDDINGS` | `stub` (offline default) or `e5` (multilingual-e5, for real semantic search). |
| `TARIFHUB_SAMPLE_DIR`, `TARIFHUB_AI_MODEL` | Optional overrides for the bundled sample sources and the harmoniser model id. |
| `SERVING_BASE_URL` | Console and MCP: base URL of the serving API. Server-side only, never exposed to the browser. |
| `INGEST_BASE_URL` | Console (optional): the ingestion review endpoint for the review form. Unset, the console serves its demo fixtures. |

No real secret is committed anywhere in this repository; `.env*` files are git-ignored (only `.env.example` is tracked).

## Documentation

The architecture is documented as an arc42 site (MkDocs Material) under `docs/`, published to GitHub Pages from `.github/workflows/docs.yml` (live once the owner enables Pages, at `https://erhanuenlue.github.io/tarifhub/`). Architecture decisions are recorded in `docs/adr/`.

## CAS scope (be honest)

Graders review code and documentation only; nothing is deployed or executed by them, so runtime evidence is captured into `docs/`. The TarifGuard console is a deliberately small demo (master-detail, review form, explain panel): no authentication, no patient data, no benchmarking. The platform demonstrates the concepts; it is not a production billing system.

## Stack

Python 3.12 + FastAPI + Pydantic v2 (one canonical `TariffRecord` end to end), PostgreSQL 16 + pgvector, Claude schema-constrained structured output (pre-freeze only), Next.js App Router (the console), Docker + Helm, GitHub Actions (ruff, pytest, gitleaks, Trivy, Syft).

## Development

Contributors should read `AGENTS.md` (project facts, layout, commands, the determinism rule) and `CLAUDE.md` (the working pipeline), then `SETUP.md` / `QUICKSTART.md` for one-time machine setup.

## License

MIT. See [LICENSE](LICENSE).
