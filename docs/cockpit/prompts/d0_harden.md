# d0 · Cockpit harden (ThreadingHTTPServer, security triad, time fix, test harness)

> **Gate-01: pre-approved by the owner for the in-scope tooling work below.** Stop and ask if you would touch anything outside the Constraints block, contact the freeze line, breach the green-contract or ratchet, or run a destructive operation.
> **Precondition: do not run before CAS submission is confirmed merged (6 July 2026).** This prompt lives in `docs/cockpit/prompts/`; promote it to `prompts/cockpit/d0_harden.md` only post-submission, so `tools/loop.sh`'s glob cannot reach it earlier.

Run at `/effort ultracode`. Read `AGENTS.md`, `CLAUDE.md`, `docs/cockpit/00-build-spec.md`, `docs/cockpit/01-contracts.md`, and C-02/C-03. This stage is cheap, high-ROI, and adds NO SQLite. It hardens the running board and gives the package a test harness so every later stage is loop-able. TDD: write each test first, watch it fail, then implement.

## Constraints
- Allowed paths: `tools/shipboard/**`, `tests/cockpit/**`, `docs/cockpit/**` (cockpit ADRs under `docs/cockpit/adr/**`), and the named hooks `.claude/hooks/approval_gate.sh` and `.claude/hooks/shipboard_emit.sh` only. Do NOT edit `.github/workflows/ci.yml` (the `cockpit:` job already exists) or product `docs/adr/**`.
- Excluded: `services/**`, `db/migrations/applied/**`, `tools/cas_check.py`, `tools/cas_baseline.json`, `tools/loop.sh`, `.claude/settings.json`, the boundary tests, `vault/**`.
- Zero new Python dependencies. No em-dashes in any doc or comment. Do not lower the CAS floor; `cas_check.py` stays byte-unchanged.

## Work (verification checklist)
1. **ThreadingHTTPServer** with `daemon_threads=True`, a socket timeout, and `BrokenPipe`/`ConnectionReset` caught on every write. Replaces the single-thread `HTTPServer` bind. Still `127.0.0.1` only.
2. **Security triad on every state-changing POST including `/reset`** (C-03): mint `secrets.token_urlsafe(32)` on start, write `.shipboard/cockpit.token` mode `0600`, deliver it to the same-origin page, require `X-Cockpit-Token` on every POST as the mandatory authorizer (wrong or missing to 401 regardless of Origin); Host allowlist `{127.0.0.1:PORT, localhost:PORT, [::1]:PORT}` exact match, missing Host on a POST denied; Origin/Referer check as defense in depth, absent Origin never an independent allow path. `OPTIONS` preflight returns no `Access-Control-Allow-Headers`/`Access-Control-Allow-Origin`. Keep the existing `rid` format/existence validation, first-writer-wins, and 65536 body bound.
3. **Time fix** (must-fix M4): `emit.sh` switches to UTC `gmtime` plus explicit `Z`; the dashboard stops force-tagging the naive local string as UTC.
4. **Gate-timeout TOCTOU fix** (should-fix S1): on its ~9-minute fail-safe, `approval_gate.sh` writes a terminal `decided/<id>.json` with `decision:timeout` atomically (same `os.link` discipline) before denying, so a late dashboard POST hits first-writer-wins and returns timeout, not a phantom allow.
5. **Definitive run end**: emit a conclusive `run.ended` and add a `trap` groundwork note so a stale "running" cannot persist (full reconciliation lands in d1).
6. **Test harness and CI fitness function** (fix 4): guard `serve_forever()` behind `__main__`, extract pure functions so the module imports cleanly; create `tests/cockpit/` with `test_security.py`, `test_render_smoke.py`, `test_zero_dep_core.py`, and `test_determinism_boundary_cockpit.py` (the AST guard, S9), plus the minimal runner config at the cockpit test root (a `conftest.py` or `pytest.ini` with `pythonpath = tools`, stdlib-only, no uv). The guarded `cockpit:` job already exists in `.github/workflows/ci.yml` (it skips while `tests/cockpit/test_*.py` is absent, so it is green now); creating the tests + config makes it run `python3 -m pytest tests/cockpit -q` for real. Do NOT edit `ci.yml`.

## Done means (quote the evidence, do not assert it)
- `test_security.py` green, including: Host `evil.com` to 403, `[::1]:PORT` allowed, missing Host on POST to 403, `127.0.0.1.evil.com:PORT` to 403; cross-origin Origin to 403; token missing/wrong to 401, correct to 200; (Origin absent + valid token) to 200, (absent + no token) to 401; cross-origin `/reset` without token to 401; `OPTIONS` has no ACAH/ACAO; token file `0600`, gitignored, never logged; gate-timeout then late-approve returns timeout.
- `test_render_smoke.py` d0 assertions green (shell renders, token delivered, `--demo` seeds the legacy rail and renders, `py_compile` + `bash -n` clean), `test_zero_dep_core.py` and `test_determinism_boundary_cockpit.py` green.
- The `cockpit:` CI job runs `python3 -m pytest tests/cockpit -q` and is green on the PR: the fitness function is live, not merely "tests collected" (fix 4, S11).
- The board still serves with no UI regression; the inspector still resolves every clickable.
- Ship report quotes the failing-then-passing run of each new suite. Green-contract and ratchet hold; `cas_check.py` byte-unchanged. Then `/ship`.
