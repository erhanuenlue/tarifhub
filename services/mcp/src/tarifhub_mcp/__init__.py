"""tarifhub MCP server: read-only tools over the deterministic serving API.

Same ``src/`` layout as the other three services (crit-7 consistency): the package
holds exactly the former flat modules — ``server`` (the FastMCP tools) and ``config``
(env-driven Settings + the HTTP client factory).
"""

__version__ = "0.1.0"
