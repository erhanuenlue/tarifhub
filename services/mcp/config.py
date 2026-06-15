"""Configuration for the tarifhub MCP server.

The server is a thin, READ-ONLY proxy in front of the deterministic serving API. Its
only configuration is where that API lives and how the MCP transport is exposed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Settings:
    """Resolved settings (immutable)."""

    serving_base_url: str
    request_timeout: float
    transport: str
    host: str
    port: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            # Base URL of the FastAPI serving service (system of record for frozen values).
            serving_base_url=os.environ.get("SERVING_BASE_URL", "http://localhost:8000").rstrip("/"),
            request_timeout=float(os.environ.get("MCP_HTTP_TIMEOUT", "10")),
            # "streamable-http" for the container/Service; "stdio" for a local agent.
            transport=os.environ.get("MCP_TRANSPORT", "streamable-http"),
            host=os.environ.get("MCP_HOST", "0.0.0.0"),
            port=int(os.environ.get("MCP_PORT", "8090")),
        )


settings = Settings.from_env()


def build_client(transport: httpx.BaseTransport | None = None) -> httpx.AsyncClient:
    """Construct an async HTTP client bound to the serving base URL.

    Tests inject an ``httpx.MockTransport`` so no network is touched. In production
    ``transport`` is ``None`` and httpx uses its default transport.
    """

    return httpx.AsyncClient(
        base_url=settings.serving_base_url,
        timeout=settings.request_timeout,
        transport=transport,
    )
