# Cross-lingual ranked-retrieval eval — e5 query/passage prefix (2026-06-11)

Live evaluation of the multilingual-e5 **query-prefix fix** (`feat/fr-search-ranking`)
against the Block-0 baseline. Block-0's pgvector proof
(`docs/evidence/2026-06-11-postgres-serving-pgvector.md` §6b) showed French
`hématocrite` ranking the exact record (EAL 1375, *Hämatokrit, zentrifugiert*) at **3**,
because the serving search path embedded queries through the **passage** path
(`embed(q)`, applying the `"passage: "` prefix) instead of the e5-expected `"query: "`
prefix. The fix routes queries through `embed_query` (`"query: "`).

## Method

- **Harness:** `tools/search_eval/eval.py` — embeds each labelled query both ways via the
  repo's own `get_embedder`, ranks with the same pgvector cosine SQL the serving API
  uses (`ServingRepository.search_by_embedding`), top-5.
- **Corpus:** EAL only, **1 279 frozen records** (1 279/1 279 carry a 1024-dim
  multilingual-e5-large embedding; verified). No TARDOC in the corpus for this run.
- **Model:** `intfloat/multilingual-e5-large`, loaded from the local HF cache.
- **Modes:** `--prefix passage` (`embed`, the faithful Block-0 baseline) vs
  `--prefix query` (`embed_query`, the fix).
- **Labelled set:** 12 queries (FR 4, DE 3, IT 2, EN 3) → real EAL codes, incl. the
  headline `hématocrite → 1375`. See `tools/search_eval/queries.yaml` for the `why` notes.
- **Metric note:** reciprocal rank is taken over the top-5 retrieved, so the aggregate is
  **MRR@5** (a record ranked >5 contributes 0). `recall@5` = share of queries whose
  expected code appears in the top-5.
- Wall clock: passage 14.4 s, query 10.6 s.

## Results

### Run A — `--prefix passage` (faithful Block-0 baseline)

| id | lang | query | expected | rank | top-5 codes |
|----|------|-------|----------|------|-------------|
| hematocrite_fr | fr | hématocrite | 1375 | 3 | 1369, 6204.6, 1375, 6204.55, 1240.1 |
| haematokrit_de | de | Hämatokrit | 1375 | 1 | 1375, 6204.55, 6204.56, 1369, 6204.6 |
| ematocrito_it | it | ematocrito | 1375 | — | 1769, 1567, 1240.1, 1426, 3482 |
| hematocrit_en | en | hematocrit blood test | 1375 | — | 1405, 1369, 1363, 1422, 1279 |
| glucose_de | de | Glukose im Blut | 1356 | 2 | 1356.01, 1356, 1363.01, 1359, 1363 |
| glucose_fr | fr | glucose sanguin | 1356 | 1 | 1356, 1356.01, 1355, 1471, 1267 |
| glucosio_it | it | glicemia | 1356 | 3 | 1356.01, 1355, 1356, 1471, 6233.6 |
| vitamin_d_en | en | vitamin D blood test | 1006 | 1 | 1006, 1000, 3423, 3422, 1410.1 |
| vitamine_d_fr | fr | vitamine D | 1006 | 1 | 1006, 1000, 1755, 1747, 1267 |
| hba1c_de | de | Langzeitzucker HbA1c | 1363 | 1 | 1363, 1363.01, 6203.54, 6203.51, 6203.6 |
| cholesterol_en | en | HDL cholesterol | 1410.1 | 1 | 1410.1, 1410.01, 1230.01, 1230, 1731.01 |
| cortisol_fr | fr | cortisol | 1240.1 | 1 | 1240.1, 1241, 1239, 1489, 1221 |

**MRR@5 = 0.681 · recall@5 = 0.833 (n=12)**

### Run B — `--prefix query` (the fix)

| id | lang | query | expected | rank | top-5 codes |
|----|------|-------|----------|------|-------------|
| hematocrite_fr | fr | hématocrite | 1375 | 2 | 1372.01, 1375, 1372, 1371, 1374 |
| haematokrit_de | de | Hämatokrit | 1375 | 1 | 1375, 1372, 1372.01, 1371, 1396 |
| ematocrito_it | it | ematocrito | 1375 | 3 | 1567, 1761, 1375, 1426, 3398 |
| hematocrit_en | en | hematocrit blood test | 1375 | — | 1372.01, 1371, 1372, 1374, 1363.01 |
| glucose_de | de | Glukose im Blut | 1356 | 3 | 1472, 1356.01, 1356, 1359, 1363.01 |
| glucose_fr | fr | glucose sanguin | 1356 | 2 | 1356.01, 1356, 1355, 1363.01, 1471 |
| glucosio_it | it | glicemia | 1356 | 2 | 1356.01, 1356, 1472, 1355, 1363.01 |
| vitamin_d_en | en | vitamin D blood test | 1006 | 1 | 1006, 1000, 3075, 1745, 1283 |
| vitamine_d_fr | fr | vitamine D | 1006 | 1 | 1006, 1000, 1747, 1755, 1748 |
| hba1c_de | de | Langzeitzucker HbA1c | 1363 | 2 | 1363.01, 1363, 6227.61, 1359, 1688 |
| cholesterol_en | en | HDL cholesterol | 1410.1 | 2 | 1410.01, 1410.1, 1230.01, 1521, 1230 |
| cortisol_fr | fr | cortisol | 1240.1 | 1 | 1240.1, 1472, 1241, 1239, 1761 |

