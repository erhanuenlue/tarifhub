# Phase 4, variant 1: amendment A1 and the books of a first repetition, offline (2026-11-26)

**What this page records.** The step after the frozen, offline coverage decision
([previous page](2026-11-25-phase4-coverage-decision-offline.md)): an analysis amendment recorded
before any live result, Phase 4's own books for one exploratory repetition, the remaining review
points of that step, and a simulated rehearsal through the ordinary entry point; section 8 records
the fixes Erhan approved on 2026-11-27 and section 9 those of 2026-11-28, with their checks. No
live run, no
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
| Books (`evidence_agent.py`) | Phase 4's ledger beside the others, its own limit pinned in code and in its first line, the repetition in every reservation, settlement and record, repetition 1 and B, C, D only; D and every frozen Phase 4 question (the freeze record's 19 hashes) refused in the Phase 2 and 3 books, whose reader also refuses a D cell or a repetition as damage; every Phase 4 admission holds back the case's other cells not yet booked, whoever calls; a frozen case is booked in Phase 4's books only under its frozen ID, question and editions; the books' time budget is pinned with their first reservation (as built that day, the pin was written before the request was saved, so a failed request write left a pin without a reservation: corrected on 2026-11-27, section 8) | 29 new in `test_coverage_condition.py` (52) |
| Runner (`run_comparison.py`) | `--design phase4` books in those books under repetition 1, takes only the frozen runner input (SHA-256 pinned), admits case by case under the lock, shows how the reserved calls stand in its plan, and refuses a symbolic link as its local output folder or as a request or response folder in it; it takes only the frozen corpus, stops after a cell that booked nothing so a rerun keeps the frozen order, refuses a rerun with another time budget, claims its run folder with a claim file before spending (as built that day this refused a later invocation of either design, but not a Phase 3 run already past its output check and loading: corrected on 2026-11-27, section 8) and reports the Phase 4 cap; the default design refuses a frozen Phase 4 case, by its ID or its question, before anything loads | 21 new in `test_run_comparison.py` (69) |
| Scorer (`phase4_scoring.py`) | A1 beside T3 (`a1`, `search_thresholds`); a missing or malformed time budget refused; a search refused for want of rounds before both rounds were used refused; one repetition per scoring; completeness derived by the scorer and only for the frozen cohort (the freeze record's case IDs, question hashes and editions); the frozen gold file only, read once; a symbolic link as `local/` refused | 29 new in `test_phase4_scoring.py` (172) |

The previous step's open review points and what happened to each:

| Point (as the reviewer reported it) | Now |
|---|---|
| "validate missing or malformed `budget_s`" | every record needs a finite time budget above 0 |
| "reject premature `refused_rounds`" | refused unless both rounds were used before it |
| "disallow symlinked `local/` output directories" | refused by the scorer and, for its local records, by the runner |
| "Handle unencodable coverage text before replaying a tool turn" | kept as the limit C and D share (no guard for D alone, which would make the conditions differ); its accounting on failure is tested (section 6) |

## 4. Checks

- **Pilot suite:** 734 tests in fifteen files pass offline (655 before), with pytest-socket's block on.
  Run against the code of `140ca86`, the four changed test files fail or error in 107 of their 449 tests,
  so the new tests depend on the new behaviour; they were written after the code, not before.
- **Unchanged:** B's and C's requests equal the hashes taken before D existed, also in the Phase 4
  books; a scripted B cell and C cell in the Phase 2 and 3 books give the same ledger lines (times
  aside), records and requests at `140ca86` and now; the default Phase 3 `plan` output on the
  recorded books equals that of `140ca86`; the recorded ledgers and the freeze record are
  byte-identical.
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
  and C and D stay comparable. Since 2026-11-27 the cell is recorded from the books as run and
  failed, so it no longer leaves its case incomplete (section 8).
- **Unresolved bookings:** a call whose sending is unknown stays open at its reservation, a call
  released before sending stays released, and neither is sent again; either leaves its case
  incomplete. Does not block.
- **Headroom near the end:** with the cap at USD 40 a fresh case starts only while at most USD
  29.6512 is committed. Under the high scenario of USD 31.24 (USD 1.644404 per case) the 19th case
  starts with about USD 0.05 to spare, so one call kept at its reservation could stop the run before
  the last case. Does not block;
  the cap is Erhan's decision.
- **Carried from ADR-027:** D's schemas have never been sent to the provider, so their live contract
  is unverified; the cases are AI-drafted and one person selected them and rates the answers.
- **Open for Erhan (independent review, round 1):** keeping the record of a C or D cell that a
  replay failure ended after a sent call would make such a cell count as run, but it changes C's
  behaviour for that input, which the frozen contract keeps unchanged; it stays as described above
  until he decides. Decided by him on 2026-11-27: kept at the runner and in the scoring, C's
  behaviour unchanged (section 8).

## 7. Not done

No live repetition (it needs Erhan's separate decision), no blinded review, no Jev replay and no
second or third repetition (each needs another decision on cap and code). The delivery items are
unchanged: [project frame](../agents/cas-ai-engineering.md).

## 8. The fixes of 2026-11-27

**Decided by Erhan on 2026-11-27** for the three P2 points and the P3 point that the third
independent review round left open (as the reviewer reported them in
[#73](https://github.com/erhanuenlue/tarifhub/pull/73)), recorded in
[ADR-028](../adr/028-phase4-books.md). Approving these fixes, like approving the USD 40 technical
cap, authorizes no expenditure; a live run needs his separate decision.

| Point (as the reviewer reported it) | Fix |
|---|---|
| "Commit the time-budget pin with the first reservation" | the first call's request is saved first; the pin and the first reservation are then written as one accounting event (the ledger is created holding both lines or not at all: staged beside it and linked into place, never replacing a ledger). A failed request write, or a ledger write that leaves the ledger absent, leaves neither line; a write whose result is not known stops the run before anything is sent |
| "Make output tags exclusive across both comparison designs" | both designs claim the run's local folder before the client is built or the model loads (the folder, then a claim file naming the design and a token only that invocation holds); a second invocation under the tag, of either design and in either start order, is refused before it loads anything |
| "Preserve confirmed sends when a Phase 4 cell aborts" | C's and D's shared failure and model behaviour are unchanged; the same error now carries the cell's record as it stood. The runner records the aborted cell before the run stops: a call counts as sent only when this run saved its request and its response, consistent with the books (a settlement, where there is one, saying sent with that response's SHA-256; since 2026-11-28 only when that response is the complete one, section 9), which makes the cell one that ran and failed, as the frozen rubric counts it; a reservation without that proof confirms nothing. The searches those calls ran are kept as the cell recorded them and scored like any failed cell's (T3 counts an executed unnecessary search; the supplemental A1 report counts the executed or refused attempt beside it); nothing after the last recorded step is inferred, and the summary counts those that ran apart (one without a proven send is not run) |
| "Release unused claims if marker creation fails or `_run` aborts during pre-cell setup" | a failure while the claim is written, before the first cell, or an interruption there gives back only that invocation's own unused claim; another invocation's claim and any artifact stay |

Unchanged: the frozen requests (B's and C's request hashes, D's frozen texts), the file names
(`claimed.json`, `local/<tag>-comparison/`, `results/<tag>-comparison.json`), the ledger lines and
their strict reading (books written in the earlier order read as before), the recorded ledgers and
results, the freeze record's file hashes and the scoring rules.

**Independent review of the fixes (round 4, its revision named in [#73](https://github.com/erhanuenlue/tarifhub/pull/73))** found 0 P1, 3 P2 and a P3 line, all on
the recovery of an aborted cell: a saved response should prove a send whose settlement was
interrupted; a matching request hash does not prove which run booked a call (the frozen requests
are identical across runs); a search that ran before the abort should be scored. Fixed the same
day as stated in the table above (the proof is the run's own request and response, since
2026-11-28 its complete response, section 9; the cell's record rides on the error); a typed `/ship-it source-only` in a fresh session was left for Erhan (typed after `/clear` on 2026-11-28, which he accepted as resolving the point; section 9).

**Independent review of those fixes (round 5, its revision named in [#73](https://github.com/erhanuenlue/tarifhub/pull/73))** found 0 P1, 3 P2 and a P3 line, again
in the recovery path: a booking another run made after this run stopped still entered its
accounting and outputs; a settlement line cut short made the books unreadable and hid a send the
run's own files prove; an interruption while the lock was given back escaped without the cell's
record. Fixed the same day: a booking counts as the run's own only with its own response or the
call in its own record, anything else is left out of the record, the accounting and the outputs;
unreadable books take no part in the proof (accounting `unknown`), and the damaged books still
refuse every run until repaired; the record rides on any error around the lock, and a cell that
had ended keeps its recorded ending (`ended`), so a recorded answer turn is not turned into no
action.

**Checks.** The pilot's offline suite: 781 tests in fifteen files, all passing (734 before): D 56
(52), runner 89 (69), scorer 195 (172). Run against the code before the first fix commit (the
third review round's revision, named in [#73](https://github.com/erhanuenlue/tarifhub/pull/73)), the three changed test files of that commit
failed in 26 of their 326 tests, all of them the new behaviour (the
ten refusals of malformed aborted records passed there too, since that code refused every aborted
record); run against the code that round 4 and round 5 reviewed (named in [#73](https://github.com/erhanuenlue/tarifhub/pull/73)), the
round-4 fixes' tests fail in 10 of 336 and the round-5 fixes' tests in 5 of 340. Lint clean. A
scripted B cell and C cell in the Phase 2 and 3 books give identical records, requests and ledger
lines (times aside) at `140ca86` and now; `results/` is byte-identical to `140ca86`; the 14 file
hashes of the freeze record hold.

**Rehearsal (simulated, the harness and inputs of section 5 on the fixed code):**

| Scenario | Result |
|---|---|
| One repetition, one invocation; a concurrent invocation under another tag | as in section 5: 57 cells, 77 calls each sent once, 19 of 19 cases complete; the concurrent invocation refused by the lock |
| Interrupted while `P4-F05`'s C call 1 was on the wire, then restarted | as in section 5 (76 calls, the open call never sent again, 18 of 19 complete); the cell is now kept as aborted, with no confirmed send |
| Interrupted while `P4-F05`'s C call 2 was on the wire (call 1 sent and settled), then restarted | the cell is kept as run and failed (one confirmed send, the open call unconfirmed); the restart sends no call again; 77 calls; 19 of 19 complete |
| Same tag, Phase 4 first: a Phase 3 and a second Phase 4 invocation start while it loads the model | both refused before loading anything; one model load; 77 calls, each sent once; 19 of 19 complete |
| Same tag, Phase 3 first: a Phase 4 invocation starts while it loads the model | refused: nothing counted, sent or booked, no Phase 4 ledger; the Phase 3 invocation, interrupted before its first cell, gave its claim back; the Phase 2 and 3 books unchanged |
| Replay failure in C of `P4-F03` and in D of `P4-F07` | each stopped its run with the cell recorded as run (one confirmed send, priced) and its one search kept; two restarts completed the repetition: 75 calls, none sent twice, 19 of 19 complete, 2 aborted cells |
| Expensive usage; another case kept at USD 29.6512; one micro-dollar more | as in section 5: a stop before `P4-F14` (USD 32.118), the exact fit admitted (a stop before `P4-F02`), one micro-dollar more refused before the model loads |

The copies of the Phase 2 and 3 ledgers stayed byte-identical in every scenario, and the
repository's `results/` stayed byte-identical with no Phase 4 ledger.

**Residual limits** (none blocks a live run): a reservation whose sending is unknown, or a send that
got no response this run kept (since 2026-11-28 also one whose response file an interruption cut
short, section 9), confirms nothing, so a cell with no earlier proven send stays not
run; an aborted cell is scored up to its last recorded step only; the headroom near the end and the
limits carried from ADR-027 are as in section 6. The rehearsal ran on the round-4 and round-5
fixes as well, with the same results.

## 9. The fixes of 2026-11-28

**Decided by Erhan on 2026-11-28.** He confirmed the parts of the fixes of 2026-11-27 that go
beyond the runner layer, narrowly for recovering what an aborted cell observed: the cell's record
carried on the unchanged error of the shared `evidence_agent.run_case`, raised where it was before,
and the scorer's reading of aborted records. The error and when it is raised, B's and C's requests
and behaviour, D's frozen contract and the scoring rules stay unchanged. He had the two P2 points
and the P3 point that the sixth independent review round left open (as the reviewer reported them
in [#73](https://github.com/erhanuenlue/tarifhub/pull/73)) fixed test-first, recorded in
[ADR-028](../adr/028-phase4-books.md). Approving them authorizes no expenditure; a live run needs
his separate decision.

For each interruption, what the cell observed, what the books establish and what the scorer may
count:

| Point (as the reviewer reported it) | The cell observed | The books establish | The scorer may count |
|---|---|---|---|
| "Preserve D's recorded coverage when ranking is interrupted" | D's call sent, its complete response saved and settled; D's coverage decision recorded with a valid targeted search; the search interrupted while being ranked, no result recorded | the call reserved and settled as sent, with the response's SHA-256 | the call as sent, at a decision point without action (listed, left out of the rates); D's coverage entry in its coverage diagnostics only; no executed or refused search, no returned passage, nothing in T3 or in the supplemental A1 report |
| "Reject incomplete response files as proof of a send" | the call sent and the complete response's SHA-256 recorded; the response file empty, cut short or holding other bytes when the interruption came | the call reserved and not settled: open, committed at its reservation | no send: the call is listed as unconfirmed and never sent again; an earlier proven call stays proven; with none, the cell did not run and its case stays incomplete |
| "Keep `ended: deadline` when lock release is interrupted after the final reservation was released unsent" | its earlier calls sent; its last call reserved, then released unsent because the deadline had passed; the deadline recorded as its ending; then the lock's release interrupted | the earlier calls settled as sent, the last one as not sent (released) | the earlier calls and their searches as before; the released call is none; the local record keeps the ending (`ended: deadline`), the public outcome stays `aborted`; a release that was never saved, or books that cannot be read, infer neither a release nor an ending |

**Rules in code.** A saved response file proves a send only when its SHA-256 equals the complete
response's as recorded apart from the file, by the cell before it saved the file (its record,
carried on the error) and by readable books that settled the call as sent: at least one of them
present and none different, and a zero-byte file never, even for an empty response
(`run_comparison._aborted`). D's coverage entries are kept for every
proven call (`run_comparison._traced`); the scorer counts the entry of the call an aborted cell
was cut off at, before that call's action was recorded, as recorded (a search entry only for a
call offered the tool), while completed cells, cells that had ended and every other call keep the
strict check that an entry's action is its call's (`phase4_scoring._coverage`). A cell's recorded
ending is kept also when its one booking after the sent calls was released unsent, as its record
says and readable books hold. Books that cannot be read, whatever their damage, take no part
(accounting `unknown`), and since the ninth review neither does a Phase 4 ledger missing when the
run recovers; a call readable books settle as sent that the run cannot show it sent
leaves the accounting `uncertain`, ahead of any overage, which stays on its call
(`above_reservation`, unconfirmed calls included).

**The independent review of these fixes** (round 7, its revision named in [#73](https://github.com/erhanuenlue/tarifhub/pull/73)) found three more P2 gaps in the
same recovery, fixed the same day, test-first, in the runner alone: a zero-byte response file still
proved a send when the response itself was empty; a response file that disagreed with a usage
settlement left the accounting `priced`; books made unreadable by an amount past float range or by
nesting past the parser escaped the unreadable-books rule, so the aborted cell was dropped. Its P3
points on the documentation are taken into the sentences above and into ADR-028, the README and
arc42 sections 5, 6, 11 and 12 (when an aborted record is written, the open and the retained
booking, a recorded answer turn, the aborted cells counted).

**The review of those fixes** (round 8, its revision named in
[#73](https://github.com/erhanuenlue/tarifhub/pull/73)) found the round-6 and round-7 points
resolved but one: the uncertainty was still hidden when that call's usage settlement was also above
its reservation (the overage took the accounting). Fixed the same day, test-first: any uncertainty
makes the accounting `uncertain` ahead of an overage, and each unconfirmed call carries its
settlement's `above_reservation`, as the sent calls already did. (This page added that an overage
always ends its cell, so no other pairing of the two arises; the ninth review refuted that: a tool
turn kept at its reservation can precede a later call above its own, so the uncertainty and the
overage arise on different calls, with the same result, tested since.) Its P3 points are taken in: the unresolved-tail sentence of
the runner's module docstring is qualified, and this page names the reviewed revisions through
#73 instead of citing branch commits.

**The final review of those fixes** (round 9, its revision named in
[#73](https://github.com/erhanuenlue/tarifhub/pull/73)) found one more gap in the same recovery:
a Phase 4 ledger that is missing when the run recovers (there since an earlier booking) is a new
one to the books' reader, so the recovery took the books as readable and empty, dropped the call
the run's own files prove (accounting `nothing_reserved`), and a restart with the ledger restored
skipped the cell, leaving the case incomplete. Fixed the same day, test-first (in the runner; after
the tenth review also in the books' recovery reader, below): a ledger that is not there when the run recovers takes no part, like books that cannot be
read (accounting `unknown`); the run's own request, complete response and record still decide, no
cost is taken from the response, and nothing is written to the books. A missing ledger alone
proves nothing: a first use books as any other, a complete response file without the cell's record
proves no send, and one cut short stays unconfirmed. The books stay the only record of what was
booked: a run started while the ledger is still missing finds new books and would book and send
every cell again (shown offline), so a missing ledger is restored before any restart. Its three P3
points are taken in: a call can itself prove its send (the runner's module docstring, ADR-028, the
README and arc42 section 6), the uncertainty and an overage can arise on different calls (the
sentence above, now with a guard test), and the scorer's `aborted` subtotal counts only aborted
cells with a proven send (its docstrings, ADR-028 and arc42 section 13, with a guard test).

**The review of that fix** (round 10, its revision named in
[#73](https://github.com/erhanuenlue/tarifhub/pull/73)) found the ledger could still be missed:
probed before and after the read, a ledger away only while the recovery read it, and back
afterwards, looked present, so the books read as empty dropped the proven send again; the other
way round, a probe after the read could override readable books that hold no booking of the cell.
Fixed the same day, test-first: the books' recovery reader (`evidence_agent.phase4_cell`, used by
the recovery alone) reports a ledger that is not there as it is read (only a missing ledger reads
as no events, since a present one holds its pin), so the recovery observes the ledger once and the
probes are gone; the strict ledger reading, admission, `run_case`, B, C, D and the scoring are
unchanged. Its two P3 points are taken in: ADR-028's guarantee that a restart sends or books no
cell twice holds while the books hold its booking, and a deadline ending is kept only when
readable books hold the release (ADR-028, arc42 section 6 and the README).

**Test first** (the repository's `tdd` skill; the scripted provider, temporary books and
deterministic interruptions, through the runner's and the scorer's entry points): each regression
failed on the code before its fix and passes with it.

| Point | Regression | Before the fix | With the fix |
|---|---|---|---|
| D's coverage | an interruption while D's search is ranked (raised at the e5 boundary when the search's query is embedded), the record scored by the real scorer | the record kept no coverage entry (`assert [] == [{...}]`); with the runner's change alone the scorer refused the record ("a coverage entry's action must be the action of its call") | passes |
| Complete response | C's response file left empty, truncated or as other JSON; call 1 proven, then call 2 cut short; books that cannot be read; each ending in a restart | the cut-short file counted as a sent call (`(1, [...]) == (0, [])`, and `(2, ...) == (1, ...)` after a proven call) | passes: no send counted, the reservation open, nothing sent again |
| Deadline ending | C's last call released unsent at the deadline, then the lock's release interrupted | `('aborted', None, 1) == ('aborted', 'deadline', 1)` | passes |
| Zero-byte file (round 7) | C's response an empty body, interrupted while its file is written or after its settlement | the zero-byte file counted as a sent call (`(1, [...]) == (0, [])`) | passes: no send, the call booked and never sent again |
| Digest conflict (round 7) | C's response file altered after its usage settlement, then the lock's release interrupted | `'priced' == 'uncertain'` | passes |
| Unreadable books (round 7) | the books damaged by an amount past float range, or by nesting past the parser, while C's lock is given back | C's cell dropped (`['fixed10'] == ['fixed10', 'agent']`) | passes: the cell kept with its proven send, accounting `unknown` |
| Overage and conflict (round 8) | C's answer settled above its reservation, its response file then altered, the lock's release interrupted | `'above_reservation' == 'uncertain'` | passes: accounting `uncertain`, the overage on the unconfirmed call |
| Missing ledger (round 9) | C's call booked, sent, saved and settled; the Phase 4 ledger moved away while C's lock is given back, then restored, byte for byte, before a restart | the proven call dropped (`'nothing_reserved' == 'unknown'`) | passes: one proven call, accounting `unknown`, no cost; the case complete; the restart sends and books D only |
| Ledger gone during the read (round 10) | C's call proven; the ledger moved away exactly while the recovery reads it, then moved back | the proven call dropped (`'nothing_reserved' == 'unknown'`) | passes: accounting `unknown`, the send kept, the case complete after the restart, which sends D only |
| Books read, then gone (round 10) | the recovery reads an earlier copy without C's booking, and the ledger is gone right after the read | the probe overrode the readable books (`'unknown' == 'nothing_reserved'`) | passes: the readable books decide (`nothing_reserved`, nothing kept) |
| Missing ledger alone (round 9) | the ledger moved away after C ran, the error carrying no record of the cell; a response file cut short while the ledger is moved away | `'nothing_reserved' == 'unknown'` in both | passes: no send proven, the call unconfirmed, accounting `unknown`; nothing sent again |

Guards that pass before and after: an entry whose action is not its call's stays refused in a
completed cell, in a cell that had ended and for an earlier call; a release that was never saved
and books that cannot be read infer neither an ending nor a release. Three scorer tests of the
rule (D's entry for the call cut off as a search, a refused search or an answer turn) were written
after the fix and fail on the code before it; a search entry for a call never offered the tool
failed first and is refused now. Since the ninth review, three more guards that pass before and
after: a first use whose run stopped before its books were created books and sends each cell once
on the restart; a tool turn kept at its reservation followed by an answer above its own
reservation leaves the accounting `uncertain` with the overage on its call; the summary counts an
aborted cell without a proven send as not run.

**Checks** (on the code of these fixes): the pilot's offline suite, 811 tests in fifteen files, all
passing, none skipped (809 before the round-10 fix, 803 before round 9's, 781 before round 6's):
runner 111 (109, 104, 89),
scorer 203 (202, 195); D 56 and the agent loop 156 unchanged. Lint clean. A scripted B cell and C cell in the Phase 2 and 3 books give identical
records, requests and ledger lines at `140ca86` and now; `results/` is byte-identical to
`140ca86`; the 14 file hashes of the freeze record hold; no Phase 4 ledger exists. The simulated
rehearsal of section 5, run again on this code (after the round-7 to round-10 fixes too),
gave the same results in all nine scenarios. A
typed `/ship-it source-only` (after `/clear`, on this branch) loaded
`.claude/skills/ship-it/SKILL.md` from the repository's Git root, not a link; a newly launched
lead process later loaded `/ship-it source-only` through its skill loader (invoked by the lead, not
typed) and it reported the same repository file.

**Residual limits** (none blocks a live run): a call whose response file an interruption cut short
or left at zero bytes proves no send (open at its reservation when the interruption came before
its settlement), like a call interrupted on the wire, so a cell
with no earlier proven call stays not run and its case incomplete; the cell's recorded ending
(`ended`) is kept in the local record only; a run started while the Phase 4 ledger is missing finds
new books and would book and send every cell again, so a missing ledger is restored before any
restart.
