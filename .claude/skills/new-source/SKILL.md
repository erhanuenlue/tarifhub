---
name: new-source
description: Add a new tariff data source to the L0 pipeline (adapter → parser → mapping → tests → docs). The repeatable domain workflow.
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Agent
---

Adding source **$ARGUMENTS** to the harmonisation pipeline. The pattern is fixed; the parsing is the work.

1. **Recon first:** fetch a real sample file; inspect structure, encoding, language fields, value semantics (tax points vs CHF prices vs both). Record source URL, format, update cadence and licence note in `docs/arc42/03-context-scope.md`'s source table. **BAG/opendata.swiss sources only until the non-BAG licensing gate clears (Feasibility §8) — flag anything else to Erhan, don't add it.**
2. **Adapter:** `services/ingestion/adapters/<source>.py` — fetch + checksum + store raw artifact (S3/MinIO path convention), idempotent re-fetch.
3. **Parser:** `services/ingestion/parsers/` — raw file → typed raw rows. Hostile-input limits (size, depth). Golden-file fixture: commit a small real sample under `tests/fixtures/<source>/`.
4. **Mapping:** extend `map_raw` deterministically for structural fields; let `ai_map` refine designations/category only (non-billing fields — the boundary). New tariff_system enum value if needed → that's a model change → ADR first (locked contract, ADR-03).
5. **Tests:** parser unit tests on the fixture; pipeline integration test source→freeze on SQLite; pinned-hash test for one known record; re-run idempotency test.
6. **Evidence:** harmonisation report (records in/out, review rate, confidence histogram) — append the figures to `docs/arc42/10-quality-requirements.md`'s results table. Journal entry: what AI mapped well/badly on this format.
7. Finish with `verifier` + `determinism-auditor`, then `/ship`.
