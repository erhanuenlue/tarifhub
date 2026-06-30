# C-01: Event-sourced, persisted cockpit telemetry store

*Status: Proposed (design ratified in principle, build deferred post-submission) · Date: 2026-06-14 · Decider: Erhan (+ AI-assisted design, red-teamed)*

## Context
The build-machine dashboard (`tools/shipboard/shipboard.py`) reconstructs pipeline state by scraping Claude Code transcript JSONL plus `gh`/`git` command text, holds it in a volatile in-memory dict, and serves a fixed 2-second poll. Three structural failures all trace to one root cause, that it infers truth from artifacts never meant to be its source of truth:
1. State is wiped on restart (the inspector returns "delegation not found (server restarted?)").
2. There is no run history: `tools/loop.sh` truncates `.shipboard/events.jsonl` per prompt (line 94) and events carry no `run_id`, so per-run isolation is faked by timestamp-gating.
3. Cost is an estimate from a hardcoded price table that rots on any reprice.

The project already committed to evidence-over-assertion, and to OpenTelemetry for the product (ADR-011, not yet implemented, its build trigger being "the capstone runtime-evidence capture"). The build-machine should meet the same bar.

## Decision
We make structured, persisted events the source of truth for the cockpit. Emitters (hooks, `emit.sh`, `loop.sh`, ship phases, gates) append typed events to run-scoped append-only logs; a single-writer collector ingests them into an append-only SQLite `events` table (stdlib `sqlite3`, zero new dependency) and maintains derived read-model projection tables (`runs`, `spans`, `agents`, `gates`, `approvals`) that are fully rebuildable by replaying the log in `seq` order. Transcript scraping is demoted to an enrichment fallback. Each event carries a stable ULID `event_id` (idempotent `INSERT OR IGNORE`), a `run_id`, and OpenTelemetry-shaped span identifiers, so the same store maps directly to OTLP spans for optional export (C-04). Cost is never stored as truth: token counts are stored, the dollar value is derived at projection time from a pluggable `prices.json`.

The full event schema and DDL live in `docs/cockpit/01-contracts.md`.

## Alternatives weighed
- **Keep scraping, add a cache file**: persists the symptom (inference from the wrong source) and still mis-senses on any Claude Code schema or test-runner change.
- **A client/server database (Postgres)**: the product runs Postgres, but a localhost single-operator build tool does not justify a daemon, a connection pool, or the operational weight; SQLite in WAL mode gives one writer and many readers with no server.
- **A pure event log with no projections (recompute per request)**: simple, but every page load replays the whole log; materialized projections keep reads O(1) while the log stays the rebuildable truth.

## Consequences
- (+) Run history, multi-run comparison, restart-survival and trace replay become queries, not heroics; the "server restarted?" amnesia is gone.
- (+) Cost stops drifting: reprice is an edit to `prices.json`, no code change, tokens untouched.
- (+) The build-machine inherits the product's evidence-first posture and is OTLP-exportable for free (C-04).
- (–) An ingestion and projection layer is new surface to test; mitigated by the rebuild-equals-live invariant (a projection is a pure function of the log) being a first-class test (`test_event_store.py`).
- (–) The migration must not break the live loop's ability to emit. It is sequenced and contracted in `docs/cockpit/00-build-spec.md`: run-scoped logs replace per-prompt truncation, and the collector trusts emitted `event_id`s rather than byte offsets, so a truncate or rotate cannot cause silent history loss. Revisit trigger: a second consumer needing the data over a network would reopen the Postgres question.

## Key invariants (full DDL in `docs/cockpit/01-contracts.md`)
- `events.seq INTEGER PRIMARY KEY AUTOINCREMENT` is the sole total-order and replay authority. `ts_unix` is a display and duration attribute only; it is not trusted for ordering across sources, because `emit.sh` and the approval gate historically stamped different clocks (`emit.sh` is corrected to UTC in d0).
- `events.event_id` (26-char id) `UNIQUE` gives idempotent `INSERT OR IGNORE` and is distinct from any span identifier. Two id regimes (must-fix from the d1 review): a native emitter mints a full-entropy ULID (the full 80-bit random component, never truncated, so two events in the same millisecond cannot collide and be silently dropped); the legacy-ingest path, where flat `emit.sh` lines carry no id, synthesizes a deterministic content-addressed id from `(file-identity, line-number, line-bytes)`, so re-reading the same legacy line yields the same id and ingest is exactly-once even before the `(inode, offset)` tail cursor exists.
- `span_id` is 8 random bytes (16 hex chars, `UNIQUE`); `trace_id` is the first 16 bytes of `SHA-256(run_id)` (32 hex chars); `runs.run_id` is `UNIQUE` so the derived `trace_id` cannot collide. These are the OpenTelemetry span and trace id widths, so export is a structural map rather than a translation.
- Partial runs (no `run.ended` on SIGKILL or a HALT) are reconciled deterministically from the log alone: open spans whose run has gone inactive are force-closed with `status=unknown` at the last-seen timestamp, so rebuild-equals-live still holds.
- Retention is bounded and rebuildable: a sweep keeps the last N runs (config, default 50) and ages out older ones, deleting whole runs (their `events` rows and their `.shipboard/runs/<run_id>/` log dir) as a pure function over run boundaries, so neither `events` nor the run-scoped logs grow without bound and rebuild-equals-live holds over the retained window.
- One fact, one source of truth: tokens are stored only on `agent.finished`; `runs.total_tokens` and `total_cost_usd` are derived at projection. When a summary disagrees with the detail sum, the detail sum wins and the discrepancy is logged.

*Lineage: new; reuses the ADR-011 OpenTelemetry standard for a different subject, the build-machine rather than the product. Cross-reference C-02 (push transport), C-03 (control-plane security), C-04 (export and repository boundary).*
