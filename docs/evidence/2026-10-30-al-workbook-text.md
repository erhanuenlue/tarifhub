# BAG AL workbook texts in the edition comparison: local verification

Verification record for the comparison of selected German workbook columns as published text
([ADR-024](../adr/024-al-workbook-text.md)), on the BAG Analysenliste editions of 1 January and
1 July 2026. Captured on 2026-10-30 on the macOS host (Apple Silicon, Python 3.13.12 in the
service environments), against SQLite and a disposable Postgres 16 container: no API key, no
external network, no e5 model.

## Tested revision

The working tree on top of `b87095f` (branch `feat/al-workbook-text`), committed for review
after these runs; the files under test did not change. These are local results: the CI runs
of the pushed revision are recorded in its pull request, not here. The files under test, by
git blob ID:

| Blob | File |
|---|---|
| `6385b5bafa2f` | `services/ingestion/src/tarifhub_ingest/ingestion/edition_comparison.py` |
| `8204e3ef5f99` | `services/ingestion/src/tarifhub_ingest/adapters/bag_eal.py` |
| `a7473636a2f9` | `services/ingestion/src/tarifhub_ingest/cli.py` (docstring only) |
| `81ef3fa2f059` | `services/ingestion/src/tarifhub_ingest/ingestion/manifest.py` (unchanged) |
| `62d3737be5f1` | `services/ingestion/tests/test_edition_comparison.py` |
| `dfb6cfe4cfad` | `services/ingestion/tests/test_bag_eal.py` |
| `382ddcd25ee6` | `services/ingestion/tests/fixtures/eal/make_edition_fixtures.py` |
| `4bacf0ce2fc5` | `services/ingestion/tests/fixtures/eal/Analysenliste per 1. Januar 2026_text_fixture.xlsx` (new) |
| `cd1bfb3867ff` | `services/ingestion/tests/fixtures/eal/Analysenliste per 1. Juli 2026_text_fixture.xlsx` (new) |
| `ce2bfb20a85f` | `data/manifests/bag-al.json` (unchanged) |

## Expectation (planning analysis, 2026-10-30)

Before any code existed, scratch scripts outside the repository (plain openpyxl on the
hash-checked workbooks, no tarifhub code) compared the 24 selected columns of the German sheet
for the 1279 positions listed in both editions: `Limitationen`, `Bemerkungen` and
`Kumulierbarkeit` (I to K) and the 21 laboratory flags, S to AB under the banner for the
laboratories of Article 54 KVV (eight columns, each a type of laboratory billing for its own
needs or on external order, plus `Hausbesuch` and `Schnelle Analyse`) and AC to AM, the eleven
titles of the practice laboratories of physicians with specific further-education titles. The
prescriber flags (AN, AO) are not among them. They found 161 positions with 174 changed
cells: `Bemerkungen` 139, `Limitationen` 30, `Kumulierbarkeit` 4 and `Gynäkologie und
Geburtshilfe` 1, none in a position whose compared fields change. Unicode NFC and whitespace
folding remove none of the 174 differences. This reproduced the 161 of the
[ADR-023 record](2026-10-30-al-edition-comparison.md), whose differences fall entirely in
these columns. These are dated observations about two editions, not values the
implementation knows; the tests derive none of them.

The two committed fixtures are copied, unchanged, from the hash-checked workbooks by
`make_edition_fixtures.py`: positions 1000, 1474.1, 1762, 4707.1 and, in July only, 1779.
Rebuilding with the script rewrote the two existing fixtures with cell values identical to the
committed ones (checked sheet by sheet); their committed bytes were then restored, so they are
unchanged.

## Results

### Real editions on a disposable SQLite database

