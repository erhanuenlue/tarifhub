# Fazit notes (raw, running)

> One dated line whenever a tool surprises you — good or bad. The Fazit (6 pts) gets written from these in Block 3.

- 2026-06-10: workspace rebuilt lean for Fable 5; hypothesis to test — fewer agents + outcome prompts beat the 10-agent zoo on review burden.

↩ [[00-index]]

## 2026-06-13
- Veto moment: I rejected parallel implementation worktrees for Block-05 and kept the tightly-coupled console contract and brand truth-up in the orchestrator.
- Correction: codex gpt-5.5 found the client-only billing-field guard that earlier AI reviews missed, and I accepted the finding by adding server-side `BILLING_FIELDS` rejection in `app/api/review/route.ts` (commit 0524f9a).

## 2026-06-13
- Veto: I did not delegate the tightly-coupled console implementation to parallel worktrees, and kept the contract and brand layer in-orchestrator on Opus 4.8.
- Correction: codex gpt-5.5 found that earlier AI review under-weighted the client-only billing guard, and I accepted the finding by adding server-side `BILLING_FIELDS` rejection in `app/api/review/route.ts` (commit 0524f9a).

## 2026-06-13
- I did not delegate the billing-value guard to AI: codex gpt-5.5 found the client-only guard, I accepted the finding and added server-side `BILLING_FIELDS` rejection in `app/api/review/route.ts` (commit 0524f9a).
- I corrected an AI-backed documentation overclaim before submission evidence: the L2 intelligence service is containerised and runs, but remains post-CAS and outside the graded MVP value path (commit 080c9e0).

## 2026-06-13
- I rejected parallel implementation worktrees for the console and kept the tightly-coupled contract and brand implementation in-orchestrator.
- I corrected my own crit-17 overclaim: L2 intelligence is containerised and runs, but the rules feature stays post-CAS and outside the graded MVP value path.

## 2026-06-13
- I did not delegate the freeze line, value-path safety or final acceptance to AI; the billing guard correction in 0524f9a shows why server-side gates stayed human-owned.
- The biggest correction was evidence honesty: I accepted review findings where the draft overclaimed deployment scope or SQLite search behaviour, then reconciled the docs in 080c9e0 instead of defending the first draft.

## 2026-06-13
- Veto moment: I rejected parallel implementation worktrees and kept the console implementation in-orchestrator because the contract and brand layer were tightly coupled.
- Correction: I accepted the grader and codex gpt-5.5 findings where my docs overclaimed deployed L2 intelligence and misstated SQLite search behaviour, then reconciled the report with the implemented system.

## 2026-06-13
- I rejected parallel implementation worktrees for the console because the contract and brand layer were tightly coupled, and kept the implementation in-orchestrator on Opus 4.8.
- I corrected evidence claims when §10 and a screenshot contradicted ADR-017: SQLite search returned 200, while the live 501 came from the Postgres vector dimension guard.

## 2026-06-13
- Veto moment: I rejected parallel implementation worktrees and kept the console work in-orchestrator on Opus 4.8 because the contract and brand layer were tightly coupled.
- Correction: The grader and re-read passes changed two documented claims: L2 intelligence was not part of the graded deployed value path, and SQLite `/search` returns 200 rather than refusing offline search.

## 2026-06-13
- I rejected codex's reversed-freeze-line finding because the diagram expressed the AI-touchable versus immutable-value-path split, not the layer stack.
- I corrected the data-flow diagram after codex showed that human review happens after deterministic freeze into a new version, not as a gate before freezing.

## 2026-06-13
- Veto moment: I rejected parallel implementation worktrees for PR #16 because the TarifGuard console was one tightly-coupled contract and brand layer, and I kept the implementation in-orchestrator on Opus 4.8.
- Correction: codex gpt-5.5 twice caught evidence or artifact claims that first-pass verification missed: the deck was not fully offline until fonts were vendored, and the data-flow diagram wrongly showed human review gating freeze.

## 2026-06-13
- I rejected the AI suggestion to split implementation into parallel worktrees and kept the console work in-orchestrator because the contract and brand layer were tightly coupled.
- Codex gpt-5.5 caught false offline and diagram claims that my first-pass verifier and my own checks missed, so I corrected the artifacts and kept the diffs traceable.

## 2026-06-13
- I rejected the AI suggestion to split console implementation into parallel worktrees and kept the work in one Opus 4.8 orchestrator path because the contract and brand layer were tightly coupled.
- The independent gpt-5.5 CAS scoring pass found the phantom `parsers/fhir_parser.py` reference that the Opus pass had accepted, so I recorded it as a point-lift item instead of treating one model's full score as enough.

## 2026-06-13
- Final acceptance stayed owner-only: both graders found the unsigned Eigenstaendigkeitserklaerung as the largest C15 gap, and I recorded it as owner-only rather than letting AI close it.
- Independent model review changed the work: codex gpt-5.5 found the false offline deck claim and the phantom `parsers/fhir_parser.py` doc reference that first-pass review missed.

## 2026-06-13
- Veto: I rejected parallel implementation worktrees for the console and kept the tightly-coupled contract and brand layer in-orchestrator on Opus 4.8.
- Correction: I recorded the unsigned Eigenständigkeitserklärung as the largest C15 point gap, because final acceptance remains owner-only.

## 2026-06-14
- I did not accept the one-line `services/` sweep: even real P1 findings stayed out because the authorized task was exactly three docs and `.env.example` contradictions.
- A quoted CI log replaced my unbacked green claim in arc42/13: the correction was 18 Vitest tests passed, one e2e smoke passed, one CAPTURE-gated screenshot spec skipped.

## 2026-06-14
- I rejected service-layer P1 fixes in this task because the authorized scope was docs and `.env.example`, so `services/` changes needed a separate task and determinism-auditor.
- The surprise was that my own timeline claim about the console test script was wrong: `git show 265b2e3:apps/tarifguard/package.json` proved the stale-doc issue existed from day one.

## 2026-06-14
- I corrected the evidence claim after AI review showed that the console pipeline was `1 passed / 1 skipped`, not two green Playwright end-to-end tests.
- I rejected the `services/` fixes in this pass because the authorized scope was the three named documentation contradictions only.

## 2026-06-14
- I did not delegate the final meaning of the official rubric quotations to AI: I kept the German citation text verbatim and only added English glosses.
- The second-model repo-wide crawl corrected a false PASS from the diff-only verifier by finding two in-scope German files that my heuristic scan missed.

## 2026-06-14
- I did not let AI fully translate the official German rubric quotations; I kept the citations verbatim and glossed them in English.
- The C5 review showed that a verifier PASS was not enough; codex opened the serving and MCP source and forced me to correct `as_of`, response-shape and determinism overclaims before merge.