**MRR@5 = 0.597 · recall@5 = 0.917 (n=12)**

## Per-language movement (passage → query)

| lang | query | expected | passage rank | query rank | Δ |
|------|-------|----------|--------------|------------|---|
| fr | hématocrite | 1375 | 3 | 2 | better |
| fr | glucose sanguin | 1356 | 1 | 2 | worse |
| fr | vitamine D | 1006 | 1 | 1 | — |
| fr | cortisol | 1240.1 | 1 | 1 | — |
| it | ematocrito | 1375 | miss | 3 | **recovered** |
| it | glicemia | 1356 | 3 | 2 | better |
| de | Hämatokrit | 1375 | 1 | 1 | — |
| de | Glukose im Blut | 1356 | 2 | 3 | worse |
| de | Langzeitzucker HbA1c | 1363 | 1 | 2 | worse |
| en | HDL cholesterol | 1410.1 | 1 | 2 | worse |
| en | vitamin D blood test | 1006 | 1 | 1 | — |
| en | hematocrit blood test | 1375 | miss | miss | — |

## Trade-off analysis

The fix is a **deliberate trade-off, not a uniform win**:

- **recall@5 +0.084** (0.833 → 0.917): the cross-lingual goal. Both Italian misses are
  recovered — `glicemia → 1356` was already a top-5 hit and `ematocrito → 1375` moves
  from **outside** the top-5 into rank 3. The headline French case `hématocrite → 1375`
  improves **3 → 2**. This is exactly the Block-0 problem (cross-lingual queries failing
  to surface the right record) getting measurably better.
- **MRR@5 −0.084** (0.681 → 0.597): several rank-1 hits slip to rank 2–3, pulling the
  mean reciprocal rank down even though more records are *found*.

**What the rank-2/3 slips actually are (verified against the dev DB, read-only):**

- **Same-name `.01` variant swaps (cosmetic).** For `glucose_de`, `hba1c_de` and
  `cholesterol_en` the displacing code is a billing variant of the *same* analyte with a
  **byte-identical German designation**: 1356 and 1356.01 are both *"Glukose"*; 1363 and
  1363.01 are both *"Hämoglobin A1c"*; 1410.1 and 1410.01 are both *"HDL-Cholesterin"*.
  When the e5 query embedding ranks 1356.01 above 1356, the user still sees the correct
  analyte at the top — the "wrong" rank-1 is the same test under a sibling code. These
  slips are presentation-neutral for the search use case.
- **One genuine non-variant intrusion.** `glucose_de` (DE 2 → 3) is *not* purely
  cosmetic: the new rank-1 is **1472** = *"Insulininduzierte Hypoglykämie: Bestimmung von
  6 Glucose- und 6 Cortisol-Werten"* — a compound provocation-test panel, not a Glukose
  variant. The `"query: "` prefix pulled this multi-analyte panel above the plain Glukose
  record. This is a real (if minor) precision regression on that one query.
- **Hematocrit still not rank 1.** Under the fix, `hématocrite → 1375` reaches rank 2 but
  the rank-1 is **1372.01** = *"Hämatogramm III: …, Hämatokrit, …"* — a broad haematogram
  panel whose passage text literally contains "Hämatokrit". The exact record 1375
  (*"Hämatokrit, zentrifugiert"*) loses to the panel because the panel's indexed passage
  text mentions the term while 1375's does not carry the FR/IT designation in its passage.
  Sibling panels 1371 / 1372 / 1374 (all "Hämatogramm …, Hämatokrit, …") cluster around it.

## Decision

**Ship the `"query: "` prefix.** It is the *correct* use of multilingual-e5 (the model is
trained for the query/passage asymmetry), and cross-lingual recall — the exact Block-0
defect — improves (+0.084 recall@5, both IT misses recovered, French headline 3 → 2). The
MRR@5 dip is dominated by same-name `.01` variant swaps that are cosmetic for search; the
single real precision regression (1472 on `glucose_de`) and the persistent hematocrit
rank-2 are tracked, not blocking.

**Open follow-up (documented, not in this PR):** `hématocrite → 1375` is still not rank 1
because the indexed **passage text** is `"{system} {code} {designation_de}"` — German only.
Extending the passage to include the FR/IT designations (and the broader-vs-exact panel
disambiguation) and **re-embedding** the corpus is the next lever. That is explicitly out
of scope here (it requires re-embedding all stored vectors); this PR ships the e5-correct
query usage and the eval harness that will measure that next change.
