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


def _e5_input(text: str, *, kind: str) -> str:
    """Apply the multilingual-e5 instruction prefix for the given ``kind``.

    multilingual-e5 is trained with an asymmetric scheme: documents to index are
    embedded as ``"passage: ..."`` and search queries as ``"query: ..."``. Indexing a
    passage but embedding the query raw degrades cross-lingual alignment (Block-0:
    a French "hématocrite" query ranked the exact record at 3, not 1). Keeping the
    prefix application in one pure function makes the asymmetry unit-testable without
    downloading the model. ``kind`` is ``"passage"`` or ``"query"``.
    """

    if kind not in ("passage", "query"):
        raise ValueError(f"kind must be 'passage' or 'query', got {kind!r}")
    return f"{kind}: {text}"


@runtime_checkable
class Embedder(Protocol):
    """Port for turning text into a dense vector.

    ``embed`` is the passage/document side (used by ingestion to index frozen records);
    ``embed_query`` is the search side. For the real multilingual-e5 model these differ
    by the instruction prefix (``"passage: "`` vs ``"query: "``).
    """

    @property
    def dimension(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...

    def embed_query(self, text: str) -> list[float]: ...


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

    def embed_query(self, text: str) -> list[float]:
        # The stub is not semantic, so it does NOT differentiate query from passage:
        # a query embeds identically to the same text as a passage. This keeps offline
        # tests free of any order/flake sensitivity that a fabricated prefix would add.
        return self.embed(text)


def _build_e5_embedder(_model_cls=None):
    """Construct the real e5 embedder. Import is guarded; never hit during tests.

    ``_model_cls`` is a test-only injection seam: a fake SentenceTransformer can be
    passed so the query/passage prefix wiring is verifiable without downloading the
    model. Left ``None`` in production, the real ``SentenceTransformer`` is imported
    lazily (its import is the guarded boundary the offline suite must not cross).
    """

    if _model_cls is None:  # pragma: no cover - exercised only when the model is present
        try:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        except ImportError as exc:  # offline / CI default
            raise RuntimeError(
                "multilingual-e5 requires the optional 'ai' extra "
                "(pip install -e '.[ai]'); falling back to the offline stub."
            ) from exc
        _model_cls = SentenceTransformer

    class _E5Embedder:
        def __init__(self) -> None:
            self._model = _model_cls("intfloat/multilingual-e5-large")

        @property
        def dimension(self) -> int:
            return E5_DIMENSION

        def embed(self, text: str) -> list[float]:
            # Passage side: indexed documents. BYTE-IDENTICAL to the original
            # "passage: {text}" string so stored vectors stay valid (no re-embedding).
            vec = self._model.encode(_e5_input(text, kind="passage"), normalize_embeddings=True)
            return [float(x) for x in vec]

        def embed_query(self, text: str) -> list[float]:
            # Query side: e5 expects the "query: " prefix; same normalization.
            vec = self._model.encode(_e5_input(text, kind="query"), normalize_embeddings=True)
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
