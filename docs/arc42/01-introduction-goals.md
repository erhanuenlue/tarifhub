# 1. Introduction and Goals

TarifHub harmonizes Swiss ambulatory tariff data from many public sources into one
canonical, versioned, machine-readable model, and serves it through adaptive APIs.

## Requirements overview

- Ingest heterogeneous public tariff sources (e.g. BAG EAL XLSX, BAG ePL FHIR).
- Harmonize them into one canonical model with AI assistance and human review.
- Freeze each accepted record as an immutable, versioned, SHA-256-hashed fact.
- Serve frozen records deterministically (REST, content negotiation) and offer AI
  semantic search/discovery over them.

## Quality goals

| Priority | Goal | Motivation |
|---|---|---|
| 1 | Determinism of billing-relevant values | A position either has 47.50 tax points or it does not; values must be reproducible and auditable. |
| 2 | Auditability / lineage | Every frozen value traces back to source, parser, confidence and validation. |
| 3 | Correctness of harmonization | Low-confidence mappings are flagged for human review, never silently trusted. |
| 4 | Extensibility | New sources and consumers without breaking the frozen contract. |

## Stakeholders

| Role | Interest |
|---|---|
| PIS/HIS software vendors | Authoritative, ready-to-consume tariff data via adaptive APIs. |
| Tariff domain experts | Trustworthy harmonization with human-in-the-loop review. |
| Platform maintainers | A small, auditable, testable system that is cheap to operate. |
