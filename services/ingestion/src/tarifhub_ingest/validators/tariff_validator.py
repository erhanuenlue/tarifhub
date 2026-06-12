"""Deterministic pre-freeze validation of canonical records.

Errors block a record from being trusted (it is force-flagged for human review);
warnings are advisory. Pure function of record content — no AI, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tarifhub_ingest.models.tariff_model import TariffRecord


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a single record."""

    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate(record: TariffRecord) -> ValidationResult:
    """Validate a record about to be scored and frozen."""

    errors: list[str] = []
    warnings: list[str] = []

    if not record.tariff_code.strip():
        errors.append("tariff_code is empty")
    if not record.designation.de.strip():
        errors.append("canonical German designation is empty")
    if (
        record.valid_from is not None
        and record.valid_to is not None
        and record.valid_from > record.valid_to
    ):
        errors.append("valid_from is after valid_to")

    # A billing value the mapper could not represent at the canonical schema scale was
    # failed closed to None with the original captured in metadata["raw_*"]. That is a
    # silent-rounding risk a human must resolve, so surface it as an ERROR -> review.
    if "raw_price_chf" in record.metadata:
        errors.append("price_chf exceeded canonical scale (2 dp); fail-closed to review")
    if "raw_tax_points" in record.metadata:
        errors.append("tax_points exceeded canonical scale (4 dp); fail-closed to review")

    if record.tax_points is None and record.price_chf is None:
        warnings.append("neither tax_points nor price_chf is set")
    if record.valid_from is None:
        warnings.append("valid_from is missing")
    if record.designation.fr is None and record.designation.it is None:
        warnings.append("no FR/IT translation present")

    return ValidationResult(ok=not errors, errors=errors, warnings=warnings)
