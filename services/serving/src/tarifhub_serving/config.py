"""Runtime configuration (12-factor: everything from the environment).

Mirrors the ingestion ``Settings`` style: read live from the environment on every
``get_settings()`` call so tests can adjust them with ``monkeypatch.setenv`` without
import-time caching. SQLite is the offline default; switch to Postgres with a single
``TARIFHUB_DB_URL`` change.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# SQLite by default => offline, zero-dependency dev & test store. The serving service
# shares the system of record with ingestion, so the default URL matches.
DEFAULT_DB_URL = "sqlite:///./tarifhub_dev.db"
DEFAULT_LIST_LIMIT = 100
MAX_LIST_LIMIT = 1000


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of runtime configuration."""

    db_url: str
    app_name: str = "tarifhub-serving"


def get_settings() -> Settings:
    """Build a fresh :class:`Settings` from the current environment."""

    return Settings(db_url=os.getenv("TARIFHUB_DB_URL", DEFAULT_DB_URL))
