"""Endpoint tests for the serving API (offline: SQLite + stub embedder).

Exercises health, list (incl. system filter + pagination + latest-version), get
(incl. 404), and the search 501 path on SQLite. No network, no containers.
"""

from __future__ import annotations


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_returns_latest_version_per_key(client):
    resp = client.get("/api/v1/tariffs")
    assert resp.status_code == 200
    body = resp.json()
    # Three distinct (system, code) keys; the AA.00.0010 v1 must not appear.
    keys = {(r["tariff_system"], r["tariff_code"]) for r in body}
    assert keys == {
        ("TARDOC", "AA.00.0010"),
        ("TARDOC", "BB.00.0020"),
        ("EAL", "1234.00"),
    }
    aa = next(r for r in body if r["tariff_code"] == "AA.00.0010")
    assert aa["version"] == 2
    assert aa["designation"]["de"] == "Grundkonsultation (rev)"


def test_list_is_deterministically_ordered(client):
    body = client.get("/api/v1/tariffs").json()
    ordered = sorted(body, key=lambda r: (r["tariff_system"], r["tariff_code"]))
    assert body == ordered


def test_list_filters_by_system(client):
    resp = client.get("/api/v1/tariffs", params={"system": "TARDOC"})
    assert resp.status_code == 200
    body = resp.json()
    assert {r["tariff_system"] for r in body} == {"TARDOC"}
    assert len(body) == 2


def test_list_pagination_limit_and_offset(client):
    page1 = client.get("/api/v1/tariffs", params={"limit": 1, "offset": 0}).json()
    page2 = client.get("/api/v1/tariffs", params={"limit": 1, "offset": 1}).json()
    assert len(page1) == 1 and len(page2) == 1
    assert page1[0]["tariff_code"] != page2[0]["tariff_code"]


def test_list_rejects_out_of_range_limit(client):
    assert client.get("/api/v1/tariffs", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/tariffs", params={"limit": 100000}).status_code == 422


def test_get_returns_latest_record(client):
    resp = client.get("/api/v1/tariffs/TARDOC/AA.00.0010")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 2
    assert body["tax_points"] == "10.10"
    assert body["record_hash"]


def test_get_unknown_returns_404(client):
    resp = client.get("/api/v1/tariffs/TARDOC/DOES.NOT.EXIST")
    assert resp.status_code == 404
    assert "no frozen record" in resp.json()["detail"]


def test_search_on_sqlite_returns_501(client):
    resp = client.get("/api/v1/search", params={"q": "blood glucose", "limit": 5})
    assert resp.status_code == 501
    assert resp.json()["detail"] == "semantic search requires Postgres+pgvector"


def test_search_requires_query(client):
    # Empty/missing q fails input validation before reaching the 501 path.
    assert client.get("/api/v1/search", params={"q": ""}).status_code == 422
    assert client.get("/api/v1/search").status_code == 422


def test_list_on_empty_db_is_empty(empty_client):
    resp = empty_client.get("/api/v1/tariffs")
    assert resp.status_code == 200
    assert resp.json() == []
