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
