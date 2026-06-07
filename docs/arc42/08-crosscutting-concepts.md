# 8. Crosscutting Concepts

## The freeze line (determinism)

The central concept. AI may assist up to and including mapping; from `freeze` onward a
record is immutable. The `record_hash` is a SHA-256 over the sorted canonical content
fields (excluding `record_hash`, `created_at`, `version`), so identical content always
yields the same hash and re-ingestion is idempotent.

## Canonical model

One Pydantic model (ingestion) and one Panache entity (serving) map onto the same
columns. The field set is frozen; changes are additive and require an ADR.

## Confidence and human-in-the-loop

Confidence is a deterministic function of record content. Records below the configured
threshold (or failing validation) are flagged `requires_review`.

## Auditability / lineage

`audit/` writes an append-only event per freeze: source file, parser version,
confidence, validation outcome and the resulting hash.

## Embeddings and search

Embeddings (multilingual-e5 in production; an offline deterministic stub in dev) are
written to pgvector. Search embeds the query and returns nearest frozen rows.

## Security and data sovereignty

The core processes only public tariff data (no PII). Secrets come from the environment;
the serving value path imports no LLM client; CI runs gitleaks, Trivy and an SBOM step.

## Observability

Prometheus metrics and OpenTelemetry traces from serving; structured logs from both.
