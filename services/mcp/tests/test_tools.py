"""Tests for the TarifHub MCP tools.

The serving API is mocked with ``httpx.MockTransport`` so the suite runs fully offline.
The contract under test: each tool returns EXACTLY what the backend returns and never
fabricates or mutates a tariff value.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

import server

# A canonical frozen record as the serving service would return it (camelCase JSON).
FROZEN_RECORD = {
    "id": 1,
    "tariffCode": "00.0010",
    "tariffSystem": "TARDOC",
    "designationDe": "Konsultation, erste 5 Min.",
    "taxPoints": "9.57",
    "priceChf": "10.42",
    "validFrom": "2026-01-01",
    "validTo": None,
    "requiresReview": False,
    "recordHash": "deadbeef",
    "version": 1,
}


def _patch_client(monkeypatch, handler):
    """Point server.build_client at an AsyncClient backed by a MockTransport."""

    def factory():
        return httpx.AsyncClient(
            base_url="http://serving.test", transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(server, "build_client", factory)


def test_get_tariff_returns_backend_record_verbatim(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=FROZEN_RECORD)

    _patch_client(monkeypatch, handler)
    result = asyncio.run(server.get_tariff("TARDOC", "00.0010"))

    # Verbatim passthrough: identical object, nothing added or changed.
    assert result == FROZEN_RECORD
    assert captured["path"] == "/api/v1/tariffs/TARDOC/00.0010"


def test_search_tariffs_passes_query_and_returns_hits_verbatim(monkeypatch):
    hits = [{"rank": 1, "record": FROZEN_RECORD}]
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=hits)

    _patch_client(monkeypatch, handler)
    result = asyncio.run(server.search_tariffs("glucose", system="TARDOC", limit=5))

    assert result == hits
    assert captured["path"] == "/api/v1/search"
    assert captured["params"]["q"] == "glucose"
    assert captured["params"]["system"] == "TARDOC"
    assert captured["params"]["limit"] == "5"


def test_explain_crosswalk_proxies_code(monkeypatch):
    payload = {"code": "00.0010", "records": [FROZEN_RECORD], "explanation": None}
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=payload)

    _patch_client(monkeypatch, handler)
    result = asyncio.run(server.explain_crosswalk("00.0010"))

    assert result == payload
    assert captured["path"] == "/api/v1/explain"
    assert captured["params"]["code"] == "00.0010"


def test_tool_surfaces_error_instead_of_fabricating(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "no frozen record"})

    _patch_client(monkeypatch, handler)
    # A missing record must raise — never a made-up value.
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(server.get_tariff("TARDOC", "99.9999"))
