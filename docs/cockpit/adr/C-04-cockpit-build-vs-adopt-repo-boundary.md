# C-04: Cockpit build-vs-adopt and repository boundary

*Status: Accepted (owner confirmed the three marked decisions 2026-06-14; build deferred post-submission) · Date: 2026-06-14 · Decider: Erhan*

## Context
A cockpit needs trace, cost and evaluation UIs. A mature open category already provides these for agent and LLM telemetry (Langfuse, LangSmith, Helicone, AgentOps). None of them provide coding-agent build-loop control: start, stop and resume a multi-prompt autonomous build, an approval inbox wired to a freeze line, and a CAS-style fitness ratchet. Separately, the cockpit is build-machinery and a product seed; it must not entangle the CAS freeze or the 6 July 2026 submission.

## Decision (proposed)
1. **Adopt, do not rebuild, the observability category.** Emit OpenTelemetry (OTLP) and run self-hosted Langfuse (OSS) for trace, cost and eval UIs; build only the differentiated control and evaluation surface. The zero-dependency export path targets a generic OTLP collector (Tempo or the OpenTelemetry Collector, where OTLP/HTTP-JSON is in spec); Langfuse is the dependency-gated option once its exact ingestion contract (endpoint, encoding, required attributes) is verified, not assumed.
2. **Extract the cockpit into its own repository after submission.** The emitters (the hooks, `emit.sh`, the `loop.sh` `run_id` minting) stay in tarifhub and write events; the cockpit (collector, store, api, web) consumes them and moves out. The contract between them is the typed event schema, a versioned interface: the cockpit accepts `schema_version <= N`, and for `schema_version > N` it ingests but does not project the event, with a warning (so a newer post-extraction emitter cannot silently drop history), and it reads the rail from a path argument, not a hardcoded sibling. Until 6 July it stays in `tools/` to avoid churn.

## Alternatives weighed
- **Build our own trace, cost and eval UIs**: months rebuilding a solved category; spend the engineering on the control plane that nothing off-the-shelf sells.
- **Keep the cockpit in tarifhub permanently**: simplest, but couples a product-seed build tool to the graded CAS repo and its freeze, and complicates open-sourcing either side.
- **Adopt a hosted SaaS (LangSmith)**: recurring cost and build telemetry sent off-box for a solo operator; self-hosted Langfuse keeps the data local.

## Consequences
- (+) Trace and eval UIs for free; engineering goes to the loop control plane and the gate/eval surface that is the actual differentiated value and the product seed.
- (+) The CAS repo stays clean of build-machinery churn; either repo can be opened independently.
- (–) Self-hosted Langfuse is real operational weight (containers, Postgres); it is opt-in at d3, not required for d0 to d2, and the core stays runnable without it.
- (–) Extraction needs a stable event-schema contract and a path-configurable rail; recorded now, implemented post-submission. Revisit trigger: owner confirmation of the three marked decisions below.

## Owner-confirmed decisions (2026-06-14)
- **Frontend**: HTMX + Alpine + SSE, keep the bespoke Canvas. Confirmed. See C-02.
- **Adopt versus build**: adopt OTel + Langfuse, build only the control plane. Confirmed.
- **Repository**: extract post-submission, emitters stay in tarifhub. Confirmed. The four staged prompts stay in `docs/cockpit/prompts/` until submission (glob-safety), promoted to `prompts/cockpit/` only post-6-July.

*Lineage: new; reuses ADR-011 (OpenTelemetry) for the export path. Cross-reference C-01, C-02, C-03.*
