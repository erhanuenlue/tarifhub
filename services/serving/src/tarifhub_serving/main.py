"""FastAPI app: deterministic read API over frozen tariff records (L1 TarifCore).

Every value returned is an unaltered, frozen, versioned record read straight from the
system of record. No AI is on this value path. The only AI-adjacent seam is the
semantic-search endpoint, which uses an embedder to RANK frozen rows by similarity —
it never computes, alters, or fabricates a billing value. Search ranks via pgvector on
Postgres and via a deterministic in-process cosine over the stored embeddings on the
offline SQLite mirror (ADR-017); a dimension mismatch on Postgres fails closed (501).

Import discipline: from ``tarifhub_ingest`` we import ONLY ``models.tariff_model`` and
``embeddings.embedder`` — never mappers, never anything that could pull an LLM client.
This is enforced by ``tests/test_serving_boundary.py``.
"""

from __future__ import annotations

import contextlib
import threading
import time
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, Path, Query, Request
from tarifhub_ingest.embeddings.embedder import E5_DIMENSION, get_embedder
from tarifhub_ingest.models.tariff_model import TariffRecord, TariffSystem

from tarifhub_serving.config import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    Settings,
    get_settings,
)
from tarifhub_serving.db import Database
from tarifhub_serving.errors import (
    SearchBackendUnavailable,
    TariffNotFound,
    register_exception_handlers,
)
from tarifhub_serving.explain import build_diff, build_explanation
from tarifhub_serving.fhir import (
    ChargeItemDefinition,
    CodeSystem,
    to_charge_item_definition,
    to_code_system,
)
from tarifhub_serving.models import (
    DiffResponse,
    ExplainResponse,
    HealthResponse,
    SearchHit,
)
from tarifhub_serving.repository import ServingRepository
from tarifhub_serving.telemetry import setup_telemetry

# Process-wide Postgres connection pools, keyed by db_url. A pool is expensive to build
# and is meant to be shared across requests, so we create at most one per URL and reuse
# it. SQLite is never pooled (cheap, file-local per-request connections) and is absent
# from this registry. The app lifespan warms the pool for the configured URL at startup
# and disposes every pool at shutdown. Double-checked locking guards lazy creation when
# the app is exercised without its lifespan (a bare TestClient), so the same single pool
# is shared either way.
_POOLS: dict[str, Any] = {}
_POOLS_LOCK = threading.Lock()


def _get_pool(db: Database, settings: Settings):
    """Return the shared pool for ``db`` (``None`` for SQLite), creating it once per URL."""

    if db.dialect != "postgresql":
        return None
    pool = _POOLS.get(db.db_url)
    if pool is None:
        with _POOLS_LOCK:
            pool = _POOLS.get(db.db_url)  # re-check inside the lock
            if pool is None:
                pool = db.create_pool(
                    min_size=settings.db_pool_min_size, max_size=settings.db_pool_max_size
                )
                _POOLS[db.db_url] = pool
    return pool


