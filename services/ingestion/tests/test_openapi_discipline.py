"""Every route must document itself and serve a typed Pydantic model.

The acceptance criterion behind this meta-test (uniform route discipline, arc42 §10)
would otherwise erode one undocumented route at a time: a new endpoint, or a regression
of an existing one back to ``-> dict``, must fail here until it carries an explicit
OpenAPI summary, a description, AND a Pydantic ``response_model``.

The round-trip pins go one step further: the JSON the read routes serve must be exactly
the canonical :class:`TariffRecord` model's JSON-mode dump, so the served surface cannot
drift from the frozen contract. Fully offline: temp SQLite + the bundled samples.
"""

from __future__ import annotations

import typing

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

from tarifhub_ingest.main import app, create_app
from tarifhub_ingest.models.tariff_model import TariffRecord


def _api_routes() -> list[APIRoute]:
    return [r for r in app.routes if isinstance(r, APIRoute)]


def _response_model_class(route: APIRoute) -> object:
    """Return the route's response model, unwrapping ``list[Model]`` to ``Model``."""

    model = route.response_model
    if typing.get_origin(model) is list:
        args = typing.get_args(model)
        model = args[0] if args else model
    return model


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("TARIFHUB_DB_URL", f"sqlite:///{tmp_path / 'openapi_test.db'}")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return TestClient(create_app())


def test_app_has_expected_route_surface():
    paths = sorted({route.path for route in _api_routes()})
    assert paths == [
        "/health",
        "/ingest/sample",
        "/review",
        "/review/queue",
        "/tariffs",
        "/tariffs/{tariff_code}",
    ]


def test_every_route_has_summary_and_description():
    missing = [
        f"{route.path} ({'summary' if not route.summary else 'description'})"
        for route in _api_routes()
        if not route.summary or not route.description
    ]
    assert not missing, f"routes missing OpenAPI summary/description: {missing}"


def test_every_route_response_model_is_pydantic():
    offenders = [
        f"{route.path} -> {route.response_model!r}"
        for route in _api_routes()
        if not (
            isinstance(_response_model_class(route), type)
            and issubclass(_response_model_class(route), BaseModel)
        )
    ]
    assert not offenders, f"routes without a Pydantic response model: {offenders}"


def test_read_routes_serve_canonical_model_json(tmp_path, monkeypatch):
    """GET /tariffs[/{code}] must serve exactly ``TariffRecord.model_dump(mode="json")``."""

    with _client(tmp_path, monkeypatch) as client:
        seeded = client.post("/ingest/sample")
        assert seeded.status_code == 200, seeded.text
        assert seeded.json()["frozen"] > 0

        listing = client.get("/tariffs")
        assert listing.status_code == 200
        items = listing.json()
        assert items, "expected the sample pipeline to seed at least one record"
        for item in items:
            assert TariffRecord.model_validate(item).model_dump(mode="json") == item

        code = items[0]["tariff_code"]
        single = client.get(f"/tariffs/{code}")
        assert single.status_code == 200
        body = single.json()
        assert TariffRecord.model_validate(body).model_dump(mode="json") == body
