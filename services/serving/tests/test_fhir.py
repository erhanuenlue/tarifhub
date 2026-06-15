"""Tests for the FHIR R4 read adapter (offline: SQLite + stub embedder).

Covers the two read routes added per ADR-008:

* ``GET /api/v1/fhir/ChargeItemDefinition/{system}/{code}`` (+ ?version, ?as_of)
* ``GET /api/v1/fhir/CodeSystem/{system}`` (+ ?limit, ?offset, ?as_of)

The shared ``client`` fixture (conftest) seeds the canonical set. One local fixture seeds
a dedicated SQLite DB containing a price-based (price_chf) record so the ``base``/CHF
priceComponent and its Decimal round-trip can be pinned without disturbing the exact key
set the existing tests assert on. No network, no containers, no API key.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from tarifhub_ingest.embeddings.embedder import get_embedder
from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem
from tarifhub_ingest.storage.db import Database
from tarifhub_ingest.storage.tariff_repository import TariffRepository
from tarifhub_ingest.versioning.freeze_record import freeze

CID = "/api/v1/fhir/ChargeItemDefinition"
CS = "/api/v1/fhir/CodeSystem"


@pytest.fixture()
def price_client(tmp_path, monkeypatch) -> TestClient:
    """A seeded DB whose one record is price-based (price_chf set, tax_points None).

    Lets us pin the FHIR ``base`` priceComponent (CHF Money) and its Decimal round-trip
    on real frozen data. Kept in its own DB so the canonical seed's exact key set (which
    other tests assert on) is untouched.
    """

    db_path = tmp_path / "fhir_price.db"
    url = f"sqlite:///{db_path}"
    db = Database.from_url(url)
    conn = db.connect()
    db.init_schema(conn)
    repo = TariffRepository(conn, db)
    record = TariffRecord(
        tariff_code="MED.0001",
        tariff_system=TariffSystem.SL,
        designation=Designation(de="Beispielmedikament", fr="Medicament", it="Medicinale"),
        category="medication",
        price_chf=Decimal("12.34"),
        tax_points=None,
        unit="pack",
        valid_from=date(2024, 1, 1),
        valid_to=None,
        source_url="https://example.test/sl",
        source_version="2024.1",
        harmonization_confidence=0.95,
        requires_review=False,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        version=1,
    )
    frozen = freeze(record)
    repo.add(frozen, embedding=get_embedder().embed("SL MED.0001 Beispielmedikament"))
    conn.close()
    monkeypatch.setenv("TARIFHUB_DB_URL", url)
    from tarifhub_serving.main import app

    return TestClient(app)


# --- ChargeItemDefinition: happy path ----------------------------------------


def test_cid_happy_path_shape_and_values(client):
    """Latest TARDOC/AA.00.0010 (v2) maps to a valid, value-preserving R4 resource."""

    resp = client.get(f"{CID}/TARDOC/AA.00.0010")
    assert resp.status_code == 200
    body = resp.json()

    assert body["resourceType"] == "ChargeItemDefinition"
    # id: lowercased, '.' replaced with '-'  => tardoc-aa-00-0010-2
    assert body["id"] == "tardoc-aa-00-0010-2"
    assert body["url"] == ("https://tarifhub.example/fhir/ChargeItemDefinition/TARDOC/AA.00.0010")
    assert body["version"] == "2"
    # Latest version -> active (deterministic, derived from data not the clock).
    assert body["status"] == "active"
    assert body["name"] == "Grundkonsultation (rev)"
    assert body["title"] == "Grundkonsultation (rev)"

    coding = body["code"]["coding"][0]
    assert coding["system"] == ("https://tarifhub.example/fhir/CodeSystem/TARDOC")
    assert coding["code"] == "AA.00.0010"
    assert coding["display"] == "Grundkonsultation (rev)"

    # effectivePeriod: open-ended -> start present, end omitted.
    assert body["effectivePeriod"] == {"start": "2024-01-01"}

    # tax_points -> informational priceComponent carrying value as a factor.
    component = body["propertyGroup"][0]["priceComponent"][0]
    assert component["type"] == "informational"
    assert component["code"]["text"] == "tax_points"
    # Decimal round-trip: the JSON number equals the frozen tax_points exactly.
    assert Decimal(str(component["factor"])) == Decimal("10.1")

    # Provenance extension carries the record hash, verbatim.
    hashes = [e["valueString"] for e in body["extension"] if e["url"].endswith("/record-hash")]
    assert hashes and len(hashes[0]) == 64  # sha-256 hex


def test_cid_price_chf_maps_to_base_money_component(price_client):
    """A price_chf record emits a base/CHF Money component; the Decimal round-trips."""

    body = price_client.get(f"{CID}/SL/MED.0001").json()
    components = body["propertyGroup"][0]["priceComponent"]
    base = next(c for c in components if c["type"] == "base")
    assert base["amount"]["currency"] == "CHF"
    assert Decimal(str(base["amount"]["value"])) == Decimal("12.34")
    # tax_points is None on this record -> no informational component.
    assert all(c["type"] != "informational" for c in components)


def test_cid_version_param_returns_that_version_retired(client):
    """?version=1 returns the superseded v1, whose status is 'retired'."""

    body = client.get(f"{CID}/TARDOC/AA.00.0010", params={"version": 1}).json()
    assert body["version"] == "1"
    assert body["id"] == "tardoc-aa-00-0010-1"
    assert body["status"] == "retired"
    assert body["name"] == "Grundkonsultation"


def test_cid_as_of_returns_pit_version(client):
    """?as_of inside PIT.0001 v1's 2022 window returns v1."""

    body = client.get(f"{CID}/TARDOC/PIT.0001", params={"as_of": "2022-06-01"}).json()
    assert body["version"] == "1"
    assert body["status"] == "retired"  # v1 is superseded by v2
    assert body["name"] == "Periodenposition alt"


