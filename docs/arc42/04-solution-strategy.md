# 04 · solution strategy

The load-bearing decision is the **freeze line**. AI-assisted harmonisation runs strictly *before* it (the `ai_map` seam: structured output, fill-only on non-billing fields, deterministic gap-gate and fallback); everything *below* it (freezing, versioning, serving) is deterministic and read-only. The line is physical, not conventional: it is a process boundary between two services, and it enforces the rule:

> **No AI computes or mutates a billing value at serve time.**

| Decision | Rationale | ADR |
|----------|-----------|-----|
| Four-layer product cut: L0 ingestion → L1 serving + MCP → L2 intelligence (post-CAS) → L3 apps | Each layer consumes only the one below; CAS scope stops at L1 plus a thin L3 console | [ADR-013](../adr/013-demo-scope.md) |
| Python-first single-language core | One canonical Pydantic model end-to-end, one toolchain for one engineer; TypeScript only in the console | [ADR-001](../adr/001-python-first-core.md) |
| Two services split on the freeze line, the database as the only contract | The AI/deterministic boundary becomes independently deployable processes; no RPC between write and read sides | [ADR-002](../adr/002-freeze-line-decomposition.md) |
| One canonical, immutable record model + SHA-256 content-hash freeze | Locked additive-only field set as the integration contract; frozen records are tamper-evident, updates are new versions | [ADR-003](../adr/003-canonical-record-model.md), [ADR-004](../adr/004-freeze-content-hash-lineage.md) |
| Exactly one AI seam with human-in-the-loop review | All live AI funnels through `ai_map` pre-freeze; low-confidence proposals route to a human reviewer | [ADR-005](../adr/005-single-ai-seam.md) |
| PostgreSQL 16 + pgvector as the single store for rows **and** vectors | Relational integrity plus multilingual semantic search in one CH-hostable engine; no separate vector database | [ADR-006](../adr/006-postgres-pgvector.md) |

How the quality goals are reached:

- **Determinism:** an AST boundary test in CI asserts no LLM client is importable on the value path; guard hooks protect the frozen modules.
- **Reproducibility:** content-hash idempotency: re-ingesting identical source content yields the same `record_hash`, never a duplicate.
- **Auditability:** every state change is appended to an immutable `audit_log`; frozen records carry their lineage.
