"""FastAPI admin / read surface for the ingestion service.

Endpoints:
    GET  /health
    GET  /tariffs
    GET  /tariffs/{tariff_code}
    POST /ingest/sample          (runs the offline sample pipeline)

This module is deliberately on the deterministic side of the freeze line: the GET
endpoints only read frozen records, and NO LLM client is imported here. The single
AI seam lives behind ``ingestion.pipeline`` (pre-freeze) and is import-guarded.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel

from tarifhub_ingest import __version__
from tarifhub_ingest.audit.audit_logger import AuditLogger
from tarifhub_ingest.config import Settings, get_settings
from tarifhub_ingest.embeddings.embedder import get_embedder
from tarifhub_ingest.ingestion.pipeline import run_pipeline
from tarifhub_ingest.ingestion.source_loader import default_sample_dir, discover_samples
from tarifhub_ingest.storage.db import Database
from tarifhub_ingest.storage.tariff_repository import TariffRepository


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
            raise HTTPException(status_code=404, detail=f"tariff_code {tariff_code!r} not found")
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
            raise HTTPException(status_code=404, detail=f"no sample sources under {sample_dir}")
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

    return app


app = create_app()


def run() -> None:
    """Console-script entry point: serve the app with uvicorn."""

    import uvicorn  # local import keeps module import light for tests

    uvicorn.run("tarifhub_ingest.main:app", host="0.0.0.0", port=8000, reload=False)
