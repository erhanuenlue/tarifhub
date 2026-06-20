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
review write-back is human-driven and likewise AI-free: it runs the SAME deterministic
``validate`` -> ``freeze`` -> audit pipeline as ingest, persisting an immutable new
version (``tests/test_review_boundary.py`` proves no LLM client is importable here).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Query, Request
from pydantic import BaseModel

from tarifhub_ingest import __version__
from tarifhub_ingest.audit.audit_logger import AuditLogger
from tarifhub_ingest.config import Settings, get_settings
from tarifhub_ingest.embeddings.embedder import get_embedder
from tarifhub_ingest.errors import (
    ReviewConflict,
    ReviewRecordNotFound,
    ReviewValidationError,
    SampleSourcesNotFound,
    TariffCodeNotFound,
    register_exception_handlers,
)
from tarifhub_ingest.ingestion.pipeline import run_pipeline
from tarifhub_ingest.ingestion.source_loader import default_sample_dir, discover_samples
from tarifhub_ingest.review import (
    ReviewDecision,
    ReviewItem,
    ReviewResult,
    prepare_reviewed_record,
    review_message,
    to_review_item,
)
from tarifhub_ingest.storage.db import Database
from tarifhub_ingest.storage.tariff_repository import TariffRepository
from tarifhub_ingest.validators.tariff_validator import validate
from tarifhub_ingest.versioning.freeze_record import freeze


class IngestSampleResponse(BaseModel):
    """Summary of a sample-pipeline run (the POST /ingest/sample output contract)."""

    processed: int
    frozen: int
    skipped_existing: int
    flagged_for_review: int
    refill: bool
    tariff_codes: list[str]


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

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "tarifhub-ingest", "version": __version__}

    @app.get("/tariffs")
    def list_tariffs(request: Request) -> list[dict]:
        repo: TariffRepository = request.app.state.repo
        return [record.model_dump(mode="json") for record in repo.list_all()]

    @app.get("/tariffs/{tariff_code}")
    def get_tariff(tariff_code: str, request: Request) -> dict:
        repo: TariffRepository = request.app.state.repo
        record = repo.get(tariff_code)
        if record is None:
            raise TariffCodeNotFound(f"tariff_code {tariff_code!r} not found")
        return record.model_dump(mode="json")

    @app.post(
        "/ingest/sample",
        response_model=IngestSampleResponse,
        summary="Run the offline sample pipeline (set refill=true to re-fill AI gaps)",
    )
    def ingest_sample(
        request: Request,
        refill: Annotated[
            bool,
            Query(description="Bypass AI fill-reuse and re-run ai_map for changed/unchanged rows"),
        ] = False,
    ) -> IngestSampleResponse:
        active: Settings = request.app.state.settings
        repo: TariffRepository = request.app.state.repo
        audit: AuditLogger = request.app.state.audit
        sample_dir = active.sample_dir or default_sample_dir()
        specs = discover_samples(sample_dir)
        if not specs:
            raise SampleSourcesNotFound(f"no sample sources under {sample_dir}")
        report = run_pipeline(
            specs, repo, audit, settings=active, embedder=get_embedder(active), refill=refill
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
    def review_queue(request: Request) -> list[ReviewItem]:
        """Return the latest flagged version of each key, shaped to the console contract.

        Read-only: it never mutates a record. Each item carries the per-field
        raw-vs-proposal diff, the billing flags, the harmonisation confidence and the
        proposing model, exactly as the review form consumes it.
        """

        repo: TariffRepository = request.app.state.repo
        settings: Settings = request.app.state.settings
        return [
            to_review_item(record, threshold=settings.review_threshold)
            for record in repo.list_flagged()
        ]

    @app.post(
        "/review",
        response_model=ReviewResult,
        summary="Apply a human approve/correct decision and freeze a new version",
    )
    def submit_review(decision: ReviewDecision, request: Request) -> ReviewResult:
        """Close the human-in-the-loop: a reviewed decision becomes a new frozen version.

        Loads the current flagged version, rejects any billing-field correction (400),
        applies the decision, then runs the SAME deterministic pipeline as ingest —
        ``validate`` (422 if the reviewed record is still invalid) then ``freeze`` — and
        persists an immutable new version (``version + 1``, new ``record_hash``) with an
        appended audit event. The prior version and the audit log are never rewritten.
        """

        repo: TariffRepository = request.app.state.repo
        audit: AuditLogger = request.app.state.audit
        settings: Settings = request.app.state.settings

        record = repo.get(decision.tariff_code, decision.tariff_system)
        if record is None:
            raise ReviewRecordNotFound(
                f"no record for system={decision.tariff_system.value} "
                f"code={decision.tariff_code}"
            )
        if not record.requires_review:
            raise ReviewConflict(
                f"record {decision.tariff_system.value}/{decision.tariff_code} "
                "is not flagged for review"
            )
        # Optimistic concurrency: if the client names a version, it must be the live one.
        if decision.record_hash and record.record_hash != decision.record_hash:
            raise ReviewConflict(
                "record_hash does not match the current flagged version (stale read)"
            )

        # A refused decision (billing/unknown-field correction) raises ReviewError, a domain
        # exception the registered handler renders as the same problem+json envelope (400).
        prepared = prepare_reviewed_record(record, decision)

        result = validate(prepared)
        if not result.ok:
            raise ReviewValidationError(
                "reviewed record fails validation", extra={"errors": result.errors}
            )

        frozen = freeze(prepared)
        # Re-embed exactly as the pipeline does so the corrected designation stays
        # searchable. The embedder is optional (None when skipped on the Postgres leg,
        # whose vector(1024) column rejects the 16-dim offline stub) — mirror the
        # pipeline's guard rather than assuming a vector.
        embedder = get_embedder(settings)
        embedding = None
        if embedder is not None:
            text = f"{frozen.tariff_system.value} {frozen.tariff_code} {frozen.designation.de}"
            embedding = embedder.embed(text)
        stored = repo.add(frozen, embedding=embedding)
        if not stored:
            raise ReviewConflict("this exact reviewed version already exists")

        # Re-read for the authoritative version the repository assigned (hash is stable).
        current = repo.get(decision.tariff_code, decision.tariff_system)
        assert current is not None  # just persisted

        corrected_fields = (
            sorted(decision.corrections or {}) if decision.action == "correct" else []
        )
        audit.log(
            event_type=f"review_{decision.action}",
            record=current,
            source_file="console-review",
            confidence=current.harmonization_confidence,
            validation_ok=result.ok,
            detail={
                "action": decision.action,
                "reviewer": decision.reviewer,
                "note": decision.note,
                "corrected_fields": corrected_fields,
                "prev_version": record.version,
                "prev_record_hash": record.record_hash,
            },
        )

        return ReviewResult(
            ok=True,
            tariff_system=current.tariff_system.value,
            tariff_code=current.tariff_code,
            action=decision.action,
            frozen=True,
            version=current.version,
            record_hash=current.record_hash,
            message=review_message(decision.action, current.version, corrected_fields),
        )

    return app


app = create_app()


def run() -> None:
    """Console-script entry point: serve the app with uvicorn."""

    import uvicorn  # local import keeps module import light for tests

    uvicorn.run("tarifhub_ingest.main:app", host="0.0.0.0", port=8000, reload=False)