| Step | Result |
|---|---|
| Import of both editions (CLI, offline stub embedder, no key) | exit 0; January 1279 and July 1280 positions frozen, 0 flagged, 0 parse failures |
| Comparison, run in two separate processes | exit 0 both times, empty stderr, about 1.4 s each; 416 656 bytes of JSON, SHA-256 `8e4c6499f3fd0f86381e44c848883c9c8f2be77fdc78b4599301b17e4072439d` both times, byte-identical |
| SHA-256 of the database file before and after both comparisons | identical, `885a9266e09c4cb015b4bc0f33adcde5e9d0afed1846d3f1948ab9da958ec742` |
| The `b87095f` comparison code (its `edition_comparison.py`, taken from git and run on the same database) | 33 106 bytes, SHA-256 `3ff429ef6ea495a982bb6d47dbacc302d4dff058d9aadb1f79a94671f0564dbb`: exactly the output the ADR-023 record captured |
| The new output against that baseline | `from_edition`, `to_edition`, `compared_fields`, `counts`, `added`, `removed`, `changed` and `unchanged` identical; `workbook_text` appended after them. In `scope_limitation` the summary is rewritten, `columns_compared_as_text` names the 24 columns, `columns_not_compared` loses exactly those 24 (9 German names remain, in their order), and the French and Italian lists are unchanged |
| Counts within `compared_fields` | added 1, removed 0, changed 12, unchanged 1267, as before |
| `workbook_text` | coverage `complete`, the 24 columns requested and compared, `not_comparable` empty; 1279 positions compared, 161 with text changes, 0 of them listed under `changed`, 174 cells changed; by column `Bemerkungen` 139, `Limitationen` 30, `Kumulierbarkeit` 4, `Gynäkologie und Geburtshilfe` 1, each of the other 20 columns 0 |
| Independent check against the raw cells (plain openpyxl, no tarifhub code, both workbooks hash-checked) | every selected cell of both editions is a string or empty; the script's own comparison (NFC and whitespace folding over the 24 columns, positions listed in both editions) equals the reported positions exactly, cell references and verbatim texts included, each difference once; the `in_changed` flags equal the overlap with `changed` (none); both sources cite the manifest document and the verbatim header cells `I2` to `AM2`; trim-only equality gives the same 174 cells |

Three entries of the output, as printed (one per line here):

```json
{"tariff_code": "1474.1", "in_changed": false, "changes": [
 {"column": "Limitationen", "from_cell": "I313", "to_cell": "I313", "from_text": null, "to_text": "Nicht zur Bestimmung des Placental Growth Factors (PlGF) zum Screening auf Präeklampsie im ersten Trimester bei asymptomatischen Schwangeren."},
 {"column": "Kumulierbarkeit", "from_cell": "K313", "to_cell": "K313", "from_text": "Nicht kumulierbar mit 1525.00 und 1526.00", "to_text": "Nicht kumulierbar mit 1525.00, 1526.00 und 1779.00"}]}
{"tariff_code": "1762", "in_changed": false, "changes": [
 {"column": "Gynäkologie und Geburtshilfe", "from_cell": "AG541", "to_cell": "AG541", "from_text": "Oui", "to_text": "Ja"}]}
{"tariff_code": "4707.1", "in_changed": false, "changes": [
 {"column": "Kumulierbarkeit", "from_cell": "K1012", "to_cell": "K1013", "from_text": "Kumulierbar mit 4707.20 bis maximal 18 Taxpunkte pro Tag", "to_text": "Kumulierbar mit 4707.20 bis maximal 13 Taxpunkte pro Tag"}]}
```

All three positions stay in `unchanged`. 1762's change is the cell's literal text: its French
(`Oui`) and Italian (`Si`) cells and its `letzte Änderung (Datum)` did not change, and the
output claims no entitlement. 6206.55 shows the other shifted row: `Limitationen` `I1049` to
`I1050`, the citation `SR 11.11` corrected to `SR 811.11`.

### Behaviour on the fixtures

The tests use the public seams only: `compare_editions` on databases `import_manifest` filled
(every such test runs on SQLite and, with the opt-in URL, on Postgres), the CLI's `main`, and
`bag_eal.text_cells`. Expected values are copied from the BAG cells or written into edited
copies of the fixtures, never computed by the code under test. They cover:

- provenance: sheet, header row, the 24 header cells, an empty cell as a cell without text,
  4707.1 at `K6` in January and `K7` in July;
