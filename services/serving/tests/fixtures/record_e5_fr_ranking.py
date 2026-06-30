#!/usr/bin/env python3
"""One-time generator for the recorded e5 FR-ranking fixture (NOT run in CI).

Records REAL ``intfloat/multilingual-e5-large`` query and passage vectors so the offline
test ``services/serving/tests/test_e5_ranking.py`` can demonstrate that the real semantic
search ranks the French query "hematocrite" onto the German record EAL 1375
("Haematokrit, zentrifugiert") without downloading the 2 GB model in CI.

Run once, locally, with the optional ``ai`` extra installed and the model in the HF cache::

    cd services/ingestion
    TARIFHUB_EMBEDDINGS=e5 uv run --extra ai python \
        ../serving/tests/fixtures/record_e5_fr_ranking.py

It uses the project's own embedder, so the recorded vectors use exactly the same
``query:`` / ``passage:`` prefixes and L2 normalisation as the live ingest and search
paths, and the passage text mirrors the ingest pipeline verbatim
(``f"{system} {code} {designation_de}"``). The records are real BAG EAL analyses: the
target 1375 is the documented FR-ranking ground truth
(``docs/evidence/2026-06-11-fr-ranking-eval.md``); the distractors are real records from
the committed EAL fixture (codes 1000 to 1037). The near-duplicate haematogram panel
1372.01 is deliberately excluded: the full 1279-record eval (recorded separately) shows
that panel outranks 1375 for the French query because its own text contains "Haematokrit",
so this curated handful isolates the cross-lingual designation match.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

_SYSTEM = "EAL"
_QUERY_LANG = "fr"
_QUERY_TEXT = "hématocrite"
_TARGET_CODE = "1375"
# (code, designation_de) — real BAG EAL records. 1375 is the documented FR ground truth;
# the rest are distinct analyses from the committed EAL fixture (services/ingestion/tests/
# fixtures/eal/analysenliste_2026-01-01_fixture.xlsx).
_RECORDS = [
    ("1375", "Hämatokrit, zentrifugiert"),
    ("1000", "1,25-Dihydroxy-Vitamin D"),
    ("1020", "Alanin-Aminotransferase (ALAT)"),
    ("1021", "Albumin"),
    ("1026", "Aldosteron"),
    ("1027", "Alkalische Phosphatase"),
    ("1032", "Alpha-1-Antitrypsin"),
]
_OUT = Path(__file__).with_name("e5_fr_ranking.json")
_ROUND = 8


def _passage_text(code: str, designation_de: str) -> str:
    """Exactly what the ingest pipeline embeds (ingestion/pipeline.py)."""
    return f"{_SYSTEM} {code} {designation_de}"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return 0.0 if na == 0.0 or nb == 0.0 else dot / (na * nb)


def main() -> None:
    os.environ.setdefault("TARIFHUB_EMBEDDINGS", "e5")
    from tarifhub_ingest.config import get_settings
    from tarifhub_ingest.embeddings.embedder import E5_DIMENSION, get_embedder

    embedder = get_embedder(get_settings())
    if embedder.dimension != E5_DIMENSION:
        raise SystemExit(
            f"expected the real e5 embedder ({E5_DIMENSION}-dim) but got "
            f"{embedder.dimension}-dim. Install the 'ai' extra and set TARIFHUB_EMBEDDINGS=e5."
        )

    def rnd(vec: list[float]) -> list[float]:
        return [round(float(x), _ROUND) for x in vec]

    query_vector = rnd(embedder.embed_query(_QUERY_TEXT))
    passages = []
    for code, de in _RECORDS:
        text = _passage_text(code, de)
        passages.append(
            {
                "tariff_system": _SYSTEM,
                "tariff_code": code,
                "designation_de": de,
                "passage_text": text,
                "vector": rnd(embedder.embed(text)),
            }
        )

    fixture = {
        "_comment": (
            "REAL intfloat/multilingual-e5-large query+passage vectors, recorded once by "
            "record_e5_fr_ranking.py (see its docstring). Read by test_e5_ranking.py to "
            "demonstrate cross-lingual semantic ranking offline, with no model download."
        ),
        "model": "intfloat/multilingual-e5-large",
        "dimension": E5_DIMENSION,
        "rounded_decimals": _ROUND,
        "query": {"lang": _QUERY_LANG, "text": _QUERY_TEXT, "vector": query_vector},
        "target_code": _TARGET_CODE,
        "passages": passages,
    }
    _OUT.write_text(json.dumps(fixture, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # Self-check with the same recipe as serving.search_offline: cosine desc, then
    # (system, code) ascending.
    scored = sorted(
        (
            (_cosine(query_vector, p["vector"]), p["tariff_system"], p["tariff_code"])
            for p in passages
        ),
        key=lambda s: (-s[0], s[1], s[2]),
    )
    print(f"wrote {_OUT} ({len(passages)} passages, {E5_DIMENSION}-dim)")
    print(f"FR query {_QUERY_TEXT!r} ranking:")
    for rank, (score, system, code) in enumerate(scored, 1):
        mark = "  <- target" if code == _TARGET_CODE else ""
        print(f"  {rank}. {system} {code}  cos={score:.4f}{mark}")
    assert scored[0][2] == _TARGET_CODE, "target did not rank top-1 — recurate the set"


if __name__ == "__main__":
    main()
