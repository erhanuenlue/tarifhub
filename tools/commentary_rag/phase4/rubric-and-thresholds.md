# Phase 4 rubric, measures, analysis rules and decision thresholds (frozen)

Frozen on 2026-11-25 with the case set and the condition contract ([`conditions.md`](conditions.md)),
before any ranking of the selected cases and before condition D was implemented; hashes in
`../results/2026-11-25-phase4-freeze.json`. Nothing here changes after any result exists.

**Basis.** On 2026-11-25 Erhan selected the proposed set of 19 cases and approved the study design
(this rubric as proposed, with its thresholds). In the same request he set how R1 and R2 are stated,
that 19 pairs apply throughout, that search opportunities are counted from the evidence and search
capacity available before each decision, that justified gap checks stay separate, and that the
treatment of partly supported claims and of incomplete repetitions is fixed in advance. The lead
wrote those rules into this text before the freeze; the wording of the partly-supported rule and of
the incomplete-repetition rule is the lead's specification.

## Units and pairing

- **Unit:** the question (case). 19 cases, `P4-F01` to `P4-F19`; every comparison has 19 pairs.
- **Conditions** ([`conditions.md`](conditions.md)): B fixed top 10 (`fixed10`), C the Phase 3 agent
  (`agent`), D the agent with the coverage decision (`coverage`). One ranking per case; C and D
  start from its top 5, B receives its top 10.
- **Pairing:** by question. D against C is the primary comparison, D against B the reference. For each
  pair and repetition: better, same or worse on full case success.
- **Repetitions:** Erhan decides before each live repetition. Deterministic measures are computed for
  every complete repetition and reported as median (minimum to maximum); human-rated measures come
  from repetition 1, unless Erhan decides before any rating to rate every repetition.

## Parts and equivalent evidence (frozen with the cases)

- Each case has 1 to 4 **required parts**. A **fact part** has a frozen set of equivalent supporting
  passages within the case's editions: any one of them suffices. A **gap part** has no supporting
  passage in those editions (justified in the case); a good answer names it as missing.
- The sets are frozen. A passage the reviewer later finds stating a fact part is recorded and reported
  as unlisted support; the frozen set and the deterministic measures do not change.

## Search opportunities and search measures (C and D; deterministic; not applicable to B)

- **Decision point:** a generation call of a C or D cell before which the cell still has search
  capacity: a later generation call, a search round left (2 per cell, refused requests included) and
  fewer than 10 passages supplied. It is determined from the trace by capacity alone, the same way for
  C and D, never from whether the tool was offered and never from D's coverage record. The code offers
  the tool at exactly these calls; a call where the two disagree is reported as a trace anomaly.
- **Evidence before the decision:** the passages supplied immediately before that call (the initial
  five and everything earlier searches returned), never what a later search returned.
- At a decision point a fact part is **covered** when a passage of its frozen set is among those
  passages; otherwise it is **missing but retrievable** (every frozen set lies in the case's editions,
  and a decision point has passage budget left).
- **Kinds of decision point** (each is exactly one): **search-needed** (some fact part missing but
  retrievable), **gap-check** (every fact part covered and at least one gap part; a case of gap parts
  only is always here), **no-search-needed** (every fact part covered and no gap part).
- **Action at a decision point** (exactly one): **search run** (the request passed every check and was
  executed: outcome `passages`, `no_new_passages` or `tool_error`), **search refused** (the code
  refused it, any `refused_*` outcome; the round is used), **answer** (the call ended in an answer
  turn, accepted or not), or **no action** (the call ended otherwise: provider error, cut-off or
  declined generation, protocol error, deadline).
- **Warranted search:** a search run at a search-needed decision point. **Unnecessary search:** a
  search run at a no-search-needed decision point. **Gap-check search:** a search run at a gap-check
  decision point, reported separately and counted neither as unnecessary nor as useful.
  **Missed useful search:** a search-needed decision point whose action is an answer or a refused
  search.
