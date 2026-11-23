# commentary_rag: retrieval and cited answers over the BAG commentaries (RAG pilot)

This folder ranks passages of the two BAG commentaries on the changes to the Analysenliste
(editions 2026-01-01 and 2026-07-01) with BM25, the repository's multilingual-e5 embedder and
their reciprocal rank fusion, evaluates the rankings on eight dev cases, and sends each case's
top 5 passages (hybrid, edition filter) to `claude-opus-5-5` for a cited German answer
(ADR-025, `docs/adr/025-commentary-retrieval.md`, accepted 2026-11-14). Nothing here reads or
writes the tariff database or frozen records; generated text never computes, updates or replaces
a tariff record or billing result, though it may quote tariff numbers the BAG passages state.

**Status after the run (2026-11-15, 00:33 CET):** retrieval is measured (below); its
pre-generation rerun reproduced the saved run exactly. The first generation run
(`2026-11-15-generation`, 2026-11-15 00:21 to 00:33 CET) produced eight schema-valid answers on
first attempts for a calculated $1.93; every citation lies in its own context, D1 abstained on its
retrieval miss and U1/U2 abstained as expected
(`docs/evidence/2026-11-15-commentary-generation.md`). These were deterministic checks on
AI-drafted dev cases; semantic support, the rubric and the cases then awaited Erhan's review.

**Human review (completed 2026-11-15):** Erhan Ünlü reviewed the eight stored answers against the
passages and metadata the generator received, the rubric and both commentaries (one reviewer, not
blinded). He judged all 48 structured claims supported by what they cite, but 27 of them fully
relevant to their question (14 partly, 7 not); 14 of the 19 required rubric claims are covered and
the 5 missing ones are all D1's, so D1 stays an end-to-end failure although its abstention was
justified (overall partly appropriate); U1 and U2 abstained appropriately. Aggregates, method and limitations:
`results/2026-11-15-human-review-summary.json`; detailed ratings stay local. This describes one run
on eight dev cases with no held-out test, not an accuracy figure.

**Seeking missing evidence (UC2), offline increments (2026-11-15, 16 and 18):**
`evidence_search.py` is the commentary search of the evidence-seeking agent (ADR-026, proposed),
one read-only search whose bounds are code; `evidence_agent.py` is the agent's loop for one
question, with per-call spending protection; `run_question.py` is the one-question runner that
ranks a question afresh and hands it to the loop once. All three are tested offline, against a
mocked provider with temporary ledgers, and the deadline is cooperative, not a hard limit. Its
books: USD 100 is one aggregate limit for Phase 2 and Phase 3 together;
[`results/generation-ledger.jsonl`](results/generation-ledger.jsonl) stays byte-identical and
counts with all it committed (USD 1.930804, SHA-256
`e0d031ac4b648f5cd1e086c85ae55c3778254b1b70afcc5a9be461a8a4cf5caa`), and all later spending goes
to one active ledger beside it, [`results/phase3-ledger.jsonl`](results/phase3-ledger.jsonl). The
hash is pinned in the agent's code, not chosen by a caller. The comparison with fixed top-5 and
top-10 contexts is built and tested offline since 2026-11-21 and ran live once that day (below):
all three conditions use the agent's accounting path, and the Phase 2 runner must not be used
during Phase 3 to bypass it.

