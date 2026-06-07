"""TarifIQ data model (Pydantic v2) — the contracts for rules, cross-walk, and checks.

Deliberately, **no model here carries a billing value** (no tax points, no CHF). Rules
and cross-walk entries describe *relationships* between frozen tariff positions; the
authoritative values live behind the L1 serving API as frozen records. This keeps the
freeze line intact: TarifIQ reasons about codes, never about prices.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TariffSystem(str, Enum):
    """Tariff systems TarifIQ reasons over (subset of the platform-wide set)."""

    TARMED = "TARMED"
    TARDOC = "TARDOC"


class CombinabilityRelation(str, Enum):
    """The kind of relationship a combinability rule encodes."""

    EXCLUSIVE = "EXCLUSIVE"  # the two codes may not be billed together in one session
    REQUIRES = "REQUIRES"  # code may only be billed if related_code is also present
    CUMULATION_LIMIT = "CUMULATION_LIMIT"  # code may be billed at most max_quantity times


class CombinabilityVerdict(str, Enum):
    """Overall outcome of a combinability check."""

    COMBINABLE = "COMBINABLE"
    NOT_COMBINABLE = "NOT_COMBINABLE"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"  # e.g. a code unknown to the frozen tariff store


class CrosswalkMappingType(str, Enum):
    """Shape of a TARMED→TARDOC cross-walk entry."""

    ONE_TO_ONE = "ONE_TO_ONE"
    ONE_TO_MANY = "ONE_TO_MANY"
    NO_EQUIVALENT = "NO_EQUIVALENT"


class CombinabilityRule(BaseModel):
    """A single frozen combinability/cumulation rule.

    Also used as the *candidate* payload for ``POST /v1/validate``: a rule must pass
    deterministic validation before a human freezes it into the rule set.
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., description="Stable identifier, e.g. 'R-EXCL-001'")
    system: TariffSystem
    relation: CombinabilityRelation
    code: str = Field(..., description="Primary tariff code the rule is about")
    related_code: Optional[str] = Field(
        default=None, description="The other code for EXCLUSIVE / REQUIRES relations"
    )
    max_quantity: Optional[int] = Field(
        default=None, ge=1, description="Cap for CUMULATION_LIMIT relations"
    )
    note: str = Field(default="", description="Human-readable rationale")
    source: str = Field(default="", description="Provenance, e.g. 'TARDOC 1.3 Anwendungsregeln'")


class Position(BaseModel):
    """One coded position on an encounter."""

    model_config = ConfigDict(extra="forbid")

    code: str
    quantity: int = Field(default=1, ge=1)


class CombinabilityCheckRequest(BaseModel):
    """Request body for ``POST /v1/combinability-check``."""

    model_config = ConfigDict(extra="forbid")

    system: TariffSystem = TariffSystem.TARDOC
    positions: list[Position] = Field(default_factory=list)


class Conflict(BaseModel):
    """A single rule violation found during a combinability check."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    relation: CombinabilityRelation
    codes: list[str]
    message: str


class CombinabilityCheckResult(BaseModel):
    """Deterministic outcome of a combinability check."""

    model_config = ConfigDict(extra="forbid")

    verdict: CombinabilityVerdict
    conflicts: list[Conflict] = Field(default_factory=list)
    unknown_codes: list[str] = Field(default_factory=list)
    rule_set_version: str
    rule_set_hash: str
    # Always true: this result is computed by deterministic table evaluation, no model.
    deterministic: bool = True


class CrosswalkEntry(BaseModel):
    """A frozen TARMED→TARDOC cross-walk entry."""

    model_config = ConfigDict(extra="forbid")

    tarmed_code: str
    tardoc_codes: list[str] = Field(default_factory=list)
    mapping_type: CrosswalkMappingType
    note: str = ""
    source: str = ""


class CrosswalkResult(BaseModel):
    """Response body for ``GET /v1/crosswalk/{tarmed_code}``."""

    model_config = ConfigDict(extra="forbid")

    tarmed_code: str
    found: bool
    entry: Optional[CrosswalkEntry] = None
    crosswalk_version: str
    crosswalk_hash: str
    deterministic: bool = True


class CrosswalkSuggestion(BaseModel):
    """A PRE-FREEZE, AI-suggested candidate cross-walk entry.

    Produced by the replaceable ``ai_rule_suggest`` seam for a human to review. It is
    never authoritative and never auto-frozen: ``needs_human_review`` is always true.
    """

    model_config = ConfigDict(extra="forbid")

    tarmed_code: str
    suggested_tardoc_codes: list[str] = Field(default_factory=list)
    mapping_type: CrosswalkMappingType
    rationale: str
    needs_human_review: bool = True
    suggested_by: str = "ai_rule_suggest:placeholder"
    # True while this is the offline, deterministic placeholder (no live model call).
    deterministic_placeholder: bool = True


class RuleValidationResult(BaseModel):
    """Outcome of validating a candidate rule before freeze (``POST /v1/validate``)."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_codes: list[str] = Field(default_factory=list)
