"""Centralised error handling for the TarifIQ intelligence API (RFC 7807 + structured logging).

This is the SAME problem+json layer the serving API ships in
``tarifhub_serving/errors.py``, replicated here so the rule / cross-walk / validation
surface leaves every failure as one consistent shape: an ``application/problem+json``
body (RFC 7807) with the members ``type``, ``title``, ``status``, ``detail`` and
``instance``. Four handlers are registered on the app:

* the domain base :class:`TarifIQError` -> its mapped status (404 today);
* :class:`fastapi.exceptions.RequestValidationError` -> 422 (declarative input errors);
* Starlette's :class:`HTTPException` -> the same problem+json envelope (so a library- or
  router-raised HTTP error, e.g. an unknown path's 404, is never a bare ``{"detail": ...}``);
* a catch-all :class:`Exception` -> 500 with a generated **correlation id** and a generic
  message: an unexpected store or lookup error becomes a structured 500, never a bare 500
  and never a leaked stack trace or internal string.

The generic plumbing below (``_correlation_id``, ``_problem``, ``_log_problem``, the four
handlers and ``register_exception_handlers``) is intentionally byte-for-byte identical to
the serving and ingestion copies; only the logger name and the service's domain exception
vocabulary differ. The module is replicated, not shared, so each service keeps a
self-contained determinism boundary and no new cross-service Python coupling is introduced.

Determinism note: client-error (4xx) bodies carry no correlation id, so they stay
byte-reproducible; only the 500 path, whose whole purpose is to correlate a caller report
with a server-side log line, embeds the (random) id in the body and the ``X-Correlation-ID``
response header. This module imports no LLM client — the determinism-boundary test enforces it.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_LOG = logging.getLogger("tarifiq.errors")

PROBLEM_CONTENT_TYPE = "application/problem+json"
_PROBLEM_BASE = "https://tarifhub.example/problems"


# --- domain exceptions -------------------------------------------------------


class TarifIQError(Exception):
    """Base for intelligence-layer domain errors, each carrying its HTTP mapping.

    Subclasses set the class attributes ``status``, ``title`` and ``type_`` (an RFC 7807
    problem-type URI); the instance carries the occurrence-specific ``detail`` message and
    an optional ``extra`` mapping rendered as RFC 7807 extension members. A route raises one
    of these instead of constructing an :class:`~fastapi.HTTPException` inline, so the
    status<->problem mapping lives in exactly one place.
    """

    status: int = 500
    title: str = "Intelligence service error"
    type_: str = f"{_PROBLEM_BASE}/intelligence-service-error"

    def __init__(self, detail: str, *, extra: dict[str, Any] | None = None) -> None:
        self.detail = detail
        self.extra = extra
        super().__init__(detail)


class CrosswalkNotFound(TarifIQError):
    """The requested TARMED code is not present in the frozen cross-walk table (404)."""

    status = 404
    title = "Cross-walk entry not found"
    type_ = f"{_PROBLEM_BASE}/crosswalk-not-found"


# --- problem+json plumbing ---------------------------------------------------


def _correlation_id(request: Request) -> str:
    """Honour an inbound ``X-Request-ID`` for trace continuity, else mint a fresh id."""

    return request.headers.get("x-request-id") or uuid.uuid4().hex


def _problem(
    request: Request,
    *,
    status: int,
    title: str,
    detail: str,
    type_: str,
    correlation_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build an RFC 7807 ``application/problem+json`` response for ``request``.

    ``instance`` is the request path (the specific occurrence). ``correlation_id``, when
    given, is added to the body and echoed in the ``X-Correlation-ID`` header so a caller
    can quote it against the server log.
    """

    body: dict[str, Any] = {
        "type": type_,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
    }
    if correlation_id is not None:
        body["correlation_id"] = correlation_id
    if extra:
        body.update(extra)
    headers = {"X-Correlation-ID": correlation_id} if correlation_id else None
    return JSONResponse(
        status_code=status, content=body, media_type=PROBLEM_CONTENT_TYPE, headers=headers
    )


def _log_problem(
    request: Request,
    *,
    status: int,
    correlation_id: str,
    error: str,
    exc_info: BaseException | None = None,
) -> None:
    """Emit one structured log line for a handled failure.

    Fields are both formatted into a greppable ``key=value`` message (visible under any
    logging config) and attached via ``extra`` (typed fields for a structured aggregator).
    Level follows the class of the status: 5xx -> ERROR, anything else -> WARNING.
    """

    fields: dict[str, Any] = {
        "method": request.method,
        "path": request.url.path,
        "status": status,
        "correlation_id": correlation_id,
        "error": error,
    }
    record_hash = getattr(request.state, "record_hash", None)
    if record_hash is not None:
        fields["record_hash"] = record_hash
    message = "request_failed " + " ".join(f"{k}={v}" for k, v in fields.items())
    level = logging.ERROR if status >= 500 else logging.WARNING
    _LOG.log(level, message, extra=fields, exc_info=exc_info)


# --- handlers ----------------------------------------------------------------


async def _handle_domain_error(request: Request, exc: TarifIQError) -> JSONResponse:
    correlation_id = _correlation_id(request)
    _log_problem(
        request, status=exc.status, correlation_id=correlation_id, error=type(exc).__name__
    )
    # Client errors (4xx) stay byte-reproducible: no correlation id in the body.
    body_correlation = correlation_id if exc.status >= 500 else None
    return _problem(
        request,
        status=exc.status,
        title=exc.title,
        detail=exc.detail,
        type_=exc.type_,
        correlation_id=body_correlation,
        extra=exc.extra,
    )


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    correlation_id = _correlation_id(request)
    _log_problem(request, status=422, correlation_id=correlation_id, error="RequestValidationError")
    return _problem(
        request,
        status=422,
        title="Request validation failed",
        detail="One or more request parameters failed validation.",
        type_=f"{_PROBLEM_BASE}/validation-error",
        # Field-level errors as an RFC 7807 extension member (jsonable: ctx may hold
        # non-serialisable objects that FastAPI's own encoder would normalise).
        extra={"errors": jsonable_encoder(exc.errors())},
    )


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Wrap a library/router-raised HTTPException into the same problem+json envelope."""

    correlation_id = _correlation_id(request)
    _log_problem(
        request, status=exc.status_code, correlation_id=correlation_id, error="HTTPException"
    )
    body_correlation = correlation_id if exc.status_code >= 500 else None
    return _problem(
        request,
        status=exc.status_code,
        title=str(exc.detail),
        detail=str(exc.detail),
        type_="about:blank",
        correlation_id=body_correlation,
    )


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: any unhandled error becomes a structured 500, never a bare one.

    The internal detail and full traceback go to the log (keyed by the correlation id);
    the caller receives a generic message plus that id, with no stack trace or internal
    string leaked.
    """

    correlation_id = _correlation_id(request)
    _log_problem(
        request,
        status=500,
        correlation_id=correlation_id,
        error=type(exc).__name__,
        exc_info=exc,
    )
    return _problem(
        request,
        status=500,
        title="Internal server error",
        detail=(
            "An unexpected error occurred while serving the request. "
            f"Quote correlation id {correlation_id} when reporting this issue."
        ),
        type_=f"{_PROBLEM_BASE}/internal-error",
        correlation_id=correlation_id,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register the four problem+json handlers on ``app`` (called once from ``create_app``)."""

    app.add_exception_handler(TarifIQError, _handle_domain_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected_error)
