# Cockpit build spec

How the `tools/shipboard/shipboard.py` dashboard becomes an event-sourced agentic cockpit. Design artifact, em-dash-free. Pairs with `01-contracts.md` (the machine contracts) and the staged prompts under `docs/cockpit/prompts/`. Decisions recorded in `docs/cockpit/adr/` (C-01 to C-04). The whole `docs/cockpit/` tree, including `adr/`, is excluded from the MkDocs build (`exclude_docs`) and from the PDF, and is deferred to post-submission per C-04. Red-teamed 2026-06-14; the must-fixes from that review are baked in below and tagged `(Mn)`/`(Sn)`. A second principal red-team pass (fixes 4 to 11) is folded in and tagged `(fix N)`.

---

## 0. Thesis and scope
The current dashboard is observability by archaeology: it infers truth from Claude Code transcripts and command text, holds it in volatile memory, and serves a 2-second poll. The redesign inverts the data flow: emitters tell the cockpit what happened, durably; the cockpit persists, projects and pushes. The foundation (event-sourced, SQLite-persisted, OTel-native) makes run history, restart-survival, push liveness and a control plane straightforward instead of heroic.

**In scope this session: design only.** No implementation code is written. Stage 0 is built later, after the owner reviews this package.

---

## 1. Module split (strangler-fig, stdlib core)
The 2,702-line single file becomes a package. Each module is introduced additively; the monolith is gutted progressively, never rewritten big-bang.

```
tools/shipboard/
  __main__.py     CLI, wire collector+api+web, serve            (invocation: python3 -m, see 1.1)
  store.py        SQLite store: schema, append, project, query, rebuild   (zero-dep)
  events.py       typed envelope + payload schemas + validation + factories (zero-dep)
  collector.py    continuous in-process tailer thread: ingest run-scoped logs + approvals + session -> typed events; transcript enrichment DEMOTED (zero-dep)
  api.py          read-model handlers + SSE /events + control POSTs        (zero-dep)
  security.py     Host/Origin/token; optional unix socket                  (zero-dep)
  web.py + static/  UI assets (externalize the 1,100-line HTML string); vendored HTMX/Alpine; bespoke Canvas kept
  prices.py       pluggable cost from prices.json                          (zero-dep)
  control.py      (d2) loop supervisor: start/stop/resume loop.sh as a managed job  (zero-dep)
  otlp.py         (d3) spans -> OTLP/JSON export; ONLY module allowed a non-stdlib dep
  migrations/     SQL schema + future migrations
  shipboard.py    thin shim: `python3 tools/shipboard/shipboard.py` still works until extraction
```

### 1.1 Invocation contract (decide up front, must-fix M7)
Pick one and keep it: package run via `python3 -m tools.shipboard` for the real entry, with `shipboard.py` a thin shim that delegates to `__main__`. Absolute imports only (no implicit relative), so the package survives extraction to its own repo (C-04) without an import rewrite.

### 1.2 What is preserved (hard constraint)
- The everything-clickable to evidence inspector model. Every `/detail?type=...` endpoint keeps resolving, now from the store, so a past run resolves after restart (the "delegation not found (server restarted?)" amnesia is gone).
- The bespoke Canvas vault-graph, unchanged.
- Zero-dependency Python core. The only deviations, both named and justified: vendored HTMX/Alpine JS assets (C-02), and a quarantined OTLP exporter dependency in `otlp.py` if hand-rolled OTLP/JSON proves insufficient (C-04).

---

## 2. Migration stages
Four stages, four prompt files. Each is independently valuable and shippable, and the board works at every step. d1 and d2 are internally ordered into individually-green sub-steps so a partial land cannot merge a broken board.

