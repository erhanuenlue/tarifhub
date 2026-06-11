# ADR-003 — Canonical, versioned, immutable record model

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
Sources differ in structure, language and value type (tax points vs. CHF prices), while consumers need one stable shape. Because ingestion and serving share only the database (ADR-002), the record model *is* the integration contract — instability here breaks both sides at once.

## Decision
We adopt one canonical `TariffRecord` with a locked, additive-only field set, German as the canonical designation language (FR/IT optional), immutable versioned rows, and idempotent re-ingestion by content hash.

The locked field set: `tariff_code, tariff_system, designation (de canonical + fr/it), category, tax_points, price_chf, unit, valid_from, valid_to, source_url, source_version, harmonization_confidence, requires_review, metadata (JSONB), record_hash, version, created_at`. Values are `Decimal`/null.

## Alternatives weighed
- **Flexible schema (per-source shapes, schemaless JSONB)** — rejected; it defers harmonisation to every consumer and makes the cross-service contract unstable by design.
- **Separate models per service** — rejected; duplicated definitions drift (the repo already observed exactly this between Pydantic and the former Panache entity).

## Consequences
- (+) Fields, columns and routes are a frozen contract: one Pydantic model end-to-end, extended additively, never broken.
- (+) Idempotent re-ingestion by content hash makes pipeline re-runs safe.
- (–) A breaking change requires a new ADR plus a coordinated migration; the additive-only discipline can accumulate awkward fields. Revisit when a real requirement cannot be expressed additively — that is the signal for a versioned contract change, not a workaround.

*Lineage: restates legacy/003-canonical-model.md, with its Panache-entity alignment clause removed per ADR-001 (one Pydantic model is now the only definition).*
