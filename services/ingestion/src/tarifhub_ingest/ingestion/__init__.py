"""Pre-freeze ingestion pipeline.

Deterministic orchestration: load -> parse -> map -> validate -> score -> flag
-> freeze -> store -> audit. AI may assist only up to the mapping step; the
freeze/store/audit tail is pure and reproducible.
"""
