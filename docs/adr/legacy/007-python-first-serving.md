# ADR-007 — Python-first serving (FastAPI), no JVM

- Status: Accepted
- Date: 2026-06-11

> **Superseded numbering.** This is repo-era ADR-007 (pre-register). The consolidated 2026-06 register renumbered all decisions — see [the mapping](README.md).

## Context

The owner decided (final, 2026-06-11): **no Java/JVM anywhere** — a single-language Python
backend. A complete Quarkus serving app already existed (ADR-004): a read-only REST API over
frozen records plus pgvector semantic search. Two build toolchains (ADR-001) was a cost the
no-JVM decision removes.

## Decision

Delete the Java/Quarkus serving app and **port the three serving endpoints to Python 3.12 +
FastAPI** in `services/serving`: list, get-by-key, and pgvector semantic search. The port
reuses the canonical Pydantic `TariffRecord` from ingestion (ADR-003), stays **read-only and
deterministic**, and keeps the same DB contract — frozen rows in PostgreSQL.

## Consequences

- One backend language; simpler CI and toolchain (no JDK/Maven, no native-image step).
- Supersedes **ADR-004** and amends **ADR-001** (the two-service split stands; the serving
  toolchain changes from Quarkus to FastAPI).
- Semantic search requires Postgres + pgvector; on the SQLite offline test mirror the search
  endpoint returns an explicit **501**, so the unit suite stays network-free.
