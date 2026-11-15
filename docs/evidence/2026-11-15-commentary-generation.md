# BAG commentary RAG: first generation run on eight dev cases

Measurement record of run `2026-11-15-generation` of the commentary RAG pilot
([ADR-025](../adr/025-commentary-retrieval.md)): for each of the eight dev cases, the top 5
passages of the frozen corrected retrieval went to `claude-opus-5-5` for a cited German answer.
Executed on 2026-11-15 from 00:21:11 to 00:33:33 CET (2026-11-14T23:21:11Z to 23:33:33Z; the
records store UTC, the file names carry the local date) on the macOS host, Python 3.13.12,
`anthropic` 0.109.1. The retrieval it builds on is recorded in
[the retrieval evidence](2026-11-14-commentary-retrieval.md) and was not rerun for this run.

**Exploratory pilot on dev cases, not an evaluation of answer correctness.** The eight cases and
the answer rubric are AI-drafted and pending Erhan's review; none is held out. Every check below
is deterministic (IDs, schema, term matches, status); whether a cited passage really supports a
claim has not been judged by a person, and all human ratings are empty.

**Update 2026-11-15, human review completed.** The paragraph above and the sections up to
"Human review requested at the time of the run" record the state at the end of the run. Erhan
Ünlü has since reviewed the same, unchanged answers: see
[Human review (completed 2026-11-15)](#human-review-completed-2026-11-15). No record of the run
was changed.

## What was and was not done

| Done and recorded here | Not done (at the time of the run) |
|---|---|
| Models API entry and token counts of every request before sending; a recorded plan with cost ceilings | Human rating of any answer, of the rubric or of the dev cases (done afterwards, see the last section) |
| One request per case, eight attempts, eight schema-valid answers; usage, latency, stop reason, returned model and calculated cost per attempt | Semantic, legal or tariff validation of any claim |
| Deterministic checks: citation membership, expected-evidence citation, required-fact term checks, abstention | A held-out test, a repeat of the run, another model or another retrieval configuration |
| Raw requests and responses kept locally (git-ignored), hashed in the public record | Comparison with an invoice (the cost is calculated) |

## Inputs (frozen before the run)

- **Retrieval**: hybrid RRF, edition filter, k = 5, 256-token passages, from
  `results/2026-11-14-retrieval-corrected.json` (SHA-256 `764c45ee0841...`). Its rerun on
  2026-11-14 (`results/2026-11-14-retrieval-rerun.json`, `332510cd0592...`) reproduced all 48
  rankings, every score and all passage hashes, so the contexts are the saved top 5. The run
  checked every passage's text hash against the saved record before sending.
- **Cases**: `cases.json` (`9d471418546a...`), unchanged; only the question, the selected
  editions and the passages with their provenance (document title, edition, PDF and printed
  page, section number and title) were sent. Reference answers, gold evidence and expected
  statuses were not (tested offline).
- **Rubric**: `rubric.json` (`654ca467de6e...`), written on 2026-11-14 before any answer
  existed and unchanged since: 19 required claims for the six answerable cases (15 with term
  checks, 4 left to human review), of which 14 had their support retrieved (all but D1's 5).
- **Prompt and schema**: system prompt `f8698c98e374...`, answer schema `31f86409999f...`
  (status, claims with passage citations, missing evidence). Request bodies are hashed per case
  in the plan and the record.
- **Prices**: `pricing.json`, Claude Opus 5.5 at $4 input and $20 output per million tokens,
  read on 2026-11-14 from the Anthropic pricing page (page SHA-256 `048ccb65c7aa...`).

## Configuration and access

`claude-opus-5-5` through the Anthropic Messages API directly (`https://api.anthropic.com`),
effort `max` (the repository's quality-before-cost rule; this model's API default is `medium`),
adaptive thinking (display left at the API default, omitted), `max_tokens` 32,000 for thinking
and answer together, non-streaming with a 1,200 s timeout, client retries off, no tools, web
search, MCP servers, fallback model, sampling parameters, prompt caching, `inference_geo` or fast
mode. The Models API reported `claude-opus-5-5` with `max_tokens` 128,000, `max_input_tokens`
1,000,000, effort levels `low` to `max`, structured outputs, and adaptive thinking only.

Access took three configuration rounds, all stopped on the first, free request and none billed:
a key not scoped to a workspace (HTTP 400 asking for `anthropic-workspace-id`), then a workspace
value the API rejected as invalid, then a replaced key. With the replaced key a non-empty
workspace ID was still present in `.env`, so the first plan of this run went out with that
header; it is kept unchanged as `results/2026-11-15-generation-plan-with-workspace-header.json`.
Because the owner intended no workspace ID, the plan was repeated and the run executed with the
variable set empty in the process (verified: the header is then not sent). The repeated plan,
`results/2026-11-15-generation-plan.json`, counted the same tokens and confirmed access without
the header.

## Plan and spending guard

| Case | Counted input tokens | Reserved ceiling (USD) |
|---|---|---|
| D1 | 3,148 | 0.6539 |
| D2 | 3,520 | 0.6555 |
| D3 | 3,370 | 0.6548 |
| D4 | 3,369 | 0.6548 |
| D5 | 3,533 | 0.6555 |
| D6 | 3,712 | 0.6563 |
| U1 | 3,487 | 0.6553 |
| U2 | 3,157 | 0.6539 |

Each ceiling is the counted input plus a 10 % margin at $4 per million, plus the full 32,000
output tokens at $20 per million. Before the run nothing was committed in the ledger; the
first-pass ceiling was $5.2401 and the ten-attempt worst case $6.5634, against the authorised
cumulative ceiling of $100. Every attempt was reserved in `results/generation-ledger.jsonl`
before it was sent and settled after; no reservation is open.

## Attempts

| Attempt | Outcome | Status | Input tokens (counted / reported) | Output tokens (thinking) | Latency (s) | Calculated cost (USD) |
|---|---|---|---|---|---|---|
| D1-1 | valid | insufficient_evidence | 3,148 / 3,148 | 26,183 (23,833) | 211.4 | 0.5363 |
| D2-1 | valid | answered | 3,520 / 3,520 | 15,547 (14,578) | 128.4 | 0.3250 |
| D3-1 | valid | answered | 3,370 / 3,370 | 6,099 (5,331) | 48.7 | 0.1355 |
| D4-1 | valid | answered | 3,369 / 3,369 | 5,640 (5,010) | 46.5 | 0.1263 |
| D5-1 | valid | answered | 3,533 / 3,533 | 6,482 (5,609) | 51.9 | 0.1438 |
| D6-1 | valid | answered | 3,712 / 3,712 | 22,478 (20,501) | 177.5 | 0.4644 |
| U1-1 | valid | insufficient_evidence | 3,487 / 3,487 | 4,019 (3,712) | 36.3 | 0.0943 |
| U2-1 | valid | insufficient_evidence | 3,157 / 3,157 | 4,633 (4,273) | 40.3 | 0.1053 |

Every response had HTTP 200, stop reason `end_turn`, returned model `claude-opus-5-5`, service
tier `standard`, inference `global`, speed `standard` and no cache tokens. No attempt failed, so
none was retried; 8 of the 10 allowed attempts are used.

**Usage and cost**: 27,296 input and 91,081 output tokens (82,847 of them thinking, 8,234
answer); calculated cost **$1.930804**, equal to 27,296 × $4 + 91,081 × $20 per million. It is
calculated from the provider-reported usage and the recorded prices, not taken from an invoice.
No charge is uncertain: there was no timeout or connection error, so no attempt is charged at
its reservation. The highest output was D1 with 26,183 of the 32,000 allowed tokens.

## Checks per case

| Case | Retrieval: gold items in the top 5 | Answer status (expected) | Citations in own context | Gold items cited / retrieved | Required claims: term-checked stated / with cited support / human review only / not retrievable |
|---|---|---|---|---|---|
| D1 | **retrieval miss**: 0 of 2 | insufficient_evidence (answered) | 11 / 11 | n/a (0 retrieved) | 0 / 0 / 0 / 5 |
| D2 | 3 of 3 | answered (answered) | 6 / 6 | 3 / 3 | 3 / 3 / 0 / 0 |
| D3 | 2 of 2 | answered (answered) | 6 / 6 | 2 / 2 | 2 / 2 / 0 / 0 |
| D4 | 3 of 3 | answered (answered) | 6 / 6 | 3 / 3 | 3 / 3 / 0 / 0 |
| D5 | 1 of 1 | answered (answered) | 9 / 9 | 1 / 1 | 0 / 0 / 2 / 0 |
| D6 | 4 of 4 | answered (answered) | 16 / 16 | 4 / 4 | 3 / 3 / 1 / 0 |
| U1 | no gold items | insufficient_evidence (insufficient_evidence) | no claims | n/a | none required |
| U2 | no gold items | insufficient_evidence (insufficient_evidence) | no claims | n/a | none required |

The four failure kinds are kept apart:

- **Retrieval misses**: D1's two gold items (July p. 6 and p. 7, ranks 6 and 7) are outside the
  top 5, so D1's five required claims were not reachable for the generator. This is a retrieval
  failure; nothing in the answer changes it.
- **Generation failures**: none. All eight responses completed, matched the schema (8 of 8) and
  came from the requested model.
- **Unsupported claims (deterministic indicators only)**: 0 of 54 citations point outside their
  request's context, and no claim is uncited. One term match for a claim whose support was not
  retrieved was flagged (D1-R4, "1. Juli 2026"); on inspection the date comes from D1 claims about
  other sections whose cited passages state it, so the flag is a term-check false positive, not
  evidence of an unsupported claim. Whether each claim is supported by what it cites is the
  pending human review.
- **Abstentions**: U1 and U2, which have no supporting evidence in the selected July commentary,
  answered `insufficient_evidence` (2 of 2 as expected); this means the selected passages do not
  state the answer, not that no tariff or change exists. D1 also answered
  `insufficient_evidence`, on a retrieval miss: an appropriate reaction at status level that does
  not repair retrieval. There was no false abstention in the five cases whose required support
  was retrieved.

Required facts: in the five answerable cases with retrieved support, all 11 term-checked
required claims were stated and each answer cited a passage covering their support; 3 required
claims (D5-R1, D5-R2, D6-R3) are semantic and left to human review. A passing term check is not
semantic validation: it cannot see polarity or attribution.

## Observations for the review (AI-assisted reading, not a human rating)

These come from reading the answers in the local review sheet with Claude (the same model family
as the generator), so they are not independent and decide nothing:

- D1's ten claims describe what the five retrieved passages do say (sections 2.2, 2.3, 2.4, 2.6
  and 4.1) instead of the asked positions; its missing-evidence list states that no passage names
  4700.00 or 1368.00 and that section 2.4 assigns the Auftragstaxe no position number.
- D1 claims 1 and 2 rest on provenance attributes rather than passage text: the decree date and
  AS number come from the July document title, and positions 1012.00 to 1288.00 from the section
  2.2 title, which the corpus truncates (a known limitation). The review sheet shows these
  attributes next to each cited excerpt.
- D2 lists the three 20 % positions and reports the seven other table rows as 10 % cuts; D6
  labels each claim with the edition it comes from, or as a comparison of both.

## Reproducibility and integrity

- The run executed with the tool files pinned in the record; after the run, only the review-sheet
  renderer of `run_generation.py` changed (`43ea74f5a1b6...` at run time, `90048babe3ac...` now:
  it now shows document and section titles beside each cited excerpt and can re-render the sheet
  alone). The sheet was re-rendered with `report --sheet-only`; the public record
  (`results/2026-11-15-generation.json`, `6cde1ad1bb11...`) is byte-identical to the one written
  at the end of the run, and no request was sent again.
- The baseline, corrected, comparison and rerun retrieval records are unchanged.
- Raw requests, raw responses (`local/2026-11-15-generation/`), the run result and the review
  sheet are local and git-ignored; the public record holds hashes, counts, usage and cost, no
  answer text. No credential or workspace ID is stored anywhere.
- The answers come from one run each; the model is not deterministic, and no repeat was made.
- Update 2026-11-15, before publication: `run_generation.py` and `run_eval.py` changed again
  after the review, so the published files differ from the hashes the record pins for them.
  Every step and `run_eval.py --out` now refuse to overwrite an existing output, the offline
  tests no longer skip for a missing dependency, and after an independent review the context,
  ledger, response-hash and redaction checks were tightened (README, "Code after the recorded
  run"). The run's contexts pass the stricter context check. No request, recorded value or
  metric changed, the run did not exercise this code, and no record of the run was rewritten.

## Assessment at the time of the run

The pilot shows that the pipeline works end to end on real data within its guards: hash-checked
contexts, counted and reserved requests, eight schema-valid answers on first attempts, every
citation inside its own context, the gold evidence that was retrieved cited in every case, both
unanswerable cases abstaining, and a calculated cost of $1.93 against a $6.56 worst case. It does
not show that the answers are correct or complete: the dev cases and rubric are unreviewed AI
drafts, the checks are deterministic, there is no held-out set, and D1, the Zwischenbericht 1
demo case, could not be answered because retrieval at k = 5 missed its evidence.

## Remaining limitations

- Eight dev cases, one run each, one model, effort `max` only; no repeat, no variance estimate.
- Term checks cover 15 of the rubric's 19 required claims and only by surface matching.
- D1 used 82 % of its output allowance; a longer thinking trace would have been cut off and
  counted as a generation failure.
- Passage provenance includes truncated section titles (continuation lines are lost), which a
  model can quote as if complete.
- Costs are calculated, not reconciled with an invoice.

## Human review requested at the time of the run

Completed on 2026-11-15 (next section). Requested then in
`tools/commentary_rag/local/2026-11-15-review-sheet.md` (local), for Erhan:

1. Each answer claim: supported by its cited passages and their attributes (yes / partly / no).
2. Each required rubric claim: covered by the answer, and whether the rubric claim itself is
   right.
3. Each case overall: appropriate behaviour, in particular D1's abstention on the retrieval miss
   and U1/U2.
4. The eight dev cases and their gold evidence (`cases.json`), still unreviewed.

## Human review (completed 2026-11-15)

Erhan Ünlü reviewed the eight stored answers of this run and confirmed all his ratings on
2026-11-15; they were transferred into the structured review file the same day (12:49 CET).

- **Method**: one reviewer, not blinded (he knew the cases, the rubric, the earlier reports and
  the model). Basis: the stored answers, the contexts the generator actually received with their
  metadata, the cases, the rubric and both original commentaries (their hashes match the
  manifest). Support was judged only against what the generator received; other PDF pages served
  to check the references and do not repair a retrieval miss. The missing-evidence statements of
  all eight answers were assessed too. An AI assistant supported presentation and recording and
  made no ratings. This is a document-grounding review on eight dev cases, not an independent
  expert validation, not a professional medical or legal certification and not a held-out test.
- **Integrity**: before the transfer, all 14 inputs linked by the review file (run record, rubric,
  cases, contexts, review sheet, ledger, the eight raw responses) matched their recorded SHA-256,
  and every claim text, rubric claim, question and citation list in the approved review matched
  the stored artifacts.

| Measure | Result | Kind |
|---|---|---|
| Citations inside their own request's context | 54 of 54 | deterministic check (run record) |
| Structured claims supported by what they cite | 48 of 48 | human review |
| Relevance of the structured claims | 27 yes, 14 partly, 7 no (of 48) | human review |
| Required rubric claims covered | 14 of 19 (D2 to D6: 14 of 14; D1: 0 of 5) | human review |
| Behaviour per case | appropriate in 7, partly appropriate in 1 (D1) | human review |
| End to end | 5 answered (D2 to D6), 2 appropriate abstentions (U1, U2), 1 not answered (D1, retrieval failure) | human review |
| Cases and references | question appropriate and reference expectation correct in 8 of 8; gold quotes of D1 to D6 judged correct search anchors, not complete proof of every sub-claim; no gold evidence for U1 and U2 (not applicable) | human review |
| Cost | $1.930804 calculated from reported usage, not reconciled with an invoice | run record |

| Case | Claims supported | Relevance yes / partly / no | Required claims covered | Behaviour |
|---|---|---|---|---|
| D1 | 10 of 10 | 0 / 4 / 6 | 0 of 5 | partly appropriate |
| D2 | 6 of 6 | 5 / 1 / 0 | 3 of 3 | appropriate |
| D3 | 6 of 6 | 4 / 2 / 0 | 2 of 2 | appropriate |
| D4 | 6 of 6 | 4 / 2 / 0 | 3 of 3 | appropriate |
| D5 | 7 of 7 | 5 / 2 / 0 | 2 of 2 | appropriate |
| D6 | 13 of 13 | 9 / 3 / 1 | 4 of 4 | appropriate |
| U1 | no claims (not applicable) | not applicable | none required | appropriate abstention |
| U2 | no claims (not applicable) | not applicable | none required | appropriate abstention |

From the review:

- **D1**: the abstention is justified, but the question stays unanswered because retrieval missed
  its evidence; the ten additional claims are supported but mostly off-topic. The answer keeps the
  recommended CHF 10 reduction apart from a decided tariff. The date in D1's other claims does not
  establish when the asked positions change (D1-R4 not covered).
- **U1 and U2**: neither invents a tariff or a change. U1's absence statement holds for the five
  received passages only: the July commentary names 1034.00 on p. 7, without a tariff.
- **Reservations for later evaluations**: D1's two gold quotes do not literally cover every part
  of its five rubric claims; D2's gold rows rely on the table header; some rubric support quotes
  (D1-R5, D6-R3) are shortened anchors to recheck after any change of chunking. No rubric item,
  reference or gold item was disputed, and none was changed.
- **Not settled by the review**: a separate overall relevance value per case (relevance is rated
  per claim), and a yes / partly / no value for the gold evidence of D1 to D6.

**Assessment after the review.** On these eight dev cases the generator stayed within the passages
it received: no structured claim was judged unsupported, the two unanswerable cases abstained, and
the five cases with retrieved evidence covered every required claim. The weak points are retrieval
(D1, the Zwischenbericht 1 demo case) and focus: 21 of the 48 claims are only partly relevant or
not relevant, 10 of them in D1. This is one non-blinded reviewer's judgement of one run on dev
cases; it is not an accuracy figure and says nothing about unseen questions.

Files: `tools/commentary_rag/results/2026-11-15-human-review-summary.json` (public: method,
limitations, aggregate counts, unsettled fields, source hashes); local and git-ignored, Erhan's
approved review `TarifHub_RAG_Bewertung_Erhan_2026-11-15.md` (SHA-256 `52efe0181811...`) and its
structured transfer `2026-11-15-human-review.json`. The run record, ledger, cases, rubric,
contexts, requests, responses and review sheet are unchanged.
