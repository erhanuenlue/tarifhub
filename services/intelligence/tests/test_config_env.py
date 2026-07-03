"""Env-parsing helper and field-name precedence for ``Settings`` (pure config, no network).

Complements ``test_config.py`` (which locks the ``serving_base_url`` alias fall-through)
by pinning the reference ``_env_bool`` helper the ``offline`` validator mirrors, and the
model-validator branch where a value supplied directly by field name wins over the env
alias. Each test controls its own env vars so nothing leaks between cases.
"""

from __future__ import annotations

import pytest

from tarifiq.config import Settings, _env_bool

_SCRATCH = "TARIFIQ_SCRATCH_BOOL"


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "Yes", "  on  "])
def test_env_bool_recognises_truthy_values(monkeypatch, raw):
    """The truthy set is case-insensitive and whitespace-tolerant."""

    monkeypatch.setenv(_SCRATCH, raw)
    assert _env_bool(_SCRATCH, default=False) is True


@pytest.mark.parametrize("raw", ["0", "no", "off", "garbage", ""])
def test_env_bool_treats_anything_else_as_false_without_raising(monkeypatch, raw):
    """Any unrecognised value is False and never raises (unlike native bool coercion)."""

    monkeypatch.setenv(_SCRATCH, raw)
    assert _env_bool(_SCRATCH, default=True) is False


def test_env_bool_unset_returns_the_default(monkeypatch):
    """An unset variable yields the supplied default, either way."""

    monkeypatch.delenv(_SCRATCH, raising=False)
    assert _env_bool(_SCRATCH, default=True) is True
    assert _env_bool(_SCRATCH, default=False) is False


def test_field_name_serving_base_url_wins_over_env_alias(monkeypatch):
    """A directly supplied ``serving_base_url`` overrides the env alias resolution."""

    monkeypatch.setenv("TARIFIQ_SERVING_BASE_URL", "http://from-env.example")
    assert Settings(serving_base_url="http://direct.example").serving_base_url == (
        "http://direct.example"
    )