- Refused searches and decision points without action are reported separately, per kind; decision
  points without action are listed and left out of the rate denominators below.
- **Rates:** unnecessary-search rate = unnecessary searches over no-search-needed decision points with
  an action; missed-search rate = missed useful searches over search-needed decision points with an
  action.
- **D's own coverage judgement does not enter these measures.** An answer that D's coverage record
  calls complete still counts as a missed useful search when a fact part was missing but retrievable,
  and D cannot lower the count by withholding the tool, which the code offers by capacity alone.
- **Secondary, reported only:** search yield (warranted searches after which a previously missing
  fact part was covered), searches, refused searches, tool errors and calls per cell, and for D the
  agreement of its coverage record with the frozen sets and its `missing_not_reported` flag
  (exploratory: its own split into parts can differ from the frozen parts).

## Answer measures (all conditions; blinded human review)

- **Fact part:** covered yes, partly or no. Yes when a claim states it and cites a passage that
  supports it; partly when the claim states only part of it or its cited passages support it only in
  part.
- **Gap part:** handled correctly when the answer names it as missing and asserts nothing about it.
- **Claims:** support yes, partly or no against the cited passages. An **unsupported claim** is a claim
  rated no, or a factual claim without any citation.
- **Partly supported claims:** a fact part counts only when it is covered yes, so a required part
  stated only by a partly supported claim is covered at most partly and prevents full case success.
  Any other claim rated partly does not prevent full case success and does not count as unsupported
  for T2. Partly supported claims are reported per condition as k of n claims beside T2.
- **Status fit:** the reviewer's judgement of the status against the answer's own claims and cited
  passages; the expected status of the case is reported beside it.
- **Full case success:** every fact part covered yes, every gap part handled correctly, no unsupported
  claim, and the status judged to fit.
- **Correctly handled gaps (reported separately):** per condition, gap parts handled correctly over gap
  parts, and for cases of gap parts only, whether the answer abstained (`insufficient_evidence`).
- A cell that ran but ended without an accepted answer is not a success; its search decisions, if any,
  are still scored. Such cells are listed.

## Strata (computed by code after the freeze, never before)

From the shared ranking (top 10) and the frozen sets: **S1** every fact part has support within ranks
1 to 5; **S2** every fact part has support within ranks 1 to 10 and some only at ranks 6 to 10;
**S3** some fact part has no support within ranks 1 to 10; **G** every part is a gap. A case with fact
and gap parts belongs to the stratum of its fact parts and is flagged. The **top-10 group** is S1 and
S2; the **beyond-top-10 group** is S3; G belongs to neither and is reported under gaps. No case is
redrafted, dropped, moved between strata or pooled after the freeze.

## Complete and incomplete repetitions

- A repetition is **complete** when every one of the 19 cases has a cell for B, C and D in it that ran,
  whether or not the cell gave an accepted answer. A cell that ran and failed counts as run (a
  non-success). A cell **not run** (refused at admission, held back after the runner stopped, refused by
  the books, or never started) leaves its case incomplete in that repetition.
- An incomplete repetition may be completed only by running its missing cells in the frozen case order
  and the order B, C, D, with the same frozen inputs and code, before any answer of that repetition is
  reviewed or unblinded. A cell that ran is never run again or replaced.
- A repetition that stays incomplete yields **no verdict**: its results are reported as exploratory with
  the number of complete cases, and none of T1 to T5, R1 or R2 is assessed on it.
- T1, T2, T5, R1 and R2 are assessed on repetition 1 only. If repetition 1 cannot be completed, the
  primary and the reference result are **not established**; no later repetition replaces it for the
  human ratings.
- T3 and T4: with one repetition they are decided on it; with three, each must hold in at least two
  complete repetitions, and a repetition that stays incomplete does not count towards the two. Values
  are reported per repetition.

## Small and empty groups

- Every table cell shows counts as k of n; percentages only when n is at least 5.
- n = 0: reported as "no cases"; a threshold on it is **not assessable**, never met.
- n from 1 to 4: counts only, flagged as a small group; rate thresholds on it are not assessed; count
  thresholds are decided as written.
