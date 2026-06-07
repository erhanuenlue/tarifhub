# 10. Quality Requirements

## Quality tree (top priorities first)

1. **Determinism** — billing-relevant values are reproducible and never AI-derived.
2. **Auditability** — every frozen value has complete lineage.
3. **Correctness** — harmonization errors surface as review flags, not silent data.
4. **Maintainability** — small, layered, testable; tests green before done.
5. **Extensibility** — new sources/consumers without breaking the frozen contract.

## Evaluation scenarios

| Quality | Scenario | Expected response |
|---|---|---|
| Determinism | The same source is ingested twice | Identical hashes; second run freezes nothing new (idempotent). |
| Determinism | A code reviewer checks the serving value path | No LLM client is imported (enforced by a boundary test). |
| Auditability | An auditor asks where a value came from | The audit log yields source file, parser version, confidence, validation, hash. |
| Correctness | A record is missing a billing value | Confidence drops below threshold → `requires_review = true`. |
| Integrity | A stored record is tampered with | `verify()` recomputes the hash and detects the mismatch. |
| Extensibility | A new source format is added | A new parser/mapper is added; the canonical model and routes are unchanged. |
