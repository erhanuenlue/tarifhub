# ADR-017 — Deterministic offline search fallback and record-grounded explain endpoint

*Status: Accepted · Date: 2026-06-12 · Decider: Erhan (gate-01 plan approval)*

## Context
Two seams blocked "TarifCore serves everything the docs promise" (criteria 16/17): semantic search returned HTTP 501 everywhere except a Postgres with e5 embeddings installed — so the documented search use-case (UC-06) was untestable offline and undemoable in the default stack — and MCP's `explain_crosswalk` proxied a `/api/v1/explain` endpoint that did not exist (404, ADR-008/013). Both fixes must hold the inviolable rule: no AI on the serve path, frozen values verbatim.

## Decision
(1) `GET /api/v1/search` ranks **offline on SQLite via a deterministic in-process cosine** over the stored stub embeddings — same query path, same response shape as pgvector; ties broken by `(tariff_system, tariff_code)`; Postgres keeps pgvector (`<=>`), and a dimension mismatch against `vector(1024)` still fails closed with 501. (2) `GET /api/v1/explain?code=&system=` is **live and deterministic**: it returns every frozen version of the matching records verbatim plus a rule-generated explanation assembled only from record fields, prefixed `[deterministic]` — no LLM import, no crosswalk coupling to L2 (`services/intelligence`); crosswalk *reasoning* stays L2 scope per ADR-002.

## Alternatives weighed
- **Keep 501 offline** — honest but leaves UC-06 and the MCP search tool undemonstrable in the offline/default stack; rejected at gate 01.
- **LLM-generated explanation on serving** — violates the determinism boundary (AST test); the console's labelled, de-identified AI panel already covers that need at L3.

## Consequences
- (+) The full search and explain paths are testable offline (`uv run pytest -q`, zero network) and the MCP↔serving integration tests exercise real ranked results; the AST boundary test stays untouched and green.
- (–) Two ranking implementations (Python cosine, pgvector) must agree; the Postgres-gated parity leg with a deterministic 1024-dim test embedder guards the pgvector side.

*Lineage: extends [ADR-008](008-api-styles.md) (API surface) and [ADR-013](013-demo-scope.md) (explain seam); boundary rule per [ADR-002](002-freeze-line-decomposition.md)/[ADR-005](005-single-ai-seam.md).*
