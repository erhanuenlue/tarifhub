"""Offline tests for BM25, dense and RRF hybrid ranking over one passage corpus.

Dense ranking uses a stand-in embedder with fixed vectors; the real multilingual-e5 model is
used only in the recorded evaluation run.

    uv run --project services/ingestion --frozen --offline --extra ai --extra dev \\
        python -m pytest tools/commentary_rag -q
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import corpus
import retrieval

JUL = "2026-07-01"
JAN = "2026-01-01"


def passage(passage_id: str, text: str, edition: str = JUL) -> corpus.Passage:
    return corpus.Passage(
        passage_id=passage_id, edition=edition, document_sha256="0" * 64, source_url=None,
        page=1, page_label=None, section=None, section_title=None, text=text,
        text_sha256="0" * 64, tokens=len(text.split()), split="whole",
    )


class FixedEmbedder:
    """Stand-in for the e5 embedder: a fixed vector per passage text and for every query."""

    def __init__(self, vectors: dict[str, list[float]], query: list[float]) -> None:
        self._vectors = vectors
        self._query = query
        self.embedded: list[str] = []

    @property
    def dimension(self) -> int:
        """Width of the fixed vectors."""
        return len(self._query)

    def embed(self, text: str) -> list[float]:
        """The fixed passage vector for ``text``."""
        self.embedded.append(text)
        return self._vectors[text]

    def embed_query(self, text: str) -> list[float]:
        """The one fixed query vector."""
        return self._query


def test_bm25_matches_a_hand_computed_score_and_breaks_ties_by_passage_id():
    # N = 2 passages of 2 terms each; "taxe" occurs once in one passage:
    # idf = ln(1 + (2 - 1 + 0.5) / (1 + 0.5)) = ln 2; tf part = 1 * 2.2 / (1 + 1.2 * 1) = 1.
    retriever = retrieval.Retriever([passage("b", "Taxe sinkt"), passage("a", "Tarif sinkt")])

    hits = retriever.rank("Taxe", method="bm25", editions=[JUL])

    assert [h.passage_id for h in hits] == ["b", "a"]
    assert hits[0].score == pytest.approx(math.log(2))
    assert hits[1].score == 0.0
    # Equal scores: ordered by passage_id, whatever the input order.
    for order in (["c", "a", "b"], ["b", "c", "a"]):
        tied = retrieval.Retriever([passage(pid, "gleich") for pid in order])
        assert [h.passage_id for h in tied.rank("gleich", method="bm25", editions=[JUL])] == [
            "a", "b", "c"
        ]


def test_hybrid_is_reciprocal_rank_fusion_of_the_bm25_and_dense_rankings():
    # BM25 orders x > y > z by term frequency; the stand-in vectors order y > z > x.
    texts = {"x": "q q q f", "y": "q q f f", "z": "q f f f"}
    vectors = {texts["x"]: [0.0, 1.0], texts["y"]: [1.0, 0.0], texts["z"]: [0.8, 0.6]}
    retriever = retrieval.Retriever(
        [passage(pid, text) for pid, text in texts.items()],
        embedder=FixedEmbedder(vectors, query=[1.0, 0.0]),
    )

    assert [h.passage_id for h in retriever.rank("q", method="bm25", editions=[JUL])] == [
        "x", "y", "z"
    ]
    assert [h.passage_id for h in retriever.rank("q", method="dense", editions=[JUL])] == [
        "y", "z", "x"
    ]
    hybrid = retriever.rank("q", method="hybrid", editions=[JUL])
    assert [(h.passage_id, round(h.score, 6)) for h in hybrid] == [
        ("y", round(1 / 62 + 1 / 61, 6)),
        ("x", round(1 / 61 + 1 / 63, 6)),
        ("z", round(1 / 63 + 1 / 62, 6)),
    ]


def test_a_strict_edition_selection_never_returns_another_editions_passage():
    passages = [
        passage("jan/1", "Procalcitonin 1619.00 Tarif", JAN),
        passage("jul/1", "Auftragstaxe 4700.00 Tarif", JUL),
        passage("jul/2", "Procalcitonin wird nicht erwähnt", JUL),
    ]
    vectors = {p.text: [1.0, float(i)] for i, p in enumerate(passages)}
    retriever = retrieval.Retriever(passages, embedder=FixedEmbedder(vectors, [1.0, 0.0]))

    for method in retrieval.METHODS:
        july = retriever.rank("Procalcitonin 1619.00", method=method, editions=[JUL])
        both = retriever.rank("Procalcitonin 1619.00", method=method, editions=[JAN, JUL])
        assert [h.passage_id for h in july if h.passage_id.startswith("jan")] == [], method
        assert {h.passage_id for h in both} == {"jan/1", "jul/1", "jul/2"}, method

    with pytest.raises(ValueError, match=r"unknown edition\(s\) 2027-01-01; the corpus has "
                                         r"2026-01-01, 2026-07-01"):
        retriever.rank("x", method="bm25", editions=["2027-01-01"])
    with pytest.raises(ValueError, match="select at least one edition"):
        retriever.rank("x", method="bm25", editions=[])
