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

### BAG Spezialitätenliste (SL) — per 01.06.2026, run ⟪TBD: live run⟫

Full official list (FHIR R5 NDJSON, one `ch-idmp-bundle` per line, sha256
`2dece0da…`, CC0-1.0) through the live pipeline into **PostgreSQL 16 + pgvector**;
review threshold 0.85. Identical deterministic metrics verified on the SQLite mirror.
Offline-fixture figures (255-bundle slice) are quoted where a real-run metric is
still pending so the shape of the result is visible.

| metric | value |
|---|---|
| bundles in | ⟪TBD: live run⟫ (6 763 export-wide) |
| reimbursed packages | ⟪TBD: live run⟫ (10 408 export-wide) |
| records frozen (GTIN-keyable) | ⟪TBD: live run⟫ (10 299 export-wide) |
| parse failures (package without GTIN, fail-closed) | ⟪TBD: live run⟫ (109 export-wide) |
| skipped (idempotent) | ⟪TBD: live run⟫ |
| flagged for review | ⟪TBD: live run⟫ |
| confidence distribution | ⟪TBD: live run⟫ |
| wall clock | ⟪TBD: live run⟫ |

**Honest note on the fail-closed path.** 109 of the 10 408 reimbursed packages
reference a `PackagedProductDefinition` that carries no `packaging.identifier` (no
GTIN). Since GTIN is the frozen join key, such a package cannot be keyed — the
adapter emits a `_parse_failure` marker, the pipeline counts it in
`PipelineReport.parse_failures`, and **no frozen record is produced**. This is the
engineering rule "a parsing failure must never produce a frozen record" exercised on
real data, not a contrived test (the 255-bundle fixture reproduces 11 such cases).

### Per-source comparative summary

| | EAL (Analysenliste) | SL (Spezialitätenliste) |
|---|---|---|
| source format | flat XLSX, 3 parallel sheets | hierarchical FHIR R5 NDJSON (IDMP graph) |
| join key | position number (`Pos.-Nr.`) | GTIN (`urn:oid:2.51.1.1`, prefix 7680) |
| value type | tax points (`Decimal`) | retail price CHF (`Decimal`), money-only |
| languages | DE canonical, FR/IT by sheet join | DE/FR/IT all present per product (born-trilingual) |
| records frozen | 1 279 | ⟪TBD: live run⟫ (10 299 export-wide) |
| review rate | 0.0 % | ⟪TBD: live run⟫ |
| AI-assisted records | 0 (complete feed) | ⟪TBD: live run⟫ (≈55 products carry no ATC → category gap) |

### XLSX vs FHIR R5 — what format diversity costs harmonisation

The two BAG sources sit at opposite ends of the structural spectrum, and ingesting
both through one `TariffRecord` ([ADR-003](../adr/003-canonical-record-model.md)) is
the platform's harmonisation proof. **EAL** is a flat three-sheet workbook: each
tariff position is a row, the three languages are three parallel sheets joined by
position number, and a value is a single cell — harmonisation is essentially a
column-mapping plus a positional join, and a missing translation is just an empty
cell. **SL** is a born-FHIR resource *graph*: each medication is a bundle of an
IDMP `MedicinalProductDefinition` (names, ATC), one or more
`PackagedProductDefinition` (the billable line items, keyed by GTIN), and pairs of
`RegulatedAuthorization` discriminated only by a coded `type`; the entire billing
payload (retail/ex-factory prices, dossier number, cost share, listing dates) hangs
off a deeply nested `reimbursementSL` extension whose sub-extensions are
content-discriminated (by `url`, `system`, `code`, BCP-47 language) and **never by
position**. Extracting one canonical row therefore means traversing the graph,
resolving relative references (`CHIDMP…/<id>` against the package id), matching
extension urls *exactly at each nesting level* (both `reimbursementSL` and the
limitation extension carry a `status` child — flattening by name would corrupt the
data), and selecting the right slice of a polymorphic `value[x]`. Where EAL is
born-trilingual only after a join, SL is born-trilingual at the product, but pays for
it with depth: roughly five resource types and three extension-nesting levels to
reach a single price. The cost of format diversity is thus paid almost entirely in
the *adapter*, not the canonical model — `bag_eal.py` and `bag_epl.py` differ
completely while emitting the same flat row dict, and the same deterministic
mapper/validator/scorer/freeze chain runs unchanged over both. That is the design
intent of the freeze-line decomposition ([ADR-002](../adr/002-freeze-line-decomposition.md)):
heterogeneity is absorbed at the edge so the value path stays a single, auditable,
deterministic shape.

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