### d0 Harden (no SQLite yet)
Cheap, high-ROI, no rewrite. Makes everything after it loop-able by giving the package a test harness and closing the security hole now that approvals are real.
- `ThreadingHTTPServer` with `daemon_threads=True`, socket timeout, BrokenPipe handling (replaces the single-thread bind).
- Security triad on all POSTs and `/reset` (C-03, must-fix M3): per-session `X-Cockpit-Token` (mandatory authorizer), Host allowlist, Origin check. `/reset` joins the protected set.
- Time fix (must-fix M4): `emit.sh` switches to UTC `gmtime` + `Z`; the dashboard stops force-tagging naive local as UTC.
- Gate-timeout TOCTOU fix (should-fix S1): `approval_gate.sh` writes a terminal `decided/<id>.json` with `decision:timeout` atomically before denying, so a late dashboard POST returns timeout, not a phantom allow.
- Definitive `run.ended` and a `loop.sh` `trap` so stale "running" is killed (groundwork for S4).
- Make the module importable (guard `serve_forever()` behind `__main__`, extract pure functions); add `tests/cockpit/` plus the zero-dep guard and the cockpit determinism-boundary AST test (S9). Add the minimal pytest runner config at the cockpit test root (a `conftest.py` or `pytest.ini` with `pythonpath = tools`, stdlib-only, no uv) so the guarded `cockpit:` job already present in `.github/workflows/ci.yml` runs the suites for real and is green (fix 4, S11). d0 does not edit `ci.yml`: that job is authored once in this package commit and is exists-guarded; d0 makes it green by creating the tests and the config.
- Allowed edits to `.claude/hooks/`: `approval_gate.sh` (timeout decision) and `shipboard_emit.sh` (UTC, and an optional `run_id` passthrough). Named exceptions only.

### d1 Event store (the keystone). Run STANDALONE, never through `loop.sh` (must-fix M2)
Because d1 edits `tools/loop.sh`, and `loop.sh` reads its own script incrementally, this stage must not be driven by `loop.sh`. Ordered sub-steps, each its own green PR:
1. `events.py` + `store.py` + `collector.py`: the collector reads the EXISTING legacy `.shipboard/events.jsonl`, synthesizes the envelope for each flat line with a DETERMINISTIC content-addressed `event_id` (a hash of `(file-identity, line-number, line-bytes)`, so re-reading the same line yields the same id and ingest is exactly-once across a collector restart, before the `(inode, offset)` cursor of sub-step 2 exists) and the active `run_id` (must-fix M1, d1 dedup fix), and the board reads from the store. Truncation still happens; prove old-board parity.
2. Run-scoped append-only logs `.shipboard/runs/<run_id>/events.jsonl`; stop truncating; the collector tails by `(inode, offset)` so a rotate is a new file, not an offset reset. Implement the bounded-retention sweep (keep the last N runs, age out older `events` rows and `runs/<run_id>/` dirs) and partial-run reconciliation as pure functions of the log (fix 10, S4, C-01). `.shipboard/` stays gitignored; confirm the SQLite file and `runs/` are ignored too (repo-fit).
3. `loop.sh` mints `run_id` (env `SHIPBOARD_RUN_ID`, additive: defaults to a generated ULID if unset so an un-migrated loop keeps emitting) and emits `run.started`/`run.ended` (with the `trap` from d0).

Result: run history, multi-run comparison, restart-survival. Frontend largely unchanged.

### d2 Push and control. Split into d2a then d2b (should-fix S12)
- **d2a**: `api.py` SSE `/events` (snapshot + delta + heartbeat + bounded `Last-Event-ID` replay, contract in `01-contracts.md` section 4); promote the d0 auth into `security.py`; SSE ships additively with `/state` poll kept as the `EventSource.onerror` fallback. A render/SSE parity test must prove the everything-clickable inspector did not regress.
- **d2b**: `control.py` loop supervisor (start, stop, pause, resume, re-run-a-prompt; supervises `loop.sh` as a managed child job) behind secured POSTs; the approval inbox becomes a first-class secured surface reading from the store.

This is when it becomes a cockpit, not a viewer.

### d3 Eval and adopt
- `otlp.py`: spans to OTLP/HTTP-JSON via `urllib`, targeting a generic OTLP collector by default; Langfuse dependency-gated after its ingestion contract is verified (should-fix S6, C-04).
- Run-comparison read-model and view (diff two runs across cost, duration, gates, CAS floor, files).
- The dual-blind scorecard / grade-auditor wired as a recurring tracked eval, score-over-time, regression flag.
- Finish the collector/api/web split; retire the monolith's remaining inline logic. Optional repository extraction (C-04), owner-gated.

