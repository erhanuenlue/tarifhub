"""Both real sources through one canonical model — the format-diversity proof.

EAL (flat XLSX, tax-point based, joined by position) and SL (hierarchical FHIR R5
NDJSON, money-only, keyed by GTIN) run through the SAME ``run_pipeline`` onto the
SAME SQLite store and both freeze. This is the CAS criterion-16 evidence that one
``TariffRecord`` harmonises two structurally different source formats.
"""

from __future__ import annotations

from pathlib import Path

from tarifhub_ingest.audit.audit_logger import AuditLogger
from tarifhub_ingest.config import get_settings
from tarifhub_ingest.ingestion.pipeline import run_pipeline
from tarifhub_ingest.ingestion.source_loader import SourceSpec
from tarifhub_ingest.models.tariff_model import TariffSystem
from tarifhub_ingest.storage.db import Database
from tarifhub_ingest.storage.tariff_repository import TariffRepository

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_EAL_FIXTURE = _FIXTURES / "eal" / "analysenliste_2026-01-01_fixture.xlsx"
_EPL_FIXTURE = _FIXTURES / "epl" / "foph-sl-export-20260601_fixture.ndjson"
_EAL_URL = "https://www.bag.admin.ch/de/analysenliste-al"
_SL_URL = "https://epl.bag.admin.ch"


def _setup(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    db = Database.from_url(f"sqlite:///{tmp_path / 'both.db'}")
    conn = db.connect()
    db.init_schema(conn)
    repo = TariffRepository(conn, db)
    audit = AuditLogger(conn, db)
    specs = [
        SourceSpec(system=TariffSystem.EAL, kind="bag_eal", path=_EAL_FIXTURE, source_url=_EAL_URL),
        SourceSpec(system=TariffSystem.SL, kind="bag_epl", path=_EPL_FIXTURE, source_url=_SL_URL),
    ]
    return specs, repo, audit, conn


def test_both_sources_freeze_into_one_store(tmp_path, monkeypatch):
    specs, repo, audit, conn = _setup(tmp_path, monkeypatch)
    report = run_pipeline(specs, repo, audit, settings=get_settings())

    # EAL fixture = 25 rows, ePL fixture = 310 keyable rows.
    assert report.frozen == 25 + 310
    assert report.parse_failures == 11  # ePL unkeyable packages

    # A known record from each system is present, with the right value type.
    eal = repo.get("1000", TariffSystem.EAL)
    sl = repo.get("7680536620137", TariffSystem.SL)
    assert eal is not None and eal.tax_points is not None and eal.price_chf is None
    assert sl is not None and sl.price_chf is not None and sl.tax_points is None

    # Audit rows exist for both systems.
    cur = conn.execute("SELECT DISTINCT tariff_system FROM audit_log ORDER BY tariff_system")
    systems = {row[0] for row in cur.fetchall()}
    assert "EAL" in systems
    assert "SL" in systems
    conn.close()


def test_both_sources_idempotent(tmp_path, monkeypatch):
    specs, repo, audit, conn = _setup(tmp_path, monkeypatch)
    settings = get_settings()
    first = run_pipeline(specs, repo, audit, settings=settings)
    second = run_pipeline(specs, repo, audit, settings=settings)

    assert second.frozen == 0
    assert second.skipped_existing == first.frozen
    conn.close()
