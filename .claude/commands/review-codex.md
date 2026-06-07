---
description: Run an independent OpenAI Codex review of the current diff (working tree, staged, or vs the base branch) and report the findings. Does not commit or merge.
argument-hint: "[optional: base ref or PR number, e.g. origin/main or 42]"
allowed-tools: Bash, Read, Grep, Glob
model: inherit
---

Run a **Codex review** of the current change set. Codex is TarifHub's independent reviewer:
Claude writes, a different model checks.

Optional target: **$ARGUMENTS** (a base ref like `origin/main`, or a PR number). If empty,
review the diff of the current branch against its merge-base with `origin/main`, plus any
uncommitted/staged changes.

## Do this

1. Delegate to the **codex-reviewer** subagent, passing the target. It will run the review
   via the codex-plugin-cc plugin or `codex exec` and return findings as
   `SEVERITY — file:line — problem — suggested fix`, with a final `CODEX VERDICT: ...`.

2. Ask it to specifically check TarifHub's invariants: the determinism boundary (no LLM on a
   value path; `versioning/`, `audit/`, `services/intelligence/**/crosswalk/`, `rules_frozen*`
   untouched), the patient de-identification boundary (rule 7), and contract drift (no renamed
   fields/columns/routes).

3. Relay the findings to me unmodified, grouped by severity. **Do not** fix anything in this
   command — this is review-only. To address findings and merge, use `/ship`.

If Codex is not installed, say so and point to `scripts/setup-claude-code.sh` and
`docs/START_GUIDE.md` — do not substitute a Claude-only review for the independent one.
