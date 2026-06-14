# Constraints

Constraints TarifHub must satisfy as given; they bound every decision in chapters 04 to 09. The first is the architectural constraint everything else serves:

> **No AI computes or mutates a billing value at serve time.**

| # | Constraint | Rationale |
|---|------------|-----------|
| 1 | **CAS capstone deadline 6 July 2026** | Fixed submission date; scope is cut to what is shippable and gradeable by then. |
| 2 | **Solo engineer** | One toolchain (Python + uv), no coordination overhead; rules out polyglot service stacks. |
| 3 | **Graders review code and documentation only** | Nothing is deployed or executed by graders; runtime evidence must be captured into `docs/` (screenshots, CI links, coverage figures). |
| 4 | **No Java / JVM anywhere** (owner decision, final) | Stack is Python plus a TypeScript console; a second runtime would split the canonical model and the toolchain. |
| 5 | **MVP data sources limited to public BAG feeds** | OAAT/SASIS material is licence-gated; the pipeline is built source-extensible, but only public data ships in the MVP. |
| 6 | **Data residency Switzerland; patient-facing LLM calls de-identified, EU/CH region** | Persistent data stays CH-hosted; the core handles public data only, so revFADP bites only at the app layer ([ADR-012](../adr/012-data-residency-llm-region.md)). |
| 7 | **Canonical field set locked, additive-only** | The record model is the integration contract between services; breaking changes need a new ADR first ([ADR-003](../adr/003-canonical-record-model.md)). |
| 8 | **Env-only configuration** (`TARIFHUB_DB_URL`, `TARIFHUB_REVIEW_THRESHOLD`, `ANTHROPIC_API_KEY`) | Twelve-factor; no config files to drift between dev, CI and containers. Without an API key, `ai_map` falls back to deterministic `map_raw`. |
| 9 | **Tests offline by default** (SQLite mirror + stub embedder) | `pytest -q` runs without containers, network or API keys: fast CI and reproducible local runs. |
| 10 | **Conventional Commits, squash-merge green PRs only** | Linear, machine-readable history; nothing lands red, since CI gates (ruff, pytest, gitleaks, Trivy) are the merge condition. |

Constraint 6 describes the design boundary for patient-facing apps; the de-identification module exists in the console today, while the L3 apps that would carry patient data are post-CAS.
