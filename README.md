# TarifHub

AI-assisted harmonization platform for Swiss ambulatory tariff data. TarifHub ingests
public tariff sources (BAG EAL, BAG ePL, …), harmonizes them through an AI-assisted,
human-in-the-loop pipeline, **freezes** each record as an immutable, versioned,
SHA-256-hashed fact, and serves those facts deterministically over adaptive APIs.

**The architectural backbone is the freeze line.** AI may assist *before* the freeze
(format recognition, field mapping, multilingual normalization, anomaly flagging) and
for *search/discovery/explanation* in serving — but **AI never computes or mutates a
billing-relevant value**. Every authoritative value returned is an unaltered frozen
record. See `AGENTS.md` for the seven non-negotiable rules.

## Architecture — one platform, four layers

TarifHub is **one platform** organized as **four layers** around the freeze line. Each
layer has a product/brand name and maps to one or more independently containerized
sub-systems:

| Layer | Brand name | Sub-system(s) | Stack | Role |
|---|---|---|---|---|
| **L0** | **Harmonization Engine** | `services/ingestion` | Python 3.12, FastAPI, Pydantic v2 | Ingest → AI-map (pre-freeze) → confidence → human review → **FREEZE + VERSION + HASH + LINEAGE** → canonical store |
| **L1** | **TarifCore API** + **TarifMCP** | `services/serving` + `services/mcp` | Java 21 / Quarkus; Python / FastMCP | Deterministic REST (JSON/XML) + semantic search over frozen records; read-only MCP tools for AI agents |
| **L2** | **TarifIQ** | `services/intelligence` | Python 3.12, FastAPI | Deterministic combinability/cumulation rules, **TARMED↔TARDOC cross-walk**, rule validation. AI only *suggests* rules pre-freeze |
| **L3** | **TarifGuard · KassenFlow · MeldePilot** | `apps/tarifguard`, `apps/kassenflow`, `apps/meldepilot` | Next.js (App Router), React, Tailwind | Practice / payer / reporting apps — read-only over L1 + L2, de-identified LLM boundary |

Shared: `db/` (PostgreSQL 16 + pgvector schema), `deploy/helm/` (Kubernetes), `docs/`
(arc42 site + C4 diagrams + ADRs), `scripts/` (helpers).

```
            ┌──────────────────────────── THE FREEZE LINE ────────────────────────────┐
 sources ─▶ │ L0 Harmonization Engine (ingestion): load→map→…→FREEZE+HASH+VERSION       │ ─▶ canonical store
            │      (AI assists pre-freeze only)            │  NO AI COMPUTES A VALUE BEYOND HERE
            └──────────────────────────────────────────────┼──────────────────────────┘
                                                            ▼
                              L1 TarifCore API (serving): deterministic REST + semantic search
                                                            │
                         ┌──────────────────┬───────────────┼───────────────────────────┐
                         ▼                  ▼               ▼                              ▼
                   TarifMCP (mcp)   L2 TarifIQ (intelligence)                       (read-only)
                   read-only tools  deterministic rules /     ───────────────▶  L3 apps: TarifGuard,
                   for AI agents    cross-walk / validation                      KassenFlow, MeldePilot
```

Everything downstream of the freeze line is read-only over frozen records: L1 serves
them verbatim, L2 reasons about *relationships between codes* (never prices), and L3 apps
relay frozen values and L2 verdicts. AI may only assist **before** the freeze
(L0 mapping, L2 rule *suggestion*) or for search/explain — it never computes or mutates a
billing value. Any LLM use in an L3 app is on de-identified data, confined to that app's
`lib/deident.ts` (see `AGENTS.md` rule 7); see `docs/adr/006-four-layer-product.md`.

## Run the ingestion pipeline & API locally (offline)

Requires Python 3.12. No network, no Postgres, no LLM key needed — SQLite by default.

```bash
cd services/ingestion
python3 -m venv .venv && . .venv/bin/activate
pip install -e .

# Start the admin/read API
tarifhub-ingest                      # or: uvicorn tarifhub_ingest.main:app --reload

# In another shell: ingest the bundled sample sources, then read frozen records
curl -X POST localhost:8000/ingest/sample
curl localhost:8000/tariffs
curl localhost:8000/tariffs/0010.00
```

## Run the tests

```bash
cd services/ingestion && pytest -q          # fully offline
```

## Run the serving service

```bash
docker-compose up -d db                      # Postgres 16 + pgvector
cd services/serving && mvn quarkus:dev       # http://localhost:8080/q/swagger-ui
# Endpoints: GET /api/v1/tariffs , GET /api/v1/tariffs/{system}/{code} , GET /api/v1/search?q=...
```

