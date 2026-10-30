# BAG AL edition comparison: local verification

Verification record for the read-only comparison of the BAG Analysenliste editions of
1 January and 1 July 2026 ([ADR-023](../adr/023-al-edition-comparison.md)). Captured on
2026-10-30 on the macOS host (Apple Silicon, Python 3.13.12 in the service environments),
against SQLite and a disposable Postgres 16 container: no API key, no external network.

## Tested revision

The working tree on top of `6cc68da` (branch `feat/al-edition-comparison`), including the
fix that refuses a database without the schema; it was committed for review after these
runs. These are local results: the CI runs of the pushed revision are recorded in its pull
request, not here. The files under test, by git blob ID:

| Blob | File |
|---|---|
| `1ba35b36fdb3` | `services/ingestion/src/tarifhub_ingest/ingestion/edition_comparison.py` |
| `81ef3fa2f059` | `services/ingestion/src/tarifhub_ingest/ingestion/manifest.py` |
| `87496458a1a2` | `services/ingestion/src/tarifhub_ingest/cli.py` |
| `179328d472ae` | `services/ingestion/src/tarifhub_ingest/storage/db.py` |
| `ae1b62dbae7d` | `services/ingestion/src/tarifhub_ingest/adapters/bag_eal.py` |
| `93d492fc1c2f` | `services/ingestion/tests/test_edition_comparison.py` |
| `37a1d2224ca4` | `services/ingestion/tests/_parity.py` |
| `faadb9735fad` | `services/ingestion/tests/conftest.py` |
| `5ea6ae6aa605` | `.github/workflows/ci.yml` |
| `ce2bfb20a85f` | `data/manifests/bag-al.json` (unchanged) |

## Expectation (planning analysis, 2026-10-29)

Before any code existed, the planning analysis parsed both hash-checked workbooks through the
import's own verify, parse and map path and expected, within the compared fields: 1 added
position (`1779`, 73.3 TP), 0 removed, 12 changed, all in `tax_points`, and 1267 unchanged.
The twelve, with TP before and after: 1006 47.7 to 38.2, 1245 9 to 8.1, 1314 7.1 to 6.4,
1368 59.4 to 64.4, 1374 13.1 to 11.8, 1446.1 32.4 to 29.2, 1718.1 8.1 to 7.3, 1727.1 54.9 to
43.9, 1749 22.5 to 18, 3333 99 to 89.1, 3396 47.7 to 42.9, 4700 21.6 to 16.6. They are the
changes in the compared fields, not every change the two BAG publications contain (see the
analysis below).

## Results

### Real editions on a disposable SQLite database

| Step | Result |
|---|---|
| Import of both editions (CLI, offline stub embedder, no key) | exit 0; January 1279 and July 1280 positions frozen, 0 flagged, 0 parse failures |
| Comparison, run in two separate processes | exit 0 both times, empty stderr; 33 106 bytes of JSON, SHA-256 `3ff429ef6ea495a982bb6d47dbacc302d4dff058d9aadb1f79a94671f0564dbb` both times, byte-identical, and the same SHA-256 as this record's first capture, before the missing-schema fix |
| SHA-256 of the database file before and after both comparisons | identical, `073337b7dbf41665c4189c7fb1443c506bdb00ad27ce24440580c7d0ab06ff9e` (a fresh file, whose rows carry their own `created_at`) |
| Counts within `compared_fields` | added 1, removed 0, changed 12, unchanged 1267, as expected |
| Changed positions | exactly the twelve codes above, each with one change, in `tax_points`, with the planned values |
| Independent check against the raw German-sheet cells (plain openpyxl, no tarifhub code) | every reported TP before and after equals its cell; `1779`'s TP and German designation equal the July cells; every position of each edition appears exactly once. Run on the first capture; it still applies, since the JSON and the hash-pinned workbooks are byte-identical |
| Scope limitation | 33 German-sheet columns named as not compared, among them `Limitationen`, `Bemerkungen`, `Kumulierbarkeit` and the laboratory columns; the 7 discipline columns named as compared only through `category` |
| Comparison against a missing database | exit 2, empty stdout, "the database cannot be opened read-only (OperationalError)"; the file was not created |
| Comparison against an existing database without the schema (an empty file) | exit 2, empty stdout, "the database lacks the required schema (a table the comparison reads is missing); the comparison never initialises a database"; the file is still 0 bytes |

