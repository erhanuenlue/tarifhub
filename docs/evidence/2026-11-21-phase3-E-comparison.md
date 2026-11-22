# Phase 3 comparison: fixed top 5, fixed top 10 and the evidence-seeking agent on E1 to E6

Record of the first and only live run of the comparison runner of
[ADR-026](../adr/026-commentary-evidence-search.md) (proposed) and of Erhan's blinded review of
its 18 answers. One authorised invocation of `run_comparison.py run` on the frozen evaluation set
E1 to E6, executed on 2026-11-21 from 16:56:07 to 17:23:29 CET (2026-11-21T15:56:07Z to
16:23:29Z, first reservation to last settlement; the console ran from 15:55:49Z to 16:23:30Z) on
the macOS host with the code of `main` at `861994b` (PR #57; every tool file hash in the record
matches that revision and none was uncommitted). Python 3.13.12, `anthropic` 0.109.1, `httpx`
0.28.1, `claude-opus-5-5` with effort `max`, adaptive thinking, `max_tokens` 32,000, 600 s per
cell, no retries. The ratings were confirmed on 2026-11-22.

**Six cases, one run per case and condition, one reviewer.** The figures below are observations
on this set, not accuracy figures and not estimates for other questions. E1 overlaps the
development case D1 and is reported apart; the primary set is E2 to E6. Retrieval figures come
from deterministic checks of the saved files; support, relevance, coverage, status fit and the
overall verdicts are Erhan's judgements.

## Inputs

- The frozen evaluation set: six cases, AI-drafted, decided by Erhan and frozen on 2026-11-21
  before any retrieval or generation on them
  (freeze record `tools/commentary_rag/results/2026-11-21-phase3-E-freeze.json`: runner input SHA-256 `93d1e25d32cb...`, the private gold evidence and rubric by hash, each
  question by hash). Questions, gold evidence and rubric stay local.
- Three conditions per case, fixed in code: A `fixed5` (the Phase 2 request with the hybrid top
  5, one call, no tool), B `fixed10` (the same with the top 10) and C `agent` (the top 5, the
  search instruction and the one search tool, at most three calls, two searches and ten
  passages). One fresh hybrid ranking per case over its editions only: A's five are B's first
  five and C's initial five.
- The runner's offline plan before the run: a worst case of USD 44.352 against USD 97.508644 of
  headroom, an estimate of about USD 6.29 from development cases.

## Outcome and books

All 18 cells ended with an accepted answer or abstention (execution `answer`, accounting
`priced`); none failed, was skipped or stopped, and the runner exited 0. Every C cell searched
exactly once, after its first call, and that search filled the ten-passage budget, so its second
and last call offered no tool; no C cell made a third call.

| Item | USD |
|---|---|
| Committed before the run (Phase 2 1.930804 + D1 0.560552) | 2.491356 |
| This run: 24 calls (A 6, B 6, C 12), each reserved at its ceiling, then settled from usage | 4.569196 |
| Reserved for those 24 calls before sending | 18.188853 |
| Committed now, Phase 2 and Phase 3 together, of the USD 100 limit | 7.060552 |
| Outstanding reservations | 0 |

No call cost more than its reservation and every settlement is priced from validated usage. The
active ledger `phase3-ledger.jsonl` grew from 5 to 53 lines (24 reservations, 24 settlements); its
first five lines are byte-identical to the books before the run (SHA-256 `ac0bd49ae8d9...`), and
the historical Phase 2 ledger is unchanged. The public record's cost of every call equals its
ledger settlement, the agent's own reader (`spending_state`) reports USD 7.060552 committed, and
the per-condition sums below add up to USD 4.569196. Costs are calculated from reported usage and
`pricing.json`, not taken from an invoice. The plan's estimate (about 6.29) was above the
calculated cost.

## Review and unblinding

The packet showed each case's question and frozen rubric, then its three answers under neutral
IDs in an order fixed before any answer existed, each claim with its citations and the text of
every passage it cites. How an answer was produced, call and search counts, costs and timings were
withheld. Erhan rated every claim (support, relevance), every required claim (covered yes, partly
or no, and by which claims), the gaps a good answer should name, the listed errors and any other
error, whether the answer's status fits its claims and cited passages, and an overall verdict.

