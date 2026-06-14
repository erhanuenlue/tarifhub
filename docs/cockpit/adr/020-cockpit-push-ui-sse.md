# ADR-020: Push-based cockpit UI (SSE over polling, HTMX over SPA)

*Status: Proposed · Date: 2026-06-14 · Decider: Erhan (+ AI-assisted design)*

## Context
The dashboard refreshes by a fixed 2-second client poll layered over server caches (TTLs from 5 to 60 seconds), so liveness is eventually-consistent: a new subagent can take roughly 20 seconds to appear and CI lags 30 to 45 seconds. The UI is an 1,100-line HTML string re-rendered by full `innerHTML` every tick, which also churns transient UI state (open drawers, scroll). Once events are persisted and totally ordered by `seq` (ADR-019), the server can push deltas instead of being polled.

## Decision
We replace the poll with a Server-Sent Events stream (`GET /events`, stdlib, one-way, simpler than WebSockets) carrying typed domain events keyed by the event `seq`, with an initial `snapshot` frame and a periodic heartbeat; reconnection replays missed events durably via `Last-Event-ID` against the store. We render with HTMX plus Alpine rather than an SPA: the server keeps owning state, the client stays minimal, and the bespoke Canvas vault-graph is preserved unchanged. The `/state` poll is kept as a degraded fallback so an SSE defect cannot blank the board. The full wire contract (frame shapes, heartbeat, replay bound, fallback) is in `docs/cockpit/01-contracts.md`.

## Alternatives weighed
- **WebSockets**: bidirectional and heavier; the cockpit's live data is server-to-client only, so SSE is the right tool, and `EventSource` gives auto-reconnect and `Last-Event-ID` replay for free.
- **A Svelte or React SPA**: rich client interactivity, but a build step, a `node_modules` tree, and a client state layer for a single operator; unjustified versus HTMX, and it forfeits the "runs anywhere, no build" virtue. Reach for Svelte only if client interactivity later becomes the bottleneck.
- **Keep polling, shorten the interval**: more load, still TTL-lagged, still full re-render; does not remove the root latency.

## Consequences
- (+) Sub-second liveness with no cache-TTL lag; the browser stops full-`innerHTML` re-rendering every tick.
- (+) Durable replay across reconnect and server restart with no missed events, the payoff of ADR-019 persistence.
- (+) HTMX keeps the server-rendered simplicity the maintainer already works in, with a fraction of the JavaScript.
- (–) HTMX and Alpine are vendored JavaScript assets, a named deviation from the zero-JS-dependency ethos; mitigated by vendoring the files (no CDN, no npm) so the tool still runs offline and anywhere. The Python core stays zero-dependency.
- (–) Long-lived SSE connections need concurrency discipline on stdlib `http.server` (a thread cap, daemon threads, socket timeouts, BrokenPipe handling, and an in-process fan-out queue), specified in the build spec and gated by tests. Revisit trigger: if the UI ever needs a true bidirectional control channel, reconsider WebSockets.

*Lineage: new. Cross-reference ADR-019 (the `seq` the stream is keyed on), ADR-021 (the stream and its control POSTs share the security model).*
