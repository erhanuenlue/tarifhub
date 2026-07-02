"""Runtime configuration (12-factor: everything from the environment).

Settings are read live from the environment on every ``get_settings()`` call so tests
can adjust them with ``monkeypatch.setenv`` without import-time caching. The model is a
``pydantic_settings.BaseSettings``: each field binds to its historical environment
variable via ``validation_alias`` (the names share no common prefix), and
``get_settings()`` builds a FRESH instance every call so per-call live env reads are
preserved. The env contract is byte-for-byte identical to the previous frozen dataclass.
"""

from __future__ import annotations

import os
from typing import ClassVar

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base URL of the L1 TarifCore serving API (system of record for frozen tariff values).
# 8000 is the port serving actually binds (Dockerfile CMD and compose alike).
DEFAULT_SERVING_BASE_URL = "http://localhost:8000"
DEFAULT_REQUEST_TIMEOUT = 10.0
# Offline-first, like the ingestion service: the bundled frozen store is used unless an
# operator explicitly opts into reading live frozen records (TARIFIQ_OFFLINE=0 + a
# reachable SERVING_BASE_URL). This keeps the test suite hermetic with zero config.
DEFAULT_OFFLINE = True
# Bind address for the console-script entry point (main.run). The Docker CMD passes
# uvicorn flags directly and does not read these; the defaults match it byte-for-byte.
DEFAULT_API_HOST = "0.0.0.0"
DEFAULT_API_PORT = 8070

# The exact set of strings that count as "true" for a boolean env var. One definition,
# shared by _env_bool and the Settings.offline validator, so the tolerant parse (a bad
# value never raises) has a single source of truth.
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_bool(name: str, default: bool) -> bool:
    """Tolerant boolean env parse; the reference semantics the ``offline`` validator mirrors.

    ``1/true/yes/on`` (case-insensitive, stripped) is True, an unset variable yields the
    default, and ANY other value (``0``, ``no``, ``garbage``) is False and never raises.
    """

    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


class Settings(BaseSettings):
    """Immutable snapshot of runtime configuration, sourced from the environment."""

    # ``validate_by_name`` keeps direct field-name construction working alongside the
    # env-alias contract (``validate_by_alias`` stays at its default True), matching the
    # other services so all four construct uniformly.
    model_config = SettingsConfigDict(extra="ignore", frozen=True, validate_by_name=True)

    serving_base_url: str = Field(
        default=DEFAULT_SERVING_BASE_URL,
        # Accept TARIFIQ_SERVING_BASE_URL, then the shared SERVING_BASE_URL, then default.
        # The empty-primary fall-through is handled by ``_resolve_serving_base_url`` below,
        # because a bare AliasChoices would pick an empty primary alias over the shared one.
        validation_alias=AliasChoices("TARIFIQ_SERVING_BASE_URL", "SERVING_BASE_URL"),
    )
    request_timeout: float = Field(
        default=DEFAULT_REQUEST_TIMEOUT, validation_alias="TARIFIQ_HTTP_TIMEOUT"
    )
    offline: bool = Field(default=DEFAULT_OFFLINE, validation_alias="TARIFIQ_OFFLINE")
    # Presence of this key is the ONLY switch that could enable a live rule-suggestion
    # model (PRE-FREEZE, human-reviewed). Absent (the test/CI default) => deterministic
    # tables only, and ai_rule_suggest returns a clearly marked placeholder.
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    api_host: str = Field(default=DEFAULT_API_HOST, validation_alias="TARIFIQ_API_HOST")
    api_port: int = Field(default=DEFAULT_API_PORT, validation_alias="TARIFIQ_API_PORT")
    # A fixed constant, not a settings field: no env binding (avoids an accidental APP_NAME knob).
    app_name: ClassVar[str] = "tarifiq"

    @model_validator(mode="before")
    @classmethod
    def _resolve_serving_base_url(cls, data: object) -> object:
        """Restore the ``os.getenv(primary) or os.getenv(shared) or DEFAULT`` fall-through.

        A bare ``AliasChoices`` picks the first PRESENT alias, so an EMPTY primary alias
        would win over a populated shared one. The old dataclass treated an empty primary as
        absent and fell through. Here the or-chain is resolved from ``os.environ`` and
        injected under the primary alias key (mirroring the MCP blanket-seed pattern), unless
        the caller supplied the value directly by field name (which wins outright) or no env
        alias is set at all (leaving any field-name/alias init and the default untouched).
        """

        if not isinstance(data, dict) or "serving_base_url" in data:
            return data
        primary = os.environ.get("TARIFIQ_SERVING_BASE_URL")
        shared = os.environ.get("SERVING_BASE_URL")
        if primary is None and shared is None:
            return data
        data["TARIFIQ_SERVING_BASE_URL"] = primary or shared or DEFAULT_SERVING_BASE_URL
        data.pop("SERVING_BASE_URL", None)
        return data

    @field_validator("serving_base_url", mode="after")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        """Normalise the base URL so a configured trailing slash never doubles a path."""

        return value.rstrip("/")

    @field_validator("offline", mode="before")
    @classmethod
    def _coerce_offline(cls, value: object) -> bool:
        """Replicate ``_env_bool`` rather than pydantic's native bool coercion.

        Native coercion raises on an unrecognised string (e.g. ``garbage``); the env
        contract must not. A real bool (direct construction) passes through unchanged; any
        other value maps through the shared truthy set, so nothing raises.
        """

        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in _TRUTHY

    @field_validator("anthropic_api_key", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        """Coerce an empty string env value to ``None`` (mirrors ``os.getenv(...) or None``)."""

        if value == "":
            return None
        return value


def get_settings() -> Settings:
    """Build a fresh :class:`Settings` from the current environment.

    A new instance is returned on every call (no caching) so a test that mutates the
    environment with ``monkeypatch.setenv`` sees the change on the next read.
    """

    return Settings()
