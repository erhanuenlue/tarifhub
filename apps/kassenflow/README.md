# KassenFlow

**Layer-3 app stub (in development).** KassenFlow automates payer correspondence and
**Kostengutsprache** (cost-approval) workflows: insurer queries, MiGeL/medication
approvals, and multi-payer handling. Like TarifGuard, it is a thin **Next.js (App Router,
React + Tailwind)** client over the deterministic platform: read-only over the serving
API (L1) and the TarifIQ rule engine (L2). It computes no billing value of its own.

## Planned scope (none wired yet)

| Screen | Purpose | Talks to (planned) |
|---|---|---|
| Kostengutsprache requests | Draft cost-approval / prior-authorization requests grounded in frozen positions + combinability checks | serving (L1) + TarifIQ (L2) |
| MiGeL & medication approvals | Track device/medication approval cases, evidence, and payer decisions | serving (L1) |
| Multi-payer correspondence inbox | Insurer queries & structured responses across payers | serving (L1) |

## Two boundaries this app must respect

1. **Determinism.** Every value KassenFlow shows is an unaltered frozen record relayed
   verbatim from serving, and every combinability/cross-walk answer comes from TarifIQ. It
   never computes, rounds, or mutates a billing value.
2. **De-identification.** Patient identifiers never leave Swiss infrastructure. Any
   LLM-assisted drafting scrubs input with `lib/deident.ts` (the **only** module allowed
   to build an LLM-bound payload) before anything is forwarded; the model call is served
   by the backend and routed via AWS Bedrock EU / Google Vertex AI EU.

## Layout

```
apps/kassenflow/
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
cd apps/kassenflow
cp .env.example .env.local         # set SERVING_BASE_URL + TARIFIQ_BASE_URL
npm install                        # generates package-lock.json (commit it for `npm ci`/CI)
npm run dev                        # http://localhost:3001
```

`npm run lint` and `npm run build` are the CI gates (see `.github/workflows/ci.yml`).
CI uses `npm ci`, so commit `package-lock.json` after the first `npm install`.

## Environment

| Variable | Purpose |
|---|---|
| `SERVING_BASE_URL` | Base URL of the deterministic L1 serving API. Server-side only. |
| `TARIFIQ_BASE_URL` | Base URL of the L2 TarifIQ rule engine. Server-side only. |
