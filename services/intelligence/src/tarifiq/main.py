"""FastAPI surface for the TarifIQ intelligence service (Layer 2).

Endpoints:
    GET  /health
    POST /v1/combinability-check     (deterministic rule/cumulation evaluation)
    GET  /v1/crosswalk/{tarmed_code}  (deterministic TARMED→TARDOC lookup)
    POST /v1/validate                 (deterministic pre-freeze rule validation)

This module is on the deterministic side of the freeze line: every endpoint is a pure
function of the request and the frozen rule/cross-walk tables, and NO LLM client is
imported here. The single AI seam (``crosswalk.tarmed_tardoc.ai_rule_suggest``) only
*suggests* candidate rules pre-freeze and is intentionally NOT wired into any endpoint.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from tarifiq import __version__
from tarifiq.config import Settings, get_settings
from tarifiq.crosswalk.tarmed_tardoc import lookup_crosswalk
from tarifiq.models.rule_model import (
    CombinabilityCheckRequest,
    CombinabilityCheckResult,
    CombinabilityRule,
    CrosswalkResult,
    RuleValidationResult,
)
from tarifiq.rules.combinability import evaluate_combinability
from tarifiq.store.frozen_client import get_frozen_store
from tarifiq.validators.rule_validator import validate_rule


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory. Settings resolve at startup so tests can set env first."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        active = settings or get_settings()
        app.state.settings = active
        # Bundled offline store by default; live serving client when TARIFIQ_OFFLINE=0.
        app.state.frozen_store = get_frozen_store(active)
        yield

    app = FastAPI(
        title="tarifhub Intelligence (TarifIQ)",
        version=__version__,
        summary="Deterministic combinability rules, TARMED↔TARDOC cross-walk, and rule validation.",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "tarifiq", "version": __version__}

    @app.post("/v1/combinability-check")
    def combinability_check(
        payload: CombinabilityCheckRequest, request: Request
    ) -> CombinabilityCheckResult:
        return evaluate_combinability(payload, store=request.app.state.frozen_store)

    @app.get("/v1/crosswalk/{tarmed_code}")
    def crosswalk(tarmed_code: str) -> CrosswalkResult:
        result = lookup_crosswalk(tarmed_code)
        if not result.found:
            raise HTTPException(
                status_code=404,
                detail=f"TARMED code {tarmed_code!r} not in the frozen cross-walk table",
            )
        return result

    @app.post("/v1/validate")
    def validate(rule: CombinabilityRule, request: Request) -> RuleValidationResult:
        return validate_rule(rule, store=request.app.state.frozen_store)

    return app


app = create_app()


def run() -> None:
    """Console-script entry point: serve the app with uvicorn."""

    import uvicorn  # local import keeps module import light for tests

    uvicorn.run("tarifiq.main:app", host="0.0.0.0", port=8070, reload=False)
