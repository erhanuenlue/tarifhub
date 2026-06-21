"""True integration tests: each MCP tool proven against the REAL serving API.

Unlike ``test_tools.py`` (which mocks HTTP and would pass even if serving never implemented
the endpoints), these run the genuine serving FastAPI app over a seeded temp SQLite DB and
reach it through ``httpx.ASGITransport`` — fully offline. The contract under test: every
tool returns serving's frozen records VERBATIM and surfaces errors instead of fabricating.

Fixtures (``wire_mcp_to_serving``, ``serving_client``, the seed helpers) live in
``conftest.py``.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

import server
from conftest import (
    MULTI_VERSION_KEY,
    SEARCH_KEY,
    SEARCH_QUERY,
    UNKNOWN_CODE,
)


@pytest.mark.usefixtures("wire_mcp_to_serving")
def test_integration_get_tariff_returns_real_frozen_record(serving_client):
    """get_tariff returns exactly what a direct GET to the real serving app returns."""

    system, code = MULTI_VERSION_KEY

    tool_result = asyncio.run(server.get_tariff(system, code))

    async def _direct() -> dict:
        resp = await serving_client.get(f"/api/v1/tariffs/{system}/{code}")
        resp.raise_for_status()
        return resp.json()

    served = asyncio.run(_direct())

    # Verbatim passthrough against REAL data — byte-for-byte identical, nothing added.
    assert tool_result == served
    # Real frozen record, not mock data: integrity hash is present...
    assert tool_result["record_hash"]
    assert isinstance(tool_result["record_hash"], str)
    # ...and Decimal money/points serialise as scale-canonical strings (10.10 -> "10.1").
    assert tool_result["tax_points"] == "10.1"
    # get_latest returns the highest version of the key.
    assert tool_result["version"] == 2


@pytest.mark.usefixtures("wire_mcp_to_serving")
def test_integration_search_tariffs_returns_ranked_hits():
    """search_tariffs returns >=1 ranked frozen hit, deterministically ordered."""

    system, code = SEARCH_KEY

    hits = asyncio.run(server.search_tariffs(SEARCH_QUERY, limit=5))

    assert len(hits) >= 1
    # Each hit matches the serving SearchHit shape: {rank, record} (no value is computed).
    for hit in hits:
        assert set(hit.keys()) == {"rank", "record"}
        assert isinstance(hit["rank"], int)
        # The wrapped payload is a real frozen record.
        assert hit["record"]["record_hash"]
    # The seeded key must surface for a query matching its designation.
    matched = [h["record"] for h in hits if h["record"]["tariff_code"] == code]
    assert matched, f"expected {code} among hits for query {SEARCH_QUERY!r}"
    assert matched[0]["tariff_system"] == system

    # Deterministic ordering: two identical queries return identical ranked results.
    hits_again = asyncio.run(server.search_tariffs(SEARCH_QUERY, limit=5))
    assert hits_again == hits


@pytest.mark.usefixtures("wire_mcp_to_serving")
def test_integration_search_tariffs_system_filter_changes_results():
    """The tool's `system` argument is honoured end to end and genuinely narrows results.

    Previously serving ignored the forwarded `system` parameter, so the advertised filter
    was a silent no-op. With serving reading it, a system-filtered call returns only that
    system's frozen records, a strict subset of the unfiltered ranking.
    """

    unfiltered = asyncio.run(server.search_tariffs(SEARCH_QUERY, limit=10))
    # The seed spans both systems, so an unfiltered search returns TARDOC and EAL hits.
    assert {h["record"]["tariff_system"] for h in unfiltered} == {"TARDOC", "EAL"}

    eal_only = asyncio.run(server.search_tariffs(SEARCH_QUERY, system="EAL", limit=10))
    assert eal_only, "a system-filtered tool call must still return ranked hits"
    assert {h["record"]["tariff_system"] for h in eal_only} == {"EAL"}
    # The filter is not a no-op: it strictly narrows the result set.
    assert len(eal_only) < len(unfiltered)


@pytest.mark.usefixtures("wire_mcp_to_serving")
def test_integration_explain_crosswalk_returns_deterministic_explanation(serving_client):
    """explain_crosswalk returns {code, records, explanation}; records are all versions."""

    system, code = MULTI_VERSION_KEY

    result = asyncio.run(server.explain_crosswalk(code))

    assert set(result.keys()) == {"code", "records", "explanation"}
    assert result["code"] == code
    # The explanation is rule-generated, labelled with its deterministic provenance.
    assert result["explanation"].startswith("[deterministic]")

    # ``records`` must contain ALL versions of the key, verbatim. Cross-check each against
    # a direct point-in-time GET of that exact version on the real serving app.
    versions = sorted(
        r["version"] for r in result["records"] if r["tariff_code"] == code
    )
    assert versions == [1, 2]

    # Verbatim check: the explain records equal the records served elsewhere for the key.
    async def _direct_all() -> list[dict]:
        resp = await serving_client.get("/api/v1/explain", params={"code": code})
        resp.raise_for_status()
        return resp.json()["records"]

    served_records = asyncio.run(_direct_all())
    explain_for_key = [r for r in result["records"] if r["tariff_code"] == code]
    served_for_key = [r for r in served_records if r["tariff_code"] == code]
    assert explain_for_key == served_for_key


@pytest.mark.usefixtures("wire_mcp_to_serving")
def test_integration_unknown_code_surfaces_404():
    """An unknown code raises HTTPStatusError — the tool never fabricates a result."""

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        asyncio.run(server.explain_crosswalk(UNKNOWN_CODE))
    assert exc_info.value.response.status_code == 404

    # get_tariff for an unknown key fails closed the same way.
    with pytest.raises(httpx.HTTPStatusError) as exc_info2:
        asyncio.run(server.get_tariff("TARDOC", UNKNOWN_CODE))
    assert exc_info2.value.response.status_code == 404
