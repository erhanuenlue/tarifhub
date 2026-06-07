"""Deterministic freeze + content hashing of canonical records. PROTECTED MODULE.

The ``record_hash`` is a SHA-256 over the canonical *content* fields in sorted
order. It is fully deterministic: the same logical content always yields the same
hash, independent of

* the hash field itself (cannot hash itself),
* ``created_at`` (wall clock), and
* ``version`` (supersession metadata, not content) — so re-ingesting unchanged
  content is recognised as the *same* frozen record and is idempotent.

Decimal values are normalised (``10.50`` == ``10.5``) so equivalent numbers hash
identically. DO NOT add AI / network / nondeterministic behaviour here: this is the
integrity anchor of the entire platform.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from tarifhub_ingest.models.tariff_model import TariffRecord

# Canonical content fields that participate in the integrity hash, sorted.
# Deliberately EXCLUDES: record_hash, created_at, version (see module docstring).
HASHED_FIELDS: tuple[str, ...] = (
    "category",
    "designation",
    "harmonization_confidence",
    "metadata",
    "price_chf",
    "requires_review",
    "source_url",
    "source_version",
    "tariff_code",
    "tariff_system",
    "tax_points",
    "unit",
    "valid_from",
    "valid_to",
)


def _canonical(value: Any) -> Any:
    """Normalise a value into a stable, JSON-serialisable representation."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        # normalize() collapses 10.50 -> 10.5 so equivalent numbers hash the same
        return format(value.normalize(), "f")
    if isinstance(value, float):
        return format(round(value, 6), ".6f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _canonical(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return str(value)


def _payload(record: TariffRecord) -> dict[str, Any]:
    dumped = record.model_dump()
    return {field: _canonical(dumped.get(field)) for field in HASHED_FIELDS}


def compute_record_hash(record: TariffRecord) -> str:
    """Return the deterministic SHA-256 hex digest of the record's content."""

    canonical = json.dumps(
        _payload(record), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def freeze(record: TariffRecord) -> TariffRecord:
    """Return an immutable, hash-stamped copy of ``record``.

    Raises ``ValueError`` if the record is already frozen — frozen records are
    immutable and must never be re-frozen or mutated.
    """

    if record.record_hash is not None:
        raise ValueError("record is already frozen; frozen records are immutable")
    digest = compute_record_hash(record)
    return record.model_copy(update={"record_hash": digest})


def verify(record: TariffRecord) -> bool:
    """Return True iff the stored ``record_hash`` matches the recomputed content hash."""

    if record.record_hash is None:
        return False
    return record.record_hash == compute_record_hash(record)
