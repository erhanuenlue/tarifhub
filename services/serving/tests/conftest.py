"""Offline test fixtures: a temp SQLite db seeded with frozen records + a TestClient.

No network, no containers, no API key. The temp DB is provisioned with the ingestion
``Database`` SQLite mirror and seeded via the ingestion ``TariffRepository`` + ``freeze``
helpers (test-only imports — the serving package itself never imports these). The
serving app is pointed at the temp DB through ``TARIFHUB_DB_URL``.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tarifhub_ingest.embeddings.embedder import get_embedder
from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem
from tarifhub_ingest.storage.db import Database
from tarifhub_ingest.storage.tariff_repository import TariffRepository
from tarifhub_ingest.versioning.freeze_record import freeze
from _parity import ENGINE_PARAMS, Engine, make_engine


def _embedding_text(record: TariffRecord) -> str:
    """Mirror the ingestion pipeline's passage-side embedding input text exactly.

    Ingestion builds the embedded passage as ``"{system} {code} {designation.de}"``
    (see ``ingestion.pipeline``); the offline search fallback ranks against vectors
    produced this same way, so the test seeds must use the identical recipe.
    """

    return f"{record.tariff_system.value} {record.tariff_code} {record.designation.de}"


def _seed_records() -> list[TariffRecord]:
    """Seed set covering latest-version, point-in-time windows and search ranking.

    The original three keys (AA.00.0010 v1+v2, BB.00.0020, 1234.00) are kept byte-for-
    byte so the existing latest-version tests stay green. New point-in-time keys carry
    distinct validity windows across versions, plus a NULL-``valid_from`` "beginning of
    time" record, so the ``?as_of=`` filter has something to discriminate.
    """

    base = dict(
        category="consultation",
        valid_from=date(2024, 1, 1),
        source_url="https://example.test/src",
        source_version="2024.1",
        harmonization_confidence=0.95,
        requires_review=False,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    return [
        TariffRecord(
            tariff_code="AA.00.0010",
            tariff_system=TariffSystem.TARDOC,
            designation=Designation(de="Grundkonsultation", fr="Consultation de base"),
            tax_points=Decimal("9.57"),
            unit="per 5 min",
            version=1,
            **base,
        ),
        # A superseding version of the same key — list/get must return v2 only.
        TariffRecord(
            tariff_code="AA.00.0010",
            tariff_system=TariffSystem.TARDOC,
            designation=Designation(de="Grundkonsultation (rev)", fr="Consultation de base"),
            tax_points=Decimal("10.10"),
            unit="per 5 min",
            version=2,
            **base,
        ),
        TariffRecord(
            tariff_code="BB.00.0020",
            tariff_system=TariffSystem.TARDOC,
            designation=Designation(de="Zuschlag Komplexität"),
            tax_points=Decimal("4.25"),
            version=1,
            **base,
        ),
        TariffRecord(
            tariff_code="1234.00",
            tariff_system=TariffSystem.EAL,
            designation=Designation(de="Blutzucker (Glukose)"),
            tax_points=Decimal("2.50"),
            version=1,
            **base,
        ),
        # --- Point-in-time keys (new; do not affect the existing latest tests) -----
        # PIT.0001 has two non-overlapping validity windows across versions:
        #   v1 valid 2022-01-01 .. 2022-12-31  (historical)
        #   v2 valid 2023-01-01 .. open-ended  (current)
        # An as_of in 2022 must return v1; an as_of in 2024 must return v2; a gap date
        # before 2022 returns nothing.
        TariffRecord(
            tariff_code="PIT.0001",
            tariff_system=TariffSystem.TARDOC,
            designation=Designation(de="Periodenposition alt"),
            category="consultation",
            tax_points=Decimal("5.00"),
            valid_from=date(2022, 1, 1),
            valid_to=date(2022, 12, 31),
            source_url="https://example.test/src",
            source_version="2022.1",
            harmonization_confidence=0.95,
            requires_review=False,
            created_at=datetime(2022, 1, 1, tzinfo=timezone.utc),
            version=1,
        ),
        TariffRecord(
            tariff_code="PIT.0001",
            tariff_system=TariffSystem.TARDOC,
            designation=Designation(de="Periodenposition neu"),
            category="consultation",
            tax_points=Decimal("6.00"),
            valid_from=date(2023, 1, 1),
            valid_to=None,
            source_url="https://example.test/src",
            source_version="2023.1",
            harmonization_confidence=0.95,
            requires_review=False,
            created_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            version=2,
        ),
        # PIT.NULLFROM has a NULL valid_from -> valid from the beginning of time. Any
        # as_of on or before its valid_to must match it.
        TariffRecord(
            tariff_code="PIT.NULLFROM",
            tariff_system=TariffSystem.EAL,
            designation=Designation(de="Urposition ohne Startdatum"),
            category="lab",
            tax_points=Decimal("3.00"),
            valid_from=None,
            valid_to=date(2022, 6, 30),
            source_url="https://example.test/src",
            source_version="2020.1",
            harmonization_confidence=0.95,
            requires_review=False,
            created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            version=1,
        ),
    ]


def _seed(repo: TariffRepository) -> None:
    """Freeze + store every seed record with a stub-embedder passage embedding."""

    embedder = get_embedder()
    for record in _seed_records():
        frozen = freeze(record)
        embedding = embedder.embed(_embedding_text(frozen))
        repo.add(frozen, embedding=embedding)


@pytest.fixture()
def seeded_db_url(tmp_path) -> str:
    db_path = tmp_path / "serving_test.db"
    url = f"sqlite:///{db_path}"
    db = Database.from_url(url)
    conn = db.connect()
    db.init_schema(conn)
    repo = TariffRepository(conn, db)
    _seed(repo)
    conn.close()
    return url


@pytest.fixture()
def client(seeded_db_url, monkeypatch) -> TestClient:
    monkeypatch.setenv("TARIFHUB_DB_URL", seeded_db_url)
    # Import after env is set so the app reads the seeded URL on each request.
    from tarifhub_serving.main import app

    return TestClient(app)


@pytest.fixture(params=ENGINE_PARAMS)
def engine(request, tmp_path) -> Iterator[Engine]:
    """Yield a provisioned, isolated DB engine (sqlite always; postgres when opted in).

    Parity tests request this fixture and assert the serving API returns identical JSON
    on both engines, making Postgres-vs-SQLite drift impossible to pass silently.
    """

    yield from make_engine(request.param, tmp_path)


@pytest.fixture()
def empty_client(tmp_path, monkeypatch) -> TestClient:
    db_path = tmp_path / "serving_empty.db"
    url = f"sqlite:///{db_path}"
    db = Database.from_url(url)
    conn = db.connect()
    db.init_schema(conn)
    conn.close()
    monkeypatch.setenv("TARIFHUB_DB_URL", url)
    from tarifhub_serving.main import app

    return TestClient(app)


@pytest.fixture()
def no_embedding_client(tmp_path, monkeypatch) -> TestClient:
    """A seeded DB whose rows have NO stored embedding (search must exclude them)."""

    db_path = tmp_path / "serving_no_embedding.db"
    url = f"sqlite:///{db_path}"
    db = Database.from_url(url)
    conn = db.connect()
    db.init_schema(conn)
    repo = TariffRepository(conn, db)
    for record in _seed_records():
        repo.add(freeze(record))  # no embedding=
    conn.close()
    monkeypatch.setenv("TARIFHUB_DB_URL", url)
    from tarifhub_serving.main import app

    return TestClient(app)
