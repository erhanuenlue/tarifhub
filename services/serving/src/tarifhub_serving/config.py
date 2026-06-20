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

# Postgres connection-pool bounds (the read path borrows a pooled connection per request
# instead of opening a fresh one each time). Sane single-replica defaults, tuneable per
# deployment via TARIFHUB_DB_POOL_MIN_SIZE / TARIFHUB_DB_POOL_MAX_SIZE. SQLite is not
# pooled (cheap, file-local connections), so these apply only on the Postgres leg.
DEFAULT_DB_POOL_MIN_SIZE = 1
DEFAULT_DB_POOL_MAX_SIZE = 10


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of runtime configuration."""

    db_url: str
    db_pool_min_size: int = DEFAULT_DB_POOL_MIN_SIZE
    db_pool_max_size: int = DEFAULT_DB_POOL_MAX_SIZE
    app_name: str = "tarifhub-serving"


def get_settings() -> Settings:
    """Build a fresh :class:`Settings` from the current environment."""

    return Settings(
        db_url=os.getenv("TARIFHUB_DB_URL", DEFAULT_DB_URL),
        db_pool_min_size=int(os.getenv("TARIFHUB_DB_POOL_MIN_SIZE", str(DEFAULT_DB_POOL_MIN_SIZE))),
        db_pool_max_size=int(os.getenv("TARIFHUB_DB_POOL_MAX_SIZE", str(DEFAULT_DB_POOL_MAX_SIZE))),
    )
