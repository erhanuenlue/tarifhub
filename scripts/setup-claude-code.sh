#!/usr/bin/env bash
#
# setup-claude-code.sh — install the Claude Code dev tooling for TarifHub.
#
# RUN THIS ON YOUR MACHINE. It installs the Codex CLI + codex-plugin-cc (the in-Claude
# reviewer), graphify (codebase knowledge graph + MCP + Obsidian export), context7 (wired via
# .mcp.json), and mattpocock/skills, and registers the Claude Code plugin marketplaces. None
# of this runs in the build sandbox / CI. `gh` is also required for the git flow but is set
# up separately (scripts/bootstrap-github.sh). See docs/START_GUIDE.md.
#
# Best-effort by design: plugin/marketplace identifiers can change, so non-critical installs
# warn instead of aborting. Confirm exact names against each project's README if one warns.
# Prereqs: Node 20+ / npm, and the `claude` CLI on PATH.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

have() { command -v "$1" >/dev/null 2>&1; }

echo "==> Checking prerequisites"
have node || { echo "ERROR: Node 20+ is required (https://nodejs.org)." >&2; exit 1; }
have npm  || { echo "ERROR: npm is required." >&2; exit 1; }
have claude || echo "WARNING: 'claude' CLI not found — install Claude Code first (see docs/START_GUIDE.md). Plugin steps will be skipped."

echo "==> Codex CLI (the independent reviewer; sign in with your GPT Pro account)"
npm install -g @openai/codex || echo "WARNING: could not install @openai/codex globally; install manually."
echo "    After install, authenticate once:  codex login"

echo "==> graphify (codebase + docs knowledge graph; MCP server + git-hook auto-rebuild + Obsidian export)"
npm install -g graphify || echo "WARNING: could not install graphify globally; see https://github.com/safishamsi/graphify."
if have graphify; then
  # Install the post-commit hook that auto-rebuilds the graph, then build it once.
  graphify init   || echo "NOTE: 'graphify init' skipped/failed — run it in the repo to install the git hook."
  graphify .       || echo "NOTE: initial graph build skipped/failed — run 'graphify .' in the repo."
  # Export the graph into the Obsidian vault so notes can link to code nodes.
  graphify --obsidian knowledge || echo "NOTE: run 'graphify --obsidian knowledge' to export into the vault."
fi

if have claude; then
  echo "==> Claude Code plugin marketplaces"
  # codex-plugin-cc: runs a Codex review from inside Claude Code (the /review-codex + /ship loop).
  claude plugin marketplace add openai/codex-plugin-cc || echo "WARNING: could not add openai/codex-plugin-cc marketplace."
  claude plugin install codex-plugin-cc@openai          || echo "WARNING: confirm the codex-plugin-cc install name in its README."

  # mattpocock/skills: small, composable engineering skills (tdd, diagnose, grill-with-docs, git-guardrails).
  claude plugin marketplace add mattpocock/skills || echo "WARNING: could not add mattpocock/skills marketplace."
  claude plugin install skills@mattpocock          || echo "WARNING: confirm the skills install name in the mattpocock/skills README."

  echo "==> context7 is wired via .mcp.json (npx @upstash/context7-mcp); no global install needed."
  echo "    Optional: export CONTEXT7_API_KEY for higher rate limits."
else
  echo "==> Skipped Claude Code plugin steps ('claude' CLI not found)."
fi

cat <<'NOTE'

==> Done (review any WARNING/NOTE lines above).

MCP servers (.mcp.json) are picked up automatically by Claude Code in this repo
(enableAllProjectMcpServers is on). Fill in the placeholder env vars you want:
  - CONTEXT7_API_KEY   (optional; higher rate limits)
  - GRAPHIFY_API_KEY   (optional; only for INFERRED doc edges — code extraction is local)
  - TARIFHUB_VAULT     (optional; defaults to ./knowledge for the Obsidian MCP)

First session: open the repo in Claude Code, confirm the model is claude-opus-4-8, run
`/graphify .` (or rely on the git hook), then use `/ship` to open reviewed PRs.
NOTE
