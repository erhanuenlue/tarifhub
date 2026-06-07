"""Mapper tests: rules-based mapping and the AI seam's offline fallback."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tarifhub_ingest.mappers.tariff_mapper import ai_map, map_raw
from tarifhub_ingest.models.tariff_model import TariffSystem


def test_map_eal_row_is_tax_point_based_and_de_only():
    raw = {
        "tariff_code": "0010.00",
        "designation_de": "Hämatokrit",
        "tax_points": "8.5",
        "unit": "point",
        "valid_from": "2026-01-01",
    }
    record = map_raw(raw, system=TariffSystem.EAL, source_url="https://bag", source_version="2026-06")

    assert record.tariff_code == "0010.00"
    assert record.tariff_system is TariffSystem.EAL
    assert record.designation.de == "Hämatokrit"
    assert record.designation.fr is None and record.designation.it is None
    assert record.tax_points == Decimal("8.5")
    assert record.price_chf is None
    assert record.valid_from == date(2026, 1, 1)
    assert record.source_version == "2026-06"


def test_map_epl_resource_is_price_based_and_multilingual():
    raw = {
        "tariff_code": "7680000000017",
        "designation_de": "Beispielin",
        "designation_fr": "Exempline",
        "designation_it": "Esempina",
        "category": "Analgetika",
        "price_chf": "12.50",
        "unit": "pack",
        "valid_from": "2026-01-01",
    }
    record = map_raw(raw, system=TariffSystem.SL, source_url="https://github")

    assert record.tariff_system is TariffSystem.SL
    assert (record.designation.fr, record.designation.it) == ("Exempline", "Esempina")
    assert record.price_chf == Decimal("12.50")
    assert record.tax_points is None


def test_swiss_decimal_comma_is_normalized():
    raw = {"tariff_code": "X", "designation_de": "Y", "tax_points": "1'234,50"}
    record = map_raw(raw, system=TariffSystem.EAL)
    assert record.tax_points == Decimal("1234.50")


def test_ai_map_offline_does_not_alter_billing_values(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    raw = {
        "tariff_code": "0010.00",
        "designation_de": "Hämatokrit",
        "tax_points": "8.5",
        "valid_from": "2026-01-01",
    }
    ai = ai_map(raw, system=TariffSystem.EAL, source_url="https://bag")
    rules = map_raw(raw, system=TariffSystem.EAL, source_url="https://bag")

    # With no API key the AI seam must equal the deterministic rules output and,
    # in particular, must never touch the billing-relevant value.
    assert ai.tax_points == rules.tax_points
    assert ai.price_chf == rules.price_chf
    assert ai.designation == rules.designation
    assert ai.metadata.get("ai_assisted") is False
