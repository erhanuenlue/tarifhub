# ADR-001 — Two-service split: Python ingestion + Quarkus serving

- Status: Accepted
- Date: 2026-06

## Context

TarifHub needs an AI-rich harmonization stage and a strictly deterministic serving
stage. These have different qualities: the first benefits from Python's AI/data
ecosystem; the second benefits from a strongly-typed, fast, deterministic JVM service.

## Decision

Split into two services along the freeze line:

- **Ingestion (Python 3.12, FastAPI):** everything up to and including freeze/store/audit.
- **Serving (Java 21, Quarkus):** deterministic read API over frozen records + semantic search.

The contract between them is the set of frozen canonical records in PostgreSQL — not a
chatty RPC interface.

## Consequences

- The AI/deterministic boundary maps cleanly onto a process boundary and is easy to
  enforce and test.
- Two build toolchains to maintain.
- The shared database schema becomes the integration contract and must stay stable
  (see ADR-003).
