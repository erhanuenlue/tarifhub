# START GUIDE: what to install before a Claude Code session

This is the pre-flight for developing tarifhub with Claude Code (Opus 4.8) and Codex as the
automated reviewer. Install the toolchain once, authenticate, then use the "first session"
checklist every time. Copy-paste commands are below; adjust package names if an upstream
project has renamed something.

> **Everything here runs on your machine.** The build sandbox/CI does **not** have `gh`, the
> `claude`/`codex` CLIs, or your accounts. The remote repo create/push, PR creation, reviews,
> and merges all happen locally (or via Claude Code running locally on your machine).

---

## 1. Accounts / subscriptions

- **Claude Max**: for Claude Code on **Opus 4.8** (`claude-opus-4-8`).
- **GPT Pro**: for the **Codex CLI**, used as the independent PR reviewer.
- **GitHub** account (the repo is created private).

## 2. Core toolchain

| Tool | Why | Install (macOS shown; use your platform's equivalent) |
|---|---|---|
| **Claude Code** | Primary dev environment (Opus 4.8, hooks, subagents, `/ultracode`) | `npm install -g @anthropic-ai/claude-code`, then run `claude` |
| **Codex CLI** | Independent reviewer (`codex exec`, codex-plugin-cc) | `npm install -g @openai/codex`, then `codex login` |
| **gh (GitHub CLI)** | All git/gh automation (repo, PRs, merges) | `brew install gh`, then `gh auth login` |
| **Node 20+** | Next.js apps, npx-based MCP servers, the CLIs | `brew install node` (or nvm) |
| **Python 3.12** | ingestion + intelligence + **serving (FastAPI)** services | `brew install python@3.12` |
| **uv** | Python package/venv manager for every service | `brew install uv` |
| **Docker** | Local Postgres+pgvector, MinIO, container builds | Docker Desktop |
| **k3d** or **kind** | Local Kubernetes for the Helm chart | `brew install k3d` (or `brew install kind`) |
| **Helm** | Deploy the chart | `brew install helm` |
| **Obsidian** | The `knowledge/` second brain | https://obsidian.md (point it at `knowledge/`) |

Quick version check:

```bash
claude --version && codex --version && gh --version \
  && node -v && python3 --version && uv --version \
  && docker --version && helm version --short && (k3d version || kind version)
```

## 3. MCP servers, plugins, and skills

Most of this is one script. From the repo root:

```bash
./scripts/setup-claude-code.sh
```

It installs/refreshes:

- **Codex CLI + codex-plugin-cc**: the in-Claude Codex review used by `/review-codex` and `/ship`.
- **graphify** (`npm i -g graphify`): codebase/doc knowledge graph + MCP server + a
  **post-commit git hook that auto-rebuilds the graph** + an `--obsidian` export into the vault.
  It runs `graphify init` (installs the hook), `graphify .` (first build), and
  `graphify --obsidian knowledge`.
- **mattpocock/skills**: small composable skills (`tdd`, `diagnose`, `grill-with-docs`,
  `git-guardrails-claude-code`), added via the Claude Code plugin marketplace.
- **context7**: wired via `.mcp.json` (npx `@upstash/context7-mcp`); no global install needed.

The repo's **`.mcp.json`** declares three MCP servers (context7, graphify, obsidian). Claude
Code picks them up automatically (`enableAllProjectMcpServers` is on in `.claude/settings.json`).
Fill in the placeholder env vars you care about:

```bash
export CONTEXT7_API_KEY="…"     # optional: higher rate limits
export GRAPHIFY_API_KEY="…"     # optional: only for INFERRED doc edges; code extraction is local
export TARIFHUB_VAULT="$PWD/knowledge"   # optional: Obsidian MCP vault path (defaults to ./knowledge)
```

## 4. Create the GitHub repo (once)

```bash
gh auth login                       # if not already authed
./scripts/bootstrap-github.sh       # creates private 'tarifhub', pushes, protects main
```

`bootstrap-github.sh` creates the private repo from the current directory, sets `origin`,
pushes, and applies branch protection (require the CI gate, linear history, no force-push). It
does **not** require human PR approvals: Codex is the in-loop reviewer (a solo founder can't
self-approve PRs anyway).

---

## First session checklist

1. **Open the repo in Claude Code** (`claude` in the repo root). Confirm the model is
   **`claude-opus-4-8`** (set in `.claude/settings.json`).
2. **Confirm the MCP servers are up** (context7, graphify, obsidian) and that the determinism
   hooks loaded (`.claude/settings.json`).
3. **Build the graph:** `/graphify .` (or rely on the post-commit hook), then optionally
   `graphify --obsidian knowledge` to bridge code nodes into the vault.
4. **Pick a mode** (see `knowledge/ai-workflow.md`):
   - small/reversible edit → normal mode;
   - feature touching a contract or >1 layer → spec-driven (plan mode first);
   - big, test-gated, parallelizable work → **`/ultracode`**.

5. **Develop.** Let the hooks run. Don't try to bypass `guard_frozen.sh`.
6. **Ship:** `/ship "feat(scope): summary"` → Claude branches, commits (Conventional Commits),
   pushes, opens the PR, runs the **Codex review** + determinism/security audits, addresses
   findings, then merges once CI is green. You never run git by hand.

---

## `/ultracode` + Opus 4.8 + Dynamic Workflows, and why the hooks matter

- **Opus 4.8** (28 May 2026, `claude-opus-4-8`): 1M-token context, strong agentic coding, and
  the ability to spawn **parallel subagents that each plan, execute, and verify a slice** and
  report to an orchestrator, built for codebase-scale work.
- **`/ultracode`** (28 May 2026): a session-only Claude Code setting that sends *xhigh* effort
  and auto-orchestrates **Dynamic Workflows** (research preview): many parallel agents that
  keep working until the test suite passes. This is the mode for big refactors, migrations,
  and fan-out tasks (e.g. one ingestion adapter per tariff source). Use normal mode for small
  edits.
- **Why the determinism hooks matter MORE here:** under `/ultracode`, many agents touch the
  tree at once. Any one of them could, in principle, edit a frozen path or wire an LLM client
  onto a value path. Three guardrails keep parallelism safe, and they are the reason
  `/ultracode` is allowed at all on this repo:
  1. **PreToolUse guard** (`.claude/hooks/guard_frozen.sh`) blocks edits to `versioning/`,
     `audit/`, `services/intelligence/**/crosswalk/`, and `rules_frozen*` for *every* agent
     (orchestrator or subagent), exiting 2 with a clear message.
  2. **Stop / SubagentStop hooks** run the determinism-boundary tests (ingestion + intelligence)
     so no agent can declare "done" across a broken freeze line.
  3. **The determinism-auditor + codex-reviewer subagents** independently confirm the boundary
     on the PR before merge.

Keep a **single orchestrator that owns the determinism gate**: parallelism must never become
a backdoor around the freeze line. The non-negotiable rule stands in every mode: **AI never
computes or mutates a billing value.**

See also: `docs/CLAUDE_CODE_SETUP.md` (what each wired file does), `AGENTS.md` (the seven
rules), and `knowledge/ai-workflow.md` (the Vibe/Spec/Agentic matrix).
