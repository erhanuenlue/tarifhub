# Decision Matrix

Three AI-assisted working modes were available throughout tarifhub. They are not ranked in
the abstract; they are *placed* against this project's real constraints. The vibe-to-spec
spectrum follows Osmani's framing of AI-assisted development [1]; the agentic, multi-agent
pipeline follows the agentic-workflow patterns in [9]. Every claim below is grounded in a
dated incident from the contemporaneous journal (`vault/daily/`) and `LEARNINGS.md`, with the
PR or commit reference given, so the matrix is evidence and not opinion.

- **Vibe**: an ad-hoc prompt straight to code, with no specification and no review before it lands.
- **Spec-Driven**: a written spec or plan and a human gate before code lands.
- **Agentic**: a multi-agent pipeline (model-pinned workers, fresh-context verifier, and an
  independent second model reviewing every PR).

| Criterion | Vibe | Spec-Driven | Agentic |
|---|---|---|---|
| **Billing-grade correctness** | Worst fit, and the project has the cautionary tale: an AI scaffold in the console's `lib/api.ts` used a camelCase, Java-flavoured contract and so rendered every served value as a dash placeholder. It was caught by reading both sides of the wire, not by a test (2026-06-13, PR #16). Ungrounded generation is unsafe on the value contract. | A hard floor. The written freeze-line rule and the `guard_frozen` hook stopped an AI edit that wrote an `int` into a boolean audit column; work halted and the owner authorised exactly one line under protocol (2026-06-11, PR #2, `057a6c1`). A spec plus a hard gate makes the dangerous edit impossible to land silently. | The strongest evidence, but not a guarantee. The independent reviewer (Codex) caught a metadata write that broke re-ingest idempotency and a `json.loads` on a Postgres JSONB value that would have returned a 500 error on every read, both invisible to 28 green tests (2026-06-11, PR #2). Counter-evidence: the same reviewer once proposed a wrong fix from a shared misconception (rejected, PR #7), and a worker's race-condition diagnosis was refuted at the merge gate (PR #8). |
| **Solo throughput, 4-week window** | Fast to a first draft, then slow: the `lib/api.ts` scaffold shipped quickly and cost a manual rewrite (PR #16). (Throughput here is interpretation, not a logged metric.) | Front-loads effort at the plan gate to avoid the rework loop. The win is visible as the absence of large rollbacks rather than a single incident. | This is the throughput multiplier for one operator: independent breadth (parsers, API surfaces, demo) runs on parallel model-pinned workers. The limit is coupling: parallel worktrees were rejected for the one tightly-coupled console contract and the work was kept in-orchestrator (2026-06-13, PR #16). The agentic mode therefore favours independent breadth over coupled depth. |
| **Auditability of the process** | No direct evidence; by nature vibe leaves no spec or rationale trail. | The paper trail this report is built on. A flawed brief (a wrong HTTP status) propagated into three files before a fresh-context verifier caught it (2026-06-12, PR #4, `07cdfc5`); the freeze-line fix landed as one isolated, diffable commit. Specs, gates and commit references make the history reconstructable. | Converts a one-off catch into a durable guardrail: the reviewer's "lock the field set with a drift guard, not discipline" became `test_model_contract.py` (2026-06-12, PR #12, `257c0e0`). Agentic review can leave a test behind, not just a comment. |
| **Review burden / code bloat** | No direct evidence; the cost shows up as rework, not review load. | A spec scales correctness and errors alike: one wrong brief multiplied across three files (PR #4), so review burden tracks spec quality. | Adds adjudication burden: one review yielded a rejected invented invariant and a valid fix in the same pass (2026-06-12, PR #5, `ac8296c`), so each second-model finding must be weighed. This burden is mitigated deliberately by running fewer, outcome-focused agents rather than a large overlapping set. |

## Conclusion

The modes are matched to the **blast radius** of an error.

**Spec-driven** governs the core contract: the freeze line, the `record_hash`, the canonical
model. There a single silent error is irreversible, so the gate is a hard human stop. The
evidence that this is the right placement is concrete: the freeze-line rule actually stopped
a bad edit (PR #2), and the worst near-miss on correctness came precisely when a brief was
wrong and scaled (PR #4).

**Agentic** governs breadth: the parsers, the API surfaces and the demo, dispatched to
model-pinned workers with an independent second model (Codex gpt-5.5) reviewing every PR. It
caught defects that both the test suite and the first-pass reviews missed (PR #2; the
server-side billing-field guard in PR #16, `265b2e3`). Its honest limit is that it is not a
safety net: a reviewer and a worker each produced a confidently-wrong diagnosis (PR #7, PR #8),
so the human merge gate remains the backstop.

**Vibe** is confined to throwaway exploration. The one time an ungrounded scaffold reached a
contract surface, it silently broke every displayed value (PR #16, `lib/api.ts`).

The transfer to future practice is the rule itself: a hard gate and a spec where an error is
irreversible, agentic breadth plus a second model where it is recoverable, and vibe only where
the output is disposable. The non-delegated backstops (the freeze line, the plan and merge
gates) are taken up in the [Conclusion](fazit.md).

## References

- [1] A. Osmani, on AI-assisted software development and the spec-driven vs vibe spectrum (course literature).
- [9] O'Reilly, on agentic and multi-agent development workflows (course literature).
