# 09 · architecture decisions

Consolidated ADR register, adopted from Architecture v2.1 (2026-06).
Each ADR is at most one page on the house template.

| # | Decision | Status | ADR |
|---|----------|--------|-----|
| 001 | Build the entire core (L0-L2) in Python 3.12 + FastAPI; Next.js only at L3 | Accepted | [001](../adr/001-python-first-core.md) |
| 002 | Split services along the freeze line: ingestion (write, pre-freeze) and serving (read, post-freeze) share only the database contract | Accepted | [002](../adr/002-freeze-line-decomposition.md) |
| 003 | Use one canonical, versioned, immutable record model with a locked, additive-only field set | Accepted | [003](../adr/003-canonical-record-model.md) |
| 004 | Freeze reviewed records under a SHA-256 content hash with append-only audit-log lineage | Accepted | [004](../adr/004-freeze-content-hash-lineage.md) |
| 005 | Keep exactly one live-AI seam (`ai_map`), pre-freeze, non-billing fields only, with human review below the confidence threshold | Accepted | [005](../adr/005-single-ai-seam.md) |
| 006 | Use PostgreSQL 16 + pgvector as the single system of record and vector index | Accepted | [006](../adr/006-postgres-pgvector.md) |
| 007 | Store immutable raw source artifacts in S3-compatible object storage, referenced from the audit log | Accepted | [007](../adr/007-object-store-raw-artifacts.md) |
| 008 | Serve REST + GraphQL + FHIR R4 + XML + MCP over one shared service layer | Accepted | [008](../adr/008-api-styles.md) |
| 009 | Ship each sub-system as a Docker image, deployed via Helm to Kubernetes; docker-compose for local development | Accepted | [009](../adr/009-docker-kubernetes-helm.md) |
| 010 | Run GitHub Actions CI/CD with DevSecOps gates: gitleaks, Trivy, Syft SBOM, images to GHCR | Accepted | [010](../adr/010-github-actions-devsecops.md) |
| 011 | Standardise observability on OpenTelemetry → Prometheus/Grafana, with Sentry for errors | Accepted | [011](../adr/011-opentelemetry-observability.md) |
| 012 | Host persistent data in Switzerland; L3 de-identifies server-side and routes LLM calls via an EU/CH model region | Accepted | [012](../adr/012-data-residency-llm-region.md) |
| 013 | TarifGuard console demo limited to master-detail + review form + labelled explain panel; no auth, no patient data | Accepted | [013](../adr/013-demo-scope.md) |
| 014 | arc42-light retained as the documentation framework over Diátaxis, pure C4+ADR, and Starlight | Accepted | [014](../adr/014-arc42-light.md) |
| 015 | Ingest the BAG ePL Spezialitätenliste (FHIR R5 NDJSON) per reimbursed package, keyed by GTIN, retail price as the canonical value, money-only | Accepted | [015](../adr/015-epl-sl-fhir-ingestion.md) |
| 016 | Quantize billing values to the canonical NUMERIC scales pre-freeze so stored bytes == hashed bytes on every engine; lossy values fail closed to review | Accepted | [016](../adr/016-decimal-scale-contract.md) |
| 017 | Search ranks offline via deterministic in-process cosine on SQLite (pgvector on Postgres); `/api/v1/explain` is live, deterministic and record-grounded, with no LLM on the serve path | Accepted | [017](../adr/017-deterministic-search-fallback-explain.md) |

## Legacy register

The pre-register repo ADRs live in [adr/legacy/](../adr/legacy/README.md) together
with the renumbering map from repo-era numbers to this register. They are kept
verbatim as contemporaneous evidence of the decision history, not as current policy.

All register entries follow the house [template](../adr/template.md).
