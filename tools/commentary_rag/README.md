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

**Seeking missing evidence (UC2), offline increments (2026-11-15 and 16):** `evidence_search.py`
is the commentary search of the evidence-seeking agent (ADR-026, proposed), one read-only search
whose bounds are code; `evidence_agent.py` is the agent's loop for one question, with per-call
spending protection. Both are tested offline only, the loop against a mocked provider with
temporary ledgers. **The loop is not ready for live use:** there is no runner and no command,
it has never called the provider, and the provider contract (the request shape and the usage
it reports) is unverified; its deadline is cooperative, not a hard limit. Its books: USD 100 is
one aggregate limit for Phase 2 and Phase 3 together; `results/generation-ledger.jsonl` stays
byte-identical and counts with all it committed (USD 1.930804, SHA-256
`e0d031ac4b648f5cd1e086c85ae55c3778254b1b70afcc5a9be461a8a4cf5caa`), and all later spending goes
to one active ledger beside it, `phase3-ledger.jsonl`, which no run has written yet. The hash
is pinned in the agent's code, not chosen by a caller. The comparison with fixed top-5 and
top-10 contexts is planned, not built: those conditions do not yet use the shared accounting
path, and the Phase 2 runner must not be used during Phase 3 to bypass it. Nothing above
changed.

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
- `conftest.py`: stops the suite with a message when the `anthropic` client or `pdftotext` is
  missing, so no test is skipped for a missing dependency.
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
  agent loop below calls it, and only against a mocked provider so far.
- `test_evidence_search.py`: offline tests of the search on a synthetic two-edition corpus with
  hand-worked rankings, the real retriever and a stand-in e5 embedder.
- `evidence_agent.py`: the evidence-seeking agent's loop for one question, **not ready for live
  use** (no runner, provider contract unverified). `run_case(task, *, client, retriever,
  passages, clock, budget_s, spending)` takes an `AgentTask` (case ID, question, selected
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
  `artifacts/requests/<case>-call<n>.json`, reserved at its ceiling and only then sent (a request
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
  settlement must match the cost of its saved usage and a call ID its case. A late
  or invalid response is settled and still not accepted. One monotonic deadline per question,
  checked before each count, after the count and reservation just before sending, after each
  generation call and after each search, and bounding every request's timeout; cooperative,
  since a check cannot interrupt a request or a search already running. The record and the
  ledger hold IDs, codes, counts, hashes, usage counts and amounts; requests, responses, search
  arguments and errors are local.
- `test_evidence_agent.py`: offline tests of the loop with the real `anthropic` client on a
  mocked HTTP transport, a fake key, the real search, a stand-in monotonic clock and temporary
  ledgers and artifact folders; two tests read byte copies of the recorded Phase 2 ledger, one
  of them altered.
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
- `local/` (git-ignored): contexts with passage text (`2026-11-14-contexts.json`), raw requests
  and responses and the run result (`2026-11-15-generation/`), the human-review sheet as generated
  (`2026-11-15-review-sheet.md`, ratings empty, kept unchanged), Erhan's approved review
  (`TarifHub_RAG_Bewertung_Erhan_2026-11-15.md`) and its structured transfer with every rating,
  excerpt and the input hashes it was checked against (`2026-11-15-human-review.json`).

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

Offline tests, all 208 (no model, no key, no network): poppler's `pdftotext` and the ingestion
`ai` extra (the locked `anthropic` client) are required, and the suite refuses to start without
them. A separate environment keeps the `ai` extra out of the ingestion venv (CI runs the same
suite in its own `commentary-rag` job):

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

## Limitations

- Two short documents: 40 passages in the corrected run (29 July, 11 January; 47 in the
  baseline). With so few candidates a random ranking already reaches an expected Evidence
  Recall@5 of 0.259 with the edition filter (0.219 for the baseline corpus).
- Eight dev cases, written by an AI and reviewed by one person (Erhan, not blinded, 2026-11-15); no
  held-out test. The corrected run is a development-set-informed correction, not validation.
- Table detection is specific to the commentaries' position tables (a code line and a value
  line per row, introduced by a line ending in ':'); it takes the first row's description to be
  one line. The only table in the corpus fits the budget whole, so the split-table context is
  exercised by the tests only.
- Sections come from numbered headings. A heading's continuation lines are not in the section
  title, and footnotes join the last section on their page: the footnote list of HDS positions
  belonging to section 2.3 of the July commentary appears as three section 2.4 passages on p. 4.
  A page without a printed footer would get no page label (both documents have one on every
  content page).
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