- Strata and groups are never pooled or merged after the results to rescue a threshold.

## Decision thresholds

**Primary: D against C** (19 pairs; human-rated measures from repetition 1).

| ID | Property | Rule | Assessable when |
|---|---|---|---|
| T1 | Quality kept | D's full case successes are at least C's minus 1 | repetition 1 complete |
| T2 | No added unsupported claims | D's unsupported claims are at most C's | repetition 1 complete |
| T3 | Fewer unnecessary searches | D's unnecessary searches are at most a third of D's no-search-needed decision points with an action, and at least 2 fewer than C's | D has at least 5 no-search-needed decision points with an action |
| T4 | No more missed useful searches | D's missed useful searches are at most C's plus 1, and at most a fifth of D's search-needed decision points with an action | D has at least 5 search-needed decision points with an action |
| T5 | Gaps kept | D's correctly handled gap parts are at least C's | at least 3 gap parts in the complete repetition |

**Reference: D against B** (repetition 1, human-rated; complete B and D cells).

| ID | Property | Rule | Assessable when |
|---|---|---|---|
| R1 | Beyond the top 10 | Let n be the beyond-top-10 cases (S3) in which B has no full case success, and k those of them in which D has full case success: R1 is met when 2k is at least n (D succeeds on at least half) | n is at least 3 |
| R2 | Within the top 10 | In the top-10 group (S1 and S2), D's full case successes are at least B's minus 1 | the group is not empty |

**Primary outcome** (every combination has exactly one; with repetition 1 incomplete there is no
verdict and the result is "not established"):

| Outcome | When |
|---|---|
| D supported: propose the coverage decision for the agent's UC2 use (ADR-027, proposed) | T1, T2, T3 and T4 met, and T5 met or not assessable |
| D not adopted | T1, T2, T4 or T5 failed (whatever T3 shows) |
| No benefit shown | T3 failed or not assessable, while T1, T2 and T4 are met and T5 is met or not assessable |
| Not established, reported as exploratory | T4 not assessable and no rule above applies |

**Reference outcome** (informs the single-call default only; it never changes the primary outcome):

| Outcome | When |
|---|---|
| No reference recommendation | R2 not assessable (empty top-10 group), whatever R1 shows |
| Fixed top 10 stays the default for every question | R2 failed, whatever R1 shows |
| D recommended for UC2 questions whose evidence may lie beyond the top 10; fixed top 10 stays the default otherwise | R2 met and R1 met |
| Fixed top 10 stays the default for every question; no gain of D over B shown | R2 met and R1 failed |
| Fixed top 10 stays the default; the beyond-top-10 benefit is not established | R2 met and R1 not assessable |

With 19 pairs these are decision thresholds, not significance tests. The exact two-sided sign test on
discordant pairs is reported for information only.

## Reported beside the thresholds

Cost and wall-clock time per cell (median, minimum to maximum over complete repetitions), calls and
searches per cell, refused searches, validator refusals, and the stability of each case's search
decision across repetitions (same in all, or not).

## Publication

Gold-derived results are published only as aggregates. Case-level results (gold coverage per case,
passage IDs per case, stratum membership per case) stay local.

## Limits carried into the report

- Because the Phase 3 records were published after the Phase 3 runs, Phase 4 does not treat the
  Phase 3 evaluation cases as blind held-out tests.
- The cases were drafted by an AI case author and checked by the lead, also an AI; Erhan selected the
  proposed set as a whole and approved the study design, and he also rates the answers. Answers are
  shown verbatim, so blinding is partial.
- A 40-passage corpus (January 11, July 29); on January-only cases B sees 10 of the 11 January passages.
- One model at one setting (`claude-opus-5-5`, effort `max`, adaptive thinking).
- The ten-passage total is held fixed, so an agent that starts from the top 10 is not tested; whether
  it would do better needs other limits and stays open.
