# ADR-002: Service decomposition along the freeze line

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
The platform's one inviolable rule, "No AI computes or mutates a billing value at serve time", should be physically enforceable, not a code convention. Independently deployable sub-systems are also a CAS criterion and an operational good. The AI-rich harmonisation stage (write-time) and the deterministic serving stage (read-time) have opposite quality profiles and scaling behaviour.

## Decision
We decompose the platform into separate, independently containerised sub-systems: ingestion (write, pre-freeze) and serving (read, post-freeze) sharing only the database contract, plus MCP, intelligence, and the apps, with no chatty RPC between the write and read sides.

## Alternatives weighed
- **Monolith**: one deployable would mix pre-freeze AI code with the serving value path, reducing the freeze line to a convention inside a single process. Simpler ops doesn't pay for that.
- **RPC between write and read sides**: rejected. It couples the services at runtime when the set of frozen records in PostgreSQL is already a complete, stable contract.

## Consequences
- (+) The freeze line maps onto a process boundary: the serving container ships no LLM client, and the AST boundary test plus the image contents enforce the rule mechanically.
- (+) Sub-systems scale, deploy and fail independently: the read side stays up while ingestion changes.
- (-) The shared schema (ADR-003) becomes the integration contract and must stay stable. Every schema change is a cross-service coordination. Revisit if a use case genuinely needs richer write/read interaction than the shared database can express.

*Lineage: refines legacy/001-two-service-split.md (keeps the split, drops its Quarkus serving side per ADR-001).*
