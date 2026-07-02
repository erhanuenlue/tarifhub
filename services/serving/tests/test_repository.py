"""Unit tests for the read-only repository mapping helpers (no DB needed)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from tarifhub_serving.db import Database
from tarifhub_serving.repository import (
    ServingRepository,
    _cosine_similarity,
    _parse_embedding,
    _parse_metadata,
    _row_to_record,
    _text_to_date,
)


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


def test_parse_embedding_none_and_empty_are_none():
    assert _parse_embedding(None) is None
    assert _parse_embedding("") is None


def test_parse_embedding_decodes_both_storage_forms():
    """Postgres returns a native sequence; SQLite a JSON string — both decode to floats."""

    assert _parse_embedding([1, 2, 3]) == [1.0, 2.0, 3.0]
    assert _parse_embedding("[0.5, 0.25]") == [0.5, 0.25]


def test_cosine_similarity_zero_vector_is_zero():
    """A zero-norm vector yields 0.0, never a divide-by-zero."""

    assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_text_to_date_passes_through_date_and_handles_none():
    assert _text_to_date(date(2026, 1, 2)) == date(2026, 1, 2)
    assert _text_to_date(None) is None
    assert _text_to_date("2026-01-02T00:00:00") == date(2026, 1, 2)


def test_search_by_embedding_refuses_without_postgres():
    """On SQLite there is no pgvector; the repository raises rather than fake a ranking."""

    db = Database.from_url("sqlite:///:memory:")
    conn = db.connect()
    repo = ServingRepository(conn, db)
    with pytest.raises(RuntimeError, match="requires Postgres"):
        repo.search_by_embedding([0.1, 0.2, 0.3, 0.4], limit=5)
    conn.close()
