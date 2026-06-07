"""Runtime configuration (12-factor: everything from the environment).

Settings are read live from the environment on every ``get_settings()`` call so tests
can adjust them with ``monkeypatch.setenv`` without import-time caching.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Base URL of the L1 TarifCore serving API (system of record for frozen tariff values).
DEFAULT_SERVING_BASE_URL = "http://localhost:8080"
DEFAULT_REQUEST_TIMEOUT = 10.0
# Offline-first, like the ingestion service: the bundled frozen store is used unless an
# operator explicitly opts into reading live frozen records (TARIFIQ_OFFLINE=0 + a
# reachable SERVING_BASE_URL). This keeps the test suite hermetic with zero config.
DEFAULT_OFFLINE = True


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of runtime configuration."""

    serving_base_url: str
    request_timeout: float
    offline: bool
    anthropic_api_key: str | None
    app_name: str = "tarifiq"


def get_settings() -> Settings:
    """Build a fresh :class:`Settings` from the current environment."""

    return Settings(
        # Accept TARIFIQ_SERVING_BASE_URL, then the shared SERVING_BASE_URL, then default.
        serving_base_url=(
            os.getenv("TARIFIQ_SERVING_BASE_URL")
            or os.getenv("SERVING_BASE_URL")
            or DEFAULT_SERVING_BASE_URL
        ).rstrip("/"),
        request_timeout=float(os.getenv("TARIFIQ_HTTP_TIMEOUT", str(DEFAULT_REQUEST_TIMEOUT))),
        offline=_env_bool("TARIFIQ_OFFLINE", DEFAULT_OFFLINE),
        # Presence of this key is the ONLY switch that could enable a live rule-suggestion
        # model (PRE-FREEZE, human-reviewed). Absent (the test/CI default) => deterministic
        # tables only, and ai_rule_suggest returns a clearly marked placeholder.
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
    )
