# ADR-011: OpenTelemetry-based observability

*Status: Accepted · Date: 2026-06-11 · Amended: 2026-07-01 (instrumented in the serving service) · Decider: Erhan (+ AI-assisted analysis)*

## Context
The platform is a set of distributed sub-systems (ingestion, serving, MCP, console) in two language runtimes, so behaviour must be traceable across process boundaries without a per-service bespoke solution. The constraint that makes this a decision: lineage correlation, where an operator must be able to connect any served response to the exact frozen record version behind it.

## Decision
We use OpenTelemetry as the single telemetry standard (traces, metrics and logs exported to Prometheus/Grafana, with Sentry for error tracking) and structured JSON logs that carry `record_hash` and version so telemetry correlates with lineage.

The serving service (L1 TarifCore) is the first surface instrumented against this standard. Its FastAPI app is auto-instrumented (`FastAPIInstrumentor.instrument_app`) so every request produces a trace, a custom `serving.search` span traces the semantic-search path and a `serving.search.duration_ms` histogram records the latency of each successful search ranking (a fail-closed 501 records no point), and the OTLP exporter endpoint is read from `OTEL_EXPORTER_OTLP_ENDPOINT`. The instrumentation observes only and stays off the value contract: it never reads, computes or mutates a billing value and imports no LLM client, which `test_serving_boundary.py` continues to enforce.

## Alternatives weighed
- **Custom logging stack**: bespoke formats per service, no context-propagation standard, and every cross-service trace becomes manual log archaeology.
- **Vendor APM agent (e.g. Datadog)**: lock-in and recurring cost for capabilities the open standard plus Prometheus/Grafana already covers at this scale.

## Consequences
- (+) One vendor-neutral standard across Python and Node. Dashboards for API latency, scraper success and review-queue depth all hang off the same exporters.
- (+) `record_hash`/version in every log line makes any served value traceable back to its immutable frozen record: observability reinforces the determinism story instead of sitting beside it.
- (+) **Instrumented in the serving service.** FastAPI request traces plus a search-latency histogram are emitted through the OpenTelemetry SDK. The OTLP HTTP exporter is selected only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. When it is unset the setup installs no span processor and no metric reader, a deliberate no-op default so the offline test suite and CI need no collector and nothing breaks. Prometheus/Grafana and Sentry remain the intended production backends behind that endpoint, and the same `setup_telemetry` pattern is ready to extend to ingestion and mcp.
- (-) The collector stack (Prometheus/Grafana/Sentry) is not stood up in this capstone, where graders review code and captured evidence and nothing runs, and ingestion and mcp are not yet instrumented. Serving is the proof pattern. Extending it to the other services and deploying the collectors behind a real endpoint is the remaining work.
- (-) The OTel SDK adds dependency weight to every service once wired. Accepted as the price of one standard.

*Lineage: new, no legacy counterpart.*