**First live run (2026-11-20, dev case D1, code of `main` at `df5d20d`):** one authorised
invocation of `run_question.py run` (evidence:
[`docs/evidence/2026-11-20-phase3-d1-agent-run.md`](../../docs/evidence/2026-11-20-phase3-d1-agent-run.md),
public record [`results/2026-11-20-question-D1.json`](results/2026-11-20-question-D1.json)). Two
calls, both priced from their usage within their reservations (USD 0.560552 calculated, nothing
left reserved, USD 2.491356 committed in all), one search, ten passages supplied, so the passage
cap left no second search; a structurally accepted `partial` answer that cites one of D1's two
previously missing passages (`2026-07-01/p6/s2.5/5`; `2026-07-01/p7/s2.5/1` was not retrieved,
its rank for the agent's query unknown). The live provider contract is verified only for what
that run exercised; no error, timeout or deadline path has run live. One development
observation, not an evaluation. No earlier record changed.

**Human review of the D1 run (confirmed 2026-11-21):** Erhan Ünlü rated the stored answer in a
local worksheet (one reviewer, not blinded). Claims: support 16 yes, 1 partly, 0 no; relevance 9
fully, 4 partly, 4 not. Rubric: 3 of 5 items covered, 1 partly, 1 not. Reported gaps: 5 accurate,
1 partly; 3 fully relevant, 1 partly, 2 not. `partial` judged appropriate; the agent's overall
behaviour partly appropriate. The answer covered both tariff changes and how they offset each
other, the effective date only partly, and missed the evaluation through 30 June 2028 and the
recalculation under transAL-2, whose passage the agent never received. Scoped to this one dev
case; details on the evidence page, ratings and notes local.

**Phase 3 comparison, offline increment (2026-11-21):** `run_comparison.py` runs each question
under three conditions through the agent's one accounting path: A (`fixed5`), the Phase 2 request
with the hybrid top 5; B (`fixed10`), the same request with the top 10; C (`agent`), the
evidence-seeking agent from the top 5. Each cell (case and condition) is its own identity in the
books, and one case ID names one question over one edition selection. Built and tested offline
(mocked provider, temporary ledgers), then run live once on 2026-11-21 (next paragraph). Its
evaluation set is six cases, E1 to E6, AI-drafted,
decided by Erhan and frozen on 2026-11-21 before any retrieval or generation on them (hashes in
[`results/2026-11-21-phase3-E-freeze.json`](results/2026-11-21-phase3-E-freeze.json); questions,
gold evidence and rubric kept local). Its offline plan for these cases is
[`results/2026-11-21-comparison-plan.json`](results/2026-11-21-comparison-plan.json): 18 cells,
a worst case of USD 44.352 against USD 97.508644 of headroom (a bound) and about USD 6.29 estimated
(from development cases, not a bound). Details under "Comparing the three conditions" below.

**Phase 3 comparison, live run and blinded review (run 2026-11-21, ratings confirmed
2026-11-22):** one authorised invocation of `run_comparison.py run` on E1 to E6 with the code of
`main` at `861994b` (evidence:
[`docs/evidence/2026-11-21-phase3-E-comparison.md`](../../docs/evidence/2026-11-21-phase3-E-comparison.md),
public record [`results/2026-11-21-phase3-E-comparison.json`](results/2026-11-21-phase3-E-comparison.json),
review summary [`results/2026-11-22-phase3-E-review-summary.json`](results/2026-11-22-phase3-E-review-summary.json)).
18 of 18 cells answered; 24 calls, each reserved and settled from usage within its reservation,
USD 4.569196 calculated, USD 7.060552 committed in all, nothing outstanding. Erhan rated the 18
answers blinded (neutral IDs, conditions withheld); his ratings were fixed by hash
([`results/2026-11-22-phase3-E-review-lock.json`](results/2026-11-22-phase3-E-review-lock.json))
before the key was opened. Primary set E2 to E6 (E1 apart, D1 overlap): overall verdict `yes` on
3 of 5 cases for A, 4 of 5 for B and 5 of 5 for C; required claims covered 8, 10 (plus 1 partly)
and 11 of 11; gold evidence items in context 7, 11 and 13 of 13. C changed the verdict against B
on one case, E2, through the one passage its search added from outside the fixed top 10 that
carries required evidence; B and C reached the same overall verdict and required-claim coverage on
E3 to E6, and on E4 to E6 A already sufficed. Calculated cost on E2 to E6: A 1.288300, B 1.261744,
C 1.237324 USD; C made one more call per case and sent 2.1 times B's input; output tokens dominate
every cell's cost, and one run per cell establishes no repeatable cost difference.
On E1, C alone covered both required claims. One run per cell, six cases, one reviewer: an
observation on this set, not an accuracy figure.

## Files

- `corpus.py`: manifest, hash-verified bytes, `pdftotext` on stdin, page-bounded passages. Each
  passage carries its edition, document SHA-256, BAG URL, PDF page, printed page label (checked
  against the page index) and section, and fits a token budget counted with the embedding
  tokenizer. Passage text is always a contiguous run of one page.
- `retrieval.py`: BM25 (`k1` 1.2, `b` 0.75), e5 dense (cosine) and RRF hybrid (`k` 60) over an
  explicit edition selection; equal scores ordered by passage ID.
- `evaluation.py`: case loading and checks, metric definitions, the run record, `recompute`,
  `compare_records`.
- `run_eval.py`: the recorded run with the cached e5 model; `--recompute` for a record,
  `--compare` for two records.
- `cases.json`: the eight dev cases. **AI-drafted; reviewed by Erhan on 2026-11-15** (question
  and reference expectation judged appropriate for all eight; the file is unchanged). None is held
  out; D1 is the Zwischenbericht 1 demo case.
- `results/`: the recorded runs (source, model and configuration identifiers, every full ranking
  with scores, the metrics; passage hashes, no passage text):
  - `2026-11-14-retrieval.json`: the **baseline**, kept byte for byte (SHA-256 `094e5268...`).
  - `2026-11-14-retrieval-corrected.json`: the **corrected run**, a development-set-informed
    correction of the passage construction (below), with the same cases, metrics, top-k, budget
    and ranker settings; its record names the baseline it is compared with.
  - `2026-11-14-comparison.json`: the two runs compared by case, method and mode, with the
    passage identities removed, added or changed and the evidence items whose passages moved.
- `test_corpus.py`, `test_retrieval.py`, `test_evaluation.py`: offline tests with small generated
  PDFs, a stand-in tokenizer and a stand-in embedder.
- `conftest.py`: stops the suite with a message when the `anthropic` client, `pytest-socket` or
  `pdftotext` is missing, so no test is skipped for a missing dependency, and turns pytest-socket
  on around each test: creating a Python socket other than a Unix socket raises
  `SocketBlockedError`, so a test that tries to reach the network fails instead of connecting. The
  block covers Python's `socket` module inside each test only, not subprocesses such as
  `pdftotext` or sockets opened by C libraries. `test_socket_guard.py` checks it.
- `layout_probe.py`: a diagnostic outside the pilot (nothing imports it). For one manifest-verified
  commentary it sets pdfplumber's character geometry and the PDF's tags beside the Poppler text the
  corpus is cut from, finds the frozen passages by text SHA-256 and reports heading lines,
  footnotes and their references. It needs pdfplumber, which no environment here installs: run it
  with `uv run --no-project --with pdfplumber==0.11.11 python tools/commentary_rag/layout_probe.py
  --edition 2026-07-01 --pages 4,6`; without pdfplumber it exits 2. Evidence:
  [`docs/evidence/2026-11-22-pdfplumber-layout-probe.md`](../../docs/evidence/2026-11-22-pdfplumber-layout-probe.md).
- `generation.py`: the request per case (question, selected editions, passages with provenance as
  escaped, untrusted data; no tools, web search, fallback model or sampling parameters), the
  answer schema (status, claims with passage citations, missing evidence), local validation
  (schema, citation membership), and the spending guard (token count, reserved ceiling, ledger,
  attempt cap, budget, no client retries).
- `answers.py`: deterministic checks of the answers (citation membership, expected-evidence
  citation, required-fact term checks, abstention), keeping retrieval misses, generation
  failures and abstention apart. Checks, not semantic or legal validation.
- `run_generation.py`: `prepare` (retrieval rerun and contexts), `plan` (Models API entry, token
  counts, planned cost), `run` (requests, then `report`), `report` (public record and local
  review sheet from the ledger and local artifacts, no API call; `--sheet-only` keeps the record).
  Outputs carry the date of their own step (`--tag`, default today); `--prepared` names the
  `prepare` outputs to use (default: the same `--tag`; the 2026-11-15 run used 2026-11-14 and
  defaulted to it then). No step overwrites an output an earlier run wrote, and a `run` refused by
  another run's ledger lock publishes nothing (added 2026-11-15, after the recorded run).
- `rubric.json`: the answer rubric, **AI-drafted before any generation and used unchanged in
  Erhan's review of 2026-11-15** (which notes that some support quotes, such as D1-R5 and D6-R3,
  are shortened anchors): required claims with verified support quotes and optional term checks,
  optional background, expected status.
- `pricing.json`: the `claude-opus-5-5` prices used for calculated costs, with source URL, date
  and page hash.
- `test_generation.py`, `test_answers.py`, `test_run_generation.py`: offline tests of the
  generation run against a mocked provider HTTP boundary, of the answer checks, and of the steps'
  refusal to overwrite earlier outputs.
- `evidence_search.py`: the commentary search of the evidence-seeking agent (ADR-026,
  proposed). `search_commentary(arguments, state, *, retriever, passages, limits)` runs one
  search request: hybrid ranking over the question's selected editions only, at most
  `min(5, remaining capacity)` passages not yet supplied from the top 10, at most 10 passages per
  question (the fixed five included) and two search rounds (refused and failed requests use
  theirs). It returns the next state, the tool result as escaped passage data, a publishable
  `record` (IDs, ranks, scores, hashes, counts, outcome) and a `local` part with the raw
  arguments and error text; the tool result carries passage text and stays local too. Only the
  agent loop below calls it: in the tests against a mocked provider, and live for the one search
  of the D1 run (2026-11-20) and the one search of each of the comparison's six agent cells
  (2026-11-21).
- `test_evidence_search.py`: offline tests of the search on a synthetic two-edition corpus with
  hand-worked rankings, the real retriever and a stand-in e5 embedder.
