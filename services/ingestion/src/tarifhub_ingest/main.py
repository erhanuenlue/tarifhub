"""FastAPI admin / read surface for the ingestion service.

Endpoints:
    GET  /health
    GET  /tariffs
    GET  /tariffs/{tariff_code}
    POST /ingest/sample          (runs the offline sample pipeline)
    GET  /review/queue           (flagged records awaiting human review)
    POST /review                 (apply a human approve/correct decision; re-freezes)

This module is deliberately on the deterministic side of the freeze line: the GET
endpoints only read frozen records, and NO LLM client is imported here. The single
AI seam lives behind ``ingestion.pipeline`` (pre-freeze) and is import-guarded. The
review write-back is human-driven and likewise AI-free: the route delegates to
``review_service.apply_review_decision``, which runs the SAME deterministic
``validate`` -> ``freeze`` -> audit pipeline as ingest, persisting an immutable new
version (``tests/test_review_boundary.py`` pins this module and ``review.py``;
``tests/test_value_path_boundary.py`` scans the whole package, the service included).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from pydantic import BaseModel

from tarifhub_ingest import __version__
from tarifhub_ingest.audit.audit_logger import AuditLogger
from tarifhub_ingest.config import Settings, get_settings
from tarifhub_ingest.embeddings.embedder import get_embedder
from tarifhub_ingest.errors import (
    SampleSourcesNotFound,
    TariffCodeNotFound,
    register_exception_handlers,
)
from tarifhub_ingest.ingestion.pipeline import run_pipeline
from tarifhub_ingest.ingestion.source_loader import default_sample_dir, discover_samples
from tarifhub_ingest.models.tariff_model import TariffRecord
from tarifhub_ingest.review import (
    ReviewDecision,
    ReviewItem,
    ReviewResult,
    to_review_item,
)
from tarifhub_ingest.review_service import apply_review_decision
from tarifhub_ingest.storage.db import Database
from tarifhub_ingest.storage.tariff_repository import TariffRepository


class HealthResponse(BaseModel):
    """Liveness payload for GET /health (status, service name and version).

    Field order is the wire order: status, service, version.
    """

    status: str
    service: str
    version: str


class IngestSampleResponse(BaseModel):
    """Summary of a sample-pipeline run (the POST /ingest/sample output contract)."""

    processed: int
    frozen: int
    skipped_existing: int
    flagged_for_review: int
    refill: bool
    tariff_codes: list[str]


# Request-scoped providers. The lifespan (below) populates ``app.state`` once at
# startup; these expose those singletons to the routes via ``Depends`` instead of the
# routes reaching into ``request.app.state`` directly (mirrors the serving layer). The
# settings provider deliberately reads ``app.state.settings`` rather than calling
# ``config.get_settings()`` so the ``create_app(settings=...)`` override keeps working.
def get_repository(request: Request) -> TariffRepository:
    """Return the read/write repository bound to the app's startup connection."""

    return request.app.state.repo


def get_audit_logger(request: Request) -> AuditLogger:
    """Return the append-only audit logger bound to the app's startup connection."""

    return request.app.state.audit


def get_active_settings(request: Request) -> Settings:
    """Return the settings resolved at startup (honours the create_app override)."""

    return request.app.state.settings


