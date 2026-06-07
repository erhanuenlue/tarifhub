# 9. Architecture Decisions

The significant decisions are recorded as ADRs:

- [ADR-001 — Two-service split (Python ingestion + Quarkus serving)](../adr/001-two-service-split.md)
- [ADR-002 — AI before freeze only](../adr/002-ai-before-freeze.md)
- [ADR-003 — Canonical tariff model](../adr/003-canonical-model.md)
- [ADR-004 — Quarkus for deterministic serving](../adr/004-quarkus-serving.md)
- [ADR-005 — Merge TarifGuard, add an MCP server, fix the de-identification boundary](../adr/005-tarifguard-merge-and-mcp.md)
- [ADR-006 — One platform, four layers (TarifIQ + the app suite)](../adr/006-four-layer-product.md)

New decisions that touch the canonical model, the freeze rule, or the service boundary
must be captured as a new ADR before implementation.
