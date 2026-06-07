# ADR-003 — Canonical tariff model

- Status: Accepted
- Date: 2026-06

## Context

Sources differ in structure, language and value type (tax points vs. CHF prices).
Consumers need one stable shape. The model is also the integration contract between the
two services.

## Decision

Adopt one canonical, versioned, immutable record with this LOCKED field set:

`tariff_code, tariff_system, designation (de canonical + fr/it), category, tax_points,
price_chf, unit, valid_from, valid_to, source_url, source_version,
harmonization_confidence, requires_review, metadata (JSONB), record_hash, version,
created_at`.

- German is the canonical reference designation; FR/IT are optional.
- Values are `Decimal`/null; `record_hash` is a deterministic SHA-256 over the sorted
  canonical content fields (excluding `record_hash`, `created_at`, `version`).
- Rows are immutable and versioned; the same content re-ingested is idempotent.

## Consequences

- Fields, columns and routes are a frozen contract: extend additively, never break.
  Breaking changes require a new ADR and coordinated migration.
- The Pydantic model and the Panache entity must stay aligned to these columns.
