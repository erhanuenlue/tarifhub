# ADR-011: OpenTelemetry-based observability

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
The platform is a set of distributed sub-systems (ingestion, serving, MCP, console) in two language runtimes, so behaviour must be traceable across process boundaries without a per-service bespoke solution. The constraint that makes this a decision: lineage correlation, where an operator must be able to connect any served response to the exact frozen record version behind it.

## Decision
We use OpenTelemetry as the single telemetry standard (traces, metrics and logs exported to Prometheus/Grafana, with Sentry for error tracking) and structured JSON logs that carry `record_hash` and version so telemetry correlates with lineage.

## Alternatives weighed
- **Custom logging stack**: bespoke formats per service, no context-propagation standard, and every cross-service trace becomes manual log archaeology.
- **Vendor APM agent (e.g. Datadog)**: lock-in and recurring cost for capabilities the open standard plus Prometheus/Grafana already covers at this scale.

## Consequences
- (+) One vendor-neutral standard across Python and Node; dashboards for API latency, scraper success and review-queue depth all hang off the same exporters.
- (+) `record_hash`/version in every log line makes any served value traceable back to its immutable frozen record: observability reinforces the determinism story instead of sitting beside it.
- (–) **Not yet implemented.** This ADR records the decided direction; no service emits OpenTelemetry today and the Prometheus/Grafana/Sentry wiring does not exist. Instrumentation is pending: the trigger to build it is the first deployment anyone besides the developer depends on, or the capstone's runtime-evidence capture, whichever comes first.
- (–) The OTel SDK adds dependency weight to every service once wired; accepted as the price of one standard.

*Lineage: new, no legacy counterpart.*