def _close_pools() -> None:
    """Close and forget every pool (called from the lifespan on shutdown)."""

    with _POOLS_LOCK:
        for pool in _POOLS.values():
            pool.close()
        _POOLS.clear()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm the Postgres connection pool once at startup, dispose it at shutdown.

    On Postgres this opens the shared pool the request dependency then borrows from, so
    connections are pooled rather than opened per request. On SQLite there is no pool to
    warm (``_get_pool`` returns ``None``), so the dependency opens a cheap per-request
    connection exactly as before. Resolving settings here means the configured URL is read
    once at startup.
    """

    settings = get_settings()
    _get_pool(Database.from_url(settings.db_url), settings)
    try:
        yield
    finally:
        _close_pools()
        # Flush and stop the telemetry exporters so background exporter threads do not leak
        # and any queued spans or final metrics are flushed at shutdown. A no-op when no
        # endpoint is configured (no span processor or metric reader was installed).
        telemetry = getattr(app.state, "telemetry", None)
        if telemetry is not None:
            telemetry.tracer_provider.shutdown()
            telemetry.meter_provider.shutdown()


# Routes are attached to a module-level router and mounted onto the app inside
# create_app(). This keeps the route definitions module-level (imported by tests) while
# letting the factory build the FastAPI instance, wire error handlers and instrument
# observe-only telemetry in one place.
router = APIRouter()


def get_repository(request: Request):
    """Yield a read-only repository bound to a pooled (Postgres) or fresh (SQLite) conn.

    On Postgres a connection is borrowed from the shared process pool for the duration of
    the request and returned to the pool on completion (``with pool.connection()``). On
    SQLite there is no pool, so a fresh connection is opened and closed per request, the
    prior behaviour byte-for-byte. The repository API and the served rows are identical on
    both paths. Settings are read per request so a test that repoints ``TARIFHUB_DB_URL``
    still takes effect.
    """

    settings = get_settings()
    db = Database.from_url(settings.db_url)
    pool = _get_pool(db, settings)
    if pool is None:
        conn = db.connect()
        try:
            yield ServingRepository(conn, db)
        finally:
            conn.close()
    else:
        with pool.connection() as conn:
            yield ServingRepository(conn, db)


RepoDep = Annotated[ServingRepository, Depends(get_repository)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

# Bound the search-latency metric's cardinality. An unauthenticated caller can pass any
# ?system= value, so only the known tariff systems (plus "all" when unfiltered) are used
# verbatim as the metric attribute and every other value buckets to "other". This keeps
# the histogram's label set to a small fixed size instead of one time series per arbitrary
# input. Observe-only: the served result is unaffected either way.
_KNOWN_TARIFF_SYSTEMS = frozenset(s.value for s in TariffSystem)


def _system_metric_label(system: str | None) -> str:
    """Map a request's ``system`` filter to a bounded metric attribute value."""

    if system is None:
        return "all"
    return system if system in _KNOWN_TARIFF_SYSTEMS else "other"


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health() -> HealthResponse:
    """Return ``{"status": "ok"}`` when the service is up."""

    return HealthResponse(status="ok")


_AS_OF_DESCRIPTION = (
    "Point-in-time date (ISO YYYY-MM-DD). Return the version of each key whose validity "
    "window covers this date: valid_from <= as_of AND (valid_to IS NULL OR valid_to >= "
    "as_of), then MAX(version) among matches. A record with a NULL valid_from is treated "
    "as valid from the beginning of time. Omit for the latest version (default behaviour)."
)


