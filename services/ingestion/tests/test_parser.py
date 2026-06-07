"""Parser tests: XLSX (EAL-like) and FHIR (ePL-like), both fully offline."""

from __future__ import annotations

import json

from tarifhub_ingest.parsers import fhir_parser, xlsx_parser


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


def test_fhir_parser_extracts_multilingual_and_price(tmp_path):
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "meta": {"versionId": "ePL-2026-06"},
        "entry": [
            {
                "resource": {
                    "resourceType": "MedicinalProductDefinition",
                    "identifier": [{"system": "urn:bag:sl", "value": "7680000000017"}],
                    "name": [
                        {"language": "de-CH", "productName": "Beispielin 100 mg"},
                        {"language": "fr-CH", "productName": "Exempline 100 mg"},
                        {"language": "it-CH", "productName": "Esempina 100 mg"},
                    ],
                    "classification": [{"text": "Analgetika"}],
                    "price": {"value": 12.50, "currency": "CHF"},
                    "unit": "pack",
                    "validityPeriod": {"start": "2026-01-01"},
                }
            }
        ],
    }
    path = tmp_path / "epl.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")

    rows = fhir_parser.parse(path)

    assert len(rows) == 1
    row = rows[0]
    assert row["tariff_code"] == "7680000000017"
    assert row["designation_de"] == "Beispielin 100 mg"
    assert row["designation_fr"] == "Exempline 100 mg"
    assert row["designation_it"] == "Esempina 100 mg"
    assert row["price_chf"] == 12.50
    assert row["category"] == "Analgetika"
    assert row["source_version"] == "ePL-2026-06"
