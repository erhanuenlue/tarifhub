"""Configuration for the tarifhub MCP server.

The server is a thin, READ-ONLY proxy in front of the deterministic serving API. Its
only configuration is where that API lives and how the MCP transport is exposed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

# Sane per-phase defaults: a short connect budget fails fast when serving is unreachable,
# a longer read budget tolerates a slower search query. A single legacy MCP_HTTP_TIMEOUT,
# if set, seeds both phases so existing deployments keep working.
DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = 30.0


@dataclass(frozen=True)
class Settings:
    """Resolved settings (immutable)."""

    serving_base_url: str
    connect_timeout: float
    read_timeout: float
    transport: str
    host: str
    port: int

    @classmethod
    def from_env(cls) -> "Settings":
        # A single MCP_HTTP_TIMEOUT (legacy, blanket) seeds both phases when present, and
        # the connect and read budgets can each be overridden independently for tuning.
        blanket = os.environ.get("MCP_HTTP_TIMEOUT")
        connect_default = blanket if blanket is not None else str(DEFAULT_CONNECT_TIMEOUT)
        read_default = blanket if blanket is not None else str(DEFAULT_READ_TIMEOUT)
        return cls(
            # Base URL of the FastAPI serving service (system of record for frozen values).
            serving_base_url=os.environ.get("SERVING_BASE_URL", "http://localhost:8000").rstrip("/"),
            connect_timeout=float(os.environ.get("MCP_HTTP_CONNECT_TIMEOUT", connect_default)),
            read_timeout=float(os.environ.get("MCP_HTTP_READ_TIMEOUT", read_default)),
            # "streamable-http" for the container/Service; "stdio" for a local agent.
            transport=os.environ.get("MCP_TRANSPORT", "streamable-http"),
            host=os.environ.get("MCP_HOST", "0.0.0.0"),
            port=int(os.environ.get("MCP_PORT", "8090")),
        )


settings = Settings.from_env()


def build_client(transport: httpx.BaseTransport | None = None) -> httpx.AsyncClient:
    """Construct an async HTTP client bound to the serving base URL.

    The client carries an explicit ``httpx.Timeout`` with distinct connect and read
    budgets (rather than one blanket float), so a request can never hang indefinitely on a
    stalled connection or a stalled read. Write and pool reuse the connect budget. Tests
    inject an ``httpx.MockTransport`` so no network is touched. In production ``transport``
    is ``None`` and httpx uses its default transport.
    """

    return httpx.AsyncClient(
        base_url=settings.serving_base_url,
        timeout=httpx.Timeout(
            connect=settings.connect_timeout,
            read=settings.read_timeout,
            write=settings.connect_timeout,
            pool=settings.connect_timeout,
        ),
        transport=transport,
    )