One entry of the output, as printed:

```json
{"tariff_code": "4700",
 "from_record": {"version": 1, "record_hash": "21a2e84466c242ce65905f09a0f02ef0b772f96c4860cd053c385f8717e334db", "successor_versions": []},
 "to_record": {"version": 2, "record_hash": "45897b85bed583653605c058a25708f18c993f1c8aa68dfea5bdc85de00a2e75", "successor_versions": []},
 "changes": [{"field": "tax_points", "from_value": "21.6", "to_value": "16.6"}]}
```

### A database without the schema

The CLI test `test_cli_compare_refuses_a_database_without_the_schema_and_leaves_it_untouched`
runs on both engines: an empty SQLite file, and a Postgres scratch database created without
`db/schema.sql` (the parity harness's `schema=False`). It expects exit 2, empty stdout,
exactly the refusal above on stderr, and the database as it was: the SQLite file's bytes, and
no Postgres relation outside the system schemas. Before the fix it failed with SQLite's
`no such table: tariff` and with Postgres' `UndefinedTable`; after it, it passes. Two
throwaway probes outside the suite: with the CLI made to create a stray table before
comparing, the test failed on both engines at its unchanged-database assertion; and errors
other than the engine's missing-table error (a locked SQLite file, Postgres
`InsufficientPrivilege` and `UndefinedColumn`, a `TypeError`, an `AttributeError`) escaped
the CLI unchanged instead of becoming a refusal.

### Test suites on the host

Offline (`TARIFHUB_PG_TEST_URL` and `ANTHROPIC_API_KEY` unset), Python 3.13.12, counts read
from the junit files of the final runs:

| Suite | Tests | Failures | Errors | Skipped |
|---|---|---|---|---|
| ingestion, whole suite | 319 | 0 | 0 | 4 |
| of which `tests/test_edition_comparison.py` | 35 | 0 | 0 | 0 |
| serving, whole suite (its edition tests import through the changed `manifest.py`) | 127 | 0 | 0 | 2 |

The skips are the ones the 2026-10-27 record lists: three Postgres-only audit tests and the
normalisation case APFS cannot hold, plus serving's two pgvector-only tests. `ruff check` is
clean in `services/ingestion`, `mkdocs build --strict` and `tools/cas_check.py --ci` pass,
and the boundary tests pass in ingestion (determinism, value path, review), intelligence and
serving. Two tests were checked against a deliberate write in the first capture: with an
audit event written inside the comparison, the no-write test failed for the compared and the
refused-after-reading cases, and on the CLI's read-only connection SQLite itself rejected the
write ("attempt to write a readonly database"); the write was then removed.

### Postgres

Against a disposable Postgres 16.14 with pgvector 0.8.2 (`pgvector/pgvector:pg16`, the tmpfs
`db` service of `deploy/docker-compose.verify.yml` on 127.0.0.1:55432; each case uses its own
scratch database, dropped afterwards), counts from the junit files:

