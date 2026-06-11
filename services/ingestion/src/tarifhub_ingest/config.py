"""Runtime configuration (12-factor: everything from the environment).

Settings are read live from the environment on every ``get_settings()`` call so
tests can adjust them with ``monkeypatch.setenv`` without import-time caching.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

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


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of runtime configuration."""

    db_url: str
    review_threshold: float
    anthropic_api_key: str | None
    sample_dir: str | None
    embeddings_backend: str = DEFAULT_EMBEDDINGS_BACKEND
    ai_model: str = DEFAULT_AI_MODEL
    app_name: str = "tarifhub-ingest"


def get_settings() -> Settings:
    """Build a fresh :class:`Settings` from the current environment."""

    return Settings(
        db_url=os.getenv("TARIFHUB_DB_URL", DEFAULT_DB_URL),
        review_threshold=float(
            os.getenv("TARIFHUB_REVIEW_THRESHOLD", str(DEFAULT_REVIEW_THRESHOLD))
        ),
        # Presence of this key is the ONLY switch that enables the live Claude
        # harmonizer. Absent (the test/CI default) => deterministic rules only.
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        sample_dir=os.getenv("TARIFHUB_SAMPLE_DIR") or None,
        embeddings_backend=os.getenv("TARIFHUB_EMBEDDINGS", DEFAULT_EMBEDDINGS_BACKEND),
        ai_model=os.getenv("TARIFHUB_AI_MODEL", DEFAULT_AI_MODEL),
    )