- the three real changes above, with the classification unchanged, and complete coverage with
  its counts, zero columns included, and both workbook sources;
- the scope limitation's new partition;
- whitespace and Unicode form only (line breaks, runs of spaces, a no-break space, padding,
  decomposed umlauts): no entry, while the reader shows the verbatim cells differ;
- a digit, punctuation, case, a word, a diacritic, a cleared cell: one entry each, verbatim;
- a position also changed in a compared field (4700): listed once, `in_changed: true`;
- a blank row inserted in July: the cell is cited at `I5` instead of `I4`;
- a missing header, a header named twice, and a formula, number, boolean, date or error value
  in a requested column: that column listed under `not_comparable` with the cells concerned,
  coverage `partial`, the column counted nowhere and listed as not compared in the scope;
- no readable column at all (CLI): coverage `unavailable`, `counts`,
  `cells_changed_by_column` and `positions` null, the frozen counts as before, exit 0;
- a position number written as a formula: the comparison is refused, naming the cell;
- the reader refuses a repeated position and a workbook without a German header to cite.

Red before green: the reader, the real changes, the coverage block, the scope partition,
normalisation, the overlap flag, each `not_comparable` reason, the unavailable coverage, the
formula position number and the repeated position each failed first. The meaningful-change
cases, the inserted blank row, the CLI key-order check and the reader's two anchor cases passed
on their first run, because the code already behaved so; the reader's two anchor checks had
been written before their test.

### Test suites on the host

Offline (`TARIFHUB_PG_TEST_URL` and `ANTHROPIC_API_KEY` unset), counts read from the junit
files of the final runs:

| Suite | Collected | Passed | Skipped | Failed or errors |
|---|---|---|---|---|
| ingestion, whole suite | 343 | 339 | 4 | 0 |
| of which `tests/test_edition_comparison.py` | 55 | 55 | 0 | 0 |
| of which `tests/test_bag_eal.py` | 31 | 31 | 0 | 0 |
| serving, whole suite (it imports the changed adapter) | 127 | 125 | 2 | 0 |