- `evidence_agent.py`: the evidence-seeking agent's loop for one question, tested offline and run
  live in two invocations (**live provider contract verified only in part**, by the D1 run and
  the comparison above; its callers are `run_question.py` and `run_comparison.py`). `run_case(task, *, client, retriever,
  passages, clock, budget_s, spending, condition="agent")` runs one question under one condition
  of `CONDITIONS` (fixed in code, chosen by name): `fixed5` and `fixed10` send the Phase 2
  request itself with at most 5 or 10 passages, once, without any tool, admitted at one call's
  ceiling; `agent` is the loop described here. It takes an `AgentTask` (case ID, question, selected
  editions, verified fixed passages: nothing used to score the answer) and a required `Spending`
  (the historical ledger and its expected SHA-256, which must be the hash pinned in the code,
  the active ledger beside it, both in `results/` and refused anywhere else, and a local
  artifact folder; the limit, the Phase 2 settings and the prices of `pricing.json` are fixed
  in code), and sends the Phase 2 request
  content and system
  prompt with a generic search instruction and the one tool; at most three generation calls,
  the conversation only appended to (assistant turns as returned, tool results by tool-use ID),
  no tool on the last call or once searches or passages are used up, no retries (switched off
  on whatever client is given). An answer is
  accepted only when it matches the schema and cites only supplied passages. Outcomes: `answer`
  (with its own status, `insufficient_evidence` included), `invalid_answer`,
  `incomplete_generation`, `protocol_error`, `provider_error`, `deadline`, and for the books
  `refused` (locked, already run, damaged or changed books, admission or input over its
  limit), `persistence_error` (a failed write) and `spending_stop` (a cost above its
  reservation, before a further call). Spending: the case holds Phase 2's folder lock
  throughout; it is admitted only if three calls at the 80,000-token input cap fit beside all
  committed spending under USD 100; each call is counted, refused above the cap, saved under
  `artifacts/requests/<case>-<condition>-call<n>.json`, reserved at its ceiling and only then sent (a request
  the deadline stops is recorded as never sent), its raw response saved under `responses/` and
  settled at its validated usage cost, or at its whole reservation when nothing can be priced
  (timeouts, error responses, missing usage), recorded as exposure, not an invoice. The ceiling
  is the agent's own, for admission and reservations alike: the counted input with a 10 %
  margin at the dearest input rate of `pricing.json` (8 USD per million, an hour's cache
  write), the full 32,000-token output allowance and the 1.1 US multiplier, rounded up to a
  micro-dollar: USD 0.71852 at 1,500 counted tokens, 1.4784 at the cap, so a question is
  admitted against 4.4352. Any usage the settlement prices within the margin fits its
  reservation; that is a calculation from recorded prices, not a billing guarantee. A failed
  write stops the case; a sent call, or one whose release was not saved, stays reserved. The
  books are used by their canonical paths (a link from elsewhere cannot move the lock), and a
  settlement must match the cost of its saved usage and a call ID its case and condition (every
  event names its condition; entries without one, the D1 run's, are the agent's). A late
  or invalid response is settled and still not accepted. One monotonic deadline per question,
  checked before each count, after the count and reservation just before sending, after each
  generation call and after each search, and bounding every request's timeout; cooperative,
  since a check cannot interrupt a request or a search already running. The record and the
  ledger hold IDs, codes, counts, hashes, usage counts and amounts; requests, responses, search
  arguments and errors are local.
- `test_evidence_agent.py`: offline tests of the loop with the real `anthropic` client on a
  mocked HTTP transport, a fake key, the real search, a stand-in monotonic clock and temporary
  ledgers and artifact folders; two tests read byte copies of the recorded Phase 2 ledger, one
  of them altered, and one reads byte copies of both recorded ledgers, pinning the active ledger
  as the comparison left it (53 lines) and its first five lines as they stood before it.
- `run_question.py`: the one-question runner of the agent (below, "One question with the
  evidence-seeking agent"): `prepare` (offline: input checks, verified corpus, fresh top 5) and
  `run` (the live step: one `run_case` call, local and public outputs, exit codes).
- `test_run_question.py`: offline tests of the runner's command over a tiny real corpus
  (generated PDFs through the real corpus builder), the real retriever, the real loop and the
  real `anthropic` client on a mocked HTTP transport with a fake key; only the e5 model and the
  provider's HTTP side are stand-ins. Every test checks that the repository's `results/`,
  `local/` and ledgers stay byte-identical.
- `run_comparison.py`: the Phase 3 comparison (below, "Comparing the three conditions"): `plan`
  (offline: matrix, order, bounds, admission headroom and labelled estimates from the books read
  without the lock) and `run` (one ranking per case, then A, B and C through `run_case`).
- `test_run_comparison.py`: offline tests of the comparison's command over a tiny real corpus whose
  twelve-passage ranking is worked out by hand, the real retriever, loop and `anthropic` client on
  a mocked HTTP transport and temporary books; the repository's `results/` and `local/` are
  checked to stay byte-identical.
- `trace_demo.py`: one synthetic question through the real agent loop (`evidence_agent.run_case`)
  with a scripted provider and the real search over the synthetic test corpus, traced to a local
  Phoenix over OpenTelemetry (OTLP/HTTP, 127.0.0.1:6016). The spans hold IDs, codes, counts, elapsed
  times and SHA-256 prefixes only: no text and no cost. The books are temporary. Offline, no key
  (below, "Tracing one synthetic run in a local Phoenix").
- `phoenix_serve.sh`: starts that Phoenix from an empty environment with TarifHub's own storage in
  `local/phoenix/`, loopback only, gRPC receiver disabled.
- `training_inventory.py`: the Phase 4 training-data inventory, offline (the e5 tokenizer counts
  tokens, nothing is embedded or sent). It parses the earlier commentaries pinned in
  `data/manifests/bag-al-2024-2025.json` with `corpus.py`, rebuilds the frozen 2026 corpus and checks
  it against `results/2026-11-14-retrieval-corrected.json`, groups the earlier sections into change
  families by shared position codes or named projects, drops every family that shares a code or a
  project with the 2026 material, and counts usable and eligible passages with the sensitivities of
  its rules. It reads no evaluation case. Record:
  [`results/2026-11-23-training-inventory.json`](results/2026-11-23-training-inventory.json) (IDs,
  hashes, codes, projects, families and counts, no passage text); evidence:
  [`docs/evidence/2026-11-23-phase4-training-data-inventory.md`](../../docs/evidence/2026-11-23-phase4-training-data-inventory.md).
  It reads the e5 model from the local cache only and never replaces an existing record.
  With `--older-commentaries` it reads the ten 2021 to 2023 commentaries of
  `data/manifests/bag-al-commentaries-2021-2023.json` (a commentary-only manifest read by
  `corpus.build_commentaries`, which gives each PDF a source ID: two commentaries share 1 January 2023
  and one covers 1 January and 1 February 2022) and records three views, the four commentaries above,
  the ten alone and all fourteen with the families rebuilt across them, with every passage of the
  baseline and of the older view whose eligibility changes. Record:
  [`results/2026-11-23-training-inventory-2021-2025.json`](results/2026-11-23-training-inventory-2021-2025.json);
  evidence:
  [`docs/evidence/2026-11-23-phase4-older-commentaries-inventory.md`](../../docs/evidence/2026-11-23-phase4-older-commentaries-inventory.md).
  `test_training_inventory.py` tests it on synthetic passages and tiny generated PDFs.
- `sign_test_power.py`: the exact power of the paired sign test planned for the Phase 4 comparison
  (standard library only; p-values as fractions). Its record
  [`results/2026-11-23-sign-test-power.json`](results/2026-11-23-sign-test-power.json) holds the
  scenarios of the evidence page; `test_sign_test_power.py` checks it against an exact-fraction
  recomputation of the same sums.
- [`results/2026-11-21-comparison-plan.json`](results/2026-11-21-comparison-plan.json): the offline
  plan for the cases E1 to E6 (IDs and editions only, made before they were frozen), made against
  the recorded books.
- [`results/2026-11-21-phase3-E-freeze.json`](results/2026-11-21-phase3-E-freeze.json): the freeze
  record of the evaluation set E1 to E6: the SHA-256 of the runner input and of the private gold
  evidence and rubric (all three kept local), each question's SHA-256 as the books record it, the
  editions, the generic scoring and reporting rules, the decision and freeze dates and the
  provenance; no question, evidence or rubric text.
- `results/2026-11-14-retrieval-rerun.json`: the pre-generation rerun of the corrected run
  (identical rankings, scores, metrics and passages).
- `results/2026-11-15-generation-plan.json` (the plan the run used, no workspace header) and
  `results/2026-11-15-generation-plan-with-workspace-header.json` (the first plan of that day,
  kept unchanged); `results/2026-11-15-generation.json` (the run record: configuration, contexts
  by hash, every attempt with usage and calculated cost, the checks; no answer text);
  `results/generation-ledger.jsonl` (append-only reservations and settlements, cumulative).
- `results/2026-11-15-human-review-summary.json`: the public summary of Erhan's completed review
  (method, limitations, aggregate counts, fields the review leaves unsettled, source hashes; no
  answer text and no review comments).
- [`results/phase3-ledger.jsonl`](results/phase3-ledger.jsonl) (the active ledger: its baseline
  pin, the D1 run's two reservations and two usage settlements, then the comparison's 24
  reservations and 24 usage settlements) and
  [`results/2026-11-20-question-D1.json`](results/2026-11-20-question-D1.json) (the D1 run's public
  record), each as the runners wrote them on 2026-11-20 and 2026-11-21.
- [`results/2026-11-21-phase3-E-comparison.json`](results/2026-11-21-phase3-E-comparison.json): the
  comparison run's public record (provenance, every case's ranking by ID, score and hash, per cell
  its statuses, calls, usage, costs, searches by passage ID and rank, supplied and cited passages;
  no question, answer, passage, query or provider text), as the runner wrote it.
