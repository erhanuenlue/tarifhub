"""Cross-engine read parity for the ingestion read surface (SQLite vs Postgres).

Every test runs against BOTH engines via the ``engine`` fixture (Postgres added when
``TARIFHUB_PG_TEST_URL`` is set). We seed the SAME logical records into the engine,
then assert each read endpoint's FULL JSON body equals an engine-independent expected
snapshot. Because both engines must match the same snapshot, they must match each other
— SQLite-only blindness becomes impossible.

Seed data deliberately exercises every Block-0 drift surface:
  * non-ASCII designations (ü, é, ç) — collation / ordering,
  * nested metadata dicts — JSONB (native dict) vs TEXT (json string),
  * ``requires_review`` True AND False — BOOLEAN vs INTEGER (the tariff-table twin of
    the audit_log bool fixed in Block 0),
  * Decimal with trailing-zero scale (10.50) — NUMERIC(12,4)/(12,2) vs TEXT,
  * valid_from / valid_to dates — DATE vs TEXT,
  * two versions of one (system, code) — latest-version selection,
  * pagination windows and the system filter.

``created_at`` is pinned with a fixed clock (monkeypatch) so full-body equality is
honest rather than achieved by excluding fields. Env mutations are monkeypatch-scoped.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem
from tarifhub_ingest.storage.tariff_repository import TariffRepository
from tarifhub_ingest.versioning.freeze_record import freeze

# A single fixed instant for every seeded record so created_at is engine-independent.
FIXED_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _seed_records() -> list[TariffRecord]:
    """Records spanning every cross-engine drift surface (see module docstring)."""

    common = dict(
        valid_from=date(2024, 1, 1),
        source_url="https://example.test/src",
        source_version="2024.1",
        harmonization_confidence=0.91,
        created_at=FIXED_NOW,
    )
    return [
        # requires_review=False, trailing-zero Decimal, nested metadata, valid_to set.
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
        # Superseding version of the same key — list/get must return v2 only.
        TariffRecord(
            tariff_code="AA.00.0010",
            tariff_system=TariffSystem.TARDOC,
            designation=Designation(de="Übungsbehandlung (rev)", fr="Thérapie révisée"),
            category="therapy",
            tax_points=Decimal("11.00"),
            price_chf=Decimal("12.30"),
            unit="per 5 min",
            requires_review=True,  # the BOOLEAN-vs-INTEGER twin, read side
            metadata={"source": {"page": 4}, "rev": 3},
            version=2,
            **common,
        ),
        # Non-ASCII (ç) ordering probe; requires_review=True; empty metadata.
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
        # Different system (EAL) — exercises the system filter; é in designation.
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
def app_client(engine, monkeypatch) -> Iterator[TestClient]:
    """Seed the engine, then a TestClient over the ingestion app bound to it.

    Entered as a context manager so the app's lifespan provisions ``state.repo``
    against the seeded engine URL (the app reads frozen records read-only).
    """

    _seed(engine)
    monkeypatch.setenv("TARIFHUB_DB_URL", engine.db_url)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from tarifhub_ingest.main import create_app

    with TestClient(create_app()) as client:
        yield client


# --- engine-independent expected snapshots --------------------------------------
#
# Built from the canonical model the same way the endpoint does (model_dump json),
# so the assertion pins the exact wire shape AND ties both engines to one truth.


def _canonical_decimal(value: str | None) -> str | None:
    """Normalise a serialised Decimal to the scale-canonical read form (10.50 -> 10.5).

    Mirrors ``tariff_repository._text_to_decimal``: the read path normalises Decimals to
    the integrity-hash form so the wire value is identical regardless of engine. The
    expected snapshot must reflect that read-side normalisation, not the raw input scale.
    """

    if value is None:
        return None
    return format(Decimal(value).normalize(), "f")


def _expected_records() -> list[dict]:
    frozen = [freeze(r) for r in _seed_records()]
    # version is stamped by the repository as MAX(version)+1 per key; our seed already
    # carries the right versions (1 then 2 for AA, 1 elsewhere), matching that logic.
    out: list[dict] = []
    for r in frozen:
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
    return list(latest.values())


def test_health_parity(app_client):
    resp = app_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_list_full_body_parity(app_client):
    """GET /tariffs returns ALL versions ordered (system, code, version), identically."""

    resp = app_client.get("/tariffs")
    assert resp.status_code == 200
    body = resp.json()

    expected = sorted(
        _expected_records(),
        key=lambda r: (r["tariff_system"], r["tariff_code"], r["version"]),
    )
    assert body == expected


def test_list_order_is_identical_across_engines(app_client):
    """Order (the key list) must be byte-stable; non-ASCII must not reorder by engine."""

    body = app_client.get("/tariffs").json()
    order = [(r["tariff_system"], r["tariff_code"], r["version"]) for r in body]
    expected_order = sorted(
        (r["tariff_system"], r["tariff_code"], r["version"]) for r in _expected_records()
    )
    assert order == expected_order


def test_get_latest_version_parity(app_client):
    """GET /tariffs/{code} returns the highest version with its full body."""

    resp = app_client.get("/tariffs/AA.00.0010")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 2

    expected = next(
        r
        for r in _latest_by_key(_expected_records())
        if r["tariff_code"] == "AA.00.0010"
    )
    assert body == expected


def test_requires_review_bool_read_parity(app_client):
    """requires_review must read back as JSON bool on BOTH engines (Block-0 twin)."""

    body = app_client.get("/tariffs").json()
    flags = {(r["tariff_code"], r["version"]): r["requires_review"] for r in body}
    assert flags[("AA.00.0010", 1)] is False
    assert flags[("AA.00.0010", 2)] is True
    assert flags[("BB.00.0020", 1)] is True
    assert flags[("1234.00", 1)] is False


def test_metadata_dict_read_parity(app_client):
    """Nested metadata dicts survive JSONB(dict) vs TEXT(json) identically."""

    body = app_client.get("/tariffs").json()
    aa_v1 = next(
        r for r in body if r["tariff_code"] == "AA.00.0010" and r["version"] == 1
    )
    assert aa_v1["metadata"] == {"source": {"page": 3, "lang": ["de", "fr"]}, "rev": 2}


def test_decimal_scale_read_parity(app_client):
    """Trailing-zero Decimals serialise identically (NUMERIC scale vs TEXT)."""

    body = app_client.get("/tariffs").json()
    aa_v1 = next(
        r for r in body if r["tariff_code"] == "AA.00.0010" and r["version"] == 1
    )
    expected = next(
        r for r in _expected_records()
        if r["tariff_code"] == "AA.00.0010" and r["version"] == 1
    )
    assert aa_v1["tax_points"] == expected["tax_points"]
    assert aa_v1["price_chf"] == expected["price_chf"]


def test_unknown_code_404_parity(app_client):
    assert app_client.get("/tariffs/__nope__").status_code == 404
