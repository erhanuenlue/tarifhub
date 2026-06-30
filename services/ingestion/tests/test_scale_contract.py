"""Decimal scale contract — quantize pre-freeze, lossy fails closed (hash integrity).

The canonical model accepts arbitrary-scale Decimals, but ``db/schema.sql`` declares
``tax_points NUMERIC(12,4)`` and ``price_chf NUMERIC(12,2)``. Without a pre-freeze
contract, Postgres silently rounds on insert, so the STORED bytes differ from the
HASHED bytes — a silent freeze-contract breach. This module pins the contract:

* a NON-LOSSY value is quantized to the canonical scale pre-freeze (76.5 -> 76.5000),
  which is scale-invariant under the freeze canonicalisation and so NEVER moves a hash;
* a LOSSY value (more digits than the column can hold) is set to ``None`` with the
  original preserved as a string in ``metadata["raw_*"]``, and the validator raises an
  ERROR -> ``requires_review`` -> a human decides. The frozen record stores ``None``
  cleanly on every engine.

All offline: SQLite mirror, deterministic scorer, no network.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tarifhub_ingest.audit.audit_logger import AuditLogger
from tarifhub_ingest.config import get_settings
from tarifhub_ingest.ingestion.pipeline import run_pipeline
from tarifhub_ingest.ingestion.source_loader import SourceSpec
from tarifhub_ingest.mappers.tariff_mapper import (
    PRICE_CHF_SCALE,
    TAX_POINTS_SCALE,
    map_raw,
)
from tarifhub_ingest.models.tariff_model import TariffSystem
from tarifhub_ingest.storage.db import Database
from tarifhub_ingest.storage.tariff_repository import TariffRepository
from tarifhub_ingest.validators.tariff_validator import validate
from tarifhub_ingest.versioning.freeze_record import compute_record_hash, freeze


def test_canonical_scales_mirror_schema():
    """The canonical scales mirror db/schema.sql NUMERIC(12,4)/(12,2)."""
    assert TAX_POINTS_SCALE == Decimal("0.0001")
    assert PRICE_CHF_SCALE == Decimal("0.01")


def test_nonlossy_tax_points_quantized_to_four_dp():
    """76.5 -> Decimal('76.5000') (4 dp), the schema's NUMERIC(12,4) scale."""
    record = map_raw({"tariff_code": "X", "designation_de": "Y", "tax_points": "76.5"},
                     system=TariffSystem.EAL)
    assert record.tax_points == Decimal("76.5")
    assert record.tax_points.as_tuple().exponent == -4  # 76.5000


def test_nonlossy_price_chf_quantized_to_two_dp():
    """191.9 -> Decimal('191.90') (2 dp), the schema's NUMERIC(12,2) scale."""
    record = map_raw({"tariff_code": "X", "designation_de": "Y", "price_chf": "191.9"},
                     system=TariffSystem.SL)
    assert record.price_chf == Decimal("191.9")
    assert record.price_chf.as_tuple().exponent == -2  # 191.90


def test_quantization_does_not_move_record_hash():
    """HASH-INVARIANCE: quantizing 76.5 -> 76.5000 yields the same hash as raw 76.5.

    Freeze canonicalisation normalises Decimals (``10.50`` == ``10.5``), so quantizing
    to a wider scale must never change the content hash. This is the proof that the
    pinned EAL/ePL hashes cannot move.
    """
    record = map_raw({"tariff_code": "1000", "designation_de": "Vit D", "tax_points": "76.5"},
                     system=TariffSystem.EAL)
    # Hash of the quantized record equals the hash of a hand-built raw-scale twin.
    raw_twin = record.model_copy(update={"tax_points": Decimal("76.5")})
    assert compute_record_hash(record) == compute_record_hash(raw_twin)


def test_lossy_price_fails_closed_to_none_with_raw_metadata():
    """A 3-dp price (12.345) cannot fit NUMERIC(12,2): billing field -> None, raw kept."""
    record = map_raw({"tariff_code": "X", "designation_de": "Y", "price_chf": "12.345"},
                     system=TariffSystem.SL)
    assert record.price_chf is None
    assert record.metadata["raw_price_chf"] == "12.345"


def test_lossy_tax_points_fails_closed_to_none_with_raw_metadata():
    """A 5-dp tax-point value cannot fit NUMERIC(12,4): field -> None, raw kept."""
    record = map_raw({"tariff_code": "X", "designation_de": "Y", "tax_points": "1.23456"},
                     system=TariffSystem.EAL)
    assert record.tax_points is None
    assert record.metadata["raw_tax_points"] == "1.23456"