@router.get(
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


@router.get(
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
        raise TariffNotFound(f"no frozen record for system={system} code={code}")
    return record


@router.get(
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
        raise TariffNotFound(f"no version {from_version} for system={system} code={code}")
    to_record = repo.get_version(system, code, to_version)
    if to_record is None:
        raise TariffNotFound(f"no version {to_version} for system={system} code={code}")
    return build_diff(system, code, from_record, to_record)


@router.get(
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
        raise TariffNotFound(f"no frozen record for code={code}")
    return ExplainResponse(
        code=code,
        records=records,
        explanation=build_explanation(code, records),
    )


_FHIR_STATUS_RULE = (
    "status is derived ONLY from record data, never from the wall-clock: the selected "
    "version is 'active' when it is the highest version of its (system, code) key, else "
    "'retired' (a superseded version). No 'today' is consulted anywhere."
)
_FHIR_ID_RULE = (
    "The FHIR resource id is built as '{system}-{code}-{version}', lower-cased, with every "
    "character outside [a-z0-9-] (notably the '.' in tariff codes) replaced by '-' so it is "
    "FHIR-id-safe (e.g. TARDOC/AA.00.0010 v2 -> 'tardoc-aa-00-0010-2')."
)


@router.get(
    "/api/v1/fhir/ChargeItemDefinition/{system}/{code}",
    response_model=ChargeItemDefinition,
    response_model_exclude_none=True,
    summary="FHIR R4 ChargeItemDefinition for one frozen tariff record",
    description=(
        "Maps ONE frozen TariffRecord to a minimal valid R4 ChargeItemDefinition over the "
        "same value path as the REST routes (read-only; no AI, no value computation). "
        "Version selection precedence: ?version wins over ?as_of; both absent -> latest "
        f"version. {_AS_OF_DESCRIPTION} {_FHIR_STATUS_RULE} {_FHIR_ID_RULE} price_chf maps "
        "to a 'base' priceComponent with a CHF Money amount; tax_points maps to an "
        "'informational' priceComponent factor (a component is omitted when its field is "
        "None). FHIR decimals are JSON numbers emitted via float(); at our scales they "
        "round-trip the stored Decimal exactly. record_hash and source_url are carried as "
        "valueString extensions under the tarifhub canonical URL space. 404 when the key, "
        "version or as_of date matches no frozen record."
    ),
)
def fhir_charge_item_definition(
    repo: RepoDep,
    system: Annotated[str, Path(description="Tariff system, e.g. TARDOC")],
    code: Annotated[str, Path(description="Tariff code, e.g. AA.00.0010")],
    version: Annotated[
        int | None,
        Query(ge=1, description="Exact version; wins over as_of when both are supplied"),
    ] = None,
    as_of: Annotated[date | None, Query(description=_AS_OF_DESCRIPTION)] = None,
) -> ChargeItemDefinition:
    """Resolve one frozen record (version | as_of | latest) and map it to R4, or 404."""

    if version is not None:
        record = repo.get_version(system, code, version)
        if record is None:
            raise TariffNotFound(f"no version {version} for system={system} code={code}")
    else:
        record = repo.get_latest(system, code, as_of=as_of)
        if record is None:
            raise TariffNotFound(f"no frozen record for system={system} code={code}")

    # is_latest drives the deterministic status rule: compare the selected version with
    # the unfiltered highest version of the key. No wall-clock is consulted.
    latest = repo.get_latest(system, code)
    is_latest = latest is not None and latest.version == record.version
    return to_charge_item_definition(system, code, record, is_latest=is_latest)


@router.get(
    "/api/v1/fhir/CodeSystem/{system}",
    response_model=CodeSystem,
    response_model_exclude_none=True,
    summary="FHIR R4 CodeSystem for a tariff system's latest-version records",
    description=(
        "Maps a tariff system's latest-version (or as-of) records to ONE minimal valid R4 "
        "CodeSystem (read-only; no AI). content='fragment' is honest: the response carries a "
        "windowed page (limit/offset), not necessarily the whole catalogue. count is the "
        "TOTAL number of (system, code) keys in the system, independent of the window. "
        "status is always 'active' (an aggregate of current records, derived from data not "
        "the clock). concept entries are ordered by tariff_code ascending (deterministic); "
        "each carries the German display plus fr/it as concept.designation entries (only "
        f"when non-null). {_AS_OF_DESCRIPTION} An unknown or empty system returns 404, "
        "consistent with the other routes."
    ),
)
def fhir_code_system(
    repo: RepoDep,
    system: Annotated[str, Path(description="Tariff system, e.g. TARDOC")],
    as_of: Annotated[date | None, Query(description=_AS_OF_DESCRIPTION)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIST_LIMIT)] = DEFAULT_LIST_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CodeSystem:
    """Map a system's latest-version records (windowed) to one R4 CodeSystem, or 404."""

    total = repo.count_latest_keys(system, as_of=as_of)
    if total == 0:
        raise TariffNotFound(f"no frozen records for system={system}")
    records = repo.list_latest(system=system, as_of=as_of, limit=limit, offset=offset)
    return to_code_system(system, records, count=total)


@router.get(
    "/api/v1/search",
    response_model=list[SearchHit],
    summary="Semantic search over frozen records (pgvector, or offline ranking on SQLite)",
    description=(
        "Ranks frozen records by cosine similarity to the embedded query, using the same "
        "embedder as ingestion. On Postgres+pgvector the ranking runs in SQL. On the "
        "offline SQLite mirror it runs in-process over stored embeddings of matching "
        "dimension (deterministic, ties broken by tariff_system then tariff_code). An "
        "optional system filter restricts the ranked candidates to one tariff system "
        "(TARDOC, EAL or SL); omit it to rank across every system. On Postgres with a "
        "non-1024-dim embedder the endpoint fails closed with HTTP 501 rather than issue a "
        "doomed pgvector query. Hits are unaltered frozen records — search only ranks, it "
        "never computes a value."
    ),
)
def search(
    repo: RepoDep,
    settings: SettingsDep,
    request: Request,
    q: Annotated[str, Query(min_length=1, description="Free-text query")],
    system: Annotated[
        str | None,
        Query(description="Optional tariff system filter, e.g. TARDOC, EAL or SL"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIST_LIMIT)] = 10,
) -> list[SearchHit]:
    """Rank frozen records by cosine similarity to the embedded query (see description)."""

    telemetry = getattr(request.app.state, "telemetry", None)
    db = Database.from_url(settings.db_url)

    # Observe-only: time and trace the embed+rank work. This records latency and a span
    # for observability alone and never affects the served value. nullcontext is a
    # defensive fallback for the (unexpected) case where telemetry was not wired.
    span = (
        telemetry.tracer.start_as_current_span("serving.search")
        if telemetry is not None
        else contextlib.nullcontext()
    )
    start = time.perf_counter()
    with span:
        # Embed the user query through the QUERY path (e5 "query: " prefix), not the
        # passage path used to index records — the asymmetry is what e5 is trained for.
        vector = get_embedder().embed_query(q)

        if db.dialect == "postgresql":
            # The pgvector column is vector(1024). A non-1024-dim embedder (e.g. the
            # offline stub) would trigger a dimension-mismatch error inside pgvector
            # mid-request; fail closed with the same explicit 501 instead of issuing the
            # doomed query.
            if len(vector) != E5_DIMENSION:
                raise SearchBackendUnavailable(
                    f"search requires a {E5_DIMENSION}-dim embedder (multilingual-e5); "
                    f"current backend produces {len(vector)} dims"
                )
            records = repo.search_by_embedding(vector, limit, system=system)
        else:
            # SQLite has no pgvector; rank stored embeddings in-process (deterministic).
            # Only rows whose stored dimension matches the query vector's are candidates.
            records = repo.search_offline(vector, limit, system=system)

    # Observe-only: record the wall-clock latency once ranking succeeded (a 501 above
    # skips this). Never read back into the served value.
    if telemetry is not None:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        telemetry.search_latency.record(elapsed_ms, {"system": _system_metric_label(system)})

    return [SearchHit(rank=i, record=r) for i, r in enumerate(records, start=1)]


def create_app(
    *,
    telemetry_span_exporter=None,
    telemetry_metric_reader=None,
) -> FastAPI:
    """Build the serving app: routes, RFC 7807 handlers and observe-only telemetry.

    The telemetry exporter/reader default to ``None`` (no collector), so the offline
    suite and CI run with a true no-op; the tests inject in-memory ones to assert the
    span and metric are produced. The optional overrides are the only reason this is a
    factory rather than a module-level app.
    """

    app = FastAPI(
        title="tarifhub Serving (L1 TarifCore)",
        description="Deterministic read API over frozen Swiss ambulatory tariff records.",
        version="0.1.0",
        lifespan=lifespan,
    )
    # Centralised RFC 7807 problem+json error handling (domain errors, validation, any
    # HTTPException, and a catch-all that turns an unexpected error into a structured 500
    # with a correlation id instead of a bare 500). See tarifhub_serving.errors.
    register_exception_handlers(app)
    # Observe-only tracing + metrics. Never on the billing value path (see telemetry).
    setup_telemetry(
        app,
        span_exporter=telemetry_span_exporter,
        metric_reader=telemetry_metric_reader,
    )
    app.include_router(router)
    return app


# Module-level app so existing ``from tarifhub_serving.main import app`` imports keep
# working (conftest fixtures, test_app_lifespan, the ASGI entrypoint).
app = create_app()