- [`results/2026-11-22-phase3-E-review-lock.json`](results/2026-11-22-phase3-E-review-lock.json):
  the SHA-256 of both review packets, the ratings template, the transferred ratings, the neutral ID
  listing and the blinding key, committed before the key was opened.
- [`results/2026-11-22-phase3-E-review-summary.json`](results/2026-11-22-phase3-E-review-summary.json):
  the public summary of the blinded review by case and condition (method, unblinding checks,
  limitations, every rating count, retrieval figures, what the agent's searches added, paired
  verdicts, costs and the books; no neutral ID, note, question, answer or passage text).
- `local/` (git-ignored): contexts with passage text (`2026-11-14-contexts.json`), raw requests
  and responses and the run result (`2026-11-15-generation/`), the human-review sheet as generated
  (`2026-11-15-review-sheet.md`, ratings empty, kept unchanged), Erhan's approved review
  (`TarifHub_RAG_Bewertung_Erhan_2026-11-15.md`) and its structured transfer with every rating,
  excerpt and the input hashes it was checked against (`2026-11-15-human-review.json`); for the
  2026-11-20 D1 run, the runner's folder (`2026-11-20-question-D1/`: raw requests and responses,
  answer, full result), its console output (`2026-11-20-question-D1-console/`), the review
  worksheet as generated (`2026-11-20-D1-review-worksheet.md`, ratings empty, kept unchanged)
  and Erhan's completed copy with his ratings and notes (`2026-11-20-D1-review-worksheet-erhan.md`,
  confirmed 2026-11-21); for the comparison of 2026-11-21, the frozen set with its blinding
  listing (`2026-11-21-phase3-E-set/`), the key (`2026-11-21-phase3-E-blinding-key/`), the run's
  requests, responses and full result (`2026-11-21-phase3-E-comparison/`), its console output, the
  trace findings sealed until the ratings were fixed (`2026-11-21-phase3-E-sealed/`), the packaging
  and unblinding scripts (`2026-11-21-phase3-E-packaging/`) and the review folder
  (`2026-11-21-phase3-E-review/`: both packets, the blank and the transferred ratings, the local
  lock copies and the unblinded table with neutral IDs).

## Passage construction (corrected run)

The corrections followed the baseline's D2 and D6 misses, so they are informed by the dev cases:

- A compound abbreviation such as `Pos.-Nr.` no longer ends a sentence.
- A table of position rows (description, code such as `1006.00`, value) stays one passage with
  its heading line (ending in ':') and column names when it fits the budget. If it does not, it
  is split between rows and every later part carries that heading and the column names as
  `context`: verbatim text from the same page, indexed and counted with the part but never
  counted as the part's own text when evidence is matched.
- A heading with no text of its own joins the text it heads on the same page; a heading at the
  foot of a page is recorded as excluded, since it cannot join text on another page.

## Commands (from the repository root)

Offline tests, all 414 (no model, no key, no network; pytest-socket blocks Python sockets in each
test): poppler's `pdftotext`, the ingestion `ai` extra (the locked `anthropic` client) and the
`dev` extra's `pytest-socket` are required, and the suite refuses to start without them. A
separate environment keeps the `ai` extra out of the ingestion venv (CI runs the same suite in its
own `commentary-rag` job):

```bash
UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" uv run --project services/ingestion \
  --frozen --extra ai --extra dev python -m pytest tools/commentary_rag -q
```

Recorded run (the model must already be in the Hugging Face cache; `--offline` and
`HF_HUB_OFFLINE=1` refuse any download), then drop the e5 extra from the service venv again
(the AGENTS.md gotcha). The corrected run was recorded with `--label` and `--baseline`:

