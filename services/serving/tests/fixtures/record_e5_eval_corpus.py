#!/usr/bin/env python3
"""One-time generator for the recorded e5 search-quality eval corpus (NOT run in CI).

Records REAL ``intfloat/multilingual-e5-large`` vectors for the FULL 12-query ranked
retrieval evaluation over the entire 1279-record BAG EAL corpus, so the offline test
``services/serving/tests/test_search_eval_metrics.py`` can recompute the headline
search-quality metrics (recall@5, MRR@5, both prefix runs) from committed vectors with
no model download and no live API. This closes the gap where CI only proved top-1 on a
7-record fixture while the headline figures came from a one-time offline eval.

Run once, locally, with the optional ``ai`` extra installed and the model in the HF cache::

    cd services/ingestion
    TARIFHUB_EMBEDDINGS=e5 uv run --extra ai python \
        ../serving/tests/fixtures/record_e5_eval_corpus.py

It uses the project's own EAL parser and embedder, so the recorded vectors use exactly
the same ``query:`` / ``passage:`` prefixes and L2 normalisation as the live ingest and
search paths, and the passage text mirrors the ingest pipeline verbatim
(``f"{system} {code} {designation_de}"`` with system ``EAL``; ingestion/pipeline.py:115).

Provenance ground truth (documented, must be reproduced exactly by the self-check below):

    baseline (passage-prefix queries)  MRR@5 = 0.681   recall@5 = 0.833   (10/12)
    query-prefix (the fix)             MRR@5 = 0.597   recall@5 = 0.917   (11/12)

(docs/evidence/2026-06-11-fr-ranking-eval.md:47,66). The self-check ranks each query over
all 1279 ROUNDED passage vectors with the same cosine + ``(system, code)`` tie-break as
``ServingRepository.search_offline``, computes both metrics exactly as
``tools/search_eval/eval.py`` does, and refuses to write the fixture unless
``round(metric, 3)`` matches the documented values for BOTH runs. It never adjusts the
vectors or the math to force a match — a mismatch prints the real numbers and aborts.
"""

from __future__ import annotations

import json
import math
import os
from operator import mul
from pathlib import Path

import yaml

_SYSTEM = "EAL"
_ROUND = 8
_TOPK = 5
_EXPECTED_RECORDS = 1279

# Repo-root-relative paths so the recorder works regardless of the CWD it is launched from
# (the documented invocation runs it from services/ingestion).
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[4]
_RAW_XLSX = _REPO_ROOT / "data" / "raw" / "eal" / "analysenliste_2026-01-01.xlsx"
_QUERIES_YAML = _REPO_ROOT / "tools" / "search_eval" / "queries.yaml"
_OUT = _HERE.with_name("e5_eval_corpus.json")

# Documented ground truth (3-decimal renderings of fractions over n=12). The self-check is
# a hard gate against these, not a suggestion.
_DOC = {
    "baseline": {"mrr_at_5": 0.681, "recall_at_5": 0.833},
    "query": {"mrr_at_5": 0.597, "recall_at_5": 0.917},
}


def _passage_text(code: str, designation_de: str) -> str:
    """Exactly what the ingest pipeline embeds (ingestion/pipeline.py:115)."""
    return f"{_SYSTEM} {code} {designation_de}"


def _cosine(a: list[float], b: list[float], b_norm: float) -> float:
    """Cosine similarity mirroring ``repository._cosine_similarity`` (0.0 on a zero vector).

    ``b_norm`` is the precomputed L2 norm of ``b`` so the passage norm is not recomputed
    for every query; the arithmetic is otherwise identical to the serving helper.
    """
    dot = sum(map(mul, a, b))
    a_norm = math.sqrt(sum(x * x for x in a))
    if a_norm == 0.0 or b_norm == 0.0:
        return 0.0
    return dot / (a_norm * b_norm)


def _rank_over_corpus(query_vec: list[float], passages: list[dict], expected: str) -> int | None:
    """1-based rank of ``expected`` over all passages: cosine desc, then (system, code) asc.

    Mirrors ``search_offline``: negate the score so a single ascending sort by
    ``(-score, system, code)`` yields the deterministic order. Returns ``None`` if the
    expected code is absent (cannot happen here, but kept honest).
    """
    scored = [
        (_cosine(query_vec, p["vec"], p["_norm"]), _SYSTEM, p["code"]) for p in passages
    ]
    scored.sort(key=lambda s: (-s[0], s[1], s[2]))
    for rank, (_score, _system, code) in enumerate(scored, start=1):
        if code == expected:
            return rank
    return None


def _metrics(query_vectors: list[list[float]], queries: list[dict], passages: list[dict]):
    """Return ``(ranks, {mrr_at_5, recall_at_5})`` over ``query_vectors`` (one per query).

    ``recall@5 = hits_in_top5 / n`` and ``MRR@5 = mean(1/rank if rank<=5 else 0)`` — the
    exact aggregation of ``tools/search_eval/eval.py:128-135``.
    """
    ranks: list[int | None] = []
    reciprocals: list[float] = []
    hits = 0
    for vec, q in zip(query_vectors, queries):
        rank = _rank_over_corpus(vec, passages, str(q["expected_code"]))
        ranks.append(rank)
        reciprocals.append(1.0 / rank if rank and rank <= _TOPK else 0.0)
        if rank is not None and rank <= _TOPK:
            hits += 1
    n = len(queries)
    return ranks, {"mrr_at_5": sum(reciprocals) / n, "recall_at_5": hits / n}


