"""Canonical tariff data model (Pydantic v2) — the FROZEN contract.

Per the engineering rules, the field set here is a frozen contract: extend it
additively, never break it. The relational schema (``db/schema.sql``) and the
Quarkus serving entity map onto exactly these fields.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class TariffSystem(str, Enum):
    """Swiss ambulatory tariff systems handled by TarifHub.

    Values are the canonical short identifiers used across the whole platform.
    """

    TARDOC = "TARDOC"
    EAL = "EAL"  # Analysenliste / lab analyses (BAG), tax-point based, DE-only
    SL = "SL"  # Spezialitätenliste / medications (BAG ePL), price based, multilingual
    MIGEL = "MiGeL"  # Mittel- und Gegenständeliste
    SWISSDRG = "SwissDRG"
    TARPSY = "TARPSY"
    ST_REHA = "ST_REHA"


class Designation(BaseModel):
    """Multilingual designation. German is the canonical reference language."""

    model_config = ConfigDict(extra="forbid")

    de: str = Field(..., description="Canonical German designation")
    fr: Optional[str] = Field(default=None, description="French designation")
    it: Optional[str] = Field(default=None, description="Italian designation")


class TariffRecord(BaseModel):
    """A single harmonized tariff position (LOCKED field set).

    The record is *mutable* only while it travels through the pre-freeze pipeline.
    Once :func:`tarifhub_ingest.versioning.freeze_record.freeze` stamps a
    ``record_hash`` it must be treated as immutable, and the repository stores it
    without ever updating it in place.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    tariff_code: str = Field(..., description="Code, primary key within a tariff system")
    tariff_system: TariffSystem
    designation: Designation
    category: Optional[str] = None
    tax_points: Optional[Decimal] = Field(default=None, ge=0)
    price_chf: Optional[Decimal] = Field(default=None, ge=0)
    unit: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    source_url: Optional[str] = None
    source_version: Optional[str] = None
    harmonization_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_review: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    record_hash: Optional[str] = Field(default=None, description="SHA-256 content hash; set at freeze")
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_frozen(self) -> bool:
        return self.record_hash is not None
