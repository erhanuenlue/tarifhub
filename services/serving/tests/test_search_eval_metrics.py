"""Offline reproduction of the headline search-quality metrics from recorded e5 vectors.

The headline figures (real-e5 recall@5 0.833 -> 0.917 when the ``"query: "`` prefix is
applied) came from a one-time offline eval against live Postgres+pgvector; CI on its own
only proved top-1 on a 7-record fixture. This test closes that gap: it recomputes recall@5
and MRR@5 for BOTH prefix runs from committed REAL ``intfloat/multilingual-e5-large``
vectors over the full 1279-record BAG EAL corpus, with no model, no network and no live API.

The vectors were recorded once from the cached model by
``fixtures/record_e5_eval_corpus.py`` (see its docstring + hard self-check gate). The ranking
recipe (cosine descending, then ``(tariff_system, tariff_code)`` ascending) and the metric
aggregation (recall@5 = hits_in_top5 / n, MRR@5 = mean(1/rank if rank<=5 else 0)) mirror
``tarifhub_serving.repository.search_offline`` and ``tools/search_eval/eval.py`` exactly, so a
regression in either the vectors or the documented figures fails here.

Stdlib only; the whole file ranks 24 query vectors over 1279 passages in pure Python in a
couple of seconds by precomputing passage norms once.
"""

from __future__ import annotations

import json
import math
from operator import mul
from pathlib import Path
from typing import Any

_FIXTURE = Path(__file__).parent / "fixtures" / "e5_eval_corpus.json"
_SYSTEM = "EAL"
_DIMENSION = 1024
_TOPK = 5


def _load() -> dict[str, Any]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _norm(vec: list[float]) -> float:
    return math.sqrt(sum(x * x for x in vec))


def _cosine(a: list[float], a_norm: float, b: list[float], b_norm: float) -> float:
    """Cosine similarity mirroring ``repository._cosine_similarity`` (0.0 on a zero vector).

    Both norms are passed in precomputed; the arithmetic is otherwise identical to the
    serving helper (``dot / (norm_a * norm_b)``).
    """
    if a_norm == 0.0 or b_norm == 0.0:
        return 0.0
    return sum(map(mul, a, b)) / (a_norm * b_norm)


def _passages_with_norms(fx: dict[str, Any]) -> list[tuple[str, list[float], float]]:
    """``(code, vec, norm)`` per passage — norms precomputed once for all queries."""
    return [(p["code"], p["vec"], _norm(p["vec"])) for p in fx["passages"]]


def _ranked_codes(
    query_vec: list[float],
    passages: list[tuple[str, list[float], float]],
) -> list[str]:
    """Codes ranked by cosine desc, then ``(system, code)`` asc — the search_offline order."""
    q_norm = _norm(query_vec)
    scored = [
        (_cosine(query_vec, q_norm, vec, p_norm), _SYSTEM, code)
        for code, vec, p_norm in passages
    ]
    scored.sort(key=lambda s: (-s[0], s[1], s[2]))
    return [code for _score, _system, code in scored]


def _rank_over_corpus(
    query_vec: list[float],
    passages: list[tuple[str, list[float], float]],
    expected: str,
) -> int | None:
    """1-based rank of ``expected`` in the search_offline order (``None`` if absent)."""
    codes = _ranked_codes(query_vec, passages)
    return codes.index(expected) + 1 if expected in codes else None


def _metrics(fx: dict[str, Any], vec_key: str) -> tuple[dict[str, int | None], dict[str, float]]:
    """Rank every query by its ``vec_key`` vector and aggregate recall@5 + MRR@5.

    ``vec_key`` is ``"query_vec"`` (the ``"query: "`` prefix, the fix) or ``"baseline_vec"``
    (the ``"passage: "`` prefix, the faithful Block-0 baseline).
    """
    passages = _passages_with_norms(fx)
    ranks: dict[str, int | None] = {}
    reciprocals: list[float] = []
    hits = 0
    for q in fx["queries"]:
        rank = _rank_over_corpus(q[vec_key], passages, q["expected_code"])
        ranks[q["id"]] = rank
        reciprocals.append(1.0 / rank if rank and rank <= _TOPK else 0.0)
        if rank is not None and rank <= _TOPK:
            hits += 1
    n = len(fx["queries"])
    return ranks, {"mrr_at_5": sum(reciprocals) / n, "recall_at_5": hits / n}


