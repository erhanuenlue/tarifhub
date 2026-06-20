"""Uniform RFC 7807 error envelope on the TarifIQ intelligence surface (offline).

Pins that intelligence now leaves every failure as the SAME ``application/problem+json``
shape the serving API ships: the cross-walk domain error -> 404, an unknown route -> 404, a
declarative validation failure -> 422 with the field errors as an extension member, and an
unexpected error -> a structured 500 with a correlation id and no leaked internals. No
default/bare FastAPI bodies remain.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tarifiq.main import create_app

PROBLEM = "application/problem+json"
_SECRET = "TARIFIQ-SECRET-do-not-leak-13579"


def _assert_problem_shape(body: dict, *, status: int) -> None:
    assert set(body) >= {"type", "title", "status", "detail", "instance"}
    assert body["status"] == status
    assert isinstance(body["type"], str) and body["type"]
    assert isinstance(body["title"], str) and body["title"]
    assert isinstance(body["detail"], str) and body["detail"]


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("TARIFIQ_OFFLINE", "1")
    with TestClient(create_app()) as test_client:
        yield test_client


def test_crosswalk_not_found_returns_problem_404(client):
    """An unknown TARMED code raises ``CrosswalkNotFound`` -> 404 problem+json."""

    resp = client.get("/v1/crosswalk/99.9999")

    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith(PROBLEM)
    body = resp.json()
    _assert_problem_shape(body, status=404)
    assert body["type"].endswith("/crosswalk-not-found")
    assert "99.9999" in body["detail"]
    assert body["instance"] == "/v1/crosswalk/99.9999"
    assert "correlation_id" not in body


def test_unknown_route_returns_problem_404(client):
    resp = client.get("/no/such/route")

    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith(PROBLEM)
    _assert_problem_shape(resp.json(), status=404)


def test_validation_error_returns_problem_422(client):
    """A malformed /v1/validate body fails declarative validation -> 422 problem+json."""

    resp = client.post("/v1/validate", json={"not": "a valid rule"})

    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith(PROBLEM)
    body = resp.json()
    _assert_problem_shape(body, status=422)
    assert body["type"].endswith("/validation-error")
    # Field-level errors are preserved as an RFC 7807 extension member.
    assert isinstance(body["errors"], list) and body["errors"]


def test_unexpected_error_returns_structured_500_without_leak(monkeypatch):
    monkeypatch.setenv("TARIFIQ_OFFLINE", "1")

    def boom(*_a, **_k):
        raise RuntimeError(_SECRET)

    # Force an unexpected fault inside an otherwise-deterministic endpoint.
    monkeypatch.setattr("tarifiq.main.lookup_crosswalk", boom)
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        resp = test_client.get("/v1/crosswalk/00.0010")

    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith(PROBLEM)
    body = resp.json()
    _assert_problem_shape(body, status=500)
    assert body["type"].endswith("/internal-error")

    correlation_id = body["correlation_id"]
    assert correlation_id
    assert resp.headers["x-correlation-id"] == correlation_id
    assert correlation_id in body["detail"]

    text = resp.text
    assert _SECRET not in text
    assert "RuntimeError" not in text
    assert "Traceback" not in text
