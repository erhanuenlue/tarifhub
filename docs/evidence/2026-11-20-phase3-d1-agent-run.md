# Evidence-seeking agent: first live run, development case D1

Record of the first and only live run of the one-question runner of
[ADR-026](../adr/026-commentary-evidence-search.md) (proposed), authorised by Erhan for one
invocation. Executed on 2026-11-20 from 00:19:07 to 00:22:37 CET (2026-11-19T23:19:07Z to
23:22:37Z; the records store UTC, the file names carry the local date) on the macOS host, with
the code of `main` at `df5d20d` (PR #55, the runner's squash merge; every tool file hash in the
record matches that revision). Python 3.13.12, `anthropic` 0.109.1, `httpx` 0.28.1,
`claude-opus-5-5` with effort `max`, adaptive thinking and `max_tokens` 32,000.

**One development observation, not an evaluation.** D1 is a dev case already used in Phase 2
and in the first progress report; nothing is held out, nothing was repeated, and no other
condition (fixed top 5 or top 10) was run. The run figures below come from the saved files and
deterministic checks of them; whether the answer's claims are supported and relevant is Erhan's
judgement, confirmed on 2026-11-21 and summarised in
[Human review](#human-review-confirmed-2026-11-21).

## Inputs

- `run_question.py run --case-id D1 --edition 2026-07-01 --time-budget-s 600 --tag 2026-11-20`
  with the D1 question verbatim (SHA-256 `e35d33da1135...`), the API key from the root `.env`
  and the workspace header off, as in the [2026-11-15 run](2026-11-15-commentary-generation.md).
- The fresh initial top 5 (hybrid, edition 2026-07-01 only) equals D1's recorded Phase 2
  context, in IDs, order and text hashes (`2026-11-15-generation.json`) and in scores
  (`2026-11-14-retrieval-corrected.json`): `p4/s2.3/2`, `p4/s2.4/1`, `p7/s2.6/1`, `p8/s4.1/1`,
  `p4/s2.2/1` (all `2026-07-01/`). The offline `prepare` step reproduced it before
  the run. No dev case, gold evidence, rubric or expected answer reached the agent.
- Before `prepare`, the local commentary environment had to be rebuilt offline from the lockfile
  (a temporary-folder purge had removed files of it); no repository file changed.

## Outcome

| Exit code | Execution outcome | Answer status | Accounting status |
|---|---|---|---|
| 0 | `answer` | `partial` (structurally accepted) | `priced` |

| Call | Tool offered | Stop reason | Counted input | Reported input / output (thinking) | Reserved USD | Calculated USD |
|---|---|---|---|---|---|---|
| 1 | yes (`auto`, no parallel tool use) | `tool_use` | 3,860 | 3,860 / 528 (307) | 0.741365 | 0.026 |
| 2 | no (`none`) | `end_turn` | 7,288 | 7,288 / 25,270 (22,194) | 0.77455 | 0.534552 |

- **Two priced calls, one search, ten passages supplied.** The one search returned five new
  passages from its top-10 window (ranks 1, 2, 4, 5 and 6; rank 3 was already supplied):
  `p4/s2.4/3`, `p6/s2.5/5`, `p4/s2.4/2`, `p6/s2.5/3`, `p5/s2.4/2`. That filled the
  10-passage budget, so the second call offered no tool: the passage cap, not the model,
  prevented a second search. The run took 210.8 s of its 600 s cooperative budget.
- **One of the two previously missing D1 passages was retrieved and cited.**
  `2026-07-01/p6/s2.5/5` (D1's first evidence item in `cases.json`) came back at rank 2 and is
  cited. `2026-07-01/p7/s2.5/1` (its second) was neither supplied nor cited; its rank for the agent's query is unknown, since the record keeps only the
  passages a search returns, and ranking it now would be a new condition.
- **The answer** matches the schema and cites only supplied passages: status `partial`, 17
  claims citing six passages (`p4/s2.4/1`, `p4/s2.4/2`, `p4/s2.4/3`, `p5/s2.4/2`, `p6/s2.5/3`,
  `p6/s2.5/5`), six missing-evidence items, SHA-256 `aa9ea5460028...`. That is a structural
  check, not a judgement of correctness, support or rubric coverage; those are in the human
  review below.

## The books

| Item | USD |
|---|---|
| Phase 2 committed, opening balance of the active ledger (historical ledger unchanged, SHA-256 `e0d031ac4b64...`) | 1.930804 |
| Admission check for this question (three calls at the 80,000-token cap; a check, not a charge) | 4.4352 |
| Reserved: call 1 + call 2, each the ceiling of its counted input | 0.741365 + 0.77455 |
| Settled from validated usage: call 1 + call 2 | 0.026 + 0.534552 = 0.560552 |
| Still reserved | 0 |
| Aggregate committed, Phase 2 and Phase 3, of the USD 100 limit | 2.491356 |

The active ledger holds the pin, two reservations and two usage settlements. Costs are
calculated from reported usage and `pricing.json`, not taken from an invoice. A read-only
reconciliation of the saved files passed 42 checks: both ledgers read by the agent's own strict
reader, every request and response file matching the hash its ledger line and the public record
name, each reservation recomputed as the ceiling of its count, each cost recomputed from the usage
re-validated out of the saved response, the public record agreeing with the local result and
answer, and every tool file hash matching `df5d20d`.

## Provider interactions

Observed once each, all accepted: token counting with the tool definition; a request with one
strict tool beside the JSON-schema answer format, adaptive thinking and effort `max`;
`tool_choice` `auto` with parallel tool use disabled, answered by exactly one tool call; the
assistant turn replayed verbatim (a thinking block with empty text and a signature, then the
tool call) followed by the tool result for its ID; `tool_choice` `none` with the tool still
listed, answered in the schema. Both responses named `claude-opus-5-5`, reported usage the
validator priced (`service_tier` `standard`, `inference_geo` `global`, so no US multiplier, and a
`speed` field the validator does not inspect), and the counted input equalled the reported input.

Untested live: a third call, a second search, a refused or failed search, error responses,
timeouts and lost connections, the deadline paths, a reservation kept as exposure, a cost above
its reservation, failed writes, lock contention, the workspace header and US inference.

## Human review (confirmed 2026-11-21)

Erhan Ünlü reviewed the stored answer of the 2026-11-20 run and confirmed his ratings on
2026-11-21. He judged each of the 17 claims against the passages and attributes the agent had
received, the five D1 rubric items against what the answer says, the six reported gaps against all
ten passages the agent received, and the two overall questions. One reviewer, not blinded: the
rubric, the Phase 2 result for D1 and this run's outcome were known. An AI assistant presented
the material and recorded his choices and made no rating. The counts below were checked against
the completed local worksheet before publication; the ratings, his notes and the answer text stay
local.

| Review dimension | Confirmed result |
|---|---|
| Support for 17 claims | 16 yes, 1 partly, 0 no |
| Relevance of 17 claims | 9 fully, 4 partly, 4 not relevant |
| Coverage of 5 rubric items | 3 yes, 1 partly, 1 no |
| Accuracy of 6 reported gaps | 5 yes, 1 partly, 0 no |
| Relevance of 6 reported gaps | 3 fully, 1 partly, 2 not relevant |
| Was `partial` appropriate? | Yes |
| Was the agent's overall behaviour appropriate? | Partly |

In this one case the answer covered both tariff changes and how they offset each other (rubric
items R1 to R3). It covered the effective date only partly (R4): the date came from the document
title, and the answer itself reported that the received passages state no effective date for the
changes in sections 2.4 and 2.5. It missed the evaluation of the 1368.00 tariff through 30 June
2028 and its recalculation under transAL-2 (R5), whose passage was not among the ten received.
The targeted search recovered one of the two previously missing evidence passages
(`2026-07-01/p6/s2.5/5`, which carries R1 to R3); the other (`2026-07-01/p7/s2.5/1`, which
carries R4 and R5) was not returned, and the passage budget then left no second search.

These findings describe one answer to one development case, from one run, rated by one person.
D1 was used before and is not held out, so they are not an accuracy figure for the agent and say
nothing about other questions; the wider Phase 3 evaluation is separate.

## Files

- Committed, in `tools/commentary_rag/results/` (outside this site, so named by path; the pilot
  README links them): the active ledger `phase3-ledger.jsonl` (SHA-256 `ac0bd49ae8d9...`) and
  the public record `2026-11-20-question-D1.json` (`3a63dee7ab30...`), both kept byte for byte
  as the run wrote them, beside the unchanged Phase 2 ledger `generation-ledger.jsonl`. The record's
  field `provider_contract` still reads "unverified before the first live run (ADR-026)": the
  code at `df5d20d` writes that text, and it is kept as emitted; this page records what the run
  observed.
- Local and git-ignored: the raw requests and responses, the answer and the full result in
  `tools/commentary_rag/local/2026-11-20-question-D1/`, the runner's console output beside it,
  the review worksheet as generated (`tools/commentary_rag/local/2026-11-20-D1-review-worksheet.md`,
  ratings empty) and Erhan's completed copy beside it
  (`2026-11-20-D1-review-worksheet-erhan.md`, his ratings and notes). No question, answer,
  passage, search, provider or review-note text is in a committed file.