---

## 3. Test plan (the loop fitness function, mandatory)
pytest, offline, stdlib, no containers (consistent with `uv run pytest -q`). Temp `.shipboard` and a temp-file SQLite per test. Seven suites; the first five are the brief's required set, the last two turn the zero-dep and determinism ethos into fitness functions.

1. **`test_event_store.py`** schema and WAL set; idempotent `append` (ULID `event_id`, `INSERT OR IGNORE`, `seq` monotonic); per-type projections; **rebuild-equals-live** (truncate projections, replay, identical read-models); restart-survival (close, reopen, data present); cost derived from an injected price table (change prices, cost changes, tokens unchanged); run isolation (run A query excludes run B); **seq-only ordering under cross-source clock skew** (feed UTC and naive-local events spanning a day boundary, assert `seq` order is correct and `ts_unix` is not trusted); partial-run reconciliation (S4); span_id 8-byte uniqueness, `trace_id` derivation, `runs.run_id` UNIQUE (M5).
2. **`test_collector.py`** legacy flat line to typed envelope with a synthesized globally-unique `event_id` and active `run_id`; approvals `log.jsonl` (requested/allow/deny/timeout) to approval events; **ingest, rotate or truncate mid-stream, ingest again, assert zero loss and zero double-count** (must-fix M1, replacing the offset-hash test); trust ordering (an `enrichment` event never overwrites an explicit `emit`); malformed line skipped, collector continues; naive timestamp explicitly localized or rejected (M4).
3. **`test_read_model_api.py`** `/api/runs` newest-first with status/cost/floor-delta; `/api/run/<id>` span tree plus gates plus approvals; `/detail` parity (everything-clickable preserved); **a past run's agent detail resolves after a simulated restart** (the amnesia regression killed); pending-approvals query from the projection (N4); 404s and query-param validation.
4. **`test_security.py`** Host `evil.com` to 403, `[::1]:PORT` allowed, missing Host on a POST to 403, `127.0.0.1.evil.com:PORT` to 403 (N1); cross-origin Origin to 403; token missing to 401, wrong to 401, correct to 200; (Origin absent + valid token) to 200, (absent + no token) to 401; **cross-origin `/reset` without token to 401** (M3); `OPTIONS` preflight returns no `Access-Control-Allow-Headers` and no permissive `Access-Control-Allow-Origin`; `rid` malformed to 400, unknown to 400; first-writer-wins on double-approve; body bound 65536; token file `0600`, gitignored, never in any log or event (S3); `/events` enforces Host and the cookie token (S2); **gate-timeout then late-approve returns timeout, not allow** (S1).
5. **`test_render_smoke.py`** (assertions land stage by stage, matching when each capability first exists, fix 11). **d0**: shell renders with no unsubstituted placeholder; token delivered by cookie, or HTML-escaped if inlined (S3); `--demo` seeds the legacy rail and the shell renders; `py_compile` every module and `bash -n` the hooks. **d1** (the store now exists): `--demo` seeds the store and the run list renders a run. **d2** (SSE now exists): connect yields a `snapshot` frame then a heartbeat; **append pushes a framed `id`/`event`/`data` message to a client within 100ms**; `Last-Event-ID` replays missed events, bounded to roughly 500 with a `gap` marker beyond; concurrent-SSE cap returns 503; a closed client frees its slot; `flush` after every frame.
6. **`test_zero_dep_core.py`** `store`, `events`, `collector`, `api`, `security`, `web` import only `sys.stdlib_module_names`; the first justified dependency (the OTLP exporter) is allowlisted to `otlp.py` only.
7. **`test_determinism_boundary_cockpit.py`** (should-fix S9) AST import-graph walk: no `anthropic`/`openai`/LLM-client symbol is reachable from `collector`/`store`/`events`/`api`/`security`, so cockpit projections (graded CAS evidence) are deterministic by construction. Mirrors the product's `test_determinism_boundary.py` and strengthens CAS crit 12.

Plus a contract assertion (S8): `tools/cas_check.py` and `tools/cas_baseline.json` are byte-unchanged across the migration.