RepoDep = Annotated[TariffRepository, Depends(get_repository)]
AuditDep = Annotated[AuditLogger, Depends(get_audit_logger)]
SettingsDep = Annotated[Settings, Depends(get_active_settings)]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory. Settings resolve at startup so tests can set env first."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        active = settings or get_settings()
        db = Database.from_url(active.db_url)
        conn = db.connect()
        db.init_schema(conn)
        app.state.settings = active
        app.state.db = db
        app.state.conn = conn
        app.state.repo = TariffRepository(conn, db)
        app.state.audit = AuditLogger(conn, db)
        try:
            yield
        finally:
            conn.close()

    app = FastAPI(
        title="tarifhub Ingestion",
        version=__version__,
        summary="Pre-freeze harmonization pipeline + read API over frozen records.",
        lifespan=lifespan,
    )

    # Centralised RFC 7807 problem+json error handling, identical to the serving layer:
    # domain errors -> mapped status, validation -> 422, any HTTPException, and a catch-all
    # that turns an unexpected error into a structured 500 with a correlation id. The review
    # write path raises domain exceptions (no bare HTTPException). See tarifhub_ingest.errors.
    register_exception_handlers(app)

    @app.get(
        "/health",
        response_model=HealthResponse,
        summary="Liveness probe with service name and version",
    )
    def health() -> HealthResponse:
        """Return ``{"status": "ok", ...}`` with the service name and version when up."""

        return HealthResponse(status="ok", service="tarifhub-ingest", version=__version__)

    @app.get(
        "/tariffs",
        response_model=list[TariffRecord],
        summary="List every frozen tariff record (all versions)",
    )
    def list_tariffs(repo: RepoDep) -> list[TariffRecord]:
        """Return all frozen records (every version of every key), ordered by system, code, version.

        FastAPI serializes each canonical :class:`TariffRecord` through its response
        model, which equals the model's JSON-mode dump.
        """

        return repo.list_all()

    @app.get(
        "/tariffs/{tariff_code}",
        response_model=TariffRecord,
        summary="Get the latest frozen record for a tariff code",
    )
    def get_tariff(tariff_code: str, repo: RepoDep) -> TariffRecord:
        """Return the highest-version frozen record for the code, or 404 if none exists."""

        record = repo.get(tariff_code)
        if record is None:
            raise TariffCodeNotFound(f"tariff_code {tariff_code!r} not found")
        return record

    @app.post(
        "/ingest/sample",
        response_model=IngestSampleResponse,
        summary="Run the offline sample pipeline (set refill=true to re-fill AI gaps)",
    )
    def ingest_sample(
        repo: RepoDep,
        audit: AuditDep,
        settings: SettingsDep,
        refill: Annotated[
            bool,
            Query(description="Bypass AI fill-reuse and re-run ai_map for changed/unchanged rows"),
        ] = False,
    ) -> IngestSampleResponse:
        """Run the offline sample pipeline and freeze any new records.

        Reads the bundled sample sources, runs the deterministic
        map -> ai_map -> validate -> score -> freeze pipeline, and persists new frozen
        versions. Hash-idempotent: re-running identical content freezes nothing new.
        """

        sample_dir = settings.sample_dir or default_sample_dir()
        specs = discover_samples(sample_dir)
        if not specs:
            raise SampleSourcesNotFound(f"no sample sources under {sample_dir}")
        report = run_pipeline(
            specs, repo, audit, settings=settings, embedder=get_embedder(settings), refill=refill
        )
        return IngestSampleResponse(
            processed=report.processed,
            frozen=report.frozen,
            skipped_existing=report.skipped_existing,
            flagged_for_review=report.flagged_for_review,
            refill=refill,
            tariff_codes=[record.tariff_code for record in report.records],
        )

    @app.get(
        "/review/queue",
        response_model=list[ReviewItem],
        summary="List flagged records awaiting human review (the review queue)",
    )
    def review_queue(repo: RepoDep, settings: SettingsDep) -> list[ReviewItem]:
        """Return the latest flagged version of each key, shaped to the console contract.

        Read-only: it never mutates a record. Each item carries the per-field
        raw-vs-proposal diff, the billing flags, the harmonisation confidence and the
        proposing model, exactly as the review form consumes it.
        """

        return [
            to_review_item(record, threshold=settings.review_threshold)
            for record in repo.list_flagged()
        ]

    @app.post(
        "/review",
        response_model=ReviewResult,
        summary="Apply a human approve/correct decision and freeze a new version",
    )
    def submit_review(
        decision: ReviewDecision,
        repo: RepoDep,
        audit: AuditDep,
        settings: SettingsDep,
    ) -> ReviewResult:
        """Close the human-in-the-loop: a reviewed decision becomes a new frozen version.

        Thin adapter: FastAPI validates the ``ReviewDecision`` body, the route binds it
        to the app's repository/audit/settings, and
        :func:`tarifhub_ingest.review_service.apply_review_decision` owns the
        load -> guard -> ``validate`` -> ``freeze`` -> embed -> store -> audit
        orchestration. Failures surface as domain exceptions rendered by the registered
        problem+json handlers (404/409/400/422 as documented on the service function).
        """

        return apply_review_decision(decision, repo=repo, audit=audit, settings=settings)

    return app


app = create_app()


def run() -> None:
    """Console-script entry point: serve the app with uvicorn.

    Host and port come from the env-driven :class:`Settings` (TARIFHUB_API_HOST /
    TARIFHUB_API_PORT), defaulting to the same 0.0.0.0:8000 the Docker CMD passes.
    """

    import uvicorn  # noqa: PLC0415  (lazy: keep module import light for tests)

    settings = get_settings()
    uvicorn.run(
        "tarifhub_ingest.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
