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
├─ main.py                 FastAPI app (GET /health, /tariffs, /tariffs/{code}; POST /ingest/sample); no LLM import
├─ config.py               12-factor settings (SQLite default; Postgres-ready)
├─ models/tariff_model.py  Canonical Pydantic model (LOCKED field set)
├─ ingestion/              pipeline.py (orchestration), source_loader.py (discover samples),
│                          manifest.py (dated BAG AL editions from data/manifests/)
├─ adapters/               bag_eal.py (EAL XLSX), bag_epl.py (ePL/SL FHIR R5, streamed + traversed)
├─ parsers/xlsx_parser.py  generic XLSX parsing into raw rows (EAL/SL specifics live in adapters/)
├─ mappers/tariff_mapper.py  rules-based map + replaceable ai_map() seam
├─ confidence/scorer.py    deterministic confidence in [0,1]
├─ validators/tariff_validator.py  pre-freeze validation
├─ versioning/freeze_record.py  PROTECTED: deterministic freeze + hash
├─ audit/audit_logger.py   PROTECTED: append-only lineage log
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

## Import dated BAG AL editions (manifest)

`data/manifests/bag-al.json` (tracked) lists each Analysenliste edition under its effective
date, with every downloaded document's repository path, SHA-256 and BAG download URL. Only
an edition's `full_list_xlsx` enters the pipeline; the PDFs are supporting sources.

```bash
TARIFHUB_DB_URL=sqlite:////tmp/al-demo.db \
  uv run --no-sync python -m tarifhub_ingest.cli --manifest ../../data/manifests/bag-al.json
```

Before the first write the importer checks the manifest schema, verifies every listed
document (inside the repository, present, matching its SHA-256), parses each tariff list
from the very bytes it verified, and compares the batch with the stored EAL rows. Editions
then import oldest first, with `valid_from` and `source_version` (`BAG AL YYYY-MM-DD`) taken
from the manifest, so a record's identity never depends on the file's name or location.
Positions already stored with the same content are skipped, so a re-run is idempotent and
an interrupted run resumes; reviewed corrections stay current. An unsafe batch (a hash
mismatch, an older edition after a newer one, undated or conflicting EAL rows) exits 2,
lists every problem, and writes no tariff or audit row. The import itself is one
transaction, whether it runs from the CLI or from a direct `import_manifest(path, conn, db)`
call: a failure part way, or another writer changing the stored editions during the run,
rolls the whole batch back. Against Postgres the run needs the e5 embedder
(`TARIFHUB_EMBEDDINGS=e5`), since the `vector(1024)` column rejects the 16-dim offline stub;
`deploy/docker-compose.verify.yml` runs it in containers against a throwaway Postgres.
Manifest paths are NFC, and each path component is matched on disk by its NFC form, the
same way on every file system: the two July 2026 PDFs that macOS saved with NFD names are
found on a Linux disk too, and two files whose names differ only in normalisation are
refused as ambiguous. Matching is otherwise exact, so case must match on macOS as well.

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
