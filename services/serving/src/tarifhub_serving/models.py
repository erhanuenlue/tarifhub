"""API response models for the serving service.

The wire shape is the canonical :class:`TariffRecord` itself (one canonical model
end-to-end). These thin aliases/wrappers exist only to give the search endpoint its
ranked shape and to keep OpenAPI documentation explicit.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from tarifhub_ingest.models.tariff_model import TariffRecord


class HealthResponse(BaseModel):
    """Liveness probe payload."""

    status: str


class SearchHit(BaseModel):
    """A ranked semantic-search hit wrapping a frozen record (values verbatim)."""

    rank: int
    record: TariffRecord


class FieldChange(BaseModel):
    """One field that differs between two versions of a frozen record.

    ``from_value`` / ``to_value`` are the values exactly as the API serialises them
    elsewhere (verbatim frozen values; nested designation leaves use dotted field names
    such as ``designation.de``). ``None`` is preserved as null.
    """

    field: str
    from_value: Any = None
    to_value: Any = None


class DiffResponse(BaseModel):
    """Field-level diff between two versions of a frozen ``(system, code)`` record."""

    tariff_system: str
    tariff_code: str
    from_version: int
    to_version: int
    from_record_hash: str | None = None
    to_record_hash: str | None = None
    changes: list[FieldChange]


class ExplainResponse(BaseModel):
    """All versions of a code plus a deterministic, record-grounded explanation.

    ``explanation`` is assembled by a rule from record fields only — no LLM, no
    randomness, no wall-clock — and is labelled ``[deterministic]`` to mark its
    provenance. This is the payload ``services/mcp`` ``explain_record`` proxies.
    """

    code: str
    records: list[TariffRecord]
    explanation: str
