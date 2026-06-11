# SL Live Ingest — BAG ePL Spezialitätenliste (FHIR R5) Evidence

**Date:** 2026-06-12 (run executed 2026-06-11 22:07–22:16 UTC)
**Branch:** feat/epl-sl-fhir-source
**Stack:** PostgreSQL 16 + pgvector · multilingual-e5-large embeddings · live `ANTHROPIC_API_KEY` · review threshold 0.85
**Source:** `foph-sl-export-20260601.ndjson`
**sha256:** `2dece0dad13f1f54b33c4bb41044ee8bda85b2dc2103108f7462605af916ca18`
**Export shape:** 6 763 bundles / 10 408 reimbursed packages (~93 MB)

All numbers below are cross-checked against the append-only `audit_log` and the live
DB. No rounding.

---

## 1. Canonical first-ingest run — report numbers

| metric | value |
|---|---|
| bundles in | 6 763 |
| reimbursed packages | 10 408 |
| processed (keyable rows) | 10 299 |
| frozen | 10 299 (every record carries an e5 embedding + an append-only audit entry) |
| skipped (idempotent) | 0 |
| parse_failures (GTIN-less packages, fail-closed) | 109 (never frozen) |
| flagged for review | 111 → **review rate 1.08 %** (target < 15 %) |
| AI-assisted records | 47 (all `ai_fields=["category"]`) |
| confidence distribution | 10 188 @ 1.0 · 111 @ 0.75 |
| wall clock | 574 s incl. e5 embedding (~18 rec/s) |

`10 299 frozen + 109 parse_failures = 10 408 reimbursed packages` — every reimbursed
package is accounted for: keyed and frozen, or fail-closed and counted, never dropped.

---

## 2. Database sanity checks (psql)

### 2a. Frozen SL records all carry an embedding

```
$ docker exec tarifhub-db psql -U tarifhub -d tarifhub -c \
    "SELECT count(*), count(embedding) FROM tariff WHERE tariff_system='SL';"
 count | count
-------+-------
 10299 | 10299
(1 row)
```

**Proves:** all 10 299 SL records have a non-null 1024-dim pgvector embedding.

### 2b. Review-flag and confidence distribution

```
$ docker exec tarifhub-db psql -U tarifhub -d tarifhub -c \
    "SELECT requires_review, harmonization_confidence, count(*)
       FROM tariff WHERE tariff_system='SL' AND version=1
      GROUP BY 1,2 ORDER BY 2 DESC;"
 requires_review | harmonization_confidence | count
-----------------+--------------------------+-------
 f               |                      1.0 | 10188
 t               |                     0.75 |   111
(2 rows)
```

**Proves:** 111 records flagged (1.08 %), all at 0.75; the rest at 1.0. Matches the
histogram (`docs/img/sl_confidence_hist_2026-06-01.png`, version=1 rows).

### 2c. AI-assisted records — category fills only, never designations

```
$ docker exec tarifhub-db psql -U tarifhub -d tarifhub -c \
    "SELECT count(*) FROM tariff
      WHERE tariff_system='SL' AND version=1
        AND metadata->>'ai_assisted'='true';"
 count
-------
    47
(1 row)

$ docker exec tarifhub-db psql -U tarifhub -d tarifhub -c \
    "SELECT DISTINCT metadata->>'ai_fields' FROM tariff
      WHERE tariff_system='SL' AND metadata->>'ai_assisted'='true';"
 ?column?
------------
 [\"category\"]
(1 row)
```

**Proves:** exactly 47 AI-assisted records, and the only field the model ever filled
is `category`. SL is born-trilingual, so designations needed nothing.

### 2d. Audit log — append-only, one freeze row per frozen record

```
$ docker exec tarifhub-db psql -U tarifhub -d tarifhub -c \
    "SELECT event_type, count(*) FROM audit_log
      WHERE tariff_system='SL' GROUP BY 1 ORDER BY 1;"
   event_type   | count
----------------+-------
 freeze         | 10299
(1 row)
```

**Proves:** 10 299 append-only freeze entries — one per frozen record, no in-place
mutation.

### 2e. Money-only invariant holds on real data

```
$ docker exec tarifhub-db psql -U tarifhub -d tarifhub -c \
    "SELECT count(*) FROM tariff WHERE tariff_system='SL' AND tax_points IS NOT NULL;"
 count
-------
     0
(1 row)
```

**Proves:** zero tax points anywhere in SL — the canonical `tax_points = None`
mapping rule is correct against the full export.

---

## 3. Three real category fills (criterion 16, from the live ingest)

ATC-less nutritional / special-diet products: the deterministic mapper has no
category, the gap-gate invokes Claude with `ai_fields=["category"]`.

| GTIN | designation (DE) | category before → after |
|---|---|---|
| 4003053090963 | Milupa OS 2-prima 1-8 Jahre | ∅ → `Spezialnahrung` |
| 4003053091007 | Milupa GA 2-prima ab 1 Jahr | ∅ → `Diätetische Lebensmittel` |
| 4003053091212 | Milupa PKU 2-mix Kind | ∅ → `Spezialnahrung bei Phenylketonurie` |

---

## 4. API smoke (read path)

### 4a. SL list — price-based, money-only

```
GET /api/v1/tariffs?system=SL&limit=3  →  HTTP 200
```

Kalydeco rows (a high-cost CFTR modulator) return as expected:

