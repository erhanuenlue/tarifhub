---
name: determinism-boundary-architecture
description: How the tarifhub freeze line / determinism boundary is enforced and which AST guard tests cover which value-path files
metadata:
  type: project
---

The determinism boundary (no LLM client on the value/serve path) is enforced by AST-scanning guard tests, not runtime checks. Each guard parses a fixed tuple of files and asserts none import `{anthropic, openai, cohere, langchain, llama_index}`.

**Why:** the inviolable rule is "no AI computes or mutates a billing value at serve time." A frozen `test_determinism_boundary.py` is the CI gate; CI fails if an LLM client becomes importable on the value path.

**How to apply:** when auditing a new write/serve path, confirm a guard test actually lists the new file in its scanned tuple — a guard that does not name the file does not cover it.

Guard test coverage map (services/ingestion):
- `tests/test_determinism_boundary.py` (FROZEN by guard_frozen hook, cannot be edited) scans: `main.py`, `storage/db.py`, `storage/tariff_repository.py`.
- `tests/test_review_boundary.py` (sibling, carries additional scope since the original is frozen) scans: `review.py`, `main.py`.
- serving has its own `services/serving/tests/test_serving_boundary.py` (basename matters for guard_frozen — see [[guard-frozen-basename]]).

Pattern: because the original boundary test is frozen, new surfaces add a SIBLING boundary test rather than editing the frozen one. This is the sanctioned extension mechanism.

The hash integrity anchor is `versioning/freeze_record.py`: SHA-256 over sorted `HASHED_FIELDS`, which EXCLUDES `record_hash`, `created_at`, `version`. Decimals normalised via `format(Decimal.normalize(), "f")`. `freeze()` raises ValueError if `record_hash is not None` (re-freeze forbidden). `audit_logger.py` and `freeze_record.py` are PROTECTED modules (change only with explicit human confirmation).
