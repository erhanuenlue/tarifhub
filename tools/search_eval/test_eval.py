"""Offline tests for the search-eval harness: pure helpers + the labelled set.

No DB, no model, no network — only the rank/MRR math and the committed query file.
Run from repo root under the serving venv:

    uv run --project services/serving python -m pytest tools/search_eval/test_eval.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import eval as harness  # noqa: E402


def test_rank_of_found_and_missing():
    codes = ["1369", "6204.6", "1375", "6204.55", "1240.1"]
    assert harness._rank_of(codes, "1375") == 3
    assert harness._rank_of(codes, "1369") == 1
    assert harness._rank_of(codes, "9999") is None


def test_markdown_is_deterministic_and_paste_ready():
    rows = [
        {
            "id": "hematocrite_fr",
            "lang": "fr",
            "query": "hématocrite",
            "expected_code": "1375",
            "rank": 1,
            "top_codes": ["1375", "1369"],
        },
        {
            "id": "missing",
            "lang": "en",
            "query": "x",
            "expected_code": "0000",
            "rank": None,
            "top_codes": [],
        },
    ]
    metrics = {"n": 2, "mrr": 0.5, "recall_at_5": 0.5}
    md = harness._markdown(rows, metrics, prefix_on=True)
    assert "prefix on (query: prefix)" in md
    assert "| hematocrite_fr | fr | hématocrite | 1375 | 1 | 1375, 1369 |" in md
    assert (
        "| missing | en | x | 0000 | — | — |" in md
    )  # missing rank renders as em dash
    assert "**MRR** = 0.500 · **recall@5** = 0.500 (n=2)" in md


def test_labelled_set_covers_four_languages_and_the_headline_case():
    queries = harness._load_queries()
    # Headline Block-0 case must be present and map to EAL 1375.
    headline = [q for q in queries if q["query"] == "hématocrite"]
    assert len(headline) == 1
    assert str(headline[0]["expected_code"]) == "1375"

    langs = {q["lang"] for q in queries}
    assert langs == {"de", "fr", "it", "en"}, "all four languages must be represented"

    # Every entry carries a non-empty `why` rationale.
    assert all(q.get("why") for q in queries)

    # ~12 queries; deterministic count guards accidental edits.
    assert len(queries) == 12
