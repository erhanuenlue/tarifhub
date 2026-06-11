"""Parser tests: XLSX (EAL-like) and the ePL FHIR R5 sample, both fully offline.

The toy ``fhir_parser`` was retired (PR ``feat/epl-sl-fhir-source``) in favour of the
real :mod:`tarifhub_ingest.adapters.bag_epl` FHIR R5 adapter; its detailed coverage
lives in ``tests/test_bag_epl.py``. Here we only smoke-test the shipped offline
``bag_epl_sample.ndjson`` so ``discover_samples`` has a parseable SL artifact.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from tarifhub_ingest.adapters import bag_epl
from tarifhub_ingest.parsers import xlsx_parser

_SAMPLE_DIR = Path(__file__).resolve().parents[1] / "sample-data" / "input"
_EPL_SAMPLE = _SAMPLE_DIR / "bag_epl_sample.ndjson"


def test_xlsx_parser_reads_header_and_rows(tmp_path):
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["tariff_code", "designation_de", "tax_points", "unit", "valid_from"])
    sheet.append(["0010.00", "Hämatokrit", 8.5, "point", "2026-01-01"])
    sheet.append(["0020.00", "Hämoglobin", 5.0, "point", "2026-01-01"])
    sheet.append([None, None, None, None, None])  # blank row is dropped
    path = tmp_path / "eal.xlsx"
    workbook.save(path)

    rows = xlsx_parser.parse(path)

    assert len(rows) == 2
    assert rows[0]["tariff_code"] == "0010.00"
    assert rows[0]["designation_de"] == "Hämatokrit"
    assert rows[0]["tax_points"] == 8.5


def test_csv_parser_roundtrip(tmp_path):
    path = tmp_path / "eal.csv"
    path.write_text(
        "tariff_code,designation_de,tax_points,unit,valid_from\n"
        "0010.00,Hämatokrit,8.5,point,2026-01-01\n",
        encoding="utf-8",
    )
    rows = xlsx_parser.parse(path)
    assert rows == [
        {
            "tariff_code": "0010.00",
            "designation_de": "Hämatokrit",
            "tax_points": "8.5",
            "unit": "point",
            "valid_from": "2026-01-01",
        }
    ]


def test_epl_sample_parses_real_bundles():
    """The shipped offline SL sample (3 real bundles) parses into keyed rows."""
    rows = bag_epl.parse(_EPL_SAMPLE)
    keyed = [r for r in rows if not r.get("_parse_failure")]
    assert keyed, "ePL sample must yield at least one keyable row"
    first = next(r for r in keyed if r["tariff_code"] == "7680536620137")
    assert first["designation_de"] == "3TC Filmtabl 150 mg"
    assert first["designation_fr"] == "3TC cpr pell 150 mg"
    assert first["price_chf"] == Decimal("191.9")  # retail price, Decimal-typed
    assert first["tax_points"] is None  # SL is money-only
