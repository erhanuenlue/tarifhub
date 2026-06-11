# 05 · building block view

## Level 0 — system context

![C4 system context](../diagrams/c4-context.svg)

TarifHub ingests Swiss ambulatory tariff sources (BAG EAL XLSX, FHIR catalogues), harmonises them once pre-freeze, and serves immutable frozen records to humans (TarifGuard console), machines (REST/FHIR clients) and AI assistants (MCP). All consumers read from the same deterministic serving layer; nothing downstream of the freeze line writes.

## Level 1 — containers

![C4 container view](../diagrams/c4-container.svg)

| Container | Repo path | Layer | Responsibility |
|-----------|-----------|-------|----------------|
| Ingestion service | `services/ingestion/` | L0 | AI-assisted harmonisation pipeline: load → parse → map → validate → score → flag → freeze → store → audit |
| Serving API (TarifCore) | `services/serving/` | L1 | Read-only REST: list/get tariffs, pgvector semantic search; no write path, no LLM client importable (AST-tested) |
| MCP server (TarifMCP) | `services/mcp/` | L1 | `search_tariffs`, `get_tariff`, `explain_crosswalk` — read-only httpx proxies to the serving API (`explain_crosswalk` currently errors with 404: the serving endpoint is designed, not yet built) |
| TarifGuard console | `apps/tarifguard/` | L3 | Master–detail search UI + labelled AI explain panel with server-side de-identification (the review form is designed, not yet implemented) |
| Database | `db/` | — | PostgreSQL 16 + pgvector; `schema.sql` + forward-only migrations; the only contract between L0 and L1 |
| Deployment | `deploy/` | — | docker-compose + Helm/k3d; container-first distribution evidence |

L2 (intelligence: rules, crosswalk reasoning) is post-CAS scope. An offline-tested scaffold exists at `services/intelligence/` (tarifiq: frozen rule table, combinability evaluation, TARMED↔TARDOC crosswalk), but it is not wired into the deployed stack and is deliberately absent from the MVP container view.

## Level 2 — ingestion service components

![C4 component view — ingestion](../diagrams/c4-component-ingestion.svg)

The ingestion service is the only place where AI runs, and only at the `map` step.

> **No AI computes or mutates a billing value at serve time.**

| Component | Module (under `services/ingestion/src/tarifhub_ingest/`) | Responsibility |
|-----------|-----------------------------------------------------------|----------------|
| Adapters | `adapters/bag_eal.py` | Source-specific acquisition of raw BAG EAL rows |
| Parsers | `parsers/xlsx_parser.py`, `parsers/fhir_parser.py` | Format-specific parsing into raw row dicts, each with a pinned parser version |
| Mapper | `mappers/tariff_mapper.py` (`map_raw`) | Deterministic mapping to the canonical `TariffRecord` — owns **all billing values** |
| `ai_map` seam | `mappers/tariff_mapper.py` (`ai_map`, `AIRefinement`) | The **only live-AI point in the system**: fill-only on non-billing fields, deterministic gap-gate decides whether to call at all, structured output via `messages.parse`, deterministic fallback to `map_raw` without an API key |
| Validator | `validators/tariff_validator.py` (`validate`, `ValidationResult`) | Schema and business-rule checks; failures fail closed into review |
| Confidence scorer | `confidence/scorer.py` (`score`) | Deterministic harmonisation-confidence score per record |
| Review routing | `ingestion/pipeline.py` (`requires_review`) | Flags records with confidence below `TARIFHUB_REVIEW_THRESHOLD` (default 0.85) or failed validation for human review |
| Freeze | `versioning/freeze_record.py` (`freeze`, `compute_record_hash`, `verify`) | SHA-256 `record_hash` over sorted canonical content; freezing an already-frozen record raises `ValueError`; updates are new versions |
| Audit | `audit/audit_logger.py` (`AuditLogger`) | Append-only lineage event per pipeline outcome |
| Embedder | `embeddings/embedder.py` (`Embedder` protocol, `HashingEmbedder`, `get_embedder`) | Search embeddings only — never on the value path; deterministic hashing stub offline |
| Repository | `storage/tariff_repository.py`, `storage/db.py` | Persistence of frozen records + embeddings; idempotent on `record_hash` |
| Pipeline orchestrator | `ingestion/pipeline.py` (`run_pipeline`) | Fixed stage order `load → parse → map → validate → score → flag → freeze → store → audit`; pure function of sorted inputs |

## Data model

![ER model — tariff and audit_log](../diagrams/er-data-model.svg)

Two tables. `tariff` holds immutable versioned rows: `UNIQUE(tariff_system, tariff_code, version)` makes versions explicit, `record_hash UNIQUE` (SHA-256 over sorted canonical content) is the integrity anchor and idempotency key, and `embedding vector(1024)` carries the pgvector HNSW cosine index for semantic search. `audit_log` is append-only lineage, keyed by `record_hash` — every freeze and skipped re-ingest leaves an event.

Canonical source of truth: `db/schema.sql` in the repository, mirrored in SQLite for offline tests. The field set is locked additive-only per [ADR-003](../adr/003-canonical-record-model.md); the Pydantic model (`models/tariff_model.py`, `TariffRecord`) is the same shape end-to-end.
