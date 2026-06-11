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

The section below documents measured harmonisation evidence for the determinism, reproducibility and review-rate rows (EAL run 2026-06-11: 1 279/1 279 frozen, review rate 0.0 %; SL run 2026-06-11: 10 299 frozen, review rate 1.08 %, with a measured reproducibility caveat on the 47 AI-gap records — see below).

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

### BAG Spezialitätenliste (SL) — per 01.06.2026, run 2026-06-11 22:07–22:16 UTC

Full official list (FHIR R5 NDJSON, one `ch-idmp-bundle` per line, sha256
`2dece0dad13f1f54b33c4bb41044ee8bda85b2dc2103108f7462605af916ca18`, CC0-1.0) through
the live pipeline into **PostgreSQL 16 + pgvector** with multilingual-e5-large
embeddings; `ANTHROPIC_API_KEY` set, review threshold 0.85. All numbers below are
cross-checked against the append-only `audit_log` and the live DB; full run evidence
(queries + verbatim results, API smoke) is at
[`docs/evidence/2026-06-12-sl-live-ingest.md`](../evidence/2026-06-12-sl-live-ingest.md).

| metric | value |
|---|---|
| bundles in | 6 763 |
| reimbursed packages | 10 408 |
| records frozen (GTIN-keyable) | 10 299 (every record carries an e5 embedding + an append-only audit entry) |
| skipped (idempotent) | 0 |
| parse failures (package without GTIN, fail-closed) | 109 (never frozen) |
| flagged for review | 111 — **review rate 1.08 %** (target < 15 %) |
| AI-assisted records | 47 (all `ai_fields=["category"]`; see note) |
| confidence distribution | 10 188 @ 1.0 · 111 @ 0.75 |
| wall clock | 574 s incl. e5 embedding (~18 rec/s) |

![SL confidence histogram](../img/sl_confidence_hist_2026-06-01.png)

**Honest note on the AI seam.** SL is *born-trilingual* — every product carries DE/FR/IT
names — so the fill-only `ai_map` seam ([ADR-005](../adr/005-single-ai-seam.md)) never
touches a designation. The only gap it fills is `category`: 47 records are ATC-less
nutritional / special-diet products (Milupa, Nutricia and similar) for which the
deterministic mapper has no category, and the gap-gate therefore invokes Claude with
`ai_fields=["category"]`. The other 10 252 records are gap-free and made zero API calls.
Billing values are structurally unreachable by the model. Separately, the 111
flagged-for-review records all score exactly 0.75 — the single `−0.25` no-value penalty
— i.e. they are the reimbursed packages carrying **no retail price**: keyable and frozen
with the price gap left `None`, then routed to review (the EAL `nach Aufwand` precedent).
That is a different set from the 47 AI-`category` fills (a record with price, category,
unit and trilingual names scores 1.0). See the
[evidence doc](../evidence/2026-06-12-sl-live-ingest.md) §2b for the derivation.

**Three real before/after `ai_map` category fills** (criterion 16, from the live ingest):

| GTIN | designation (DE) | category before → after |
|---|---|---|
| 4003053090963 | Milupa OS 2-prima 1-8 Jahre | ∅ → `Spezialnahrung` |
| 4003053091007 | Milupa GA 2-prima ab 1 Jahr | ∅ → `Diätetische Lebensmittel` |
| 4003053091212 | Milupa PKU 2-mix Kind | ∅ → `Spezialnahrung bei Phenylketonurie` |

**Honest note on the fail-closed path.** 109 of the 10 408 reimbursed packages
reference a `PackagedProductDefinition` that carries no `packaging.identifier` (no
GTIN). Since GTIN is the frozen join key, such a package cannot be keyed — the
adapter emits a `_parse_failure` marker, the pipeline counts it in
`PipelineReport.parse_failures`, and **no frozen record is produced**. This is the
engineering rule "a parsing failure must never produce a frozen record" exercised on
real data, not a contrived test (the 255-bundle fixture reproduces 11 such cases).

**Honest note on reproducibility (measured).** Re-running the *identical* export with a
live key: every deterministic record skips idempotently (matched `record_hash`), but the
**AI-gap records re-version** — 34 re-versioned on the first re-run, 21 on the second.
For example GTIN 4003053091007 moved v1 `Diätetische Lebensmittel` → v2
`Spezialnahrung / Stoffwechseldiät` → v3 `Spezialnahrung bei Stoffwechselstörungen`,
and one v2 fill carried a literal `ä` escape artifact. Live category fills are **not
byte-stable across runs**. This was contained rather than catastrophic: the UNIQUE
constraints + append-only versioning produced **zero duplicate hashes**, every variant
is audit-logged at 0.75 confidence and routes to the review queue. Stated precisely: the
reproducibility target holds **unconditionally** for gap-free sources (EAL: zero AI
calls) and for SL's 10 252 gap-free records; for the 47 AI-gap records it holds **only
without a live key**. The deterministic core is reproducible; the live-fill seam is not,
which is exactly why fills are never trusted as final and always land in review. This is
tracked as an open follow-up (re-version churn on re-ingest with a live key — decision
pending with the owner; cf. [ADR-015](../adr/015-epl-sl-fhir-ingestion.md)).

### Per-source comparative summary

| | EAL (Analysenliste) | SL (Spezialitätenliste) |
|---|---|---|
| source format | flat XLSX, 3 parallel sheets | hierarchical FHIR R5 NDJSON (IDMP graph) |
| join key | position number (`Pos.-Nr.`) | GTIN (`urn:oid:2.51.1.1`, prefix 7680) |
| value type | tax points (`Decimal`) | retail price CHF (`Decimal`), money-only |
| languages | DE canonical, FR/IT by sheet join | DE/FR/IT all present per product (born-trilingual) |
| records frozen | 1 279 | 10 299 (109 GTIN-less packages fail-closed, never frozen) |
| review rate | 0.0 % | 1.08 % (111 of 10 299) |
| AI-assisted records | 0 (complete feed) | 47 (ATC-less products → `category` fill only; designations born-trilingual) |

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

