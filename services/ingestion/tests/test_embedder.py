"""Offline unit tests for the embedder query/passage distinction.

The real multilingual-e5 model is never downloaded here. We test the pure prefix
function directly and exercise the ``_E5Embedder`` wrapper against a tiny fake that
records what string the model was asked to encode — proving query vs passage prefixes
are applied without any network or model weights.
"""

from __future__ import annotations

import math

from tarifhub_ingest.embeddings.embedder import (
    E5_DIMENSION,
    HashingEmbedder,
    _build_e5_embedder,
    _e5_input,
)


def test_e5_input_applies_passage_prefix():
    assert _e5_input("Hämatokrit", kind="passage") == "passage: Hämatokrit"


def test_e5_input_applies_query_prefix():
    assert _e5_input("hématocrite", kind="query") == "query: hématocrite"


def test_e5_input_passage_byte_identical_to_legacy():
    # The stored vectors were indexed with exactly this string; it must not change.
    assert _e5_input("EAL 1375 Hämatokrit, zentrifugiert", kind="passage") == (
        "passage: EAL 1375 Hämatokrit, zentrifugiert"
    )


def test_e5_embedder_query_and_passage_use_distinct_prefixes():
    """The e5 wrapper must send 'query: ' for queries and 'passage: ' for passages.

    A fake SentenceTransformer captures the encoded string instead of loading weights.
    """

    seen: list[str] = []

    class _FakeModel:
        def __init__(self, name: str) -> None:  # noqa: D401 - matches ST signature
            self._name = name

        def encode(self, text, normalize_embeddings=True):
            seen.append(text)
            # Return a deterministic 1024-dim unit-ish vector; values are irrelevant here.
            return [0.0] * E5_DIMENSION

    embedder = _build_e5_embedder(_model_cls=_FakeModel)
    embedder.embed("Hämatokrit, zentrifugiert")
    embedder.embed_query("hématocrite")

    assert seen == ["passage: Hämatokrit, zentrifugiert", "query: hématocrite"]


def test_hashing_embedder_query_is_deterministic_and_matches_passage():
    """Stub: query path is a pure function and (by decision) equals the passage path.

    The offline stub does NOT differentiate query vs passage — it is not semantic and
    differentiating would only add ordering sensitivity to offline tests for no benefit.
    """

    stub = HashingEmbedder()
    q1 = stub.embed_query("blood glucose")
    q2 = stub.embed_query("blood glucose")
    assert q1 == q2  # deterministic
    assert q1 == stub.embed("blood glucose")  # query == passage for the stub
    # unit-normalised
    assert math.isclose(math.sqrt(sum(v * v for v in q1)), 1.0, rel_tol=1e-9)


def test_hashing_embedder_satisfies_embedder_protocol_with_query_method():
    stub = HashingEmbedder()
    assert hasattr(stub, "embed")
    assert hasattr(stub, "embed_query")
