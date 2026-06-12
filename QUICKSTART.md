# Quickstart — from zero to shipping

The operational runbook: machine setup → repo assembly → first session → the daily loop. Detail lives in `SETUP.md`; this is the order you do things in.

## 0 · One-time machine setup (~15 min)

```bash
brew install uv gh k3d helm kubectl          # toolchain
# Docker Desktop: install & start it
npm install -g @anthropic-ai/claude-code@latest   # needs v2.1.170+ for Fable 5
gh auth login                                 # GitHub CLI
```

**Codex: already in place on this machine** — both the CLI and the official Claude Code plugin are installed. The `codex-reviewer` agent prefers the plugin's native integration and falls back to the CLI; nothing to configure. (Fresh machine someday: install the OpenAI Codex CLI + plugin, or skip — the reviewer reports "skipped" and the pipeline continues.)

## 1 · Assemble the working repo (Option A — your existing repo, ~10 min)

```bash
cd ~/Documents/Tarif/tarifhub                 # your existing repo

# bring in the bundle (note: tools/ is part of it now)
B=~/Documents/Claude/Projects/Tarif/tarifhub-fable5/06_Dev/tarifhub
cp -R $B/{CLAUDE.md,AGENTS.md,.claude,.mcp.json,prompts,vault,docs,deploy,.github,.env.example,.gitignore,tools} .

# retire the old generation (replaced by the bundle)
rm -rf .claude/commands scripts/ship.sh       # old commands & ship script
# delete old agents that aren't in the new set; keep all real code, tests, fixtures

cp .env.example .env                          # then edit: ANTHROPIC_API_KEY (+ OBSIDIAN_VAULT optional)
chmod +x .claude/hooks/*.sh tools/shipboard/emit.sh

git checkout -b cas-build && git add -A && git commit -m "chore: fable5 pipeline workspace"
git push -u origin cas-build                  # gh repo create tarifhub --private --source=. --push  (first time only)
```

One-time on GitHub — **repository-level** settings, not your account settings (the account page only shows "Verified domains", which you don't need): open `github.com/<you>/tarifhub` → **Settings** → sidebar *Code and automation* → **Pages** → *Build and deployment* → **Source: GitHub Actions**. No branch, no domain — the site publishes to `https://<you>.github.io/tarifhub/`. Set `repo_url` in `docs/mkdocs.yml`.

> **Private-repo caveat:** on a free plan, Pages needs a **public** repo. Recommended path: develop private, then in Block 3 (site-publishing week, `prompts/07`) flip the repo to public (Settings → General → Change visibility) and select the Pages source the same day — the repo must be grader-reachable by 5 July anyway. Until then, `mkdocs serve -f docs/mkdocs.yml` covers preview and PDF export locally. (`.env` is git-ignored and gitleaks gates every push, so going public is safe by construction.)

## 2 · First session (Block 0)

**Terminal A — the board:**
```bash
python3 tools/shipboard/shipboard.py          # → http://localhost:8787  (try --demo once to see it)
```

The board shows three layers: the **session strip** (status, context gauge vs the 1M window, tokens in/out, cache-hit %, est. cost, turns/prompts/tools — live from the session transcript), **active agent chips**, and the **9 pipeline phases**. Phases stay pending until `/ship` runs — that's honesty, not a bug. Note: the session strip needs the `session_track` hook, which arms when a Claude session **starts** in the repo — after pulling new hooks, restart the Claude session (and the board server) once.

**Terminal B — the work:**
```bash
claude
/model fable
/effort ultracode      # build/ship sessions: xhigh + auto-orchestration; effort floats per task (medium↔xhigh)
# paste the full text of prompts/01_foundation_reconciliation.md (pick the "Option A" context line)
```

What happens, and where you're needed:

1. Claude plans, then works (reconciliation audit → live `ai_map` → evidence). Watch the board.
2. When it reports done with evidence, type **`/ship`**.
3. **Phase 01 stops for you:** it presents the plan of what's being shipped — read it, correct it, approve it.
4. Phases 02–08 run: Opus implements fixes if needed, gates, parallel reviews (verifier always; determinism for `services/`; security when relevant; **Codex on architectural diffs or when you say "include codex review"**), PR + CI, Sonnet's runtime verification, the consolidated report.
5. **Phase 09 merges itself when the green-contract holds** (CI fully green incl. security, all findings dispositioned, no unauthorized frozen-path change, tree clean) and tells you what merged and why it qualified. Anything less **stops for you** with the failing condition named.
6. Before closing: open `vault/daily/<today>.md` — curate the drafted journal entry to 3–6 honest lines. **This is graded material; 2 minutes, every working day.**

First-session sanity (from SETUP.md): `pytest` green offline · `ai_map` makes a real Claude call with the key set · ask Claude to edit `services/ingestion/versioning/` once and watch `guard_frozen` refuse · CI green · Pages live.

## 3 · The daily loop (→ 5 July)

- **One sitting = one prompt = one shipped outcome.** The road: `prompts/02` (spec & design artifacts) → `03` (FHIR second source) → `04` (services + MCP) → `05` (console) → `06` (validation evidence) → `07` (documentation + Fazit + submission). Block plan and gates: CAS Dossier §7.
- **Prompts are the mission; `/ship` is the landing.** Every prompt ends in `/ship` automatically. For ad-hoc changes between prompts, just describe the change and say `/ship` when it's ready — the pipeline scales down fine for small diffs.
- `/cas-status` once or twice a week: honest floor check against the rubric, evidence-based.
- The board, the journal hook, brain_sync and the vault auto-commit run themselves; merges land themselves on green. Your only recurring duties: **approve plans, curate the journal** — and answer the rare gate when the green-contract doesn't hold.
- After a fresh clone or any `graphify hook install`: run `tools/hooks/install.sh` — re-applies the repo-local **incremental** graph hooks (upstream's regenerate full-walk versions pollute `graph.json` and drop doc nodes; see `tools/hooks/README.md`).

## 4 · Submission week (Block 3)

`prompts/07` assembles everything: AI-tools chapter, Fazit (from your journal — your voice on the final pass), German Zusammenfassung, criterion map, PDF export with the repo URL on the cover, pre-flight checklist. Submit Sunday 5 July; Monday 00:00 is the cliff. Your open Moodle items meanwhile: the refreshed-rubric diff (~14 Jun), the Problemstellung one-pager, Modulevaluation by 22 Jun.
