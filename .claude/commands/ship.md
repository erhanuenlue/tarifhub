---
description: Autonomous ship flow — branch, conventional commit, push, open a PR, run the Codex review + determinism/security audits, address findings, then merge. Claude performs ALL git/gh; the user never runs git by hand.
argument-hint: <conventional commit subject, e.g. "feat(intelligence): add cumulation rule">
allowed-tools: Bash, Read, Edit, Grep, Glob
model: claude-opus-4-8
---

You are running the **/ship** flow for TarifHub. You own every git and `gh` step — the
user never touches git manually (AGENTS.md). Be deterministic and stop on any failure.

The task / commit subject is: **$ARGUMENTS**

## Steps

1. **Pre-flight.** Confirm `gh` is installed and authed (`gh auth status`). If not, stop and
   tell the user to run `gh auth login` (gh is on their machine, not in CI/sandbox). Confirm
   there are changes to ship (`git status --short`).

2. **Local guard (fast).** Run the determinism-boundary tests before doing anything remote:
   `cd services/ingestion && pytest -q tests/test_determinism_boundary.py && cd ../intelligence && pytest -q tests/test_determinism_boundary.py`.
   If red, fix first or stop — never ship across a broken freeze line.

3. **Branch + commit + push + open PR.** Run the script, which does branch → staged
   conventional commit → push -u → `gh pr create`:
   `./scripts/ship.sh "$ARGUMENTS"`
   It prints the PR URL and writes the Codex findings to `.codex-review.md`. The script does
   **not** merge.

4. **Independent review (the loop).** In parallel, delegate to the three reviewers:
   - the **codex-reviewer** subagent (independent OpenAI Codex second opinion on the diff),
   - the **determinism-auditor** subagent (no LLM on a value path; freeze/audit/crosswalk
     untouched),
   - the **security-reviewer** subagent (secrets, injection, the de-identification boundary).

5. **Address findings.** Apply fixes for every blocker and major finding with minimal,
   incremental diffs (rule 3). Re-run the relevant tests. Commit the fixes
   (`git commit`) and push (`git push`) — do not rewrite history on a shared branch. Re-run
   the Codex review if you changed anything substantive.

6. **Merge.** Once the reviews are clean and CI is green, merge:
   `./scripts/ship.sh --merge`  (squash-merges the PR and deletes the branch).
   If branch protection requires checks that are still running, prefer
   `gh pr merge --squash --delete-branch --auto` so it merges automatically when green.

7. **Report.** Print the merged PR URL, the Codex verdict, and a one-line summary of what
   shipped.

Never bypass `.claude/hooks/guard_frozen.sh`. Never edit `versioning/`, `audit/`,
`services/intelligence/**/crosswalk/`, or `rules_frozen*` as part of shipping a feature.
