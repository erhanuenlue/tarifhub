# One-time setup

## 0. Decide the starting point (do this consciously)

Two options:

- **A — Continue the existing repo (recommended):** your working repo (`Documents/Tarif/tarifhub`) already has the pipeline, freeze, tests and arc42 chapters. Copy this bundle over it: `CLAUDE.md`, `AGENTS.md`, `.claude/`, `.mcp.json`, `prompts/`, `vault/`, `docs/` (its mkdocs.yml replaces the old one), `deploy/`, `.github/`, `tools/` (Shipboard), `.env.example`, `.gitignore`. Delete the old `.claude/commands/`, the old 6–10 agent set, `scripts/ship.sh`, and the graphify hooks — this setup replaces them. Keep all real code, tests, fixtures, ADRs. **The exact command sequence: `QUICKSTART.md`.**
- **B — Greenfield:** start from this folder, `git init`, and let session 1 (FIRST_PROMPT.md) scaffold services from the architecture doc. Only sensible if you decide the existing code is more burden than asset — it isn't; choose A.

The older environments (`tarifhub_Master/dev`, `tarifhub-fable`) are **superseded by this bundle** — archive them, don't run them in parallel.

## 1. Tools

```bash
# macOS
brew install uv gh k3d helm kubectl
brew install --cask docker        # or Docker Desktop already installed
npm install -g @anthropic-ai/claude-code@latest   # latest stable
gh auth login
```

Optional but valuable (CAS multi-tool evidence): OpenAI Codex CLI for the independent reviewer; VS Code + Copilot for the "course tools" mention in the writeup.

## 2. Secrets

```bash
cp .env.example .env   # create it: TARIFHUB_DB_URL, TARIFHUB_REVIEW_THRESHOLD=0.85, ANTHROPIC_API_KEY
```

`.env` is git-ignored and read-denied to Claude (settings.json). The pipeline runs without `ANTHROPIC_API_KEY` (deterministic fallback) — tests rely on that.

## 3. Repo + hooks

```bash
chmod +x .claude/hooks/*.sh
git init && git add -A && git commit -m "chore: fable5 workspace baseline"
gh repo create tarifhub --private --source=. --push   # Claude can also do this in session 1
```

## 4. Docs site & publishing (the deliverable)

The architecture documentation is a MkDocs Material site, configured in `docs/mkdocs.yml` (on Option A: **replace** the old repo's mkdocs.yml with this one — it adds the PDF export and the AI-method chapters).

```bash
pip install mkdocs-material mkdocs-print-site-plugin
mkdocs serve -f docs/mkdocs.yml          # live preview at :8000
mkdocs build -f docs/mkdocs.yml --strict # what CI runs
```

- **Publishing:** push to `main` → `.github/workflows/docs.yml` deploys to GitHub Pages. One-time: repo **Settings → Pages → Source: GitHub Actions**, and set `repo_url` in mkdocs.yml.
- **The Moodle PDF:** open the deployed site's **"Full document (PDF)"** page (print-site plugin) → browser print → save as PDF → repo URL is on it via the header. That is the hand-in artifact.

## 5. Second brain (Obsidian) — live, automatic

The repo **is** the knowledge source of truth; the `brain_sync` hook keeps it shaped for Obsidian at every session end: it regenerates `vault/00-index.md` (a current map of all ADRs, journal entries, learnings, reflection notes) so nothing is forgotten or orphaned. Two ways to plug it into your brain:

1. **Recommended:** open the repo folder itself in Obsidian (or symlink it into your main vault: `ln -s ~/path/tarifhub ~/ObsidianVault/tarifhub-dev`). You see code-adjacent knowledge live, links work, zero copying.
2. **Mirror mode:** set `OBSIDIAN_VAULT=/absolute/path/to/your/vault` in `.env` → the hook copies `vault/` + `docs/adr/` + `LEARNINGS.md` into `<vault>/tarifhub/` after each session (one-way; the repo stays canonical).

What lands in the brain automatically: every ADR (architecture memory), every journal day (process memory), the decision matrix and Fazit notes (reflection memory), and the regenerated index tying it together. The strategy corpus notes live in `tarifhub-fable5/07_Vault/` — drop that folder in once.

## 6. Model

```bash
claude
/model opus         # Opus 4.8 (orchestrator). Pinned in .claude/settings.json
```

Note: the orchestrator is Opus 4.8 (Fable 5 was used through 22 June 2026, when access ended). The model is pinned once in .claude/settings.json; switch with tools/switch_model.sh.

## 7. Session 1

Paste `prompts/01_foundation_reconciliation.md` (= FIRST_PROMPT.md) into Claude Code. It runs the Block-0 plan from the CAS Dossier: repo reconciliation → live `ai_map` → journal start. The full road to submission is `prompts/01–07`.

## Sanity checklist after session 1

- [ ] `uv run pytest -q` green offline
- [ ] `ai_map` makes a real Claude call when `ANTHROPIC_API_KEY` is set (and falls back cleanly without)
- [ ] `vault/daily/<today>.md` exists and is curated (not the raw skeleton)
- [ ] `guard_frozen` actually blocks an edit to `services/ingestion/versioning/` (try it once — ask Claude to touch it and watch it refuse)
- [ ] CI green on GitHub; Pages workflow deployed the docs site
- [ ] `vault/00-index.md` regenerated after the session (brain_sync ran); if `OBSIDIAN_VAULT` is set, `<vault>/tarifhub/` exists
