---
name: ship
description: The 9-phase multi-model shipping pipeline — plan-approval, TDD implementation, reviews, CI, runtime verification, auto-merge on green. Invoke whenever work is ready to land (prompts end with "then /ship" — that means run this skill). Gate 01 (plan approval) always stops for Erhan; phase 09 auto-merges only under its green-contract and stops for Erhan otherwise (owner decision 2026-06-11).
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Agent
---

Ship the requested work through the phased pipeline. **The first action of every phase is its emit command — before any other tool call of that phase.** **You, the orchestrator (model pinned in `.claude/settings.json`, ADR-018), do only the jobs where quality compounds: the plan, the orchestration, the merge-gate review, and complex senior-level decisions.** Delegate the volume. Emit a dashboard event at every phase transition: `bash tools/shipboard/emit.sh <01-09> <running|pass|fail|skip> "<short detail>"` (the phase argument is the two-digit number, e.g. `emit.sh 03 running "pytest serving"`) — never let an emit failure block the pipeline. Watch the board at `python3 tools/shipboard/shipboard.py` → http://localhost:8787.

**Model discipline:** each agent's model is pinned in its config — never override it, never switch a model mid-task (prompt caches are model-scoped; a switch re-reads the whole context at full price). Hold the plan-quality bar ruthlessly: a wrong plan wastes every downstream token.

**Effort policy (owner law): `/effort ultracode` throughout, no down-shift to save tokens.** Every inline phase (plan, gates, fix, PR, report, merge-gate) runs at ultracode. Every delegated worker carries `effort: ultracode` in its own frontmatter (implementer, e2e-tester, verifier, determinism-auditor, security-reviewer, grade-auditor; codex-reviewer relays gpt-5.5 on the owner's Codex login). Auto-orchestration operates **inside** this skill's contract: the nine phases and their order stand, the emits fire, **gate 01 always stops for Erhan**, and phase 09 auto-merges only when its green-contract holds, anything less stops for him.

## Phase 01 — Plan *(inline, orchestrator · Opus 4.8)*
Read the task/issue + the code it touches. Produce the plan: scoped task list with file-level targets, acceptance criteria per task, review routing (which reviewers this diff needs), and what phase 07 must prove. **STOP and present the plan to Erhan for approval.** Do not proceed without his explicit yes; fold in his corrections. `emit 01 pass`.

## Phase 02 — Implement *(delegated: `implementer` × N, Opus)*
Dispatch each approved task to an `implementer` — in parallel where tasks are independent (separate files/services), sequentially where they conflict. Branch first if on `main` (`feat/…|fix/…`). Review each returned report; reject scope creep immediately. You write code yourself only for trivial glue the dispatch overhead doesn't justify.

## Phase 03 — Local gates *(inline)*
`uv run ruff check . && uv run pytest -q` per touched service (offline suite); `npm run lint && npm test` if `apps/` changed. Quote failures verbatim; route fixes back to the responsible implementer. Stage related changes into small Conventional Commits.

## Phase 04 — Reviews *(delegated, parallel)*
Always: `verifier` (fresh-context diff-vs-plan) **and `codex-reviewer` on every PR** (owner decision 13 Jun — independent second model family, gpt-5.5 on the owner's Pro login; brief covers correctness, edge cases, security AND missing test cases). Conditional: `determinism-auditor` (anything under `services/`), `security-reviewer` (secrets/parsing/deident/API surface). Launch applicable reviewers **in one parallel batch**.

## Phase 05 — Fix cycle *(orchestrated)*
Consolidate findings, de-duplicate, rank. Route real defects to `implementer`; reject false positives with one-line reasoning (keep it in the report). Re-run phase 03 gates + the objecting reviewer after fixes. Loop until clean or escalate to Erhan if a finding disputes the approved plan itself.

## Phase 06 — PR + CI *(inline)*
`gh pr create` — description: what + why, evidence (test output), review summary, what phase 07 will prove. Wait for CI; the determinism boundary test must be visible in the run log. CI red → phase 05.

## Phase 07 — Runtime verification *(delegated: `e2e-tester`, Opus 4.8)*
Compose-up, integration suite against real Postgres, API smoke, console smoke + screenshots when `apps/` changed, container-log scan. This is the CAS-fit replacement for cloud staging — captured evidence beats a live deploy nobody will visit. Findings → phase 05.

## Phase 08 — Full report *(inline, orchestrator · Opus 4.8)*
Consolidated ship report: what landed (per task), evidence (quoted test/CI/runtime output), review findings and their dispositions, files touched, risks remaining. **Include the CAS anchor delta:** run `python3 tools/cas_check.py` and report one line — elements gained/lost vs. the run's start and any ratchet regressions (a regression blocks the green-contract until fixed: it is a failing check). Append the journal-relevant extract to today's `vault/daily/` draft — which agents ran on which model, what they got wrong, what caught it (criterion-15 raw material, generated as a by-product).

## Phase 09 — Merge *(auto on green · fallback gate: Erhan)*
Owner decision 2026-06-11: Erhan delegated routine merge confirmation. Present the phase-08 report, then check the **green-contract — ALL FOUR must hold:**

1. CI fully green on the PR — every check, security job included; the determinism boundary test visible in the run log.
2. Every reviewer finding resolved or explicitly dispositioned in the report — no open P1/P2.
3. The diff touches **no frozen path** (`versioning/`, `audit/`, applied migrations, boundary tests) beyond changes Erhan explicitly authorized **this session**.
4. Working tree clean; branch current with `main`.

All four hold → `gh pr merge --squash --delete-branch` without waiting, `emit 09 pass "auto-merged on green"`, confirm `brain_sync` ran, and close the report with one line stating what merged and why it qualified. **Any condition fails → STOP and ask Erhan**, naming exactly which condition failed. Never widen the contract; when in doubt, it is a gate.

**Failure posture:** any phase fails → `emit <phase> fail "<reason>"`, attempt the fix loop once, then stop and report rather than thrash. Gate 01 is never skipped, never assumed; phase 09's autonomy exists only inside its green-contract.
