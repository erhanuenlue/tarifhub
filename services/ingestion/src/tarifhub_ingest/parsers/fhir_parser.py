"""FHIR parser for the BAG ePL Spezialitätenliste-style bundle (medications + prices).

Reads a FHIR R5-flavoured ``Bundle`` of ``MedicinalProductDefinition`` entries with
JSON only (stdlib ``json``) so the suite stays offline; in production the
``fhir.resources`` models can validate the same payload. The bundle shape used here
is intentionally simplified for the offline sample but mirrors the real fields:
identifier (SL/GTIN code), multilingual ``name``, ``classification`` (category),
a CHF ``price``, ``unit`` and a ``validityPeriod``.

Emits flat ``dict`` rows using the shared key vocabulary. No AI, no network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PARSER_VERSION = "fhir-parser/0.1.0"

# Map FHIR BCP-47 language tags to canonical-model designation keys.
_LANG_TO_KEY = {"de": "designation_de", "fr": "designation_fr", "it": "designation_it"}


def parse(path: str | Path) -> list[dict[str, Any]]:
    """Parse a FHIR bundle JSON file into a list of row dicts."""

    bundle = json.loads(Path(path).read_text(encoding="utf-8"))
    source_version = (bundle.get("meta") or {}).get("versionId")
    rows: list[dict[str, Any]] = []
    for entry in bundle.get("entry", []):
        resource = entry.get("resource") or {}
        row = _resource_to_row(resource)
        if not row:
            continue
        if source_version and "source_version" not in row:
            row["source_version"] = source_version
        rows.append(row)
    return rows


def _resource_to_row(resource: dict[str, Any]) -> dict[str, Any]:
    code = _first_identifier(resource.get("identifier"))
    if not code:
        return {}

    row: dict[str, Any] = {"tariff_code": code}

    for name in resource.get("name", []) or []:
        language = str(name.get("language", "")).split("-")[0].lower()
        key = _LANG_TO_KEY.get(language)
        product_name = name.get("productName") or name.get("text")
        if key and product_name:
            row[key] = product_name

    classification = resource.get("classification") or []
    if classification:
        row["category"] = classification[0].get("text") or classification[0].get("code")

    price = resource.get("price") or {}
    if "value" in price:
        row["price_chf"] = price.get("value")

    if resource.get("unit"):
        row["unit"] = resource["unit"]

    validity = resource.get("validityPeriod") or {}
    if validity.get("start"):
        row["valid_from"] = validity["start"]
    if validity.get("end"):
        row["valid_to"] = validity["end"]

    return row


def _first_identifier(identifiers: Any) -> str | None:
    if not identifiers:
        return None
    for identifier in identifiers:
        value = identifier.get("value")
        if value:
            return str(value)
    return None
