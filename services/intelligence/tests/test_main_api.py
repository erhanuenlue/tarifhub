"""Application-surface behaviours not covered by the per-endpoint suites (offline).

Covers the ``/health`` liveness endpoint and the ``run()`` console-script entry point,
whose only job is to hand the env-driven bind address to uvicorn. ``uvicorn.run`` is
monkeypatched so the entry point is exercised without actually binding a socket.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tarifiq import __version__
from tarifiq.main import create_app, run


def test_health_endpoint_reports_service_and_version(monkeypatch):
    """``GET /health`` returns a 200 with the service name and the package version."""

    monkeypatch.setenv("TARIFIQ_OFFLINE", "1")
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok", "service": "tarifiq", "version": __version__}


def test_run_serves_app_with_env_configured_bind_address(monkeypatch):
    """``run()`` passes the app target and the Settings-derived host/port to uvicorn."""

    monkeypatch.setenv("TARIFIQ_API_HOST", "127.0.0.1")
    monkeypatch.setenv("TARIFIQ_API_PORT", "9091")

    captured: dict[str, object] = {}

    def fake_run(app: object, **kwargs: object) -> None:
        captured["app"] = app
        captured.update(kwargs)

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", fake_run)

    run()

    assert captured["app"] == "tarifiq.main:app"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9091
    assert captured["reload"] is False
