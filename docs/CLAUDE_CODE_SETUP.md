# CLAUDE CODE SETUP — what is wired into this repo

A concise map of the Claude Code development setup: every file, what it does, the
review loop, and the autonomous git flow. For install/first-session steps see
`docs/START_GUIDE.md`; for the mode-selection matrix see `knowledge/ai-workflow.md`.

The whole setup exists to make one promise hold while moving fast: **AI never computes or
mutates a billing value.** AI assists pre-freeze and for search/explain; authoritative values
are frozen, versioned, hashed records (`AGENTS.md`, rules 1–2).

## Files at a glance

| File | Role |
|---|---|
| `.mcp.json` | Declares 3 MCP servers: **context7** (fresh library docs), **graphify** (codebase/doc graph + `query_graph`/`shortest_path`), **obsidian** (the `knowledge/` vault). Placeholder envs: `CONTEXT7_API_KEY`, `GRAPHIFY_API_KEY`, `TARIFHUB_VAULT`. |
| `.claude/settings.json` | Sets the model (**`claude-opus-4-8`**), trusts the project MCP servers, references the **codex-plugin-cc** plugin, pre-approves safe commands, and registers the hooks. |
| `.claude/hooks/guard_frozen.sh` | **PreToolUse** guard on Edit/Write/MultiEdit. Exits 2 (blocks) for edits to `versioning/`, `audit/`, `services/intelligence/**/crosswalk/`, and `rules_frozen*`. |
| `.claude/agents/codex-reviewer.md` | Subagent that delegates the diff to **Codex** (codex-plugin-cc / `codex exec`); read-only; returns findings. |
| `.claude/agents/determinism-auditor.md` | Subagent that runs the determinism-boundary tests + scans for LLM imports on value paths + checks frozen paths in the diff. |
| `.claude/agents/security-reviewer.md` | Subagent for secrets/injection/deps + the patient **de-identification boundary** (rule 7) + the read-only contract. |
| `.claude/commands/ship.md` | `/ship` — the autonomous branch→commit→push→PR→review→merge flow. |
| `.claude/commands/review-codex.md` | `/review-codex` — independent Codex review of the current diff (no merge). |
| `.claude/commands/new-source.md` | `/new-source` — scaffold an ingestion adapter (pre-freeze; follows the parser + source-loader pattern). |
| `.claude/commands/arc42-update.md` | `/arc42-update` — sync `docs/arc42/*` (+ an ADR) with a change, rebuild the MkDocs site. |
| `scripts/bootstrap-github.sh` | `gh repo create tarifhub --private --source=. --remote=origin --push` + branch protection on `main`. (gh local-only.) |
| `scripts/ship.sh` | The git/gh mechanics behind `/ship`: branch, Conventional Commit, push, PR, Codex review, `--merge`. |
| `scripts/setup-claude-code.sh` | Installs Codex CLI + codex-plugin-cc, graphify (+git hook + Obsidian export), mattpocock/skills; notes context7 via `.mcp.json`. |
| `knowledge/` | The Obsidian vault (second brain): `00-index`, `ai-workflow` (journal + Vibe/Spec/Agentic matrix), `decisions/`, `research/`, `daily/`. |
| `CLAUDE.md` / `AGENTS.md` | Project memory + the seven non-negotiable rules (shared by Claude Code and Codex). |

## The hooks (the determinism guardrails)

- **PreToolUse** (`Edit|Write|MultiEdit`) → `guard_frozen.sh`. Blocks any agent — orchestrator
  or subagent — from editing frozen/protected paths. Exit 2 surfaces a clear message.
- **Stop** → runs `pytest -q` in **ingestion** and **intelligence**, plus an explicit run of
  the **determinism-boundary tests**. If red, the task is not done.
- **SubagentStop** → runs the determinism-boundary tests so a *parallel* subagent can't finish
  across a broken freeze line. This is what makes `/ultracode` safe here.

(Serving is Python too: its determinism gate is `uv run pytest tests/test_determinism_boundary.py`
— the same Python AST check that runs in **ingestion** and **serving**, asserting no LLM client is
importable on the value path. Run in CI as a pre-PR gate.)

## The review loop (Codex reviews every PR)

Cadence: **per PR / per logical task**, not per keystroke — automated by `/ship`.

```
write (Claude, Opus 4.8)
   └─ /ship "feat(scope): …"
        1. fast determinism tests (local guard)
        2. branch → Conventional Commit → push → gh pr create        [scripts/ship.sh]
        3. review IN PARALLEL:
             • codex-reviewer  (independent OpenAI Codex 2nd opinion)
             • determinism-auditor (no LLM on a value path; frozen paths intact)
             • security-reviewer  (secrets/injection/deps; de-identification boundary)
        4. address blockers/majors → commit → push (re-review if needed)
        5. merge once reviews clean + CI green                        [scripts/ship.sh --merge]
```

Codex is the independent reviewer: a *different* model family catches what the author's model
misses. If Codex isn't installed, `/review-codex` says so and points at
`scripts/setup-claude-code.sh` — it never silently substitutes a Claude-only review.

## The autonomous git flow (you never run git by hand)

Claude Code performs **all** git/gh operations (`AGENTS.md`). Two scripts encapsulate it:

- **`scripts/bootstrap-github.sh`** (once): init/commit if needed, `gh repo create … --private
  --source=. --remote=origin --push`, then branch protection (require the `devsecops gates` CI
  check, linear history, no force-push, conversation resolution) and enable squash auto-merge.
- **`scripts/ship.sh`** (per task): validates the Conventional Commit subject, runs the fast
  determinism tests, derives a `type/slug` branch, commits, pushes, opens the PR, triggers the
  Codex review (writes `.codex-review.md`), and — with `--merge` — squash-merges and deletes
  the branch once checks pass.

> **Sandbox caveat:** `gh`, `claude`, and `codex` are **not** in the build sandbox/CI. Every
> remote action runs on your machine (gh authenticated there). The orchestrator only git-inits
> locally and leaves these scripts ready.

## Knowledge tooling

- **graphify** = structural brain of the code (what's wired to what); MCP + post-commit
  auto-rebuild + `graphify --obsidian knowledge` export into the vault.
- **Obsidian vault** (`knowledge/`) = human brain (why we decided things).
- **context7** = fresh external library docs (FastAPI/FHIR/Next.js).
- **mattpocock/skills** = composable engineering skills that complement, not replace, the
  spec-driven spine.

See `DevSetup/TarifHub_ClaudeCode_Setup_EN.md` for the full tool evaluation and
`knowledge/decisions/0001-adopt-claude-code-ultracode-codex-review.md` for the rationale.
