"""Offline integration fixtures: the REAL serving app, wired to the MCP tools in-process.

The unit suite (``test_tools.py``) mocks HTTP, so it would pass even if serving never
implemented the endpoints. This harness instead builds the genuine serving FastAPI app
against a temp SQLite DB seeded with frozen records, and connects the MCP tools to it via
``httpx.ASGITransport`` — no network, no containers, no API key.

Seeding mirrors ``services/serving/tests/conftest.py`` exactly (freeze each record, then
store it with a stub-embedder passage embedding built from the same
``"{system} {code} {designation.de}"`` recipe the ingestion pipeline uses) so the offline
SQLite search fallback can rank the seeded rows. These imports are TEST-ONLY: the MCP
runtime code (``server.py``, ``config.py``) imports neither serving nor ingestion.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
import pytest

import config
import server
from tarifhub_ingest.embeddings.embedder import get_embedder
from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem
from tarifhub_ingest.storage.db import Database
from tarifhub_ingest.storage.tariff_repository import TariffRepository
from tarifhub_ingest.versioning.freeze_record import freeze

# A seeded key whose designation a query can match for the search test.
SEARCH_KEY = ("EAL", "1234.00")
SEARCH_QUERY = "Blutzucker Glukose"
# A key with two frozen versions, used to prove explain returns every version verbatim.
MULTI_VERSION_KEY = ("TARDOC", "AA.00.0010")
UNKNOWN_CODE = "ZZ.99.9999"


def _embedding_text(record: TariffRecord) -> str:
    """Mirror the ingestion pipeline's passage-side embedding input text exactly.

    The offline search fallback ranks against vectors produced as
    ``"{system} {code} {designation.de}"`` (see ``ingestion.pipeline``), so the seeds must
    use the identical recipe or the deterministic cosine ranking would not surface them.
    """

    return f"{record.tariff_system.value} {record.tariff_code} {record.designation.de}"


def _seed_records() -> list[TariffRecord]:
    """A small frozen seed set: a two-version key, plus distinct single-version keys."""

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
        # A superseding version of the same key — explain must return BOTH versions.
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
            designation=Designation(de="Zuschlag Komplexitaet"),
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


def _seed(repo: TariffRepository) -> None:
    """Freeze + store every seed record with a stub-embedder passage embedding."""

    embedder = get_embedder()
    for record in _seed_records():
        frozen = freeze(record)
        embedding = embedder.embed(_embedding_text(frozen))
        repo.add(frozen, embedding=embedding)


@pytest.fixture()
def seeded_db_url(tmp_path) -> str:
    """Provision a temp SQLite DB seeded with frozen records + embeddings; return its URL."""

    db_path = tmp_path / "mcp_integration.db"
    url = f"sqlite:///{db_path}"
    db = Database.from_url(url)
    conn = db.connect()
    db.init_schema(conn)
    _seed(TariffRepository(conn, db))
    conn.close()
    return url


@pytest.fixture()
def serving_app(seeded_db_url, monkeypatch):
    """The REAL serving FastAPI app, pointed at the seeded temp DB via TARIFHUB_DB_URL.

    Imported after the env is set; serving reads ``TARIFHUB_DB_URL`` live on each request,
    so a fresh connection to the seeded store is opened per call.
    """

    monkeypatch.setenv("TARIFHUB_DB_URL", seeded_db_url)
    from tarifhub_serving.main import app

    return app


@pytest.fixture()
def serving_client(serving_app) -> Iterator[httpx.AsyncClient]:
    """A direct async client onto the serving ASGI app — the ground-truth oracle.

    The integration tests compare what the MCP tool returns against a direct GET issued
    through this client, so a passthrough divergence (the tool mutating a value) would fail.
    """

    transport = httpx.ASGITransport(app=serving_app)
    client = httpx.AsyncClient(base_url="http://serving.asgi", transport=transport)
    yield client


@pytest.fixture()
def wire_mcp_to_serving(serving_app, monkeypatch) -> None:
    """Point the MCP tools at the in-process serving app via ``httpx.ASGITransport``.

    Uses the exact seam the unit suite uses — monkeypatching ``server.build_client`` — so
    no runtime code changes. ``config.build_client`` already accepts an optional
    ``transport``; here we hand it a real ``ASGITransport`` bound to the seeded serving app
    instead of a ``MockTransport``, making every tool call a genuine round-trip to serving.
    """

    def factory() -> httpx.AsyncClient:
        return config.build_client(transport=httpx.ASGITransport(app=serving_app))

    monkeypatch.setattr(server, "build_client", factory)
