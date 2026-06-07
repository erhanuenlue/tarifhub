# 11. Risks and Technical Debt

| # | Risk / debt | Mitigation |
|---|---|---|
| 1 | Source-data licensing / republishing terms vary by source | Build on clearly-open sources first; harmonize (transform) rather than resell raw data; clear terms before serving restricted sources. |
| 2 | Embedding-model/dimension drift between ingestion and serving | Pin one model (multilingual-e5, 1024-dim) and match `quarkus.langchain4j.pgvector.dimension` and the `embedding` column. |
| 3 | The live AI mapping seam is a placeholder | `ai_map` falls back to deterministic rules; wire and review the live Claude path behind the `ai` extra before relying on it. |
| 4 | Schema is provisioned by SQL, not a migration tool | Adopt a migration runner (Flyway/Liquibase) when the schema starts evolving. |
| 5 | Determinism could regress in a refactor | Boundary tests (Python AST scan, Java source scan) + the frozen-path edit guard hook. |
| 6 | Single Postgres instance is a single point of failure | Acceptable for the core/demo; add HA/replicas when scale warrants. |

## Known debt

- Serving `@QuarkusTest` requires a reachable Postgres (or Dev Services with a
  pgvector image); document or wire Testcontainers for fully self-contained CI.
- The offline embedder stub is not semantically meaningful (dev/test only).
