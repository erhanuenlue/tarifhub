"""Every route must document itself: an OpenAPI summary AND description per route.

The acceptance criterion behind this meta-test ("OpenAPI summaries on every route",
arc42 §10) would otherwise erode one undocumented route at a time. New routes fail
here until they carry both fields.
"""

from fastapi.routing import APIRoute

from tarifhub_serving.main import app


def _api_routes() -> list[APIRoute]:
    return [r for r in app.routes if isinstance(r, APIRoute)]


def test_app_has_expected_route_surface():
    paths = sorted({route.path for route in _api_routes()})
    assert paths == [
        "/api/v1/explain",
        "/api/v1/fhir/ChargeItemDefinition/{system}/{code}",
        "/api/v1/fhir/CodeSystem/{system}",
        "/api/v1/search",
        "/api/v1/tariffs",
        "/api/v1/tariffs/{system}/{code}",
        "/api/v1/tariffs/{system}/{code}/diff",
        "/health",
    ]


def test_every_route_has_summary_and_description():
    missing = [
        f"{route.path} ({'summary' if not route.summary else 'description'})"
        for route in _api_routes()
        if not route.summary or not route.description
    ]
    assert not missing, f"routes missing OpenAPI summary/description: {missing}"


def test_every_route_has_response_model():
    missing = [route.path for route in _api_routes() if route.response_model is None]
    assert not missing, f"routes missing response_model: {missing}"