def test_cid_version_beats_as_of(client):
    """version wins over as_of when both are supplied (documented precedence)."""

    body = client.get(f"{CID}/TARDOC/PIT.0001", params={"version": 2, "as_of": "2022-06-01"}).json()
    # as_of=2022 alone would pick v1; version=2 overrides it.
    assert body["version"] == "2"
    assert body["status"] == "active"


def test_cid_unknown_key_returns_404(client):
    resp = client.get(f"{CID}/TARDOC/DOES.NOT.EXIST")
    assert resp.status_code == 404
    assert "no frozen record" in resp.json()["detail"]


def test_cid_unknown_version_returns_404(client):
    resp = client.get(f"{CID}/TARDOC/AA.00.0010", params={"version": 99})
    assert resp.status_code == 404
    assert "99" in resp.json()["detail"]


def test_cid_as_of_gap_date_returns_404(client):
    resp = client.get(f"{CID}/TARDOC/PIT.0001", params={"as_of": "2021-06-01"})
    assert resp.status_code == 404


def test_cid_invalid_as_of_returns_422(client):
    assert client.get(f"{CID}/TARDOC/AA.00.0010", params={"as_of": "nope"}).status_code == 422


def test_cid_is_deterministic_byte_identical(client):
    a = client.get(f"{CID}/TARDOC/AA.00.0010")
    b = client.get(f"{CID}/TARDOC/AA.00.0010")
    assert a.content == b.content


# --- CodeSystem ---------------------------------------------------------------


def test_codesystem_happy_path(client):
    """TARDOC CodeSystem: count of all keys, deterministic windowed concepts."""

    resp = client.get(f"{CS}/TARDOC")
    assert resp.status_code == 200
    body = resp.json()

    assert body["resourceType"] == "CodeSystem"
    assert body["id"] == "tardoc"
    assert body["url"] == "https://tarifhub.example/fhir/CodeSystem/TARDOC"
    assert body["status"] == "active"
    assert body["content"] == "fragment"
    assert body["caseSensitive"] is True
    assert body["publisher"] == "tarifhub"

    # TARDOC latest keys: AA.00.0010, BB.00.0020, PIT.0001 -> count 3.
    assert body["count"] == 3
    codes = [c["code"] for c in body["concept"]]
    assert codes == sorted(codes)  # tariff_code ascending, deterministic
    assert codes == ["AA.00.0010", "BB.00.0020", "PIT.0001"]
    # AA.00.0010 latest is v2: German display from the current designation.
    aa = next(c for c in body["concept"] if c["code"] == "AA.00.0010")
    assert aa["display"] == "Grundkonsultation (rev)"


def test_codesystem_includes_fr_it_designations_when_seeded(price_client):
    """An SL record seeded with fr+it surfaces both as concept.designation entries."""

    body = price_client.get(f"{CS}/SL").json()
    concept = body["concept"][0]
    langs = {d["language"]: d["value"] for d in concept["designation"]}
    assert langs == {"fr": "Medicament", "it": "Medicinale"}


def test_codesystem_count_is_independent_of_window(client):
    """count reflects TOTAL keys even when limit/offset window the concept list."""

    body = client.get(f"{CS}/TARDOC", params={"limit": 1, "offset": 0}).json()
    assert body["count"] == 3  # total, not the window size
    assert len(body["concept"]) == 1


def test_codesystem_limit_and_offset_paginate_deterministically(client):
    page1 = client.get(f"{CS}/TARDOC", params={"limit": 1, "offset": 0}).json()
    page2 = client.get(f"{CS}/TARDOC", params={"limit": 1, "offset": 1}).json()
    assert page1["concept"][0]["code"] == "AA.00.0010"
    assert page2["concept"][0]["code"] == "BB.00.0020"


def test_codesystem_unknown_system_returns_404(client):
    # MIGEL is a valid enum value but has no seeded rows -> empty system -> 404.
    resp = client.get(f"{CS}/MiGeL")
    assert resp.status_code == 404


def test_codesystem_rejects_out_of_range_limit(client):
    assert client.get(f"{CS}/TARDOC", params={"limit": 0}).status_code == 422
    assert client.get(f"{CS}/TARDOC", params={"limit": 100000}).status_code == 422


# --- OpenAPI documentation ----------------------------------------------------


def test_fhir_routes_documented_in_openapi(client):
    """Both FHIR routes appear in /openapi.json with non-empty summary AND description."""

    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    cid_path = "/api/v1/fhir/ChargeItemDefinition/{system}/{code}"
    cs_path = "/api/v1/fhir/CodeSystem/{system}"
    for path in (cid_path, cs_path):
        assert path in paths, f"{path} missing from OpenAPI"
        op = paths[path]["get"]
        assert op["summary"].strip()
        assert op["description"].strip()
