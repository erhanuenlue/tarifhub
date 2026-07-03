---
paths:
  - "services/**/*.py"
  - "db/**"
  - "tests/**/*.py"
---

# Backend rules (loaded only when touching services/db/tests)

- Pydantic v2 models are the contract: parse, don't validate by hand; no raw dicts crossing module boundaries.
- The pipeline is a pure function of sorted inputs — no wall-clock branching, no randomness without a seeded generator, no network in tests (SQLite mirror + stub embedder are the offline defaults).
- SQL is parameterised, always. Migrations are forward-only files in `db/migrations/`; an applied migration is never edited (guard-protected).
- Decimal money/points: `Decimal`, never float. `10.50 == 10.5` after normalisation — the hash test pins this.
- Every route gets: input model, output model, an OpenAPI summary line, and a test; the discipline is uniform and enforced per service by the OpenAPI meta-tests. Read paths must not import anything from `ingestion`'s AI modules — keep the import graph clean for the AST boundary test.
- Errors fail closed into the review queue; a parsing failure must never produce a frozen record.
