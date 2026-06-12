"""Pure, deterministic builders for the diff and explain endpoints.

No AI, no randomness, no wall-clock. Both functions are pure functions of their frozen
``TariffRecord`` inputs, so the same records always produce byte-identical output. They
import only the canonical model from ``tarifhub_ingest`` (allowed by the boundary test);
they never touch an LLM client, mappers, storage or versioning.
"""

from __future__ import annotations

from typing import Any

from tarifhub_ingest.models.tariff_model import TariffRecord

from tarifhub_serving.models import DiffResponse, FieldChange

# Versioning / provenance fields are never part of a field-level diff: a version bump and
# its hash are bookkeeping, and created_at is a wall-clock stamp. Everything else in the
# locked field set is diffable.
_DIFF_EXCLUDED = {"record_hash", "version", "created_at"}


def _flatten(record: TariffRecord) -> dict[str, Any]:
    """Flatten a record's diffable fields to ``{dotted_field: json_value}``.

    Values are rendered exactly as the API serialises them elsewhere
    (``model_dump(mode="json")``). The nested ``designation`` is expanded to dotted
    leaves (``designation.de`` / ``.fr`` / ``.it``); every other field is a scalar.
    """

    dumped = record.model_dump(mode="json")
    flat: dict[str, Any] = {}
    for field in record.__class__.model_fields:
        if field in _DIFF_EXCLUDED:
            continue
        value = dumped[field]
        if field == "designation" and isinstance(value, dict):
            for leaf in ("de", "fr", "it"):
                flat[f"designation.{leaf}"] = value.get(leaf)
        else:
            flat[field] = value
    return flat


def build_diff(
    system: str,
    code: str,
    from_record: TariffRecord,
    to_record: TariffRecord,
) -> DiffResponse:
    """Build the field-level diff between two frozen versions of a record.

    Iterates the diffable fields in sorted (dotted) field-name order — deterministic —
    and emits one :class:`FieldChange` per field whose serialised value differs. Identical
    versions yield ``changes=[]``.
    """

    before = _flatten(from_record)
    after = _flatten(to_record)
    changes: list[FieldChange] = []
    for field in sorted(before):
        if before[field] != after[field]:
            changes.append(
                FieldChange(field=field, from_value=before[field], to_value=after[field])
            )
    return DiffResponse(
        tariff_system=system,
        tariff_code=code,
        from_version=from_record.version,
        to_version=to_record.version,
        from_record_hash=from_record.record_hash,
        to_record_hash=to_record.record_hash,
        changes=changes,
    )


def _validity_window(record: TariffRecord) -> str:
    """Render a record's validity window as ``from .. to`` (open ends spelled out)."""

    start = record.valid_from.isoformat() if record.valid_from else "beginning of time"
    end = record.valid_to.isoformat() if record.valid_to else "open-ended"
    return f"{start} .. {end}"


def build_explanation(code: str, records: list[TariffRecord]) -> str:
    """Assemble a deterministic, record-grounded explanation for ``code``.

    Grounded only in record fields (systems, the current designation, validity window,
    version count, record-hash provenance). Labelled ``[deterministic]`` to mark that it
    is rule-generated, not AI-written. ``records`` is the full version list ordered by
    ``(tariff_system, version)`` ascending (the repository's order); the "current" record
    is the highest version of the lexicographically-first system in that list.
    """

    systems = sorted({r.tariff_system.value for r in records})
    current = max(records, key=lambda r: (r.tariff_system.value, r.version))
    version_count = len(records)
    hash_provenance = current.record_hash or "unhashed"
    return (
        f"[deterministic] Tariff code {code} in system "
        f"{', '.join(systems)} resolves to {version_count} frozen "
        f"version(s). The current version is v{current.version}: "
        f'"{current.designation.de}", valid {_validity_window(current)}. '
        f"This record is served verbatim from a frozen, hashed entry "
        f"(record_hash {hash_provenance}); no value was computed or altered."
    )