```json
{ "tariff_code": "...", "tariff_system": "SL",
  "designation": { "de": "Kalydeco ...", ... },
  "price_chf": "12114.85", "tax_points": null, ... }
```

**Verified:** `price_chf` = 12114.85, `tax_points` = `null` (SL is money-only). ✓

### 4b. SL single record — the pinned 3TC package

```
GET /api/v1/tariffs/SL/7680536620137  →  HTTP 200
```

```json
{
  "tariff_code": "7680536620137",
  "tariff_system": "SL",
  "designation": { "de": "3TC Filmtabl 150 mg", "fr": "3TC cpr pell 150 mg", "it": "3TC Filmtabl 150 mg" },
  "category": "J05AF05",
  "price_chf": "191.90",
  "tax_points": null,
  "unit": "60 Stk",
  "valid_from": "2026-06-01",
  "source_version": "BAG SL 2026-06-01",
  "harmonization_confidence": 1.0,
  "requires_review": false,
  "record_hash": "7a88ab04ae8599c0285bcb371a38d798adaee9f20f7464af5c871390b35076fc",
  "version": 1
}
```

**Verified:** retail `price_chf` = 191.90, `tax_points` = `null`, `record_hash` =
`7a88ab04…` — byte-identical to the pinned offline fixture hash from PR-01. ✓

### 4c. EAL intact after SL ingest (no cross-source regression)

```
GET /api/v1/tariffs/EAL/1000  →  HTTP 200
```

`tax_points` = `76.5000`, `record_hash` = `33f658ff…` (unchanged). EAL is untouched
by the SL ingest. ✓

### 4d. Search returns HTTP 501 with the stub embedder (by design)

```
GET /api/v1/search?q=Lamivudin&limit=5  →  HTTP 501
{"detail":"semantic search requires the e5 embedding backend"}
```

**Note:** the serving process for this smoke ran with the **stub** embedder, which
cannot answer semantic search — the endpoint returns 501 by design rather than
fabricate a ranking. The 10 299 stored e5 vectors (§2a) were written by the *ingest*
process (e5 backend); search is exercised against e5 in the separate serving-evidence
run (`docs/evidence/2026-06-11-postgres-serving-pgvector.md`).

---

## 5. Withheld-FR/IT AI-seam demonstration (in-memory, never frozen)

Three real SL packages re-mapped with FR/IT product names withheld; Claude
(structured output, fill-only) filled the gaps, graded against BAG's official text.
**Never stored as frozen records; billing fields (`price_chf`, `tax_points`)
byte-identical in all three.**

| GTIN | designation (DE) | AI fr | AI it | result |
|---|---|---|---|---|
| 7680672760056 | Ezetimib-Rosuvastatin Viatris Filmtabl 10/10mg | `Ezetimib-Rosuvastatine Viatris cpr pell 10/10mg` (official: `Ezetimib-Rosuvastatin Viatris cpr pell 10/10mg`) | `Ezetimibe-Rosuvastatina Viatris cpr riv 10/10mg` | partial — clinically correct, abbreviation/orthography style differs |
| 7680672760063 | Ezetimib-Rosuvastatin Viatris Filmtabl 10/10mg (28 cpr) | `Ézétimibe-Rosuvastatine Viatris cpr pell 10/10mg` (accented) | as above | partial — clinically correct, accents/abbreviation diverge |
| 7680661410023 | Fosfomycin-Mepha Plv 3 g | **null** | **null** | correct conservative refusal — designed fill-only behaviour |

The fills are clinically correct but diverge from BAG's compact-abbreviation house
style; the model also correctly returned `null` for both languages on the third
package rather than guess. In a real gap scenario all of these land in the review
queue at 0.75 confidence for a human decision — never silently frozen.

---

## 6. Reproducibility — measured re-run finding (honest)

Re-running the *identical* export with a live key:

- **Deterministic records:** all skip idempotently (matched `record_hash`), zero new
  freezes — the reproducibility target holds unconditionally for the 10 252 gap-free
  SL records (and for EAL, which makes zero AI calls).
- **AI-gap records re-version:** 34 re-versioned on the first re-run, 21 on the
  second. The live category fill is **not byte-stable across runs**.

Version chain for GTIN 4003053091007 (`Milupa GA 2-prima ab 1 Jahr`):

| version | category fill |
|---|---|
| v1 | `Diätetische Lebensmittel` |
| v2 | `Spezialnahrung / Stoffwechseldiät` (one v2 fill elsewhere carried a literal `ä` escape artifact) |
| v3 | `Spezialnahrung bei Stoffwechselstörungen` |

**Contained, not catastrophic:** UNIQUE constraints + append-only versioning produced
**zero duplicate hashes**; every variant is audit-logged at 0.75 confidence and routes
to the review queue. Precisely stated — the deterministic core is fully reproducible;
the live-fill seam is not, which is exactly why fills are never trusted as final and
always land in review. Tracked as an open follow-up (re-version churn on re-ingest
with a live key — decision pending with the owner; cf.
[ADR-015](../adr/015-epl-sl-fhir-ingestion.md)).

---

## 7. Timings

| phase | wall clock |
|---|---|
| parse + map + ai_map (47 live calls) + validate + score + freeze + e5 embed + store | 574 s total |
| effective throughput | ~18 rec/s (10 299 records) |
| run window | 2026-06-11 22:07–22:16 UTC |
