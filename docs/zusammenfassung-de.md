# Summary

## Vision and problem

Switzerland's ambulatory tariff data is fragmented. Around 110 active tariff types
appear across more than 20 sources in the XLSX, XML, PDF and FHIR formats, without a
single authoritative machine interface. The downstream costs add up: every PIS/HIS
vendor reimplements parsing per source, tariff values reach the billing systems without
provable provenance, version changes are reconciled by hand, and an undetected mapping
error silently becomes an incorrect invoice. TarifHub consolidates this data into a
canonical, versioned and deterministic interface. The target audience comprises PIS/HIS
vendors as machine consumers (REST/OpenAPI and FHIR R4), the tariff experts who review
uncertain mappings, practice users who look things up in the TarifGuard console, and AI
agents that read released data over MCP. The core is the assurance that a delivered value
is provably exactly the value that was reviewed and frozen.

## Architecture

The system is organized into four layers, separated by an enforced freeze line. Above the
line lies the AI-assisted harmonisation (L0): adapters, parsers, the mapping into the
canonical `TariffRecord` data model, the deterministic validation and the scoring. Below
the line lies the deterministic, read-only serving API (L1, TarifCore with REST and FHIR
R4, point-in-time and diff queries) together with the read-only MCP tools (TarifMCP). Above
those sit the rules (L2, after the CAS) and the demo console (L3, TarifGuard). Frozen records
are immutable: a SHA-256 `record_hash` over the sorted canonical content seals them, updates
create new versions, and the `audit_log` is append-only. Persistence and multilingual semantic
search run on PostgreSQL 16 with pgvector (HNSW, cosine, multilingual-e5, 1024 dimensions); a
SQLite mirror serves the offline tests.

## AI use

AI acts at only two clearly bounded points. First, before the freeze in `ai_map`: a single
seam fills exclusively the missing, non-billing-relevant fields with schema-bound structured
output (fill-only); if an API key is missing, deterministic `map_raw` takes over. Second, in
search and explain seams that only read values and never change them. The build itself is
multi-agent: model-bound workers implement and review, and an independent second model (Codex
gpt-5.5), as a second model family, reviews every pull request. For example, the second model
caught a metadata write that broke the idempotence of re-import, as well as a `json.loads` on a
Postgres JSONB column that would have made every response fail with status 500, even though 28
green tests missed both.

## Conclusion key message

It is not the AI that makes billing data controllable, but the boundary around it. An enforced,
tested determinism boundary (an AST test in CI that forbids any LLM client on the value path,
plus the `guard_frozen` hook that actually stopped a faulty edit below the line) is exactly what
makes the use of AI on billing data accountable and usable in the first place. Above the line, AI
may deliver speed and breadth; below the line, the value stays deterministic, traceable and under
human responsibility.
