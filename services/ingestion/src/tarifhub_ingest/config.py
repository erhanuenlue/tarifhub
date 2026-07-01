"""Runtime configuration (12-factor: everything from the environment).

Settings are read live from the environment on every ``get_settings()`` call so
tests can adjust them with ``monkeypatch.setenv`` without import-time caching. The
model is a ``pydantic_settings.BaseSettings``: each field binds to an explicit
environment variable via ``validation_alias`` (the names do not share a common
prefix), and ``get_settings()`` builds a FRESH instance every call so per-call live
env reads are preserved.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# SQLite by default => offline, zero-dependency dev & test store.
# Switch to Postgres with e.g. ``postgresql://tarifhub:tarifhub@localhost:5432/tarifhub``.
DEFAULT_DB_URL = "sqlite:///./tarifhub_dev.db"
DEFAULT_REVIEW_THRESHOLD = 0.85
# "stub" => offline deterministic hashing embedder (default); "e5" => multilingual-e5
# (requires the optional 'ai' extra). Never auto-enabled, so tests stay offline.
DEFAULT_EMBEDDINGS_BACKEND = "stub"
# Claude model for the pre-freeze harmonizer. Exact string, no date suffix; this
# model has no temperature/top_p/top_k knobs. Override with TARIFHUB_AI_MODEL.
DEFAULT_AI_MODEL = "claude-opus-4-8"


class Settings(BaseSettings):
    """Snapshot of runtime configuration, sourced from the environment.

    Field-to-env binding is explicit per field (``validation_alias``) because the
    variable names share no common prefix. An empty string for the optional secrets
    (``ANTHROPIC_API_KEY``, ``TARIFHUB_SAMPLE_DIR``) coerces to ``None``, matching the
    prior ``os.getenv(...) or None`` behaviour byte-for-byte.
    """

    # ``validate_by_name`` keeps direct field-name construction working alongside the
    # env-alias contract (``validate_by_alias`` stays at its default True). The prior frozen
    # dataclass accepted field-name kwargs, and ``cli.py`` rewraps by field name to apply
    # ``--embeddings`` for one run, so dropping them would silently ignore that override.
    model_config = SettingsConfigDict(extra="ignore", frozen=True, validate_by_name=True)

    db_url: str = Field(default=DEFAULT_DB_URL, validation_alias="TARIFHUB_DB_URL")
    review_threshold: float = Field(
        default=DEFAULT_REVIEW_THRESHOLD, validation_alias="TARIFHUB_REVIEW_THRESHOLD"
    )
    # Presence of this key is the ONLY switch that enables the live Claude harmonizer.
    # Absent (the test/CI default) => deterministic rules only.
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    sample_dir: str | None = Field(default=None, validation_alias="TARIFHUB_SAMPLE_DIR")
    embeddings_backend: str = Field(
        default=DEFAULT_EMBEDDINGS_BACKEND, validation_alias="TARIFHUB_EMBEDDINGS"
    )
    ai_model: str = Field(default=DEFAULT_AI_MODEL, validation_alias="TARIFHUB_AI_MODEL")
    # A fixed constant, not a settings field: no env binding (avoids an accidental APP_NAME knob).
    app_name: ClassVar[str] = "tarifhub-ingest"

    @field_validator("anthropic_api_key", "sample_dir", mode="before")
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
