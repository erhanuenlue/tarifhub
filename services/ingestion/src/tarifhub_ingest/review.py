"""Human-in-the-loop review write-back: contract models + deterministic logic.

This is the server side of the TarifGuard console review form. It does two things:

* shapes flagged frozen records into the console's ``ReviewItem`` contract for the
  review queue (read-only); and
* applies a human ``approve`` / ``correct`` decision to a flagged record and prepares
  the (re-frozen) successor version.

The intelligence on this path is the HUMAN, never an LLM: this module imports no
Anthropic/OpenAI client and never reaches the network (asserted by
``tests/test_review_boundary.py``). It also never touches a billing value: corrections
to ``tax_points`` / ``price_chf`` are rejected here as defence in depth, on top of the
console's client- and BFF-side guards.

Field-name reconciliation (the canonical place the ``route.ts`` note asks for): the
console addresses fields with dotted keys (``designation.de``) while the canonical
:class:`~tarifhub_ingest.models.tariff_model.TariffRecord` uses flat attributes and the
``ai_map`` provenance in ``metadata["ai_fields"]`` uses underscore tokens
(``designation_fr``). The maps below are the single source of truth for that mapping.

The actual freeze/validate/persist/audit orchestration lives in ``review_service.py``
(called by the ``main.py`` route) so this module stays a pure, importable unit. The
value-path side effects remain boundary-covered: ``tests/test_value_path_boundary.py``
AST-scans every module in the package — the service module included — while the frozen
``tests/test_review_boundary.py`` keeps pinning this module and ``main.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, StringConstraints

from tarifhub_ingest.confidence.scorer import score
from tarifhub_ingest.errors import IngestionError
from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem

# --- field maps (the one canonical reconciliation place) ---------------------

# Billing values are frozen at ingest and are never AI-filled or human-corrected.
BILLING_KEYS: tuple[str, ...] = ("tax_points", "price_chf")

# Bounds on a review decision body (defence in depth on an unauthenticated write seam):
# a correction value is a short non-billing label, and only five fields are correctable,
# so an oversized value or an oversized map is rejected with HTTP 422 before it can reach
# the content hash or the frozen row. Generous vs real designations (well under 200 chars).
MAX_CORRECTION_VALUE_LEN = 2000
MAX_CORRECTIONS = 16

# Non-billing fields a human reviewer may correct, by their console key.
CORRECTABLE_KEYS: tuple[str, ...] = (
    "designation.de",
    "designation.fr",
    "designation.it",
    "category",
    "unit",
)

# Console key -> the ``metadata["ai_fields"]`` provenance token ``ai_map`` writes when
# it fills that field. Only these three are ever AI-fillable (see AIRefinement); de/unit
# and the billing fields are never AI-authored, so they have no token here.
_AI_FIELD_TOKEN: dict[str, str] = {
    "designation.fr": "designation_fr",
    "designation.it": "designation_it",
    "category": "category",
}

# Console key -> human-facing label (mirrors the console's review-fixtures labels).
_FIELD_LABELS: dict[str, str] = {
    "designation.de": "Designation (DE)",
    "designation.fr": "Designation (FR)",
    "designation.it": "Designation (IT)",
    "category": "Category",
    "unit": "Unit",
    "tax_points": "Tax points",
    "price_chf": "Price (CHF)",
}

# The order fields are presented in the queue: non-billing first, then any present
# billing value (certified, shown unchanged).
_QUEUE_FIELD_ORDER: tuple[str, ...] = (
    "designation.de",
    "designation.fr",
    "designation.it",
    "category",
    "unit",
)


# --- wire contract (mirrors apps/tarifguard/lib/api.ts) ----------------------


class ReviewField(BaseModel):
    """One field in the review diff: deterministic raw extract vs the ``ai_map`` proposal.

    ``aiFilled`` is camelCase to match the console contract verbatim; the rest are
    snake_case as the console expects them.
    """

    field: str
    label: str
    raw: Optional[str]
    proposal: Optional[str]
    aiFilled: bool  # noqa: N815 - console wire key (apps/tarifguard/lib/api.ts ReviewField)
    billing: bool


class ReviewItem(BaseModel):
    """One flagged record awaiting human review (``requires_review is True``)."""

    tariff_system: TariffSystem
    tariff_code: str
    record_hash: Optional[str]
    version: int
    designation_de: str
    confidence: float
    requires_review: bool
    ai_model: Optional[str]
    flagged_reason: str
    fields: list[ReviewField]


class ReviewDecision(BaseModel):
    """The human decision the console POSTs (the one write path).

    Lenient on extra keys for forward compatibility; strict on the fields it reads.
    """

    tariff_system: TariffSystem
    tariff_code: str
    record_hash: Optional[str] = None
    action: Literal["approve", "correct"]
    # field -> corrected value, when action == "correct". Billing fields are rejected
    # (by key), and both the value length and the map size are bounded (by type).
    corrections: Optional[
        dict[str, Annotated[str, StringConstraints(max_length=MAX_CORRECTION_VALUE_LEN)]]
    ] = Field(default=None, max_length=MAX_CORRECTIONS)
    reviewer: Optional[str] = None
    note: Optional[str] = None


class ReviewResult(BaseModel):
    """The result of an approve/correct: the (re)frozen successor version, decided here."""

    ok: bool
    tariff_system: str
    tariff_code: str
    action: str
    frozen: bool
    version: int
    record_hash: str
    message: str


class ReviewError(IngestionError):
    """A review decision the server refuses, carrying the HTTP status to surface.

    A domain exception (subclass of :class:`~tarifhub_ingest.errors.IngestionError`) so the
    registered problem+json handler renders it as the SAME envelope as every other failure,
    with no inline ``HTTPException`` translation in ``main.py``. ``status`` is per-instance
    (400 for a billing-field or unknown-field correction); ``title`` / ``type_`` are fixed.
    """

    title = "Review decision rejected"
    type_ = "https://tarifhub.example/problems/review-rejected"

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# --- queue shaping (read-only) -----------------------------------------------


def _decimal_str(value: Decimal | None) -> str | None:
    """Render a billing Decimal exactly as the serving layer does (normalised text)."""

    return None if value is None else format(value, "f")


def _field_value(record: TariffRecord, key: str) -> str | None:
    """Return the record's current (post-``ai_map``) value for a console field key."""

    match key:
        case "designation.de":
            return record.designation.de
        case "designation.fr":
            return record.designation.fr
        case "designation.it":
            return record.designation.it
        case "category":
            return record.category
        case "unit":
            return record.unit
        case "tax_points":
            return _decimal_str(record.tax_points)
        case "price_chf":
            return _decimal_str(record.price_chf)
    return None


