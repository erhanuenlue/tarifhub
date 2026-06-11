"""BAG ePL (SL) FHIR R5 adapter + pipeline tests — fully offline (SQLite, no network).

The fixture ``foph-sl-export-20260601_fixture.ndjson`` is a content-verbatim slice of
the real BAG ePL bulk export (see ``tests/fixtures/epl/README.md``): 255 bundles, 310
GTIN-keyable reimbursed packages, 11 unkeyable packages (PPD without a GTIN → counted
as parse failures, never frozen), 0 duplicate GTINs.

Hostile-input cases use small hand-written NDJSON strings, not the large fixture.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from tarifhub_ingest.adapters import bag_epl
from tarifhub_ingest.audit.audit_logger import AuditLogger
from tarifhub_ingest.config import get_settings
from tarifhub_ingest.ingestion.pipeline import run_pipeline
from tarifhub_ingest.ingestion.source_loader import SourceSpec
from tarifhub_ingest.mappers.tariff_mapper import map_raw
from tarifhub_ingest.models.tariff_model import TariffSystem
from tarifhub_ingest.storage.db import Database
from tarifhub_ingest.storage.tariff_repository import TariffRepository

_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "epl" / "foph-sl-export-20260601_fixture.ndjson"
)
_SL_URL = "https://epl.bag.admin.ch"

# Pinned content hash of the frozen GTIN-7680536620137 record ("3TC Filmtabl 150 mg",
# the first fixture bundle) as produced by the pipeline (map_raw -> deterministic
# scorer confidence 1.0, requires_review False -> freeze). A change here means the
# hashing rule or this record's canonical content changed — which must be deliberate.
GTIN_3TC_HASH = "7a88ab04ae8599c0285bcb371a38d798adaee9f20f7464af5c871390b35076fc"


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    return bag_epl.parse(_FIXTURE)


@pytest.fixture(scope="module")
def record_rows(rows) -> list[dict]:
    """Only the rows that key to a record (drop the fail-closed markers)."""
    return [r for r in rows if not r.get("_parse_failure")]


def _by_code(record_rows: list[dict], code: str) -> dict:
    matches = [r for r in record_rows if r["tariff_code"] == code]
    assert matches, f"GTIN {code} not in fixture"
    return matches[0]


def test_adapter_version_pinned():
    assert bag_epl.ADAPTER_VERSION == "bag-epl/0.1.0"


def test_bundle_count_to_row_count(rows, record_rows):
    """255 bundles -> 310 keyable rows + 11 fail-closed markers (321 total)."""
    assert len(record_rows) == 310
    failures = [r for r in rows if r.get("_parse_failure")]
    assert len(failures) == 11


def test_no_duplicate_gtin_in_fixture(record_rows):
    codes = [r["tariff_code"] for r in record_rows]
    assert len(codes) == len(set(codes))  # GTIN is the frozen join key


def test_trilingual_extraction_spot_check(record_rows):
    """Real product names by usage.language for the first fixture package."""
    raw = _by_code(record_rows, "7680536620137")
    assert raw["designation_de"] == "3TC Filmtabl 150 mg"
    assert raw["designation_fr"] == "3TC cpr pell 150 mg"
    assert raw["designation_it"] == "3TC Filmtabl 150 mg"


def test_retail_price_selected_not_ex_factory(record_rows):
    """price_chf is the RETAIL price (756002005001); ex-factory goes to metadata."""
    raw = _by_code(record_rows, "7680536620137")
    assert raw["price_chf"] == Decimal("191.9")  # retail, not 162.73 ex-factory
    assert isinstance(raw["price_chf"], Decimal)
    assert raw["metadata"]["ex_factory_chf"] == "162.73"
    assert isinstance(raw["metadata"]["ex_factory_chf"], str)  # JSON-native


def test_record_maps_to_canonical(record_rows):
    """The first package round-trips through map_raw with the expected values."""
    raw = _by_code(record_rows, "7680536620137")
    record = map_raw(raw, system=TariffSystem.SL, source_url=_SL_URL)

    assert record.tariff_code == "7680536620137"
    assert record.tariff_system is TariffSystem.SL
    assert record.designation.de == "3TC Filmtabl 150 mg"
    assert record.designation.fr == "3TC cpr pell 150 mg"
    assert record.designation.it == "3TC Filmtabl 150 mg"
    assert record.price_chf == Decimal("191.9")
    assert isinstance(record.price_chf, Decimal)
    # SL is money-only: NO tax points anywhere in the export.
    assert record.tax_points is None
    assert record.unit == "60 Stk"
    assert record.category == "J05AF05"  # ATC code
    assert record.valid_from == date(2026, 6, 1)
    assert record.source_version == "BAG SL 2026-06-01"


def test_tax_points_never_set(record_rows):
    """SL is money-only: every keyable row carries no tax_points."""
    assert all(r.get("tax_points") is None for r in record_rows)


def test_unit_is_pack_size_string(record_rows):
    raw = _by_code(record_rows, "7680536620137")
    assert raw["unit"] == "60 Stk"


def test_category_is_atc_code(record_rows):
    raw = _by_code(record_rows, "7680536620137")
    assert raw["category"] == "J05AF05"


def test_missing_atc_yields_none_category(record_rows):
    """The real ai_map gap: ~55 products carry no ATC -> category None (still keyed)."""
    missing = [r for r in record_rows if r.get("category") is None]
    assert missing, "fixture must contain at least one missing-ATC product"
    sample = missing[0]
    assert sample["tariff_code"]  # still a valid GTIN-keyed row
    assert sample["designation_de"]


def test_metadata_is_json_native(record_rows):
    """All metadata extras must be JSON-serialisable (no Decimal) for the hash."""
    raw = _by_code(record_rows, "7680536620137")
    meta = raw["metadata"]
    # json.dumps must not raise (no Decimal objects).
    json.dumps(meta)
    assert meta["dossier_number"] == "16577"
    assert meta["cost_share_pct"] == 10
    assert isinstance(meta["cost_share_pct"], int)
    assert meta["swissmedic_authno"] == "53662013"
    assert isinstance(meta["has_limitation"], bool)


def test_valid_from_and_version_from_filename():
    """valid_from / source_version are a pure function of the filename convention."""
    assert bag_epl._date_from_filename("foph-sl-export-20260601.ndjson") == date(2026, 6, 1)
    assert (
        bag_epl._source_version_from_filename("foph-sl-export-20260601.ndjson")
        == "BAG SL 2026-06-01"
    )
    # A non-conforming name yields None for both (documented graceful degradation).
    assert bag_epl._date_from_filename("random.ndjson") is None
    assert bag_epl._source_version_from_filename("random.ndjson") is None


def test_open_ended_sentinel_treated_as_none(record_rows):
    """A 2100-12-31 sentinel end date means 'open-ended' -> valid_to None."""
    # No keyable row should carry the sentinel as a concrete valid_to.
    assert all(r.get("valid_to") != "2100-12-31" for r in record_rows)


# --------------------------------------------------------------------------- #
# Hostile-input guards (small hand-written NDJSON, no large fixture)
# --------------------------------------------------------------------------- #


def _minimal_bundle(gtin: str = "7680000000017") -> dict:
    """Smallest bundle that yields one keyable reimbursed-package row."""
    ppd_id = "pkg-1"
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "fullUrl": "http://fhir.epl.bag.admin.ch/MedicinalProductDefinition/mpd-1",
                "resource": {
                    "resourceType": "MedicinalProductDefinition",
                    "id": "mpd-1",
                    "name": [
                        {
                            "productName": "Beispielin",
                            "usage": [{"language": {"coding": [{"code": "de-CH"}]}}],
                        }
                    ],
                    "classification": [
                        {"coding": [{"system": "http://www.whocc.no/atc", "code": "X01"}]}
                    ],
                },
            },
            {
                "fullUrl": f"http://fhir.epl.bag.admin.ch/PackagedProductDefinition/{ppd_id}",
                "resource": {
                    "resourceType": "PackagedProductDefinition",
                    "id": ppd_id,
                    "packaging": {"identifier": [{"system": "urn:oid:2.51.1.1", "value": gtin}]},
                    "containedItemQuantity": [{"unit": "10 Stk"}],
                },
            },
            {
                "fullUrl": "http://fhir.epl.bag.admin.ch/RegulatedAuthorization/ra-foph",
                "resource": {
                    "resourceType": "RegulatedAuthorization",
                    "id": "ra-foph",
                    "type": {
                        "coding": [
                            {
                                "system": "http://fhir.ch/ig/ch-epl/CodeSystem/ch-authorisation-type",
                                "code": "756000002003",
                            }
                        ]
                    },
                    "subject": [{"reference": f"CHIDMPPackagedProductDefinition/{ppd_id}"}],
                    "extension": [
                        {
                            "url": "http://fhir.ch/ig/ch-epl/StructureDefinition/reimbursementSL",
                            "extension": [
                                {
                                    "url": "http://fhir.ch/ig/ch-epl/StructureDefinition/productPrice",
                                    "extension": [
                                        {
                                            "url": "type",
                                            "valueCodeableConcept": {
                                                "coding": [
                                                    {
                                                        "system": "http://fhir.ch/ig/ch-epl/CodeSystem/ch-epl-foph-price-type",
                                                        "code": "756002005001",
                                                    }
                                                ]
                                            },
                                        },
                                        {
                                            "url": "value",
                                            "valueMoney": {"value": 12.5, "currency": "CHF"},
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                },
            },
        ],
    }


def _write_ndjson(path: Path, bundles: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(b) for b in bundles) + "\n", encoding="utf-8")
    return path


def test_minimal_bundle_parses_one_row(tmp_path):
    path = _write_ndjson(tmp_path / "foph-sl-export-20260601.ndjson", [_minimal_bundle()])
    parsed = bag_epl.parse(path)
    keyed = [r for r in parsed if not r.get("_parse_failure")]
    assert len(keyed) == 1
    assert keyed[0]["tariff_code"] == "7680000000017"
    assert keyed[0]["price_chf"] == Decimal("12.5")


def test_refuses_oversized_file(tmp_path, monkeypatch):
    big = tmp_path / "foph-sl-export-20260601.ndjson"
    big.write_text('{"resourceType":"Bundle"}\n', encoding="utf-8")
    monkeypatch.setattr(bag_epl, "_MAX_BYTES", 0)
    with pytest.raises(ValueError, match="over the"):
        bag_epl.parse(big)


def test_refuses_too_many_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(bag_epl, "_MAX_LINES", 1)
    path = _write_ndjson(
        tmp_path / "foph-sl-export-20260601.ndjson",
        [_minimal_bundle("7680000000017"), _minimal_bundle("7680000000024")],
    )
    with pytest.raises(ValueError, match="line"):
        bag_epl.parse(path)


def test_refuses_oversized_line(tmp_path, monkeypatch):
    monkeypatch.setattr(bag_epl, "_MAX_LINE_BYTES", 10)
    path = _write_ndjson(tmp_path / "foph-sl-export-20260601.ndjson", [_minimal_bundle()])
    with pytest.raises(ValueError, match="byte"):
        bag_epl.parse(path)


def test_invalid_json_line_is_hard_fail(tmp_path):
    path = tmp_path / "foph-sl-export-20260601.ndjson"
    path.write_text('{"resourceType":"Bundle","entry":[]}\n{not valid json}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="JSON|decode"):
        bag_epl.parse(path)


def test_duplicate_gtin_is_hard_fail(tmp_path):
    path = _write_ndjson(
        tmp_path / "foph-sl-export-20260601.ndjson",
        [_minimal_bundle("7680000000017"), _minimal_bundle("7680000000017")],
    )
    with pytest.raises(ValueError, match="7680000000017"):
        bag_epl.parse(path)


def test_bundle_without_gtin_is_fail_closed_not_record(tmp_path):
    """A bundle whose package has no GTIN emits a parse_failure marker, no record."""
    bundle = _minimal_bundle()
    # Strip the packaging identifier -> unkeyable package.
    for entry in bundle["entry"]:
        if entry["resource"]["resourceType"] == "PackagedProductDefinition":
            entry["resource"].pop("packaging", None)
    path = _write_ndjson(tmp_path / "foph-sl-export-20260601.ndjson", [bundle])
    parsed = bag_epl.parse(path)
    keyed = [r for r in parsed if not r.get("_parse_failure")]
    failures = [r for r in parsed if r.get("_parse_failure")]
    assert keyed == []
    assert len(failures) == 1


def test_parse_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        bag_epl.parse(tmp_path / "nope.ndjson")


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://epl.bag.admin.ch/x.ndjson",  # wrong scheme
        "file:///etc/passwd",  # file://
        "https://evil.example.com/x.ndjson",  # wrong host
        "https://epl.bag.admin.ch.evil.com/x.ndjson",  # suffix-spoof host
        "https://bag.admin.ch/x.ndjson",  # parent host, not the exact ePL host
    ],
)
def test_fetch_rejects_untrusted_url(bad_url):
    with pytest.raises(ValueError):
        bag_epl._validate_fetch_url(bad_url)


def test_fetch_accepts_epl_host():
    bag_epl._validate_fetch_url("https://epl.bag.admin.ch/static/foph-sl-export-20260601.ndjson")


def test_redirect_handler_refuses_and_names_location():
    """The shared redirect handler raises ValueError naming the rejected Location."""
    from tarifhub_ingest.adapters import _http

    handler = _http._RefuseRedirects()
    with pytest.raises(ValueError, match="evil.example.com"):
        handler.redirect_request(
            req=None,
            fp=None,
            code=302,
            msg="Found",
            headers=None,
            newurl="https://evil.example.com/loot.ndjson",
        )


def test_fetch_download_refuses_redirect(tmp_path, monkeypatch):
    """A 302 on the file download is refused before any byte is read (no network)."""
    import urllib.request

    def _fake_open(request, *, timeout):  # the redirect-refusing opener would raise here
        raise ValueError("fetch refused a 302 redirect to 'https://evil.example.com/x'")

    monkeypatch.setattr(bag_epl, "_validate_fetch_url", lambda url: None)
    monkeypatch.setattr(
        bag_epl, "_download_bytes", lambda url, max_bytes: b'{"fhir": {"fileUrl": "x.ndjson"}}'
    )
    monkeypatch.setattr(bag_epl, "open_no_redirect", _fake_open)
    monkeypatch.setattr(urllib.request, "Request", lambda *a, **k: object())
    with pytest.raises(ValueError, match="redirect"):
        bag_epl.fetch(tmp_path)


# --------------------------------------------------------------------------- #
# Pipeline integration (SQLite, offline)
# --------------------------------------------------------------------------- #


def _pipeline(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    db = Database.from_url(f"sqlite:///{tmp_path / 'epl.db'}")
    conn = db.connect()
    db.init_schema(conn)
    repo = TariffRepository(conn, db)
    audit = AuditLogger(conn, db)
    spec = SourceSpec(system=TariffSystem.SL, kind="bag_epl", path=_FIXTURE, source_url=_SL_URL)
    return [spec], repo, audit, conn


def test_pipeline_source_to_freeze(tmp_path, monkeypatch):
    """End-to-end source->freeze over the ePL fixture on SQLite, kind 'bag_epl'."""
    specs, repo, audit, conn = _pipeline(tmp_path, monkeypatch)
    report = run_pipeline(specs, repo, audit, settings=get_settings())

    assert report.processed == 310  # keyable rows only
    assert report.frozen == 310
    assert report.skipped_existing == 0
    assert report.parse_failures == 11  # unkeyable packages, never frozen

    stored = repo.get("7680536620137", TariffSystem.SL)
    assert stored is not None
    assert stored.price_chf == Decimal("191.9")
    assert stored.tax_points is None
    assert stored.requires_review is False  # complete record scores 1.0
    conn.close()


def test_pipeline_pins_record_hash(tmp_path, monkeypatch):
    """Pinned-hash regression for one known fixture record (GTIN 7680536620137)."""
    specs, repo, audit, conn = _pipeline(tmp_path, monkeypatch)
    run_pipeline(specs, repo, audit, settings=get_settings())

    stored = repo.get("7680536620137", TariffSystem.SL)
    assert stored is not None
    assert stored.record_hash == GTIN_3TC_HASH
    conn.close()


def test_pipeline_is_idempotent_on_rerun(tmp_path, monkeypatch):
    """A second run over the same fixture skips every record (idempotency)."""
    specs, repo, audit, conn = _pipeline(tmp_path, monkeypatch)
    settings = get_settings()

    first = run_pipeline(specs, repo, audit, settings=settings)
    second = run_pipeline(specs, repo, audit, settings=settings)

    assert first.frozen == 310
    assert second.frozen == 0
    assert second.skipped_existing == first.frozen
    assert second.parse_failures == 11  # deterministic count, run-independent
    conn.close()
