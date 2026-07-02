# Journal Excerpts

These are selected excerpts from the contemporaneous `vault/daily/` journal. They are a selection
only, never backfilled. The full journal lives in the repository (`vault/daily/2026-06-11.md`,
`2026-06-12.md`, `2026-06-13.md`). Each excerpt keeps its original commit or PR reference. Typography
is normalised to the house style. The synthesis these events add up to, the concrete lessons I take
forward, is collected in [What these events taught me](#what-these-events-taught-me) at the foot of
this page, and generalises into the single rule stated in the [Conclusion](fazit.md).

## Freeze-line guard event (2026-06-11, PR #2, 057a6c1)

Guard event, owner-authorised one-line type fix: the first real Postgres pipeline run exposed
`int(validation_ok)` in `audit/audit_logger.py` (below the freeze line). psycopg sends a smallint,
Postgres rejects it for the boolean column. `guard_frozen` blocked my edit. Per protocol I stopped
and asked. Erhan authorised exactly one line (`"validation_ok": validation_ok,`), conditions met:
isolated commit `fix(audit): ...`, frozen-file diff shown pre-commit, guard re-armed and
probe-verified (a follow-up Edit attempt was BLOCKED), and a Postgres round-trip regression test
added outside the floor (True/False/None, opt-in via `TARIFHUB_PG_TEST_URL`, 3 passed live).

## Codex catches a hash-breaking error path (2026-06-11, PR #1, 79169f0)

What AI got wrong, and what caught it: my `ai_map` error path wrote `ai_status` into metadata,
producing a different `record_hash` than the no-key fallback and breaking re-ingest idempotency
under transient API outages. This was caught by Codex review, not by the 28 green tests. In the
same review, serving `_row_to_record` called `json.loads()` on Postgres JSONB (already a dict), so
every Postgres response would have returned 500. Codex caught this too, while the SQLite-only tests
were blind to it. Both dispositioned as AI corrected.

## The explain-501 brief error (2026-06-11, PR #4, 07cdfc5)

What AI got wrong, and what caught it: my own brief told all writers "explain_crosswalk returns
501." The code 404s, because no serving route existed. The accuracy verifier checked the actual
httpx path and caught my orchestrator-level error after it had already propagated into 3 files. An
error in the orchestrator's own brief scales as fast as the agents do. A fresh-context verifier
against the real code is what bounded it.

## The e5 query-prefix recall gain (2026-06-12, PR #7, 5da6472)

e5 is asymmetric: queries need the `query:` prefix, passages the `passage:` prefix. Block-0 embedded
search queries through the passage path, degrading cross-lingual ranking. Codex's fix proposal,
built on the same prefix confusion, was rejected. The `query:` prefix fix lifted recall@5 from .833
to .917, with the MRR@5 dip documented as a deliberate trade-off rather than hidden.

## The lib/api.ts scaffold correction (2026-06-13, PR #16)

I corrected the previous AI scaffold in `lib/api.ts`: it used a camelCase, Java-flavoured contract
(`id`, `taxPoints`, POST explain/coding-check) that rendered every value as a dash placeholder
against the real snake_case serving API. I caught it by reading both sides of the wire, not by a
test. I also rejected the AI workflow suggestion to use parallel implementation worktrees and kept
implementation in-orchestrator on Opus 4.8, because the console was one tightly-coupled contract and
brand layer.

## Codex finds the client-only billing guard (2026-06-13, PR #16, 265b2e3)

I accepted the codex gpt-5.5 finding that the verifier and security pass under-weighted: the
billing-field guard was client-side only, plus the review BFF silently masked a configured upstream
failure as success. Diff pointer: the codex prompt "try to find what the first-pass reviews missed"
flagged the client-only billing guard, then the diff added server-side `BILLING_FIELDS` rejection in
`app/api/review/route.ts` (commit `265b2e3`).

## Distribution evidence captured into the repo (2026-06-13, PR #18, 7e0e4da)

Graders never deploy, so I captured real runtime evidence into the repo: `docker compose ps` with 8
independent containers, a live `EAL/1000` read at p95 15.8 ms, and a k3d `helm install` with 8 of 9
pods Running, all quoted in arc42 §7 and `docs/evidence/2026-06-13-distribution.md` and illustrated
by two PNGs at the time. The stale k3d screenshot was later replaced by a fresh pasted kubectl
transcript when the topology was recaptured against the current chart (PR #36), so the tree now
holds the compose PNG plus that transcript. Evidence that exists only at runtime had to be quoted
and interpreted in the report, not left as a screenshot.

## What these events taught me

The excerpts above are the raw record. These are the lessons I actually drew from them. Each is tied
to the event that taught it, and none is a general theory: together they generalise into the single
rule I carry forward, stated in the [Conclusion](fazit.md).

1. **A wrong premise in the plan scales as fast as the agents consume it.** My own brief asserted
   `explain_crosswalk` returned 501 when the code 404s, and that single error had already propagated
   into three files before a fresh-context verifier caught it against the real httpx path (PR #4,
   `07cdfc5`). The orchestrator's mistakes do not stay local, so the plan is the highest-leverage
   place for a human to read.

2. **Green tests prove only the paths and the engine you ran them on.** The independent reviewer
   caught two defects that 28 green tests missed: a `json.loads()` on a Postgres JSONB value (already
   a dict) that would have returned 500 on every Postgres read, invisible to the SQLite-only suite
   because SQLite returns text, and an `ai_map` error path that wrote `ai_status` into metadata and so
   produced a different `record_hash` than the no-key fallback, silently breaking re-ingest
   idempotency under a transient API outage (PR #1, `79169f0`). I now treat a second engine and a
   second model family as coverage for different blind spots, not as belt-and-braces on the same one.

3. **Ungrounded generation is most dangerous exactly where it meets a real contract.** The
   `lib/api.ts` scaffold rendered every served value as a dash placeholder because it was written
   against an invented camelCase shape, and no test caught it: reading both sides of the wire did
   (PR #16). At a contract surface I now ground the generation in the real artifact before trusting
   it.

4. **Enforce the boundary in code, not by trust.** When a worker wrote an `int` into a boolean audit
   column below the freeze line, the `guard_frozen` hook blocked the edit and halted the run for my
   one-line authorisation (PR #2, `057a6c1`). A rule the tooling enforces, a hook or the drift guard
   that later became `test_model_contract.py`, holds under autonomy in a way a documented convention
   does not, and that is what lets the loop run unattended.
