# ADR-016 — Canonical Decimal scale contract (stored bytes == hashed bytes)

*Status: Accepted · Date: 2026-06-12 · Decider: Erhan (+ AI-assisted analysis)*

## Context
The freeze contract ([ADR-004](004-freeze-content-hash-lineage.md)) rests on one promise: what was hashed at freeze is exactly what is stored and served, on every engine, on every re-run. The canonical model accepts arbitrary-scale `Decimal` billing values, but `db/schema.sql` declares `tax_points NUMERIC(12,4)` and `price_chf NUMERIC(12,2)`. A value with more decimal places than the column holds is **silently rounded by Postgres on insert** — so the stored bytes no longer equal the hashed bytes. That is a silent freeze-contract breach: `verify()` would fail on a record nobody knowingly changed, and the SQLite mirror (which keeps the writer's exact text) would diverge from Postgres. The scale of the database column, not the model, is the real contract; the model must honour it before freeze.

## Decision
We quantize every billing value to the canonical schema scales **pre-freeze** (`tax_points` → `Decimal("0.0001")`, `price_chf` → `Decimal("0.01")`, total precision capped at 12 digits), defined once beside the mapper coercion. A value that quantization would change (more decimal places than the scale holds, or over the 12-digit cap) is **lossy**: the billing field fails closed to `None`, the original is preserved as a canonical string in `metadata["raw_price_chf"]` / `metadata["raw_tax_points"]`, and the validator raises an ERROR so the record routes to human review — the database never silently rounds it away.

Quantizing a non-lossy value is **hash-invariant**: freeze canonicalisation already normalises Decimals (`format(value.normalize(), "f")`, so `76.5` == `76.5000`), so widening `76.5` → `76.5000` cannot move a `record_hash`. The two pinned fixture hashes (EAL Pos-1000, ePL GTIN 7680536620137) stay textually untouched and green — that is the proof the contract changes nothing for already-conformant data.

## Alternatives weighed
- **Round lossy values silently to fit** — rejected; rounding a billing value without a human in the loop is exactly the "no AI/machine mutates a billing value" rule, applied to the database. Fail-closed-to-review is the established EAL `nach Aufwand` → `None` precedent.
- **Widen the NUMERIC columns instead** — rejected; the column scale *is* the published BAG precision (4 dp tax points, 2 dp prices). Widening hides over-precise junk rather than surfacing it.
- **Normalise only at read time** — rejected; the breach happens at *write* (insert-time rounding). Normalising on read cannot recover bytes Postgres already discarded.

## Consequences
- (+) Stored bytes provably equal hashed bytes on every engine: a frozen value can no longer drift between the SQLite mirror and Postgres, and `verify()` stays honest. The cross-engine parity suite seeds max-scale (`12.34` / `76.5000`) and a lossy case asserted identical on both engines.
- (+) Over-precise or sub-scale inputs (e.g. `Decimal("0.0000001")`) can no longer leak to storage — they fail closed to `None` + review, closing the exponent-leakage path.
- (–) A genuinely over-precise source value is held out of the served set until a human resolves it; revisit the scales here only if BAG publishes a source whose real precision exceeds NUMERIC(12,4)/(12,2) — which would itself need a schema migration and a new ADR.

*Lineage: extends [ADR-004](004-freeze-content-hash-lineage.md) (freeze content hash) and the cross-engine read normalisation; the schema scales it mirrors are `db/schema.sql`.*
