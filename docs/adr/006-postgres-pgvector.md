# ADR-006: PostgreSQL 16 + pgvector as the single store

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
The platform needs transactional integrity for its append-only lineage design (immutable frozen versions, uniqueness over the version tuple and over `record_hash`, an append-only `audit_log`) *and* multilingual semantic search, hostable in Switzerland by a solo operator. Every additional datastore is another system to secure, back up, and reconcile with the lineage story: the constraint is operational surface, not query features.

## Decision
We use PostgreSQL 16 with the pgvector extension (HNSW index, cosine distance, multilingual-e5-large 1024-dim embeddings) as the single system of record and vector index. A SQLite mirror with a stub embedder serves offline dev and tests.

## Alternatives weighed
- **Separate vector DB (Pinecone, or self-hosted Qdrant/Weaviate)**: a second system to host, secure, pay for and keep consistent with the frozen records. CH data residency is harder, and the earlier Pinecone choice is explicitly rejected.
- **NoSQL document store**: gives up relational integrity and transactional freeze + audit semantics, the exact properties billing data needs.

## Consequences
- (+) One backup, one lineage story, one connection string (`TARIFHUB_DB_URL`). Vectors live next to the records they index, so search results are always frozen records.
- (+) Integrity is append-only and hash-anchored rather than foreign-key based: `db/schema.sql` deliberately declares no FOREIGN KEY constraints. `UNIQUE (tariff_system, tariff_code, version)` and `UNIQUE (record_hash)` pin record identity, and `audit_log` rows anchor to `tariff` by `record_hash` value, so immutable rows plus the append-only write path preserve lineage without referential actions in the engine ([ADR-004](004-freeze-content-hash-lineage.md), arc42 §5 data-model figure).
- (+) `pytest -q` runs offline against the SQLite mirror, no container needed for the default test loop.
- (-) ANN recall/latency depends on HNSW tuning. Revisit if the corpus grows to where pgvector recall measurably degrades against a dedicated engine.
- (-) Two SQL dialects to keep in sync: schema changes must land in Postgres and the SQLite mirror together.

*Lineage: new.*
