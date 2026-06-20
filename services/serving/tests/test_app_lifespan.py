"""The app lifespan starts and stops cleanly offline (SQLite: no pool warmed).

The other suites construct a bare ``TestClient(app)``, which does not run the lifespan,
so they exercise the per-request ``get_repository`` path but not the startup/shutdown
hook. Entering the client as a context manager runs the lifespan: on SQLite no Postgres
pool is warmed (``_get_pool`` returns ``None``) and shutdown disposes an empty registry,
so the app comes up and tears down with no network and no driver. The Postgres pool-warm
leg is covered by the CI ``python-parity`` job against a live pgvector container.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_lifespan_starts_and_stops_without_pool_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("TARIFHUB_DB_URL", f"sqlite:///{tmp_path / 'lifespan.db'}")
    import tarifhub_serving.main as serving_main
    from tarifhub_serving.main import app

    with TestClient(app) as client:
        # Lifespan has run, and on SQLite it warms no pool.
        assert serving_main._POOLS == {}
        assert client.get("/health").json() == {"status": "ok"}

    # Shutdown ran _close_pools(): the registry is empty and the app stopped cleanly.
    assert serving_main._POOLS == {}
