"""Ranked-retrieval evaluation for cross-lingual EAL search.

Measures whether adding the multilingual-e5 ``"query: "`` prefix to user queries fixes
the Block-0 cross-lingual regression (French "hématocrite" ranking the exact record at
3 instead of 1; see docs/evidence/2026-06-11-postgres-serving-pgvector.md §6b).

It runs DIRECTLY against the repo's own modules — the same ``get_embedder`` and
``ServingRepository.search_by_embedding`` the serving API uses — against a live
Postgres+pgvector DB with the multilingual-e5 model installed. This is simpler than
standing up the HTTP server and removes a moving part; the ranking SQL is identical.

In production the search endpoint called ``embed(q)``, which applies the e5 PASSAGE
prefix (``"passage: "``) instead of the model-expected ``"query: "`` prefix — so the
Block-0 baseline is passage-prefixed queries, NOT raw queries. The harness measures that
faithful baseline against the fix:

  --prefix passage   embed each query via embedder.embed()        (faithful Block-0 baseline)
  --prefix query     embed each query via embedder.embed_query()  ("query: " prefix; the fix)

For each labelled query it reports the rank of the expected ``tariff_code`` (the lower
the better, ``—`` if outside top-k), then aggregates MRR@5 and recall@5, and prints a
ready-to-paste Markdown table. Output ordering is deterministic (queries in file order).
(MRR is computed over the top-5 results the harness retrieves, hence MRR@5.)

Usage (from repo root, serving venv has the modules + the 'ai' extra for e5):

    TARIFHUB_DB_URL=postgresql://tarif:tarif@localhost:5432/tarifhub \\
    TARIFHUB_EMBEDDINGS=e5 \\
    uv run --project services/serving python tools/search_eval/eval.py --prefix query

Requires Postgres+pgvector with frozen EAL embeddings and the e5 model; with the offline
stub (16-dim) the harness refuses to run rather than emit meaningless ranks.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

# Reuse the exact serving-path components — no duplicated ranking logic.
from tarifhub_ingest.embeddings.embedder import E5_DIMENSION, get_embedder
from tarifhub_serving.config import get_settings
from tarifhub_serving.db import Database
from tarifhub_serving.repository import ServingRepository

_QUERIES = Path(__file__).resolve().with_name("queries.yaml")
_TOPK = 5


def _load_queries() -> list[dict]:
    data = yaml.safe_load(_QUERIES.read_text(encoding="utf-8"))
    return list(data["queries"])


def _embed(embedder, query: str, *, query_path: bool) -> list[float]:
    """Embed via the query path (e5 'query: ' prefix) or the passage path (baseline).

    ``query_path=True`` uses ``embed_query`` (the fix); ``False`` uses ``embed``, which
    applies the ``"passage: "`` prefix — the faithful Block-0 production baseline.
    """

    return embedder.embed_query(query) if query_path else embedder.embed(query)


def _rank_of(codes: list[str], expected: str) -> int | None:
    """1-based rank of ``expected`` within ``codes``, or ``None`` if absent."""

    for i, code in enumerate(codes, start=1):
        if code == expected:
            return i
    return None


def evaluate(query_path: bool) -> tuple[list[dict], dict]:
    """Run every labelled query and return per-query rows + aggregate metrics.

    ``query_path=True`` embeds via ``embed_query`` (the fix); ``False`` via ``embed``
    (the passage-prefixed faithful Block-0 baseline).
    """

    settings = get_settings()
    db = Database.from_url(settings.db_url)
    if db.dialect != "postgresql":
        raise SystemExit(
            f"eval requires Postgres+pgvector; TARIFHUB_DB_URL points at {db.dialect}. "
            "Start it with `docker compose up -d db` and set TARIFHUB_DB_URL."
        )

    embedder = get_embedder()
    if embedder.dimension != E5_DIMENSION:
        raise SystemExit(
            f"eval requires the {E5_DIMENSION}-dim multilingual-e5 embedder; current "
            f"backend produces {embedder.dimension} dims. Set TARIFHUB_EMBEDDINGS=e5 "
            "and install the 'ai' extra."
        )

    rows: list[dict] = []
    reciprocal_ranks: list[float] = []
    hits_at_5 = 0

    conn = db.connect()
    try:
        repo = ServingRepository(conn, db)
        for q in _load_queries():
            vector = _embed(embedder, q["query"], query_path=query_path)
            records = repo.search_by_embedding(vector, _TOPK)
            codes = [r.tariff_code for r in records]
            rank = _rank_of(codes, str(q["expected_code"]))
            reciprocal_ranks.append(1.0 / rank if rank else 0.0)
            if rank is not None and rank <= _TOPK:
                hits_at_5 += 1
            rows.append(
                {
                    "id": q["id"],
                    "lang": q["lang"],
                    "query": q["query"],
                    "expected_code": str(q["expected_code"]),
                    "rank": rank,
                    "top_codes": codes,
                }
            )
    finally:
        conn.close()

    n = len(rows)
    # Reciprocal rank is computed over the top-5 the harness retrieves (_TOPK=5), so this
    # is MRR@5, not unbounded MRR — a record ranked >5 contributes 0.
    metrics = {
        "n": n,
        "mrr_at_5": (sum(reciprocal_ranks) / n) if n else 0.0,
        "recall_at_5": (hits_at_5 / n) if n else 0.0,
    }
    return rows, metrics


def _markdown(rows: list[dict], metrics: dict, query_path: bool) -> str:
    state = (
        "query (query: prefix — the fix)"
        if query_path
        else "passage (passage: prefix — faithful Block-0 baseline)"
    )
    lines = [
        f"#### Eval run — prefix {state}",
        "",
        "| id | lang | query | expected | rank | top-5 codes |",
        "|----|------|-------|----------|------|-------------|",
    ]
    for r in rows:
        rank = str(r["rank"]) if r["rank"] is not None else "—"
        top = ", ".join(r["top_codes"]) if r["top_codes"] else "—"
        lines.append(
            f"| {r['id']} | {r['lang']} | {r['query']} | {r['expected_code']} | {rank} | {top} |"
        )
    lines += [
        "",
        f"**MRR@5** = {metrics['mrr_at_5']:.3f} · **recall@5** = {metrics['recall_at_5']:.3f} "
        f"(n={metrics['n']})",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix",
        choices=("passage", "query"),
        required=True,
        help=(
            "passage = embed() / 'passage:' prefix (faithful Block-0 baseline); "
            "query = embed_query() / 'query:' prefix (the fix)"
        ),
    )
    args = parser.parse_args(argv)
    query_path = args.prefix == "query"

    rows, metrics = evaluate(query_path=query_path)
    print(_markdown(rows, metrics, query_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
