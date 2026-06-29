# Conclusion

This conclusion is written in the first person because the decisions it records were mine to make. The project relied heavily on AI: model-pinned worker agents wrote most of the volume, a second model family reviewed every pull request, and even this journal was drafted by an automated pipeline. What follows is an honest account of where I refused to delegate, where I delegated and how it went, and what I would carry into future work. I do not claim the result is flawless. I claim it is auditable, and that the boundaries held.

## Three veto decisions: never delegated to AI

There were three places where I would not let AI act on its own judgment. I treated each as a hard veto, not a guideline.

**Veto 1: No AI ever computes or mutates a billing value.** This is the freeze line, and it is enforced in code, not by trust. On 11 June the `guard_frozen` hook blocked an edit to `audit/audit_logger.py`, a file below the freeze line, where a worker had written `int(validation_ok)` into a column Postgres treats as boolean. The hook stopped the edit, so per protocol the run halted for my decision. I authorised exactly one line. It landed as an isolated `fix(audit):` commit with the frozen-file diff shown before commit, the guard was re-armed, and a follow-up edit attempt was deliberately probed and BLOCKED to prove the guard was live again (PR #2, 057a6c1). The point is not that the bug was small. It is that the dangerous edit could not land silently, and the human authorisation is on the record.

**Veto 2: Plan approval and the merge green-contract stay under human judgment.** No plan reached implementation without the owner's gate-01 approval, and no PR auto-merged unless its green-contract held. This veto proved its value. On 12 June my own orchestrator brief claimed the explain route returned HTTP 501 when the code actually 404'd, because no serving route existed at all. That single error propagated into three files before a fresh-context verifier caught it against the real httpx path (PR #4, 07cdfc5). An error in my brief scaled exactly as fast as the agents that consumed it, which is precisely why a human reads the plan and why every reviewer finding is dispositioned in the PR body rather than waved through.

**Veto 3: Final acceptance is never delegated.** The go-live decision and the release of the work to the public stay with me. This is partly structural: repository visibility and the GitHub Pages settings can only be changed by the owner, and the public-readiness sweep on 13 June (a secret scan across the full commit history, an MIT LICENSE, a documented production-override path for the Helm demo password) explicitly left visibility and Pages with the owner (PR #17). Making the repository and the documentation site public, and presenting them to the examiner, is an act only I can perform. No automated pipeline gets to declare the work released.

## What I delegated, and how it went

The volume was delegated, deliberately. The `implementer`, `verifier`, `determinism-auditor`, `security-reviewer` and `codex-reviewer` fleet did the breadth of the build: parsers, the read-only API surfaces, the FHIR adapter, the demo console, and, late in the project, the human-in-the-loop review write-back that was the one piece left at design scope in the MVP, now built behind the same plan gate and freeze line as the rest (a corrected billing field is still refused in code). Even the journal and conclusion-note drafting runs through Codex gpt-5.5 via `tools/curate.sh`, fully automated and disclosed in the AI-tools chapter. The owner edits before submission. This conclusion is the human edit of that material.

The measured results are mixed in the honest way. Review burden was real but bounded: the live EAL run froze 1279 records at a 0.0% review rate, and the SL ingest froze 10,299 records at a 1.08% review rate (111 records flagged into the review queue), with a further 109 GTIN-less packages fail-closed and never frozen. Re-version churn was a genuine surprise: live `ai_map` fills are not byte-stable across runs, so re-runs produced 55 re-versions until the fill-reuse fix landed (PR #8, d027a1d). The FR ranking improvement was concrete: adding the e5 `query:` prefix lifted recall@5 from .833 to .917, with the MRR@5 dip documented as a deliberate trade-off rather than hidden (PR #7, 5da6472).

Agentic breadth clearly beat spec-driven work where the surface was wide. An independent second model caught defects that 28 green tests had missed: a metadata write that broke re-ingest idempotency, and a `json.loads()` on a Postgres JSONB value that would have 500'd every read (PR #2, 057a6c1). The reverse held on the core contract. The freeze line, the `record_hash`, and the canonical model belong behind a hard human gate, and I rejected agentic parallelism exactly once where it mattered: parallel implementation worktrees for the one tightly-coupled console contract were turned down, and I kept that work in-orchestrator (PR #16). Breadth wins on independent work. Coupled depth does not.

The central lesson sits underneath all of this. An enforced, tested determinism boundary, the AST boundary test asserting that no LLM client is importable on the value path, is what makes AI usable on billing data at all. Without that test, "no AI touches a billing value" would be a promise. With it, the promise is checked on every CI run and the build fails if it is broken.

## Honest limits

The tools are not infallible, and pretending otherwise would undercut the whole argument. Codex proposed a confidently wrong e5 prefix fix built on the same misconception the bug came from, and I rejected it (PR #7, 5da6472). A worker's TOCTOU race diagnosis for the re-versioning problem was refuted at the merge gate by audit timestamps and a clean `UNIQUE(record_hash)` constraint (PR #8, d027a1d). The Codex CLI failed to emit a formal report in two of six sessions in one block, once on a plugin error and once on a silent termination. The adjudication burden of weighing every second-model finding is itself a cost, not a free safety net. The backstop is always the human gate.

## Transfer to future practice

The transfer into a future way of working is a single rule: match the working mode to the blast radius of an error. Where an error is irreversible, use a hard gate plus a written spec, so the dangerous change cannot land silently. Where an error is recoverable, use agentic breadth with an independent second model, so wide work moves fast and defects get a second pair of eyes. Where the output is disposable, vibe coding is fine and a written spec would only be ceremony. The mistake to avoid in future work is applying one mode everywhere: a spec on throwaway exploration is waste, and vibe coding on a value contract is exactly how the console scaffold silently rendered every billing value as a dash placeholder until I read both sides of the wire (PR #16). The mode is a function of consequence, not of habit.

### Core statement

An enforced, tested determinism boundary, the AST test that guarantees no LLM client is importable on the value path, is the precondition that makes AI usable on billing-grade data at all. The boundary is not a promise. It is a fact checked on every CI run.

## References

- [1] A. Osmani, on AI-assisted software development and the vibe-to-spec spectrum (course literature).
- [9] O'Reilly, on agentic and multi-agent development workflows (course literature).