def _ai_filled(record: TariffRecord, key: str) -> bool:
    """True iff ``ai_map`` filled this field (the deterministic extract left it empty)."""

    token = _AI_FIELD_TOKEN.get(key)
    if token is None:
        return False
    return token in (record.metadata.get("ai_fields") or [])


def _review_field(record: TariffRecord, key: str) -> ReviewField:
    """Build one :class:`ReviewField`.

    The faithful raw-vs-proposal reconstructable after freeze: ``ai_map`` is fill-only,
    so an AI-filled field had an empty raw extract (``raw=None``); everything else carries
    the deterministic extract unchanged (``raw == proposal``). The raw text of a value the
    AI merely normalised does not survive freeze, and is not invented here.
    """

    proposal = _field_value(record, key)
    ai_filled = _ai_filled(record, key)
    return ReviewField(
        field=key,
        label=_FIELD_LABELS[key],
        raw=None if ai_filled else proposal,
        proposal=proposal,
        aiFilled=ai_filled,
        billing=key in BILLING_KEYS,
    )


def _flagged_reason(record: TariffRecord, threshold: float) -> str:
    """Deterministically restate why the record is in the queue (confidence/validation).

    Imported lazily to keep the determinism-boundary import graph of this module minimal.
    """

    from tarifhub_ingest.validators.tariff_validator import validate  # noqa: PLC0415

    reasons: list[str] = []
    if record.harmonization_confidence < threshold:
        reasons.append(f"harmonization_confidence {record.harmonization_confidence} < {threshold}")
    result = validate(record)
    if not result.ok:
        reasons.append("validation: " + "; ".join(result.errors))
    return "; ".join(reasons) or "flagged for human review"


