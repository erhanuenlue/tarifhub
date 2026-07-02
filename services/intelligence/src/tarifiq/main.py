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
from typing import Annotated

from fastapi import Depends, FastAPI, Request

from tarifiq import __version__
from tarifiq.config import Settings, get_settings
from tarifiq.crosswalk.tarmed_tardoc import lookup_crosswalk
from tarifiq.errors import CrosswalkNotFound, register_exception_handlers
from tarifiq.models.rule_model import (
    CombinabilityCheckRequest,
    CombinabilityCheckResult,
    CombinabilityRule,
    CrosswalkResult,
    RuleValidationResult,
)
from tarifiq.rules.combinability import evaluate_combinability
from tarifiq.store.frozen_client import FrozenStore, get_frozen_store
from tarifiq.validators.rule_validator import validate_rule


def provide_frozen_store(request: Request) -> FrozenStore:
    """FastAPI dependency: the read-only frozen store wired onto ``app.state`` at startup.

    Reading from ``request.app.state`` (rather than a module global) keeps the store bound
    to the app the request hit, so ``create_app(settings=...)`` still selects its own store.
    Named distinctly from ``store.frozen_client.get_frozen_store`` to avoid shadowing it.
    """

    return request.app.state.frozen_store


StoreDep = Annotated[FrozenStore, Depends(provide_frozen_store)]


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

    # Centralised RFC 7807 problem+json error handling, identical to the serving and
    # ingestion layers: domain errors -> mapped status, validation -> 422, any HTTPException,
    # and a catch-all that turns an unexpected error into a structured 500 with a correlation
    # id and no leaked internals. See tarifiq.errors.
    register_exception_handlers(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "tarifiq", "version": __version__}

    @app.post("/v1/combinability-check")
    def combinability_check(
        payload: CombinabilityCheckRequest, store: StoreDep
    ) -> CombinabilityCheckResult:
        return evaluate_combinability(payload, store=store)

    @app.get("/v1/crosswalk/{tarmed_code}")
    def crosswalk(tarmed_code: str) -> CrosswalkResult:
        result = lookup_crosswalk(tarmed_code)
        if not result.found:
            raise CrosswalkNotFound(
                f"TARMED code {tarmed_code!r} not in the frozen cross-walk table"
            )
        return result

    @app.post("/v1/validate")
    def validate(rule: CombinabilityRule, store: StoreDep) -> RuleValidationResult:
        return validate_rule(rule, store=store)

    return app


app = create_app()


def run() -> None:
    """Console-script entry point: serve the app with uvicorn.

    Host and port come from the env-driven :class:`Settings` (TARIFIQ_API_HOST /
    TARIFIQ_API_PORT), defaulting to the same 0.0.0.0:8070 the Docker CMD passes.
    """

    import uvicorn  # noqa: PLC0415  (lazy: keep module import light for tests)

    settings = get_settings()
    uvicorn.run(
        "tarifiq.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
