"""Tests for the intelligence (tarifiq) service's env-driven ``Settings``.

Locks the ``serving_base_url`` resolution, which must reproduce the previous
``os.getenv(primary) or os.getenv(shared) or DEFAULT`` fall-through: an EMPTY primary
alias falls through to the shared ``SERVING_BASE_URL``, then to the default. A naive
``AliasChoices`` picks the first PRESENT alias even when it is the empty string, which
diverges, so the fall-through is restored explicitly. Also locks field-name construction
(field-name population must survive the dataclass -> BaseSettings migration). Pure
configuration only: no network, no serving app, no API key.
"""

from __future__ import annotations

import pytest

from tarifiq.config import DEFAULT_SERVING_BASE_URL, Settings

# Every env var the resolution reads; cleared per-test so the fall-through is observed
# against a known-empty baseline rather than an ambient shared alias.
_INTEL_ENV_VARS = (
    "TARIFIQ_SERVING_BASE_URL",
    "SERVING_BASE_URL",
    "TARIFIQ_HTTP_TIMEOUT",
    "TARIFIQ_OFFLINE",
    "ANTHROPIC_API_KEY",
)


@pytest.fixture()
def clean_env(monkeypatch):
    """Delete every intelligence env var so each test starts from a known-empty baseline."""

    for name in _INTEL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_empty_primary_falls_through_to_shared(clean_env):
    """An empty primary alias falls through to the shared ``SERVING_BASE_URL``."""

    clean_env.setenv("TARIFIQ_SERVING_BASE_URL", "")
    clean_env.setenv("SERVING_BASE_URL", "http://shared.example")

    assert Settings().serving_base_url == "http://shared.example"


def test_empty_primary_and_unset_shared_falls_through_to_default(clean_env):
    """An empty primary with no shared alias falls through to the default."""

    clean_env.setenv("TARIFIQ_SERVING_BASE_URL", "")

    assert Settings().serving_base_url == DEFAULT_SERVING_BASE_URL


def test_present_primary_wins(clean_env):
    """A present primary alias wins over the shared alias and the default."""

    clean_env.setenv("TARIFIQ_SERVING_BASE_URL", "http://primary.example")
    clean_env.setenv("SERVING_BASE_URL", "http://shared.example")

    assert Settings().serving_base_url == "http://primary.example"


def test_field_name_construction_overrides_default(clean_env):
    """A field-name kwarg wins over the default (regression: it was silently dropped)."""

    assert Settings(offline=False).offline is False
