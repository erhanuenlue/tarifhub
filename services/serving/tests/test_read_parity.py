"""Cross-engine read parity for the serving API (SQLite vs Postgres).

Every test runs against BOTH engines via the ``engine`` fixture (Postgres added when
``TARIFHUB_PG_TEST_URL`` is set). The serving service is read-only, so we seed the SAME
logical frozen records into the engine via the ingestion repository (test-only import),
then assert each read endpoint's FULL JSON body equals an engine-independent expected
snapshot. Both engines matching the same snapshot ⇒ they match each other; SQLite-only
blindness becomes impossible.

Drift surfaces exercised (the Block-0 class): non-ASCII designations (ü, é, ç) for
collation/ordering, nested metadata dicts (JSONB dict vs TEXT json), requires_review
True/False (BOOLEAN vs INTEGER), trailing-zero Decimals (NUMERIC scale vs TEXT),
valid_from/valid_to dates, multiple versions of one key (latest-version GROUP BY),
pagination windows, and the system filter. ``created_at`` is pinned with a fixed clock
so full-body equality is honest. ``/api/v1/search`` is Postgres-only; on SQLite the 501
contract is asserted (in scope only as that contract).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem
from tarifhub_ingest.storage.tariff_repository import TariffRepository
from tarifhub_ingest.versioning.freeze_record import freeze

FIXED_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _seed_records() -> list[TariffRecord]:
    common = dict(
        valid_from=date(2024, 1, 1),
        source_url="https://example.test/src",
        source_version="2024.1",
        harmonization_confidence=0.91,
        created_at=FIXED_NOW,
    )
    return [
        TariffRecord(
            tariff_code="AA.00.0010",
            tariff_system=TariffSystem.TARDOC,
            designation=Designation(de="Übungsbehandlung", fr="Thérapie", it="Terapia"),
            category="therapy",
            tax_points=Decimal("10.50"),
            price_chf=Decimal("12.30"),
            unit="per 5 min",
            valid_to=date(2025, 12, 31),
            requires_review=False,
            metadata={"source": {"page": 3, "lang": ["de", "fr"]}, "rev": 2},
            version=1,
            **common,
        ),
        TariffRecord(
            tariff_code="AA.00.0010",
            tariff_system=TariffSystem.TARDOC,
            designation=Designation(de="Übungsbehandlung (rev)", fr="Thérapie révisée"),
            category="therapy",
            tax_points=Decimal("11.00"),
            price_chf=Decimal("12.30"),
            unit="per 5 min",
            requires_review=True,
            metadata={"source": {"page": 4}, "rev": 3},
            version=2,
            **common,
        ),
        TariffRecord(
            tariff_code="BB.00.0020",
            tariff_system=TariffSystem.TARDOC,
            designation=Designation(de="Çedille-Position", fr="Façade"),
            category="surcharge",
            tax_points=Decimal("4.25"),
            requires_review=True,
            version=1,
            **common,
        ),
        TariffRecord(
            tariff_code="1234.00",
            tariff_system=TariffSystem.EAL,
            designation=Designation(de="Blutzucker (Glukose)", fr="Glycémie élevée"),
            category="lab",
            tax_points=Decimal("2.50"),
            requires_review=False,
            metadata={"unit_count": 1},
            version=1,
            **common,
        ),
    ]


def _seed(engine) -> None:
    conn = engine.db.connect()
    try:
        engine.db.init_schema(conn)
        repo = TariffRepository(conn, engine.db)
        for record in _seed_records():
            repo.add(freeze(record))
    finally:
        conn.close()


@pytest.fixture()
def serving_client(engine, monkeypatch) -> TestClient:
    """Seed the engine, then a TestClient over the serving app bound to it."""

    _seed(engine)
    monkeypatch.setenv("TARIFHUB_DB_URL", engine.db_url)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from tarifhub_serving.main import app

    return TestClient(app)


# --- engine-independent expected snapshots --------------------------------------


def _canonical_decimal(value: str | None) -> str | None:
    """Normalise a serialised Decimal to the scale-canonical read form (10.50 -> 10.5).

    Mirrors ``repository._text_to_decimal``: the read path normalises Decimals to the
    integrity-hash form so the served value is engine-independent.
    """

    if value is None:
        return None
    return format(Decimal(value).normalize(), "f")


def _expected_records() -> list[dict]:
    out: list[dict] = []
    for r in (freeze(rec) for rec in _seed_records()):
        dumped = r.model_dump(mode="json")
        dumped["tax_points"] = _canonical_decimal(dumped["tax_points"])
        dumped["price_chf"] = _canonical_decimal(dumped["price_chf"])
        out.append(dumped)
    return out


def _latest_by_key(records: list[dict]) -> list[dict]:
    latest: dict[tuple[str, str], dict] = {}
    for r in records:
        key = (r["tariff_system"], r["tariff_code"])
        if key not in latest or r["version"] > latest[key]["version"]:
            latest[key] = r
    return sorted(latest.values(), key=lambda r: (r["tariff_system"], r["tariff_code"]))


def test_health_parity(serving_client):
    resp = serving_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_latest_full_body_parity(serving_client):
    """GET /api/v1/tariffs returns the latest version per key, full body, identically."""

    resp = serving_client.get("/api/v1/tariffs")
    assert resp.status_code == 200
    assert resp.json() == _latest_by_key(_expected_records())


def test_list_order_identical_across_engines(serving_client):
    """Result order must be byte-stable across engines.

    The list endpoints ORDER BY ``(tariff_system, tariff_code)`` only — never by a
    designation. Both columns are structurally ASCII (Swiss tariff systems/codes), so
    SQLite's BINARY collation and Postgres's default collation agree and no explicit
    ``COLLATE "C"`` is required. Non-ASCII text (ü, é, ç) lives only in designations,
    which are not ordering keys, so it cannot reorder the result. This test pins that:
    if a future ORDER BY ever sorts on a non-ASCII column, the two engines would diverge
    here and the fix would be an explicit ``COLLATE "C"`` on that column.
    """

    body = serving_client.get("/api/v1/tariffs").json()
    order = [(r["tariff_system"], r["tariff_code"]) for r in body]
    assert order == [(r["tariff_system"], r["tariff_code"]) for r in _latest_by_key(_expected_records())]


def test_list_system_filter_parity(serving_client):
    resp = serving_client.get("/api/v1/tariffs", params={"system": "TARDOC"})
    assert resp.status_code == 200
    body = resp.json()
    expected = [r for r in _latest_by_key(_expected_records()) if r["tariff_system"] == "TARDOC"]
    assert body == expected


def test_list_pagination_windows_parity(serving_client):
    """limit/offset windows return identical pages and identical order on both engines."""

    latest = _latest_by_key(_expected_records())
    page1 = serving_client.get("/api/v1/tariffs", params={"limit": 1, "offset": 0}).json()
    page2 = serving_client.get("/api/v1/tariffs", params={"limit": 1, "offset": 1}).json()
    page3 = serving_client.get("/api/v1/tariffs", params={"limit": 2, "offset": 1}).json()
    assert page1 == latest[0:1]
    assert page2 == latest[1:2]
    assert page3 == latest[1:3]


def test_list_pagination_edge_windows_parity(serving_client):
    """Edge offset/limit windows behave identically across engines (full-body equality).

    Three edges that differ from the happy path:
      * offset == total_rows -> empty page (200, not an error),
      * offset > total_rows  -> empty page (200, no error or off-by-one divergence),
      * limit > remaining rows -> a short last page (all remaining rows, not padded).
    LIMIT/OFFSET semantics past the end can drift between SQLite and Postgres; pin them.
    """

    latest = _latest_by_key(_expected_records())
    total = len(latest)  # 3 keys -> EAL/1234.00, TARDOC/AA.00.0010, TARDOC/BB.00.0020

    # offset exactly at the end: empty page, HTTP 200.
    at_end = serving_client.get("/api/v1/tariffs", params={"limit": 10, "offset": total})
    assert at_end.status_code == 200
    assert at_end.json() == []

    # offset past the end: still an empty page, still 200 (no error, no wraparound).
    past_end = serving_client.get("/api/v1/tariffs", params={"limit": 10, "offset": total + 7})
    assert past_end.status_code == 200
    assert past_end.json() == []

    # limit larger than the rows remaining after the offset -> short last page with
    # exactly the remaining rows (here offset 1 leaves 2 rows; limit 50 must not pad).
    short_last = serving_client.get("/api/v1/tariffs", params={"limit": 50, "offset": 1})
    assert short_last.status_code == 200
    assert short_last.json() == latest[1:]
    assert len(short_last.json()) == total - 1


def test_get_latest_version_parity(serving_client):
    resp = serving_client.get("/api/v1/tariffs/TARDOC/AA.00.0010")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 2
    expected = next(r for r in _latest_by_key(_expected_records()) if r["tariff_code"] == "AA.00.0010")
    assert body == expected


def test_get_unknown_404_parity(serving_client):
    resp = serving_client.get("/api/v1/tariffs/TARDOC/DOES.NOT.EXIST")
    assert resp.status_code == 404


def test_requires_review_bool_read_parity(serving_client):
    """requires_review reads back as JSON bool on both engines (Block-0 twin, read side)."""

    body = serving_client.get("/api/v1/tariffs").json()
    flags = {r["tariff_code"]: r["requires_review"] for r in body}
    # AA latest is v2 (True); BB v1 True; EAL v1 False.
    assert flags["AA.00.0010"] is True
    assert flags["BB.00.0020"] is True
    assert flags["1234.00"] is False


def test_metadata_dict_read_parity(serving_client):
    """Nested metadata dicts survive JSONB(dict) vs TEXT(json) identically."""

    body = serving_client.get("/api/v1/tariffs").json()
    aa = next(r for r in body if r["tariff_code"] == "AA.00.0010")
    assert aa["metadata"] == {"source": {"page": 4}, "rev": 3}


def test_decimal_scale_read_parity(serving_client):
    """Trailing-zero Decimals serialise identically (NUMERIC scale vs TEXT)."""

    body = serving_client.get("/api/v1/tariffs").json()
    aa = next(r for r in body if r["tariff_code"] == "AA.00.0010")
    expected = next(r for r in _latest_by_key(_expected_records()) if r["tariff_code"] == "AA.00.0010")
    assert aa["tax_points"] == expected["tax_points"]  # 11.00 -> "11"
    assert aa["price_chf"] == expected["price_chf"]  # 12.30 -> "12.3"


def test_dates_read_parity(serving_client):
    """valid_from / valid_to (DATE vs TEXT) serialise identically."""

    body = serving_client.get("/api/v1/tariffs").json()
    # BB.00.0020: valid_from set, valid_to None.
    bb = next(r for r in body if r["tariff_code"] == "BB.00.0020")
    assert bb["valid_from"] == "2024-01-01"
    assert bb["valid_to"] is None
    # AA.00.0010 (latest v2): both valid_from and valid_to set.
    aa = next(r for r in body if r["tariff_code"] == "AA.00.0010")
    assert aa["valid_from"] == "2024-01-01"
    # v2 carries no valid_to in the seed; the date-typed None must round-trip identically.
    assert aa["valid_to"] is None


def test_search_contract_per_engine(serving_client, engine):
    """On SQLite search is 501; on Postgres the stub embedder's 16 dims also 501.

    Either way the value path is never faked. The dimension-guard 501 on Postgres is the
    in-scope confirmation that semantic search stays honest cross-engine.
    """

    resp = serving_client.get("/api/v1/search", params={"q": "glucose", "limit": 3})
    assert resp.status_code == 501
    if engine.label == "sqlite":
        assert resp.json()["detail"] == "semantic search requires Postgres+pgvector"
    else:
        assert "1024-dim embedder" in resp.json()["detail"]
