"""Real e5 semantic-ranking demonstration over recorded multilingual-e5-large vectors.

The default offline suite ranks on the deterministic 16-dim ``HashingEmbedder`` stub, so on
its own it cannot show that the *real* semantic search works. This test closes that gap with
no model download: it ranks a small set of REAL ``intfloat/multilingual-e5-large`` query and
passage vectors with the production cosine ranker and asserts that the French query
"hematocrite" puts the German record EAL 1375 ("Haematokrit, zentrifugiert") top-1, the
cross-lingual match the stub cannot make.

The vectors were recorded once from the cached model by ``fixtures/record_e5_fr_ranking.py``
(see its docstring for provenance). The records are real BAG EAL analyses: 1375 is the
documented FR-ranking ground truth (``docs/evidence/2026-06-11-fr-ranking-eval.md``); the
distractors are real records from the committed EAL fixture. The near-duplicate haematogram
panel 1372.01 is excluded so the curated handful isolates the cross-lingual designation match
(the full 1279-record eval records that, with that panel included, 1375 ranks 2 for the
French query because the panel text also contains "Haematokrit").

Offline and deterministic: no model, no network, no LLM client on the value path. The ranking
recipe (cosine descending, then ``(tariff_system, tariff_code)`` ascending) mirrors
``tarifhub_serving.repository.search_offline``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tarifhub_ingest.embeddings.embedder import E5_DIMENSION, HashingEmbedder
from tarifhub_serving.repository import _cosine_similarity

_FIXTURE = Path(__file__).parent / "fixtures" / "e5_fr_ranking.json"


def _load() -> dict[str, Any]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _rank(query_vector: list[float], passages: list[dict[str, Any]]) -> list[tuple[float, str, str]]:
    """Rank passages exactly as ``search_offline`` does: cosine desc, then (system, code) asc."""
    scored = [
        (_cosine_similarity(query_vector, p["vector"]), p["tariff_system"], p["tariff_code"])
        for p in passages
    ]
    scored.sort(key=lambda s: (-s[0], s[1], s[2]))
    return scored


def test_fixture_is_real_e5_vectors() -> None:
    """The committed fixture is real 1024-dim e5 output, not the 16-dim stub."""
    fx = _load()
    assert fx["model"] == "intfloat/multilingual-e5-large"
    assert fx["dimension"] == E5_DIMENSION
    assert fx["query"]["lang"] == "fr"
    assert len(fx["query"]["vector"]) == E5_DIMENSION
    assert all(len(p["vector"]) == E5_DIMENSION for p in fx["passages"])


def test_real_e5_ranks_french_query_onto_german_record_top1() -> None:
    """Real e5 vectors: the FR query 'hematocrite' ranks EAL 1375 top-1 with a clear margin."""
    fx = _load()
    ranked = _rank(fx["query"]["vector"], fx["passages"])
    assert ranked[0][2] == fx["target_code"] == "1375"
    # A clear separation, not a coin-flip tie: the cross-lingual match is unambiguous.
    assert ranked[0][0] - ranked[1][0] > 0.02


def test_stub_embedder_does_not_make_the_cross_lingual_match() -> None:
    """The 16-dim non-semantic stub does NOT rank 1375 top-1 over the same texts.

    This is the contrast that makes the point: on the default offline embedder the French
    query has no special affinity for the German record, so it is the recorded real-model
    vectors, not the stub, that produce the correct ranking.
    """
    fx = _load()
    stub = HashingEmbedder()
    assert stub.dimension != E5_DIMENSION
    query_vector = stub.embed_query(fx["query"]["text"])
    passages = [
        {
            "vector": stub.embed(p["passage_text"]),
            "tariff_system": p["tariff_system"],
            "tariff_code": p["tariff_code"],
        }
        for p in fx["passages"]
    ]
    ranked = _rank(query_vector, passages)
    assert ranked[0][2] != "1375"