Semantic search ranks frozen records via a langchain4j embedding model (multilingual-e5,
matching the pgvector column). The optional `QUARKUS_LANGCHAIN4J_ANTHROPIC_API_KEY` adds
natural-language explanations over the frozen text — it never fabricates or mutates values.

## Run the MCP server

Read-only MCP tools (`search_tariffs`, `get_tariff`, `explain_crosswalk`) over serving.

```bash
cd services/mcp
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
SERVING_BASE_URL=http://localhost:8080 python server.py   # streamable-HTTP on :8090
cd services/mcp && pytest -q                                # fully offline (serving is mocked)
```

## Run the intelligence service (TarifIQ)

The L2 service — deterministic combinability checks, TARMED↔TARDOC cross-walk, and rule
validation. Runs fully offline (bundled frozen rule/cross-walk tables); set
`TARIFIQ_OFFLINE=0` + `SERVING_BASE_URL` to read live frozen records from serving.

```bash
cd services/intelligence
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q                                  # fully offline

tarifiq                                    # uvicorn tarifiq.main:app on :8070
curl -X POST localhost:8070/v1/combinability-check -H 'content-type: application/json' \
  -d '{"system":"TARDOC","positions":[{"code":"AA.00.0010"},{"code":"AA.00.0030"}]}'
curl localhost:8070/v1/crosswalk/00.0010
```

TarifIQ *evaluates* rules deterministically; AI may only *suggest* a candidate rule
pre-freeze (the replaceable `ai_rule_suggest` seam), which a human validates via
`POST /v1/validate` before freezing. No endpoint calls a model.

## Run the TarifGuard front end

The practice-facing Next.js app (search / coding-check / explain), read-only over serving.

```bash
cd apps/tarifguard
cp .env.example .env.local            # set SERVING_BASE_URL (default http://localhost:8080)
npm install && npm run dev            # http://localhost:3000
```

TarifGuard never computes a billing value, and the only code that may build an
LLM-bound payload is `lib/deident.ts` (de-identified inputs, EU-routed model).

## Run the KassenFlow / MeldePilot app stubs

Two further L3 apps, currently **skeleton stubs** that ship their planned scope (a
"coming in development" screen), not working features. **KassenFlow** automates payer
correspondence / Kostengutsprache; **MeldePilot** automates mandatory reporting and
quality data (BFS/MARS, ANQ, interRAI/BESA → cantonal). Both are read-only over L1 + L2
and carry the same de-identification boundary (`lib/deident.ts`).

```bash
cd apps/kassenflow      # or: apps/meldepilot
cp .env.example .env.local        # set SERVING_BASE_URL + TARIFIQ_BASE_URL
npm install && npm run dev        # KassenFlow :3001 · MeldePilot :3002
```

## Local stack (Postgres + MinIO)

```bash
cp .env.example .env
docker-compose up                            # db = pgvector/pgvector:pg16 , minio
./scripts/init_db.sh                          # apply db/schema.sql + migrations
```

## Deploy to Kubernetes (Helm)

```bash
helm install tarifhub deploy/helm/tarifhub
# or with overrides:  helm install tarifhub deploy/helm/tarifhub -f my-values.yaml
```

## Publish the arc42 documentation site

```bash
pip install mkdocs-material
mkdocs serve -f docs/mkdocs.yml               # preview at http://localhost:8000
mkdocs gh-deploy -f docs/mkdocs.yml           # publish to GitHub Pages
```

## Layout

```
tarifhub/
├─ services/ingestion/    L0 Harmonization Engine — Python pipeline (pre-freeze, AI-assisted)
├─ services/serving/      L1 TarifCore API — Quarkus serving (post-freeze, deterministic)
├─ services/mcp/          L1 TarifMCP — Python MCP server (read-only tools, for AI agents)
├─ services/intelligence/ L2 TarifIQ — Python rules / cross-walk / validation (deterministic)
├─ apps/tarifguard/       L3 TarifGuard — Next.js (search / coding-check / explain), read-only
├─ apps/kassenflow/       L3 KassenFlow — Next.js stub (payer correspondence / Kostengutsprache)
├─ apps/meldepilot/       L3 MeldePilot — Next.js stub (mandatory reporting / quality data)
├─ db/                    PostgreSQL schema + migrations (canonical model + pgvector + audit)
├─ deploy/helm/tarifhub/  Helm chart (ingestion, serving, mcp, intelligence, the 3 apps, postgres, ingress)
├─ docs/                  arc42 site (MkDocs Material), C4 diagrams, ADRs
├─ scripts/               init_db.sh, run_ingestion.sh, run_serving.sh
├─ .claude/               Claude Code hooks (tests on Stop, frozen-path guard)
├─ AGENTS.md  CLAUDE.md   Working agreement + the seven non-negotiable rules
└─ docker-compose.yml     Postgres+pgvector, MinIO (+ services profile: intelligence; apps profile: the apps + mcp)
```
