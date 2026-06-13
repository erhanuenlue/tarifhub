"""Freeze tests: the record hash is deterministic, stable and content-addressed."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem
from tarifhub_ingest.versioning.freeze_record import (
    _canonical,  # noqa: PLC2701 — exercising the canonicaliser's edge branches directly
    compute_record_hash,
    freeze,
    verify,
)

# Pinned digest of GOLDEN_RECORD. If this changes, the hashing rule changed — which
# is a breaking change to the integrity contract and must be deliberate.
GOLDEN_HASH = "7a39f3050ed814665cb732089eba11e1957d5286f473e339d3d2606174ed47bf"


def golden_record(**overrides) -> TariffRecord:
    data = dict(
        tariff_code="0010.00",
        tariff_system=TariffSystem.EAL,
        designation=Designation(de="Hämatokrit"),
        category="Hämatologie",
        tax_points=Decimal("8.50"),
        unit="point",
        valid_from=date(2026, 1, 1),
    )
    data.update(overrides)
    return TariffRecord(**data)


def test_hash_is_deterministic_across_fresh_records():
    assert compute_record_hash(golden_record()) == compute_record_hash(golden_record())


def test_hash_is_stable_pinned_value():
    assert compute_record_hash(golden_record()) == GOLDEN_HASH


def test_hash_ignores_created_at_and_version():
    base = golden_record()
    other = golden_record(
        created_at=datetime(2000, 1, 1, tzinfo=timezone.utc), version=99
    )
    assert compute_record_hash(base) == compute_record_hash(other)


def test_decimal_scale_does_not_change_hash():
    assert compute_record_hash(golden_record(tax_points=Decimal("8.5"))) == compute_record_hash(
        golden_record(tax_points=Decimal("8.50"))
    )


def test_content_change_changes_hash():
    assert compute_record_hash(golden_record()) != compute_record_hash(
        golden_record(tax_points=Decimal("9.00"))
    )


def test_freeze_sets_hash_and_verifies():
    frozen = freeze(golden_record())
    assert frozen.record_hash == GOLDEN_HASH
    assert frozen.is_frozen
    assert verify(frozen)


def test_double_freeze_is_rejected():
    frozen = freeze(golden_record())
    with pytest.raises(ValueError):
        freeze(frozen)


def test_verify_returns_false_for_an_unfrozen_record():
    """A record with no stored hash never verifies (the verify-before-trust gate)."""

    assert verify(golden_record()) is False


def test_canonical_normalises_enum_to_its_value():
    """A (non-str) Enum canonicalises to its ``.value`` — the stable form the hash sees.

    A plain ``Enum`` is used deliberately: ``TariffSystem`` is a ``str`` subclass and so
    is normalised by the string branch, leaving the dedicated Enum branch this asserts.
    """

    import enum

    class _Color(enum.Enum):
        RED = "red"

    assert _canonical(_Color.RED) == "red"


def test_canonical_falls_back_to_str_for_exotic_types():
    """An unhandled type is stringified rather than crashing the integrity hash."""

    class _Weird:
        def __str__(self) -> str:
            return "weird-value"

    assert _canonical(_Weird()) == "weird-value"
