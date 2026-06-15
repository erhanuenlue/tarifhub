# TarifGuard Console

The trust surface of the tarifhub platform: a thin **Next.js (App Router, React + Tailwind)**
console over the deterministic Python serving API. It renders frozen records verbatim and
carries the product's trust story; it has no billing logic of its own.

Four components (ADR-013 scope: no auth, no patient data, no benchmarking, no state library):

| Surface | Route | Talks to |
|---|---|---|
| Master list | `/search` | `GET /api/v1/search` (semantic) + `GET /api/v1/tariffs` (browse) |
| Detail panel | `/tariffs/{system}/{code}` | `GET /api/v1/tariffs/{system}/{code}` (+ `GET /api/v1/explain` for history/cross-walk) |
| Review form | `/review` | the console's BFF `POST /api/review` (the one write path; freeze server-side) |
| Explain panel | `/explain` | `GET /api/v1/explain?code=` (deterministic, labelled AI surface) |

A small ADR-013-accepted **coding-check** page (`/coding-check`) does structural lookups
(`GET /api/v1/tariffs/{system}/{code}` per position): no combinability verdict is computed here.

## Two boundaries this app respects

1. **Determinism.** TarifGuard is read-only over serving. Every value it shows (tax points,
   price, validity) is an unaltered frozen record relayed verbatim. It never computes, rounds,
   or mutates a billing value. The one write path (the review form) goes through the API and
   freezes server-side; it never touches the database and never calls `freeze()` directly.
2. **De-identification.** Patient identifiers never leave Swiss infrastructure. The explain
   seam takes a **tariff code only**; any optional free-text context is scrubbed by
   `lib/deident.ts` (the only sanctioned identifier-scrubber) and shown as an audit, never
   forwarded. See ADR-012 and `AGENTS.md`.

## The visual law (review-blocking)

Mirrored from `docs/brand/tokens.css`: frozen/deterministic values render `.value-certified`
(navy + JetBrains Mono 600, tabular) with version + truncated `record_hash` chips; AI output
renders on a labelled `.ai-content` slate surface ("AI-generated, not a billing value") and is
never styled like, or blended with, a frozen value.

## Layout

```
apps/tarifguard/
├─ app/
│  ├─ layout.tsx                     shell + brand header (logo once)
│  ├─ page.tsx                       landing + visual-law legend
│  ├─ search/page.tsx                master list (search + browse)
│  ├─ tariffs/[system]/[code]/page.tsx  detail panel (server component)
│  ├─ review/page.tsx                review form (the one write path)
│  ├─ explain/page.tsx               labelled AI explain panel
│  ├─ coding-check/page.tsx          structural coding check
│  └─ api/                           server-side proxies (keep SERVING_BASE_URL server-side)
│     ├─ search/route.ts · tariffs/route.ts
│     ├─ review/route.ts             BFF: queue + approve/correct (freeze server-side)
│     ├─ explain/route.ts            code-only seam + de-identification audit
│     └─ coding-check/route.ts
├─ components/                       NavBar, TariffCard, DetailPanel, ReviewForm, brand primitives
├─ lib/  api.ts (typed serving client + contracts) · deident.ts · review-fixtures.ts
└─ Dockerfile                        multi-stage Node build (Next standalone)
```

The browser never holds `SERVING_BASE_URL`: pages call same-origin handlers under `app/api/*`,
which run server-side via `lib/api.ts`.

## Run locally

Requires Node 20+ and a running serving API. Bring the backend up offline (SQLite mirror):

```bash
# 1. seed sample frozen records + start serving (:8000); see services/ingestion + services/serving
# 2. run the console:
cd apps/tarifguard
echo "SERVING_BASE_URL=http://localhost:8000" > .env.local
npm install
npm run dev                          # http://localhost:3000
```

`npm run lint`, `npm run build` and `npm test` (Vitest component tests + a Playwright smoke
against a mocked API) are the CI gates; see `.github/workflows/ci.yml`. The smoke is fully
offline (a mock serving server + fixture review queue), so it is deterministic and needs no
live backend. It also owns isolated ports so a local `npm test` stays hermetic even when a dev
server is running on `:3000`: the smoke serves the console on `127.0.0.1:3100` and the mock on
`127.0.0.1:8799` by default, and never reuses a pre-existing server. Override with
`PLAYWRIGHT_WEB_PORT` / `PLAYWRIGHT_MOCK_PORT`, or set `PLAYWRIGHT_REUSE=1` to reuse a server you
started yourself.

## Environment

| Variable | Purpose |
|---|---|
| `SERVING_BASE_URL` | Base URL of the deterministic serving API (default `http://localhost:8000`). Server-side only; never exposed to the browser. |
| `INGEST_BASE_URL` | Optional. When set, the review BFF proxies approve/correct to the future ingestion review endpoint; otherwise it serves fixtures and simulates the server-side freeze. |
