# Cockpit contracts: event schema, SQLite store, OTel mapping, SSE wire

Machine-facing reference for the cockpit redesign. Authoritative for `events.py` (envelope and payload validation), `store.py` (DDL and projections), `otlp.py` (export), and `api.py` (SSE). Design artifact, em-dash-free per owner law. See ADR-019, ADR-020, ADR-021, ADR-022.

---

## 1. Typed event schema

### 1.1 Envelope (every event)
Every event is a JSON object with a common envelope plus a type-specific `payload`. Envelope fields:

| Field | Type | Required | Definition |
|---|---|---|---|
| `event_id` | string (26-char id) | yes | Idempotency key (`INSERT OR IGNORE`), distinct from any span id. Native emitters mint a full-entropy ULID (no truncation). The legacy-ingest path synthesizes a deterministic content-addressed id (see 1.5). |
| `run_id` | string (ULID) | yes (null only for pre-run global events) | Correlates all events of one loop or ship run. Derives the OTel `trace_id`. |
| `span_id` | string (16 hex chars = 8 bytes) | for span-bearing events | The span this event opens, closes or annotates. OTel span-id width. |
| `parent_span_id` | string (16 hex) | optional | Parent span for nesting (agent under phase under run). |
| `type` | string | yes | Dotted taxonomy (section 1.2). |
| `ts` | string (ISO-8601 with offset, UTC) | yes | Wall-clock at emit. Display and duration only, never the ordering key. |
| `ts_unix` | number (epoch seconds) | yes | Derived from `ts`. Display and duration only; not trusted across sources (see 1.4). |
| `seq` | integer | assigned by store | Monotonic insertion order, assigned by the single-writer collector. The sole total-order and replay authority. |
| `session_id` | string | optional | Claude Code session that produced it; links transcript enrichment. |
| `source` | enum | yes | `loop` \| `hook` \| `ship` \| `gate` \| `dashboard` \| `enrichment`. Encodes trust ordering (explicit emit wins over enrichment). |
| `schema_version` | integer | yes | Starts at 1. The cockpit accepts `schema_version <= N`; for `> N` it ingests but does not project the event, with a warning, so a newer emitter cannot silently drop history (ADR-022 extraction contract). |
| `payload` | object | yes | Type-specific fields (section 1.2), validated by `events.py`. |

`seq` is assigned by the store, not the emitter. Emitters that cannot reach the store (hooks, `emit.sh`) write the envelope without `seq`; the collector assigns it on ingest in arrival order.

### 1.2 Event types and payloads

```
run.started        { prompts:[str], model:str, cmd:str, cwd:str, git_branch:str, git_sha:str, floor_start:int }
run.ended          { status:"ok"|"failed"|"halted", floor_end:int, floor_delta:int, wallclock_s:number,
                     total_tokens:{in,out,cache_read,cache_write}, halt_reason:str? }
                     # note: total_tokens is an ADVISORY cross-check; the projected per-agent sum wins.
                     # total_cost_usd is NOT carried here: cost is always derived from prices.json.

phase.transition   { phase:"01".."09"|name, status:"running"|"pass"|"fail"|"skip", evidence_ref:str?, detail:str? }
                     # status=running OPENS a phase span; a terminal status CLOSES it.

agent.spawned      { agent:str, model:str, phase:str?, prompt_ref:str?, parent_span_id:str? }
                     # OPENS an agent span (child of the phase span, or the run span).
agent.finished     { agent:str, model:str, status:"done"|"error",
                     tokens:{in,out,cache_read,cache_write}, report_ref:str?, duration_s:number? }
                     # CLOSES the agent span. tokens are the ONLY place tokens are stored.

gate.result        { gate:"ratchet"|"floor"|"tree"|"secrets"|"ci"|"determinism"|"pytest"|"ruff",
                     passed:bool, detail:str?, evidence_ref:str? }
                     # point-in-time; projected to the gates table and mapped to an OTel span event.

approval.requested { approval_id:str, risk:"merge-to-main"|"destructive-git"|"publish"|"action",
                     tool_name:str, summary:str, tool_input_ref:str? }
approval.decided   { approval_id:str, decision:"allow"|"deny"|"timeout", via:"dashboard"|"telegram"|"cli",
                     by:str?, latency_s:number? }
                     # decision=timeout is written by the gate on its ~9-minute fail-safe (ADR-021).

commit             { sha:str, branch:str, message:str, files:[str], insertions:int?, deletions:int? }
merge              { sha:str, branch:str, target:str, pr:int? }
                     # commit and merge are first-class events; their OTel span-event mapping is export-time only.

session.started    { session_id, transcript_path? }          # optional, folds in .shipboard/session.json
session.compacted  { session_id, count:int }
session.ended      { session_id }

control.action     { action:"start"|"stop"|"pause"|"resume"|"rerun", by:str, run_id:str?, mode:str, target:str? }
                     # audit event for the loop control plane (ADR-021), one per control action.
                     # mode records the launch permission mode (non-bypass, or APPROVALS_ON=1 forced).
```

