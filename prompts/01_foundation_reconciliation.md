# First prompt — session 1 (Block 0)

Paste this into Claude Code after SETUP.md is done. Adjust the bracketed line to your starting point.

---

Read AGENTS.md and CLAUDE.md, then plan before coding.

Context: [Option A — this is the existing tarifhub repo with the new Fable 5 control files applied / Option B — greenfield from the architecture doc]. We are in **Block 0** of the CAS plan (CAS Dossier §6): foundation honest, due Sunday 14 June.

Goal for this session, in priority order:

1. **Reconciliation audit, then fix:** verify the repo matches ADR-01 (Python-first) — serving is FastAPI with no Quarkus remnants (`tariff_model.py`, `db/schema.sql`, `ci.yml` serving job), `.venv` not committed, imports clean for the AST boundary test. Fix what isn't.
2. **Make `ai_map` live:** real Claude call (structured output, temperature 0) refining designations/category only, on the EAL XLSX source; confidence scoring routes <0.85 to the review queue; deterministic fallback without API key stays intact. Run the pipeline end-to-end on the real EAL file and show me: records in, records frozen, review rate, one before/after mapping example.
3. **Evidence:** make sure `pytest -q` is green offline, the determinism boundary test runs in CI, and today's `vault/daily/` entry is curated with what you (the AI) did, what went wrong, and what caught it.

Constraints: simplest thing that works; no new abstractions; nothing below the freeze line (guard_frozen will block you — if you hit it, tell me why instead of working around it). Verify your own claims against tool output before reporting. When done, run the verifier agent on the diff and give me its findings plus your plan for the rest of Block 0.
