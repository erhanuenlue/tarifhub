# ADR-008 — Live `ai_map` via Claude structured output (fill-only)

- Status: Accepted
- Date: 2026-06-11

> **Superseded numbering.** This is repo-era ADR-008 (pre-register). The consolidated 2026-06 register renumbered all decisions — see [the mapping](README.md).

## Context

ADR-002 permits AI **pre-freeze only**, on non-billing fields. AGENTS.md specified the seam as
"structured output, temp 0". Implementing `ai_map` against current Claude models surfaced one
gap: the `temperature` parameter no longer exists on those models (the API removes it), so the
old "temp 0" wording can no longer describe how determinism is achieved.

## Decision

`ai_map` calls Claude (`claude-opus-4-8`) via **structured output** (`messages.parse`, a Pydantic
schema). The policy is **fill-only**: AI fills missing `designation_fr` / `designation_it` /
`category`, **never overwrites** source data, and structurally cannot touch billing values.
Without `ANTHROPIC_API_KEY` the seam falls back to the deterministic `map_raw`. Determinism is
guaranteed **architecturally** — a deterministic scorer plus an AI-isolated merge — **not** by a
sampling parameter; the absent `temperature` knob is therefore not relied on.

## Consequences

- Review routing stays with the deterministic confidence scorer: `< 0.85` → review queue.
- AI provenance is recorded in record metadata: `ai_model`, `ai_fields`, `ai_status`.
- The "temp 0" phrasing in older docs is superseded by this architectural-determinism
  guarantee; the freeze-line boundary (ADR-002) is unchanged.
- **Gap-gate (deterministic pre-check):** `ai_map` computes fillable gaps (missing
  `designation_fr` / `designation_it` / `category`) before any live call. With nothing
  fillable, it returns the deterministic record unchanged and never invokes the model —
  saving cost/latency on a guaranteed no-op and keeping the no-gap path byte-identical to
  the no-key path (record_hash idempotency). The model is called only when a gap exists.
