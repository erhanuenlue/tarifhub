# tarifhub — Project Facts (read first)

Swiss ambulatory tariff data platform. Four layers: L0 harmonisation (AI-assisted, pre-freeze) → L1 deterministic serving API + MCP → L2 rules (post-CAS) → L3 apps (demo now). **CAS capstone due Mon 6 July 2026, 00:00.** Deliverable: the public repository + the GitHub Pages documentation site. Grading strategy lives in Erhan's corpus (CAS Dossier v3.1). The full rubric and its operative summary are kept in the git-ignored, course-internal reference under `docs/cas/` (not published); consult them locally when a criterion's exact conditions matter.

## The one inviolable rule

**No AI computes or mutates a billing value at serve time.** AI may run only (a) pre-freeze in `ai_map` (non-billing fields, schema-constrained structured output) and (b) in explain/search seams that never alter values. Frozen records are immutable: SHA-256 `record_hash` over sorted canonical content; updates are new versions; `audit_log` is append-only. `test_determinism_boundary.py` (AST check: no LLM client importable on the value path) must stay green — CI fails otherwise.

## Layout

```
services/ingestion/      L0: adapters → parsers → map_raw → ai_map → validate → score → review → freeze
services/serving/        L1 TarifCore: REST + FHIR R4, point-in-time + diff, pgvector search (read-only)
services/mcp/            L1 TarifMCP: search_tariffs, get_tariff, explain_crosswalk (read-only proxies)
apps/tarifguard/         L3 TarifGuard Console: master-detail (search→frozen record detail) + review form + labelled AI explain panel
db/                      schema.sql + migrations (Postgres 16 + pgvector; SQLite mirror for offline tests)
deploy/                  docker-compose.yml + helm/ (k3d for the CAS K8s proof)
docs/                    arc42/ (12 chapters, MkDocs Material → the deliverable site) + adr/
vault/                   CAS evidence: daily/ journal, decision-matrix.md, fazit-notes.md
```

## Stack

Python 3.12 + FastAPI + Pydantic v2 (one canonical `TariffRecord` end-to-end) · PostgreSQL 16 + pgvector (HNSW, cosine; multilingual-e5-large 1024-dim) · Claude schema-constrained structured output (pre-freeze only) · Next.js App Router (demo) · Docker + Helm/k3d · GitHub Actions (ruff, pytest, gitleaks, Trivy, Syft → GHCR) · OpenTelemetry → Prometheus/Grafana + Sentry (decided, not yet instrumented; ADR-011). ADR register: `docs/adr/` (19 decisions; ADR-01 Python-first, ADR-13 demo scope).

## Commands

```bash
uv sync                                  # per service; uv is the package manager (not pip/poetry)
uv run pytest -q                         # offline by default: SQLite mirror + stub embedder, no containers
uv run ruff check --fix . && uv run ruff format .
docker compose up -d db                  # Postgres+pgvector when a test/dev task needs the real engine
cd apps/tarifguard && npm run dev        # console on :3000; npm test = Vitest + Playwright smoke
mkdocs serve -f docs/mkdocs.yml          # the arc42 site
python3 tools/shipboard/shipboard.py     # live /ship pipeline board on :8787 (--demo seeds, --reset clears)
```

## Conventions

- **Grounding (Opus 4.8): never speculate about code you have not opened. If a file is referenced, read it before answering or editing. Investigate the relevant files before making claims about the codebase; a claim must trace to a tool result from this session.**
- **Long runs (Opus 4.8): context auto-compacts as it fills, so do not stop early for token-budget reasons. As you approach the limit, save progress and state to a scratchpad (`.shipboard/loop-checkpoint.md` in loop runs) before the window refreshes, then continue.**

- **Quality before cost (owner law, 13 Jun): the orchestrator (plan, orchestration, merge-gate,
  complex senior-level decisions) is Opus 4.8 (Fable 5 ran the early blocks; access ended 22 Jun 2026); pinned once in
  `.claude/settings.json` "model", switched with `tools/switch_model.sh` (ADR-018). Every other
  seat that exercises judgment or writes anything runs Opus 4.8 (verifier inherits the
  orchestrator). Sonnet and Haiku are banned from every seat. The independent second model family
  is OpenAI gpt-5.5 via the owner's Codex Pro login: every PR review, the final document review,
  journal curation, and a second opinion on each grade estimate. Never downgrade a model seat, an
  effort level or a review step to save tokens. Cost is reported on the board; it is never an
  argument.**

- Conventional Commits; branch `feat/…|fix/…`; squash-merge green PRs only.
- Env-only config (`TARIFHUB_DB_URL`, `TARIFHUB_REVIEW_THRESHOLD`, `ANTHROPIC_API_KEY`). Without an API key, `ai_map` falls back to deterministic `map_raw` — tests rely on this.
- The canonical model's field set is **locked, additive-only** (ADR-03). A breaking change needs a new ADR before code.
- German is the canonical designation language; FR/IT optional.
- **Documentation style (owner law, 13 Jun): no em-dashes (—) in any documentation or report text.** Use commas, colons, periods or parentheses; rewrite the sentence rather than substituting a hyphen.
- Console scope guards (ADR-13): master-detail + review form + explain panel, ~4 components, no auth, no patient data, no benchmarking. Reject scope creep in review.
- **Graders review code and documentation only — nothing gets deployed or executed by them.** Evidence that exists only at runtime must be captured into `docs/` (screenshots, CI links, coverage figures, report tables). Distribution (criterion 17) is proven by Dockerfiles/compose/Helm + CI builds + captured screenshots, not by a live cluster.
- **No Java, no JVM, anywhere — owner's decision, final.** The stack is Python + TypeScript (console) only; the rubric is being refreshed to stack-neutral wording. The docs keep a "Modern application concepts" page (arc42 §8: DI, validation, persistence abstraction, observability, container-first — as implemented in Python, citing Modulplan Lehrmittel [5]). Never propose Quarkus/Java components for any reason, including rubric optics.
- A merged change that decides something architectural → 5-line ADR in `docs/adr/`. A working session → journal entry in `vault/daily/` (the hook drafts it; `tools/curate.sh` rewrites it via Codex gpt-5.5 and appends fazit-note candidates, fully automated, owner decision 13 Jun; the pipeline is disclosed in the AI-tools chapter; the owner edits at his discretion before submission — this is graded CAS evidence).
