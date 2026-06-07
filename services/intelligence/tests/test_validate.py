"""Deterministic pre-freeze rule validation, plus the frozen-store read path (mocked)."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from tarifiq.main import create_app
from tarifiq.models.rule_model import (
    CombinabilityRelation,
    CombinabilityRule,
    TariffSystem,
)
from tarifiq.store.frozen_client import ServingFrozenClient, bundled_offline_store
from tarifiq.validators.rule_validator import validate_rule


def test_valid_exclusive_rule_passes():
    rule = CombinabilityRule(
        rule_id="R-EXCL-900",
        system=TariffSystem.TARDOC,
        relation=CombinabilityRelation.EXCLUSIVE,
        code="AA.00.0010",
        related_code="AA.00.0030",
        source="manual",
    )
    result = validate_rule(rule, store=bundled_offline_store())
    assert result.ok is True
    assert result.errors == []
    assert set(result.checked_codes) == {"AA.00.0010", "AA.00.0030"}


def test_exclusive_rule_without_related_code_fails():
    rule = CombinabilityRule(
        rule_id="R-EXCL-901",
        system=TariffSystem.TARDOC,
        relation=CombinabilityRelation.EXCLUSIVE,
        code="AA.00.0010",
    )
    result = validate_rule(rule, store=bundled_offline_store())
    assert result.ok is False
    assert any("requires related_code" in e for e in result.errors)


def test_cumulation_rule_without_max_quantity_fails():
    rule = CombinabilityRule(
        rule_id="R-CUM-901",
        system=TariffSystem.TARDOC,
        relation=CombinabilityRelation.CUMULATION_LIMIT,
        code="AA.00.0050",
    )
    result = validate_rule(rule, store=bundled_offline_store())
    assert result.ok is False
    assert any("CUMULATION_LIMIT requires max_quantity" in e for e in result.errors)


def test_rule_referencing_unknown_code_fails_referential_check():
    rule = CombinabilityRule(
        rule_id="R-REQ-902",
        system=TariffSystem.TARDOC,
        relation=CombinabilityRelation.REQUIRES,
        code="ZZ.99.9999",
        related_code="AA.00.0010",
        source="manual",
    )
    result = validate_rule(rule, store=bundled_offline_store())
    assert result.ok is False
    assert any("ZZ.99.9999" in e and "not a frozen" in e for e in result.errors)


def test_serving_frozen_client_reads_records_via_mock_transport():
    # Proves the live serving read path works without touching the network.
    frozen = {
        "tariffCode": "AA.00.0010",
        "tariffSystem": "TARDOC",
        "designationDe": "Grundkonsultation, erste 5 Min.",
        "taxPoints": "9.57",
        "recordHash": "deadbeef",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/tariffs/TARDOC/AA.00.0010":
            return httpx.Response(200, json=frozen)
        return httpx.Response(404, json={"error": "no frozen record"})

    client = ServingFrozenClient("http://serving.test", transport=httpx.MockTransport(handler))
    record = client.get("TARDOC", "AA.00.0010")
    assert record is not None
    assert record.tariff_code == "AA.00.0010"
    assert record.tax_points == "9.57"
    assert client.exists("TARDOC", "AA.00.0010") is True
    assert client.get("TARDOC", "ZZ.99.9999") is None


def test_endpoint_validate(monkeypatch):
    monkeypatch.setenv("TARIFIQ_OFFLINE", "1")
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/validate",
            json={
                "rule_id": "R-EXCL-903",
                "system": "TARDOC",
                "relation": "EXCLUSIVE",
                "code": "AA.00.0010",
                "related_code": "AA.00.0030",
                "source": "manual",
            },
        )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
