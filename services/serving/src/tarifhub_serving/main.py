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

from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from tarifhub_ingest.embeddings.embedder import E5_DIMENSION, get_embedder
from tarifhub_ingest.models.tariff_model import TariffRecord

from tarifhub_serving.config import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    Settings,
    get_settings,
)
from tarifhub_serving.db import Database
from tarifhub_serving.explain import build_diff, build_explanation
from tarifhub_serving.models import (
    DiffResponse,
    ExplainResponse,
    HealthResponse,
    SearchHit,
)
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


_AS_OF_DESCRIPTION = (
    "Point-in-time date (ISO YYYY-MM-DD). Return the version of each key whose validity "
    "window covers this date: valid_from <= as_of AND (valid_to IS NULL OR valid_to >= "
    "as_of), then MAX(version) among matches. A record with a NULL valid_from is treated "
    "as valid from the beginning of time. Omit for the latest version (default behaviour)."
)


@app.get(
    "/api/v1/tariffs",
    response_model=list[TariffRecord],
    summary="List the latest (or as-of) version of each frozen tariff record",
    description=(
        "Returns one frozen record per (tariff_system, tariff_code), ordered by "
        "(tariff_system, tariff_code). Without as_of this is the latest version; with "
        "as_of it is the point-in-time version (see the as_of parameter). Paginated."
    ),
)
def list_tariffs(
    repo: RepoDep,
    system: Annotated[str | None, Query(description="Filter by tariff system, e.g. TARDOC")] = None,
    as_of: Annotated[date | None, Query(description=_AS_OF_DESCRIPTION)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIST_LIMIT)] = DEFAULT_LIST_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TariffRecord]:
    """One frozen record per key (latest, or as-of a date), filtered + paginated."""

    return repo.list_latest(system=system, as_of=as_of, limit=limit, offset=offset)


@app.get(
    "/api/v1/tariffs/{system}/{code}",
    response_model=TariffRecord,
    summary="Get the latest (or as-of) frozen record for a (system, code) key",
    description=(
        "Returns the highest-version frozen record for the key, or the point-in-time "
        "version when as_of is supplied (see the as_of parameter). 404 if no version "
        "matches."
    ),
)
def get_tariff(
    system: str,
    code: str,
    repo: RepoDep,
    as_of: Annotated[date | None, Query(description=_AS_OF_DESCRIPTION)] = None,
) -> TariffRecord:
    """Return the highest-version (or as-of) frozen record, or 404 if none matches."""

    record = repo.get_latest(system, code, as_of=as_of)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"no frozen record for system={system} code={code}",
        )
    return record


@app.get(
    "/api/v1/tariffs/{system}/{code}/diff",
    response_model=DiffResponse,
    summary="Field-level diff between two versions of a frozen record",
    description=(
        "Compares two versions of a (tariff_system, tariff_code) record and returns the "
        "fields that differ. Values are rendered exactly as served elsewhere (verbatim "
        "frozen values; the nested designation diffs as dotted leaves, e.g. "
        "designation.de). record_hash, version and created_at are never diffed. Changes "
        "are sorted by field name. 404 if either version is missing."
    ),
)
def diff_tariff(
    repo: RepoDep,
    system: Annotated[str, Path(description="Tariff system, e.g. TARDOC")],
    code: Annotated[str, Path(description="Tariff code")],
    from_version: Annotated[int, Query(alias="from", ge=1, description="Source version")],
    to_version: Annotated[int, Query(alias="to", ge=1, description="Target version")],
) -> DiffResponse:
    """Return the field-level diff between ``from`` and ``to`` versions, or 404."""

    from_record = repo.get_version(system, code, from_version)
    if from_record is None:
        raise HTTPException(
            status_code=404,
            detail=f"no version {from_version} for system={system} code={code}",
        )
    to_record = repo.get_version(system, code, to_version)
    if to_record is None:
        raise HTTPException(
            status_code=404,
            detail=f"no version {to_version} for system={system} code={code}",
        )
    return build_diff(system, code, from_record, to_record)


@app.get(
    "/api/v1/explain",
    response_model=ExplainResponse,
    summary="Deterministic, record-grounded explanation of a tariff code",
    description=(
        "Returns ALL versions of every (tariff_system, tariff_code) matching the code "
        "(verbatim frozen records, ordered by tariff_system then version) plus a "
        "deterministic explanation assembled only from record fields. The explanation is "
        "rule-generated (labelled '[deterministic]') with no AI, no randomness and no "
        "wall-clock. 404 if the code is unknown."
    ),
)
def explain(
    repo: RepoDep,
    code: Annotated[str, Query(min_length=1, description="Tariff code to explain")],
    system: Annotated[str | None, Query(description="Optional tariff system filter")] = None,
) -> ExplainResponse:
    """Return every version of ``code`` plus a deterministic explanation, or 404."""

    records = repo.list_versions_by_code(code, system=system)
    if not records:
        raise HTTPException(status_code=404, detail=f"no frozen record for code={code}")
    return ExplainResponse(
        code=code,
        records=records,
        explanation=build_explanation(code, records),
    )


@app.get(
    "/api/v1/search",
    response_model=list[SearchHit],
    summary="Semantic search over frozen records (pgvector, or offline ranking on SQLite)",
    description=(
        "Ranks frozen records by cosine similarity to the embedded query, using the same "
        "embedder as ingestion. On Postgres+pgvector the ranking runs in SQL. On the "
        "offline SQLite mirror it runs in-process over stored embeddings of matching "
        "dimension (deterministic, ties broken by tariff_system then tariff_code). On "
        "Postgres with a non-1024-dim embedder the endpoint fails closed with HTTP 501 "
        "rather than issue a doomed pgvector query. Hits are unaltered frozen records — "
        "search only ranks, it never computes a value."
    ),
)
def search(
    repo: RepoDep,
    settings: SettingsDep,
    q: Annotated[str, Query(min_length=1, description="Free-text query")],
    limit: Annotated[int, Query(ge=1, le=MAX_LIST_LIMIT)] = 10,
) -> list[SearchHit]:
    """Rank frozen records by cosine similarity to the embedded query (see description)."""

    db = Database.from_url(settings.db_url)

    # Embed the user query through the QUERY path (e5 "query: " prefix), not the
    # passage path used to index records — the asymmetry is what e5 is trained for.
    vector = get_embedder().embed_query(q)

    if db.dialect == "postgresql":
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
    else:
        # SQLite has no pgvector; rank stored embeddings in-process (deterministic). Only
        # rows whose stored dimension matches the query vector's are candidates.
        records = repo.search_offline(vector, limit)

    return [SearchHit(rank=i, record=r) for i, r in enumerate(records, start=1)]
