# prompts/ — the development prompt library (Fable 5)

Seven prompts covering the road from today to submission, aligned to the course blocks and the CAS Dossier plan. They are **outcome prompts, not scripts**: Fable 5 performs best when given the goal, the constraints, and the verification — and degraded by step-by-step micromanagement written for older models. Edit the bracketed context lines; keep the constraint blocks.

| # | Prompt | When | CAS criteria it feeds |
|---|---|---|---|
| 00 | `00_one_shot_greenfield.md` | Reference only — the whole system as one outcome prompt, empty dir, no CAS context | — |
| 00b | `00b_cas_one_shot.md` | The CAS one-shot: one long run inside the prepared workspace, criteria-driven, evidence-capturing (RUN-LOG → journal) | all 18 (drafts for 15/18 — Erhan's voice required) |
| 01 | `01_foundation_reconciliation.md` | Session 1 (= FIRST_PROMPT.md) | 7, 10, 16 (`ai_map` live) |
| 02 | `02_spec_design_artifacts.md` | Block 0, days 3–5 | 1, 2, 4, 5, 8 (translation page), ADR-14 |
| 03 | `03_second_source_fhir.md` | Block 1 | 16, 7 (format diversity = the thesis) |
| 04 | `04_services_depth_mcp.md` | Block 1 | 16, 17, 11, 12 |
| 05 | `05_tarifguard_console.md` | Block 2 | 1, 4, frontend-block evidence |
| 06 | `06_validation_evidence.md` | Block 2 | 11–14, 17 (the "free points") |
| 07 | `07_documentation_fazit.md` | Block 3 | 9, 15, 18 + submission |

## Standing rules (apply to every prompt)

- Session start: Claude reads `AGENTS.md` + `CLAUDE.md` automatically. Don't re-paste project facts into prompts.
- Every session ends with: tests green (quote output) → verifier on the diff → `/ship` if shippable → **journal entry curated** (criterion 15 raw material — non-negotiable).
- `/ship` is the **9-phase multi-model pipeline** (Fable plans/orchestrates/gates · Opus implements · Sonnet verifies runtime) with two human gates: you approve the plan, you confirm the merge. Build/ship sessions run **`/effort ultracode`**; Fable allocates its own effort per task (medium↔xhigh by complexity) inside the skill's contract — gates and worker pins are invariant. Watch it live: `python3 tools/shipboard/shipboard.py` → :8787.
- The freeze line is hook-enforced. If `guard_frozen` blocks something, the prompt's answer is "tell me why", never "work around it".
- One session ≈ one prompt ≈ one mergeable outcome. Don't chain two prompts without a `/clear`.
- If a session drifts or stalls: stop, `/clear`, re-run the same prompt with one added constraint naming the failure. Fable recovers better from a fresh start than from accumulated correction debt.
