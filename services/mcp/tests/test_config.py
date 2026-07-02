"""Tests for the MCP server's env-driven ``Settings``.

``config.py`` migrated from a frozen dataclass to ``pydantic_settings.BaseSettings``. These
tests lock the non-trivial precedence rule the migration inherited: a single legacy blanket
``MCP_HTTP_TIMEOUT`` seeds BOTH timeout phases, while an explicit per-phase variable always
wins for its own phase. Every case constructs ``Settings`` from a cleaned environment, so a
stray host variable can never mask a default or a seeded value.

These exercise pure configuration parsing only; no network, no serving app, no API key.
"""

from __future__ import annotations

import pytest

from tarifhub_mcp import config

# Every env var ``Settings`` binds to; cleared before each case so defaults are genuine and
# the blanket-seed precedence is observed against a known-empty baseline.
_MCP_ENV_VARS = (
    "SERVING_BASE_URL",
    "MCP_HTTP_TIMEOUT",
    "MCP_HTTP_CONNECT_TIMEOUT",
    "MCP_HTTP_READ_TIMEOUT",
    "MCP_TRANSPORT",
    "MCP_HOST",
    "MCP_PORT",
)


@pytest.fixture()
def clean_env(monkeypatch):
    """Delete every MCP env var so each test starts from a known-empty baseline."""

    for name in _MCP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_defaults_with_no_env(clean_env):
    """With nothing set, every field resolves to its documented per-phase default."""

    settings = config.Settings()

    assert settings.serving_base_url == "http://localhost:8000"
    assert settings.connect_timeout == 5.0
    assert settings.read_timeout == 30.0
    assert settings.transport == "streamable-http"
    assert settings.host == "0.0.0.0"
    assert settings.port == 8090


def test_blanket_timeout_seeds_both_phases(clean_env):
    """A lone legacy ``MCP_HTTP_TIMEOUT`` seeds both the connect and read budgets."""

    clean_env.setenv("MCP_HTTP_TIMEOUT", "12")

    settings = config.Settings()

    assert settings.connect_timeout == 12.0
    assert settings.read_timeout == 12.0


def test_explicit_per_phase_overrides_blanket(clean_env):
    """When both per-phase vars are set, each wins for its own phase over the blanket."""

    clean_env.setenv("MCP_HTTP_TIMEOUT", "7")
    clean_env.setenv("MCP_HTTP_CONNECT_TIMEOUT", "1")
    clean_env.setenv("MCP_HTTP_READ_TIMEOUT", "2")

    settings = config.Settings()

    assert settings.connect_timeout == 1.0
    assert settings.read_timeout == 2.0


def test_blanket_fills_read_when_only_connect_explicit(clean_env):
    """Mixed case: an explicit connect wins its phase; the blanket still fills read."""

    clean_env.setenv("MCP_HTTP_TIMEOUT", "7")
    clean_env.setenv("MCP_HTTP_CONNECT_TIMEOUT", "1")

    settings = config.Settings()

    assert settings.connect_timeout == 1.0
    assert settings.read_timeout == 7.0


def test_blanket_fills_connect_when_only_read_explicit(clean_env):
    """Symmetric mixed case: an explicit read wins its phase; the blanket fills connect."""

    clean_env.setenv("MCP_HTTP_TIMEOUT", "7")
    clean_env.setenv("MCP_HTTP_READ_TIMEOUT", "2")

    settings = config.Settings()

    assert settings.connect_timeout == 7.0
    assert settings.read_timeout == 2.0


def test_explicit_init_value_overrides_blanket(clean_env):
    """An explicit per-phase INIT value wins over the legacy blanket env timeout.

    Regression: the seed validator checked only ``os.environ`` and injected the blanket
    under the alias key, clobbering an init override keyed by field name. The blanket must
    still fill the read phase, which has no explicit value here.
    """

    clean_env.setenv("MCP_HTTP_TIMEOUT", "7")

    settings = config.Settings(connect_timeout=1)

    assert settings.connect_timeout == 1.0
    assert settings.read_timeout == 7.0


def test_serving_base_url_trailing_slash_stripped(clean_env):
    """A configured trailing slash is normalised away so it never doubles a request path."""

    clean_env.setenv("SERVING_BASE_URL", "http://serving.example/")

    settings = config.Settings()

    assert settings.serving_base_url == "http://serving.example"


def test_from_env_matches_direct_construction(clean_env):
    """``Settings.from_env()`` is a thin alias, equivalent to ``Settings()`` field-for-field."""

    clean_env.setenv("MCP_HTTP_TIMEOUT", "8")
    clean_env.setenv("SERVING_BASE_URL", "http://serving.example/")

    assert config.Settings.from_env() == config.Settings()