```bash
HF_HUB_OFFLINE=1 uv run --project services/ingestion --frozen --offline --extra e5 --extra dev \
  python tools/commentary_rag/run_eval.py --out tools/commentary_rag/results/<name>.json \
  [--label "<what distinguishes this run>"] [--baseline tools/commentary_rag/results/<base>.json]
(cd services/ingestion && uv sync --frozen --offline --extra dev)
```

Recompute the metrics of a stored record, or compare two records (no model needed):

```bash
uv run --project services/ingestion --no-sync python tools/commentary_rag/run_eval.py \
  --recompute tools/commentary_rag/results/2026-11-14-retrieval-corrected.json
uv run --project services/ingestion --no-sync python tools/commentary_rag/run_eval.py \
  --compare tools/commentary_rag/results/2026-11-14-retrieval.json \
            tools/commentary_rag/results/2026-11-14-retrieval-corrected.json \
  --out tools/commentary_rag/results/2026-11-14-comparison.json
```

The run refuses when a commentary is missing or fails its hash, when `get_embedder` falls back to
the 16-dimensional stub, or when a passage or query would exceed the model's 512-token input.
Token counts come from the loaded model's tokenizer on the exact embedded string (`passage: `
or `query: ` prefix, any table context, special tokens) and are checked against
SentenceTransformer's own preprocessing.

Phase 4 data feasibility (offline; the inventory needs the four commentaries and workbooks of
`data/manifests/bag-al-2024-2025.json`, and for its three views also the ten PDFs of
`data/manifests/bag-al-commentaries-2021-2023.json`, downloaded from their source URLs and the e5 model already in
the local cache, which it reads with Hugging Face offline mode forced; neither command replaces an
existing file, so give each a new name):

```bash
UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" uv run --project services/ingestion \
  --frozen --offline --extra ai --extra dev python tools/commentary_rag/training_inventory.py \
  --out tools/commentary_rag/results/<new inventory record>.json
UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" uv run --project services/ingestion \
  --frozen --offline --extra ai --extra dev python tools/commentary_rag/training_inventory.py \
  --older-commentaries data/manifests/bag-al-commentaries-2021-2023.json \
  --out tools/commentary_rag/results/<new three-view record>.json
python3 tools/commentary_rag/sign_test_power.py --out tools/commentary_rag/results/<new power report>.json
```

## Generation

The generation tests use the offline command above: the provider is a mocked HTTP transport,
and the live key is removed from the test environment.

The pilot, from the repository root. `prepare` needs the cached e5 model and no network; `plan`
and `run` read `ANTHROPIC_API_KEY` from the root `.env` through uv (presence is checked, the value
is never printed or stored). A key that is not scoped to a workspace also needs
`ANTHROPIC_WORKSPACE_ID` in `.env`; it is sent as the `anthropic-workspace-id` header and its value
is not recorded. uv's `--env-file` does not override a variable already set in the shell, so
`env ANTHROPIC_WORKSPACE_ID=` keeps the header off while the key still comes from `.env` (the
2026-11-15 run used this).

```bash
HF_HUB_OFFLINE=1 uv run --project services/ingestion --frozen --offline --extra ai --extra dev \
  python tools/commentary_rag/run_generation.py prepare --tag <date>
uv run --project services/ingestion --frozen --offline --extra ai --extra dev --env-file .env \
  python tools/commentary_rag/run_generation.py plan --tag <date>
uv run --project services/ingestion --frozen --offline --extra ai --extra dev --env-file .env \
  python tools/commentary_rag/run_generation.py run --tag <date>
uv run --project services/ingestion --frozen --offline --extra ai --extra dev \
  python tools/commentary_rag/run_generation.py report --tag <date> [--sheet-only]
(cd services/ingestion && uv sync --frozen --offline --extra dev)
```

`report` refuses for the 2026-11-15 run, since its record and review sheet exist: re-rendering
`local/2026-11-15-review-sheet.md` would empty the ratings the completed review was checked
against (by hash). Erhan's ratings live in `local/2026-11-15-human-review.json`. Every other step
refuses in the same way when its output exists.

Fixed settings: `claude-opus-5-5`, effort `max` (the repository's quality-before-cost rule; the
API default for this model is `medium`), adaptive thinking, `max_tokens` 32,000 (thinking and
answer together), non-streaming with a 1,200 s timeout, client retries off, at most 10 attempts
in the ledger, a failed case retried only after every case had one attempt, valid answers never
repeated, any other 4xx or a different returned model stops the run, USD 100 cumulative budget.
Before sending, each request's input is counted with the token-counting endpoint and its ceiling
(counted input + 10 % margin at $4/MTok, plus 32,000 output tokens at $20/MTok) is reserved in
the ledger; a timeout or connection error is charged at its reservation. Costs are calculated
from reported usage and `pricing.json`, not taken from an invoice.

What the offline tests cover: each request carries only its own case's question and passages and
none of the scoring fields, sends no tools, fallbacks or sampling parameters, and is counted
before it is sent; schema violations, cut-off answers and out-of-context citations are kept as
reported, never repaired; one HTTP call per attempt; retries within the cap; blockers stop the
run; a request whose ceiling would pass the budget is never sent; a rerun never repeats a valid
answer; a second run on the same ledger is refused while one is sending; a valid answer is
settled only after its response is saved; provider errors are redacted of key and workspace
identifiers; the answer checks' denominators; every step refuses to overwrite an earlier output,
`run` refuses contexts that differ from the saved record in any field the request carries, and
`report` refuses a saved response whose hash differs from its ledger entry and reports the
attempts whose requests its run saved; a `run` refused by another run's lock publishes nothing;
`--prepared` defaults to the step's own tag. What they miss: real model behaviour, real token counts,
real prices and whether a cited passage supports a claim.

**Code after the recorded run.** The 2026-11-15 run record names the tool files it ran with by
SHA-256 (`run.environment.tool_files_sha256`, uncommitted on top of `88cd681`). Changed since, on
2026-11-15: the steps and `run_eval.py --out` refuse to overwrite an existing output; the tests
no longer skip for a missing dependency; and, after an independent review, `run` checks every
field of the contexts against the saved record, a run holds a lock on the ledger, a valid answer
is settled only after its response is saved, `report` verifies response hashes and covers only
its own run's attempts (those whose requests it saved), a run refused by another run's lock
publishes nothing, `--prepared` defaults to the step's own tag, provider error text is redacted,
and evidence of unattempted cases is no longer counted under failed generations. None of this changes a request, a recorded value or a
metric of the recorded run, which did not exercise this code (its contexts pass the new checks).

## One question with the evidence-seeking agent

`run_question.py` runs the agent of ADR-026 on exactly one question. Both steps take the
question, a stable case ID, an explicit edition selection and a finite time budget, and check
their form before anything is loaded (a case ID and a tag are plain names, editions are distinct
`YYYY-MM-DD` dates, the time budget is a finite number of seconds above 0); that the corpus has
each edition is checked once it is built. They refuse outputs an earlier run left under the
same tag, build the hash-verified corpus with
the cached e5 model (the runner forces Hugging Face offline mode: a missing model or package or
the 16-dimensional stub is refused, nothing is downloaded), refuse a question longer than the
model's 512-token input instead of truncating it, and rank the question afresh: hybrid, the
selected editions only, top 5, as in the Phase 2 pilot. Only the question, its case ID, its
editions and those passages reach the agent; no dev case, gold evidence, rubric or expected
answer is read. The agent's own searches use the same corpus and retriever.

