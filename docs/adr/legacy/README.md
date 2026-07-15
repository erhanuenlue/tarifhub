# Legacy ADRs (repo-era numbering)

The ADRs in `docs/adr/` (**001 through 020**) follow the **Architecture v2.1
consolidated register** (see `AGENTS.md`: ADR-001 Python-first, ADR-013 demo scope).
That register was assembled in June 2026 by renumbering and consolidating all decisions
made up to that point into one coherent sequence; later decisions append to it.

The eight files in this directory are the **honest, contemporaneous originals**: the
decisions exactly as they were written while the work happened, under the repo's
original numbering. They are kept verbatim (apart from the "Superseded numbering"
banner at the top of each) because contemporaneity is part of the evidence — they show
what was decided, when, and what was later corrected (e.g. the Quarkus serving decision
that the no-JVM ruling reversed, and the "temp 0" wording that legacy ADR-008 replaced
with an architectural-determinism guarantee).

**Do not cite these by their legacy numbers in new documents.** Cite the consolidated
register in `docs/adr/` and use the mapping below.

## Mapping: legacy number → consolidated register

| Legacy ADR | Title | Fate in the consolidated register |
|---|---|---|
| 001 | [Two-service split](001-two-service-split.md) | Carried into register **ADR-002** (and ADR-001) |
| 002 | [AI before freeze only](002-ai-before-freeze.md) | Refined into **ADR-005** (and ADR-004) |
| 003 | [Canonical tariff model](003-canonical-model.md) | Restated as **ADR-003** |
| 004 | [Quarkus for deterministic serving](004-quarkus-serving.md) | Superseded by **ADR-001** (Python-first, no JVM) |
| 005 | [Merge TarifGuard, add MCP, de-identification boundary](005-tarifguard-merge-and-mcp.md) | Extended by **ADR-008** and **ADR-012** (console scope → **ADR-013**) |
| 006 | [One platform, four layers](006-four-layer-product.md) | Layering carried into the register's context (Architecture v2.1 §4) |
| 007 | [Python-first serving (FastAPI), no JVM](007-python-first-serving.md) | Became **ADR-001** |
| 008 | [Live `ai_map` via Claude structured output](008-ai-map-live.md) | Architectural-determinism correction carried into **ADR-005** |

All of these decisions orbit the one inviolable rule, which is unchanged across both
numbering eras: **"No AI computes or mutates a billing value at serve time."**
