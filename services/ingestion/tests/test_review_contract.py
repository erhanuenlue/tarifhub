"""Contract test: the ingestion review models match the console's TypeScript types.

Parses the field names out of ``apps/tarifguard/lib/api.ts`` and asserts the Pydantic
models in ``tarifhub_ingest.review`` expose exactly the same keys — so a drift on either
side (the BFF proxies the decision straight through) fails here rather than at runtime.
Fully offline: it reads the source file, never the network.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem
from tarifhub_ingest.review import (
    ReviewDecision,
    ReviewField,
    ReviewItem,
    ReviewResult,
    to_review_item,
)

_API_TS = Path(__file__).resolve().parents[3] / "apps" / "tarifguard" / "lib" / "api.ts"


def _interface_fields(name: str) -> set[str]:
    """Return the top-level property names declared in `export interface <name> { ... }`."""

    src = _API_TS.read_text(encoding="utf-8")
    match = re.search(rf"interface {name} \{{(.*?)\n\}}", src, re.DOTALL)
    assert match, f"interface {name} not found in {_API_TS}"
    body = match.group(1)
    # `name?: type;` / `name: type;` at the start of a line — strip the optional marker.
    return set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\??\s*:", body, re.MULTILINE))


def test_review_field_keys_match_console():
    assert set(ReviewField.model_fields) == _interface_fields("ReviewField")


def test_review_item_keys_match_console():
    assert set(ReviewItem.model_fields) == _interface_fields("ReviewItem")


def test_review_decision_keys_match_console():
    assert set(ReviewDecision.model_fields) == _interface_fields("ReviewDecision")


def test_review_result_keys_match_console():
    assert set(ReviewResult.model_fields) == _interface_fields("ReviewResult")


def _flagged() -> TariffRecord:
    return TariffRecord(
        tariff_code="0010.00",
        tariff_system=TariffSystem.EAL,
        designation=Designation(de="Hämatokrit", fr="Hématocrite", it=None),
        category="Hämatologie",
        tax_points=Decimal("8.50"),
        unit="point",
        valid_from=date(2026, 1, 1),
        harmonization_confidence=0.71,
        requires_review=True,
        metadata={
            "ai_assisted": True,
            "ai_model": "claude-opus-4-8",
            "ai_fields": ["designation_fr"],
        },
    )


def test_review_item_serialises_to_console_json_shape():
    item = to_review_item(_flagged(), threshold=0.85)
    payload = item.model_dump(mode="json")

    assert payload["tariff_system"] == "EAL"
    assert payload["ai_model"] == "claude-opus-4-8"
    field_keys = set(payload["fields"][0])
    assert field_keys == {"field", "label", "raw", "proposal", "aiFilled", "billing"}

    by_field = {f["field"]: f for f in payload["fields"]}
    # AI-filled field: deterministic extract was empty (raw is null), proposal carries it.
    assert by_field["designation.fr"]["aiFilled"] is True
    assert by_field["designation.fr"]["raw"] is None
    assert by_field["designation.fr"]["proposal"] == "Hématocrite"
    # Billing field: certified, shown unchanged (raw == proposal), never AI-filled. The
    # in-memory Decimal renders verbatim here; the DB round-trip normalises it (see the
    # API test, which seeds the same value and reads "8.5" back through the repository).
    assert by_field["tax_points"]["billing"] is True
    assert by_field["tax_points"]["aiFilled"] is False
    assert by_field["tax_points"]["raw"] == by_field["tax_points"]["proposal"] == "8.50"
