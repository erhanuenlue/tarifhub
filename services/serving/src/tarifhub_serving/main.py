"""FastAPI app: deterministic read API over frozen tariff records (L1 TarifCore).

Every value returned is an unaltered, frozen, versioned record read straight from the
system of record. No AI is on this value path. The only AI-adjacent seam is the
semantic-search endpoint, which uses an embedder to RANK frozen rows by similarity —
it never computes, alters, or fabricates a billing value. On SQLite (offline) semantic
search is honestly unavailable (HTTP 501); it requires Postgres+pgvector.

Import discipline: from ``tarifhub_ingest`` we import ONLY ``models.tariff_model`` and
``embeddings.embedder`` — never mappers, never anything that could pull an LLM client.
This is enforced by ``tests/test_determinism_boundary.py``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from tarifhub_ingest.embeddings.embedder import E5_DIMENSION, get_embedder
from tarifhub_ingest.models.tariff_model import TariffRecord

from tarifhub_serving.config import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    Settings,
    get_settings,
)
from tarifhub_serving.db import Database
from tarifhub_serving.models import HealthResponse, SearchHit
from tarifhub_serving.repository import ServingRepository

app = FastAPI(
    title="TarifHub Serving (L1 TarifCore)",
    description="Deterministic read API over frozen Swiss ambulatory tariff records.",
    version="0.1.0",
)


def _database() -> Database:
    return Database.from_url(get_settings().db_url)


def get_repository(db: Annotated[Database, Depends(_database)]):
    """Yield a read-only repository bound to a fresh connection per request."""

    conn = db.connect()
    try:
        yield ServingRepository(conn, db)
    finally:
        conn.close()


RepoDep = Annotated[ServingRepository, Depends(get_repository)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@app.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health() -> HealthResponse:
    """Return ``{"status": "ok"}`` when the service is up."""

    return HealthResponse(status="ok")


@app.get(
    "/api/v1/tariffs",
    response_model=list[TariffRecord],
    summary="List the latest version of each frozen tariff record",
)
def list_tariffs(
    repo: RepoDep,
    system: Annotated[str | None, Query(description="Filter by tariff system, e.g. TARDOC")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIST_LIMIT)] = DEFAULT_LIST_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TariffRecord]:
    """Latest-version frozen records, optionally filtered by ``system``, paginated."""

    return repo.list_latest(system=system, limit=limit, offset=offset)


@app.get(
    "/api/v1/tariffs/{system}/{code}",
    response_model=TariffRecord,
    summary="Get the latest frozen record for a (system, code) key",
)
def get_tariff(system: str, code: str, repo: RepoDep) -> TariffRecord:
    """Return the highest-version frozen record, or 404 if none exists."""

    record = repo.get_latest(system, code)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"no frozen record for system={system} code={code}",
        )
    return record


@app.get(
    "/api/v1/search",
    response_model=list[SearchHit],
    summary="Semantic search over frozen records (Postgres+pgvector only)",
)
def search(
    repo: RepoDep,
    settings: SettingsDep,
    q: Annotated[str, Query(min_length=1, description="Free-text query")],
    limit: Annotated[int, Query(ge=1, le=MAX_LIST_LIMIT)] = 10,
) -> list[SearchHit]:
    """Rank frozen records by cosine similarity to the embedded query.

    Uses the same embedder as ingestion (stub backend by default) and pgvector cosine
    SQL. On SQLite there is no pgvector, so this returns HTTP 501 rather than a fake
    fallback search — honest unavailability.
    """

    db = Database.from_url(settings.db_url)
    if db.dialect != "postgresql":
        raise HTTPException(
            status_code=501,
            detail="semantic search requires Postgres+pgvector",
        )

    vector = get_embedder().embed(q)
    # The pgvector column is vector(1024). A non-1024-dim embedder (e.g. the offline
    # stub) would trigger a dimension-mismatch error inside pgvector mid-request; fail
    # closed with the same explicit 501 instead of issuing the doomed query.
    if len(vector) != E5_DIMENSION:
        raise HTTPException(
            status_code=501,
            detail=(
                f"search requires a {E5_DIMENSION}-dim embedder (multilingual-e5); "
                f"current backend produces {len(vector)} dims"
            ),
        )

    records = repo.search_by_embedding(vector, limit)
    return [SearchHit(rank=i, record=r) for i, r in enumerate(records, start=1)]
