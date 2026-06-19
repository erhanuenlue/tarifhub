<div align="center">

<img src="docs/brand/assets/logo-primary.svg" alt="tarifhub" height="84">

**One trustworthy machine interface to Swiss ambulatory tariff data: AI‑assisted above a deterministic freeze line, immutable and versioned below it.**

[![CI](https://github.com/erhanuenlue/tarifhub/actions/workflows/ci.yml/badge.svg)](https://github.com/erhanuenlue/tarifhub/actions/workflows/ci.yml)
[![Docs](https://github.com/erhanuenlue/tarifhub/actions/workflows/docs.yml/badge.svg)](https://erhanuenlue.github.io/tarifhub/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.12-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-Pydantic_v2-009688.svg)
![Postgres](https://img.shields.io/badge/PostgreSQL_16-pgvector-336791.svg)

[Documentation](https://erhanuenlue.github.io/tarifhub/) · [Architecture (arc42)](https://erhanuenlue.github.io/tarifhub/arc42/01-introduction-goals/) · [How it was built](aise-harness/) · [Landing page](https://tarifhub-landing.vercel.app/) · [Survey](https://tarifhub-survey.vercel.app/) · [Pitch deck](https://erhanuenlue.github.io/tarifhub/pitch/)

</div>

---

tarifhub's commercial vision is one trustworthy machine interface to the full breadth of Switzerland's fragmented ambulatory tariff data. The submitted CAS/MVP harmonises two BAG sources, the EAL (Analysenliste) XLSX and the ePL/SL (Spezialitätenliste) FHIR R5 feed, **once**, with AI assistance, into a canonical, versioned, deterministic record, then serves it through a read‑only API, FHIR R4, and MCP tools for AI agents. TARMED and TARDOC remain out of scope for the submitted MVP. It is the capstone project for the **FFHS CAS AI‑Assisted Software Engineering** (due 6 July 2026) and the seed of a commercial platform, on a single codebase.

## The one inviolable rule

> **No AI ever computes or mutates a billing value at serve time.**

AI runs only *pre‑freeze* (filling non‑billing fields with schema‑constrained structured output) and in explain/search seams that never alter a value. Frozen records are immutable: a SHA‑256 `record_hash` over sorted canonical content, every update is a new version, and the audit log is append‑only. A **determinism boundary test** (no LLM client is even *importable* on the value path) keeps CI honest.

## Architecture

Four layers, decoupled by the freeze line:

| Layer | What it does | Where |
|---|---|---|
| **L0 · Ingestion** | AI‑assisted harmonisation: load, parse, map, validate, score, flag, **freeze** | `services/ingestion/` |
| **L1 · Serving** (TarifCore) | Deterministic read API: REST + FHIR R4, point‑in‑time + diff, semantic search | `services/serving/` |
| **L1 · MCP** (TarifMCP) | Read‑only tools (`search_tariffs`, `get_tariff`, `explain_crosswalk`) for AI agents | `services/mcp/` |
| **L3 · Console** (TarifGuard) | Master‑detail search, frozen‑record detail, human review form, labelled AI explain panel | `apps/tarifguard/` |

The database (`db/`, PostgreSQL 16 + pgvector, mirrored in SQLite for offline tests) is the **only** contract between L0 and L1. Deployment manifests (Docker Compose, Helm) live in `deploy/`.

## Quick start (offline, no API key)

The Python services run fully offline by default: a SQLite mirror plus a deterministic stub embedder, no containers, no network.

```bash
# Each service: install and run its test suite
cd services/serving && uv sync && uv run pytest -q
cd ../ingestion    && uv sync && uv run pytest -q
cd ../mcp          && uv sync && uv run pytest -q
cd ../intelligence && uv sync && uv run pytest -q

# The demo console (offline smoke is self-contained)
cd apps/tarifguard && npm install && npm test     # Vitest + Playwright smoke
npm run dev                                        # http://localhost:3000

# The documentation site
mkdocs serve -f docs/mkdocs.yml                    # http://localhost:8000
```

`uv` is the package manager. To run against real Postgres instead of the SQLite mirror: `docker compose -f deploy/docker-compose.yml up -d db` and set `TARIFHUB_DB_URL`. Config is environment‑only: `cp .env.example .env`. No real secret is committed anywhere (`.env*` is git‑ignored; only `.env.example` is tracked).

## Stack

Python 3.12 · FastAPI · Pydantic v2 (one canonical `TariffRecord` end to end) · PostgreSQL 16 + pgvector · Claude schema‑constrained structured output (pre‑freeze only) · Next.js App Router · Docker + Helm · GitHub Actions (ruff, pytest, gitleaks, Trivy, Syft).

## Two repositories in one

This repo holds **both** halves of the project:

- **The graded product + thesis**: `services/`, `apps/`, `db/`, `deploy/`, and the arc42 documentation under `docs/`.
- **The agentic build system that produced it**: documented as a guided tour in **[`aise-harness/`](aise-harness/)**. tarifhub was built with a closed‑loop, multi‑model, human‑gated AI software‑engineering pipeline; that harness (prompts, agents, governance hooks, the live dashboard, the journal) is kept on purpose as criterion‑15 evidence of *how* the work was done.

## Documentation & decisions

The architecture is documented as an arc42 site (MkDocs Material) under `docs/`, published to GitHub Pages via `.github/workflows/docs.yml` at **https://erhanuenlue.github.io/tarifhub/**. Architecture decisions are recorded in `docs/adr/` (19 ADRs). Contributors should read `AGENTS.md` (project facts, layout, the inviolable rule) and `CLAUDE.md` (the working pipeline).

## Scope

The TarifGuard console is a deliberately small demo: no authentication, no patient data, no benchmarking. It demonstrates the platform's concepts and is not a production billing system. Runtime evidence (test output, pipeline results, screenshots) is captured under `docs/`, so the architecture and behaviour can be reviewed directly from the repository.

## License

[MIT](LICENSE) © Erhan Ünlü
