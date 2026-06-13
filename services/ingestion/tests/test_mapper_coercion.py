"""Coercion-helper error cases for the deterministic mapper.

``_to_decimal`` and ``_to_date`` parse untrusted source cells. They must fail closed to
``None`` on anything they cannot represent — never raise, never guess — because a
billing value that the mapper could not represent is captured raw and routed to review
downstream (see the scale contract). These pin the fail-closed branches.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from tarifhub_ingest.mappers.tariff_mapper import _to_date, _to_decimal


def test_to_decimal_unparseable_text_fails_closed_to_none():
    assert _to_decimal("not-a-number") is None


def test_to_decimal_treats_bool_as_none():
    """bool is an int subclass; it must never be coerced into a billing Decimal."""

    assert _to_decimal(True) is None
    assert _to_decimal(False) is None


def test_to_decimal_blank_is_none_and_swiss_format_normalises():
    assert _to_decimal("   ") is None
    # Swiss thousands apostrophe + decimal comma both normalise to a plain Decimal.
    assert _to_decimal("1'234,50") == Decimal("1234.50")


def test_to_decimal_passes_numeric_types_through():
    assert _to_decimal(Decimal("9.57")) == Decimal("9.57")
    assert _to_decimal(3) == Decimal("3")


def test_to_date_garbage_fails_closed_to_none():
    assert _to_date("31.02.2026") is None  # not ISO -> ValueError branch -> None
    assert _to_date("") is None
    assert _to_date("   ") is None


def test_to_date_accepts_datetime_and_date():
    assert _to_date(datetime(2026, 1, 2, 3, 4)) == date(2026, 1, 2)
    assert _to_date(date(2026, 1, 2)) == date(2026, 1, 2)
