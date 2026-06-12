"""ADR-003 guard: the canonical TariffRecord field set is locked, additive-only.

A silently removed or renamed field would change the wire contract of every
endpoint — and the /diff field expansion — without any other test necessarily
failing (codex review finding, 2026-06-12). This snapshot makes that a loud,
deliberate change: extending the model appends here (additive-only, ADR-003);
removing or renaming a field requires a new ADR first.
"""

from tarifhub_ingest.models.tariff_model import Designation, TariffRecord

LOCKED_RECORD_FIELDS = [
    "category",
    "created_at",
    "designation",
    "harmonization_confidence",
    "metadata",
    "price_chf",
    "record_hash",
    "requires_review",
    "source_url",
    "source_version",
    "tariff_code",
    "tariff_system",
    "tax_points",
    "unit",
    "valid_from",
    "valid_to",
    "version",
]

LOCKED_DESIGNATION_FIELDS = ["de", "fr", "it"]


def test_canonical_record_field_set_is_locked():
    assert sorted(TariffRecord.model_fields) == LOCKED_RECORD_FIELDS


def test_designation_field_set_is_locked():
    assert sorted(Designation.model_fields) == LOCKED_DESIGNATION_FIELDS
