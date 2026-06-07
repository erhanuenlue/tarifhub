"""API tests via FastAPI TestClient — fully offline (temp SQLite, bundled samples)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tarifhub_ingest.main import create_app


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("TARIFHUB_DB_URL", f"sqlite:///{tmp_path / 'api_test.db'}")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return TestClient(create_app())


def test_health(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ingest_sample_then_read_frozen_records(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        ingest = client.post("/ingest/sample")
        assert ingest.status_code == 200, ingest.text
        summary = ingest.json()
        assert summary["frozen"] > 0
        assert summary["processed"] >= summary["frozen"]

        listing = client.get("/tariffs").json()
        assert len(listing) == summary["frozen"]

        code = listing[0]["tariff_code"]
        single = client.get(f"/tariffs/{code}")
        assert single.status_code == 200
        assert single.json()["tariff_code"] == code
        # Frozen records carry an integrity hash and are served verbatim.
        assert single.json()["record_hash"]

        assert client.get("/tariffs/__does_not_exist__").status_code == 404


def test_ingest_sample_is_idempotent(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        first = client.post("/ingest/sample").json()
        second = client.post("/ingest/sample").json()
    # Re-ingesting identical content freezes nothing new (hash-idempotent).
    assert first["frozen"] > 0
    assert second["frozen"] == 0
    assert second["skipped_existing"] == first["frozen"]
