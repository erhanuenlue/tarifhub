# tarifhub — knowledge index (auto-generated)

> Rebuilt by the `brain_sync` hook at every session end (2026-06-13 12:30). Do not edit by hand — edit the sources.

## Decisions (ADRs)

- [[001-python-first-core|ADR-001 — Python-first core; Next.js only at L3]]
- [[002-freeze-line-decomposition|ADR-002 — Service decomposition along the freeze line]]
- [[003-canonical-record-model|ADR-003 — Canonical, versioned, immutable record model]]
- [[004-freeze-content-hash-lineage|ADR-004 — Freeze, content-hash and lineage as the determinism anchor]]
- [[005-single-ai-seam|ADR-005 — Single AI seam (ai_map) with human-in-the-loop]]
- [[006-postgres-pgvector|ADR-006 — PostgreSQL 16 + pgvector as the single store]]
- [[007-object-store-raw-artifacts|ADR-007 — S3-compatible object store for raw source artifacts]]
- [[008-api-styles|ADR-008 — API styles: REST primary, plus GraphQL, FHIR R4, XML and MCP]]
- [[009-docker-kubernetes-helm|ADR-009 — Docker images + Kubernetes via Helm; compose for local]]
- [[010-github-actions-devsecops|ADR-010 — GitHub Actions CI/CD with DevSecOps gates]]
- [[011-opentelemetry-observability|ADR-011 — OpenTelemetry-based observability]]
- [[012-data-residency-llm-region|ADR-012 — Data residency in Switzerland; LLM region boundary for patient data]]
- [[013-demo-scope|ADR-013 — TarifGuard console demo scope: master-detail, review form, explain panel]]
- [[014-arc42-light|ADR-014 — arc42-light retained as the documentation framework]]
- [[015-epl-sl-fhir-ingestion|ADR-015 — BAG ePL Spezialitätenliste (FHIR R5) ingestion]]
- [[016-decimal-scale-contract|ADR-016 — Canonical Decimal scale contract (stored bytes == hashed bytes)]]
- [[017-deterministic-search-fallback-explain|ADR-017 — Deterministic offline search fallback and record-grounded explain endpoint]]
- [[018-orchestrator-model-lifecycle|ADR-018: Orchestrator model lifecycle (Fable 5 until 22 Jun 2026, then Opus 4.8)]]

## AI-workflow journal (CAS criterion 15 — contemporaneous)

- **3 entries.** Latest:
  - [[2026-06-11]]
  - [[2026-06-12]]
  - [[2026-06-13]]

## Reflection material

- [[vault-rules|Vault rules — what feeds which criterion]]
- [[decision-matrix|Decision matrix — Vibe vs Spec-Driven vs Agentic]]
- [[fazit-notes|Fazit notes (raw, running)]] — 1 observations
- [[LEARNINGS|LEARNINGS.md (criterion 9)]] — 19 items

## Architecture (source of truth)

- arc42: [[01-introduction-goals|§1]] · [[02-constraints|§2]] · [[03-context-scope|§3]] · [[04-solution-strategy|§4]] · [[05-building-block-view|§5]] · [[06-runtime-view|§6]] · [[07-deployment-view|§7]] · [[08-crosscutting-concepts|§8]] · [[09-architecture-decisions|§9]] · [[10-quality-requirements|§10]] · [[11-risks-technical-debt|§11]] · [[12-glossary|§12]] · [[13-test-strategy|§13]]  — site: `mkdocs serve -f docs/mkdocs.yml`
- Last docs change: 2026-06-13 · feat(console): Block-05 TarifGuard console (master-detail, review form, explain panel) (#16)
