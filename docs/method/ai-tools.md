# AI Tools and Workflow

This chapter is the honest account of how AI was used to build tarifhub, organised by
the four working phases the project actually ran: Generation, Review,
Refactoring and Research. Every claim is tied to a prompt line, the file or diff it produced, and a
PR plus commit reference taken from the contemporaneous journal (`vault/daily/`) and the
`LEARNINGS.md` register. Where AI was wrong, that is recorded with what caught it. The
companion mode analysis (vibe versus spec-driven versus agentic) lives in
[the decision matrix](decision-matrix.md) and is not repeated here; this chapter is about
the apparatus and the worked evidence.

## The reproducible apparatus

The workflow is reproducible because its rules are version-controlled, not held in a
person's head. Two files act as the context set loaded into every session:
`AGENTS.md` pins the project facts, the layout, the value-path invariant
("no AI computes or mutates a billing value at serve time") and the model policy;
`CLAUDE.md` pins the orchestration workflow on top of it. Because both are checked into the
repository, any session starts from the same constraints, and the rules the AI was given
are readable directly in the repository.

The full system view of that apparatus, the `/ship` pipeline and its green-contract, the
model-pinned seats, the autonomous loop, the quality gates and the freeze-line guard, the
CI/CD pipeline, the independent second model, the dashboard, and the human floor, is
documented in the companion chapter
[AI-Assisted Software Engineering: the framework](ai-se-framework.md), which also names the
complete external tool set: Claude Code, the OpenAI Codex CLI, and the Eraser MCP. This
chapter is the worked, phase-structured evidence behind that framework: the prompts, diffs
and commits, organised by Generation, Review, Refactoring and Research. The one mechanism
worth restating here, because its catches recur below, is governance by tooling: a pre-tool
hook (`guard_frozen`) blocks any edit below the freeze line (`versioning/`, `audit/`, the
determinism boundary test) and halts the agent rather than letting it work around the rule.
These hooks are not cosmetic: in this project a hook blocked a genuinely unsafe edit (recorded
under Review below).

A second governance-by-tooling mechanism sits on top of the freeze-line guard: the approval bridge,
the human-in-the-loop layer of the tool set. A `PreToolUse` hook (`.claude/hooks/approval_gate.sh`)
classifies each Bash action and, for the sensitive cases (a push to `main`, a merge, a destructive
git command, a publish), enqueues an approval request under `.shipboard/approvals/` and blocks until
a human decides. The decision can come from either of two surfaces over one shared queue: an
Approvals panel on the `/ship` dashboard (Approve and Deny buttons, with a count badge in the
header), or a Telegram bot (`tools/approval_telegram.py`) that sends the same request with inline
buttons. They share a single decision file, which the dashboard publishes atomically (an exclusive
link), so it is never half-read, the first writer wins, and a later tap on either surface returns the
standing decision. The gate appends each request and the decision it enforces to
`.shipboard/approvals/log.jsonl`. The bridge is
fail-safe and opt-in: it is a hard no-op unless `APPROVALS_ON=1`, and if no decision arrives within
the timeout it denies, so the worst case is the project's existing safe halt rather than an ungated
action. Where `guard_frozen` is a hard stop at the freeze line, the approval bridge turns the other
human-floor lines (merges, publishes) from halt-and-rerun into pause-tap-resume, routed and logged
rather than asserted (the framework view is in [the framework chapter](ai-se-framework.md), section
10).

## Generation

Generation is where AI produced first drafts of code, docs and diagrams, always behind a
gate before anything landed.