| Selection | Tests | Failures | Errors | Skipped |
|---|---|---|---|---|
| `tests/test_edition_comparison.py -k postgres` (the CI step's selection) | 27 | 0 | 0 | 0 |
| `tests/test_manifest_import.py -k postgres` | 70 | 0 | 0 | 1 |
| serving `tests/test_manifest_editions.py -k postgres` | 5 | 0 | 0 | 0 |
| ingestion, whole suite with Postgres enabled (119 Postgres cases) | 438 | 0 | 0 | 2 |
| serving, whole suite with Postgres enabled (24 Postgres cases) | 151 | 0 | 0 | 2 |

The 27 comparison cases are the 26 of the first capture plus the missing-schema case. The
manifest skip, and both ingestion skips, are the normalisation case APFS cannot hold, on each
engine; so the CI step's no-skip check, run on this host, stops at the manifest file, and it
passes only where that case runs (CI, on Linux). Serving's two skips are the SQLite legs of
its pgvector-only tests. No scratch database was left on the server.

## Analysis: what the compared fields cannot see

Dated observation about these two editions, not a value the implementation knows. A scratch
script outside the repository compared every German-sheet column of the two workbooks
position by position, first in the planning analysis of 2026-10-29 and again, with the same
result, at 2026-10-29T23:22Z. Of the 1279 positions listed in both editions:

- 1105 differ in no column;
- 12 differ in TP, the changed positions above;
- 161 differ only in columns the record does not carry: `Bemerkungen` 139, `Limitationen` 30,
  `Kumulierbarkeit` 4 and `Gynäkologie und Geburtshilfe` 1 (`Oui` to `Ja` for 1762). None of
  these differences is whitespace only. Example: 1474.1 gains the limitation "Nicht zur
  Bestimmung des Placental Growth Factors (PlGF) zum Screening auf Präeklampsie im ersten
  Trimester bei asymptomatischen Schwangeren." and its cumulability becomes "Nicht
  kumulierbar mit 1525.00, 1526.00 und 1779.00";
- 1 (6299.5) differs only in BAG's own column `letzte Änderung (Datum)`, which moved for 172
  positions in all.

The comparison reports those 161 positions as unchanged within `compared_fields`.

## Review

- Determinism checklist (`.claude/agents/determinism-auditor.md`), inline, on the final diff:
  clean. No LLM client in serving, MCP or any changed ingestion module; `ai_map`, freeze and
  audit code unchanged; the change adds no INSERT, UPDATE or DELETE, and the comparison has no
  commit, `init_schema`, `run_pipeline` or `ai_map` call.
- Security focus list (`.claude/agents/security-reviewer.md`), inline: no finding above Low.
  The header read uses the adapter's size guard and read-only openpyxl on re-verified bytes.
  The CLI never echoes the URL or a driver message: a database that cannot be opened is named
  by the exception type only, and the missing-schema refusal is fixed text, given only for
  the engine's own missing-table error (an `sqlite3.OperationalError` starting with
  `no such table:`, Postgres `UndefinedTable`). Low: the history read loads every EAL row with
  its embedding, as the import already does.
- Codex (gpt-6.1-sol, reasoning effort max, read-only sandbox, `codex review
  --uncommitted`) on the final change set, run before this line was written: "No actionable
  defects found in the tracked or untracked changes." Its sandbox did not run the full
  suites, the Postgres tests or the documentation build. Its run on the first capture had
  found none either.
- The repository's review procedure stood in for the `code-review` skill that `tdd` names,
  which this repository does not install.

## Reproduction

From `services/ingestion`, with a fresh database path:

```bash
DB=/tmp/al-compare-demo.db   # must not exist yet
env -u ANTHROPIC_API_KEY TARIFHUB_DB_URL="sqlite:///$DB" \
  uv run --no-sync python -m tarifhub_ingest.cli --manifest ../../data/manifests/bag-al.json
for run in 1 2; do
  env -u ANTHROPIC_API_KEY TARIFHUB_DB_URL="sqlite:///$DB" \
    uv run --no-sync python -m tarifhub_ingest.cli --manifest ../../data/manifests/bag-al.json \
    --compare 2026-01-01 2026-07-01 > "/tmp/al-compare-$run.json"
done
shasum -a 256 /tmp/al-compare-1.json /tmp/al-compare-2.json   # equal
uv run --no-sync pytest -q tests/test_edition_comparison.py
```

The Postgres cases need the disposable database of `deploy/docker-compose.verify.yml` (its
header has the commands); then, from `services/ingestion`:

```bash
TARIFHUB_PG_TEST_URL=postgresql://tarifhub:tarifhub@localhost:55432/tarifhub \
  uv run --no-sync pytest -q tests/test_edition_comparison.py -k postgres
```

## Remaining limitations

- These are local runs; the CI runs of the pushed revision are recorded in its pull request.
- Workbook columns the record does not carry (limitations, remarks, cumulability, laboratory
  and discipline flags) are not compared.
- The missing-schema refusal covers a missing table only. A `tariff` table of another layout
  (a missing column) raises the driver's error, and opening the database read-only refuses on
  any exception, naming only its type.
- `as_of` keeps serving a removed position's earlier record; the real editions have no
  removed position, and this slice does not change `as_of`.
- Codes are compared as stored (`1779`); the BAG texts cite `1779.00`, and aliases stay a
  separate decision (ADR-021).
