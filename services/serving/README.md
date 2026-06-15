# tarifhub Serving (L1 TarifCore)

Deterministic, **read-only** REST API over frozen Swiss ambulatory tariff records.
Python 3.12 + FastAPI + Pydantic v2. Every value returned is an unaltered, frozen,
versioned record read straight from the system of record — **no AI on the value path**.

## The inviolable rule

No AI computes or mutates a billing value at serve time. The only AI-adjacent seam is
semantic search, which uses an embedder to *rank* frozen rows by similarity — it never
computes, alters, or fabricates a value. No LLM client is importable anywhere in the
`tarifhub_serving` package; `tests/test_serving_boundary.py` enforces this with an AST
scan, and only `models` and `embeddings` are imported from the ingestion package.

## Endpoints

| Method & path | Description |
| --- | --- |
| `GET /health` | Liveness probe → `{"status":"ok"}` |
| `GET /api/v1/tariffs?system=&limit=&offset=` | Latest version of each frozen record, optional system filter, paginated, deterministically ordered |
| `GET /api/v1/tariffs/{system}/{code}` | Latest frozen record for a key; `404` if absent |
| `GET /api/v1/search?q=&limit=` | Semantic search (Postgres+pgvector). On SQLite returns `501` — honest unavailability, no fake fallback |

OpenAPI/Swagger UI is served at `/docs`; the schema at `/openapi.json`.

## Config (env only)

- `TARIFHUB_DB_URL` — system of record. Default `sqlite:///./tarifhub_dev.db` (offline).
  Switch to Postgres with `postgresql://tarifhub:tarifhub@localhost:5432/tarifhub`.

## Run locally

```bash
cd services/serving
uv sync --extra dev
./../../scripts/run_serving.sh        # uvicorn dev reload on :8000, Swagger at /docs
```

## Test (offline by default)

```bash
cd services/serving
uv run pytest -q          # SQLite mirror + stub embedder, no network, no containers
uv run ruff check .
```

## Container

```bash
# Build from the repo root (the image vendors the sibling ingestion package).
docker build -f services/serving/Dockerfile -t tarifhub-serving .
docker run -p 8000:8000 -e TARIFHUB_DB_URL=postgresql://tarifhub:tarifhub@host.docker.internal:5432/tarifhub tarifhub-serving
```
