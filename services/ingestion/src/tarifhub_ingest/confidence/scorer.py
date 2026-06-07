"""Deterministic confidence scoring for harmonized records (pre-freeze).

A pure function of record content — NO AI, NO randomness — so a given record
always receives the same score. AI may *propose* a mapping upstream, but the
confidence that gates human review is always computed here, deterministically.
Records below ``Settings.review_threshold`` are flagged ``requires_review``.
"""

from __future__ import annotations

from tarifhub_ingest.models.tariff_model import TariffRecord

# Penalties subtracted from a perfect score of 1.0. Tuned so a complete record
# scores 1.0, a DE-only-but-otherwise-complete record stays comfortably high,
# and a record missing any billing-relevant value drops below typical thresholds.
_PENALTY_NO_TRANSLATIONS = 0.10
_PENALTY_NO_VALUE = 0.25  # neither tax_points nor price_chf present
_PENALTY_NO_CATEGORY = 0.10
_PENALTY_NO_UNIT = 0.05
_PENALTY_NO_VALID_FROM = 0.10
_PENALTY_EMPTY_DESIGNATION = 0.40


def score(record: TariffRecord) -> float:
    """Return a deterministic confidence in ``[0.0, 1.0]`` rounded to 4 dp."""

    confidence = 1.0

    if not record.designation.de.strip():
        confidence -= _PENALTY_EMPTY_DESIGNATION
    if record.designation.fr is None and record.designation.it is None:
        confidence -= _PENALTY_NO_TRANSLATIONS
    if record.tax_points is None and record.price_chf is None:
        confidence -= _PENALTY_NO_VALUE
    if record.category is None:
        confidence -= _PENALTY_NO_CATEGORY
    if record.unit is None:
        confidence -= _PENALTY_NO_UNIT
    if record.valid_from is None:
        confidence -= _PENALTY_NO_VALID_FROM

    confidence = max(0.0, min(1.0, confidence))
    return round(confidence, 4)
