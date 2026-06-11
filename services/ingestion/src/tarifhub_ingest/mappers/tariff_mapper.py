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
    return TariffRecord(
        tariff_code=_as_text(raw.get("tariff_code") or raw.get("code")) or "",
        tariff_system=system,
        designation=designation,
        category=_as_text(raw.get("category")),
        tax_points=_to_decimal(raw.get("tax_points")),
        price_chf=_to_decimal(raw.get("price_chf")),
        unit=_as_text(raw.get("unit")),
        valid_from=_to_date(raw.get("valid_from")),
        valid_to=_to_date(raw.get("valid_to")),
        source_url=source_url,
        source_version=_as_text(raw.get("source_version")) or source_version,
        metadata={"mapper_version": MAPPER_VERSION, "ai_assisted": False},
    )


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
    return _claude_assisted_map(raw, record, settings)


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
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
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
