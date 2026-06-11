"""Unit tests for the read-only repository mapping helpers (no DB needed)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from tarifhub_serving.repository import _parse_metadata, _row_to_record  # noqa: PLC2701


def _base_row(metadata):
    """A minimal frozen-record row dict matching the tariff table columns."""

    return {
        "tariff_code": "AA.00.0010",
        "tariff_system": "TARDOC",
        "designation_de": "Grundkonsultation",
        "designation_fr": None,
        "designation_it": None,
        "category": "consultation",
        "tax_points": "9.57",
        "price_chf": None,
        "unit": "per 5 min",
        "valid_from": "2024-01-01",
        "valid_to": None,
        "source_url": "https://example.test/src",
        "source_version": "2024.1",
        "harmonization_confidence": 0.95,
        "requires_review": 0,
        "metadata": metadata,
        "record_hash": "deadbeef",
        "version": 1,
        "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat(),
    }


def test_row_to_record_accepts_native_dict_metadata():
    """Postgres JSONB comes back as a native dict; mapping must not call json.loads on it."""

    row = _base_row({"sources": ["bag"], "note": "imported"})
    record = _row_to_record(row)
    assert record.metadata == {"sources": ["bag"], "note": "imported"}
    assert record.tax_points == Decimal("9.57")


def test_row_to_record_accepts_json_text_metadata():
    """SQLite stores metadata as a JSON string; it must still decode."""

    row = _base_row('{"sources": ["bag"]}')
    record = _row_to_record(row)
    assert record.metadata == {"sources": ["bag"]}


def test_row_to_record_handles_null_metadata():
    assert _row_to_record(_base_row(None)).metadata == {}


def test_parse_metadata_variants():
    assert _parse_metadata(None) == {}
    assert _parse_metadata("") == {}
    assert _parse_metadata('{"a": 1}') == {"a": 1}
    assert _parse_metadata({"a": 1}) == {"a": 1}
