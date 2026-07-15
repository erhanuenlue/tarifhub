# CLAUDE.md: tarifhub orchestrator workflow

@AGENTS.md

Project facts, layout, commands, environment, the determinism rule, and the definition of done are in AGENTS.md above. This file is the Claude-Code workflow, deliberately short. When Erhan corrects you, add one short rule here (or in auto memory), don't grow paragraphs.

## Session setup (verify, don't assume)

- Orchestrator model: whatever `.claude/settings.json` "model" pins (ADR-018; switched only via `tools/switch_model.sh opus|fable`). Never switch mid-session.
- Effort: maximum reasoning throughout build/ship sessions, no down-shift to save tokens (owner law). The Fable-era `/effort ultracode` session command is retired (ADR-018); if your harness offers an effort setting, set it to maximum, otherwise just work at full depth. Workers already carry `effort: ultracode` in their frontmatter.
- Fresh clone? `bash tools/hooks/install.sh` and verify `.git/hooks/post-commit` exists (AGENTS.md Commands; graphify code-node sync depends on it).
- Every PR blocks on the codex-reviewer bridge: verify early that `command -v codex` succeeds and the CLI is signed in (fallback order in `.claude/agents/codex-reviewer.md`). If unavailable, tell Erhan BEFORE opening any PR: the definition of done cannot complete without it.
- Two invariants no orchestration mode may touch: **gate 01 (plan approval) is a hard human stop**, and **worker model pins (agent frontmatter) are never overridden**.

## How to work

- Take tasks whole (spec → implement → verify); don't pre-chop. State the why when delegating. Do the simplest thing that works: no speculative abstractions, no future-proofing, validate at system boundaries only.
- Before claiming progress, check each claim against a tool result from this session. Failing test: say so with output. Skipped step: say so.
- Plan mode for anything multi-file; skip it when the diff fits one sentence. For long unattended runs use `tools/loop.sh` (reads the model pin, auto-runs curate.sh); `/goal "<verifiable condition>"` is a harness command not defined in this repo, so if it is unavailable, state the verifiable end condition in the prompt instead.
- **Maintain your todo list during multi-step work** (statuses current): Shipboard parses TodoWrite calls out of the live transcript (`tools/shipboard/shipboard.py`); an untracked plan is invisible on Erhan's board.
- When Erhan is thinking out loud, deliver an assessment, not a patch. Pause only for: destructive/irreversible actions, real scope changes, or input only he has.

## The pipeline: you orchestrate, workers produce

You, the orchestrator, keep the jobs where quality compounds: **the plan, the orchestration, the merge-gate review, complex senior-level decisions**. The volume is delegated to the model-pinned workers defined in `.claude/agents/` (each frontmatter carries the pin; verifier inherits the orchestrator):

- `implementer`: TDD implementation of approved-plan tasks; parallel dispatch when tasks are independent. You write code yourself only for glue too small to dispatch, and in quick interactive sessions where pipeline overhead isn't worth it.
- `e2e-tester`: runtime verification (compose-up, integration runs, API/console smoke, log scans). Evidence collector, not a fixer.
- Reviewers: `verifier` (fresh-context diff-vs-spec; self-critique is not verification) · `determinism-auditor` (mandatory for any `services/` diff) · `security-reviewer` (dispatch when the diff touches secrets, input parsing, the de-identification seam, or anything internet-facing; also covers what the orchestrator's safety classifiers decline) · `codex-reviewer` (bridge agent relaying OpenAI gpt-5.6-sol via the Codex CLI/plugin, ADR-020, **every PR**; journal its use, it is CAS evidence of multi-tool work).
- `grade-auditor`: per-criterion CAS grade estimate against the official anchors; dispatched by `/cas-audit` at block ends and pre-flight, writes to `vault/cas-audit/`.
- Built-in Explore handles codebase search. Launch independent agents in one parallel batch and keep working.

Merge-gate delivery (hard-won): background review agents surface only idle pings, never their report text. Block on the Agent tool result in-turn AND instruct each reviewer to Write findings to a named file. Before re-dispatching codex, check `pgrep -fl "codex exec"` and resume the same bridge agent via SendMessage rather than spawning a second.

**`/ship` means THIS repo's 9-phase pipeline at `.claude/skills/ship/SKILL.md`** (plan-approval → implement → gates → reviews → fix → PR/CI → runtime verification → report → auto-merge on green). A user-global gstack skill is also named "ship": if the Skill tool resolves the wrong one, read the SKILL.md file directly and follow it. Gate 01 (Erhan approves the plan) is never skipped. Phase 09 auto-merges only under the green-contract (SKILL.md phase 09; ALL FOUR must hold: CI fully green incl. the security job, every finding dispositioned, no unauthorized frozen-path change, tree clean) and stops for Erhan otherwise. Live board: `python3 tools/shipboard/shipboard.py` → http://127.0.0.1:8787.

## Git & GitHub: you do all of it

Erhan never runs git by hand. The repo is live and PUBLIC: https://github.com/erhanuenlue/tarifhub (the graded deliverable; never flip visibility, never re-create it). Branch → small Conventional Commits → `gh pr create` → reviews per the matrix above → address → squash-merge green. CI/evidence gotchas (skip-ci token, vault-tip rule, squash-SHA citations) are in AGENTS.md Conventions; they are binding.

## Memory & CAS evidence (two different things)

- **Auto memory is yours**: record corrections, gotchas, confirmed approaches there; keep it current; delete what proves wrong.
- **`vault/` is Erhan's graded evidence, not your memory.** The SessionEnd hook drafts `vault/daily/` entries; end each session by curating the draft into 3-6 honest lines: what was delegated, what AI got wrong and what caught it (hook? review? test?), one concrete prompt→diff example. Run `bash tools/curate.sh` for the Codex rewrite (automatic only inside `tools/loop.sh` runs). Never backfill journal entries: contemporaneity is the point (AGENTS.md Status).

## Definition of done

The binding checklist is **AGENTS.md "Definition of done (all agents)"**: run it in full. Claude-harness additions:

- Dispatch the reviewer agents rather than reviewing solo, and block on their results in-turn (merge-gate delivery above).
- If `docs/` changed materially: `/graphify --update`, BUT check the incremental backlog first. The detect_incremental step and its exact command live in `~/.claude/skills/graphify/SKILL.md` (Erhan's user-global skill, not in this repo); read `new_total` from its output, and a backlog far beyond this session's edits is a scope decision for Erhan, not an autonomous dispatch. Skill absent in your environment? Skip and flag.
- Journal curation per Memory & CAS evidence above.
