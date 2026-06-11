# ADR-001 — Python-first core; Next.js only at L3

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
Framework choice is free — the CAS rubric is stack-neutral, and the owner has ruled out Java/JVM. The system is a read-mostly, cache-friendly API over a write-time-heavy AI pipeline, built and run by one engineer against a tight deadline. The canonical `TariffRecord` model already exists in Python, and the earlier hybrid plan (Quarkus serving next to Python ingestion) had produced exactly the model drift a two-toolchain core invites.

## Decision
We use Python 3.12 + FastAPI for the entire core (L0 ingestion, L1 serving + MCP, L2 intelligence) and Next.js only for L3 app front-ends, making the MVP single-language Python.

## Alternatives weighed
- **Keep Quarkus serving as-built** — a valid option (the port had a real reconciliation cost); rejected for the solo-toolchain cost: two build chains, two model definitions, Python↔Panache drift.
- **TypeScript/Node end-to-end** — rejected; the AI/data ecosystem and the existing canonical Pydantic model live in Python, and a rewrite buys nothing here.

## Consequences
- (+) One canonical Pydantic model reused end-to-end — the Python↔Panache drift the repo flagged is structurally impossible.
- (+) One toolchain: simpler CI (no JDK/Maven, no native-image step), one dependency manager (uv), one test runner, a unified AI and observability story.
- (–) Forgoes JVM strengths (native-image cold start, compile-time static typing) — immaterial for this read-mostly workload. Revisit only if serving latency or throughput demands exceed what FastAPI + PostgreSQL can deliver.

*Lineage: supersedes legacy/004-quarkus-serving.md; refines legacy/001-two-service-split.md (the split stands, both sides Python); materialises legacy/007-python-first-serving.md.*
