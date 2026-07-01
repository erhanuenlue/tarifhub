"""Runtime configuration (12-factor: everything from the environment).

Mirrors the ingestion ``Settings`` style: a ``pydantic_settings.BaseSettings`` whose
fields bind to explicit environment variables via ``validation_alias`` (the names do
not share a common prefix), read live on every ``get_settings()`` call. Each call
builds a FRESH instance (no import-time caching) so tests can adjust the environment
with ``monkeypatch.setenv`` and see the change on the next read. SQLite is the offline
default; switch to Postgres with a single ``TARIFHUB_DB_URL`` change.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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


class Settings(BaseSettings):
    """Immutable snapshot of runtime configuration, sourced from the environment.

    Field-to-env binding is explicit per field (``validation_alias``) because the
    variable names share no common prefix. ``app_name`` is a fixed constant (a
    ``ClassVar``), not a settings field or deployment knob (matching the ingestion
    ``Settings``).
    """

    # ``validate_by_name`` keeps direct field-name construction working alongside the
    # env-alias contract (``validate_by_alias`` stays at its default True), matching the
    # ingestion ``Settings`` so all four services construct uniformly.
    model_config = SettingsConfigDict(extra="ignore", frozen=True, validate_by_name=True)

    db_url: str = Field(default=DEFAULT_DB_URL, validation_alias="TARIFHUB_DB_URL")
    db_pool_min_size: int = Field(
        default=DEFAULT_DB_POOL_MIN_SIZE, validation_alias="TARIFHUB_DB_POOL_MIN_SIZE"
    )
    db_pool_max_size: int = Field(
        default=DEFAULT_DB_POOL_MAX_SIZE, validation_alias="TARIFHUB_DB_POOL_MAX_SIZE"
    )
    app_name: ClassVar[str] = "tarifhub-serving"


def get_settings() -> Settings:
    """Build a fresh :class:`Settings` from the current environment.

    A new instance is returned on every call (no caching) so a test that mutates the
    environment with ``monkeypatch.setenv`` sees the change on the next read.
    """

    return Settings()