Before the key was opened, in this order:

1. Both packet files matched the SHA-256 values Erhan gave (blank `5a175878a8d2...`, completed
   `66e080873519...`).
2. His marks were transferred into a structured ratings file on the existing template. Re-rendered
   into the blank packet, that file reproduces his completed packet exactly (2157 of 2157 lines),
   so every transferred value equals his mark and nothing else in the packet changed: 124 claims,
   39 required-claim marks, 6 gap marks, 75 listed-error checks (none marked present), 18 status
   and 18 overall verdicts.
3. The hashes of both packets, the template, the ratings file, the neutral ID listing and the key
   were committed in `tools/commentary_rag/results/2026-11-22-phase3-E-review-lock.json` in a
   commit of their own, before the key's content was opened (its file was only hashed for the
   lock).

After it: the key named all 18 IDs once each, every case had exactly one `fixed5`, one `fixed10`
and one `agent` answer, and under every ID the packet shows exactly the answer of the cell the key
names.
A local script repeats every check from the files and stops at the first mismatch: the lock
hashes, the transfer (including that the recorded errors follow from the error marks), the key
(under every ID the packet shows the status, the claims with their citations and the named gaps
of the cell the key names) and the saved run result against the public record (each answer
hashes to the record's `answer_sha256`). It produced the public summary `tools/commentary_rag/results/2026-11-22-phase3-E-review-summary.json` (case
and condition only). An independent reimplementation of the join in the session gave the
same figures. The ratings, the key, the neutral-ID mapping, Erhan's notes and all answer and
passage text stay local.

## Results by case and condition

"Status (expected)" is the answer's status and, in brackets, the status the rubric expects if all
required evidence were in context; "status fits" is Erhan's judgement of the status against the
answer's own claims and cited passages, which is the fairer test for a condition that lacked
evidence. Gold items are the required-evidence items of the frozen gold file (edition, page and
quote matched in the passages each condition received; section anchors are not checked
automatically). E5's required claims include one claim of kind gap, scored by the reviewer and
outside the evidence denominator; E6 has no required claims or evidence items, so its Evidence
Recall is N/A, and its one gap a good answer names was named by all three answers.

