"""Embedding interface + an offline, deterministic stub.

The production embedder is multilingual-e5 (1024-dim) whose vectors are written to
a pgvector column for the FastAPI serving service's semantic search. That model is
an *optional* dependency: importing ``sentence-transformers`` is guarded so the
test suite runs with no model download and no network.

The default :class:`HashingEmbedder` is a pure function of the input text — same
text always yields the same vector — which keeps ingestion reproducible offline.
Embeddings are a search/discovery aid only; they never influence a billing value.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable

from tarifhub_ingest.config import Settings, get_settings

# Production vector width (intfloat/multilingual-e5-large). The offline stub uses a
# smaller width on purpose — it is dev-only and stored as JSON in SQLite, while the
# Postgres schema declares vector(1024) for the real model.
E5_DIMENSION = 1024
STUB_DIMENSION = 16


@runtime_checkable
class Embedder(Protocol):
    """Port for turning text into a dense vector."""

    @property
    def dimension(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Deterministic, dependency-free embedder for offline dev and tests.

    Not semantically meaningful — it only guarantees stability and the right shape
    so the pipeline and storage can be exercised without the real model.
    """

    def __init__(self, dimension: int = STUB_DIMENSION) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> list[float]:
        normalized = " ".join((text or "").split()).lower()
        raw: list[float] = []
        for i in range(self._dimension):
            digest = hashlib.sha256(f"{i}:{normalized}".encode("utf-8")).digest()
            # Map the first 8 bytes to a float in [-1, 1].
            value = int.from_bytes(digest[:8], "big") / 2**64
            raw.append(value * 2.0 - 1.0)
        norm = math.sqrt(sum(v * v for v in raw)) or 1.0
        return [v / norm for v in raw]


def _build_e5_embedder():  # pragma: no cover - exercised only when the model is present
    """Construct the real e5 embedder. Import is guarded; never hit during tests."""

    try:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
    except ImportError as exc:  # offline / CI default
        raise RuntimeError(
            "multilingual-e5 requires the optional 'ai' extra "
            "(pip install -e '.[ai]'); falling back to the offline stub."
        ) from exc

    class _E5Embedder:
        def __init__(self) -> None:
            self._model = SentenceTransformer("intfloat/multilingual-e5-large")

        @property
        def dimension(self) -> int:
            return E5_DIMENSION

        def embed(self, text: str) -> list[float]:
            # e5 expects a "query:"/"passage:" prefix; we index passages.
            vec = self._model.encode(f"passage: {text}", normalize_embeddings=True)
            return [float(x) for x in vec]

    return _E5Embedder()


def get_embedder(settings: Settings | None = None) -> Embedder:
    """Return the configured embedder.

    Default is the offline :class:`HashingEmbedder`. Set ``TARIFHUB_EMBEDDINGS=e5``
    *and* install the optional ``ai`` extra to use the real multilingual-e5 model.
    Any failure to load the real model degrades gracefully to the stub.
    """

    settings = settings or get_settings()
    if settings.embeddings_backend == "e5":
        try:
            return _build_e5_embedder()
        except RuntimeError:
            return HashingEmbedder()
    return HashingEmbedder()
