# TarifGuard

The practice-facing front end of the TarifHub platform: a thin **Next.js (App Router,
React + Tailwind)** web app that consumes the deterministic serving API. Three screens,
no billing logic of its own.

| Screen | Route | Talks to |
|---|---|---|
| Tariff search | `/search` | `GET /api/v1/search` (semantic search over frozen records) |
| Coding check | `/coding-check` | `POST /api/v1/coding-check` (combinability/validation), with a per-position `GET /api/v1/tariffs/{system}/{code}` fallback |
| Explain | `/explain` | `POST /api/v1/explain` (NL explanation / TARMED↔TARDOC cross-walk over de-identified input) |

## Two boundaries this app must respect

1. **Determinism.** TarifGuard is read-only over the serving service. Every value it
   shows (tax points, price, validity) is an unaltered frozen record relayed verbatim.
   It never computes, rounds, or mutates a billing value, and never decides
   combinability itself — that is the deterministic backend's job.
2. **De-identification.** Patient identifiers never leave Swiss infrastructure. The
   `/explain` flow scrubs input with `lib/deident.ts` — the **only** module allowed to
   build an LLM-bound payload — before anything is forwarded. The LLM call itself is
   served by the backend and routed via AWS Bedrock EU / Google Vertex AI EU. See
   `AGENTS.md` rule 7.

## Layout

```
apps/tarifguard/
├─ app/
│  ├─ layout.tsx            shell + nav
│  ├─ page.tsx              landing (links to the 3 screens)
│  ├─ search/page.tsx       semantic search screen
│  ├─ coding-check/page.tsx coding-check screen
│  ├─ explain/page.tsx      de-identified explanation screen
│  └─ api/                  server-side proxies (keep SERVING_BASE_URL + de-ident server-side)
│     ├─ search/route.ts
│     ├─ coding-check/route.ts
│     └─ explain/route.ts
├─ components/              NavBar, TariffCard, DisclaimerBanner
├─ lib/
│  ├─ api.ts                typed, server-only client for the serving API
│  └─ deident.ts            de-identification choke point (the only LLM-payload builder)
└─ Dockerfile              multi-stage Node build (Next standalone)
```

The browser never holds `SERVING_BASE_URL` and never builds an LLM payload: the pages
call same-origin handlers under `app/api/*`, which run server-side and use `lib/api.ts`
(and, for `/explain`, `lib/deident.ts`).

## Run locally

Requires Node 20+ and a running serving API (`cd services/serving && mvn quarkus:dev`).

```bash
cd apps/tarifguard
cp .env.example .env.local         # set SERVING_BASE_URL (default http://localhost:8080)
npm install                        # generates package-lock.json (commit it for `npm ci`/CI)
npm run dev                        # http://localhost:3000
```

`npm run lint` and `npm run build` are the CI gates (see `.github/workflows/ci.yml`).

## Environment

| Variable | Purpose |
|---|---|
| `SERVING_BASE_URL` | Base URL of the deterministic serving API. Server-side only; never exposed to the browser. |

LLM provider/region for the `/explain` seam are configured on the **backend**, not here
(see `.env.example` for operator context).