| Case | Condition | Status (expected) | Status fits the answer | Required claims yes/partly/no | Claims | Supported yes/partly/no | Relevant fully/partly/not | Errors recorded | Overall | Gold items in context / cited | Calls | USD | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E1 | A fixed5 | `insufficient_evidence` (`answered`) | yes | 0/0/2 of 2 | 5 | 5/0/0 | 0/4/1 | 0 | partly | 0/2, 0/2 | 1 | 0.218752 | 84.4 |
| E1 | B fixed10 | `answered` (`answered`) | no | 1/0/1 of 2 | 9 | 9/0/0 | 2/6/1 | 0 | partly | 1/2, 1/2 | 1 | 0.218560 | 78.8 |
| E1 | C agent | `answered` (`answered`) | yes | 2/0/0 of 2 | 9 | 9/0/0 | 2/7/0 | 0 | yes | 2/2, 2/2 | 2 | 0.344516 | 120.8 |
| E2 | A fixed5 | `insufficient_evidence` (`answered`) | yes | 0/0/2 of 2 | 4 | 3/1/0 | 0/2/2 | 0 | partly | 0/5, 0/5 | 1 | 0.330220 | 129.5 |
| E2 | B fixed10 | `partial` (`answered`) | yes | 1/1/0 of 2 | 6 | 6/0/0 | 3/2/1 | 0 | partly | 3/5, 3/5 | 1 | 0.175876 | 60.7 |
| E2 | C agent | `answered` (`answered`) | yes | 2/0/0 of 2 | 11 | 11/0/0 | 3/5/3 | 0 | yes | 5/5, 5/5 | 2 | 0.267028 | 90 |
| E3 | A fixed5 | `answered` (`answered`) | no | 2/0/1 of 3 | 9 | 6/3/0 | 4/5/0 | 0 | partly | 4/5, 4/5 | 1 | 0.404848 | 148.9 |
| E3 | B fixed10 | `answered` (`answered`) | yes | 3/0/0 of 3 | 9 | 7/2/0 | 3/6/0 | 0 | yes | 5/5, 5/5 | 1 | 0.463300 | 171.2 |
| E3 | C agent | `answered` (`answered`) | yes | 3/0/0 of 3 | 10 | 8/2/0 | 5/5/0 | 1 | yes | 5/5, 5/5 | 2 | 0.327068 | 113 |
| E4 | A fixed5 | `answered` (`answered`) | yes | 3/0/0 of 3 | 8 | 8/0/0 | 1/6/1 | 0 | yes | 1/1, 1/1 | 1 | 0.229696 | 85.3 |
| E4 | B fixed10 | `answered` (`answered`) | yes | 3/0/0 of 3 | 9 | 9/0/0 | 2/5/2 | 0 | yes | 1/1, 1/1 | 1 | 0.261000 | 93.6 |
| E4 | C agent | `answered` (`answered`) | yes | 3/0/0 of 3 | 5 | 5/0/0 | 2/2/1 | 0 | yes | 1/1, 1/1 | 2 | 0.207828 | 63.7 |
| E5 | A fixed5 | `partial` (`partial`) | yes | 3/0/0 of 3 | 5 | 5/0/0 | 2/3/0 | 0 | yes | 2/2, 2/2 | 1 | 0.087524 | 28.7 |
| E5 | B fixed10 | `partial` (`partial`) | yes | 3/0/0 of 3 | 5 | 5/0/0 | 2/3/0 | 0 | yes | 2/2, 2/2 | 1 | 0.105436 | 32.3 |
| E5 | C agent | `partial` (`partial`) | yes | 3/0/0 of 3 | 5 | 5/0/0 | 3/2/0 | 0 | yes | 2/2, 2/2 | 2 | 0.131696 | 34.3 |
| E6 | A fixed5 | `insufficient_evidence` (`insufficient_evidence`) | yes | none | 6 | 6/0/0 | 0/5/1 | 0 | yes | N/A | 1 | 0.236012 | 96.3 |
| E6 | B fixed10 | `insufficient_evidence` (`insufficient_evidence`) | yes | none | 5 | 5/0/0 | 0/5/0 | 0 | yes | N/A | 1 | 0.256132 | 102.6 |
| E6 | C agent | `insufficient_evidence` (`insufficient_evidence`) | yes | none | 4 | 4/0/0 | 0/4/0 | 0 | yes | N/A | 2 | 0.303704 | 107.7 |

Errors recorded: none of the 25 listed errors (75 checks) was marked present in any answer. The
one error recorded is an "other error" in E3's C answer: one claim describes a scope more widely
than its cited passage, which is one of the initial five passages that A and B also received.

## The primary set, E2 to E6

| E2 to E6 | A fixed5 | B fixed10 | C agent |
|---|---|---|---|
| Overall verdict yes / partly / no (of 5 cases) | 3/2/0 | 4/1/0 | 5/0/0 |
| Status fits the answer (reviewer), of 5 | 4 | 5 | 5 |
| Status equals the expected status, of 5 | 4 | 4 | 5 |
| Required claims covered yes / partly / no (of 11) | 8/0/3 | 10/1/0 | 11/0/0 |
| Claims rated | 32 | 34 | 35 |
| Claims supported yes / partly / no | 28/4/0 | 32/2/0 | 33/2/0 |
| Claims relevant fully / partly / not | 7/21/4 | 10/21/3 | 13/18/4 |
| Errors recorded (listed or other) | 0 | 0 | 1 |
| Gold evidence items in context (4 cases, of 13) | 7 | 11 | 13 |
| Gold evidence items cited (of 13) | 7 | 11 | 13 |
| Generation calls | 5 | 5 | 10 |
| Input / output tokens | 17,665 / 60,882 | 29,886 / 57,110 | 62,861 / 49,294 |
| Calculated cost, USD | 1.288300 | 1.261744 | 1.237324 |
| Wall-clock seconds, summed | 488.7 | 460.4 | 408.7 |

Paired by case, on the overall verdict:

| Comparison (E2 to E6) | Better | Same | Worse |
|---|---|---|---|
| C agent against B fixed10 | 1 (E2) | 4 (E3, E4, E5, E6) | 0 |
| C agent against A fixed5 | 2 (E2, E3) | 3 (E4, E5, E6) | 0 |
| B fixed10 against A fixed5 | 1 (E3) | 4 (E2, E4, E5, E6) | 0 |