def to_review_item(record: TariffRecord, *, threshold: float) -> ReviewItem:
    """Shape one flagged frozen record into the console ``ReviewItem`` contract."""

    keys = list(_QUEUE_FIELD_ORDER)
    keys += [bk for bk in BILLING_KEYS if _field_value(record, bk) is not None]
    return ReviewItem(
        tariff_system=record.tariff_system,
        tariff_code=record.tariff_code,
        record_hash=record.record_hash,
        version=record.version,
        designation_de=record.designation.de,
        confidence=record.harmonization_confidence,
        requires_review=record.requires_review,
        ai_model=record.metadata.get("ai_model"),
        flagged_reason=_flagged_reason(record, threshold),
        fields=[_review_field(record, key) for key in keys],
    )


# --- decision application (prepares the successor; main.py validates/freezes) ---


def _clean(value: str | None) -> str | None:
    """Strip an optional correction; an empty/whitespace value clears the field."""

    if value is None:
        return None
    text = value.strip()
    return text or None


def _reject_invalid_keys(corrections: dict[str, str]) -> None:
    """Reject billing-field and unknown-field corrections with HTTP 400."""

    for key in corrections:
        if key in BILLING_KEYS:
            raise ReviewError(400, f"billing values cannot be corrected: {key}")
        if key not in CORRECTABLE_KEYS:
            raise ReviewError(400, f"unknown or non-correctable field: {key}")


def _apply_corrections(record: TariffRecord, corrections: dict[str, str]) -> TariffRecord:
    """Return a copy of ``record`` with the human's non-billing corrections applied.

    Designation leaves are rebuilt into one :class:`Designation`; a corrected field that
    was AI-filled is dropped from ``metadata["ai_fields"]`` (it is now human-authored).
    ``designation.de`` is required, so an emptied value is left as ``""`` for ``validate``
    to reject downstream rather than silently dropped.
    """

    _reject_invalid_keys(corrections)

    de, fr, it = record.designation.de, record.designation.fr, record.designation.it
    updates: dict[str, object] = {}
    touched_designation = False
    corrected_tokens: set[str] = set()

    for key, value in corrections.items():
        if key == "designation.de":
            de = (value or "").strip()
            touched_designation = True
        elif key == "designation.fr":
            fr = _clean(value)
            touched_designation = True
        elif key == "designation.it":
            it = _clean(value)
            touched_designation = True
        elif key == "category":
            updates["category"] = _clean(value)
        elif key == "unit":
            updates["unit"] = _clean(value)
        token = _AI_FIELD_TOKEN.get(key)
        if token is not None:
            corrected_tokens.add(token)

    if touched_designation:
        updates["designation"] = Designation(de=de, fr=fr, it=it)

    # Human corrections supersede AI provenance for the fields they touch.
    remaining = [f for f in (record.metadata.get("ai_fields") or []) if f not in corrected_tokens]
    metadata = {**record.metadata}
    if "ai_fields" in metadata:
        if remaining:
            metadata["ai_fields"] = remaining
        else:
            metadata.pop("ai_fields")
    updates["metadata"] = metadata

    return record.model_copy(update=updates)


def prepare_reviewed_record(record: TariffRecord, decision: ReviewDecision) -> TariffRecord:
    """Prepare the unfrozen successor for a human decision (caller validates + freezes).

    ``approve`` accepts the ``ai_map`` proposal verbatim; ``correct`` applies the
    non-billing corrections. The harmonisation confidence is re-scored with the SAME
    deterministic scorer the pipeline uses (so it stays a faithful function of content),
    while ``requires_review`` is cleared by explicit human authority (the whole point of
    the gate, independent of the confidence threshold). ``record_hash`` is reset so the
    caller's ``freeze`` can stamp a fresh hash; the repository assigns the next version.
    """

    working = record
    if decision.action == "correct":
        working = _apply_corrections(record, decision.corrections or {})

    return working.model_copy(
        update={
            "harmonization_confidence": score(working),
            "requires_review": False,
            "record_hash": None,
            "created_at": datetime.now(timezone.utc),
        }
    )


def review_message(action: str, version: int, corrected_fields: list[str]) -> str:
    """Human-readable outcome line for the :class:`ReviewResult`."""

    if action == "approve":
        return f"Approved the proposal verbatim and froze v{version}."
    if corrected_fields:
        return f"Corrected {', '.join(corrected_fields)} and re-froze v{version}."
    return f"Accepted the proposal and froze v{version}."
