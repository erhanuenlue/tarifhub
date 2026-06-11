# ADR-005 — Single AI seam (ai_map) with human-in-the-loop

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
Harmonising 20+ source formats across DE/FR/IT is the problem AI should help with — without ever owning a value. The inviolable rule is fixed: **"No AI computes or mutates a billing value at serve time."** The question is therefore not whether AI helps but where exactly, and how the seam stays deterministic when the model itself is not.

## Decision
We run exactly one live-AI seam, `ai_map`, pre-freeze and on non-billing fields only: Claude via structured output (`messages.parse` against a Pydantic schema), under a fill-only policy, with a deterministic confidence scorer routing anything below 0.85 to human review.

Determinism at the seam is **architectural** — not a sampling parameter (the `temperature` knob no longer exists on current Claude models):

- **Fill-only.** AI fills missing `designation_fr` / `designation_it` / `category`; it never overwrites source data and structurally cannot touch billing values.
- **Gap-gate.** A deterministic pre-check computes fillable gaps before any model call; no fillable gap → no call → output byte-identical to the no-key path (`record_hash` idempotency).
- **Fallback.** Without `ANTHROPIC_API_KEY`, the seam falls back to deterministic `map_raw`; offline tests rely on this.
- **Provenance.** `ai_model`, `ai_fields`, `ai_status` are recorded in record metadata.

## Alternatives weighed
- **AI anywhere on the value path** — violates the inviolable rule; never.
- **Several smaller AI seams across the pipeline** — every seam is a boundary to test and audit; one seam keeps the AST boundary test simple and the freeze line crisp.
- **Determinism via "temperature 0"** — the parameter is gone on current models, and a sampling knob was always a weaker promise than a structure that cannot emit a billing value.
- **Fully manual harmonisation** — does not scale across 20+ formats and three languages; the seam exists precisely to absorb this work.

## Consequences
- (+) AI accelerates mapping while the value path stays deterministic; the AST boundary test stays green by construction, not by discipline.
- (+) Quality is gated twice: deterministic scorer (`< 0.85` → review queue) plus human review. Reviewed decisions can later seed few-shot examples (planned, not yet wired).
- (+) Supersedes the "temperature 0" phrasing still found in older prose (AGENTS.md, Architecture v2.1 §11).
- (–) Mapping throughput is bounded by the review queue when confidence runs low; revisit the 0.85 threshold once review-precision data accumulates.

*Lineage: refines legacy/002 (AI before freeze only); carries the architectural-determinism correction from legacy/008-ai-map-live.md.*