The most safety-critical generation is the pre-freeze `ai_map` seam. The prompt is
deliberately narrow: "FILL-ONLY: set designation.fr/it/category ONLY where the current value
is None." That line produced the merge block in `tariff_mapper.py`, and a live run against
the official BAG list sample showed exactly the intended behaviour: French and
Italian designations filled, the existing category left untouched,
`ai_fields=['designation_fr','designation_it']`, and the billing fields byte-identical
before and after (PR #2, `057a6c1`). The schema-constrained, fill-only shape is what keeps
generation off the value contract.

Generation also scaled to documentation. One 22-agent workflow drafted five new PlantUML
diagram sources, eight arc42 chapters and the criterion map in a single pass, with four
fresh-context verifiers checking the output. The diagram drafts came back in the house palette
and the corrections were semantic, not cosmetic: the state diagram was re-routed so that
`scored` always reaches `frozen` and the review queue holds frozen flagged versions
(PR #4, `07cdfc5`).

The journal pipeline is itself a worked generation example, and its disclosure is required
here. At session end the `vault_autocommit` hook drafts the day's `vault/daily/` entry. The
`tools/curate.sh` script then sends that draft to Codex gpt-5.5, running sandboxed and
read-only so it generates text only, and the model rewrites the draft into curated prose. The
process is fully automated; the owner edits the result at his discretion before it counts as
submission evidence. The journal entries this very chapter cites were produced through that
pipeline.

A generation failure belongs here too. A previous AI scaffold for the console wrote
`lib/api.ts` against a camelCase, Java-flavoured contract (`id`, `taxPoints`, with POST
explain and coding-check shapes) that did not match the real snake_case serving API. The
result was that every served value rendered as a dash placeholder in the console. No test
caught it; it was caught by reading both sides of the wire and comparing the generated client
contract against the actual API response shape (PR #16). The lesson is that ungrounded
generation is most dangerous exactly where it meets a real contract surface.

## Review

Review is where the multi-model wave and the hooks did their heaviest work, and where the
independent second model earned its seat.

In the very first block, Codex (the independent model) caught two defects that 28 green tests
missed. The first was an `ai_map` error path writing `ai_status` into record metadata on a
transient API outage, which produced a different `record_hash` than the no-key fallback and
silently broke re-ingest idempotency. The second was a `json.loads()` call on a Postgres JSONB
column that is already a dict, which would have returned HTTP 500 on every Postgres read; the
SQLite-only tests were blind to it because the SQLite driver returns text. Both were corrected
before merge (PR #2, `057a6c1`).

The freeze-line hook produced the cleanest example of governance by tooling. The first real
Postgres run exposed `int(validation_ok)` in `audit/audit_logger.py`, below the freeze line:
psycopg sends a smallint and Postgres rejects it for a boolean column. `guard_frozen` blocked
the edit, the work halted, and per protocol the owner authorised exactly one line in an
isolated `fix(audit):` commit, with the frozen-file diff shown before commit, the guard
re-armed, and a follow-up edit attempt confirmed BLOCKED (PR #2, `057a6c1`). The AI did not
get to "just fix it"; the rule held.

A review failure here is the orchestrator's own error. A brief written by the orchestrator
claimed `explain_crosswalk` returns 501, when the code returns 404 because no serving route
existed at the time. The wrong status propagated into three files before a fresh-context
verifier checked the actual httpx path and caught it (PR #4, `07cdfc5`). Self-review by the
author who wrote the brief would not have found this; a reviewer with no stake in the brief did.

Review must also reject confident wrong suggestions. Codex raised a P1 invariant, "a billing
value must exist at freeze," which is an invented constraint: it contradicts the gate-01
design and the EAL precedent where complete records carry their own values. It was rejected
against the approved design, while in the same review its valid P2 coding finding was fixed
(PR #5, `ac8296c`). One review, two opposite dispositions, both recorded.

Finally, the second model caught what the first-pass reviewers under-weighted. On the console,
the billing-field guard was implemented client-side only. The verifier and the security pass
did not flag it strongly enough. A Codex prompt, "try to find what the first-pass reviews
missed," surfaced it (alongside a review BFF that masked an upstream failure as success), and
the accepted fix added a server-side `BILLING_FIELDS` rejection in
`app/api/review/route.ts` (PR #16, `265b2e3`). Defence in depth is not redundancy when the
layers have different blind spots.

## Refactoring

Refactoring is where one-off catches were turned into durable structure, and where some of
the hardest cross-engine bugs surfaced.

Engine parity drove two refactors. The `json.loads`-on-JSONB defect and an `int`-for-`bool`
parity bug both passed the SQLite suite and were only rejected by a real Postgres engine: a
smallint in a boolean column where 51 green SQLite tests had not objected. The fix was not a
patch but a cross-engine read-parity suite with full-body snapshots, so the class of bug is
now tested rather than hoped against (PR #2, `057a6c1`; PR #6, `56b88cb`).

The e5 embedding refactor carries an honest pairing of a fix and a rejected suggestion. The
e5 model is asymmetric: queries need a `query:` prefix and passages a `passage:` prefix.
Block-0 had embedded queries through the passage path, degrading cross-lingual ranking. The
`query:` prefix fix lifted recall@5 from .833 to .917, and the MRR@5 dip it introduced was
documented as a deliberate trade-off rather than hidden. In the same area, Codex proposed a
fix built on the same prefix confusion; that proposal was wrong and was rejected (PR #7,
`5da6472`). A review failure surfaced inside the refactoring phase, and the human gate kept
the wrong fix out.

The drift-guard refactor is the model of converting advice into a test. Codex's suggestion,
"lock the field set with a drift guard, not discipline," was accepted and became
`test_model_contract.py`, which enforces the ADR-003 additive-only canonical field set
mechanically instead of by convention (PR #12, `257c0e0`). The review left a test behind, not
a comment.

## Research

Research is where AI distilled large source material before any plan was written, and where
its readings had to be corrected against ground truth.

Exploration ran as parallel reader workflows. Before the L1 completeness plan, a five-reader
parallel Explore workflow distilled roughly 300k tokens of code and docs into a briefable
summary (PR #12). Breadth of reading is exactly the kind of work where parallel agents pay off,
because the readings are independent.

Research findings were not trusted until checked against real artifacts. The FHIR implementation
guide analysis was corrected against actual bundles on several points: the Spezialitätenliste
export carries zero tax points and is money-only, there is no `/CHIDMP/` segment in the
`fullUrl`, and a package carries three reimbursement amounts rather than a pair (PR #5 and
PR #6). Each correction came from an implementer reading the real bundles, not from accepting
the model's first reading of the IG.

For current library and API documentation, Context7 was used to fetch up-to-date docs rather
than relying on the model's training cut-off, so that framework and SDK claims in the build
trace to current sources.

---

**Eigenständigkeit.** The authorship confirmation for this work — that it was created
independently with AI support and that every part of the solution is explainable by the
author — is recorded on the [Eigenständigkeit](eigenstaendigkeit.md) page (criterion 15(b)).