**Where C changed the outcome against B: E2 only.** On E2, B returned `partial` with E2-R2
covered partly (3 of 5 gold items in its context); C's one search added a passage from outside
the fixed top 10 that carries two of E2-R2's gold items, C cited it in the claims Erhan rated as
covering E2-R2, and C's answer was `answered` with both required claims covered. On E3, E4, E5 and
E6, B and C reached the same overall verdicts and covered the same required claims; their claim
counts, support and relevance differ (table above), and C's E3 answer carries the one recorded
error. Against A, C also
improved E3: A lacked one gold item and left E3-R3 uncovered while answering `answered` (status
judged not to fit); B had that item within its top 10, and C's search fetched it.

**Where the simpler baseline sufficed.** On E4, E5 and E6, A's five passages already held every
gold item (E4, E5) or nothing was required (E6), and all three conditions were rated `yes`
overall with the same required-claim coverage. C searched anyway in all three; on E4 every added
passage was inside B's top 10, and on E5 none of the five added passages was cited. On E5 all
three named the required gap; on E6 all three abstained with `insufficient_evidence`, as expected.

## What the agent's searches added

A passage "added" is one C received from its search beyond its initial five; it may still lie
inside B's top 10. "Outside the fixed top 10" means neither A nor B received it. A cited passage
is not yet a covered rubric item: the last column counts the added passages that carry a gold
item, and the text below follows them to Erhan's coverage marks.

| Case | Searches | Passages added | Added and cited | Added from outside the fixed top 10 | Of those, cited | Added passages covering a gold item | Outside the top 10 and covering a gold item |
|---|---|---|---|---|---|---|---|
| E1 | 1 | 5 | 3 | 3 | 2 | 2 | 1 |
| E2 | 1 | 5 | 4 | 2 | 1 | 3 | 1 |
| E3 | 1 | 5 | 5 | 3 | 3 | 1 | 0 |
| E4 | 1 | 5 | 1 | 0 | 0 | 0 | 0 |
| E5 | 1 | 5 | 0 | 1 | 0 | 0 | 0 |
| E6 | 1 | 5 | 3 | 2 | 2 | 0 | 0 |
| E2 to E6 | 5 | 25 | 13 | 8 | 6 | 4 | 1 |

Followed to the rubric: of the 25 passages added on E2 to E6, 13 were cited, 8 came from outside
the fixed top 10, 4 carry a gold item, and 1 does both (on E2, for E2-R2). Of the four
gold-carrying passages, three were also within B's top 10 (two on E2, one on E3), so the only
rubric item that C covered and B did not is E2-R2, through that one passage. Every
gold-carrying added passage was cited in the claims Erhan rated as covering its required claim.
On E2, five of C's claims cite the added passage from outside the fixed top 10 (2 rated fully
relevant, 1 partly, 2 not), so two of C's three claims rated not relevant rest on it: the same
search added both the missing support and peripheral material.

The saved traces establish when C searched (after its first call in all six cells), how many
passages each search returned and from which ranks, which were already supplied, which C cited,
and which carry a gold item. They do not establish why C searched or stopped (only the model's
own statement of what it was seeking is recorded, and that stays local), whether a search was
needed, or how the same cell would behave on a repeat run.

## E1, reported apart

E1 reuses the passage that is D1's evidence, and its drafter knew D1's retrieval ranks, so it is
not part of the primary set. Here C was the only condition rated `yes` overall and the only one
to cover both required claims. A abstained (`insufficient_evidence`, status judged to fit) with
neither gold item in context. B covered E1-R2 from a passage in its ranks 6 to 10 but answered `answered` without E1-R1,
and Erhan judged that status not to fit. C's search added the passage carrying E1-R1 from outside
the fixed top 10 and the one within B's top 10 carrying E1-R2, and cited both in the covering
claims. C
cost USD 0.344516 against B's 0.218560 here.

## Costs: what the additional search cost

| Calculated cost, USD | A fixed5 | B fixed10 | C agent |
|---|---|---|---|
| E2 to E6 | 1.288300 | 1.261744 | 1.237324 |
| E1 | 0.218752 | 0.218560 | 0.344516 |
| All six | 1.507052 | 1.480304 | 1.581840 |

