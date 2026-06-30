# d2 · Cockpit push and control (SSE, secured control plane, approval inbox)

> **Gate-01: pre-approved for the in-scope work below.** Stop for any out-of-scope path, freeze-line contact, a green-contract or ratchet breach, or a destructive operation. The loop supervisor must never auto-approve a sensitive action: it starts and stops `loop.sh` jobs, it does not decide approvals.
> **Precondition: do not run before CAS submission is confirmed merged.** Promote to `prompts/cockpit/` only post-submission.

Run at `/effort ultracode`. Read `01-contracts.md` section 4 (the SSE wire contract is authoritative) and C-02/C-03. This is where it becomes a cockpit, not a viewer. Ship as two ordered sub-steps so a partial land cannot merge a broken board (should-fix S12).

## Constraints
- Allowed paths: `tools/shipboard/**`, `tests/cockpit/**`, `docs/cockpit/**` (cockpit ADRs under `docs/cockpit/adr/**`). No `tools/loop.sh`, `tools/cas_check.py`, product `docs/adr/**`, `.github/workflows/**`, or hook edits.
- Zero new Python dependencies. Vendored HTMX/Alpine JS only (no CDN, no npm), per C-02. No em-dashes.

## Work (two ordered, individually-green sub-steps)
1. **d2a SSE plus auth, additive.** `api.py` serves `GET /events` per the wire contract: `snapshot` on connect (derived from projection tables in O(1)), typed deltas keyed by `seq`, 15s heartbeat, bounded `Last-Event-ID` replay with a `gap` marker. Collector and HTTP server share one process; a single always-on collector tailer thread (fix 9) follows the run-scoped logs and pushes to an in-process per-client `queue.Queue` fan-out under a `Lock`; each SSE thread blocks on `queue.get(timeout=15)`. Concurrent-SSE cap to 503, `flush` after every frame, dead-client reaping on `BrokenPipe`. Promote the d0 auth into `security.py`; gate `/events` by Host plus a `SameSite=Strict` cookie token (should-fix S2). Keep the `/state` poll alive as the `EventSource.onerror` fallback. A render/SSE parity test must prove the everything-clickable inspector did not regress.
2. **d2b control plane.** `control.py` supervises `loop.sh` as a managed child job: start, stop, pause, resume, re-run-a-prompt. Control is a HIGHER risk class than an approval (C-03, fix 6): `start`/`resume` require an explicit, separate confirmation (not the one-click that decides an approval), launch the loop in a non-bypass permission mode or with `APPROVALS_ON=1` forced so every sensitive action inside the run is re-gated, and emit a `control.action` audit event per action. All control POSTs carry the security triad. The approval inbox becomes a first-class secured surface reading pending approvals from the projection; deciding still flows through the existing first-writer-wins gate.

## Done means (quote the evidence)
- `test_render_smoke.py` SSE assertions green: connect yields `snapshot` then heartbeat; **append pushes a framed message within 100ms**; `Last-Event-ID` replays missed events bounded to roughly 500 with a `gap` beyond; concurrent cap returns 503; a closed client frees its slot; every frame flushed.
- `test_security.py` extended green for the control endpoints and the cookie-gated `/events`.
- An e2e-tester run shows start, stop and resume of a DRY-RUN loop (`LOOP_CMD='true'`) from the API, with each control action emitting a `control.action` audit event and `start`/`resume` requiring the separate higher-risk confirmation and launching in non-bypass mode (C-03, fix 6); and the approval inbox deciding a seeded pending approval end to end.
- The board works at every step: with SSE forced off, the poll fallback still renders. Ship report quotes the failing-then-passing runs. Green-contract holds. `/ship` each sub-step.
