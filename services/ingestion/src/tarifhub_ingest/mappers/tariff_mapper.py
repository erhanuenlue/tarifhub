"""Map a raw parsed row onto the canonical :class:`TariffRecord`.

``map_raw`` is rules-based and deterministic. ``ai_map`` is the *single*, clearly
marked seam where a live Claude harmonizer may be plugged in for hard cases; it is
import-guarded and falls back to ``map_raw`` whenever no API key is configured, so
it never reaches the network during tests. Critically, AI may enrich designations
or fill gaps pre-freeze, but the deterministic rules own every billing-relevant
value (``tax_points`` / ``price_chf``) — AI never computes or mutates those.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from tarifhub_ingest.config import Settings, get_settings
from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem

MAPPER_VERSION = "tariff-mapper/0.1.0"


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
    record = map_raw(
        raw, system=system, source_url=source_url, source_version=source_version
    )
    if not settings.anthropic_api_key:
        return record
    return _claude_assisted_map(raw, record, settings)


def _claude_assisted_map(
    raw: dict[str, Any], record: TariffRecord, settings: Settings
) -> TariffRecord:  # pragma: no cover - never exercised offline / in tests
    """Replaceable placeholder for live Claude harmonization (pre-freeze).

    This is the ONLY place a live LLM may be called, and only for non-billing
    fields. The actual ``client.messages.create(...)`` call is left as a marked
    TODO so this skeleton never hits the network. Until implemented, it returns the
    deterministic mapping annotated as AI-attempted.
    """

    try:
        import anthropic  # noqa: F401, PLC0415  (guarded: optional 'ai' extra)
    except ImportError:
        return record

    # TODO: build a structured-output prompt (temperature=0), call Claude to refine
    # designations / category, validate the JSON against the canonical schema, and
    # NEVER let the model touch tax_points / price_chf. For now, return rules output.
    return record.model_copy(
        update={"metadata": {**record.metadata, "ai_assisted": True, "ai_status": "placeholder"}}
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
