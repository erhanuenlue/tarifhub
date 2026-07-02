"""Configuration for the tarifhub MCP server.

The server is a thin, READ-ONLY proxy in front of the deterministic serving API. Its
only configuration is where that API lives and how the MCP transport is exposed.
"""

from __future__ import annotations

import os

import httpx
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sane per-phase defaults: a short connect budget fails fast when serving is unreachable,
# a longer read budget tolerates a slower search query. A single legacy MCP_HTTP_TIMEOUT,
# if set, seeds both phases so existing deployments keep working.
DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = 30.0


class Settings(BaseSettings):
    """Resolved settings (immutable), read from the environment.

    Each field binds to its historical environment variable via ``validation_alias``, so
    the env contract is byte-for-byte identical to the previous ``from_env`` dataclass.
    """

    # ``validate_by_name`` keeps direct field-name construction working alongside the
    # env-alias contract (``validate_by_alias`` stays at its default True), matching the
    # other services so all four construct uniformly.
    model_config = SettingsConfigDict(extra="ignore", frozen=True, validate_by_name=True)

    # Base URL of the FastAPI serving service (system of record for frozen values).
    serving_base_url: str = Field(
        default="http://localhost:8000", validation_alias="SERVING_BASE_URL"
    )
    connect_timeout: float = Field(
        default=DEFAULT_CONNECT_TIMEOUT, validation_alias="MCP_HTTP_CONNECT_TIMEOUT"
    )
    read_timeout: float = Field(
        default=DEFAULT_READ_TIMEOUT, validation_alias="MCP_HTTP_READ_TIMEOUT"
    )
    # "streamable-http" for the container/Service; "stdio" for a local agent.
    transport: str = Field(default="streamable-http", validation_alias="MCP_TRANSPORT")
    host: str = Field(default="0.0.0.0", validation_alias="MCP_HOST")
    port: int = Field(default=8090, validation_alias="MCP_PORT")

    @model_validator(mode="before")
    @classmethod
    def _seed_blanket_timeout(cls, data: object) -> object:
        """Seed both timeout phases from the legacy blanket MCP_HTTP_TIMEOUT.

        A single MCP_HTTP_TIMEOUT (legacy, blanket) seeds both phases when present, but an
        explicit per-phase value always wins for its own phase. A phase is "explicit" when
        the incoming init ``data`` provides it (by field name OR by alias) or its own env
        variable is set, so the blanket only fills a phase that is otherwise unspecified.
        The alias-keyed inputs are written so the field validation that follows picks them
        up exactly as if they had been set in the env.
        """

        blanket = os.environ.get("MCP_HTTP_TIMEOUT")
        if blanket is not None and isinstance(data, dict):
            for field_name, alias in (
                ("connect_timeout", "MCP_HTTP_CONNECT_TIMEOUT"),
                ("read_timeout", "MCP_HTTP_READ_TIMEOUT"),
            ):
                provided = (
                    field_name in data or alias in data or os.environ.get(alias) is not None
                )
                if not provided:
                    data[alias] = blanket
        return data

    @field_validator("serving_base_url", mode="after")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        """Normalise the base URL so a configured trailing slash never doubles a path."""

        return value.rstrip("/")

    @classmethod
    def from_env(cls) -> "Settings":
        """Thin alias for ``Settings()`` kept for callers/tests using the old constructor."""

        return cls()


settings = Settings()


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
