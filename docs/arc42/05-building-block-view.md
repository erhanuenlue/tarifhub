# 5. Building Block View

## Level 1 — one platform, four layers

TarifHub is one platform organized as four layers around the freeze line. Each layer has
a product/brand name and maps to one or more sub-systems.

| Layer | Brand name | Building block(s) | Responsibility |
|---|---|---|---|
| **L0** | Harmonization Engine | Ingestion service (Python) | Pre-freeze, AI-assisted pipeline → freeze + version + hash + lineage; admin/read API. |
| **L1** | TarifCore API + TarifMCP | Serving service (Quarkus) + MCP server (Python) | Deterministic read API over frozen records + semantic search; read-only MCP tools for AI agents. |
| **L2** | TarifIQ | Intelligence service (Python) | Deterministic combinability/cumulation rules, TARMED↔TARDOC cross-walk, rule validation. AI only *suggests* rules pre-freeze. |
| **L3** | TarifGuard · KassenFlow · MeldePilot | Three Next.js apps | Practice / payer-correspondence / mandatory-reporting apps — read-only over L1 + L2. |
| — | — | PostgreSQL + pgvector | System of record (canonical rows, audit log, embeddings). |

L0 and L1's serving sit either side of the freeze line. Everything else — TarifMCP, L2
TarifIQ, and the L3 apps — is a **read-only consumer** downstream of the line: it relays
frozen records verbatim or reasons about relationships between codes, and never computes
or mutates a billing value. L2's rule *evaluation* is deterministic; its single AI seam
only *suggests* candidate rules pre-freeze.

## Level 2 — ingestion service

```
tarifhub_ingest/
├─ main.py            FastAPI (GET /health,/tariffs,/tariffs/{code}; POST /ingest/sample) — no LLM import
├─ ingestion/         pipeline.py (orchestration), source_loader.py
├─ parsers/           xlsx_parser (EAL), fhir_parser (ePL)
├─ mappers/           tariff_mapper: rules + replaceable ai_map() seam (pre-freeze only)
├─ confidence/        scorer: deterministic confidence in [0,1]
├─ validators/        tariff_validator: pre-freeze validation
├─ versioning/        freeze_record: PROTECTED, deterministic hash
├─ audit/             audit_logger: PROTECTED, append-only lineage
├─ embeddings/        embedder: port + offline stub (e5 in prod)
├─ storage/           db (SQLite/Postgres), tariff_repository
└─ models/            tariff_model: canonical Pydantic model
```

The single AI seam is `mappers.tariff_mapper.ai_map` (import-guarded, offline-safe).
`versioning/` and `audit/` are protected modules.

## Level 2 — serving service

```
ch.tarifhub.serving/
├─ TariffRecordEntity   read-only Panache projection of the frozen `tariff` table
├─ TariffRepository     read queries + pgvector nearest-neighbour helper
├─ TariffResource       GET /api/v1/tariffs[...] (JSON/XML) — value path, no AI
└─ search/              SemanticSearchService + SearchResource — the ONLY langchain4j user
```

## Level 2 — MCP server

```
services/mcp/
├─ server.py    FastMCP app + 3 read-only tools, each a thin proxy to serving:
│                 search_tariffs → GET /api/v1/search
│                 get_tariff     → GET /api/v1/tariffs/{system}/{code}
│                 explain_crosswalk → GET /api/v1/explain
└─ config.py    SERVING_BASE_URL + transport (streamable-http / stdio); httpx client
```

No DB, no model, no arithmetic: tools return serving's frozen records verbatim and
surface errors rather than fabricating a value.

## Level 2 — TarifGuard

```
apps/tarifguard/
├─ app/                three screens (search, coding-check, explain) + a small landing
│  └─ api/             server-side route handlers (keep SERVING_BASE_URL + de-ident server-side)
├─ components/         NavBar, TariffCard, DisclaimerBanner
└─ lib/
   ├─ api.ts           typed, server-only client for the serving API
   └─ deident.ts       de-identification choke point — the ONLY LLM-payload builder (rule 7)
```

Values shown in the UI are unaltered frozen records. The `/explain` flow de-identifies
input via `lib/deident.ts` before anything reaches the EU-routed explanation seam.

## Level 2 — TarifIQ (intelligence service, L2)

```
tarifiq/
├─ main.py                    FastAPI: /health, POST /v1/combinability-check,
│                               GET /v1/crosswalk/{tarmed_code}, POST /v1/validate — no LLM import
├─ config.py                  12-factor settings (offline-first; SERVING_BASE_URL when live)
├─ models/rule_model.py       Pydantic contracts (rules carry NO billing value)
├─ rules/combinability.py     deterministic EXCLUSIVE / REQUIRES / CUMULATION_LIMIT over the
│                               frozen, content-hashed rule set
├─ crosswalk/tarmed_tardoc.py deterministic cross-walk lookup + replaceable ai_rule_suggest() seam
├─ validators/rule_validator.py  structural + referential validation of a candidate rule pre-freeze
└─ store/frozen_client.py     reads frozen tariff facts from serving (httpx) + offline stub
```

Rule **evaluation is deterministic**: each endpoint is a pure function of the request and
the frozen rule/cross-walk tables (each versioned and SHA-256 content-hashed, mirroring
the L1 freeze discipline). The single AI seam, `crosswalk.tarmed_tardoc.ai_rule_suggest`,
only *suggests* a candidate cross-walk entry pre-freeze (a human validates it via
`POST /v1/validate` before freezing) and is intentionally **not** wired into any endpoint.
An AST boundary test (`tests/test_determinism_boundary.py`) asserts the value path
(`main.py`, `rules`, `crosswalk`, `validators`, `store`) imports no LLM client.

## Level 2 — KassenFlow & MeldePilot (L3 app stubs)

```
apps/kassenflow/        (payer correspondence / Kostengutsprache)
apps/meldepilot/        (mandatory reporting / quality data: BFS/MARS, ANQ, interRAI/BESA)
├─ app/layout.tsx       shell + preview banner
├─ app/page.tsx         purpose + "scope / coming in development" (planned screens listed)
├─ lib/deident.ts       de-identification choke point — the ONLY LLM-payload builder
└─ Dockerfile           multi-stage Node build (Next standalone)
```

Both are **skeleton stubs**: they ship their planned scope (a "coming in development"
screen with 2–3 planned screens), not working features. Like TarifGuard they are thin,
read-only L3 consumers over L1 (serving) and L2 (TarifIQ); they compute no billing value,
and each carries the same de-identification boundary (`lib/deident.ts`) as the only
sanctioned builder of an LLM-bound payload. KassenFlow targets insurer correspondence,
Kostengutsprache, and MiGeL/medication approvals across multiple payers; MeldePilot
targets BFS/MARS submissions, ANQ quality measures, and interRAI/BESA → cantonal routing.
