# ADR-006: PostgreSQL 16 + pgvector as the single store

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
The platform needs relational integrity (frozen versions, append-only `audit_log`, foreign keys) *and* multilingual semantic search, hostable in Switzerland by a solo operator. Every additional datastore is another system to secure, back up, and reconcile with the lineage story: the constraint is operational surface, not query features.

## Decision
We use PostgreSQL 16 with the pgvector extension (HNSW index, cosine distance, multilingual-e5-large 1024-dim embeddings) as the single system of record and vector index; a SQLite mirror with a stub embedder serves offline dev and tests.

## Alternatives weighed
- **Separate vector DB (Pinecone, or self-hosted Qdrant/Weaviate)**: a second system to host, secure, pay for and keep consistent with the frozen records; CH data residency is harder; the earlier Pinecone choice is explicitly rejected.
- **NoSQL document store**: gives up relational integrity and transactional freeze + audit semantics, the exact properties billing data needs.

## Consequences
- (+) One backup, one lineage story, one connection string (`TARIFHUB_DB_URL`); vectors live next to the records they index, so search results are always frozen records.
- (+) `pytest -q` runs offline against the SQLite mirror, no container needed for the default test loop.
- (-) ANN recall/latency depends on HNSW tuning; revisit if the corpus grows to where pgvector recall measurably degrades against a dedicated engine.
- (-) Two SQL dialects to keep in sync: schema changes must land in Postgres and the SQLite mirror together.

*Lineage: new.*
