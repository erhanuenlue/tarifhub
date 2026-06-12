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
- (+) Re-ingesting identical sources is now idempotent unconditionally (live key or not) — see the fill-reuse addendum below.
- (–) Mapping throughput is bounded by the review queue when confidence runs low; revisit the 0.85 threshold once review-precision data accumulates.

*Lineage: refines legacy/002 (AI before freeze only); carries the architectural-determinism correction from legacy/008-ai-map-live.md.*

## Addendum (2026-06-12) — fill-reuse
Live `ai_map` fills (designations, `category`) are not byte-stable across re-ingests (measured: 55 ATC-less SL records re-versioned over two re-runs), and inversely a key-less re-run would re-version filled records back to fill-less — both break re-ingest idempotency. **Fill-reuse** closes both: when a row's deterministic pre-fill content is unchanged from the latest frozen version, the pipeline strips that version back to its pre-fill state, compares content hashes against the fresh `map_raw` candidate, and on a match adopts the stored content **verbatim — AI fills included — with NO model call**. Freeze then reproduces the identical `record_hash` and the repository dedupes, so identical sources yield an identical `record_hash` set whether or not a live key is present. A deliberate re-fill is available via `--refill` (which bypasses reuse and re-runs `ai_map`). Reuse provenance (`ai_fills_reused`, `reused_from_version`) is recorded in the **audit `detail` only, never in record metadata** — writing it into the record would change the hashed bytes and re-version it, defeating the point. That byte-stability trade-off is deliberate: the audit log carries the lineage, the frozen record stays identical.
