# 4. Solution Strategy

| Goal | Strategy |
|---|---|
| Deterministic billing values | A hard **freeze line**. AI assists pre-freeze; once frozen, a record is an immutable, hashed, versioned fact. The serving value path imports no LLM client. |
| Two responsibilities, two runtimes | Python for AI-assisted ingestion (rich AI/data ecosystem); Quarkus/Java for deterministic, strongly-typed serving. The contract between them is the set of frozen canonical records in Postgres. |
| Auditability | Every freeze writes an append-only audit event (source, parser version, confidence, validation outcome, record hash). |
| Trust in harmonization | Deterministic confidence scoring + threshold-based `requires_review`; AI proposes, humans approve low-confidence items. |
| Search without fabrication | Semantic search embeds the query and returns the nearest **frozen** records, ranked. It never invents a value. |
| Single store | PostgreSQL 16 + pgvector for relational data, JSONB metadata and vectors — fewer moving parts than a separate vector database. |

The architecture is hexagonal where natural: parsers, mappers, the embedder and the
repository are ports/adapters around a pure domain core (the canonical model, scoring
and the deterministic freeze).
