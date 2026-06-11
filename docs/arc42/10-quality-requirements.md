# 10 · quality requirements

> Stub — populated in Block 0 (prompts/02) from the Architecture baseline v2.1 (`tarifhub-fable5/03_Architecture/`). On Option A, replace this stub with the existing repo chapter, then refresh per v2.1. *(Harmonisation results below are maintained per source run — /new-source step 6.)*

## Harmonisation results

### BAG Analysenliste (EAL) — per 01.01.2026, run 2026-06-11

Full official list (XLSX, 3 sheets DE/FR/IT, sha256 `f0e74874…`) through the live
pipeline into **PostgreSQL 16 + pgvector** with multilingual-e5-large embeddings;
`ANTHROPIC_API_KEY` set, review threshold 0.85. Identical deterministic metrics
verified on the SQLite mirror.

| metric | value |
|---|---|
| records in | 1 279 |
| records frozen | 1 279 (every record carries an e5 embedding + an append-only audit entry) |
| skipped (idempotent) | 0 |
| flagged for review | 0 — **review rate 0.0 %** |
| AI-assisted records | **0** (see note) |
| confidence distribution | all 1 279 records at 1.0 |
| wall clock | 70.6 s (incl. e5 embedding) |

![EAL confidence histogram](../img/eal_confidence_hist_2026-01-01.png)

**Honest note on the AI seam.** The official AL is complete — 1 279 parallel
trilingual rows, zero missing designations, zero missing tax points. Fill-only
`ai_map` (ADR-008) therefore correctly contributes **nothing**: a deterministic
gap-gate skips the Claude call when no fillable gap exists, so the live run made
zero API calls. The seam matters for incomplete feeds (cf. the de-only sample
fixture and future sources), not for this one — that is the designed behaviour,
not a failure.

### AI-seam demonstration on real positions (FR/IT withheld)

To evidence the live seam on real data, three real positions were re-mapped with
their FR/IT designations withheld (simulating a German-only feed); Claude
(structured output, fill-only) filled the gaps, graded against BAG's own
official translations. **In-memory demonstration — never stored as frozen records.**

| Pos. | designation (DE) | AI fr / BAG fr | AI it / BAG it | billing fields |
|---|---|---|---|---|
| 1000 | 1,25-Dihydroxy-Vitamin D | `1,25-dihydroxy-vitamine D` / identical ✓ | `1,25-diidrossi-vitamina D` / `1,25-diidrossivitamina D` (hyphenation) | byte-identical |
| 1734 | Troponin, T oder I | `Troponine, T ou I` / identical ✓ | `Troponina, T o I` / `Troponina (T o I)` (punctuation) | byte-identical |
| 3550 | Toxoplasma gondii, IgG-Avidität | `Toxoplasma gondii, avidité des IgG` / identical ✓ | `Toxoplasma gondii, avidità delle IgG` / identical ✓ | byte-identical |

4 of 6 fills exact-match the official text; the two deltas are stylistic
(hyphenation/punctuation), and both would surface in the review console for a
human decision in a real gap scenario. AI provenance (`ai_model`, `ai_fields`,
`ai_status`) is recorded in record metadata; billing values are structurally
unreachable by the model (ADR-008).

*Runtime serving evidence (Postgres + pgvector search) is captured under
`docs/evidence/`.*
