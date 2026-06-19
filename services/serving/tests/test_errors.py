"""Centralised RFC 7807 error handling (offline: SQLite + stub embedder).

Pins the four handlers registered in ``tarifhub_serving.errors``:

* a domain ``TariffNotFound`` -> 404 ``application/problem+json`` envelope;
* an unexpected error in a route -> a structured 500 with a correlation id and **no**
  leaked stack trace or internal string;
* a ``RequestValidationError`` -> 422 problem+json;
* a router-raised ``HTTPException`` (unknown path) -> 404 problem+json;

plus the invariants that a 200 stays plain JSON and an inbound ``X-Request-ID`` is
honoured as the correlation id. No network, no containers, no API key.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

PROBLEM = "application/problem+json"
_SECRET = "INTERNAL-SECRET-do-not-leak-12345"


def _assert_problem_shape(body: dict, *, status: int) -> None:
    """Every problem body carries the five RFC 7807 members with the right status."""

    assert set(body) >= {"type", "title", "status", "detail", "instance"}
    assert body["status"] == status
    assert isinstance(body["type"], str) and body["type"]
    assert isinstance(body["title"], str) and body["title"]
    assert isinstance(body["detail"], str) and body["detail"]


# --- domain error -> 404 problem+json ----------------------------------------


def test_domain_not_found_returns_problem_json_404(client):
    """An unknown key raises ``TariffNotFound`` -> a 404 problem+json envelope."""

    resp = client.get("/api/v1/tariffs/TARDOC/DOES.NOT.EXIST")

    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith(PROBLEM)
    body = resp.json()
    _assert_problem_shape(body, status=404)
    assert body["type"].endswith("/tariff-not-found")
    assert body["title"] == "Tariff record not found"
    # detail is the original message, verbatim -> the prior contract is preserved.
    assert "no frozen record" in body["detail"]
    # instance ties the problem to this specific request path.
    assert body["instance"] == "/api/v1/tariffs/TARDOC/DOES.NOT.EXIST"
    # A client error stays byte-reproducible: no correlation id in the body.
    assert "correlation_id" not in body


# --- unexpected error -> structured 500, no leak -----------------------------


class _BoomRepo:
    """A repository stub whose read raises an unexpected internal error."""

    def get_latest(self, *_a, **_k):
        raise RuntimeError(_SECRET)


def _client_with_exploding_repo() -> TestClient:
    """A TestClient that surfaces the 500 (not re-raise) with the repo overridden."""

    from tarifhub_serving.main import app, get_repository

    app.dependency_overrides[get_repository] = lambda: _BoomRepo()
    # raise_server_exceptions=False so the catch-all 500 response is returned to us
    # instead of the RuntimeError propagating into the test (Starlette default).
    return TestClient(app, raise_server_exceptions=False)


def test_unexpected_error_returns_structured_500_without_leak():
    from tarifhub_serving.main import app, get_repository

    test_client = _client_with_exploding_repo()
    try:
        resp = test_client.get("/api/v1/tariffs/TARDOC/AA.00.0010")
    finally:
        app.dependency_overrides.pop(get_repository, None)

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


def test_unexpected_error_honours_inbound_request_id():
    """An inbound X-Request-ID becomes the correlation id (trace continuity)."""

    from tarifhub_serving.main import app, get_repository

    test_client = _client_with_exploding_repo()
    try:
        resp = test_client.get(
            "/api/v1/tariffs/TARDOC/AA.00.0010", headers={"X-Request-ID": "trace-xyz-001"}
        )
    finally:
        app.dependency_overrides.pop(get_repository, None)

    assert resp.status_code == 500
    assert resp.json()["correlation_id"] == "trace-xyz-001"
    assert resp.headers["x-correlation-id"] == "trace-xyz-001"


# --- validation error -> 422 problem+json ------------------------------------


def test_validation_error_returns_problem_json_422(client):
    resp = client.get("/api/v1/tariffs", params={"limit": 0})

    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith(PROBLEM)
    body = resp.json()
    _assert_problem_shape(body, status=422)
    assert body["type"].endswith("/validation-error")
    # Field-level errors are preserved as an RFC 7807 extension member.
    assert isinstance(body["errors"], list) and body["errors"]


# --- router-raised HTTPException -> problem+json ------------------------------


def test_unknown_route_returns_problem_json_404(client):
    """A path with no route is a Starlette HTTPException(404) -> problem+json too."""

    resp = client.get("/no/such/route")

    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith(PROBLEM)
    _assert_problem_shape(resp.json(), status=404)


# --- success path is unaffected ----------------------------------------------


def test_success_response_stays_plain_json(client):
    """A 200 is ordinary application/json, never wrapped as a problem document."""

    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"status": "ok"}
    assert "x-correlation-id" not in resp.headers
