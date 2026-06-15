# Chore: public-readiness audit and hardening (pre go-live)

> **Gate-01: pre-approved by the owner (14 Jun).** Produce and log the plan (emit + plan report), then proceed without waiting. STOP only for: scope beyond this prompt, any freeze-line contact (hashing/versioning/audit-trail), a green-contract or ratchet breach, or a destructive operation.

Read AGENTS.md and CLAUDE.md. Goal: make the repository safe and credible to be made **public** for the CAS submission, without changing product behaviour. You do NOT change repository visibility (the owner does that in GitHub); you make the repo deserve it. No changes below the freeze line. Run at `/effort ultracode`.

## Scope, exactly these, each with evidence in the ship report

1. **Secret sweep (tracked tree + full history).** Confirm zero real secrets are or were ever committed: run `gitleaks detect --no-banner` (and `gitleaks detect --log-opts=--all` for history) if available; otherwise grep tracked files and `git rev-list --all` for key-shaped strings (`sk-`, `sk-ant-`, `ghp_`, `AKIA…`, `-----BEGIN … PRIVATE KEY-----`, real `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` values). Quote the result. If anything real is found, STOP and report (history rewrite is owner-authorized only).
2. **.gitignore completeness.** Verify `.env`, `.env.*`, local caches (`.shipboard/`, `graphify-out/`, `site/`, `node_modules/`, `.venv/`), and the course-internal `docs/cas/bewertungskriterien-anker.md` are ignored AND not tracked. The anchor doc must never go public (course material). Confirm `git ls-files` shows none of them.
3. **Helm dev secret hygiene.** In `deploy/helm/tarifhub/values.yaml`, change the dev default `postgres.password` from `tarifhub` to `changeme-in-production`, and make sure `db-secret.yaml` still sources it via `.Values` (no inlined secret). One-line note in the chart README/comment that production must override it. (Not a freeze-line file.)
4. **.env.example honesty.** Each `.env.example` lists every required variable with placeholder values only (no real keys), and the README/QUICKSTART points newcomers at copying `.env.example` → `.env`. Add any missing vars the services actually read.
5. **Public-facing front door.** Ensure there is: a clear top-level `README.md` (what tarifhub is, the determinism/freeze-line principle, how to run tests offline, link to the docs site), a `LICENSE` file (if none, add one, propose MIT or Apache-2.0 in the plan and use the owner's pick; default to MIT if unspecified), and that the README does not reference private/course-internal paths. Keep it honest about CAS scope (demo console, no patient data).
6. **Leftover-junk check.** Confirm `.claude/worktrees/` and `.claude/agent-memory/` are untracked (stale local artifacts), and that no `_sandbox_test*`, `*.log`, or scratch files are tracked. Remove from tracking (git rm --cached) only if safe and non-destructive to working files.
7. **Cold-start credibility.** From a clean checkout perspective, confirm `uv run pytest -q` is offline-green and the README's quickstart commands exist and are correct. Quote the test summary.

## Constraints

- No product/code behaviour changes beyond the dev password string and ignore/doc hygiene. No freeze-line files touched. No history rewriting (flag if needed; owner-only).
- Conventional Commit, branch `chore/public-readiness`, then `/ship`. Phase 09 auto-merges only under the green-contract; anything less stops for the owner.
- This does NOT make the repo public and does NOT enable Pages. Those stay the owner's manual go-live trio.

## Done means

A merged PR (CI + gitleaks green) plus a ship-report section "Public-readiness" that states, with evidence: secrets clean (tree + history), ignore-list verified, anchor doc confirmed private, helm dev password hardened, `.env.example` complete, README + LICENSE present, cold-start tests green. End with the explicit line: "Safe to make public. Remaining go-live steps are the owner's (visibility, Pages env, DEPLOY_PAGES)." Curate the journal entry.