# --------------------------------------------------------------------------- #
# Provenance guards
# --------------------------------------------------------------------------- #


def test_fixture_provenance_header() -> None:
    """The committed fixture is real 1024-dim e5 output over the full 1279-record corpus."""
    fx = _load()
    assert fx["model"] == "intfloat/multilingual-e5-large"
    assert fx["dimension"] == _DIMENSION
    assert fx["rounded_decimals"] == 8
    assert fx["record_count"] == 1279
    assert len(fx["passages"]) == 1279
    assert all(len(p["vec"]) == _DIMENSION for p in fx["passages"])


def test_fixture_has_twelve_multilingual_queries() -> None:
    """Exactly 12 queries, each carrying both prefix vectors, spanning fr/de/it/en."""
    fx = _load()
    queries = fx["queries"]
    assert len(queries) == 12
    assert {q["lang"] for q in queries} == {"fr", "de", "it", "en"}
    for q in queries:
        assert len(q["query_vec"]) == _DIMENSION
        assert len(q["baseline_vec"]) == _DIMENSION


def test_passage_text_matches_the_ingest_embedding_recipe() -> None:
    """Provenance guard: known rows carry the DE designation the ingest recipe embedded.

    The ingest pipeline embeds ``f"EAL {code} {designation_de}"``; a couple of known rows
    pin that the recorded corpus is the real BAG EAL content, so the recipe a maintainer
    would reconstruct matches what was vectorised.
    """
    fx = _load()
    by_code = {p["code"]: p["designation_de"] for p in fx["passages"]}
    assert by_code["1375"] == "Hämatokrit, zentrifugiert"
    assert by_code["1000"] == "1,25-Dihydroxy-Vitamin D"
    assert f"EAL 1375 {by_code['1375']}" == "EAL 1375 Hämatokrit, zentrifugiert"


# --------------------------------------------------------------------------- #
# Metric reproduction — the point of the whole fixture
# --------------------------------------------------------------------------- #


def test_baseline_passage_prefix_metrics_reproduce_documented_figures() -> None:
    """Passage-prefix (Block-0 baseline): recall@5 = 0.833, MRR@5 = 0.681 (n=12)."""
    fx = _load()
    _ranks, metrics = _metrics(fx, "baseline_vec")
    assert round(metrics["recall_at_5"], 3) == 0.833
    assert round(metrics["mrr_at_5"], 3) == 0.681


def test_query_prefix_metrics_reproduce_documented_figures() -> None:
    """Query-prefix (the fix): recall@5 = 0.917, MRR@5 = 0.597 (n=12)."""
    fx = _load()
    _ranks, metrics = _metrics(fx, "query_vec")
    assert round(metrics["recall_at_5"], 3) == 0.917
    assert round(metrics["mrr_at_5"], 3) == 0.597


def test_headline_fr_hematocrite_ranks_1375_second_behind_the_near_duplicate() -> None:
    """Documented headline behaviour: query-prefix FR 'hématocrite' puts EAL 1375 at rank 2.

    The near-duplicate haematogram panel 1372.01 outranks it because that panel's own text
    contains "Hämatokrit" (docs/arc42/10-quality-requirements.md:407-412). This pins the one
    rank the whole trade-off narrative turns on: 1372.01 at rank 1, the exact record 1375 at 2.
    """
    fx = _load()
    passages = _passages_with_norms(fx)
    fr = next(q for q in fx["queries"] if q["id"] == "hematocrite_fr")
    ranked = _ranked_codes(fr["query_vec"], passages)
    assert ranked[0] == "1372.01"
    assert ranked[1] == "1375"
