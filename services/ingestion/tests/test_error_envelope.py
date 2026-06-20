"""Uniform RFC 7807 error envelope on the ingestion admin/read/review surface (offline).

Pins that ingestion now leaves every failure as the SAME ``application/problem+json`` shape
the serving API ships: a domain error -> mapped status, an unknown route -> 404, and an
unexpected error -> a structured 500 with a correlation id and no leaked internals. The
review write path no longer returns a bare ``HTTPException`` — a missing record on POST
``/review`` surfaces as a problem document, the riskiest mutating path included.

No network, no containers, no API key (the offline SQLite mirror is the default).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tarifhub_ingest.main import create_app

PROBLEM = "application/problem+json"
_SECRET = "INGEST-SECRET-do-not-leak-98765"


def _assert_problem_shape(body: dict, *, status: int) -> None:
    """Every problem body carries the five RFC 7807 members with the right status."""

    assert set(body) >= {"type", "title", "status", "detail", "instance"}
    assert body["status"] == status
    assert isinstance(body["type"], str) and body["type"]
    assert isinstance(body["title"], str) and body["title"]
    assert isinstance(body["detail"], str) and body["detail"]


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("TARIFHUB_DB_URL", f"sqlite:///{tmp_path / 'ingest.db'}")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with TestClient(create_app()) as test_client:
        yield test_client


# --- domain error -> problem+json --------------------------------------------


def test_unknown_tariff_code_returns_problem_404(client):
    """A read for a missing code raises ``TariffCodeNotFound`` -> 404 problem+json."""

    resp = client.get("/tariffs/DOES.NOT.EXIST")

    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith(PROBLEM)
    body = resp.json()
    _assert_problem_shape(body, status=404)
    assert body["type"].endswith("/tariff-not-found")
    assert "DOES.NOT.EXIST" in body["detail"]
    assert body["instance"] == "/tariffs/DOES.NOT.EXIST"
    # A client error stays byte-reproducible: no correlation id in the body.
    assert "correlation_id" not in body


def test_review_unknown_record_returns_problem_404(client):
    """The mutating review path: POST for a missing record -> 404 problem+json, not bare."""

    resp = client.post(
        "/review", json={"tariff_system": "EAL", "tariff_code": "9999.99", "action": "approve"}
    )

    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith(PROBLEM)
    body = resp.json()
    _assert_problem_shape(body, status=404)
    assert body["type"].endswith("/review-record-not-found")
    assert body["instance"] == "/review"
    assert "correlation_id" not in body


def test_unknown_route_returns_problem_404(client):
    """A path with no route is a Starlette HTTPException(404) -> problem+json too."""

    resp = client.get("/no/such/route")

    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith(PROBLEM)
    _assert_problem_shape(resp.json(), status=404)


# --- unexpected error -> structured 500, no leak -----------------------------


class _BoomRepo:
    """A repository stub whose reads raise an unexpected internal error."""

    def get(self, *_a, **_k):
        raise RuntimeError(_SECRET)

    def list_all(self):
        raise RuntimeError(_SECRET)


def test_unexpected_error_returns_structured_500_without_leak(tmp_path, monkeypatch):
    monkeypatch.setenv("TARIFHUB_DB_URL", f"sqlite:///{tmp_path / 'ingest.db'}")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = create_app()
    # raise_server_exceptions=False so the catch-all 500 response is returned to us instead
    # of the RuntimeError propagating into the test (Starlette default).
    with TestClient(app, raise_server_exceptions=False) as test_client:
        test_client.app.state.repo = _BoomRepo()
        resp = test_client.get("/tariffs/AA.00.0010")

    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith(PROBLEM)
    body = resp.json()
    _assert_problem_shape(body, status=500)
    assert body["type"].endswith("/internal-error")

    # A correlation id is present in the body AND echoed in the response header.
    correlation_id = body["correlation_id"]
    assert correlation_id
    assert resp.headers["x-correlation-id"] == correlation_id
    assert correlation_id in body["detail"]

    # No internal string and no stack trace leak to the caller.
    text = resp.text
    assert _SECRET not in text
    assert "RuntimeError" not in text
    assert "Traceback" not in text