def _print_ranks(label: str, queries: list[dict], ranks: list[int | None]) -> None:
    print(f"\n{label} per-query ranks (rank of expected code within the full corpus):")
    for q, rank in zip(queries, ranks):
        shown = str(rank) if rank is not None else "miss"
        print(f"  {q['id']:<16} {q['lang']}  expected {q['expected_code']:<8} rank {shown}")


def main() -> None:
    os.environ.setdefault("TARIFHUB_EMBEDDINGS", "e5")
    from tarifhub_ingest.adapters import bag_eal
    from tarifhub_ingest.config import get_settings
    from tarifhub_ingest.embeddings.embedder import E5_DIMENSION, get_embedder

    embedder = get_embedder(get_settings())
    if embedder.dimension != E5_DIMENSION:
        raise SystemExit(
            f"expected the real e5 embedder ({E5_DIMENSION}-dim) but got "
            f"{embedder.dimension}-dim. Install the 'ai' extra and set TARIFHUB_EMBEDDINGS=e5."
        )

    if not _RAW_XLSX.exists():
        raise SystemExit(f"raw EAL export not found: {_RAW_XLSX}")
    raw_rows = bag_eal.parse(_RAW_XLSX)
    if len(raw_rows) != _EXPECTED_RECORDS:
        raise SystemExit(
            f"expected exactly {_EXPECTED_RECORDS} EAL records from {_RAW_XLSX.name}, "
            f"parsed {len(raw_rows)} — refusing to record a corpus of the wrong size."
        )

    queries = yaml.safe_load(_QUERIES_YAML.read_text(encoding="utf-8"))["queries"]
    if len(queries) != 12:
        raise SystemExit(f"expected 12 eval queries, loaded {len(queries)}")

    def rnd(vec) -> list[float]:
        return [round(float(x), _ROUND) for x in vec]

    print(f"embedding {len(raw_rows)} passages + {len(queries)} queries (query + passage prefix)…")
    passages: list[dict] = []
    for row in raw_rows:
        code = row["tariff_code"]
        de = row["designation_de"]
        vec = rnd(embedder.embed(_passage_text(code, de)))
        passages.append({"code": code, "designation_de": de, "vec": vec})

    # Precompute passage norms from the ROUNDED vectors for the self-check ranking (the
    # committed fixture ranking uses these same rounded vectors).
    for p in passages:
        p["_norm"] = math.sqrt(sum(x * x for x in p["vec"]))

    query_records: list[dict] = []
    query_vecs: list[list[float]] = []
    baseline_vecs: list[list[float]] = []
    for q in queries:
        text = q["query"]
        qv = rnd(embedder.embed_query(text))  # "query: " prefix (the fix)
        bv = rnd(embedder.embed(text))  # "passage: " prefix (faithful Block-0 baseline)
        query_vecs.append(qv)
        baseline_vecs.append(bv)
        query_records.append(
            {
                "id": q["id"],
                "lang": q["lang"],
                "text": text,
                "expected_code": str(q["expected_code"]),
                "query_vec": qv,
                "baseline_vec": bv,
            }
        )

    # --- HARD SELF-CHECK GATE ------------------------------------------------
    base_ranks, base_metrics = _metrics(baseline_vecs, queries, passages)
    query_ranks, query_metrics = _metrics(query_vecs, queries, passages)
    _print_ranks("baseline (passage-prefix)", queries, base_ranks)
    print(
        f"  -> MRR@5={base_metrics['mrr_at_5']:.4f} recall@5={base_metrics['recall_at_5']:.4f}"
    )
    _print_ranks("query-prefix (the fix)", queries, query_ranks)
    print(
        f"  -> MRR@5={query_metrics['mrr_at_5']:.4f} recall@5={query_metrics['recall_at_5']:.4f}"
    )

    failures: list[str] = []
    for label, computed in (("baseline", base_metrics), ("query", query_metrics)):
        for key, doc_value in _DOC[label].items():
            got = round(computed[key], 3)
            if got != doc_value:
                failures.append(f"{label}.{key}: computed {got} != documented {doc_value}")
    if failures:
        print("\nSELF-CHECK FAILED — fixture NOT written. Real vs documented:")
        for line in failures:
            print(f"  {line}")
        raise SystemExit(1)

    # --- write only after the gate passes ------------------------------------
    for p in passages:
        del p["_norm"]  # derived at read time; keep the committed fixture minimal
    fixture = {
        "_comment": (
            "REAL intfloat/multilingual-e5-large vectors for the FULL 12-query search-quality "
            "eval over the entire 1279-record BAG EAL corpus, recorded once by "
            "record_e5_eval_corpus.py (see its docstring). Read by test_search_eval_metrics.py "
            "to recompute recall@5 + MRR@5 (both prefix runs) offline, with no model download."
        ),
        "model": "intfloat/multilingual-e5-large",
        "dimension": E5_DIMENSION,
        "rounded_decimals": _ROUND,
        "corpus": "BAG Analysenliste (EAL) 2026-01-01, all frozen records; passage recipe 'EAL {code} {designation_de}'",
        "recorded": "2026-07-03",
        "source_file": _RAW_XLSX.name,
        "record_count": len(passages),
        "queries": query_records,
        "passages": passages,
    }
    _OUT.write_text(
        json.dumps(fixture, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    size_mb = _OUT.stat().st_size / (1024 * 1024)
    print(f"\nSELF-CHECK PASSED. Wrote {_OUT} ({len(passages)} passages, {size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
