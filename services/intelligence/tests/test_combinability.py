"""Deterministic combinability/cumulation evaluation — fully offline (bundled store)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tarifiq.main import create_app
from tarifiq.models.rule_model import (
    CombinabilityCheckRequest,
    CombinabilityVerdict,
    Position,
    TariffSystem,
)
from tarifiq.rules.combinability import evaluate_combinability
from tarifiq.store.frozen_client import bundled_offline_store


def _request(*positions: Position) -> CombinabilityCheckRequest:
    return CombinabilityCheckRequest(system=TariffSystem.TARDOC, positions=list(positions))


def test_exclusive_pair_is_not_combinable():
    store = bundled_offline_store()
    result = evaluate_combinability(
        _request(Position(code="AA.00.0010"), Position(code="AA.00.0030")), store=store
    )
    assert result.verdict is CombinabilityVerdict.NOT_COMBINABLE
    assert [c.rule_id for c in result.conflicts] == ["R-EXCL-001"]


def test_requires_relation_flags_missing_base():
    store = bundled_offline_store()
    result = evaluate_combinability(_request(Position(code="AA.00.0020")), store=store)
    assert result.verdict is CombinabilityVerdict.NOT_COMBINABLE
    assert result.conflicts[0].rule_id == "R-REQ-001"


def test_requires_relation_satisfied_is_combinable():
    store = bundled_offline_store()
    result = evaluate_combinability(
        _request(Position(code="AA.00.0020"), Position(code="AA.00.0010")), store=store
    )
    assert result.verdict is CombinabilityVerdict.COMBINABLE
    assert result.conflicts == []


def test_cumulation_limit_exceeded():
    store = bundled_offline_store()
    over = evaluate_combinability(_request(Position(code="AA.00.0050", quantity=7)), store=store)
    assert over.verdict is CombinabilityVerdict.NOT_COMBINABLE
    assert over.conflicts[0].rule_id == "R-CUM-001"


def test_cumulation_limit_at_boundary_is_combinable():
    store = bundled_offline_store()
    at_limit = evaluate_combinability(_request(Position(code="AA.00.0050", quantity=6)), store=store)
    assert at_limit.verdict is CombinabilityVerdict.COMBINABLE


def test_unknown_code_requires_review():
    store = bundled_offline_store()
    result = evaluate_combinability(_request(Position(code="ZZ.99.9999")), store=store)
    assert result.verdict is CombinabilityVerdict.REQUIRES_REVIEW
    assert result.unknown_codes == ["ZZ.99.9999"]


def test_evaluation_is_deterministic():
    store = bundled_offline_store()
    req = _request(Position(code="AA.00.0010"), Position(code="AA.00.0030"))
    first = evaluate_combinability(req, store=store)
    second = evaluate_combinability(req, store=store)
    assert first.model_dump() == second.model_dump()
    assert first.deterministic is True
    # The frozen rule set is content-hashed and stable across calls.
    assert first.rule_set_hash == second.rule_set_hash and len(first.rule_set_hash) == 64


def test_endpoint_combinability_check(monkeypatch):
    monkeypatch.setenv("TARIFIQ_OFFLINE", "1")
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/combinability-check",
            json={
                "system": "TARDOC",
                "positions": [{"code": "AA.00.0010"}, {"code": "AA.00.0030"}],
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verdict"] == "NOT_COMBINABLE"
    assert body["deterministic"] is True
