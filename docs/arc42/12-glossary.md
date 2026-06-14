# Glossary

The terms that recur across this report, each defined as implemented in the repository, not in the abstract.

| Term | Definition |
|---|---|
| **Freeze line** | The architectural boundary that separates AI-assisted, pre-freeze harmonisation (L0) from the deterministic, read-only serving layers below it (L1+); no AI computes or mutates a billing value at serve time. |
| **Freeze** | The pipeline step (`versioning/freeze_record.py`) that stamps a record's `record_hash` and makes it immutable; re-freezing an already-frozen record raises `ValueError`. |
| **record_hash** | The SHA-256 hash over a record's sorted canonical content (excluding `record_hash`, `created_at`, `version`); it is the integrity anchor and the idempotency key, `UNIQUE` in the database. |
| **ai_map** | The single live-AI seam (`mappers/tariff_mapper.py`), running only pre-freeze: it wraps the deterministic `map_raw` and may fill missing non-billing fields via schema-constrained structured output. |
| **fill-only** | The constraint on `ai_map`: it may only add a value to an empty non-billing field (FR/IT designation, category) and never overwrites an existing value or touches a billing value. |
| **gap-gate** | The deterministic check that decides whether `ai_map` calls the model at all; when nothing fillable is missing it skips the call entirely (the EAL live run made zero API calls over 1 279 complete rows). |
| **fill-reuse** | The mechanism (`ADR-005 addendum`) that carries a prior frozen version's AI fills forward with no model call when the deterministic pre-fill content is unchanged, making re-ingest reproducible despite non-byte-stable live fills. |
| **TariffRecord (canonical model)** | The single Pydantic v2 model (`models/tariff_model.py`) used end to end; its field set is locked additive-only ([ADR-003](../adr/003-canonical-record-model.md)) and mirrors `db/schema.sql`. |
| **harmonisation** | The process of mapping heterogeneous Swiss tariff sources (XLSX, FHIR) into the one canonical `TariffRecord` shape; heterogeneity is absorbed in source adapters so the value path stays a single deterministic shape. |
| **confidence score** | A deterministic harmonisation-confidence value in [0, 1] computed per record (`confidence/scorer.py`); records below `TARIFHUB_REVIEW_THRESHOLD` (default 0.85) are flagged for review. |
| **requires_review / review queue** | The boolean flag set when confidence is below threshold or validation fails; the record still freezes carrying the flag, and the set of flagged records is the review queue routed to a human. |
| **audit_log (append-only)** | The lineage table keyed by `record_hash`; every pipeline outcome (`freeze`, `freeze_skipped_idempotent`, review decisions) appends exactly one immutable event, never an update or delete. |
| **versioning** | The immutable-update model: a frozen record is never edited; a correction or a new source version produces a new row with a new `version` and `record_hash`, `UNIQUE(tariff_system, tariff_code, version)`. |
| **determinism boundary** | The architectural rule enforced by an AST test (`test_serving_boundary.py`, `test_determinism_boundary.py`) that statically proves no LLM client is importable on any value-path module; CI fails otherwise. |
| **EAL (BAG Analysenliste)** | The Swiss federal laboratory-analysis tariff list, ingested as a flat trilingual XLSX (three parallel DE/FR/IT sheets joined by position number), values are tax points. |
| **SL (BAG Spezialitätenliste)** | The Swiss federal list of reimbursed medicinal products, ingested as hierarchical FHIR R5 NDJSON (an IDMP resource graph keyed by GTIN), values are retail prices in CHF. |
| **TarifCore (L1 serving)** | The read-only serving API (`services/serving/`): list/get tariffs, point-in-time and diff, deterministic semantic search, record-grounded explain, and a FHIR R4 read adapter; no write path. |
| **TarifMCP (L1 MCP)** | The Model Context Protocol server (`services/mcp/`) exposing `search_tariffs`, `get_tariff`, `explain_crosswalk` as read-only httpx proxies that return the serving API's frozen records verbatim. |
| **TarifGuard (L3 console)** | The demo console (`apps/tarifguard/`, Next.js): master-detail search, frozen-record detail, a human review form, and a labelled AI explain panel; it renders frozen values verbatim and computes nothing of its own. |
| **point-in-time / as_of** | The query that returns the frozen version of a key that was valid on a given date (`?as_of=<date>`), selected by `valid_from`/`valid_to` with the highest qualifying version; 404 if none was valid then. |
| **diff** | The serving query (`/diff?from=&to=`) that returns the field-level delta between two frozen versions of one key, with both `record_hash`es included; it reports changes, never recomputes a value. |
| **FHIR R4** | The HL7 interoperability standard; the serving layer offers a read adapter that maps a frozen record to a `ChargeItemDefinition` and a tariff system to a `CodeSystem` without altering any value. |
| **de-identification seam** | The console's server-side scrubber (`lib/deident.ts`, ADR-012), the only sanctioned builder of a model-bound payload: the explain seam forwards a tariff code only and scrubs any free-text context. |
| **pgvector** | The PostgreSQL extension that stores the 1024-dim embedding column (`vector(1024)`, HNSW cosine index) and runs the semantic-search ranking (`<=>`) on the real engine. |
| **multilingual-e5** | The multilingual-e5-large embedding model (1024-dim) used for cross-lingual semantic search; it is asymmetric, indexed documents use a `passage:` prefix and queries a `query:` prefix. |