The skips are the known ones: three Postgres-only audit tests and the normalisation case APFS
cannot hold, plus serving's two pgvector-only tests. `ruff check` is clean in
`services/ingestion`; the ingestion coverage gate of CI's `python` job passes at 93.63 %
(`edition_comparison.py` 100 %, `bag_eal.py` 89 %; in `text_cells` only the row-limit guard,
which mirrors `parse()`'s, is not exercised). `mkdocs build --strict` and
`tools/cas_check.py --ci` pass, and the boundary tests pass in ingestion (determinism, value
path, review: 7), intelligence (2) and serving (3).

### Postgres

Against a disposable Postgres 16.14 with pgvector 0.8.2 (`pgvector/pgvector:pg16`, the tmpfs
`db` service of `deploy/docker-compose.verify.yml` on 127.0.0.1:55432, started for this run and
removed afterwards; each case uses its own scratch database, and none was left), counts from
the junit files:

| Selection | Collected | Passed | Skipped | Failed or errors |
|---|---|---|---|---|
| `tests/test_edition_comparison.py -k postgres` (a CI step's selection) | 47 | 47 | 0 | 0 |
| `tests/test_manifest_import.py -k postgres` (a CI step's selection) | 70 | 69 | 1 | 0 |
| `tests/test_read_parity.py` (a CI step's selection) | 22 | 22 | 0 | 0 |
| serving `tests/test_manifest_editions.py -k postgres` (a CI step's selection) | 5 | 5 | 0 | 0 |
| ingestion, whole suite with Postgres enabled | 480 | 478 | 2 | 0 |
| of which Postgres cases | 139 | 138 | 1 | 0 |
| serving, whole suite with Postgres enabled | 151 | 149 | 2 | 0 |
| of which Postgres cases | 24 | 24 | 0 | 0 |

All 47 Postgres cases of the comparison selection ran and passed; it had 27 before this
change. The one skipped manifest case, and both skips of the whole ingestion suite (one per
engine), are the normalisation case APFS cannot hold, so CI's no-skip check passes only where
that case runs (Linux). Serving's two skips are the SQLite legs of its pgvector-only tests.
These runs preceded the last test-only addition, the reader's two anchor cases in
`tests/test_bag_eal.py`, which has no Postgres legs; no source file changed since.

## Review

- Determinism checklist (`.claude/agents/determinism-auditor.md`), inline, on the full diff:
  clean. No LLM client in serving or MCP; `ai_map`, the freeze, the audit logger, the
  versioning and the migrations are untouched; the change adds no INSERT, UPDATE or DELETE and
  no commit, `init_schema`, `run_pipeline` or `ai_map` call. The texts are compared, never
  written, and no frozen record, `record_hash`, canonical field or schema changes.
- Security focus list (`.claude/agents/security-reviewer.md`), inline: no finding above Low.
  The reader opens the bytes the comparison has just verified, under the adapter's size guard,
  in read-only openpyxl, which never evaluates a formula; it caps the positions as `parse()`
  does and refuses a repeated or formula position number. Low, not new: openpyxl's
  decompression of a hostile archive is bounded only by the compressed-size cap, as for
  `parse()`; published texts are printed verbatim, JSON-escaped, so a text with bidirectional
  control characters would print them, as designations already do.
- Codex (gpt-6.1-sol, reasoning effort max, read-only sandbox, `codex review --uncommitted`) on
  the final change set, run before this line was written: "No actionable regressions found.
  Focused tests, lint, the CAS ratchet, and independent real-workbook validation passed; full
  service/Postgres suites and the MkDocs build remain unverified under read-only constraints."
  Those suites and the build are the runs recorded above.
- The repository's review procedure stood in for the `code-review` skill that `tdd` names,
  which this repository does not install.

## Reproduction

From `services/ingestion`, with a fresh database path:

```bash
DB=/tmp/al-text-demo.db   # must not exist yet
env -u ANTHROPIC_API_KEY TARIFHUB_DB_URL="sqlite:///$DB" \
  uv run --no-sync python -m tarifhub_ingest.cli --manifest ../../data/manifests/bag-al.json
for run in 1 2; do
  env -u ANTHROPIC_API_KEY TARIFHUB_DB_URL="sqlite:///$DB" \
    uv run --no-sync python -m tarifhub_ingest.cli --manifest ../../data/manifests/bag-al.json \
    --compare 2026-01-01 2026-07-01 > "/tmp/al-text-$run.json"
done
shasum -a 256 /tmp/al-text-1.json /tmp/al-text-2.json   # equal
uv run --no-sync pytest -q tests/test_edition_comparison.py tests/test_bag_eal.py
```

The Postgres cases need the disposable database of `deploy/docker-compose.verify.yml` (its
header has the commands); then, from `services/ingestion`:

```bash
TARIFHUB_PG_TEST_URL=postgresql://tarifhub:tarifhub@localhost:55432/tarifhub \
  uv run --no-sync pytest -q tests/test_edition_comparison.py -k postgres
```

## Remaining limitations

- These are local runs; the CI results of the pushed revision are in its pull request.
- Only the German sheet's 24 selected columns of positions listed in both editions are
  compared. The prescriber flags, `Anwendungen pro Primärprobe` and the other uncarried
  columns, the French and Italian sheets (whose texts change independently: 1778.01's French
  `Limitation` changes only by a line break), the texts of added and removed positions, BAG's
  change dates (6299.5 changed only there), cell formatting and the PDFs are not.
- A change is literal text. Whether it is editorial (`SR 11.11` to `SR 811.11`, `Oui` to `Ja`)
  or substantive (a new limitation, a lower cap) is not decided here.
- A column with one non-text cell is not compared at all, for both editions, not just for that
  cell. A position number written as a formula refuses the comparison, though the import reads
  the cell's cached value.
- The output grows from 33 106 to 416 656 bytes on these editions.
- Codes are compared as stored (`1474.1`); the BAG texts cite `1474.10`, and aliases stay a
  separate decision (ADR-021).
