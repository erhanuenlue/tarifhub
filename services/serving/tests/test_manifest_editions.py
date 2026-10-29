"""End to end: two dated BAG AL editions imported from a manifest, read through the API.

The edition fixtures are the ingestion suite's committed copies of four real positions
from the BAG 1 January and 1 July 2026 workbooks (``services/ingestion/tests/fixtures/eal``).
Expected values are the BAG figures; the diff and the as_of selection are the existing
serving logic, read over HTTP.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tarifhub_ingest.ingestion.manifest import import_manifest

_FIXTURES = Path(__file__).resolve().parents[2] / "ingestion" / "tests" / "fixtures" / "eal"
_EDITIONS = {
    "2026-01-01": "Analysenliste per 1. Januar 2026_fixture.xlsx",
    "2026-07-01": "Analysenliste per 1. Juli 2026_fixture.xlsx",
}


@pytest.fixture()
def editions_client(engine, tmp_path, monkeypatch) -> Iterator[TestClient]:
    """The serving client over a fresh DB (each engine) holding both editions from a manifest.

    Entered as a context manager so the app lifespan runs, as in the read-parity suite.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    root = tmp_path / "repo"
    editions = []
    for effective, name in _EDITIONS.items():
        target = root / "data" / "raw" / "bag" / "al" / effective / name
        target.parent.mkdir(parents=True)
        shutil.copyfile(_FIXTURES / name, target)
        document = {
            "kind": "full_list_xlsx",
            "path": target.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }
        editions.append({"effective_date": effective, "documents": [document]})
    manifest = root / "data" / "manifests" / "bag-al.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"manifest_version": 1, "tariff_system": "EAL", "editions": editions}),
        encoding="utf-8",
    )

    conn = engine.db.connect()
    try:
        import_manifest(manifest, conn, engine.db)
    finally:
        conn.close()
    monkeypatch.setenv("TARIFHUB_DB_URL", engine.db_url)
    from tarifhub_serving.main import app

    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    ("code", "january", "july"),
    [("4700", "21.6", "16.6"), ("1368", "59.4", "64.4")],
)
def test_diff_between_the_editions_reports_the_tax_point_change(
    editions_client, code, january, july
):
    resp = editions_client.get(f"/api/v1/tariffs/EAL/{code}/diff", params={"from": 1, "to": 2})

    assert resp.status_code == 200
    changes = {c["field"]: (c["from_value"], c["to_value"]) for c in resp.json()["changes"]}
    assert [Decimal(value) for value in changes["tax_points"]] == [
        Decimal(january),
        Decimal(july),
    ]
    assert changes["valid_from"] == ("2026-01-01", "2026-07-01")


@pytest.mark.parametrize(
    ("as_of", "expected"),
    [
        ("2026-03-15", {"4700": "21.6", "1368": "59.4"}),
        ("2026-08-15", {"4700": "16.6", "1368": "64.4"}),
    ],
)
def test_as_of_returns_the_edition_in_force_on_that_date(editions_client, as_of, expected):
    for code, tax_points in expected.items():
        resp = editions_client.get(f"/api/v1/tariffs/EAL/{code}", params={"as_of": as_of})
        assert resp.status_code == 200
        assert Decimal(resp.json()["tax_points"]) == Decimal(tax_points)


def test_position_added_in_july_is_not_in_force_in_march(editions_client):
    march = editions_client.get("/api/v1/tariffs/EAL/1779", params={"as_of": "2026-03-15"})
    august = editions_client.get("/api/v1/tariffs/EAL/1779", params={"as_of": "2026-08-15"})

    assert march.status_code == 404
    assert Decimal(august.json()["tax_points"]) == Decimal("73.3")
