# 04 — Services depth: API completeness + TarifMCP (Block 1)

Read AGENTS.md and CLAUDE.md, then plan before coding.

Goal: TarifCore serves everything the docs promise, and TarifMCP exists. Criteria 16/17 + the course's "machine-readable API protocols for AI" item.

1. **TarifCore completeness:** point-in-time (`?as_of=`) and diff (`/tariffs/{code}/diff?from=&to=`) queries; the FHIR R4 read adapter (ChargeItemDefinition/CodeSystem mapping from the canonical record); pgvector semantic search endpoint (`/search?q=`, multilingual) with the stub embedder offline and e5 behind a flag. OpenAPI summaries on every route.
2. **TarifMCP** (`services/mcp`, FastMCP): `search_tariffs`, `get_tariff`, `explain_crosswalk` — read-only proxies to TarifCore returning frozen records verbatim, with one integration test each. No direct DB access from MCP.
3. **Acceptance criteria artifact** (`docs/arc42/10-quality-requirements.md`): Given/When/Then per use-case from the catalogue, including the determinism acceptance ("no LLM client importable on the value path") and reproducibility acceptance ("identical sources → identical record_hash set").
4. **Test-strategy artifact** (`docs/arc42/`): the written approach — pytest layers, AST boundary test, SQLite mirror + stub embedder offline, TestClient + Testcontainers, console component tests later. One page, criterion 12's exact question.

Constraints: read paths stay free of any AI import (the boundary test must keep passing untouched); no webhooks, no GraphQL, no auth — they are ADR'd out of scope. Coverage on core modules moves toward >80%; quote the figure.

Done means: every documented endpoint exists with a test; MCP tools callable; both artifacts written; CI green. Verifier + determinism-auditor; `/ship`; journal curated.
