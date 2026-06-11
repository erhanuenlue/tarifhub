"""Build the committed BAG ePL (SL) test fixture FROM the real (gitignored) export.

Deterministic given the raw NDJSON: SELECTS verbatim lines (never mutates bundle
content) so the fixture is a faithful, smaller slice of the real FHIR R5 export.
The selection is the union, in original file order, of:

  * the first ``_FIRST_N`` bundles (the bulk happy path),
  * every bundle whose product carries NO ATC code (the real ai_map category gap),
  * at least one multi-package bundle (>1 PackagedProductDefinition),
  * at least one bundle with SL Limitationen (ClinicalUseDefinition entries),
  * at least one bundle with ``priceModel = true`` and at least one with an
    ``expiryDate`` (the two rare SL extension edges).

The "at least one" edges keep the committed fixture small (~3-4 MB) while still
exercising every parser branch on real data.

Run from the service root (the raw file lives at the REPO root, gitignored):

    uv run python tests/fixtures/epl/make_fixture.py

Re-running with the same raw file produces a byte-identical fixture. Only the small
fixture (``foph-sl-export-20260601_fixture.ndjson``), its README and this script are
committed; ``data/raw/`` never is.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

# .../services/ingestion/tests/fixtures/epl/make_fixture.py
_SERVICE_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = _SERVICE_ROOT.parents[1]
_RAW = _REPO_ROOT / "data" / "raw" / "epl" / "foph-sl-export-20260601.ndjson"
_FIXTURE = Path(__file__).resolve().with_name("foph-sl-export-20260601_fixture.ndjson")

_FIRST_N = 200

_ATC_SYSTEM = "http://www.whocc.no/atc"
_REIMB_TYPE_CODE = "756000002003"
_SL_EXT_SUFFIX = "reimbursementSL"


def _has_atc(bundle: dict) -> bool:
    for entry in bundle.get("entry", []):
        resource = entry.get("resource") or {}
        if resource.get("resourceType") != "MedicinalProductDefinition":
            continue
        for classification in resource.get("classification") or []:
            for coding in classification.get("coding") or []:
                if coding.get("system") == _ATC_SYSTEM and coding.get("code"):
                    return True
    return False


def _count_packages(bundle: dict) -> int:
    return sum(
        1
        for entry in bundle.get("entry", [])
        if (entry.get("resource") or {}).get("resourceType") == "PackagedProductDefinition"
    )


def _has_clinical_use(bundle: dict) -> bool:
    return any(
        (entry.get("resource") or {}).get("resourceType") == "ClinicalUseDefinition"
        for entry in bundle.get("entry", [])
    )


def _sl_extension_flags(bundle: dict) -> tuple[bool, bool]:
    """(has priceModel=true, has expiryDate) across the bundle's FOPH RAs."""

    price_model = False
    expiry = False
    for entry in bundle.get("entry", []):
        resource = entry.get("resource") or {}
        if resource.get("resourceType") != "RegulatedAuthorization":
            continue
        if not any(
            coding.get("code") == _REIMB_TYPE_CODE
            for coding in (resource.get("type") or {}).get("coding", [])
        ):
            continue
        for ext in resource.get("extension", []):
            if not str(ext.get("url", "")).endswith(_SL_EXT_SUFFIX):
                continue
            for sub in ext.get("extension", []):
                if sub.get("url") == "priceModel" and sub.get("valueBoolean") is True:
                    price_model = True
                if sub.get("url") == "expiryDate":
                    expiry = True
    return price_model, expiry


def build() -> Path:
    if not _RAW.exists():
        raise FileNotFoundError(
            f"raw ePL export not found at {_RAW}; download it before building the fixture"
        )

    keep: set[int] = set()
    multipack_added = False
    cud_added = False
    price_model_added = False
    expiry_added = False

    raw_lines: list[str] = []
    with open(_RAW, encoding="utf-8") as handle:
        for idx, line in enumerate(handle):
            raw_lines.append(line)
            stripped = line.strip()
            if not stripped:
                continue
            bundle = json.loads(stripped, parse_float=Decimal)

            if idx < _FIRST_N:
                keep.add(idx)
            if not _has_atc(bundle):
                keep.add(idx)  # the real ATC/category gap — keep ALL of these
            if not multipack_added and _count_packages(bundle) > 1:
                keep.add(idx)
                multipack_added = True
            if not cud_added and _has_clinical_use(bundle):
                keep.add(idx)
                cud_added = True
            price_model, expiry = _sl_extension_flags(bundle)
            if price_model and not price_model_added:
                keep.add(idx)
                price_model_added = True
            if expiry and not expiry_added:
                keep.add(idx)
                expiry_added = True

    selected = [raw_lines[i] for i in sorted(keep)]
    _FIXTURE.write_text("".join(selected), encoding="utf-8")
    return _FIXTURE


if __name__ == "__main__":
    path = build()
    print(f"wrote fixture: {path} ({path.stat().st_size} bytes)")
