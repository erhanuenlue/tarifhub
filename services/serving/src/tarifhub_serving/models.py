"""API response models for the serving service.

The wire shape is the canonical :class:`TariffRecord` itself (one canonical model
end-to-end). These thin aliases/wrappers exist only to give the search endpoint its
ranked shape and to keep OpenAPI documentation explicit.
"""

from __future__ import annotations

from pydantic import BaseModel

from tarifhub_ingest.models.tariff_model import TariffRecord


class HealthResponse(BaseModel):
    """Liveness probe payload."""

    status: str


class SearchHit(BaseModel):
    """A ranked semantic-search hit wrapping a frozen record (values verbatim)."""

    rank: int
    record: TariffRecord