### AI-seam demonstration on real EAL positions (FR/IT withheld)

To evidence the live seam on real data, three real positions were re-mapped with
their FR/IT designations withheld (simulating a German-only feed); Claude
(structured output, fill-only) filled the gaps, graded against BAG's own
official translations. **In-memory demonstration — never stored as frozen records.**

| Pos. | designation (DE) | AI fr / BAG fr | AI it / BAG it | billing fields |
|---|---|---|---|---|
| 1000 | 1,25-Dihydroxy-Vitamin D | `1,25-dihydroxy-vitamine D` / identical ✓ | `1,25-diidrossi-vitamina D` / `1,25-diidrossivitamina D` (hyphenation) | byte-identical |
| 1734 | Troponin, T oder I | `Troponine, T ou I` / identical ✓ | `Troponina, T o I` / `Troponina (T o I)` (punctuation) | byte-identical |
| 3550 | Toxoplasma gondii, IgG-Avidität | `Toxoplasma gondii, avidité des IgG` / identical ✓ | `Toxoplasma gondii, avidità delle IgG` / identical ✓ | byte-identical |

### AI-seam demonstration on real SL packages (FR/IT withheld)

SL is born-trilingual, so the live ingest never needed the seam for designations. To
evidence it on SL data anyway, three real packages were re-mapped with their FR/IT
product names withheld (simulating a German-only feed); Claude (structured output,
fill-only) filled the gaps, graded against BAG's own official translations.
**In-memory demonstration — never stored as frozen records; billing fields
(`price_chf`, `tax_points`) are byte-identical in all three.**

| GTIN | designation (DE) | AI fr / official fr | AI it | result |
|---|---|---|---|---|
| 7680672760056 | Ezetimib-Rosuvastatin Viatris Filmtabl 10/10mg | `Ezetimib-Rosuvastatine Viatris cpr pell 10/10mg` / official `Ezetimib-Rosuvastatin Viatris cpr pell 10/10mg` | `Ezetimibe-Rosuvastatina Viatris cpr riv 10/10mg` | partial — clinically correct, abbreviation/orthography style differs |
| 7680672760063 | Ezetimib-Rosuvastatin Viatris Filmtabl 10/10mg (28 cpr) | `Ézétimibe-Rosuvastatine Viatris cpr pell 10/10mg` (accented form) | as above | partial — clinically correct, accents/abbreviation diverge from official |
| 7680661410023 | Fosfomycin-Mepha Plv 3 g | **null** | **null** | correct conservative refusal — the designed fill-only behaviour when not confident |

The fills are clinically correct but diverge from BAG's official *compact-abbreviation*
style (e.g. `cpr pell` vs the model's expanded/accented forms); the model also correctly
returned `null` for both languages on the third package rather than guess. In a real gap
scenario every one of these lands in the review queue at 0.75 confidence
([ADR-013](../adr/013-demo-scope.md)) for a human decision — never silently frozen. AI
provenance (`ai_model`, `ai_fields`, `ai_status`) is recorded in record metadata; billing
values are structurally unreachable by the model ([ADR-005](../adr/005-single-ai-seam.md)).

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
indexed passages correctly but embedded queries through the **passage path**
(`"passage: "` prefix instead of the e5-expected `"query: "` prefix), degrading
cross-lingual alignment — French `hématocrite` ranked the exact record (EAL 1375,
*Hämatokrit, zentrifugiert*) at 3, not 1. The fix applies the `"query: "` prefix on the
serving search path (stored passage vectors are unchanged). `tools/search_eval/` runs a
12-query DE/FR/IT/EN labelled set both ways and reports rank, MRR@5 and recall@5. Live
run on the EAL corpus (1 279 records) 2026-06-11 — full tables + trade-off analysis in
[`docs/evidence/2026-06-11-fr-ranking-eval.md`](../evidence/2026-06-11-fr-ranking-eval.md).

| query (lang) | expected code | rank — prefix passage | rank — prefix query |
|---|---|---|---|
| hématocrite (fr) | 1375 | 3 | 2 |
| Hämatokrit (de) | 1375 | 1 | 1 |
| vitamin D blood test (en) | 1006 | 1 | 1 |
| glicemia (it) | 1356 | 3 | 2 |

| metric | prefix passage (baseline) | prefix query (the fix) |
|---|---|---|
| MRR@5 | 0.681 | 0.597 |
| recall@5 | 0.833 | 0.917 |

The query prefix is a deliberate **trade-off**: cross-lingual recall@5 improves +0.084
(both Italian misses recovered, French `hématocrite` 3 → 2 — the Block-0 defect), while
MRR@5 dips −0.084 as several rank-1 hits slip to rank 2, mostly cosmetic same-name `.01`
billing-variant swaps (e.g. 1356 ↔ 1356.01, both *"Glukose"*). **Decision:** the query
prefix ships — it is the e5-correct usage and cross-lingual recall is the problem Block-0
exposed. The documented follow-up (extend passage text with FR/IT designations + re-embed
the corpus) stays open, since `hématocrite → 1375` is not yet rank 1 (a broader Hämatogramm
panel, 1372.01, outranks the exact record).

**Method:** each query is embedded both ways via the repo's own `get_embedder` — the
passage path (`"passage: "`, the faithful Block-0 production baseline) and the query path
(`"query: "`, the fix) — ranked with the same pgvector cosine SQL the serving API uses,
against the frozen EAL set. (MRR is computed over the top-5 retrieved, hence MRR@5.)
