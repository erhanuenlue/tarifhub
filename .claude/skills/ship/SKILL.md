---
name: ship
description: Land a finished tarifhub change in five steps — confirm scope, run the applicable checks, review the change, handle PR and CI only when Erhan explicitly asks, report. Invoke when work is ready to land or a prompt ends with "then /ship".
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Agent
---

Ship the current change. Commit, push, open a PR or merge only when Erhan has explicitly asked for that step in this session; without that request, stop after step 5 and leave the working tree as it is.

1. **Confirm scope.** State what the change is meant to do, then list what it touches: `git status --porcelain` and `git diff --name-only main...HEAD`. Anything beyond the request, or an unclear request, is a question for Erhan before you go on.
2. **Run the applicable checks** from the AGENTS.md definition of done: `uv run --no-sync pytest -q` and `uvx ruff check .` in each touched service; `mkdocs build -f docs/mkdocs.yml --strict` and `python3 tools/cas_check.py --ci` when `docs/` changed; `npm run lint && npm run build && npm test` when `apps/tarifguard/` changed. A result already obtained counts only under the reuse rule at the end of the definition of done. Start containers only when the change alters runtime behaviour the offline suites cannot show, or when Erhan asks. Quote failures verbatim, fix, re-run.
3. **Review the change.** Read the full diff yourself. Confirm that neither listing from step 1 contains a freeze-line path. For a `services/` diff, work through the determinism-boundary checklist (`.claude/agents/determinism-auditor.md`); for secrets, input parsing, the de-identification seam or internet-facing code, the security focus list (`.claude/agents/security-reviewer.md`). When a second model family adds something concrete, run the Codex review yourself (read-only commands in `.claude/agents/codex-reviewer.md`). Dispatch a reviewer agent only when Erhan has authorized delegation for this task (CLAUDE.md) and a fresh context adds something concrete; give it step 2's results to reuse instead of re-running them, and block on its result.
4. **PR and CI, only on explicit request.** Branch first if on `main` (`feat/…|fix/…`), make small Conventional Commits, open the PR with `gh pr create` (what and why, checks run, review notes), then `gh pr checks --watch`; the determinism-boundary step must show in the CI log. Merge with `gh pr merge --squash --delete-branch` only when Erhan asked for the merge and every merge condition in the AGENTS.md Git convention holds; re-check each one immediately before merging.
5. **Report.** Files changed; checks run with their results; results reused and why they still apply; checks skipped and why; review findings and what happened to each; remaining risks; git state (uncommitted, committed, pushed, PR open, merged).

If a step fails and one fix attempt does not resolve it, stop and report instead of looping.
