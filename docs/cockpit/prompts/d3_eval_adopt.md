# d3 · Cockpit eval and adopt (OTLP export, run comparison, recurring eval)

> **Gate-01: pre-approved for the in-scope work below.** The repository extraction at the end is a separate owner decision (C-04): stop and confirm before moving any file out of tarifhub. Stop also for any out-of-scope path, freeze-line contact, or a green-contract breach.
> **Precondition: do not run before CAS submission is confirmed merged.** Promote to `prompts/cockpit/` only post-submission.

Run at `/effort ultracode`. Read C-04 and `01-contracts.md` section 3 (the OTel mapping). This stage adopts the observability category instead of rebuilding it, adds the eval surface, and finishes the module split.

## Constraints
- Allowed paths: `tools/shipboard/**`, `tests/cockpit/**`, `docs/cockpit/**` (cockpit ADRs under `docs/cockpit/adr/**`). Not product `docs/adr/**` or `.github/workflows/**`.
- The OTLP exporter is the ONLY place a non-stdlib dependency may appear, and only if hand-rolled OTLP/JSON proves insufficient; quarantine it to `otlp.py` and allowlist it explicitly in `test_zero_dep_core.py`. No em-dashes.

## Work (verification checklist)
1. **OTLP export.** `otlp.py` maps a run's spans to OTLP/HTTP-JSON via `urllib` (per the section 3 mapping: GenAI attributes, cache tokens as namespaced custom attributes, derived `cost_usd` as a custom attribute), validating id widths at export. Default target is a generic OTLP collector (Tempo or the OpenTelemetry Collector). Langfuse is dependency-gated: verify its ingestion contract first (should-fix S6); do not assume OTLP/HTTP-JSON works there.
2. **Run comparison.** A read-model and view that diffs two runs across cost, duration, gates, CAS floor, and files touched; surface the ratchet trend.
3. **Recurring eval.** Wire the dual-blind scorecard / grade-auditor as a tracked eval: score-over-time, regression flag like a CI status.
4. **Finish the split.** Retire the monolith's remaining inline logic into `collector`/`api`/`web`; the thin `shipboard.py` shim still launches the package. Confirm the import/invocation contract (section 1.1 of the build spec).
5. **Optional extraction (owner stop).** Per C-04, the emitters stay in tarifhub; the cockpit can move to its own repo reading the rail from a path argument and accepting `schema_version <= N`.

## Done means (quote the evidence)
- An e2e-tester run shows a run's spans exported and visible in a local OTLP collector (and, if adopted, Langfuse); `otlp.py` id-width validation rejects malformed ids in a unit test.
- The run-comparison view returns a real diff across two stored runs.
- `test_zero_dep_core.py` still green for the core (only `otlp.py` may carry the exporter dependency); the module-split import-graph test passes; `test_determinism_boundary_cockpit.py` still green.
- Ship report quotes the failing-then-passing runs and the exported-trace evidence. Green-contract holds. `/ship`.
