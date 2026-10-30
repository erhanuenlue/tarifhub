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
│                          manifest.py (dated BAG AL editions from data/manifests/),
│                          edition_comparison.py (read-only comparison of two AL editions)
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

## Compare two AL editions

```bash
TARIFHUB_DB_URL=sqlite:////tmp/al-demo.db \
  uv run --no-sync python -m tarifhub_ingest.cli --manifest ../../data/manifests/bag-al.json \
  --compare 2026-01-01 2026-07-01 > /tmp/al-2026-01-01_2026-07-01.json
```

`--compare FROM TO` compares two manifest editions as they are stored
([ADR-023](../../docs/adr/023-al-edition-comparison.md)). It is read-only: SQLite opens the
file in `mode=ro`, so a missing database is refused and never created, and Postgres runs
every transaction READ ONLY; nothing is imported, initialised, embedded or audited. A database
that exists without the schema (an empty SQLite file, a Postgres database without the tables)
is refused as well and left as it was; only the engine's own missing-table error becomes this
refusal, and any other database error propagates. Before comparing, it verifies both editions' documents against their SHA-256, parses their full
lists from the verified bytes and checks the stored rows by the import's own rules: every
position of each full list must be stored with that edition's date (a partly stored edition
is refused, so an unfinished import is never read as a removed position), each position's
edition member (its earliest stored version of that date) must match its row, no stored
position of that date may be missing from the file, and the stored history must be
consistent. A position number written two ways across the editions (`1000` and `1000.00`),
a value the canonical scale could not store exactly and an AI-filled value are refused too.
A refusal exits 2 and lists every problem on stderr.

The JSON lists the `added`, `removed`, `changed` and `unchanged` positions, sorted by code.
Each entry cites the `version` and `record_hash` of its edition member; later versions of the
same date, such as a review correction, are cited as `successor_versions` and never compared
in its place. A change gives the exact before and after value (decimals as the hash writes
them: `21.6`, `18`), and each edition lists its manifest documents. Only `compared_fields`
classify positions (`category`, the three designations, `price_chf`, `tax_points`, `unit`),
so `unchanged` means unchanged in those fields. `removed` means listed in the earlier
verified full list and absent from the later one; it is not a legal repeal, a deleted record
or a changed `as_of` result.

`workbook_text` compares, beside that classification, the published text of 24 German
columns the record does not carry ([ADR-024](../../docs/adr/024-al-workbook-text.md)), for
every position listed in both editions: `Limitationen`, `Bemerkungen` and `Kumulierbarkeit`
(columns I to K of the 2026 workbooks) and the 21 laboratory flags. Those are S to AB, under
the banner for the laboratories of Article 54 KVV (eight columns, each a type of laboratory
billing for its own needs or on external order, plus `Hausbesuch` and `Schnelle Analyse`),
and AC to AM, the eleven titles of the practice laboratories of physicians with specific
further-education titles. The prescriber flags `Hebammen` and `Chiropraktoren oder
Chiropraktorinnen` are not among them. The cells are read with their sheet, header and cell
references (4707.1's cumulability is `K1012` in January, `K1013` in July) from the same
bytes the comparison verified against the manifest, and formulas are read as formulas,
never as their cached values. Two texts are
equal when they match after Unicode NFC normalisation and whitespace folding
(`normalization`); any other difference is a change, shown verbatim, with `from_text` or
`to_text` null only for an empty cell. A change states what the cells say, not a changed
rule or entitlement (`interpretation: "none"`, so `Oui` to `Ja` is a change of text), and it
never moves a position out of `unchanged`; a position also listed under `changed` carries
`in_changed: true` and is listed once.

`coverage` is `complete` when every requested column was compared and `partial` when an
edition has a requested column missing, named by two headers or holding a value that is not
text (a formula, number, date, boolean or error). Such a column is compared in neither
edition: it is listed under `not_comparable` for each edition concerned, with the header
cells naming it or the cells holding the other values, and counted nowhere. With no column
compared, `coverage` is `unavailable` and `counts`, `cells_changed_by_column` and
`positions` are null, never a count of unchanged texts; the comparison still exits 0, since
the compared fields were compared. A position number written as a formula refuses the
comparison, even though the import reads the cell's cached value. Not compared at all: the
other columns the record does not carry (the prescriber flags and BAG's change dates among
them), the French and Italian sheets, the texts of added and removed positions, cell
formatting and the PDFs. `scope_limitation` names the columns compared as text and every
other workbook column the comparison does not see, so the result is still not the list of
every change BAG published.

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
