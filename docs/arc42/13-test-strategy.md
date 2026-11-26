# Test Strategy

How tarifhub is tested, as actually implemented. The strategy serves one architectural
promise above all: no AI computes or mutates a billing value at serve time, and a
served value is provably the value that was reviewed and frozen. The tests are therefore
arranged as a pyramid whose apex is an architectural AST guard rather than an end-to-end UI test,
and whose foundation is an offline-by-default contract suite that needs no network, no
container and no API key. The per-use-case acceptance criteria these tests satisfy are in
[§10](10-quality-requirements.md#acceptance-criteria).

## The test pyramid

From the broad, fast base to the narrow, high-leverage apex:

1. **Unit / mapping helpers.** Pure functions, namely `freeze` (hash over sorted canonical
   content), the deterministic `map_raw`, validators, the confidence scorer and the
   canonical-Decimal scale normalisation, are tested in isolation with fixed inputs.
   No I/O, no clock branching, no randomness. The pipeline is a pure function of sorted
   inputs by design ([§6](06-runtime-view.md)).
2. **API contract (offline).** The serving REST surface is exercised through FastAPI's
   `TestClient` against a temp SQLite database seeded with frozen records
   (`services/serving/tests/test_api.py`, `conftest.py`): health, latest-version list,
   system filter, pagination edges, 404 on unknown keys, input-validation 422s, and the
   search ranking and dimension-guard paths. The client reads the seeded DB via `TARIFHUB_DB_URL`,
   the same env-only config production uses. Error responses are themselves a tested contract:
   `services/serving/tests/test_errors.py` (6 tests) pins the centralised RFC 7807
   `application/problem+json` layer ([ADR-019](../adr/019-rfc7807-error-handling.md)), asserting a
   domain `TariffNotFound` renders a 404 problem document, a `RequestValidationError` a 422 with
   field-level detail, an unexpected error a structured 500 that carries a correlation id and leaks
   no stack trace or internal string (and honours an inbound `X-Request-ID`), and that a successful
   call stays plain `application/json` with no correlation header.
3. **Cross-engine read parity.** Every read endpoint is run against **both** SQLite and
   Postgres via the `engine` fixture, and each test asserts the endpoint's **full JSON
   body** equals an engine-independent expected snapshot
   (`services/serving/tests/test_read_parity.py`, mirrored for ingestion). Because both
   engines must match the *same* snapshot, they match each other, so an engine-specific bug that only SQLite would tolerate can no longer pass silently. This layer exists because two Postgres-vs-SQLite drift defects surfaced in Block-0 (a JSONB dict crashed `json.loads`, and an `int` for a BOOLEAN
   column was rejected by psycopg), so the snapshots deliberately stress non-ASCII
   designations (umlauts, accented Latin letters, cedillas), nested metadata dicts, `requires_review` booleans,
   trailing-zero Decimals at the exact `NUMERIC` scale, dates, multi-version keys and
   pagination windows.
4. **MCP proxy contract.** The MCP tools (`get_tariff`, `search_tariffs`,
   `explain_record`) are tested with the serving backend mocked via
   `httpx.MockTransport` (`services/mcp/tests/test_tools.py`): each tool returns the
   backend JSON **verbatim**, forwards the right path and query params, and a backend 404
   raises `httpx.HTTPStatusError` rather than fabricating a record. **MCP↔serving
   integration tests** (`services/mcp/tests/test_integration.py`) additionally drive the
   real serving ASGI app in-process via `httpx.ASGITransport`: each tool is proven against
   real responses under the same offline doctrine (SQLite mirror, stub embedder), no
   socket.
5. **Architectural AST boundary test (the apex).** A static AST scan asserts no LLM client
   is importable on the value path. This is the mechanical enforcement of the value-path invariant
   and is described as its own gate below.

## Offline by default

`uv run pytest -q` in any service runs **fully offline**: a **SQLite mirror** of the
canonical Postgres schema stands in for the database, and a deterministic **16-dim
`HashingEmbedder` stub** stands in for multilingual-e5, with **zero network, no containers,
no `ANTHROPIC_API_KEY`**. Without an API key the AI seam (`ai_map`) falls back to
deterministic `map_raw`, and the offline tests rely on exactly that fallback. Semantic
search stays fully testable offline: on SQLite the serving layer ranks by an in-process
deterministic cosine over the stored stub embeddings (same query path, same response
shape as pgvector, ties broken by `(tariff_system, tariff_code)`), so the offline suite
exercises real ranked results without pgvector. The dimension-guard still applies on
Postgres: an embedder whose dimension does not match the `vector(1024)` column makes
search **fail closed with HTTP 501** rather than issue a doomed query, an honest
unavailability and never a faked result.

## Postgres opt-in parity harness

The real engine is opt-in. Setting `TARIFHUB_PG_TEST_URL` adds a `postgres` parameter to
the `engine` fixture. Its setup connects to that server **only** to `CREATE` a
uniquely-named scratch database (`tarifhub_parity_<uuid>`), applies `db/schema.sql` into
it, yields it to the test, and **drops it on teardown**, so the shared dev `tarifhub`
database is never written to. This is our **purpose-built equivalent of Testcontainers**,
a per-run, throwaway, schema-provisioned database with deterministic teardown, built
directly on `psycopg` and `db/schema.sql`. **We do not use Testcontainers**. The harness
is hand-rolled to keep the offline default container-free and the dependency surface
minimal. In CI the `python-parity` job supplies the URL via a `pgvector/pgvector:pg16`
service container, so the identical read tests run against a real Postgres 16 + pgvector
on every push and PR.

## The determinism acceptance gate (AST boundary test)

The architectural guard is the apex test and the determinism acceptance from
[§10](10-quality-requirements.md#acceptance-criteria). It parses each value-path module's
AST and asserts that none imports `anthropic`, `openai`, `cohere`, `langchain` or
`llama_index`, at module level **or** inside a function:

- `services/serving/tests/test_serving_boundary.py` scans the **entire** `tarifhub_serving`
  package, and additionally asserts the only `tarifhub_ingest` submodules it imports are
  `models` and `embeddings`, never a mapper that could transitively pull an LLM client.
  (It is named `test_serving_boundary`, not `test_determinism_boundary`, because the latter
  filename is frozen by the `guard_frozen` hook.)
- `services/ingestion/tests/test_determinism_boundary.py` scans the ingestion value path
  (`main.py`, `storage/db.py`, `storage/tariff_repository.py`).
- `services/intelligence/tests/test_determinism_boundary.py` scans the TarifIQ rule-
  evaluation path (`main.py`, rules, crosswalk, validators, store).
- `services/ingestion/tests/test_review_boundary.py` extends the same AST guard to the
  human-in-the-loop review write-back path (`review.py` and the review routes in `main.py`),
  so the one write seam that AI-flagged fills pass through before a human freezes them also
  cannot import a model client.

All four run in the offline suite and in CI's per-service test loop on every push. The
ingestion `test_determinism_boundary.py` and serving `test_serving_boundary.py` value-path
suites additionally run **again, visibly**, as a dedicated CI step that prints them with `-v`.
CI fails if any LLM client appears on a value path. Because
the guarantee is structural (the import graph cannot reach a model), the boundary stays
green by construction, not by reviewer discipline.

## Tests of the AI components

The CAS rubric asks that the test strategy **account for the tests of the AI components**: that
the AI components are themselves tested, not just
the deterministic majority. tarifhub's AI
portion is small and sharply bounded: a single fill-only seam (`ai_map`, ADR-005) that may
only add missing non-billing designations pre-freeze, plus an embeddings-based ranking path
for search. Its tests therefore fall into six families: a **guardrail** test of the
boundary itself, **no-call** tests of the gap gate, **non-deterministic-output handling**
tests of fill-reuse, **fail-closed parsing** tests of the schema validation that treats
model output as untrusted, a **human-in-the-loop write-back** family that pins the review
queue where flagged AI fills are approved or corrected before a human freezes them, and a
**demonstration** family that exercises the real Claude structured-output contract and the real
multilingual-e5 ranking, so the intelligent behaviour is shown directly and not only mocked away. Outside the services, the commentary RAG pilot ([ADR-025](../adr/025-commentary-retrieval.md)) has its own offline suite, the seventh family below.

### 1 · Guardrail: the boundary itself

The AST boundary tests are described in full above (*The determinism acceptance gate*):
`services/serving/tests/test_serving_boundary.py`,
`services/ingestion/tests/test_determinism_boundary.py` and
`services/intelligence/tests/test_determinism_boundary.py`. This is the test *of* the AI
boundary, the AI-portion test with the highest leverage, since a single failure proves a
model became reachable on a value path. Verifies **NFR-1** ([§10](10-quality-requirements.md)).

### 2 · Gap-gate: the no-call paths

`services/ingestion/tests/test_ai_mapper.py` proves the pipeline makes **zero** model calls
when there is nothing to fill or no key is present:
`test_gap_gate_skips_call_when_nothing_fillable`,
`test_gap_gate_invokes_call_when_a_gap_exists` and
`test_no_api_key_returns_deterministic_and_never_calls_parse`. The EAL live run (**0 API
calls over 1,279 complete rows**, [§10](10-quality-requirements.md)) is exactly this
behaviour observed at scale.

### 3 · Fill-reuse: handling non-deterministic AI output

Live model output is **not** byte-stable across runs (the measured 55 re-versions,
[§10](10-quality-requirements.md)). `services/ingestion/tests/test_fill_reuse.py` pins the
mechanism that makes the pipeline reproducible anyway:
`test_reuse_makes_zero_api_calls`, `test_keyless_reuse_still_skips`,
`test_changed_content_takes_normal_path`, `test_refill_bypasses_reuse` and
`test_audit_detail_carries_reuse_provenance`, with further byte-exactness legs in the same
suite (e.g. `test_strip_to_prefill_reverses_a_category_fill_byte_exactly`). Verifies
**NFR-2** ([§10](10-quality-requirements.md)).

### 4 · Schema-validation: fail-closed on untrusted model output

Model output is treated as untrusted input. `services/ingestion/tests/test_ai_mapper.py`
asserts that refusals, empty strings and parse failures all degrade to the deterministic
path: `test_fill_only_does_not_overwrite_existing`,
`test_empty_string_output_is_normalized_to_none`,
`test_refusal_or_none_output_is_error_path` and `test_parse_raises_falls_back_safely`.
`services/ingestion/tests/test_mapper.py`'s
`test_ai_map_offline_does_not_alter_billing_values` confirms billing fields are structurally
unreachable for the seam to touch.

### 5 · Human-in-the-loop write-back: the review queue that closes the loop

The fill-only seam is only safe because a human, not the model, has the last word on every
flagged record, and that write-back is now built and tested.
`services/ingestion/tests/test_review_api.py` (11 tests) drives the ingestion review endpoints
(`GET /review/queue`, `POST /review`) end to end against the seeded database: the queue returns
only flagged records, an **approve** freezes a new immutable version, a non-billing **correct**
applies and leaves the queue, and every illegitimate decision is refused with the right status
(`test_correct_billing_field_is_rejected` and `test_correct_unknown_field_is_rejected` give a
`400`, `test_review_stale_record_hash_is_409` and `test_review_unflagged_record_is_409` a `409`,
`test_review_unknown_record_is_404` a `404`, and `test_correct_emptying_de_fails_validation_422`
and `test_correct_oversized_value_is_rejected_422` a `422`). The write-back runs the *same*
deterministic pipeline as ingest (validate → freeze → new immutable version → append-only
`audit_log`), so a reviewed value is provably the value that was frozen and the prior version is
never rewritten. `services/ingestion/tests/test_review_contract.py` (5 tests) asserts the review
models expose exactly the keys the console consumes, and the matching console BFF proxy is covered
by `apps/tarifguard/tests/unit/review-route.test.ts` (6 cases, including the same billing-field
guard enforced before any proxy call). The path's own AST guard,
`services/ingestion/tests/test_review_boundary.py`, is listed with the boundary tests above. These
pin the **UC-02** review acceptance ([§10](10-quality-requirements.md#acceptance-criteria)).

### 6 · Demonstration: the real intelligent behaviour, shown not only mocked away

Families 1 to 5 prove the *guardrails*, and they do so on the offline defaults: without a key
`ai_map` falls back to deterministic `map_raw`, and search ranks on the 16-dim `HashingEmbedder`
stub, so none of them invokes the real Claude or e5 models. Two tests close that honest gap and
demonstrate the intelligent behaviour itself in CI, still with no live key and no model download:

- **The real Claude structured-output call.** `services/ingestion/tests/test_ai_mapper.py`'s
  `test_structured_output_call_and_fill_only_merge` mocks the `anthropic` client (injected via
  `sys.modules`, so no key and no network) and asserts the seam makes exactly the live call: a single
  `client.messages.parse` with `output_format=AIRefinement`, `max_tokens=1024`, the fill-only system
  prompt, and a user payload that carries no billing field, after which the merge fills only
  `designation_fr` / `designation_it` / `category` while every billing value and the record hash stay
  byte-identical to `map_raw`. The mock stands in for the network, but the asserted contract is exactly
  the one the opt-in `ai` extra exercises live.
- **The real multilingual-e5 ranking.** `services/serving/tests/test_e5_ranking.py` ranks REAL
  `intfloat/multilingual-e5-large` query and passage vectors through the production ranker
  (`ServingRepository.search_offline` over a seeded offline mirror, plus a direct `_cosine_similarity`
  margin check) and asserts that the French query *hématocrite* ranks the German record EAL 1375
  (*Hämatokrit, zentrifugiert*) top-1 within this curated seven-record set, the cross-lingual match the
  16-dim stub does not make (the test pins both sides). The set deliberately excludes the near-duplicate
  haematogram panel 1372.01: the full 1279-record eval ranks 1375 *second* behind that panel, whose own
  text also contains *Hämatokrit*, so the fixture isolates the cross-lingual designation match rather than
  the full-corpus result. The vectors were recorded once from the cached model by
  `services/serving/tests/fixtures/record_e5_fr_ranking.py` and committed, so the real semantic search is
  demonstrated deterministically with no 2 GB download in CI. The full FR-ranking eval is recorded at
  [evidence/2026-06-11-fr-ranking-eval.md](../evidence/2026-06-11-fr-ranking-eval.md).
  Alongside that curated seven-record top-1 demonstration, `services/serving/tests/test_search_eval_metrics.py`
  recomputes the full headline metrics, recall@5 and MRR@5 for both prefix runs (passage 0.833 / 0.681,
  query 0.917 / 0.597), from a committed full-corpus real-e5 fixture
  (`services/serving/tests/fixtures/e5_eval_corpus.json`, all 1 279 EAL passages plus the 12 queries in
  both prefixes, recorded by `fixtures/record_e5_eval_corpus.py` whose self-check refuses to write on any
  mismatch), so a regression in the recorded vectors or the documented figures fails the offline suite and CI.

All six families run in the **offline default suite** (no key, no network) and again in CI on every
push. Families 1 to 5 test the guardrails without ever needing the AI. Family 6 demonstrates the real
Claude call shape and the real e5 ranking, using a mocked client and recorded vectors, so the intelligent
behaviour is exercised in CI without a live key or a model download.

### 7 · The commentary pilot: offline, at the provider's HTTP boundary

`tools/commentary_rag/` (outside the services, [§5](05-building-block-view.md#outside-the-services-the-commentary-rag-pilot)) has 732 offline tests in fifteen files, run with the ingestion lockfile's `ai` and `dev` extras (the `dev` extra brings pytest-socket) and poppler's `pdftotext`:

- **Corpus (42):** tiny real PDFs written per test go through the manifest loader, the hash check and `pdftotext`: provenance per passage, page-bounded splitting, tables, headings, and refusal of a missing or altered document or a wrong printed page number. The commentary-source manifest of `build_commentaries`: two sources of one date keep their own IDs, a source covering two dates is one document, and a manifest that breaks the schema, repeats a key, ID, path or hash, sits outside `data/manifests/`, points outside the repository, fails its hash or declares a title that is not on page 1 is refused, every problem listed at once.
- **Retrieval (3) and metrics (8):** a hand-computed BM25 score, RRF as defined, an edition selection that never returns another edition's passage, the metric definitions on worked examples, recomputation of both committed retrieval records from their stored rankings, and refusal to overwrite a record.
- **Generation (14):** the real `anthropic` client talks to an `httpx.MockTransport`, with no key and no network. Each request carries only its own question and passages and none of the scoring fields, sends no tools, fallback or sampling parameters and is counted before it is sent; schema violations, cut-off answers and out-of-context citations are kept as reported; one HTTP call per attempt; a timeout is charged at its reservation; access, model and configuration blockers stop the run; a request whose ceiling would pass the budget is never sent; a valid answer is never requested again; a second run on the same ledger is refused while one is sending; a valid answer is settled only after its response is saved; provider errors are redacted of key and workspace identifiers.
- **Answer checks (3) and steps (22):** the check denominators keep retrieval misses, generation failures, unattempted cases and abstention apart; every step refuses to overwrite an output an earlier run wrote; `run` refuses contexts that differ from the saved record in any field the request carries; `report` refuses a response whose hash differs from its ledger entry and covers only its own run's attempts, including one settled before an interruption; a `run` refused by another run's lock publishes nothing.
- **Commentary search (28):** the agent's one tool ([ADR-026](../adr/026-commentary-evidence-search.md)) over the real retriever, with a stand-in for the e5 model that logs every query it embeds, on a synthetic two-edition corpus whose rankings are worked out by hand: a search returns the best passages not yet supplied from the question's selected editions only, with provenance and rank, and without an edition argument ranks every selected edition; an empty or unselected edition selection, malformed arguments, a repeated search and a full passage budget are refused without ranking and use their round; a window of supplied passages reports no new passages; a failed ranking is a tool error that uses its round; no search runs after two rounds, refused and failed ones included; markup and instruction-like passage text return escaped; raw query and seeking text stay out of the publishable record; a passage recorded for an unselected edition never reaches the model. These tests show the tool's bounds, not how a model uses them.
- **Agent loop (156):** one question through `evidence_agent.run_case` with the real `anthropic` client on an `httpx.MockTransport`, a fake key, the real commentary search over the same synthetic corpus, a stand-in monotonic clock that the provider and e5 stand-ins advance, and temporary ledgers and artifact folders. A search request is run and the answer citing a new passage accepted, the second request appending the whole assistant turn and the tool result for its ID to an unchanged history with the same system prompt and tool; an immediate answer, including a legitimate `insufficient_evidence`; two rounds and then a call with `tool_choice` none; refused and failed searches returned as error results; an unknown tool, two tool calls, a tool call while `tool_choice` was none, a call without an ID, a cut-off or declined response, all stopped without running a search; answers off schema or citing a passage never supplied (from the corpus or from a search window) rejected; the deadline passed before or during a count, a generation call or a search, with nothing counted, sent, searched or accepted afterwards; request timeouts bounded by the time left; provider errors and unreadable counts or responses ending the case once, without retry, apart from a deadline, even with a client configured to retry; raw text kept out of the record; nothing case-specific in the instruction or the tool; initial passages outside the question or its budget refused before any request. Spending, with hand-worked amounts: every call reserved at its ceiling before it is sent and settled once from its usage beside a historical ledger with an open reservation, its request and response saved under hashes the ledger names; admission at exactly the limit and refusal a micro-dollar over it, at a worst case that includes the US multiplier, also with the worst case of a comparison's cells still to run held back beside it (a matrix rest that is not a finite amount refused); the dearest usage the settlement prices within the margin covered by its reservation and one token more above it; three calls of a question admitted at the limit each reserved and settled once, after which the next question is refused; a request over the 80,000-token input cap neither reserved nor sent; late, invalid and protocol-violating responses settled at their usage cost and still rejected; timeouts, lost connections, error responses and usage that cannot be priced kept at the whole reservation; a cost above the reservation recorded in full and no further call; a reservation the deadline overtakes recorded as never sent; failed writes before and after sending (the baseline pin, the request, the reservation, a release, the response and the settlement, the ledger failures simulated at file opening so that they fail the same way for any user), with nothing sent after a failed prerequisite, a sent or unreleased call kept reserved and no settlement or release claimed that the ledger does not hold; a concurrent invocation refused by the lock, also when it reaches the active ledger through a link from another folder, and a repeated one refused without sending or counting again; damaged, unreadable, emptied or changed books, settlements that contradict their basis or the cost of their saved usage, and call IDs that do not name their case refused as they are; books in another folder, a second ledger file, a raised limit and a lowered margin refused before anything is counted; altered historical bytes refused before any count, whether the caller vouches for them with their own hash or gives the recorded one; provider text kept out of the record and the ledger; a byte copy of the recorded Phase 2 ledger read as the baseline, USD 1.930804. The comparison conditions (31 of them): a fixed condition sends exactly the Phase 2 request once, with no tools or tool choice, under its own call ID and admitted at one call's ceiling, and runs no search a model asks for; conditions of one question share the books, each counting the cells before it, and each runs once; byte copies of both recorded ledgers refuse D1 under the agent and admit it under `fixed5` and `fixed10` at USD 7.060552 committed, pinning the active ledger as the comparison of 2026-11-21 left it (53 lines) and its first five lines as they stood before that run; case IDs that end like a condition still name cells of their own, and a call ID an older reservation holds is never written twice; a condition takes no more initial passages than its bound and an unknown condition is refused before any request; books whose conditions contradict their calls, whose question fields are malformed, that carry a question on an entry without a condition or that lack it on an entry with one are refused as damaged; every reservation records the question's hash and the sorted editions, a case booked with another question or editions is refused under any condition, and a case booked before questions were recorded passes the books. They do not show how a real model behaves, real token counts, prices or usage fields, or that the deadline is a hard limit (it is cooperative).
- **Coverage decision, condition D (52):** condition D ([ADR-027](../adr/027-coverage-decision.md)) through the same loop and fixtures: its instruction, tool, answer format and refusal texts equal the SHA-256 values frozen in `phase4/conditions.md` before the code; B's and C's requests equal the hashes taken on the code before D (C's record gains no field); a direct answer is accepted as the inner answer object with its coverage recorded; a valid search runs on C's arguments only; a coverage naming a passage not received, a search for a covered part, a `search_for` that is no integer naming a part, and malformed coverage (no part, five parts, a covered part without passages, a missing part with one, blank or over-long parts, unknown status or keys, non-string IDs) are refused as tool errors that use the round, nothing ranked, the tool still offered by capacity; a justified gap is accepted and an unreported missing part only flagged; no new evidence twice ends in an answer on the last call; a full passage budget offers no tool whatever D recorded; an invalid reference in an answer's coverage is recorded, not rejected; an answer without an answer object, off schema or citing a passage not supplied is rejected exactly as C's; D and C of one case are two cells in one set of books; D's coverage and `search_for` lead its tool's input schema; the flag for an unreported missing part needs an empty `missing_evidence` list, not an absent or invalid one; an integer past the interpreter's digit limit in the coverage leaves a valid answer accepted (the coverage malformed). Since 2026-11-26 D runs in Phase 4's own books under repetition 1 ([ADR-028](../adr/028-phase4-books.md)): D is refused in the Phase 2 and 3 books before anything is counted, and so is any condition for a frozen Phase 4 case, by its ID or its question, while Phase 4's books take a frozen case under its frozen ID, question and editions only; the first Phase 4 cell pins the books' time budget, and a cell with another budget or a non-finite one is refused; another repetition, a fixed5 cell, the Phase 2 and 3 books with a repetition and Phase 4's books without one are refused before any request; Phase 4 books that name another repetition or condition, a call ID without the repetition, a Phase 3 pin or another limit are refused as they are, and the Phase 2 and 3 books refuse a D cell or a repetition as damage; B and C send their pinned requests in Phase 4's books too, and a Phase 4 booking leaves the Phase 2 and 3 books as they are; D called on its own for a fresh case holds back B's and C's cells not yet booked (an exact fit admitted, one micro-dollar short refused); C and D fail alike when a tool input carries a lone surrogate the model escaped, their first call settled, nothing more reserved and the cell never sent again. They do not show how a real model fills the coverage.
- **Comparison runner (67):** the comparison's command (`run_comparison.py`) over a tiny real corpus whose twelve-passage July ranking is worked out by hand, with the real retriever, loop and `anthropic` client on an `httpx.MockTransport` and temporary books. `plan` lays out the matrix, its bounds, the admission headroom and labelled estimates and loads, sends and writes nothing; `run` gives A and B the top 5 and top 10 of one ranking in rank order (rank 11 excluded) as the Phase 2 request with no tool, and C A's first message with its tool and bounds, its search returning ranks 6 to 10; every cell is booked once in one ledger, each admission counting the cells before it; a repeated run, under any tag, and an agent cell the one-question runner booked are never sent again; a cases file carrying any scoring field is refused before it is used, and no reference text of a dev case reaches any request or output; a matrix whose worst case does not fit is refused before the model loads, one admitted at exactly the limit runs every cell, a cell already in the books stays out of the rest a resumed matrix holds back, and a booking by another invocation that leaves the rest of the matrix no room stops it before the next cell sends; a call ID another case holds stops the matrix rather than being skipped; a cell kept at its reservation stops the matrix, and so do a cost above a reservation, a failed write and a refusal by the books, while an unanswered cell does not; the exit code puts 5, 6 and 3 before 4 and a failed output write's 7 before a stopped cell's 5 or 6, and a cell already in the books never masks the cells that ran; a stopped matrix resumes without resending its cells; a case whose booked cells were asked another question, cover other editions or recorded none is refused before the model loads; every case is ranked before any cell is sent; an unexpected error keeps the outputs of the cells before it; estimates count only cells whose every call was priced from usage; damaged books in `plan`, an edition the corpus lacks and existing outputs are refused; a cases file nested too deep to parse is invalid input, and unknown field names are shown escaped, never their values. Since 2026-11-25 the Phase 4 design, since 2026-11-26 in Phase 4's own books: the default design is unchanged (its plan equals an explicit `--design phase3`); the triplet ceiling of USD 10.3488 is derived from the pinned configuration and prices, and the pinned runner input is the freeze record's; the Phase 4 plan lays out B, C and D with their bounds and admits case by case beside those books; plan and run refuse any cases file but the frozen runner input (a subset or another order); a case that fits exactly runs and the next that no longer fits stops the run before anything of it is counted or sent; a next case one micro-dollar short is refused before the model loads; an interrupted run resumes in the frozen order without sending a cell twice, its interrupted call kept open and its case incomplete; a call released before sending stays never sent and is never sent later; a concurrent invocation is refused by the lock and sends or books nothing, and two invocations interleaving between cells book and send every cell once; one Phase 4 case gives B, C and D their passages and publishes no passage ID while its local record keeps the ranking with its scores; a local output folder that is a symbolic link is refused before the model loads; a replay failure shared by C and D stops the run with its calls settled, and a rerun skips the cell; the default design refuses a frozen Phase 4 case, by its ID or its question, in `plan` and `run` before anything loads; a cell that booked nothing stops the run, so a rerun keeps the frozen order; a rerun with another time budget is refused before the model loads; a corpus whose PDFs are not the frozen ones is refused before anything is counted; a tag another invocation holds is refused and an unused claim given back; a linked request folder in the run folder is refused; the public record reports the Phase 4 cap; estimates read cells of every condition under either design. They do not show which condition answers better.
- **Phase 4 scorer (172):** `phase4_scoring.py` on synthetic records: the local records of one repetition merged by case and condition (a cell ran when a generation call was sent; two that ran are refused; a case is complete when B, C and D ran), each case's question, editions, ranking and records checked against the gold file and each other (C's and D's initial passages the top 5 of the ranking, B's the top 10), search records that contradict their outcome or round numbering refused, reserved calls never sent left out, cells of one repetition run with different time budgets refused, and D's coverage diagnostics counted apart from every measure; strata S1, S2, S3 and G, and mixed cases, from the top 10; decision points by capacity before each call (not by the tool choice sent, an anomaly when they disagree, and never from D's coverage record) with warranted, unnecessary, gap-check and missed useful searches, refused searches (missed at a search-needed point), points without action left out of the denominators, no new passages and a second decision point, a tool error, a full budget and the yield of a search; every boundary of T3 and T4 and every row of both outcome tables; R1 and R2 with empty and small groups; broken traces refused; T3 and T4 not assessable on an incomplete repetition; the command refuses an output anywhere in the repository except the git-ignored `local/` folder, an existing file and unreadable or mismatched inputs, and writes the same bytes twice. Since 2026-11-26: amendment A1 counts an executed search and a refused request at a no-search-needed point once each, by the same rule for C and D and over T3's own denominator, leaving gap checks, points without action and T4 as they were; T3, A1 and T4 come from one summary whose completeness is the scoring's own; A1 entries that do not add up are refused; records without a valid time budget (an integer past float range included) or an admitted repetition are refused, and one scoring holds one repetition; a repetition is complete only for the frozen cohort (the freeze record's case IDs, question hashes and editions), so a subset with its gold gives no verdict; a request refused for want of rounds before both rounds were used is refused; the command scores against the frozen gold file only and refuses a `local/` folder that is a symbolic link. They do not show how the measures come out on real runs.
- **One-question runner (48):** the runner's command driven end to end over a tiny real commentary corpus (generated PDFs and a manifest through the real corpus builder and `pdftotext`), the real retriever, the real agent loop and the real `anthropic` client on an `httpx.MockTransport` with a fake key; only the e5 model (a vector per text, word-count tokens) and the provider's HTTP side are stand-ins, with rankings worked out by hand. `prepare` ranks the question afresh in the selected editions and sends and writes nothing; `run` hands exactly that top 5 (with document titles) to one agent run, keeps the answer and full result locally and publishes metadata only; an answer naming its missing evidence (`insufficient_evidence`) is a successful run; a dev case's question brings none of its reference answer, gold evidence or rubric into any request or output; a case ID already in the books is refused under any new tag without a request or a file; existing outputs, or a file where the run's local folder goes, are refused before the model loads; malformed time budgets, questions, case IDs, tags and editions, an edition the corpus lacks and a question over the model's input are refused before anything is ranked or sent; the live step without a key is refused before the model loads, and help loads nothing; a call above its reservation (with an answer or before a search) and an answer whose usage cannot be priced never exit 0, the answer still kept locally; invalid answers, protocol errors, late answers and provider errors exit nonzero after one request; a public record that cannot be written and artifacts the agent cannot save exit as persistence failures without a second request; a question stopped before its first reservation writes nothing and can run again, while a reservation whose ledger write failed is reported as uncertain accounting and kept; an answer whose text UTF-8 cannot encode (a lone surrogate the model's JSON escaped) is kept and published without loss. Every test leaves the repository's `results/`, `local/` and ledgers byte-identical. An unavailable e5 model (its files missing, or the package missing so that the embedder falls back to the stub) is refused through the runner's real loader, the evaluation loader and the ingestion embedder, with only the `sentence_transformers` boundary replaced: offline mode is on before the model is asked for, and nothing is counted, sent, reserved or written. They do not show a successful load of the real model (only the runner's own steps with the cached model exercise it: `prepare` offline and the one live `run` on dev case D1), real provider behaviour or the live request shape.
- **Socket guard (3):** `conftest.py` turns pytest-socket on around every pilot test, Unix sockets excepted: creating an AF_INET socket and `socket.create_connection` to 127.0.0.1:9 raise `SocketBlockedError`, and a Unix socket stays available. They show that a pilot test cannot open a network socket through Python's `socket` module, not that a subprocess such as `pdftotext` or a C library cannot. The block is the pilot's own: the ingestion suite installs pytest-socket with its `dev` extra but never enables it, so its PostgreSQL legs keep their network access.
- **Training-data inventory (54):** the Phase 4 inventory (`training_inventory.py`) on synthetic passages and, end to end, on tiny generated PDFs: only explicit position codes count; the project names of the fixed list are found in their spellings and the AL handbook only in its sensitivity; series (`ff.`) and wildcards reach 2026 codes only in their sensitivity; sections link into families through shared codes or projects, transitively, and a section with neither stays alone; a family overlapping the 2026 material is dropped as a whole, while codes named only in a 2026 introduction exclude nothing; misfiled text keeps a passage only when it names no code or project, and misfiled text that is not in its passage is refused; exact and near duplicates are found, and a copy of 2026 text is never eligible, even in a family that stays; every inspection finding of a passage counts, and a passage with lost or garbled text is never usable; the report is deterministic; a 2026 rebuild that differs from the frozen record is refused; an existing record is never replaced; and without the cached e5 model the command refuses with offline mode on, attempting no download. The views of the older commentaries: a family eligible alone is dropped when older sections link it to the 2026 material, and the change is listed with its linking and excluding codes; the older view counts its own families by source ID; a finding applies only to the views holding its source and one whose passage is missing is refused; an unresolved source is left out of every count and listed; merging refuses repeated source or passage IDs and the same document under two source IDs; a source without passages must be listed as unresolved; eligibility changes are checked, not assumed, for the baseline and for the older view; printed subsections regroup a combined section, every subsection fragment decides a passage's family, a passage across two families is never eligible, a heading-only remainder decides nothing and a family whose only passage is split still counts; subsection text read as misfiled; the transAL2 spelling; and the four-document record keeps its form. They do not show that the rules fit the real commentaries; the page inspections do ([evidence](../evidence/2026-11-23-phase4-training-data-inventory.md), [older commentaries](../evidence/2026-11-23-phase4-older-commentaries-inventory.md)).
- **Sign-test power (60):** `sign_test_power.py` against an exact-fraction recomputation of the same sums: the feasibility assessment's 0.57 and 0.31, the exact p-values and rejection thresholds (5 discordant units can never reach 5 % two-sided, 6 of 6 can), outcome probabilities that sum to 1, one-sided power never below two-sided, the first and the stable unit count for a target, refusal of invalid inputs, a byte-identical report on a second run, and no existing report replaced.

They do not cover real model behaviour, real token counts or prices, the real e5 model (a stand-in embedder and tokenizer are used) or whether a cited passage supports a claim; those come from the recorded runs and the human review ([§10](10-quality-requirements.md#commentary-rag-pilot-recorded-evaluation)). For the agent, its one live run on dev case D1 ([evidence](../evidence/2026-11-20-phase3-d1-agent-run.md)) adds real token counts, usage fields and calculated costs for two calls and one search; whether its cited passages support its claims comes from Erhan's review of that one answer (confirmed 2026-11-21, on the same evidence page), not from the run. The suite refuses to start without the `anthropic` client, `pytest-socket` or `pdftotext`, so a missing dependency fails instead of skipping, and every test runs with pytest-socket's block on, so a test that tries to reach the network through Python's `socket` module fails instead of connecting.

## What CI runs per PR

From `.github/workflows/ci.yml`, on every push to `main` and every pull request:

| Job | What it does |
|---|---|
| `python` | Per service: `uv sync --frozen` → `uvx ruff check .` → `uv run pytest -q` (offline). A dedicated step re-runs the ingestion + serving boundary tests with `-v` so the determinism gate is visible in the log, and a coverage step gates ingestion, serving, mcp and intelligence at `--cov-fail-under=80`. |
| `python-parity` | Spins a `pgvector/pgvector:pg16` service container and runs the ingestion + serving read-parity suites against real Postgres 16 + pgvector (`TARIFHUB_PG_TEST_URL` set). |
| `commentary-rag` | The commentary pilot in its own runner, so the `ai` extra never enters the dev-only service environments: `uv sync --frozen --extra ai --extra dev` for ingestion, poppler, `ruff check` of `tools/commentary_rag` under the ingestion ruleset, the offline suite, and a junit check that fails on any skipped test or uncollected test file. No secret, no model download (`HF_HUB_OFFLINE=1`). |
| `console` | When `apps/tarifguard/package.json` exists: `npm ci` → `npm run lint` → `npm run build` → `npm run test --if-present`. |
| `security` | `gitleaks` (secrets) → `Trivy` (fs scan, fail on HIGH/CRITICAL) → `Syft` SBOM (`spdx-json`, uploaded as an artifact). |
| `docs` | `mkdocs build -f docs/mkdocs.yml --strict`: a broken link or nav entry fails the build. |
| `images` | On pull requests and on `main`, after `python` + `security`: checks each service's `uv.lock` against its `pyproject.toml` (`uv lock --check`), then builds every sub-system Docker image as distribution evidence, never pushed. The Python images install exactly what the lockfiles pin. |

Lockfiles are committed and CI never re-resolves (`UV_FROZEN=1`, owner decision).

## Coverage

Target: **core modules (model, freeze, pipeline, mapper) > 80 % line coverage**
([§10](10-quality-requirements.md)). Measured on the offline suite (`pytest-cov`, line
coverage) and re-measured and **gated** on every CI run in the `python` job's coverage step
(`--cov-fail-under=80`). Measured 2026-07-02 (intelligence added, measured 2026-07-03). The per-module figures and the residual misses are quoted and interpreted in
[§10 Test and pipeline results](10-quality-requirements.md#coverage-pytest-cov-line-coverage):

| Service | Core modules in scope | Measured |
|---|---|---|
| `services/serving` | `main` 92 %, `repository` 91 %, `errors` 99 %, `models` 100 % (also `fhir` 99 %, `explain` 100 %, `telemetry` 100 %; infrastructure: `db` 76 %) | **94 % total** |
| `services/ingestion` | `tariff_model` 100 %, `freeze_record` 100 %, `pipeline` 100 %, `tariff_mapper` 98 %, `tariff_validator` 100 %, `review` 93 %, `errors` 99 % | **91 % total** |
| `services/mcp` | proxy tools (`server` 86 %, `config` 100 %) | **94 % total** |
| `services/intelligence` | rule/crosswalk/validator logic (`combinability` 100 %, `tarmed_tardoc` 100 %, `rule_validator` 100 %), `config` 100 %, `main` 100 %, `errors` 98 % | **99 % total** |

Every core logic module is above the 80 % target; the one module below the line, serving's
connection-pool facade `db.py` at 76 %, is infrastructure whose uncovered lines are the
Postgres-only legs exercised by the `python-parity` CI job rather than the offline suite. The
floor is now **enforced in CI**: the
`python` job runs the ingestion, serving, mcp and intelligence coverage with `--cov-fail-under=80`, so a
regression that drops one of those totals below 80 % fails the build. The per-service totals
(ingestion 91 %, serving 94 %, mcp 94 %, intelligence 99 %) sit comfortably above the gate.

## Console component tests

The TarifGuard console is tested in CI. The `apps/tarifguard/package.json` `test`
script runs `vitest run && playwright test` (with `test:unit` and `test:e2e` running each half),
and has done so since the console landed (PR #16, commit `265b2e3`, 2026-06-13). The CI
`console` job (`.github/workflows/ci.yml`) runs `npm ci`, lint, build, installs Chromium, and
then the suite, on every push to `main` and every pull request.

The suite is **40 Vitest tests across six files** plus a **Playwright end-to-end
smoke**. The component tests assert the brand visual law: that frozen values render in navy mono
with version and truncated `record_hash` provenance chips, and that every AI output renders
inside its `.ai-content` labelled surface, marked as AI-generated content that is not a billing
value and never restyled as a frozen value (ADR-013 scope). The Playwright smoke walks search to
detail to a mocked review-freeze to explain in a real browser, against an offline mock serving
API, asserting the same two boundaries end to end. A second Playwright spec captures the doc
screenshots and is gated behind `CAPTURE=1`, so it is skipped in the CI gate.

The CI `console` job on the latest `main` run produced this result (Vitest summary, then the
Playwright run):

```
 Test Files  6 passed (6)
      Tests  40 passed (40)
...
Running 2 tests using 1 worker
  1 skipped
  1 passed (17.2s)
```

All 40 Vitest tests pass (the seven `brand` cases are the visual-law checks named
above), and the Playwright run is 1 end-to-end smoke passed plus 1 screenshot-capture spec
skipped (it runs only with `CAPTURE=1`). The console is additionally covered by the serving API
contract tests it consumes, with manual smoke captured into `docs/evidence/`.
