---
description: Scaffold a new ingestion adapter (a tariff source) in services/ingestion, following the existing parser + source-loader pattern. Pre-freeze only — never touches frozen/versioning/audit paths.
argument-hint: <SOURCE_NAME> [format: xlsx|csv|fhir|json]
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
model: claude-opus-4-8
---

Scaffold a new **ingestion source adapter** for: **$ARGUMENTS**

This is L0 / pre-freeze work. The adapter loads a raw source, parses it into the canonical
model, and hands it to the pipeline for AI-assisted mapping → confidence → human review →
**freeze**. It must NOT compute or freeze values itself, and must NOT touch
`versioning/`, `audit/`, or any frozen table.

## Follow the existing pattern (read these first)

- `services/ingestion/src/tarifhub_ingest/ingestion/source_loader.py` — `SourceSpec`,
  `discover_samples`, the per-system filename lists.
- `services/ingestion/src/tarifhub_ingest/parsers/` — `xlsx_parser.py`, `fhir_parser.py`
  (the parsing style: pure functions, return canonical-shaped rows, no I/O surprises).
- `services/ingestion/src/tarifhub_ingest/models/tariff_model.py` — the `TariffSystem`
  enum and the canonical fields (LOCKED — extend additively, never rename).
- `services/ingestion/src/tarifhub_ingest/ingestion/pipeline.py` — how a `SourceSpec`
  flows through mapping/confidence/freeze.

## Scaffold (minimal, incremental — rule 3)

1. **Parser.** Add `parsers/<source>_parser.py` with a pure `parse_<source>(path) -> list[...]`
   that returns rows shaped for the canonical model. Mirror the structure and docstring style
   of the closest existing parser for the chosen format.
2. **Register the source.** In `source_loader.py`, add the new `TariffSystem` (if needed, add
   the enum value in `tariff_model.py` — additive only), a `_<SOURCE>_SOURCE_URL`, a
   `_<SOURCE>_FILENAMES` tuple, and a `SourceSpec` in `discover_samples` (keep the
   deterministic ordering).
3. **Sample data.** Add a tiny, synthetic sample under
   `services/ingestion/sample-data/input/` matching one of the filenames. Keep it
   illustrative and license-clean — never commit a real proprietary catalogue.
4. **Wire mapping if the format is new.** If this source needs new pre-freeze mapping logic,
   extend `mappers/tariff_mapper.py` — but the ONLY live-LLM seam remains `ai_map()`; the
   offline path stays deterministic.
5. **Test.** Add `tests/test_<source>_source.py` that runs fully offline: parse the sample,
   assert the canonical fields, assert the records reach the freeze step with a stable
   `record_hash`. The suite must pass with `cd services/ingestion && pytest -q`.

## Finish

Run `cd services/ingestion && pytest -q` and `ruff check .`. Summarize the files added and
the new `TariffSystem`. When ready to ship, use `/ship`. Do not invoke `git` yourself here —
leave that to `/ship`.