### 1.3 Span lifecycle and the trace tree
- **run** span: opened by `run.started`, closed by `run.ended`. The root span; `span_id` minted for the run.
- **phase** span: opened by `phase.transition{running}`, closed by the terminal `phase.transition`. `parent_span_id` is the run span.
- **agent** span: opened by `agent.spawned`, closed by `agent.finished`. `parent_span_id` is the enclosing phase span, or the run span if no phase is active.
- **gate** result and **commit**/**merge**: annotations on the enclosing span (projected to their own tables; exported as span events).
- **approval** span (optional): opened by `approval.requested`, closed by `approval.decided`, so latency is a span duration.

### 1.4 Time and ordering (must-fix M4)
Two legacy emitters stamp incompatible clocks: `emit.sh` writes naive local wall-clock (`strftime`, no offset), the approval gate writes UTC `-Z` (`date -u`). The existing dashboard force-tags the naive string as UTC (`shipboard.py:1167`), skewing any `ts_unix` math by the local offset.
- **d0 fixes the emitter**: `emit.sh` switches to `gmtime` plus explicit `Z` so all sources are UTC-with-offset.
- **`seq` is the sole ordering and replay authority.** `ts_unix` is a display and duration attribute; the collector localizes or rejects a naive timestamp explicitly and never silently assumes UTC.

### 1.5 Identifier rules (must-fix M5)
- `event_id`: 26 chars, idempotency only, never reused as a span id. Native emitters mint a full-entropy ULID (the 80-bit random component intact, never truncated, so two same-millisecond events do not collide and get swallowed by `INSERT OR IGNORE`). The legacy-ingest path (flat `emit.sh` lines carry no id) synthesizes a deterministic id from `(file-identity, line-number, line-bytes)`, so re-reading the same line is exactly-once even before the `(inode, offset)` tail cursor exists (must-fix from the d1 review).
- `span_id`: 8 cryptographically-random bytes, lowercase hex (16 chars), `UNIQUE`, minted at span open.
- `trace_id`: first 16 bytes of `SHA-256(run_id)`, lowercase hex (32 chars). `runs.run_id` is `UNIQUE`, so the derived `trace_id` cannot collide.
- `otlp.py` validates at export time and rejects all-zero or wrong-width ids.

---

## 2. SQLite schema (`store.py`)

`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;` All writes funnel through the `store` module on one connection (the collector ingest path and the control POST path share the single writer, see nice-to-have N5); HTTP readers use separate read-only connections.

```sql
-- The immutable event log: the source of truth.
CREATE TABLE events (
  seq            INTEGER PRIMARY KEY AUTOINCREMENT,  -- total order, replay key
  event_id       TEXT NOT NULL UNIQUE,               -- ULID, idempotency (INSERT OR IGNORE)
  run_id         TEXT,                               -- trace correlation; NULL only for global events
  span_id        TEXT,
  parent_span_id TEXT,
  type           TEXT NOT NULL,
  ts             TEXT NOT NULL,                       -- ISO-8601 UTC
  ts_unix        REAL NOT NULL,                       -- display/duration only
  session_id     TEXT,
  source         TEXT NOT NULL,                       -- loop|hook|ship|gate|dashboard|enrichment
  schema_version INTEGER NOT NULL DEFAULT 1,
  payload        TEXT NOT NULL DEFAULT '{}'           -- JSON
);
CREATE INDEX idx_events_run  ON events(run_id, seq);
CREATE INDEX idx_events_type ON events(type, seq);
CREATE INDEX idx_events_span ON events(span_id);

-- Read-model: one row per run (projection, rebuildable from events).
CREATE TABLE runs (
  run_id        TEXT PRIMARY KEY,                     -- UNIQUE so trace_id cannot collide
  status        TEXT NOT NULL,                        -- running|ok|failed|halted|aborted
  cmd           TEXT, model TEXT, prompts TEXT,       -- prompts = JSON array
  git_branch    TEXT, git_sha TEXT,
  started_ts    TEXT, started_unix REAL,
  ended_ts      TEXT, ended_unix REAL, wallclock_s REAL,
  floor_start   INTEGER, floor_end INTEGER, floor_delta INTEGER,
  total_in      INTEGER DEFAULT 0, total_out INTEGER DEFAULT 0,
  total_cache_read INTEGER DEFAULT 0, total_cache_write INTEGER DEFAULT 0,
  total_cost_usd REAL,                                -- DERIVED at projection from prices.json
  halt_reason   TEXT, updated_unix REAL
);
CREATE INDEX idx_runs_started ON runs(started_unix DESC);

-- Read-model: spans (the run/phase/agent/gate trace tree).
CREATE TABLE spans (
  span_id        TEXT PRIMARY KEY,
  run_id         TEXT NOT NULL,
  parent_span_id TEXT,
  kind           TEXT NOT NULL,                       -- run|phase|agent|gate|approval
  name           TEXT NOT NULL,                       -- '02' | 'implementer' | 'ratchet'
  status         TEXT,                                -- running|pass|fail|skip|done|error|unknown
  start_ts TEXT, start_unix REAL, end_ts TEXT, end_unix REAL, duration_s REAL,
  model          TEXT,
  attributes     TEXT,                                -- JSON: evidence_ref, detail, etc.
  FOREIGN KEY(run_id) REFERENCES runs(run_id)
);
CREATE INDEX idx_spans_run    ON spans(run_id, start_unix);
CREATE INDEX idx_spans_parent ON spans(parent_span_id);

-- Read-model: agents (denormalized cost ledger).
CREATE TABLE agents (
  span_id     TEXT PRIMARY KEY,
  run_id      TEXT NOT NULL,
  agent       TEXT NOT NULL, model TEXT, phase TEXT, status TEXT,
  parent_span_id TEXT,
  tokens_in   INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0,
  cache_read  INTEGER DEFAULT 0, cache_write INTEGER DEFAULT 0,
  cost_usd    REAL,                                   -- DERIVED, recomputable from prices.json
  prompt_ref  TEXT, report_ref TEXT,
  start_unix REAL, end_unix REAL, duration_s REAL,
  FOREIGN KEY(run_id) REFERENCES runs(run_id)
);
CREATE INDEX idx_agents_run ON agents(run_id);

-- Read-model: gates.
CREATE TABLE gates (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id      TEXT NOT NULL, span_id TEXT,
  gate        TEXT NOT NULL, passed INTEGER NOT NULL,  -- 0/1
  detail      TEXT, evidence_ref TEXT, ts TEXT, ts_unix REAL,
  FOREIGN KEY(run_id) REFERENCES runs(run_id)
);
CREATE INDEX idx_gates_run ON gates(run_id, ts_unix);

-- Read-model: approvals (the secured control surface).
CREATE TABLE approvals (
  approval_id  TEXT PRIMARY KEY,
  run_id       TEXT, session_id TEXT,
  risk         TEXT NOT NULL, tool_name TEXT, summary TEXT,
  status       TEXT NOT NULL,                          -- pending|allow|deny|timeout
  requested_ts TEXT, requested_unix REAL,
  decided_ts   TEXT, decided_unix REAL,
  decision_via TEXT, decided_by TEXT, latency_s REAL
);
CREATE INDEX idx_approvals_status ON approvals(status, requested_unix DESC);  -- pending-first queries (N4)

-- Bookkeeping.
CREATE TABLE meta ( key TEXT PRIMARY KEY, value TEXT );
-- rows: ('schema_version','1'), ('last_seq_projected','<n>')
```

### 2.1 Projection and rebuild
- The collector appends to `events`, then advances the projections incrementally and records `meta.last_seq_projected`.
- `rebuild_projections()` truncates every read-model table and replays `events` by `seq`. The rebuild-equals-live invariant (a projection is a pure function of the log) is a first-class test.
- **Cost is derived**: `cost_usd = (in*pi + cache_read*pi*0.1 + cache_write*pi*1.25 + out*po)/1e6` with `(pi,po)` from `prices.json`. Tokens are stored verbatim; changing prices changes cost without touching stored tokens.

### 2.2 Partial-run reconciliation (should-fix S4)
A pure function of the log, run on projection and on `rebuild`:
- A span whose run has a later `run.ended`, or whose `run_id` has had no event past an inactivity threshold, is force-closed `status=unknown`, `end_unix = last-seen ts` of that run.
- A run with no `run.ended` after the inactivity threshold projects `status=aborted` (or `halted` if a `run.ended{halted}` exists). `loop.sh` emits `run.ended` from a bash `trap` on `EXIT/INT/TERM` so common halts self-report `halt_reason`; SIGKILL is covered by the inactivity sweep. Because reconciliation reads only the log, rebuild-equals-live still holds.

---

## 3. OpenTelemetry mapping (`otlp.py`, export at d3)

| Cockpit object | OTel construct | Key attributes |
|---|---|---|
| run | root span (`name=run`) | `cmd`, `gen_ai.request.model`, `prompts`, `vcs.repository.ref.name=git_branch`, `vcs.revision=git_sha`, `cas.floor.start/end/delta`, `run.status` |
| phase | child span (`name=phase.NN`) | `phase.status`, `evidence_ref` |
| agent | child span (`name=agent.<name>`) | `gen_ai.system="anthropic"`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `tarifhub.gen_ai.usage.cache_read_tokens`, `tarifhub.gen_ai.usage.cache_write_tokens`, `tarifhub.cost_usd` |
| gate.result | span event on the phase span (`gate.<name>`) | `gate.passed`, `detail` |
| approval | child span request to decision | `approval.risk`, `approval.decision`, `approval.latency_s` |
| commit / merge | span event on the run span | `vcs.revision`, `vcs.repository.ref.name`, `vcs.change.files` |

Rules:
- `span_id` is the OTel 8-byte span id directly; `parent_span_id` is the OTel parent; `trace_id` is `SHA-256(run_id)[:16]`. No translation, only validation.
- **Cache tokens (should-fix S7)** are the dominant Claude cost driver and have no standard GenAI slot, so they are carried as namespaced custom attributes (`tarifhub.gen_ai.usage.cache_*`). Cost stays recomputable from `prices.json` on the consumer side; `tarifhub.cost_usd` is a clearly-custom derived attribute, never a source of truth.
- **Export target (should-fix S6)**: the zero-dependency `urllib` OTLP/HTTP-JSON path targets a generic OTLP collector (Tempo, OpenTelemetry Collector), where OTLP/HTTP-JSON is in spec. Langfuse is the dependency-gated option: verify its ingestion contract (endpoint, protobuf-vs-JSON encoding, required attributes) before committing; if a dependency is needed it is quarantined to `otlp.py` and explicitly allowlisted by `test_zero_dep_core.py`.

---

## 4. SSE wire contract (`api.py`, d2)

`GET /events` returns `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`. The first byte stream sends `retry: 3000` once.

### 4.1 Frame shapes
Each message is standard SSE framing, one blank line terminated:
```
id: <seq>
event: <type>
data: <json>

```
- `id:` is the event `seq` (the replay cursor for `Last-Event-ID`).
- `event:` is the dotted type, plus three control types: `snapshot`, `heartbeat`, `gap`.
- `data:` is the event envelope plus payload, or for `snapshot` the materialized state.

### 4.2 Connection lifecycle
1. Client connects (optionally `?run_id=<id>` to scope, optionally `Last-Event-ID:` header for replay). The read plane is gated by the Host allowlist and a `SameSite=Strict` cookie token set on first GET (ADR-021, S2): `EventSource` cannot set headers, so the cookie (or a loopback `?token`) carries authorization.
2. The server immediately sends `event: snapshot`, `id: <current max seq>`, `data:` = current materialized state (active run, phase tree, agents, pending approvals), derived from projection tables in O(1), not an events-by-ts scan (N4). The client renders instantly without waiting for deltas.
3. The server then streams every new event as `id: <seq>` / `event: <type>` / `data: <json>` as it is appended.
4. **Heartbeat**: every 15 seconds a comment line `: ping` is written and flushed; the write raising `BrokenPipeError` is how a dead client is detected and reaped.
5. **Reconnect and replay**: on disconnect, `EventSource` auto-reconnects with `Last-Event-ID: <last seq seen>`. The server replays events with `seq > Last-Event-ID` from the store (durable across server restart, the ADR-019 payoff), then resumes live. Replay is bounded to roughly 500 events (default scoped to the current run); beyond the bound the server sends `event: gap` and the client re-fetches a fresh `snapshot` rather than replaying thousands of rows. `?since=0` requests full history explicitly.

### 4.3 Push mechanism and concurrency (must-fix M7)
- The collector and the HTTP server run in **one process** sharing the SQLite file. A single always-on collector **tailer thread** (`collector.py`) continuously follows the run-scoped logs plus approvals and session, and appends to the store; nothing is read lazily per request (the old `read_events()` per-request scan is retired). After each committed ingest batch, the tailer pushes `(seq, type, payload)` into an in-process thread-safe fan-out: one `queue.Queue` per connected client under a `Lock`.
- Each SSE handler thread blocks on `queue.get(timeout=15)`: it wakes instantly on a new event and emits `: ping` on timeout. No store-polling, so latency is sub-100ms, not the 1 to 2 seconds a poll would re-introduce.
- `ThreadingHTTPServer` with `daemon_threads=True`, a socket timeout, a concurrent-SSE cap (roughly 16, excess returns `503`), `wfile.flush()` after every frame, and `BrokenPipe`/`ConnectionReset` caught on every write so a forgotten tab frees its slot.
- **Degraded fallback (S12)**: the `/state` poll endpoint stays alive through d2 and d3. The client uses `EventSource.onerror` to fall back to polling, so a single SSE defect cannot blank the board.

### 4.4 Security of the read plane
`/events` enforces the Host allowlist (ADR-021). Cross-origin `EventSource` is blocked by the browser because no `Access-Control-Allow-Origin` header is sent. `approval_id` values that appear in the stream are treated as non-secret; the bearer token is the sole authorizer for any state change (ADR-021), and event-derived strings rendered into the page are HTML-escaped.
