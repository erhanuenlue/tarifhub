"""Offline test fixtures: a temp SQLite db seeded with frozen records + a TestClient.

No network, no containers, no API key. The temp DB is provisioned with the ingestion
``Database`` SQLite mirror and seeded via the ingestion ``TariffRepository`` + ``freeze``
helpers (test-only imports — the serving package itself never imports these). The
serving app is pointed at the temp DB through ``TARIFHUB_DB_URL``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem
from tarifhub_ingest.storage.db import Database
from tarifhub_ingest.storage.tariff_repository import TariffRepository
from tarifhub_ingest.versioning.freeze_record import freeze


def _seed_records() -> list[TariffRecord]:
    """Two TARDOC codes (one with v1 + v2) and one EAL code — covers latest-version."""

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
    ]


@pytest.fixture()
def seeded_db_url(tmp_path) -> str:
    db_path = tmp_path / "serving_test.db"
    url = f"sqlite:///{db_path}"
    db = Database.from_url(url)
    conn = db.connect()
    db.init_schema(conn)
    repo = TariffRepository(conn, db)
    for record in _seed_records():
        repo.add(freeze(record))
    conn.close()
    return url


@pytest.fixture()
def client(seeded_db_url, monkeypatch) -> TestClient:
    monkeypatch.setenv("TARIFHUB_DB_URL", seeded_db_url)
    # Import after env is set so the app reads the seeded URL on each request.
    from tarifhub_serving.main import app

    return TestClient(app)


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
