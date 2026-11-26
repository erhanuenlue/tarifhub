# Phase 4, variant 1: amendment A1 and the books of a first repetition, offline (2026-11-26)

**What this page records.** The step after the frozen, offline coverage decision
([previous page](2026-11-25-phase4-coverage-decision-offline.md)): an analysis amendment recorded
before any live result, Phase 4's own books for one exploratory repetition, the remaining review
points of that step, and a simulated rehearsal through the ordinary entry point. No live run, no
provider call, no GPU job and no spending (USD 0); the Phase 2 and 3 books stay at USD 7.060552 of
their USD 100, and no Phase 4 ledger exists yet. Decision records: amendments A1 and O1
([`phase4/amendments.md`](https://github.com/erhanuenlue/tarifhub/blob/main/tools/commentary_rag/phase4/amendments.md)),
[ADR-028](../adr/028-phase4-books.md) (accepted) and [ADR-027](../adr/027-coverage-decision.md)
(proposed).

## 1. Inherited platform and what this step adds

- **Inherited** (the earlier course's baseline `530f850`, 3 July 2026): no commentary retrieval
  and no agent. This course added cited answers over the BAG commentaries (ADR-025), the bounded
  evidence-seeking agent with its per-call spending protection (ADR-026, measured in Phase 3) and,
  on 2026-11-25, condition D with its frozen evaluation (ADR-027).
- **New in this step:** what a first live repetition of the frozen evaluation needs before it can
  run: a recorded analysis amendment, books and admission of its own, and the remaining review
  points of the previous step addressed where they matter for a live run. Not a result: nothing was
  measured on the model.

## 2. Decided before any live result

- **A1, unnecessary search attempts beside T3** (Erhan, 2026-11-26). At a no-search-needed decision
  point an executed search or a refused model search request counts once as an unnecessary search
  attempt, for C and D alike, over T3's original denominator, with executed and refused shown apart.
  A1 is reported, not a threshold: the frozen rubric and thresholds, T3 and its result, gap checks,
  points without action and T4 are unchanged, and so are the four documented interpretations (a
  cell ran once a generation call was sent, and a booking alone does not show that a call was sent;
  R1 needs at least three qualifying B failures; the frozen rule for partly supported claims; no
  threshold verdict on an incomplete repetition). The case rankings and simulated traces were known
  when A1 was chosen.
- **O1, Phase 4's books** (Erhan, 2026-11-26; [ADR-028](../adr/028-phase4-books.md)): one
  exploratory repetition under a separate cap of USD 40, the repetition part of every cell's
  identity, and a case admitted only when the worst case of its three cells (USD 10.3488) still
  fits.
- **The remaining review points of the previous step** were accepted by Erhan as tracked limitations
  of that offline milestone when it merged ([#72](https://github.com/erhanuenlue/tarifhub/pull/72),
  squash `140ca86`); this step addresses them for a live run (section 3).

## 3. What changed, offline

| Part | Change | Tests |
|---|---|---|
| Books (`evidence_agent.py`) | Phase 4's ledger beside the others, its own limit pinned in code and in its first line, the repetition in every reservation, settlement and record, repetition 1 and B, C, D only; D refused in the Phase 2 and 3 books, whose reader also refuses a D cell or a repetition as damage | 19 new in `test_coverage_condition.py` (42) |
| Runner (`run_comparison.py`) | `--design phase4` books in those books under repetition 1, takes only the frozen runner input (SHA-256 pinned), admits case by case under the lock, shows how the reserved calls stand in its plan, and refuses a symbolic link as its local output folder | 11 new in `test_run_comparison.py` (59) |
| Scorer (`phase4_scoring.py`) | A1 beside T3 (`a1`, `search_thresholds`); a missing or malformed time budget refused; a search refused for want of rounds before both rounds were used refused; one repetition per scoring; completeness derived by the scorer; the frozen gold file only; a symbolic link as `local/` refused | 28 new in `test_phase4_scoring.py` (171) |

The previous step's open review points and what happened to each:

| Point (as the reviewer reported it) | Now |
|---|---|
| "validate missing or malformed `budget_s`" | every record needs a finite time budget above 0 |
| "reject premature `refused_rounds`" | refused unless both rounds were used before it |
| "disallow symlinked `local/` output directories" | refused by the scorer and, for its local records, by the runner |
| "Handle unencodable coverage text before replaying a tool turn" | kept as the limit C and D share (no guard for D alone, which would make the conditions differ); its accounting on failure is tested (section 6) |

## 4. Checks

- **Pilot suite:** 713 tests in fifteen files pass offline (655 before), with pytest-socket's block on.
  Run against the code of `140ca86`, the four changed test files fail or error in 86 of their 428 tests,
  so the new tests depend on the new behaviour; they were written after the code, not before.
- **Unchanged:** B's and C's requests equal the hashes taken before D existed, also in the Phase 4
  books; the default Phase 3 `plan` output on the recorded books equals that of `140ca86`; the
  recorded ledgers and the freeze record are byte-identical.
- **The triplet ceiling** is derived in a test from the pinned configuration and `pricing.json`: USD
  1.4784 per call at the input cap, seven calls, USD 10.3488.
- **The Phase 4 plan on the recorded books** (offline, nothing written): limit USD 40, nothing
  committed, the next case `P4-F01` at USD 10.3488 fits, 19 cases to run.

## 5. Simulated rehearsal through the ordinary entry point

`run_comparison.main` with `--design phase4` and the frozen runner input, a scripted provider
(no key, no network, Python sockets blocked), the real corpus and cached e5 model, and disposable
books holding copies of the Phase 2 and 3 ledgers. Scripted usage only: the amounts are calculated
from it and measure nothing about the model; the scored measures depend on the private gold and
stay local.

| Scenario | Result |
|---|---|
| One repetition, one invocation | 57 cells, 77 calls, each sent and booked once; USD 1.848 committed (scripted); the scorer finds all 19 cases complete |
| A second invocation started while the first call was on the wire | refused by the lock (exit 3): nothing counted, sent, booked or written |
| Interrupted while `P4-F05`'s C had its first call on the wire, then run again under a new tag | the rerun skips every cell in the books and finishes in the frozen order (76 calls in all); the interrupted call stays open at its reservation (USD 0.71852) and is never sent again; the scorer finds 18 of 19 cases complete, so the repetition gives no verdict |
| Expensive scripted usage (30,000 output tokens per call) | the run stops before `P4-F14` with USD 32.118 committed, nothing of `P4-F14` counted or sent; a rerun is refused before the model loads |
| Another case kept at USD 29.6512 (USD 40 minus one triplet) | `P4-F01` is admitted and runs; the run stops before `P4-F02` |
| One micro-dollar more (USD 29.651201) | refused before the model loads: no count, no call, no record |

In every scenario the copies of the Phase 2 and 3 ledgers stayed byte-identical, every call ID named
repetition 1, the committed amount stayed within USD 40, and the repository's `results/` stayed
byte-identical with no Phase 4 ledger.

## 6. Residual limits and whether they block a live run

- **A replay failure shared by C and D** (a lone surrogate the model escaped in a tool input): the
  cell's next request cannot be written as UTF-8, and the run ends with an unexpected error after the
  cell's sent calls are settled, with nothing more reserved. The cell leaves no record, so the
  scorer reads it as not run (the books show its settled calls), and a rerun skips it: its case
  stays incomplete and the repetition gives no threshold verdict. Tested for C and D alike and
  through the runner. Does not block a live run: the input is unlikely, the accounting stays safe,
  and C and D stay comparable.
- **Unresolved bookings:** a call whose sending is unknown stays open at its reservation, a call
  released before sending stays released, and neither is sent again; either leaves its case
  incomplete. Does not block.
- **Headroom near the end:** with the cap at USD 40 a fresh case starts only while at most USD
  29.6512 is committed. Under the high scenario of USD 31.24 the 19th case starts with USD 0.0554 to
  spare, so one call kept at its reservation could stop the run before the last case. Does not block;
  the cap is Erhan's decision.
- **Carried from ADR-027:** D's schemas have never been sent to the provider, so their live contract
  is unverified; the cases are AI-drafted and one person selected them and rates the answers.

## 7. Not done

No live repetition (it needs Erhan's separate decision), no blinded review, no Jev replay and no
second or third repetition (each needs another decision on cap and code). The delivery items are
unchanged: [project frame](../agents/cas-ai-engineering.md).
