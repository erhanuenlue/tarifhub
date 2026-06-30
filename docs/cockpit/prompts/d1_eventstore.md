# d1 · Cockpit event store (SQLite, projections, run-scoped logs)

> **Gate-01: pre-approved for the in-scope work below, with one hard stop.** The `loop.sh` edit in sub-step 3 is a real Gate-01 stop, not pre-approved: stop and get owner confirmation before editing `tools/loop.sh`. Stop also for any path outside the Constraints block, freeze-line contact, a green-contract or ratchet breach, or a destructive operation.
> **Precondition: do not run before CAS submission is confirmed merged.** Promote to `prompts/cockpit/` only post-submission.
> **Run this stage STANDALONE, never through `tools/loop.sh`** (must-fix M2): it edits the very script `loop.sh` would be executing, and `loop.sh` reads its script incrementally.

Run at `/effort ultracode`. Read `docs/cockpit/00-build-spec.md` and `01-contracts.md` (the schema and DDL are authoritative). This is the keystone: structured events become the source of truth, history and restart-survival arrive. TDD throughout; the rebuild-equals-live invariant is a first-class test.

## Constraints
- Allowed paths: `tools/shipboard/**`, `tests/cockpit/**`, `docs/cockpit/**` (cockpit ADRs under `docs/cockpit/adr/**`); `tools/loop.sh` in sub-step 3 only, after the owner stop. Not product `docs/adr/**` or `.github/workflows/**`.
- Excluded: as d0, plus do not touch `tools/cas_check.py` or `tools/cas_baseline.json`.
- Zero new Python dependencies (stdlib `sqlite3`). No em-dashes. `.shipboard/`, the SQLite file, and `.shipboard/runs/` stay gitignored.

## Work (three ordered, individually-green sub-steps)
1. **Store and collector over the existing rail.** Build `events.py` (envelope + payload validation + factories, per `01-contracts.md` section 1), `store.py` (DDL, WAL, `INSERT OR IGNORE` append, incremental projections, `rebuild_projections()`, `prices.py`-derived cost), and `collector.py` reading the EXISTING legacy `.shipboard/events.jsonl`: synthesize the envelope for each flat line with a DETERMINISTIC content-addressed `event_id` (a hash of `(file-identity, line-number, line-bytes)`, so re-reading the same line is exactly-once across a collector restart, before sub-step 2's `(inode, offset)` cursor exists; native emitters keep a full-entropy ULID) and the active `run_id` (must-fix M1, d1 dedup fix), transcript scraping demoted to enrichment. The board reads from the store. Truncation still happens; prove old-board parity. Ship.
2. **Run-scoped append-only logs.** Move emission to `.shipboard/runs/<run_id>/events.jsonl`; stop truncating; the collector tails by `(inode, offset)` so a rotate is a new file, not an offset reset. Implement partial-run reconciliation and the bounded-retention sweep (keep the last N runs, age out older `events` rows and `runs/<run_id>/` dirs) as pure functions of the log (should-fix S4, fix 10, C-01). Ship.
3. **`run_id` minting (owner stop first).** `loop.sh` mints `SHIPBOARD_RUN_ID` (additive: defaults to a generated ULID if unset, so an un-migrated loop keeps emitting) and emits `run.started`/`run.ended` via a bash `trap` on `EXIT/INT/TERM` with `halt_reason`. Ship.

## Done means (quote the evidence)
- `test_event_store.py` green: idempotent append, per-type projections, **rebuild-equals-live**, restart-survival, cost derived from injected prices (tokens unchanged), run isolation, seq-only ordering under cross-source clock skew, partial-run reconciliation, span_id/trace_id widths and `runs.run_id` UNIQUE.
- `test_collector.py` green: legacy line to typed envelope; **ingest, rotate or truncate mid-stream, ingest again, zero loss and zero double-count** (including a collector restart re-reading the same legacy file, via the deterministic id); trust ordering emit over enrichment; malformed line skipped; naive timestamp localized or rejected.
- `test_read_model_api.py` green: `/api/runs` newest-first; `/api/run/<id>` span tree; `/detail` parity; **a past run's agent detail resolves after a simulated restart**.
- The run list shows at least two historical runs across a restart. Ship report quotes the failing-then-passing runs. Green-contract holds; `cas_check.py` byte-unchanged. `/ship` each sub-step.
