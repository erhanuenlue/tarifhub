# Phase 4, variant 1: the coverage decision, frozen and built offline (2026-11-25)

**What this page records.** The first increment of Phase 4, variant 1 (extending the agentic
behaviour): the evaluation of an explicit coverage decision for the evidence-seeking agent, frozen
before any code, then built and tested offline and dry-run with a simulated provider. No live run,
no provider call, no GPU job and no spending (USD 0); the books stay at USD 7.060552 of the USD 100
limit for Phases 2 and 3. Decision record: [ADR-027](../adr/027-coverage-decision.md) (proposed).

## 1. Inherited platform, Phase 3 baseline, Phase 4 capability

- **Inherited** (the earlier course's baseline `530f850`, 3 July 2026): AL import, frozen hashed
  records, REST and FHIR, pgvector search with multilingual-e5, read-only MCP tools, the console and
  TarifIQ. No commentary retrieval and no agent.
- **Measured Phase 3 baseline** (this course; [evidence](2026-11-21-phase3-E-comparison.md),
  [ADR-026](../adr/026-commentary-evidence-search.md)): fixed top 5, fixed top 10 and the bounded
  evidence-seeking agent on six frozen cases, one run per cell, rated blinded by one reviewer. On
  the primary set of five cases the overall verdict was `yes` for the agent on 5, for fixed top 10
  on 4 and for fixed top 5 on 3, at a calculated cost of the same order. The agent searched in every
  cell, also where its first five passages already held all required evidence, so whether it can
  tell when not to search stayed open.
- **New in Phase 4** (proposed, not yet evaluated): condition D, the same agent with an explicit
  coverage decision. In the same call as its action the model records the parts the question asks
  for (at most four) and whether the passages it has received state each one; it answers when every
  part is covered and otherwise searches for exactly one missing part, which it names. Everything
  else is the Phase 3 agent's.

## 2. The frozen evaluation

On 2026-11-25 Erhan selected the proposed set of 19 cases (nine drafted cases and ten alternates of
a fresh case author) and approved the study design; this was a selection of the proposed set as a
whole, not a case-by-case review by him. The cases were drafted by a fresh-context case author (a
subagent on `claude-opus-5-5` at effort `max`) whose only inputs were its brief and the 40 passages
of the two 2026 commentaries; it checked its own quotes and gap probes, and the lead checked the
drafts (structure, equivalent passages, gaps, overlap with earlier cases, the author's transcript)
and verified the selected 19 mechanically at the freeze (311 checks, all passed). No person reviewed
the cases or their gold before the freeze.

Frozen with hashes, before any ranking of the selected cases and before D was implemented
([freeze record](https://github.com/erhanuenlue/tarifhub/blob/main/tools/commentary_rag/results/2026-11-25-phase4-freeze.json)):

- the runner input, the private gold (expected statuses, required parts, equivalent evidence sets,
  gap definitions) and the decision record, all kept local;
- the [condition contract](https://github.com/erhanuenlue/tarifhub/blob/main/tools/commentary_rag/phase4/conditions.md):
  B fixed top 10 and C the Phase 3 agent unchanged; D's instruction, tool, answer format, checks and
  records verbatim, with synthetic examples;
- the [rubric and thresholds](https://github.com/erhanuenlue/tarifhub/blob/main/tools/commentary_rag/phase4/rubric-and-thresholds.md):
  19 pairs; search opportunities counted from the evidence and the search capacity before each
  decision, the same way for C and D and never from D's own coverage record; justified gap checks
  kept apart; partly supported claims and incomplete repetitions defined in advance; thresholds T1
  to T5 (D against C) and R1, R2 (D against fixed top 10) with an outcome for every combination.

Gold-derived results are published only as aggregates; case-level results stay local. Because the
Phase 3 records were published after the Phase 3 runs, Phase 4 does not treat the Phase 3
evaluation cases as blind held-out tests.

## 3. What was built (offline)

| Part | What | Tests |
|---|---|---|
| Condition D (`evidence_agent.py`) | coverage instruction, a search tool that also takes the coverage and the number of the missing part, the coverage beside the unchanged answer object; a malformed coverage, a passage not received or a search for no missing part refused as a tool error that uses the round; answers accepted exactly as C's; the tool offered by capacity alone | 24 (`test_coverage_condition.py`) |
| Phase 4 design (`run_comparison.py`) | `--design phase4` runs B, C and D per case; its public record names no passage; the default Phase 3 design unchanged | 5 more, 48 in all (`test_run_comparison.py`) |
| Scorer (`phase4_scoring.py`) | the local records of one repetition merged and checked (completeness, question, ranking and initial passages), decision points by capacity before each call, the frozen search measures, D's coverage diagnostics apart from them, the thresholds and both outcome tables | 142 (`test_phase4_scoring.py`) |

The pilot's offline suite: 655 tests in fifteen files, all passing; lint clean. The tests check D's
instruction, tool, answer format and refusal texts against the SHA-256 values frozen in the contract,
and B's and C's requests against hashes taken on the code before D existed; the default Phase 3
`plan` gives the same output on the recorded books as before. The books, the limit, the prices and
the admission rule are unchanged.

## 4. Dry run with a simulated provider

The ordinary entry point, `run_comparison.py` with `--design phase4`, ran on the frozen runner
input with the real corpus and the cached e5 model, a scripted provider in place of the API (no key,
no call) and a scratch copy of the books:

- `plan` for all 19 cases: 57 cells; worst case USD 196.6272 against a headroom of USD 92.939448,
  so the matrix does not fit; `run` refused it before the model loaded and sent nothing.
- Three batches of 8, 8 and 3 cases in the frozen order were each admitted and ran: 57 cells, 88
  simulated calls, each reserved and settled from its simulated usage in the scratch books. B
  answered once; C searched once and answered; D, by a hash of its question, answered at once,
  searched validly, or sent a search with a passage it had not received, which code refused as
  designed.
- The real books and `results/` stayed byte-identical (SHA-256 before and after); the batches'
  public records held no passage ID; the scorer, merging the three batches, found all 19 cases complete and no trace anomaly.

The simulated answers and costs measure nothing about the model. The scored measures of the dry run
depend on the private gold and the rankings of the frozen cases and are kept local.

## 5. What this does not show, and what is open

- How a real model fills the coverage, whether it searches less where nothing is missing, and the
  answers' quality: no live run exists.
- The provider contract for D's schemas (an integer field in a strict tool, the coverage beside the
  answer object) is unverified live.
- The current books cannot admit the frozen 19-case design in one invocation, and repetitions need
  their own identity: a live repetition needs Erhan's decision on books, cap and admission.
- Open finding for Erhan: as frozen, a refused search at a decision point where nothing was missing
  counts in T3's denominator but not as an unnecessary search; counting it as unnecessary would
  mirror T4, where a refused search at a search-needed point already counts as missed.
- Delivery items (presentation, demo, FFHS-Git copy with the README declaration and an executed
  notebook) are unchanged: [project frame](../agents/cas-ai-engineering.md).
