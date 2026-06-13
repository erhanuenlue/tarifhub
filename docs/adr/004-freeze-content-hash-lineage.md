# ADR-004: Freeze, content-hash and lineage as the determinism anchor

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
Tariff values are billing-relevant: they must be reproducible, auditable and stable. The rule "No AI computes or mutates a billing value at serve time" needs a mechanical anchor on the data itself: a served value must be provably the value that was reviewed and frozen, regardless of prompts, models or code changes since.

## Decision
We freeze each reviewed record by stamping a SHA-256 `record_hash` computed over its sorted canonical content (excluding `record_hash`, `created_at`, `version`), store it immutably with an append-only `audit_log` lineage trail, normalise decimals before hashing, and treat freezing an already-frozen record as an error.

## Alternatives weighed
- **Dynamic records (update in place, recompute at serve time)**: rejected; a served value could silently change after review, destroying reproducibility and any audit claim.
- **Timestamp-only versioning without a content hash**: rejected; it cannot prove content identity, so idempotent re-ingestion and tamper-evidence are lost.

## Consequences
- (+) Strong, testable determinism and provenance: any record can be re-hashed and checked; updates are new versions; the lineage from source to frozen record is append-only.
- (+) The version chain makes point-in-time and diff queries natural, designed for the serving API, not yet implemented.
- (+) The `versioning/` module is protected (the `guard_frozen` hook blocks AI edits below the freeze line).
- (-) Corrections always cost a new version: storage grows append-only and there is no in-place fix path. Revisit only if a regulator requires redaction; that would need a documented tombstone mechanism via a new ADR.

*Lineage: restates and strengthens legacy/002-ai-before-freeze.md (the determinism and enforcement core) and legacy/003-canonical-model.md (hash definition, immutability, idempotency).*