Offline preparation (no key, no client, nothing sent, nothing written, no ledger created; it
prints the initial passages by ID and score and the paths a run would write):

```bash
HF_HUB_OFFLINE=1 UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" \
  uv run --project services/ingestion --frozen --offline --extra ai --extra dev \
  python tools/commentary_rag/run_question.py prepare --case-id <ID> \
  --edition <YYYY-MM-DD> [--edition <YYYY-MM-DD>] --time-budget-s <seconds> \
  --question "<question>" [--tag <date>]
```

The live step, **only when a live run is explicitly authorised**: the same arguments with `run`
and the key from the root `.env` (presence checked before the model loads, never printed; the
workspace-header note under Generation applies):

```bash
HF_HUB_OFFLINE=1 UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" \
  uv run --project services/ingestion --frozen --offline --extra ai --extra dev --env-file .env \
  python tools/commentary_rag/run_question.py run --case-id <ID> \
  --edition <YYYY-MM-DD> --time-budget-s <seconds> --question "<question>" [--tag <date>]
```

`run` calls `evidence_agent.run_case` exactly once; that call may send up to three generation
requests (each token-counted first), all accounted in `results/phase3-ledger.jsonl` under the
aggregate USD 100 limit with the books, prices, settings, search bounds and SDK retries (off)
fixed in code; the runner has no option for any of them. The case ID, under the condition
`agent`, is the identity in the books (the comparison's C for the same case ID is the same cell):
a case already in the active ledger as the agent's is refused whatever `--tag` says, and nothing is
retried or renamed automatically. The time budget starts when the agent starts (after the corpus
and the model are loaded) and is cooperative: a request already sent is not interrupted.

Outputs, written only when the agent reserved at least one call or may have (a reservation whose
ledger write failed, reported as uncertain accounting); otherwise nothing of the case is in the
books, nothing is written, and the case can be run again:

- `local/<tag>-question-<case>/` (git-ignored): `requests/` and `responses/` (each call's raw
  request and response, saved by the agent), `answer.json` (an accepted answer) and
  `result.json` (question, editions, statuses, answer, `CaseResult.record` and
  `CaseResult.local`: requests, responses, search arguments, errors).
- `results/<tag>-question-<case>.json`: provenance (question by SHA-256, settings, prompt and
  schema hashes, corpus and tool-file hashes, the books, git head), the initial ranking by ID,
  score and hash, named keys of `CaseResult.record` (codes, counts, IDs, hashes, usage, amounts),
  answer metadata (status, claim and missing-evidence counts, cited IDs, answer hash) and the
  statuses. No question, answer, passage, search or error text.

Each output is written on its own: a write that fails leaves the others and the request and
response artifacts in place, and nothing is sent again to repair a report. The command prints
the execution status (the agent's outcome and detail), the answer status (`answered`,
`partial`, `insufficient_evidence` or none) and the accounting status (`priced`,
`above_reservation`, `uncertain`, `nothing_reserved`, with every call's reservation, cost, basis
and flag) separately. A schema-valid answer that cites only supplied passages is a checked
answer, not a correct one: its claims need human review against the cited passages.

| Exit | Meaning (when several apply, the first row wins) |
|---|---|
| 7 | persistence: the agent or the runner could not write the ledger or an output |
| 5 | spending stop: a call cost more than its reservation; an answer is still kept locally |
| 6 | accounting uncertain: a sent call could not be priced (its reservation stays committed, as for every timeout and error response) or its settlement is not confirmed |
| 3 | refused: by the runner before any provider work (existing outputs, no key, model, package or corpus unavailable) or by the agent's books (lock, case already run, damaged or changed books, admission, input over the cap) |
| 4 | not answered: invalid answer, cut-off generation, protocol or provider error, deadline |
| 0 | a structurally accepted answer or abstention (`answered`, `partial` or `insufficient_evidence`), persisted, every call priced within its reservation; it does not establish answer quality |
| 2 | invalid input, nothing counted or sent: the arguments are checked before anything loads; an edition the corpus lacks and a question over the model's input are found once the corpus and the model are loaded |
| 1 | an unexpected error |

## Comparing the three conditions (Phase 3)

`run_comparison.py` runs a set of questions under three conditions, each cell (one case under one
condition) through `evidence_agent.run_case` and therefore through the same books, ceiling,
admission, reservations, settlements, persistence, lock and answer checks. Built and tested
offline on 2026-11-21 and **run live once**, the same day, on E1 to E6 ("Live run and blinded
review" below); every further live run needs its own explicit authorisation.

| | A `fixed5` | B `fixed10` | C `agent` |
|---|---|---|---|
| Fixed context | hybrid top 5 | hybrid top 10 | hybrid top 5 |
| Most passages supplied | 5 | 10 | 10 (5 + at most 5 found) |
| Generation calls | 1 | 1 | at most 3 |
| Searches | none | none | at most 2 |
| System prompt | Phase 2's | Phase 2's | Phase 2's + the search instruction |
| Tools in the request | none (no `tools`, no `tool_choice`) | none | `search_commentary` |
| Admission (every call at the 80,000-token cap) | USD 1.4784 | USD 1.4784 | USD 4.4352 |

**Comparable by construction:** the model and settings (`claude-opus-5-5`, effort `max`, adaptive
thinking, `max_tokens` 32,000, the request timeout, no retries, the JSON-schema answer format), the
question text, its editions block, the rendering of every passage as escaped, untrusted data,
one fresh ranking per question (hybrid over its editions only: A's five are B's first five and C's
fixed five), the acceptance rule (schema, and citations only among the passages supplied), the
per-cell time budget, the input cap and the ceiling. A and B send exactly the Phase 2 request of
ADR-025.

**Different by design:** C's system prompt carries the search instruction and its requests carry the
tool definition (more input tokens); C may call up to three times, each later call carrying the
whole conversation, so its token volume and cost are larger; C reaches at most ten passages, B's
count, but through its own queries rather than the ranking's next five; A and B are admitted at
one call's worst case, C at three; and every cell gets the same time budget, which A and B spend
on one call and C shares across up to three calls and two searches (D1's two calls took 210.8 s
of 600 s), so the per-cell budget of a live run must be chosen for C.

**Accounting identity:** a cell is its case ID and its condition. Every ledger event a cell writes
carries its `condition`, and its calls are `<case>-<condition>-call<n>` (`E1-fixed5-call1`); the
one-question runner books the `agent` condition under the same identity. Every reservation also
records the question's SHA-256 and the sorted editions: one case ID names one question over one
edition selection, and a case booked before with another question or editions is refused under
any condition (`case_redefined`). A cell already in the books is refused (`already_run`) whatever
the tag or the entry point, and a call ID an older reservation holds is never written twice
(`call_id_taken`). Ledger entries without a condition (the D1 run of 2026-11-20) are the agent's
and record no question: the books never send D1 to the agent again and would admit D1 under
`fixed5` or `fixed10`, but the comparison runner cannot pair those with D1's agent cell and
refuses D1 (`unverifiable`). Code from before this change refuses books that hold an entry with a
condition as damaged, so once one is written only this code or later can use the books.

**Order and stops:** case by case, a case's A, B and C one after another, so each case's three
answers come close together in time. Before loading anything, `run` refuses a matrix whose worst
case (every cell still to run at its admission) does not fit beside everything committed under
USD 100, and a case whose cells already in the books were asked another question or editions
(`other`) or recorded none (`unverifiable`); every cell is still admitted again by the books,
and its admission, under the lock, also holds back the worst case of the matrix's cells still to
run after it, so after a booking by another invocation in between, the matrix stops at the next
cell once the rest of it no longer fits.
Every case is ranked before any cell runs, so no cell spends before every case can be ranked. The matrix stops, sending nothing
further, after a cell with a failed write, a cost above its reservation, a call kept at its
reservation (error responses, timeouts, unpriced usage) or a refusal other than a cell already in
the books (a call ID that another case's reservation holds among them); nothing is retried. The lock is taken for each cell, so another invocation could run
between the cells of a case; the books stay correct, but run one comparison at a time.

**Input:** a cases file `{"cases": [{"id", "question", "editions"}]}` and nothing else: a field
such as a reference answer, gold evidence or a rubric is refused before the file is used (exit 2),
so nothing that scores an answer can reach a request.

```bash
# Offline plan: no corpus, model, client or key; nothing counted, sent or written; the books read
# without the lock. Prints the matrix, the bounds and the assumptions behind them, each case's
# pairing with cells already in the books, the admission headroom and labelled estimates.
UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" \
  uv run --project services/ingestion --frozen --offline --extra ai --extra dev \
  python tools/commentary_rag/run_comparison.py plan --cases <cases.json>
# The live step, only when a paid comparison run is explicitly authorised:
HF_HUB_OFFLINE=1 UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" \
  uv run --project services/ingestion --frozen --offline --extra ai --extra dev --env-file .env \
  python tools/commentary_rag/run_comparison.py run --cases <cases.json> \
  --time-budget-s <seconds per cell> [--tag <date>]
```

Outputs of `run`, only when a cell reserved a call: `local/<tag>-comparison/` (git-ignored: every
call's request and response, `result.json` with the questions, answers and full traces) and
`results/<tag>-comparison.json` (provenance with the question by hash, the plan, every case's
ranking by ID, score and hash, and per cell its statuses, named metadata of the agent's record and
answer metadata; no question, answer, passage or provider text). A repeated run under any tag
sends nothing again and writes nothing (exit 3). Each cell's exit code follows the one-question
runner's table; the matrix exits with the first of 7, 5, 6, 3, 4, 0 that any cell that ran has. A
cell already in the books is skipped and sets the code only when no cell ran. The outputs of every
cell that ended are written even when an unexpected error stops the matrix (exit 1).

**Proposed plan (2026-11-21, offline):**
[`results/2026-11-21-comparison-plan.json`](results/2026-11-21-comparison-plan.json), made by `plan`
against the recorded books for the six cases E1 to E6 from their IDs and editions, before they were
frozen (their editions did not change; see the evaluation set below). Neither their questions nor
their gold evidence or rubric are committed, and no retrieval or generation has been run on them. 18 cells in the order E1 A, B, C, then E2
and so on; none is in the books, so every case pairs as `new`. The plan was made from the code of
this branch (its `planned.git_head`) and states the assumptions of its bounds: the 80,000-token
input cap, the 10 % margin at the dearest input rate (8 USD per million), the 32,000-token output
allowance at 20 USD per million, the 1.1 US multiplier and the prices of `pricing.json`.

| Figure | USD | Kind |
|---|---|---|
| Committed when planned (Phase 2 1.930804 + D1 0.560552) | 2.491356 | recorded |
| Headroom under the limit of 100 | 97.508644 | recorded |
| One call at the 80,000-token input cap | 1.4784 | bound |
| One case (A + B + C admissions) | 7.392 | bound |
| The matrix's worst case (6 cases) | 44.352 | bound: the admission check, not an expected cost |
| Headroom after the worst case | 53.156644 | bound |
| Estimate per cell: A, B, C | 0.24135, 0.24647, 0.560552 | ESTIMATE |
| Estimate for the matrix | about 6.29 | ESTIMATE |

The estimates are calculated costs of earlier usage settlements, not bounds or invoices: A from
Phase 2's eight fixed top-5 requests, C from the one D1 agent run, and B, never observed, as A plus
five passages' input (1,280 tokens at 4 USD per million). They come from development cases and say
nothing firm about E1 to E6.

**Evaluation set (frozen 2026-11-21):** six cases, AI-drafted by Claude from the text of the two
commentaries without any retrieval or generation on them, decided by Erhan on 2026-11-21 (questions,
required and optional elements, expected statuses and reporting rules; he also ruled on the one
source conflict the verifier raised), checked by a fresh verifier agent that did not draft them,
and frozen the same day, before this comparison. They are not called held-out or blind: the
drafter knew D1's retrieval ranks, and E1 reuses D1's evidence passage. Three local files, never
committed: the runner input (each case's ID, question and editions, the only file `run` reads), the
private gold evidence and the private rubric. The
[freeze record](results/2026-11-21-phase3-E-freeze.json) holds their SHA-256 and each question's
SHA-256 as every reservation of its cells records it, so the books of a later run can be matched
to the frozen set. Scoring rules: required claims are scored and optional material never is; the
required-evidence denominator holds the supports of the required claims only, so Evidence Recall is
N/A for a case without them; check terms are aids, never a verdict; section anchors are
checked by a person, since coverage matches edition, page and quote. Reporting: E1 apart from E2 to
E6 (D1 overlap); for E4 and E5, single-edition January questions, B receives 10 of the January
commentary's 11 passages; E2's edition filter keeps January out of every condition, so E2 does not
test edition selection.

**Live run and blinded review (2026-11-21, ratings confirmed 2026-11-22):** the run matched the
plan's order and bounds; the estimate (about 6.29) was above the calculated USD 4.569196. Every C
cell searched once, after its first call, and that search filled the ten-passage budget, so no C
cell made a third call. The review packet showed each answer under a neutral ID with the frozen
rubric and the text of the passages it cites; how it was produced, counts, costs and timings
were withheld. Erhan's marks were transferred into a structured ratings file that reproduces his
completed packet line for line, the hashes were committed before the key was opened, and a local
script repeated every check (18 IDs once each, one answer per condition per case, under every ID
the status, claims with citations and named gaps of the cell the key names, each saved answer
hashing to the public record) before joining ratings and key. Results by case and condition, the
searches followed from passage to cited claim to covered rubric item, the cost reconciliation,
the limits and the recommendation are on the
[evidence page](../../docs/evidence/2026-11-21-phase3-E-comparison.md).

What the offline tests show (`test_evidence_agent.py`, `test_run_comparison.py`, mocked provider,
temporary books): A and B receive exactly the top 5 and top 10 of one ranking in rank order (rank 11
excluded) as the Phase 2 request with no tool; C starts from A's request and keeps its bounds (its
search returned ranks 6 to 10, which filled the passage budget, so its last call offered no tool);
all cells write one active ledger under one pin, each admission counting the cells before it; a
repeated run, under any tag or through the one-question runner, sends nothing again, and a
stopped matrix resumes without sending its cells again; the recorded books refuse D1 under the
agent and admit its other conditions; every reservation records its question and editions, a case
booked with another is refused under any condition, and the comparison refuses, before the model
loads, a case whose booked cells were asked another question, cover other editions or recorded no
question; damaged books
(a settlement under another condition, an unknown condition, a second call of a one-call
condition, a call ID without its condition, malformed question fields, a reservation with a
condition that does not record its question and editions) are refused; scoring fields
in the input are refused and no reference text of a dev case reaches any request or output; a
matrix whose worst case does not fit, or a case that cannot be ranked, is refused before anything
is sent, and a booking by another invocation that leaves the rest of the matrix no room stops it
before the next cell sends anything; the stop rule and the exit precedence are pinned (a cost above its reservation, a failed
write, a refusal by the books and a call kept at its reservation stop the matrix, an unanswered
cell does not; a stopped cell's 5, 6 or 3 ranks before an unanswered cell's 4, a failed output
write's 7 before a stopped cell's 5 or 6, and skipped cells never mask cells that ran; 5 and 6
cannot meet among cells, since the matrix stops at the first); an unexpected error
keeps the outputs of the cells before it; estimates count only cells whose every call was priced
from usage. They do not show real model behaviour, real token counts or costs, or which condition
answers better.

## Tracing one synthetic run in a local Phoenix

`trace_demo.py` shows one search decision of the evidence-seeking agent and its elapsed time in a
local Arize Phoenix, without a key, a provider call or any cost.

- **Run:** one synthetic question passes through the real loop. The pilot's client talks to a
  scripted provider behind `httpx.MockTransport`: call 1 asks for one `search_commentary` call and
  call 2 answers. The real search ranks the synthetic corpus of `test_evidence_search`.
- **Spans:** a transport wrapper and a search wrapper (both outside the loop's modules) record four
  OpenTelemetry spans. The case span carries outcome, calls and searches; each generation call
  carries its decision (`search` or `answer`), stop reason and mocked token counts; the search span
  carries its requested limit and new passage count. Every span carries `elapsed_ms`; the 400 ms per
  call and 50 ms per query embedding in it are declared synthetic delays.
- **What they omit:** no question, passage, query or answer text, and no `llm.model_name` or
  `llm.token_count` attribute, so Phoenix derives no cost. The ledgers remain the only spending
  record. The books are a temporary copy of the pinned Phase 2 ledger, deleted after the run, and
  the spans are exported only when no span carries a run text.

Start Phoenix 20.26 (here the one installed with the CAS harness) and run the demo from the
repository root:

```bash
PHOENIX_PYTHON=<python of a Phoenix 20.26 installation> tools/commentary_rag/phoenix_serve.sh &
UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" env -u ANTHROPIC_API_KEY \
    uv run --project services/ingestion --frozen --extra ai --extra dev \
    --with opentelemetry-sdk --with opentelemetry-exporter-otlp-proto-http \
    python tools/commentary_rag/trace_demo.py
```

The `--with` packages form an ephemeral overlay: `uv.lock` and the pilot venv stay unchanged, and
the pilot tests never import the file. The UI is http://127.0.0.1:6016 (project
`tarifhub-evidence-agent`); the spans read back with `GET /v1/projects` and
`GET /v1/projects/tarifhub-evidence-agent/spans?trace_id=<id>`.

## Limitations

- Two short documents: 40 passages in the corrected run (29 July, 11 January; 47 in the
  baseline). With so few candidates a random ranking already reaches an expected Evidence
  Recall@5 of 0.259 with the edition filter (0.219 for the baseline corpus).
- Eight dev cases, written by an AI and reviewed by one person (Erhan, not blinded, 2026-11-15); no
  held-out test. The corrected run is a development-set-informed correction, not validation.
- The Phase 3 comparison is six frozen cases (E1 overlapping D1), one run per case and condition,
  one reviewer who also decided the cases, partially blinded (answers shown verbatim); on the
  January-only cases B sees 10 of 11 January passages. Its differences are observations on these
  cases, not estimates for other questions.
- Table detection is specific to the commentaries' position tables (a code line and a value
  line per row, introduced by a line ending in ':'); it takes the first row's description to be
  one line. The only table in the corpus fits the budget whole, so the split-table context is
  exercised by the tests only.
- Sections come from numbered headings. A heading's continuation lines are not in the section
  title, and footnotes join the last section on their page: the footnote list of HDS positions
  belonging to section 2.3 of the July commentary appears as three section 2.4 passages on p. 4.
  A page without a printed footer would get no page label (both documents have one on every
  content page). Measured on 2026-11-22 with the layout probe: 13 of the 29 July passages carry a
  section title cut to the heading's first line (2.1, 2.2, 2.3, 2.5; the words stay in the passage
  text), the 132 position codes of footnote 1 (section 2.3) sit in `p4/s2.4/3` to `/5`, and
  footnotes 2 to 4 land in the last passage of their page instead of the one that references them.
  Both commentaries are tagged PDFs; a fix would be a new corpus version, not an edit of the frozen
  one.
- Sentences are split by a German heuristic with an abbreviation list.
- The term check for a required claim works at answer level: its terms may stand in one claim and
  the covering citation in another. Claim-level support is the human review's judgement.
- `pdftotext` artefacts stay in the text: inline footnote numbers, hyphens dropped at line breaks
  (`NeugeborenenScreening`), table cells flattened into one line.
- BM25 has no stemming or decompounding, and its statistics are computed per edition selection,
  so filtered and unfiltered BM25 orders can differ within an edition (and so can hybrid).
- e5 ran on Apple MPS. Two baseline runs on the same machine were identical, and so were the
  corrected run and its pre-generation rerun; other machines and devices are untested.
- The tool reuses two private helpers of the ingestion manifest module (`_load`, `_verify`), the
  embedder's private prefix helper (`_e5_input`) and its model handle (`_model`, for the
  tokenizer). A change there breaks these tests or the run, never the services.
