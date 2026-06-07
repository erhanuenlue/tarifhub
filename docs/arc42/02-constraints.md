# 2. Constraints

## Technical constraints

- **Determinism rule (LOCKED):** no AI ever computes or mutates a billing-relevant value.
  AI is allowed pre-freeze and for search/discovery/explanation in serving only.
- Ingestion service is Python 3.12 and must run fully offline for tests (SQLite, no
  network, no live LLM).
- Serving service is Java 21 / Quarkus 3.x (Jakarta REST, Hibernate ORM with Panache).
- Single system of record: PostgreSQL 16 with pgvector (relational + JSONB + vectors).
  MinIO/S3 holds raw source artifacts.
- The canonical model (fields/columns/routes) is a frozen contract: extend, never break.

## Organizational constraints

- Lean, solo/small-team operation: minimal moving parts, no premature Kubernetes,
  agent frameworks or vector-SaaS.
- AI-assisted development with Claude Code and Codex; `CLAUDE.md` and `AGENTS.md`
  encode the non-negotiable rules and are kept in sync.

## Conventions

- Python: ruff, line length 100, type hints, small pure functions.
- Java: standard Quarkus layout, constructor/field injection, no business logic in resources.
- Tests-before-done: `pytest -q` (ingestion) and `mvn verify` (serving) must be green.
