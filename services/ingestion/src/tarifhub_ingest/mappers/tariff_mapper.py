"""Map a raw parsed row onto the canonical :class:`TariffRecord`.

``map_raw`` is rules-based and deterministic. ``ai_map`` is the *single*, clearly
marked seam where a live Claude harmonizer may be plugged in for hard cases; it is
import-guarded and falls back to ``map_raw`` whenever no API key is configured, so
it never reaches the network during tests. Critically, AI may enrich designations
or fill gaps pre-freeze, but the deterministic rules own every billing-relevant
value (``tax_points`` / ``price_chf``) — AI never computes or mutates those.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from tarifhub_ingest.config import Settings, get_settings
from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem

MAPPER_VERSION = "tariff-mapper/0.1.0"

# Canonical Decimal scales — defined ONCE here, mirroring db/schema.sql so the stored
# bytes provably equal the hashed bytes on every engine (hash integrity, ADR-016).
# Postgres declares tax_points NUMERIC(12,4) and price_chf NUMERIC(12,2); a value the
# database would silently round on insert is a freeze-contract breach. We quantize to
# these scales PRE-freeze. Quantizing a non-lossy value (76.5 -> 76.5000) is scale-
# invariant under the freeze canonicalisation (``format(value.normalize(), "f")``), so
# it never moves a record_hash. A value quantization WOULD change (more dp, or more than
# _PRECISION_CAP total digits) is lossy: the billing field fails closed to None, the
# original is preserved as a metadata raw_* string, and the validator routes it to review.
TAX_POINTS_SCALE = Decimal("0.0001")  # NUMERIC(12,4)
PRICE_CHF_SCALE = Decimal("0.01")  # NUMERIC(12,2)
_PRECISION_CAP = 12  # total significant digits (NUMERIC(12, _))

_LOG = logging.getLogger(__name__)

# The harmonizer refines ONLY non-billing fields. "Temperature 0" intent is satisfied
# architecturally — not via a sampling knob (this model has none): structured output
# bound to AIRefinement plus a fill-only merge means the model can never reach a
# billing value. Designations/category are the only fields it can influence.
_SYSTEM_PROMPT = (
    "You are a Swiss ambulatory tariff harmonisation assistant. You refine ONLY the "
    "non-billing designation and category fields of a tariff position. You must NEVER "
    "invent or alter codes, numbers, tax points, prices, units, or dates. When you are "
    "not confident of the exact clinical term, return null for that field."
)


class AIRefinement(BaseModel):
    """Structured-output contract for the pre-freeze harmonizer (non-billing only)."""

    model_config = ConfigDict(extra="forbid")

    designation_fr: Optional[str] = Field(
        default=None,
        description=(
            "French translation of the German designation of this Swiss "
            "lab-analysis / tariff position — ONLY if you are confident of the exact "
            "clinical term, otherwise null."
        ),
    )
    designation_it: Optional[str] = Field(
        default=None,
        description=(
            "Italian translation of the German designation of this Swiss "
            "lab-analysis / tariff position — ONLY if you are confident of the exact "
            "clinical term, otherwise null."
        ),
    )
    category: Optional[str] = Field(
        default=None,
        description=(
            "A concise German category label — ONLY if no category was already "
            "provided, otherwise null."
        ),
    )


def map_raw(
    raw: dict[str, Any],
    *,
    system: TariffSystem,
    source_url: str | None = None,
    source_version: str | None = None,
) -> TariffRecord:
    """Deterministically map a raw row to a (not-yet-frozen) canonical record."""

    designation = Designation(
        de=_as_text(raw.get("designation_de") or raw.get("designation")) or "",
        fr=_as_text(raw.get("designation_fr")),
        it=_as_text(raw.get("designation_it")),
    )
    # Quantize the billing fields to the canonical schema scales BEFORE freeze so the
    # stored value can never differ from the hashed one. A value that cannot be
    # represented at the column scale without loss fails closed to None and its raw form
    # is captured in raw_overflow for metadata + the validator (the EAL 'nach Aufwand'
    # -> None precedent, extended to scale overflow).
    raw_overflow: dict[str, str] = {}
    tax_points = _coerce_scaled(raw.get("tax_points"), TAX_POINTS_SCALE, "tax_points", raw_overflow)
    price_chf = _coerce_scaled(raw.get("price_chf"), PRICE_CHF_SCALE, "price_chf", raw_overflow)
    return TariffRecord(
        tariff_code=_as_text(raw.get("tariff_code") or raw.get("code")) or "",
        tariff_system=system,
        designation=designation,
        category=_as_text(raw.get("category")),
        tax_points=tax_points,
        price_chf=price_chf,
        unit=_as_text(raw.get("unit")),
        valid_from=_to_date(raw.get("valid_from")),
        valid_to=_to_date(raw.get("valid_to")),
        source_url=source_url,
        source_version=_as_text(raw.get("source_version")) or source_version,
        metadata=_metadata(raw, raw_overflow),
    )


def _metadata(raw: dict[str, Any], raw_overflow: dict[str, str] | None = None) -> dict[str, Any]:
    """Build record.metadata: the mapper's provenance keys plus optional source extras.

    HASH-CRITICAL: a row WITHOUT ``raw['metadata']`` (every EAL row, the pre-SL world)
    AND without a scale overflow must produce exactly
    ``{"mapper_version": ..., "ai_assisted": False}`` — byte-identical to before — so
    existing pinned record hashes never move. Source extras (the SL adapter's JSON-native
    dict) are folded in first; the provenance keys are written last so they always win on
    any collision. Scale-overflow markers (``raw_price_chf`` / ``raw_tax_points``) are
    added only when a value was lossy at the canonical scale.
    """

    metadata: dict[str, Any] = {}
    extras = raw.get("metadata")
    if isinstance(extras, dict):
        metadata.update(extras)
    metadata["mapper_version"] = MAPPER_VERSION
    metadata["ai_assisted"] = False
    if raw_overflow:
        for field, raw_value in raw_overflow.items():
            metadata[f"raw_{field}"] = raw_value
    return metadata


def ai_map(
    raw: dict[str, Any],
    *,
    system: TariffSystem,
    source_url: str | None = None,
    source_version: str | None = None,
    settings: Settings | None = None,
) -> TariffRecord:
    """AI-assisted mapping seam (pre-freeze only).

    Default / offline / CI: returns the deterministic :func:`map_raw` result. When
    an ``ANTHROPIC_API_KEY`` is configured, a live Claude harmonizer *may* refine
    non-billing fields (designations, category) — see :func:`_claude_assisted_map`.
    """

    settings = settings or get_settings()
    record = map_raw(raw, system=system, source_url=source_url, source_version=source_version)
    if not settings.anthropic_api_key:
        return record
    # Gap-gate (deterministic pre-check): the live harmonizer can only ever FILL
    # missing non-billing fields. If there is nothing fillable, calling it would cost
    # latency/tokens for a guaranteed no-op AND — because the fallback metadata must
    # stay byte-identical to the no-key path — would risk record_hash drift. So when
    # there is no gap we return the deterministic record UNCHANGED (ai_assisted=False),
    # identical to the no-key path. The model is invoked only when a gap exists.
    if not _has_fillable_gap(record):
        return record
    return _claude_assisted_map(raw, record, settings)


def _has_fillable_gap(record: TariffRecord) -> bool:
    """True iff a non-billing field the AI seam may fill is still missing."""

    return record.designation.fr is None or record.designation.it is None or record.category is None


def _claude_assisted_map(
    raw: dict[str, Any], record: TariffRecord, settings: Settings
) -> TariffRecord:
    """Live Claude harmonization (pre-freeze, non-billing fields only).

    The ONLY place a live LLM may be called. It refines ONLY ``designation.fr`` /
    ``designation.it`` / ``category`` and only where the deterministic record left a
    gap (fill-only) — structurally, the merge below can never reach a billing value.
    Any failure (no extra installed, API error, refusal, empty output) returns the
    deterministic ``record`` so the pipeline never crashes on the AI seam.
    """

    try:
        import anthropic  # noqa: PLC0415  (guarded: optional 'ai' extra)
    except ImportError:
        return record

    payload = json.dumps(
        {
            "tariff_system": record.tariff_system.value,
            "tariff_code": record.tariff_code,
            "designation_de": record.designation.de,
            "designation_fr": record.designation.fr,
            "designation_it": record.designation.it,
            "category": record.category,
            "unit": record.unit,
        },
        sort_keys=True,
        ensure_ascii=False,
    )

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
        # No temperature/top_p/top_k/thinking: removed on this model (HTTP 400 if sent).
        resp = client.messages.parse(
            model=settings.ai_model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": payload}],
            output_format=AIRefinement,
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("model refused the harmonization request")
        refinement = resp.parsed_output
        if refinement is None:
            raise RuntimeError("model returned no parsed output")
    except Exception as exc:  # noqa: BLE001 — the AI seam must never break the pipeline
        # Return the deterministic record UNCHANGED: the error fallback must be
        # byte-identical (same record_hash) to the no-key path, or transient AI
        # outages would break re-ingest idempotency. Failure evidence goes to the log.
        _LOG.warning(
            "AI harmonization failed (%s); using deterministic mapping", type(exc).__name__
        )
        return record

    fr = record.designation.fr or _as_text(refinement.designation_fr)
    it = record.designation.it or _as_text(refinement.designation_it)
    category = record.category or _as_text(refinement.category)

    filled: list[str] = []
    if record.designation.fr is None and fr is not None:
        filled.append("designation_fr")
    if record.designation.it is None and it is not None:
        filled.append("designation_it")
    if record.category is None and category is not None:
        filled.append("category")

    return record.model_copy(
        update={
            "designation": Designation(de=record.designation.de, fr=fr, it=it),
            "category": category,
            "metadata": {
                **record.metadata,
                "ai_assisted": True,
                "ai_model": settings.ai_model,
                "ai_status": "ok",
                "ai_fields": sorted(filled),
            },
        }
    )


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # guard: bool is an int subclass
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace("'", "").replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _coerce_scaled(
    value: Any, scale: Decimal, field: str, raw_overflow: dict[str, str]
) -> Decimal | None:
    """Parse a billing value and quantize it to ``scale``, failing closed when lossy.

    Returns the quantized Decimal when the value fits the canonical scale (and the
    _PRECISION_CAP) without loss — non-lossy quantization is scale-invariant under the
    freeze hash, so widening 76.5 -> 76.5000 never moves a record_hash. When quantizing
    WOULD change the value (more decimal places than the scale holds, or more than
    _PRECISION_CAP total significant digits), it is lossy: the function returns ``None``,
    records the original as a canonical string in ``raw_overflow[field]``, and the
    validator turns that marker into an ERROR (fail-closed into review). ``None`` input
    (absent / non-numeric / EAL 'nach Aufwand') passes through unchanged.
    """

    parsed = _to_decimal(value)
    if parsed is None:
        return None
    quantized = parsed.quantize(scale)
    # Lossy iff rounding moved the value, OR the quantized value exceeds the total digit
    # cap the NUMERIC(12, _) column can hold.
    digits = quantized.as_tuple().digits
    too_many_digits = len(digits) > _PRECISION_CAP
    if quantized != parsed or too_many_digits:
        raw_overflow[field] = format(parsed.normalize(), "f")
        return None
    return quantized


def _to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None
