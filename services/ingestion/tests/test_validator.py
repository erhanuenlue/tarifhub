"""Validator error-case tests — the pre-freeze ERRORs that force a record to review.

The deterministic validator is a pure function of record content. An error blocks the
record from being trusted (it is force-flagged for human review); these tests pin the
three structural errors that the broader scale-contract suite does not exercise:
empty key, empty canonical designation, and an inverted validity window. This is the
"Fehlerfälle" the test rubric (criterion 13) asks the core logic to cover.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem
from tarifhub_ingest.validators.tariff_validator import validate


def _record(**overrides) -> TariffRecord:
    data = dict(
        tariff_code="0010.00",
        tariff_system=TariffSystem.EAL,
        designation=Designation(de="Hämatokrit"),
        tax_points=Decimal("8.50"),
        valid_from=date(2026, 1, 1),
    )
    data.update(overrides)
    return TariffRecord(**data)


def test_a_complete_record_validates_clean():
    result = validate(_record())
    assert result.ok is True
    assert result.errors == []


def test_empty_tariff_code_is_an_error():
    result = validate(_record(tariff_code="   "))
    assert result.ok is False
    assert "tariff_code is empty" in result.errors


def test_empty_canonical_german_designation_is_an_error():
    result = validate(_record(designation=Designation(de="  ")))
    assert result.ok is False
    assert "canonical German designation is empty" in result.errors


def test_valid_from_after_valid_to_is_an_error():
    result = validate(_record(valid_from=date(2026, 6, 1), valid_to=date(2026, 1, 1)))
    assert result.ok is False
    assert "valid_from is after valid_to" in result.errors