def test_over_precision_cap_is_lossy():
    """More than 12 total significant digits overflows the precision cap -> None."""
    record = map_raw({"tariff_code": "X", "designation_de": "Y", "price_chf": "12345678901.99"},
                     system=TariffSystem.SL)
    assert record.price_chf is None
    assert record.metadata["raw_price_chf"] == "12345678901.99"


def test_sub_scale_exponent_value_is_lossy_not_stored():
    """Sub-scale leakage path closed: Decimal('0.0000001') is lossy -> None + review."""
    record = map_raw({"tariff_code": "X", "designation_de": "Y", "price_chf": "0.0000001"},
                     system=TariffSystem.SL)
    assert record.price_chf is None
    assert record.metadata["raw_price_chf"] == "0.0000001"


def test_validator_errors_on_raw_overflow_marker():
    """A raw_* overflow marker makes validate() fail closed -> requires_review."""
    record = map_raw({"tariff_code": "X", "designation_de": "Y", "price_chf": "12.345"},
                     system=TariffSystem.SL)
    result = validate(record)
    assert result.ok is False
    assert any("price_chf" in e and "canonical scale" in e for e in result.errors)


def test_validator_errors_on_raw_tax_points_overflow_marker():
    record = map_raw({"tariff_code": "X", "designation_de": "Y", "tax_points": "1.23456"},
                     system=TariffSystem.EAL)
    result = validate(record)
    assert result.ok is False
    assert any("tax_points" in e and "canonical scale" in e for e in result.errors)


# --------------------------------------------------------------------------- #
# End-to-end: a sub-scale value can no longer reach storage (None + review)
# --------------------------------------------------------------------------- #


def _xlsx_with_price(tmp_path, price: str):
    """Build a minimal EAL-shaped XLSX carrying one row with the given TP value."""
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    de = wb.create_sheet("Deutsch")
    de.append(["Fachbereiche"])
    de.append(["Kapitel", "Pos.-Nr.", "TP", "Bezeichnung", "Chemie"])
    de.append(["k", "9999", price, "Sub-scale probe", "Ja"])
    path = tmp_path / "analysenliste_2026-01-01.xlsx"
    wb.save(path)
    return path


def test_subscale_value_cannot_reach_storage(tmp_path, monkeypatch):
    """Regression: a sub-scale tax-point value is lossy -> stored None + requires_review."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    path = _xlsx_with_price(tmp_path, "0.0000007")

    db = Database.from_url(f"sqlite:///{tmp_path / 'probe.db'}")
    conn = db.connect()
    db.init_schema(conn)
    repo = TariffRepository(conn, db)
    audit = AuditLogger(conn, db)
    spec = SourceSpec(
        system=TariffSystem.EAL, kind="bag_eal", path=path,
        source_url="https://www.bag.admin.ch/de/analysenliste-al",
    )
    report = run_pipeline([spec], repo, audit, settings=get_settings())
    assert report.frozen == 1

    stored = repo.get("9999", TariffSystem.EAL)
    assert stored is not None
    assert stored.tax_points is None  # lossy -> never stored as a value
    assert stored.metadata["raw_tax_points"] == "0.0000007"
    assert stored.requires_review is True  # fail-closed into review

    conn.close()


def test_unscoped_get_tie_break_is_deterministic():
    """An unscoped get() across two systems sharing a code is deterministically ordered.

    ORDER BY tariff_system, version DESC: with the same code in two systems the lowest
    tariff_system name wins (EAL < SL), and within it the highest version.
    """
    db = Database.from_url("sqlite://")
    conn = db.connect()
    db.init_schema(conn)
    repo = TariffRepository(conn, db)

    from tarifhub_ingest.models.tariff_model import Designation, TariffRecord

    shared = "5555"
    repo.add(freeze(TariffRecord(
        tariff_code=shared, tariff_system=TariffSystem.SL,
        designation=Designation(de="SL one"), price_chf=Decimal("1.00"),
        valid_from=date(2026, 1, 1),
    )))
    repo.add(freeze(TariffRecord(
        tariff_code=shared, tariff_system=TariffSystem.EAL,
        designation=Designation(de="EAL one"), tax_points=Decimal("2.0000"),
        valid_from=date(2026, 1, 1),
    )))
    # Unscoped get(): deterministic — EAL sorts before SL.
    got = repo.get(shared)
    assert got is not None
    assert got.tariff_system is TariffSystem.EAL
    conn.close()
