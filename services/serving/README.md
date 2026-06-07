# tarifhub-serving

Deterministic serving of frozen tariff records (Quarkus, Java 21). This is the value
path: every value returned is an unaltered, frozen, versioned record read from the
system of record. AI lives only in the `search` package, which ranks/explains frozen
records and never fabricates a value.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/tariffs` | List frozen records (JSON or XML via `Accept`) |
| GET | `/api/v1/tariffs/{system}/{code}` | One record by key (JSON or XML) |
| GET | `/api/v1/search?q=...&limit=10` | Semantic search → frozen records ranked (JSON) |
| GET | `/q/swagger-ui`, `/q/openapi` | API docs |
| GET | `/q/metrics` | Prometheus metrics |

## Run

```bash
docker-compose up -d db          # Postgres 16 + pgvector (from repo root)
../../scripts/init_db.sh         # apply db/schema.sql + migrations
mvn quarkus:dev                  # http://localhost:8080 ; live reload
```

## Test

```bash
mvn verify
```

`DeterminismBoundaryTest` is plain JUnit and runs with no infrastructure: it asserts the
AI boundary (only `…serving.search` references langchain4j; the value path returns
persisted records). `TariffResourceTest` is a `@QuarkusTest` and expects a reachable
Postgres with the schema applied (or Dev Services with a pgvector-enabled image).

## AI semantic search

`search/SemanticSearchService` embeds the query with a langchain4j `EmbeddingModel` and
asks the repository for nearest frozen rows by cosine distance on the pgvector column.
The embedding model and the `quarkus.langchain4j.pgvector.dimension` MUST match the model
ingestion used (multilingual-e5, 1024-dim). If no embedding model is wired, the value
endpoints still work and `/api/v1/search` returns 503. Set
`QUARKUS_LANGCHAIN4J_ANTHROPIC_API_KEY` to enable optional natural-language explanations
(over frozen text only — never altering a value).

## Layout

```
src/main/java/ch/tarifhub/serving/
├─ TariffRecordEntity.java     read-only Panache projection of the frozen `tariff` table
├─ TariffRepository.java       read queries + pgvector nearest-neighbour helper
├─ TariffResource.java         GET /api/v1/tariffs[...] (JSON/XML) — no AI
└─ search/
   ├─ SemanticSearchService.java   the ONLY langchain4j user; ranks frozen records
   └─ SearchResource.java          GET /api/v1/search
```
