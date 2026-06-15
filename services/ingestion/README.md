# tarifhub-ingest

Pre-freeze, AI-assisted harmonization pipeline + admin/read API for tarifhub. Runs
fully offline (SQLite, no network, no live LLM) so the suite is reproducible anywhere.

## Pipeline

`load → parse → map → validate → score → flag → freeze → store → audit`, deterministic
end to end. AI may assist only at `map` (via `mappers/tariff_mapper.py::ai_map`, pre-freeze,
non-billing fields) and never touches `tax_points` / `price_chf`. After `freeze`, the
record is an immutable, SHA-256-hashed, versioned fact.

## Layout

```
src/tarifhub_ingest/
├─ main.py                 FastAPI app (GET /health, /tariffs, /tariffs/{code}; POST /ingest/sample) — no LLM import
├─ config.py               12-factor settings (SQLite default; Postgres-ready)
├─ models/tariff_model.py  Canonical Pydantic model (LOCKED field set)
├─ ingestion/              pipeline.py (orchestration), source_loader.py (discover samples)
├─ parsers/                xlsx_parser.py (EAL), fhir_parser.py (ePL)
├─ mappers/tariff_mapper.py  rules-based map + replaceable ai_map() seam
├─ confidence/scorer.py    deterministic confidence in [0,1]
├─ validators/tariff_validator.py  pre-freeze validation
├─ versioning/freeze_record.py  PROTECTED — deterministic freeze + hash
├─ audit/audit_logger.py   PROTECTED — append-only lineage log
├─ embeddings/embedder.py  Embedder port + offline hashing stub (e5 in prod)
└─ storage/                db.py (SQLite/Postgres), tariff_repository.py
```

## Develop

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"     # add the dev extra for ruff
pytest -q
ruff check .

# Run the API
tarifhub-ingest             # uvicorn tarifhub_ingest.main:app on :8000
```

## Configuration (env)

| Var | Default | Meaning |
|---|---|---|
| `TARIFHUB_DB_URL` | `sqlite:///./tarifhub_dev.db` | SQLite (offline) or `postgresql://…` |
| `TARIFHUB_REVIEW_THRESHOLD` | `0.85` | Confidence below this flags `requires_review` |
| `TARIFHUB_EMBEDDINGS` | `stub` | `stub` (offline) or `e5` (needs the `ai` extra) |
| `TARIFHUB_SAMPLE_DIR` | bundled | Override the sample source directory |
| `ANTHROPIC_API_KEY` | _unset_ | The ONLY switch that enables the live Claude harmonizer (pre-freeze) |

The optional `ai` extra (anthropic, sentence-transformers) is import-guarded and never
required for tests.
