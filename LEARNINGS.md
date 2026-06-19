# Learnings

This register records what the build got wrong and what caught it, drawn from the contemporaneous `vault/daily/` journal. Convention: every entry ends with its evidence ref (PR number + merge SHA); where an AI suggestion was involved its disposition is marked accepted ✓ / corrected ± / rejected ✗.

## AI output is untrusted input

- **2026-06-11: An `ai_map` error path that writes status into record metadata silently breaks idempotency.** Writing `ai_status` into metadata on a transient API outage produced a different `record_hash` than the no-key fallback, so re-ingest was no longer idempotent; 28 green tests missed it, Codex review caught it. AI corrected ± (PR #2, 057a6c1).
- **2026-06-12: Live AI fills are not byte-stable across runs, and a plausible concurrency diagnosis can be wrong.** Re-runs produced 55 re-versions; the e2e-tester's TOCTOU-race-in-`repo.add()` diagnosis was refuted at the merge gate (audit timestamps prove sequential runs; `UNIQUE(record_hash)` + zero duplicate hashes), the real cause being run-to-run `ai_map` churn. AI diagnosis rejected ✗, the fill-reuse fix landed (PR #8, d027a1d).
- **2026-06-12: A reviewer can invent an invariant; check it against the approved design before acting.** Codex P1 "a billing value must exist at freeze" was an invented constraint, rejected against the gate-01 design and the EAL precedent, while its coding[0] P2 in the same review was real and fixed: one review, two dispositions ✗ / ✓ (PR #5, ac8296c).
- **2026-06-12: Lock the canonical field set with a drift guard, not just discipline.** Codex's suggestion to enforce the ADR-003 additive-only field set was accepted and became `test_model_contract.py`. AI accepted ✓ (PR #12, 257c0e0).

## Engine parity

- **2026-06-11: `json.loads()` on a Postgres JSONB column (already a dict) would have 500'd every Postgres response.** SQLite-only tests were blind to it because the SQLite driver returns text; Codex caught it on the value path. AI corrected ± (PR #2, 057a6c1).
- **2026-06-11: `int`-for-`bool` passes SQLite and is rejected by Postgres; only a real engine surfaces it.** The first real Postgres run rejected a smallint in a boolean column where 51 green SQLite tests had not; the answer was a cross-engine read-parity suite with full-body snapshots (PR #6, 56b88cb).

## Evidence and docs discipline

- **2026-06-11: The orchestrator's own brief can propagate a factual error into many files.** A brief claiming explain returns 501 (the code 404s, no serving route existed) seeded the wrong status into 3 files; the fresh-context accuracy verifier caught it against the actual httpx path, corrected ± (PR #4, 07cdfc5).
- **2026-06-12: A docs agent will faithfully write a superseded contract; review the report against the approved design.** The docs implementer wrote the old 501-on-SQLite search contract and an AI-labelled explain into UC-09, both contradicting the gate-01-approved design; caught at orchestrator review of the agent report before commit, corrected ± (PR #12, 257c0e0).
- **2026-06-12: A single stray period breaks a "verbatim" rubric quote byte-for-byte.** A period inside the criterion-8 quote made arc42 §8 and the criterion map disagree (`2e 22` vs `22 20 28`); caught by the verifier via hexdump comparison, corrected ± (PR #13, fbe96d5).

- **2026-06-19: A build brief can assert a premise the code already contradicts; ground before building.** The Criterion-16 brief stated ingestion "has no HTTP server (it is a CLI/pipeline)", but `services/ingestion/.../main.py` was already a FastAPI app with a `test_api.py`; reading it first meant the review write-back extended the existing app (smallest change) rather than standing up a redundant second service. Recorded assumption: the console's richer raw-vs-proposal fixtures are illustrative, so the live `GET /review/queue` reconstructs the pair from `metadata.ai_fields` (an AI-filled field had an empty raw extract) instead of inventing a raw value that does not survive freeze. AI premise corrected ± *(this session, pre-commit; owner to add PR ref)*.

## Toolchain

- **2026-06-12: A lockfile is what makes a dependency tree auditable, not just reproducible.** The missing kassenflow/meldepilot lockfiles hard-failed `npm ci`, and once generated they exposed next@14.2.5's CRITICAL CVE-2025-29927 (+ 9 HIGH) to Trivy for the first time; the gate could only bite once the pin existed, so both stubs were aligned to tarifguard's clean next 15.5 set rather than suppressing the finding (PR #10, 1eaf013).
- **2026-06-12: Verify action majors against published tags; do not assume a floating alias exists.** astral-sh's setup-uv publishes no `v8` alias (only exact `v8.x` tags), so the Node-24-readiness bumps failed in 2s on tag resolution until pinned to exact `@v8.2.0`: "verify, don't guess" (PR #11, 8bb0b3b).
- **2026-06-12: A hook that silently rewrites derived state is invisible until something measures it.** The graphify git hooks full-walked ~77k vendored nodes and rebuilt code-only, dropping every doc/image node per commit; fixed at the right layer by making `.graphifyignore` a tracked single source of truth the incremental hooks consume, with the graph audit itself (criterion-16 tooling) as the detector (PR #9, cf5508c).
- **2026-06-12: e5 is asymmetric: queries need the `query:` prefix, passages the `passage:` prefix.** Block-0 embedded search queries through the passage path, degrading cross-lingual ranking; Codex's fix proposal, built on the same prefix confusion, was rejected ✗, and the `query:` prefix fix lifted recall@5 from .833 to .917, with the MRR@5 dip documented as a deliberate trade-off rather than hidden (PR #7, 5da6472).

## Freeze-line protocol

- **2026-06-11: A frozen-line type bug gets exactly one owner-authorized line, under a strict protocol.** `int(validation_ok)` in `audit/audit_logger.py` (below the freeze line) was rejected by Postgres's boolean column; `guard_frozen` blocked the edit, so per protocol the work stopped for Erhan, who authorized exactly one line in an isolated `fix(audit):` commit with the frozen-file diff shown pre-commit, the guard re-armed and probe-verified (a follow-up edit attempt was BLOCKED), and a Postgres round-trip regression test added outside the floor (PR #2, 057a6c1).
