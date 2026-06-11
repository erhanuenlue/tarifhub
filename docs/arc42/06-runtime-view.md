# 06 · runtime view

Three scenarios show the architecture at work: the deterministic harmonisation pipeline (live), semantic search through the serving API (live), and the expert review loop (design level, [ADR-013](../adr/013-demo-scope.md)). Each scenario is traceable to code under `services/`.

> **No AI computes or mutates a billing value at serve time.**

## Scenario 1 — harmonise → freeze (the pipeline)

`run_pipeline` (`services/ingestion/src/tarifhub_ingest/ingestion/pipeline.py`) processes sources in a fixed order: **load → parse → map → validate → score → flag → freeze → store → audit**. It is a pure function of sorted inputs — no randomness, no wall-clock branching — so the same sources always produce the same frozen records and hashes.

![Runtime — harmonisation and freeze](../diagrams/runtime-harmonise-freeze.svg)

1. **Load + parse** — source specs are sorted by system and path; the matching parser (`xlsx_parser`, `fhir_parser`, or the `bag_eal` adapter) yields raw rows.
2. **Map** — `ai_map` wraps the deterministic `map_raw`, which owns every billing-relevant field. The AI seam is **fill-only** (designation FR/IT, category — [ADR-005](../adr/005-single-ai-seam.md)): a deterministic gap-gate skips the model call entirely when nothing is fillable, and any failure or missing API key falls back to the `map_raw` result unchanged.
3. **Validate + score** — `validate` produces a `ValidationResult`; `score` computes a harmonisation confidence in [0, 1].
4. **Flag** — confidence below `TARIFHUB_REVIEW_THRESHOLD` (default 0.85) or a validation failure sets `requires_review`; the record still freezes, carrying the flag into the review queue.
5. **Freeze** — `freeze` stamps the SHA-256 `record_hash` over sorted canonical content; attempting to re-freeze an already-frozen record raises `ValueError`.
6. **Store + audit** — the repository inserts the immutable row (skipping when the hash already exists) and `AuditLogger` appends one event per record: `freeze` or `freeze_skipped_idempotent`.
7. **Idempotency** — re-running on identical sources yields an identical hash set, so every record is skipped and the audit trail records exactly that.

## Scenario 2 — semantic search through serving

`GET /api/v1/search` (`services/serving/src/tarifhub_serving/main.py`) ranks frozen records by cosine similarity to the embedded query. The path is strictly read-only and fails closed rather than degrading silently.

![Runtime — semantic search](../diagrams/seq-search-serving.svg)

1. A client calls `GET /api/v1/search?q=…&limit=…`; FastAPI injects the repository and settings via dependency injection.
2. **Dialect guard** — on a non-Postgres backend (the offline SQLite mirror) the endpoint returns **HTTP 501**: honest unavailability instead of a fake fallback search.
3. The query is embedded with `get_embedder().embed` — the same embedder seam ingestion used to embed the records.
4. **Dimension guard** — if the vector is not 1024-dim (e.g. the offline stub embedder against the `vector(1024)` column), the endpoint fails closed with the same explicit **501** before issuing the doomed pgvector query.
5. `ServingRepository.search_by_embedding` runs a parameterised pgvector cosine query (`<=>`) over frozen rows only.
6. Rows are rehydrated verbatim into `TariffRecord` and returned as ranked `SearchHit` items — no field is recomputed or rewritten.
7. **Read-only guarantee** — the AST boundary test (`services/serving/tests/test_serving_boundary.py`) proves no LLM client is importable on this path; CI fails otherwise.

## Scenario 3 — review → freeze loop (design level)

The console review form and its POST endpoint are **design scope ([ADR-013](../adr/013-demo-scope.md)), not yet implemented**. What is live today: the pipeline flags low-confidence records (`requires_review`), and `freeze` plus the append-only audit log are exercised on every run. The loop below describes how the designed pieces close the cycle.

![Runtime — review to freeze loop](../diagrams/seq-review-freeze.svg)

1. The pipeline flags a record (confidence < 0.85 or validation failure) — it freezes with `requires_review = true` and enters the review queue *(live)*.
2. A tariff expert opens the flagged record in the console master-detail view and corrects or approves the mapping in the review form *(designed)*.
3. The correction passes back through the same deterministic `validate` — an expert edit gets no shortcut around the rules *(designed)*.
4. `freeze` produces a **new version** with a new `record_hash`; the flagged version remains immutable and re-freezing it raises `ValueError` *(freeze live, trigger designed)*.
5. Audit events are appended for the review decision and the new freeze — the append-only `audit_log` keeps the full lineage *(audit live)*.
6. The new version carries `requires_review = false` and the record leaves the queue *(designed)*.

The freeze line itself is defended in depth: `versioning/` and `audit/` are write-protected against AI edits by the `guard_frozen` hook, and the boundary is CI-enforced by `test_determinism_boundary.py`.

## Record lifecycle (states)

![Record lifecycle](../diagrams/state-record-lifecycle.svg)

A record moves **raw → parsed → mapped → validated → scored → frozen**, with flagged records (`requires_review`) entering the review queue as frozen versions; frozen is terminal and immutable — every correction is a new version, every transition an audit event.