### 3.1 TDD enforced by evidence, not intent (should-fix S13)
`loop.sh contract()` cannot prove a test existed before its implementation, and cockpit tests sit outside the CAS `services/` ratchet. So TDD-first is enforced two ways: each prompt's done-criteria require the ship report to **quote the failing-then-passing test run** (the CAS crit 14 evidence standard), and CI runs `tests/cockpit/**` with coverage so the green-contract actually gates the cockpit (S11).

---

## 4. Decisions

### 4.1 Owner-marked (await confirmation)
| Decision | Recommendation | Why |
|---|---|---|
| Frontend | HTMX + Alpine + SSE, keep bespoke Canvas | Server owns state, minimal JS, no build step, closest to the maintainer's comfort zone; Svelte's SPA weight is unjustified for one operator. C-02. |
| Adopt vs build | Adopt OTel + self-hosted Langfuse for trace/cost/eval; build only the control plane | The observability category is solved; the differentiated value (and product seed) is build-loop control, which nothing off-the-shelf provides. C-04. |
| Repo location | Extract post-submission into its own repo; emitters stay in tarifhub | Build-machinery and a product seed must not entangle the CAS freeze; the typed event schema is the stable contract between them. C-04. |

### 4.2 Stdlib boundary
SQLite (`sqlite3`), SSE (`http.server`), OTLP/HTTP-JSON (`urllib`) are all stdlib, so the core is **zero new dependencies through d2**. The first justified dependency appears at **d3**: an OpenTelemetry exporter, only if hand-rolled OTLP/JSON proves insufficient for the chosen collector, quarantined to `otlp.py` and policed by `test_zero_dep_core.py`. HTMX and Alpine are vendored JS assets (not Python deps), a named deviation from zero-JS, vendored rather than CDN-loaded to preserve "runs anywhere."

---

## 5. Safety and sequencing (hard rules for the build, not this session)
- **Do not create `prompts/cockpit/` until CAS submission is confirmed merged (6 July 2026).** `loop.sh` globs `prompts/<n>_*.md`, so passing `cockpit/d0` would reach `prompts/cockpit/d0_*.md`. The prompts are authored under `docs/cockpit/prompts/` precisely so the loop glob cannot reach them; promote them only post-submission. Each prompt carries this precondition (S10).
- **Allowed paths** for every cockpit prompt: `tools/shipboard/**`, `tests/cockpit/**`, `docs/cockpit/**` (the cockpit ADRs now live in `docs/cockpit/adr/**`), and the named hook files `.claude/hooks/approval_gate.sh` and `.claude/hooks/shipboard_emit.sh` (d0 only). `tools/loop.sh` is editable in d1 only, run standalone.
- **Excluded paths** (S8): `services/**` (the freeze line, hook-enforced), `db/migrations/applied/**`, `tools/cas_check.py`, `tools/cas_baseline.json`, `.claude/settings.json` (model pins, ADR-018), the boundary tests, `vault/**`, `docs/adr/**` (product ADRs 001 to 018), and `.github/workflows/**` (the guarded `cockpit:` job is authored once, in this package commit, not by a cockpit prompt).
- The d1 `loop.sh` edit is a real Gate-01 stop, not pre-approved; it is the one place the migration touches the harness that drives it.
- No cockpit change may lower the CAS floor; `cas_check.py` stays byte-unchanged (contract assertion in section 3).

---

## 6. Deliverable index
- ADRs: `docs/cockpit/adr/C-01` (event-sourced store), `C-02` (push UI/SSE), `C-03` (control-plane security), `C-04` (build-vs-adopt and repo boundary). Product ADRs 001 to 018 stay in `docs/adr/`.
- Contracts: `docs/cockpit/01-contracts.md` (event schema, DDL, OTel mapping, SSE wire).
- This spec: module split, migration, test plan, decisions, safety rules.
- Staged prompts: `docs/cockpit/prompts/d0_harden.md`, `d1_eventstore.md`, `d2_sse_control.md`, `d3_eval_adopt.md` (promote to `prompts/cockpit/` post-submission).
