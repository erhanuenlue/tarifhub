---
name: review-writeback-path
description: How the human-in-the-loop review write-back re-freezes a new immutable version without an LLM and without touching billing values
metadata:
  type: project
---

The review write-back (TarifGuard console review form) closes the human-in-the-loop gate. Server side is `services/ingestion/src/tarifhub_ingest/review.py` (pure contract + decision logic) + `main.py` `POST /review` (validate -> freeze -> repo.add -> audit.log).

**Why:** the intelligence on this path is the HUMAN, never an LLM. It must obey the same freeze-line rules as ingest: immutable new version, billing never mutated, append-only audit.

**How to apply when auditing changes here:**
- Billing immutability is defence-in-depth: `review.py` `_reject_invalid_keys` rejects any correction whose key is in `BILLING_KEYS = ("tax_points","price_chf")` with HTTP 400, and unknown/non-correctable keys with 400. Correctable set is designation.de/fr/it, category, unit only.
- `prepare_reviewed_record` re-scores with the SAME `score` from `confidence.scorer` the pipeline uses (pipeline.py:17 and review.py:35 import the identical symbol), resets `record_hash=None` so `freeze()` can stamp fresh, and refreshes `created_at` (safe — excluded from hash). It clears `requires_review=False` by explicit human authority, independent of the confidence threshold (that is the whole point of the gate).
- Immutability: `main.py submit_review` never UPDATEs. It calls `repo.add(freeze(prepared))`, which inserts at `MAX(version)+1`. Prior frozen row and append-only `audit_log` are never rewritten.
- `requires_review` IS in HASHED_FIELDS, so clearing it always changes the hash — an approve of otherwise-unchanged content still produces a distinct hash and a real v2 (it does not collide as an idempotent no-op).
- `repo.list_flagged()` returns latest-version-per-key where `requires_review = ?` bound as Python `True`; bool is an int subclass so sqlite adapts to 1 (INTEGER col) and psycopg sends a real boolean (BOOLEAN col). Cross-engine correct.
- Re-freeze of an already-frozen record still raises ValueError (record_hash must be None before freeze()).

Guards on a record reaching freeze: 404 if no record, 409 if `not requires_review`, 409 on stale `record_hash`. So a record cannot be re-frozen via this path without being a live flagged version AND a human decision body.
