# 11 · risks technical debt

> Stub — the full chapter is populated in prompts/07. This section seeds the risk register with the hash-integrity risks closed in this iteration; the rest follows.

The risk register tracks each known risk with its mitigation and residual exposure.

| Risk | Mitigation | Residual |
|---|---|---|
| **AI fill variance** — live `ai_map` fills are not byte-stable across re-ingests (measured 2026-06-12: 55 re-versions of ATC-less SL records over two re-runs), breaking re-ingest idempotency | Fill-reuse: unchanged content carries the prior version's fills forward with no model call ([ADR-005 addendum](../adr/005-single-ai-seam.md)); live-measured — a full-export reuse leg froze 0 of 10 299 with an invalid key ([proof](../evidence/2026-06-12-sl-live-ingest.md#addendum-2026-06-12-live-fill-reuse-proof)) | `--refill` and model upgrades deliberately re-version (append-only); accepted, since each variant is audit-logged and routes to review |
| **Silent scale rounding** — Postgres `NUMERIC(12,4)/(12,2)` rounds an over-precise billing value on insert, so stored bytes ≠ hashed bytes | Pre-freeze quantization to the canonical scales; lossy values fail closed to `None` + review ([ADR-016](../adr/016-decimal-scale-contract.md)) | Closed: stored bytes provably equal hashed bytes on every engine |
