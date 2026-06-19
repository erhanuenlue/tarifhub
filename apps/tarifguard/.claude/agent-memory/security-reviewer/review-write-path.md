---
name: review-write-path
description: How the human-in-the-loop /review write-back enforces the billing guard and immutability — what to re-check on changes
metadata:
  type: project
---

The `POST /review` write-back (ingestion service) is the console's ONE write path and the only mutation endpoint on the ingestion service. Its billing/immutability guarantees rest on a specific chain — re-verify all of it if any link changes:

- **Allowlist is exact-match string compare** in `review.py` `_reject_invalid_keys` against `BILLING_KEYS` + `CORRECTABLE_KEYS`. Verified airtight against whitespace/case/dotted-suffix/`metadata`/`designation` key-injection variants.
- **`model_copy(update=...)` does NOT revalidate** Pydantic constraints (negative `tax_points`, `ge=0`, would slip through if it ever reached the update dict). Safe only because billing keys are rejected before the update dict is built. If anyone adds a key to the update dict from user input, this protection is gone.
- **`requires_review` is in `HASHED_FIELDS`** (freeze_record.py) so clearing it is integrity-bound; it is re-validated + re-frozen via the real `validate()`→`freeze()` in main.py, not set directly.
- **Endpoint is unauthenticated by design** (ADR-13: console has no auth; ingestion service assumed not internet-exposed, BFF is sole client).

**Why:** A 2026-06-19 report-only review confirmed PASS. Only gaps found: no `max_length`/cardinality bound on `corrections` values (a 2MB string flows straight to SHA-256+DB) — LOW because unauthenticated-but-not-exposed.

**How to apply:** On any future diff touching review.py/main.py/tariff_repository.py review path, re-run `tests/test_review_api.py` and re-check the four bullets above before passing. SQL on this path is fully parameterised via `self._ph`; flag any f-string that interpolates a value rather than the placeholder token.
