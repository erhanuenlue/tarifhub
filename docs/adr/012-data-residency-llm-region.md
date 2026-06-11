# ADR-012 — Data residency in Switzerland; LLM region boundary for patient data

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
Public tariff data and patient data have different legal footing under the revFADP: L0–L2 handle only published tariff catalogues, while the L3 apps will touch practice and patient context. One residency rule for both would either over-constrain the harmonisation core or under-protect the apps — that asymmetry is what forces a decision.

## Decision
We host all persistent data in Switzerland; L0–L2 (public tariff data) may call an LLM in the global region, while L3 de-identifies server-side and routes any LLM call via an EU/CH model region under a DPA.

## Alternatives weighed
- **Global residency for everything** — simplest operationally, but places patient-adjacent data under non-CH/EU jurisdiction and fails revFADP expectations for the L3 apps.
- **CH/EU-only for everything** — over-constrains L0 harmonisation, where the inputs are public catalogues and the strongest structured-output models may only be available in the global region.

## Consequences
- (+) Privacy by design: the core stays unconstrained on public data while the apps remain compliant on patient-adjacent data.
- (+) The boundary is code, not policy: de-identification is one marked module per side — the console's server-side `apps/tarifguard/lib/deident.ts` (route handlers keep raw input and `SERVING_BASE_URL` off the browser) and the pipeline's `ai_map()`. Neither seam can touch a billing value — "No AI computes or mutates a billing value at serve time."
- (–) Two LLM routing paths to maintain, and EU/CH model regions can lag global model availability — revisit if an L3 feature needs a model not offered in the EU/CH region.

*Lineage: new register entry; restates the de-identification boundary decided in [legacy/005](legacy/005-tarifguard-merge-and-mcp.md).*
