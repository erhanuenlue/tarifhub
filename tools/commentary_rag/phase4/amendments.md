# Phase 4 amendments after the freeze

The rubric ([`rubric-and-thresholds.md`](rubric-and-thresholds.md)) and the condition contract
([`conditions.md`](conditions.md)) stay as frozen on 2026-11-25; their hashes in
`../results/2026-11-25-phase4-freeze.json` still hold. This file records, dated and in order, what
Erhan decided after the freeze. Each entry was written before any live result: when it was
recorded, no Phase 4 cell had been sent to the provider. The published freeze record stays as it
is, its own `amendments` list empty; the amendments are recorded here instead.

## A1: unnecessary search attempts, reported beside T3 (2026-11-26)

**Decision.** Erhan, 2026-11-26, before any live result: report alongside T3 the number and the rate
of unnecessary search attempts. Recorded by the lead the same day.

**What was known when A1 was chosen.** The case rankings and simulated traces were known when A1 was
chosen. The lead had ranked all 19 frozen cases and run the simulated dry runs of 2026-11-25 (a
scripted provider, no model output) before the open rule question went to Erhan, and the lead's
gold-related findings from them existed; they stay private. No model answer, search decision or cost
of a Phase 4 cell existed then.

**The rule.**

- At a no-search-needed decision point, an executed search (action *search run*) or a refused model
  search request (action *search refused*: any `refused_*` outcome) is one **unnecessary search
  attempt**. A decision point has exactly one action, so it counts at most once.
- Reported for C and D alike, computed by the same code: the executed and the refused attempts
  separately, their total, and the attempt rate over the original T3 denominator (no-search-needed
  decision points with an action), as k of n, with a percentage only when n is at least 5.
- A1 is a reported measure, not a threshold: it enters neither T3, T4 nor any outcome.

**Unchanged.**

- The frozen rubric and its thresholds.
- T3 as frozen (an unnecessary search is an executed search), its result, reported first and as
  computed, and its denominator.
- Gap checks: a search or a refused request at a gap-check decision point is reported as before and
  is no unnecessary search attempt.
- Decision points without action: listed and left out of every denominator.
- T4 and missed useful searches.
- All 19 cases and the outcome tables.

**Interpretations kept** (documented with the freeze and the scorer; restated here unchanged):

1. A cell ran once a generation call was sent; a cell refused or stopped before any call is not
   run, and one that ran and failed counts as run. A booking alone does not establish that a call
   was sent: a reservation released as never sent, or one whose sending is unknown, does not make a
   cell run.
2. R1 needs at least three qualifying B failures (beyond-top-10 cases in which B has no full case
   success); with fewer it is not assessable.
3. Partly supported claims follow the frozen distinction: a required part stated only by a partly
   supported claim is covered at most partly and prevents full case success; any other claim rated
   partly is reported beside T2, not counted against it.
4. An incomplete repetition yields no threshold verdict: its results are reported as exploratory,
   with the number of complete cases.

**Publication.** The detailed strata and every gold-related finding stay private; gold-derived
results are published only as aggregates, as frozen.

## O1: the books of the first live repetition (2026-11-26)

**Decision.** Erhan, 2026-11-26: one exploratory repetition, repetition 1, runnable only in its own
books under a separate cap. This amends the operational part of `conditions.md` (the last item of
section 1 and section 6). It changes nothing that a condition sends: B's and C's requests stay
byte-identical, and D's are as frozen.

- **Books.** A Phase 4 ledger, `results/phase4-ledger.jsonl`, beside the Phase 2 and Phase 3 books
  and under the same folder lock, with a limit of USD 40 pinned in code and in the ledger's first
  line. Phase 2 and Phase 3 spending does not count against it, and Phase 4 spending does not count
  against their USD 100. The Phase 2 and Phase 3 ledgers stay as they are.
- **Identity.** Every Phase 4 cell is booked under (repetition, case, condition), with the call IDs
  `<case>-<condition>-r<repetition>-call<n>`. The code admits repetition 1 only; condition D is
  booked in these books only.
- **Admission.** One invocation of the comparison runner (`run_comparison.py run --design phase4`)
  takes the frozen runner input, checked by its SHA-256 as frozen, and runs its cases in the frozen
  order, B, C and D per case. Before a fresh case starts, the full worst case of its three cells
  (every call at the input cap: USD 10.3488 with the pinned configuration and prices) must fit,
  under the lock, beside everything committed: settled calls at their cost, calls kept at their
  reservation and reservations whose settlement is missing. A case that does not fit is not
  started: the run stops before anything of it is sent. A cell already in the books is never sent
  again.
- **Not authorized by this entry:** a live run, which needs Erhan's separate decision.
