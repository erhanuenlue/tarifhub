"""BM25, multilingual-e5 dense and RRF hybrid ranking over one shared passage corpus.

Every ranking is over an explicit edition selection: passages of unselected editions are never
candidates, so a strict selection cannot return another edition's passage (wrong-edition
retrieval is zero by construction, not by model behaviour). Rankings are total orders: equal
scores are broken by ``passage_id``, so a ranking never depends on input order.

* BM25: Okapi BM25 with Lucene's non-negative IDF, ``k1 = 1.2``, ``b = 0.75``, statistics over
  the selected passages only. Terms are NFC, case-folded runs of letters, or digit groups that
  keep their separators (``1368.00`` stays one term). No stemming, no stop words.
* Dense: cosine between the e5 query vector (``"query: "`` prefix) and each passage vector
  (``"passage: "`` prefix), both from the repository's own embedder; passages are embedded once.

BM25 and the embedder both see a passage's ``indexed_text``: its text, preceded by the table
heading for a later part of a split table (verbatim from the same page).
* Hybrid: reciprocal rank fusion of the BM25 and dense rankings, ``1 / (60 + rank)`` summed.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

METHODS = ("bm25", "dense", "hybrid")
BM25_K1 = 1.2
BM25_B = 0.75
RRF_K = 60

_TERM = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_]+")


@dataclass(frozen=True)
class Hit:
    """One ranked passage."""

    passage_id: str
    score: float


def terms(text: str) -> list[str]:
    """The BM25 terms of ``text``."""

    return _TERM.findall(unicodedata.normalize("NFC", text).casefold())


class Retriever:
    """Ranks the passages of a corpus; ``embedder`` (the e5 port) is needed for dense/hybrid."""

    def __init__(self, passages: Sequence, embedder=None) -> None:
        self._passages = tuple(passages)
        self._editions = tuple(sorted({p.edition for p in self._passages}))
        self._terms = {p.passage_id: Counter(terms(p.indexed_text)) for p in self._passages}
        self._lengths = {pid: sum(c.values()) for pid, c in self._terms.items()}
        self._embedder = embedder
        self._vectors = (
            {p.passage_id: embedder.embed(p.indexed_text) for p in self._passages}
            if embedder is not None
            else None
        )

    @property
    def editions(self) -> tuple[str, ...]:
        """The editions present in the corpus."""

        return self._editions

    def rank(self, query: str, *, method: str, editions: Sequence[str]) -> list[Hit]:
        """Every passage of the selected editions, best first, for ``method``."""

        selected = self._select(editions)
        if method == "bm25":
            return _ordered(self._bm25(query, selected))
        if method == "dense":
            return _ordered(self._dense(query, selected))
        if method == "hybrid":
            return fuse(
                [
                    [h.passage_id for h in _ordered(self._bm25(query, selected))],
                    [h.passage_id for h in _ordered(self._dense(query, selected))],
                ]
            )
        raise ValueError(f"unknown method {method!r}; use one of {', '.join(METHODS)}")

    def _select(self, editions: Sequence[str]) -> list[str]:
        wanted = set(editions)
        if not wanted:
            raise ValueError("select at least one edition")
        unknown = sorted(wanted - set(self._editions))
        if unknown:
            raise ValueError(
                f"unknown edition(s) {', '.join(unknown)}; the corpus has "
                f"{', '.join(self._editions)}"
            )
        return [p.passage_id for p in self._passages if p.edition in wanted]

    def _bm25(self, query: str, selected: list[str]) -> dict[str, float]:
        count = len(selected)
        average = sum(self._lengths[pid] for pid in selected) / count
        scores = dict.fromkeys(selected, 0.0)
        for term in sorted(set(terms(query))):
            frequency = sum(1 for pid in selected if term in self._terms[pid])
            if not frequency:
                continue
            idf = math.log(1 + (count - frequency + 0.5) / (frequency + 0.5))
            for pid in selected:
                tf = self._terms[pid][term]
                if tf:
                    norm = BM25_K1 * (1 - BM25_B + BM25_B * self._lengths[pid] / average)
                    scores[pid] += idf * tf * (BM25_K1 + 1) / (tf + norm)
        return scores

    def _dense(self, query: str, selected: list[str]) -> dict[str, float]:
        if self._embedder is None or self._vectors is None:
            raise ValueError("dense and hybrid ranking need an embedder")
        q = self._embedder.embed_query(query)
        return {pid: _cosine(q, self._vectors[pid]) for pid in selected}


def fuse(rankings: Iterable[Sequence[str]]) -> list[Hit]:
    """Reciprocal rank fusion: each passage scores ``sum(1 / (RRF_K + rank))``, ranks from 1."""

    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, pid in enumerate(ranking, start=1):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (RRF_K + rank)
    return _ordered(scores)


def _ordered(scores: dict[str, float]) -> list[Hit]:
    return [Hit(pid, score) for pid, score in sorted(scores.items(), key=lambda i: (-i[1], i[0]))]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0
