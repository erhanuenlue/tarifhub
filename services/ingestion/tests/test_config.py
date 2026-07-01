"""Tests for the ingestion service's env-driven ``Settings``.

``config.py`` migrated from a frozen ``@dataclass`` to ``pydantic_settings.BaseSettings``.
The old dataclass accepted field-name construction; the migrated model must preserve that
so BOTH the env-alias contract and direct field-name kwargs resolve. This matters because
``cli.py`` rewraps the settings by field name to apply ``--embeddings`` for a single run:
without field-name population that override was silently dropped and the run stayed on the
offline stub. These tests exercise pure configuration only, with no network, no pipeline
and no API key.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from tarifhub_ingest.config import (
    DEFAULT_DB_URL,
    DEFAULT_EMBEDDINGS_BACKEND,
    Settings,
    get_settings,
)

# Every env var ``Settings`` binds to; cleared per-test so field-name construction is
# observed against genuine defaults rather than an ambient env value.
_INGEST_ENV_VARS = (
    "TARIFHUB_DB_URL",
    "TARIFHUB_REVIEW_THRESHOLD",
    "ANTHROPIC_API_KEY",
    "TARIFHUB_SAMPLE_DIR",
    "TARIFHUB_EMBEDDINGS",
    "TARIFHUB_AI_MODEL",
)


@pytest.fixture()
def clean_env(monkeypatch):
    """Delete every ingestion env var so each test starts from a known-empty baseline."""

    for name in _INGEST_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_field_name_construction_overrides_default(clean_env):
    """A field-name kwarg wins over the default (regression: it was silently dropped)."""

    settings = Settings(db_url="OVR", embeddings_backend="e5")

    assert settings.db_url == "OVR"
    assert settings.embeddings_backend == "e5"


def test_env_alias_still_resolves(clean_env):
    """Enabling field-name population must not break the env-alias contract."""

    clean_env.setenv("TARIFHUB_DB_URL", "postgresql://x/y")

    assert get_settings().db_url == "postgresql://x/y"


def test_defaults_with_no_env(clean_env):
    """With nothing set, fields resolve to their documented defaults."""

    settings = get_settings()

    assert settings.db_url == DEFAULT_DB_URL
    assert settings.embeddings_backend == DEFAULT_EMBEDDINGS_BACKEND


def test_cli_embeddings_rewrap_takes_effect(clean_env):
    """The exact ``cli.py`` rewrap applies ``--embeddings`` for one run.

    Locks the ``type(settings)(**{**settings.__dict__, ...})`` construction from ``cli.py``:
    with field-name population dropped the override silently stayed on the stub.
    """

    settings = get_settings()
    assert settings.embeddings_backend == DEFAULT_EMBEDDINGS_BACKEND

    rewrapped = type(settings)(**{**settings.__dict__, "embeddings_backend": "e5"})

    assert rewrapped.embeddings_backend == "e5"


def test_anthropic_api_key_is_masked_secret(clean_env):
    """The provider key is a ``SecretStr``: its raw value never leaks via repr()/str().

    Storing the key as a plain ``str`` risked surfacing it in a log line, a repr or a
    traceback. ``SecretStr`` masks it everywhere except an explicit ``get_secret_value()``.
    """

    raw = "sk-ant-secret-value-should-never-print-0123456789"
    clean_env.setenv("ANTHROPIC_API_KEY", raw)

    settings = get_settings()

    assert isinstance(settings.anthropic_api_key, SecretStr)
    # Round-trips to the exact value only through the explicit accessor.
    assert settings.anthropic_api_key.get_secret_value() == raw
    # Masked in both representations the key could otherwise leak through.
    assert raw not in repr(settings)
    assert raw not in str(settings)


def test_empty_anthropic_api_key_still_coerces_to_none(clean_env):
    """An empty ``ANTHROPIC_API_KEY`` stays ``None`` (not ``SecretStr('')``) after the switch."""

    clean_env.setenv("ANTHROPIC_API_KEY", "")

    assert get_settings().anthropic_api_key is None
