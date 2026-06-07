# ADR-002 — AI before freeze only

- Status: Accepted
- Date: 2026-06

## Context

Tariff values are billing-relevant: they must be reproducible, auditable and stable. A
non-deterministic model in the value path would make a value depend on a prompt, a model
version or a sampling seed — unacceptable.

## Decision

AI is allowed (a) in harmonization **before** the freeze and (b) for
**search/discovery/explanation** in serving. AI **never** computes or mutates a
billing-relevant value. Every authoritative value returned is an unaltered, frozen,
versioned record served deterministically. Search finds/ranks/explains; it never invents
a number.

## Enforcement

- Ingestion: the only live-AI seam is `mappers.tariff_mapper.ai_map` (pre-freeze,
  non-billing fields, import-guarded). An AST boundary test asserts the value path
  (`main.py`, `storage`) imports no LLM client.
- Serving: only the `…serving.search` package may reference langchain4j; a source-scan
  test enforces it, and the value path returns persisted records.
- A PreToolUse hook blocks edits to the protected `versioning/` and `audit/` modules.

## Consequences

- Strong, testable determinism and auditability.
- Live AI harmonization is gated behind explicit configuration and human review.
