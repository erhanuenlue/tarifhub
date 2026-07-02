# Decision matrix: Vibe vs Spec-Driven vs Agentic

Working evidence for the AI-method chapter ([docs/method/decision-matrix.md](../docs/method/decision-matrix.md)).
Every cell is grounded in a **dated** journal incident (PR / commit ref) from `vault/daily/`
and `LEARNINGS.md`, or marked honestly as having no direct evidence. The column framing
(the vibe ↔ spec-driven spectrum, agentic workflows) follows the course literature
([1] Osmani; [9] O'Reilly). Three working modes, judged against this project's real
constraints.

| Criterion (this project) | Vibe (ad-hoc prompt → code) | Spec-Driven (plan/spec/gate first) | Agentic (multi-agent pipeline + 2nd model) |
|---|---|---|---|
| **Billing-grade correctness** | **Worst fit.** The one clean vibe incident is the cautionary tale: an AI scaffold in `lib/api.ts` used a camelCase, Java-flavoured contract (`id`, `taxPoints`) that rendered every served value as a dash; caught by reading both sides of the wire, **not by a test** (2026-06-13, PR #16). Ungrounded generation is dangerous on the value contract. | **Hard floor.** The written freeze-line rule plus `guard_frozen` stopped an AI `int(validation_ok)`-for-`bool` edit on a billing-adjacent column; work halted and the owner authorised exactly one line under protocol (2026-06-11, PR #2 `057a6c1`). A spec + hard gate makes the dangerous edit impossible to land silently. | **Strongest cell, but not infallible.** Codex (independent model) caught an `ai_status`-into-metadata hash break that broke re-ingest idempotency, and a `json.loads()`-on-JSONB Postgres-500, both invisible to 28 green tests (2026-06-11, PR #1 `79169f0`). Honest ballast: Codex also proposed a **wrong** e5 prefix fix from a shared misconception (rejected, PR #7 `5da6472`) and the e2e-tester's TOCTOU diagnosis was **refuted at the gate** (PR #8 `d027a1d`). Defence in depth, with the human gate as backstop. |
| **Solo throughput, 4-week window** | Fast to first draft, slow to correct: the `lib/api.ts` scaffold (#PR16) shipped quickly then cost a manual rewrite. Net drag once the surface is contract-bound. *(throughput framing is interpretation, not a journal metric.)* | Front-loads cost at the plan-approval gate to avoid the rework loop (cf. the brief-error propagation below). No single incident quantifies the win; the evidence is the absence of large rollbacks. *(interpretation.)* | The throughput multiplier for a solo operator: breadth (parsers, API surfaces, demo) dispatched to model-pinned workers in parallel. But agentic parallelism was **rejected** where work was coupled: parallel implementation worktrees for the one tightly-coupled console contract, kept in-orchestrator instead (2026-06-13, PR #16, Fazit veto). Wins on independent breadth, not coupled depth. |
| **Auditability of the process** | **No direct evidence** (vibe work is by nature the least auditable; it leaves no spec or rationale trail). | The paper trail this dossier is built on. A flawed orchestrator brief (explain returns 501) propagated into 3 files before a **fresh-context verifier** caught it (2026-06-12, PR #4 `07cdfc5`); the one-line freeze-line edit landed as an isolated, diffable commit (PR #2). Specs + gates + commit refs = reconstructable history. | Converts a one-off catch into a durable guardrail: Codex's "lock the field set with a drift guard, not discipline" became `test_model_contract.py` (2026-06-12, PR #12 `257c0e0`). Agentic review leaves a test behind, not just a comment. |
| **Review burden / code bloat** | **No direct evidence**; the cost surfaces as rework (the `lib/api.ts` rewrite), not as review load. | A spec scales both correctness and errors: one wrong brief multiplied across 3 files (PR #4 `07cdfc5`), so review burden tracks spec quality. | Adds adjudication burden: one Codex review yielded a **rejected** invented-invariant ("a billing value must exist at freeze") plus a **valid** P2 fix in the same pass (2026-06-12, PR #5 `ac8296c`): every second-model finding must be weighed. Mitigated deliberately by running fewer, outcome-focused agents rather than a 10-agent zoo (2026-06-10 hypothesis). |
| **Where it won here (dated ref)** | Throwaway exploration only; never the value path. Cautionary: PR #16 (`lib/api.ts`). | The freeze/hash/canonical-model core: PR #2 (`057a6c1`), PR #4 (`07cdfc5`). | Breadth + review: PR #1 (Codex catches), PR #12 (`257c0e0` drift guard), PR #16 (`265b2e3` server-side billing-field guard the first-pass reviews under-weighted). |

## Conclusion (argued, not asserted)

The three modes are not ranked; they are **placed**. **Spec-driven** governs the core
contract (freeze line, `record_hash`, canonical model), where a single silent error is
catastrophic and the gate must be a hard human stop: the evidence is that the freeze-line
rule and `guard_frozen` actually stopped a bad edit (PR #2), and that the worst near-miss
on correctness came precisely when a *brief* was wrong (PR #4). **Agentic** governs breadth:
parsers, API surfaces and the demo, dispatched to model-pinned workers, with an independent
second model (Codex gpt-5.5) reviewing every PR; it caught defects the test suite and the
first-pass reviews missed (PR #1, PR #16 `265b2e3`). Its honest limit is that it is not
infallible (a reviewer and a worker each produced a confidently-wrong diagnosis, PR #7, PR #8),
so the human merge gate stays the backstop. **Vibe** is confined to throwaway exploration:
the single time an ungrounded scaffold reached a contract surface it silently broke every
displayed value (PR #16, `lib/api.ts`). The transfer to future practice: match the mode to
the blast radius. Hard gate + spec where an error is irreversible; agentic breadth + a second
model where it is recoverable; vibe only where the output is disposable.

↩ [[00-index]]
