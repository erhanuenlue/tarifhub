# 10 · quality requirements

## Quality goals (SMART NFRs)

Targets from Architecture v2.1 §12; validated against the measured runs below.

| Attribute | Target (MVP) |
|---|---|
| Determinism | 100% of value-serving responses are frozen records; AST boundary test green in CI on every push |
| Reproducibility | Re-running the pipeline on identical sources yields identical `record_hash` set (idempotent) |
| Harmonisation review rate | <15% of records flagged for review on the two BAG sources (tune threshold) |
| API read latency | p95 < 200 ms for single-record reads (cached), < 500 ms for search |
| Freshness | New source version reflected (frozen + served) within 24 h of publication |
| Test coverage | Core modules (model, freeze, pipeline, mapper) > 80% line coverage |

The section below documents measured harmonisation evidence for the determinism, reproducibility and review-rate rows (EAL run 2026-06-11: 1 279/1 279 frozen, review rate 0.0 %).

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
`ai_map` ([ADR-005](../adr/005-single-ai-seam.md)) therefore correctly contributes **nothing**: a deterministic
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
(hyphenation/punctuation), and both would be flagged `requires_review` and routed
to the review form (design scope, [ADR-013](../adr/013-demo-scope.md)) for a
human decision in a real gap scenario. AI provenance (`ai_model`, `ai_fields`,
`ai_status`) is recorded in record metadata; billing values are structurally
unreachable by the model ([ADR-005](../adr/005-single-ai-seam.md)).

*Runtime serving evidence (Postgres + pgvector search) is captured under
`docs/evidence/`.*

### Ranked retrieval (cross-lingual)

multilingual-e5 is trained with an asymmetric instruction scheme: indexed documents
are embedded as `"passage: …"` and search queries as `"query: …"`. The Block-0 proof
indexed passages correctly but embedded queries **raw**, degrading cross-lingual
alignment — French `hématocrite` ranked the exact record (EAL 1375,
*Hämatokrit, zentrifugiert*) at 3, not 1. The fix applies the `"query: "` prefix on the
serving search path (stored passage vectors are unchanged). `tools/search_eval/` runs a
12-query DE/FR/IT/EN labelled set both ways and reports rank, MRR and recall@5; numbers
land in the e2e phase.

| query (lang) | expected code | rank — prefix off | rank — prefix on |
|---|---|---|---|
| hématocrite (fr) | 1375 | ⟪TBD: eval run⟫ | ⟪TBD: eval run⟫ |
| Hämatokrit (de) | 1375 | ⟪TBD: eval run⟫ | ⟪TBD: eval run⟫ |
| vitamin D blood test (en) | 1006 | ⟪TBD: eval run⟫ | ⟪TBD: eval run⟫ |
| glicemia (it) | 1356 | ⟪TBD: eval run⟫ | ⟪TBD: eval run⟫ |

| metric | prefix off (before) | prefix on (after) |
|---|---|---|
| MRR | ⟪TBD: eval run⟫ | ⟪TBD: eval run⟫ |
| recall@5 | ⟪TBD: eval run⟫ | ⟪TBD: eval run⟫ |

**Method:** each query is embedded both ways via the repo's own `get_embedder`, ranked
with the same pgvector cosine SQL the serving API uses, against the frozen EAL set.
