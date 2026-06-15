# MeldePilot

**Layer-3 app stub (in development).** MeldePilot automates Switzerland's mandatory
reporting and quality-data obligations: **BFS/MARS** structural and statistical returns,
**ANQ** quality measures, and **interRAI/BESA** long-term-care data to the cantons. Like
TarifGuard, it is a thin **Next.js (App Router, React + Tailwind)** client over the
deterministic platform: read-only over the serving API (L1) and TarifIQ (L2). It computes
no billing value and submits nothing without human sign-off.

## Planned scope (none wired yet)

| Screen | Purpose | Target |
|---|---|---|
| BFS / MARS submissions | Structural & statistical datasets, validated against spec | Federal Statistical Office (MARS) |
| ANQ quality measures | National quality-measurement datasets + deadlines | ANQ |
| interRAI / BESA → cantonal | Long-term-care assessment data mapped per canton | Cantonal authorities |

## Two boundaries this app must respect

1. **Determinism.** The authoritative report payload is assembled deterministically; any
   tariff value shown is an unaltered frozen record from serving, and rule/cross-walk
   answers come from TarifIQ. MeldePilot computes or mutates no billing value.
2. **De-identification.** Patient identifiers never leave Swiss infrastructure. Any
   LLM-assisted mapping/narrative scrubs input with `lib/deident.ts` (the **only** module
   allowed to build an LLM-bound payload) before anything is forwarded; the model call is
   served by the backend and routed via AWS Bedrock EU / Google Vertex AI EU.

## Layout

```
apps/meldepilot/
├─ app/
│  ├─ layout.tsx   shell + preview banner
│  ├─ page.tsx     landing: purpose + "scope / coming in development" (planned screens)
│  └─ globals.css
├─ lib/deident.ts  de-identification choke point (the only LLM-payload builder)
└─ Dockerfile      multi-stage Node build (Next standalone)
```

## Run locally

Requires Node 20+. (Backends optional while this is a scope stub.)

```bash
cd apps/meldepilot
cp .env.example .env.local         # set SERVING_BASE_URL + TARIFIQ_BASE_URL
npm install                        # generates package-lock.json (commit it for `npm ci`/CI)
npm run dev                        # http://localhost:3002
```

`npm run lint` and `npm run build` are the CI gates (see `.github/workflows/ci.yml`).
CI uses `npm ci`, so commit `package-lock.json` after the first `npm install`.

## Environment

| Variable | Purpose |
|---|---|
| `SERVING_BASE_URL` | Base URL of the deterministic L1 serving API. Server-side only. |
| `TARIFIQ_BASE_URL` | Base URL of the L2 TarifIQ rule engine. Server-side only. |
