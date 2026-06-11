# ADR-015 — BAG ePL Spezialitätenliste (FHIR R5) ingestion

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
BAG ships the Spezialitätenliste FHIR-only from June 2026 — a monthly NDJSON bulk export, one IDMP `ch-idmp-bundle` per line, ~6 800 products / ~10 400 reimbursed packages. It is the platform's format-diversity proof: a hierarchical FHIR R5 resource graph must harmonise into the same canonical `TariffRecord` ([ADR-003](003-canonical-record-model.md)) as EAL's flat XLSX, with no AI on the value path.

## Decision
We ingest SL with a dedicated streaming adapter (`adapters/bag_epl.py`) under these mapping rules:
- **Package granularity** — one `TariffRecord` per *reimbursed package* (the SL line item, a `PackagedProductDefinition`), not per product; that is the billing grain.
- **GTIN as the join key** — `tariff_code` = the package GTIN (`urn:oid:2.51.1.1`, prefix 7680). A reimbursed package with no GTIN cannot be keyed: it fails closed to a counted `parse_failure`, never a frozen record.
- **Retail price as `price_chf`** — the Publikumspreis (price-type `756002005001`) is the canonical value; the ex-factory price (`756002005002`) goes to `metadata.ex_factory_chf` as a JSON-native string. Prices are parsed `parse_float=Decimal` and never transit a binary float.
- **Money-only** — `tax_points` is always `None` (verified: zero tax points export-wide).
- **NDJSON bulk export via manifest** — `fetch()` resolves the public manifest API, then streams the static file; the parser never reads the 93 MB export into one string.
- **Filename-derived validity** — `valid_from` / `source_version` come purely from `foph-sl-export-YYYYMMDD.ndjson`, mirroring EAL, so re-ingest is deterministic and idempotent.

## Alternatives weighed
- **One record per product (MedicinalProductDefinition)** — rejected; prices, pack sizes and reimbursement status are per package, so a product-grain record cannot carry a single billing value.
- **Ex-factory price as the canonical value** — rejected; retail is the public-facing reimbursed price consumers expect; ex-factory is retained in metadata for transparency, not as the served value.
- **Skipping GTIN-less packages silently** — rejected; it would violate "a parsing failure must never produce a frozen record" and lose the deterministic count. They are surfaced as `parse_failures` instead.

## Consequences
- (+) Two structurally opposite BAG formats (flat XLSX, FHIR R5 graph) harmonise through one Pydantic model and one deterministic value path — heterogeneity is absorbed entirely in the adapter.
- (+) Fail-closed on unkeyable packages (109 export-wide) keeps the freeze set provably GTIN-keyed and the count reproducible.
- (–) The adapter carries real FHIR R5 traversal complexity (relative-reference resolution, exact extension-url matching at each nesting level, content-discriminated slices); this is tested against a 255-bundle real-data fixture and a pinned record hash. Revisit the mapping if BAG changes the IG slicing or the price-type code system.
- (–) Measured on the live run: the 47 ATC-less records whose `category` is filled by the AI seam are **not byte-stable across re-ingests with a live key** (they re-version each run, contained by UNIQUE constraints + append-only versioning with zero duplicate hashes); the deterministic core stays fully reproducible, but this re-version churn is an open follow-up pending an owner decision (see §10 reproducibility note).

*Lineage: new (replaces the retired toy `parsers/fhir_parser.py`).*
