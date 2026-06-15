"""tarifhub MCP server — read-only tools over the deterministic serving API.

Exposes tarifhub to AI agents through the Model Context Protocol. Every tool is a thin
proxy to the FastAPI serving service and returns its frozen records VERBATIM. This
server has no database, no model, and no arithmetic: it cannot and must not compute,
round, or invent a tariff value. If serving cannot answer, the tool surfaces the error
rather than fabricating a result.

Tools:
    search_tariffs(query, system?, limit?)  -> GET  /api/v1/search
    get_tariff(system, code)                 -> GET  /api/v1/tariffs/{system}/{code}
    explain_crosswalk(code)                  -> GET  /api/v1/explain   (frozen records +
                                                deterministic, record-grounded explanation)
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from config import build_client, settings

mcp = FastMCP("tarifhub-mcp")


async def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    """GET ``path`` on the serving API and return the parsed JSON verbatim.

    Raises ``httpx.HTTPStatusError`` on a non-2xx response so the failure is visible to
    the agent — we never substitute a made-up value for an error.
    """

    async with build_client() as client:
        resp = await client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def search_tariffs(query: str, system: str | None = None, limit: int = 10) -> list[dict]:
    """Semantic search over frozen tariff records.

    Args:
        query: free-text query (e.g. "blood glucose measurement").
        system: optional tariff system filter (e.g. "TARDOC", "TARMED").
        limit: maximum number of ranked hits.

    Returns the serving service's ranked hits unchanged (each wraps a frozen record).
    """

    params: dict[str, Any] = {"q": query, "limit": limit}
    if system:
        params["system"] = system
    return await _get("/api/v1/search", params)


@mcp.tool()
async def get_tariff(system: str, code: str) -> dict:
    """Fetch a single frozen tariff record by system and code.

    Args:
        system: tariff system (e.g. "TARDOC", "TARMED").
        code: tariff code (e.g. "00.0010").

    Returns the frozen record exactly as served (values are authoritative, unaltered).
    """

    return await _get(f"/api/v1/tariffs/{system}/{code}")


@mcp.tool()
async def explain_crosswalk(code: str) -> dict:
    """Explain a position and its TARMED<->TARDOC cross-walk.

    Args:
        code: a tariff code (inherently non-identifying — no patient data is involved).

    Proxies to the deterministic explanation endpoint, which grounds its natural-language
    text only in frozen records, with no model on the serve path. The tool returns whatever
    serving returns and adds nothing.
    """

    return await _get("/api/v1/explain", {"code": code})


def main() -> None:
    """Run the MCP server with the configured transport."""

    # Host/port apply to the HTTP transports; harmless for stdio.
    mcp.settings.host = settings.host
    mcp.settings.port = settings.port
    mcp.run(transport=settings.transport)


if __name__ == "__main__":
    main()
