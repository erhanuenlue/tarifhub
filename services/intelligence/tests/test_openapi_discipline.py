"""Every TarifIQ route must document itself: summary + description + a typed model.

The acceptance criterion behind this meta-test ("uniform route discipline", crit-8)
would otherwise erode one undocumented route at a time. A route regresses this suite
the moment it drops its OpenAPI summary/description or falls back to an untyped
``-> dict`` response. Modelled on ``services/serving/tests/test_openapi.py``.

These are pure route-metadata checks, so the app is built with ``create_app()`` and its
routes are inspected directly, without entering the lifespan (no TestClient needed).
"""

from __future__ import annotations

from typing import get_args, get_origin

from fastapi.routing import APIRoute
from pydantic import BaseModel

from tarifiq.main import create_app

app = create_app()


def _api_routes() -> list[APIRoute]:
    return [r for r in app.routes if isinstance(r, APIRoute)]


def _response_model_type(route: APIRoute) -> object:
    """Unwrap ``list[Model]`` to ``Model``; leave a plain model as-is."""

    model = route.response_model
    if get_origin(model) is list:
        (model,) = get_args(model)
    return model


def test_app_has_expected_route_surface():
    paths = sorted({route.path for route in _api_routes()})
    assert paths == [
        "/health",
        "/v1/combinability-check",
        "/v1/crosswalk/{tarmed_code}",
        "/v1/validate",
    ]


def test_every_route_has_summary_and_description():
    missing = [
        f"{route.path} ({'summary' if not route.summary else 'description'})"
        for route in _api_routes()
        if not route.summary or not route.description
    ]
    assert not missing, f"routes missing OpenAPI summary/description: {missing}"


def test_every_route_has_pydantic_response_model():
    """Each route must declare a Pydantic-based response model (fails on ``-> dict``)."""

    bad = [
        route.path
        for route in _api_routes()
        if not (
            isinstance(_response_model_type(route), type)
            and issubclass(_response_model_type(route), BaseModel)
        )
    ]
    assert not bad, f"routes without a Pydantic response model: {bad}"
