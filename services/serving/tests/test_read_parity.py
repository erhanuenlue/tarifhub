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
        # Max canonical scales: price_chf 12.34 (NUMERIC(12,2)) + tax_points 76.5000
        # (NUMERIC(12,4)). At the column scales exactly, so both engines must serialise
        # the SAME canonical Decimal — the scale contract's cross-engine proof.
        TariffRecord(
            tariff_code="SCALE.MAX",
            tariff_system=TariffSystem.EAL,
            designation=Designation(de="Skalengrenze"),
            category="lab",
            tax_points=Decimal("76.5000"),
            price_chf=Decimal("12.34"),
            requires_review=False,
            version=1,
            **common,
        ),
        # Lossy-input fail-closed shape: billing field None + original kept as a metadata
        # raw_* string. Both engines store None cleanly and round-trip the same marker.
        TariffRecord(
            tariff_code="SCALE.LOSSY",
            tariff_system=TariffSystem.EAL,
            designation=Designation(de="Verlustfall"),
            category="lab",
            price_chf=None,
            metadata={"raw_price_chf": "12.345"},
            requires_review=True,
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


def test_max_scale_and_lossy_record_parity(serving_client):
    """Max-scale + lossy-input records round-trip identically on both engines.

    SCALE.MAX sits exactly at NUMERIC(12,4)/(12,2); SCALE.LOSSY is the fail-closed shape
    (billing field None + raw_* metadata marker). Both engines must serialise the same
    canonical Decimals and the same None+marker — the scale contract's served invariant
    across the engine boundary.
    """

    body = serving_client.get("/api/v1/tariffs").json()
    maxr = next(r for r in body if r["tariff_code"] == "SCALE.MAX")
    expected_max = next(r for r in _latest_by_key(_expected_records()) if r["tariff_code"] == "SCALE.MAX")
    assert maxr["tax_points"] == expected_max["tax_points"]  # 76.5000 -> "76.5"
    assert maxr["price_chf"] == expected_max["price_chf"]  # 12.34 -> "12.34"

    lossy = next(r for r in body if r["tariff_code"] == "SCALE.LOSSY")
    assert lossy["price_chf"] is None
    assert lossy["metadata"]["raw_price_chf"] == "12.345"
    assert lossy["requires_review"] is True


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


def test_as_of_point_in_time_parity(serving_client):
    """?as_of= picks the version whose validity window covers the date, on both engines.

    AA.00.0010 v1 is valid 2024-01-01..2025-12-31; v2 carries no valid_to (open-ended)
    and a later created_at but the SAME valid_from. For an as_of in 2024 BOTH versions'
    windows cover the date, so the MAX(version) tie-break selects v2. The point this pins
    cross-engine is the window predicate + version tie-break, identical on SQLite/Postgres.
    """

    resp = serving_client.get("/api/v1/tariffs", params={"as_of": "2024-06-01"})
    assert resp.status_code == 200
    aa = next(r for r in resp.json() if r["tariff_code"] == "AA.00.0010")
    expected = next(r for r in _latest_by_key(_expected_records()) if r["tariff_code"] == "AA.00.0010")
    assert aa == expected

    # A get with as_of returns the same versioned record, full body, on both engines.
    got = serving_client.get("/api/v1/tariffs/TARDOC/AA.00.0010", params={"as_of": "2024-06-01"})
    assert got.status_code == 200
    assert got.json() == expected


def test_diff_parity(serving_client):
    """The v1->v2 diff of AA.00.0010 is identical across engines (full body)."""

    resp = serving_client.get(
        "/api/v1/tariffs/TARDOC/AA.00.0010/diff", params={"from": 1, "to": 2}
    )
    assert resp.status_code == 200
    body = resp.json()
    changed = {c["field"]: (c["from_value"], c["to_value"]) for c in body["changes"]}
    # designation.de and designation.fr both changed v1->v2 in the parity seed.
    assert changed["designation.de"] == ("Übungsbehandlung", "Übungsbehandlung (rev)")
    assert changed["designation.fr"] == ("Thérapie", "Thérapie révisée")
    # tax_points 10.50 -> 11.00, rendered in the canonical read form (10.5 -> 11).
    assert changed["tax_points"] == ("10.5", "11")
    # requires_review False -> True diffs as JSON booleans on both engines.
    assert changed["requires_review"] == (False, True)
    # Deterministic field-name order.
    fields = [c["field"] for c in body["changes"]]
    assert fields == sorted(fields)


def test_explain_parity(serving_client):
    """The explain payload (records + labelled deterministic text) matches across engines."""

    resp = serving_client.get("/api/v1/explain", params={"code": "AA.00.0010"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "AA.00.0010"
    assert [(r["tariff_system"], r["version"]) for r in body["records"]] == [
        ("TARDOC", 1),
        ("TARDOC", 2),
    ]
    assert body["explanation"].startswith("[deterministic]")


def test_search_contract_per_engine(serving_client, engine):
    """On SQLite search now ranks in-process; on Postgres the stub's 16 dims still 501.

    Either way the value path is never faked. On SQLite the offline fallback ranks stored
    embeddings (the parity seed stores none, so the result is an empty ranked list, HTTP
    200). On Postgres the dimension-guard 501 (16 != 1024) keeps search honest cross-engine.
    """

    resp = serving_client.get("/api/v1/search", params={"q": "glucose", "limit": 3})
    if engine.label == "sqlite":
        # Parity seed stores no embeddings -> no candidates -> empty ranked list, 200.
        assert resp.status_code == 200
        assert resp.json() == []
    else:
        assert resp.status_code == 501
        assert "1024-dim embedder" in resp.json()["detail"]


def test_pgvector_search_sql_deterministic(engine, monkeypatch):
    """pgvector search-SQL returns 200 + deterministic ordering (Postgres leg only).

    Seeds 1024-dim embeddings from a deterministic HashingEmbedder(dimension=1024) so the
    pgvector column dimensions match, points the serving query embedder at the same stub,
    runs /api/v1/search, and asserts a 200 with a stable ranked order (same query -> same
    ordering across runs). Skips offline like the other Postgres-only tests. The hits are
    unaltered frozen rows — search only RANKS, never computes a value.
    """

    if engine.label != "postgres":
        pytest.skip("pgvector search requires Postgres")

    from tarifhub_ingest.embeddings.embedder import E5_DIMENSION, HashingEmbedder

    stub = HashingEmbedder(dimension=E5_DIMENSION)  # 1024-dim, matches vector(1024)
    conn = engine.db.connect()
    try:
        engine.db.init_schema(conn)
        repo = TariffRepository(conn, engine.db)
        for record in _seed_records():
            frozen = freeze(record)
            text = f"{frozen.tariff_system.value} {frozen.tariff_code} {frozen.designation.de}"
            repo.add(frozen, embedding=stub.embed(text))
    finally:
        conn.close()

    # Point both the serving query embedder AND its default at the 1024-dim stub.
    monkeypatch.setattr("tarifhub_serving.main.get_embedder", lambda *_a, **_k: stub)
    monkeypatch.setenv("TARIFHUB_DB_URL", engine.db_url)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from tarifhub_serving.main import app

    client = TestClient(app)
    first = client.get("/api/v1/search", params={"q": "Glukose", "limit": 3})
    assert first.status_code == 200, first.text
    order1 = [(h["record"]["tariff_system"], h["record"]["tariff_code"]) for h in first.json()]
    assert order1, "search must return at least one ranked hit"
    # Ranks are 1..n and strictly increasing (deterministic ordering contract).
    assert [h["rank"] for h in first.json()] == list(range(1, len(first.json()) + 1))

    # Same query -> identical ordering (pgvector cosine SQL is deterministic).
    second = client.get("/api/v1/search", params={"q": "Glukose", "limit": 3})
    order2 = [(h["record"]["tariff_system"], h["record"]["tariff_code"]) for h in second.json()]
    assert order2 == order1