Per case, C minus B was +0.091152 (E2), -0.136232 (E3), -0.053172 (E4), +0.026260 (E5),
+0.047572 (E6) and +0.125956 (E1). What the search adds by construction is one more generation
call per case and a larger input: on E2 to E6, C sent 62,861 input tokens against B's 29,886
(2.1 times; the difference is USD 0.131900 at 4 USD per million). C's first calls, which ended in
the search request, cost USD 0.220652 together on E2 to E6. Output tokens, thinking included,
dominate every cell's cost and differ widely between cells (A alone ranged from USD 0.087524 to
0.404848 per case), and C produced fewer of them on E2 to E6 (49,294 against 57,110). C minus B
was USD -0.024420 on E2 to E6 and +0.101536 over all six cases. With one run per cell there is no
measure of how much a cell's cost varies between runs, so the data establish no repeatable cost
advantage or penalty in USD; they show the extra call and the doubled input, and a total cost of
the same order for all three conditions. Summed wall-clock time on E2 to E6 was 408.7 s for C, 460.4 s for B and 488.7 s for A,
with the same caveat.

## Limits that affect interpretation

- **One run per case and condition**, one model at effort `max` with adaptive thinking: no
  repeat and no variance estimate. A difference on one case is an observation, not a finding.
- **One reviewer**, who also decided the cases; no second rater and no agreement measure.
- **Partial blinding**: answers were shown verbatim, so their wording or the number of passages
  they cite can hint at the condition; the packet asked the reviewer not to use such hints. A
  session log of 2026-11-21 may link one E1 answer to its condition; E1 is reported apart anyway.
- **E1's overlap with D1** (above).
- **A small January corpus**: on the January-only cases E4 and E5, B receives 10 of the January
  commentary's 11 passages, so B is close to the whole edition there and B and C can hardly
  differ in what they may see.
- **E2's shared edition filter** excludes January for every condition, so E2 does not test
  edition selection; its gain came from a passage of the right edition outside the top 10.
- **Coverage matching** is by edition, page and quote; section anchors and occurrences are the
  reviewer's. Costs are calculated, not invoiced.

## Recommendation

1. **Keep fixed top 10 as the default single-call path and as the baseline.** It matched the
   agent's verdict on four of the five primary cases at one call, and B against A shows that a
   larger fixed context alone already helps (E3). Fixed top 5 is not enough on its own: it missed
   required claims on E2 and E3 (and on E1).
2. **Use the bounded agent where the needed evidence may lie beyond the fixed top 10**, the
   seeking-missing-evidence use case (UC2) it was built for. That is the only situation in which it
   changed an outcome here (E2, and E1 apart); in this run its total cost was of the same order as
   B's, and on the other four primary cases it reached the same overall verdict and required-claim
   coverage as B.
3. **Do not add an automatic escalation from B to C keyed on B's status** without testing it: on
   E1, B answered `answered` while missing a required claim, so a status trigger would not have
   caught it.
4. **Before treating the agent as the default:** repeat each cell at least three times, add cases
   whose evidence lies beyond rank 10, and test C starting from the top 10 instead of the top 5. C
   searched in every cell, including the three where its first five already held all the required
   evidence, so whether it can tell when not to search is open.

## Files

- Committed, in `tools/commentary_rag/results/` (outside this site, so named by path; the pilot
  README links them): the run record `2026-11-21-phase3-E-comparison.json` and the active ledger
  `phase3-ledger.jsonl` (SHA-256 `ca20af168ba1...`), both as the run wrote them; the review lock
  `2026-11-22-phase3-E-review-lock.json`; the review summary
  `2026-11-22-phase3-E-review-summary.json` (the review, retrieval, search and cost figures on this
  page, by case and condition; run times and tokens are in the run record).
- Local and git-ignored: the run's requests, responses and full result, the blinded packet,
  Erhan's completed packet, the blank and filled ratings, the neutral ID listing, the blinding
  key, the unblinded table with neutral IDs, the trace findings sealed before the review, and the
  packaging and unblinding scripts. No question, answer, passage, search query, reviewer note or
  neutral-ID mapping is in a committed file.
