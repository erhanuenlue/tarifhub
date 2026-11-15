"""Offline tests for the dev cases and the retrieval metrics.

Expected metric values are worked out by hand in the comments, independent of the code.

    uv run --project services/ingestion --no-sync python -m pytest tools/commentary_rag -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import corpus
import evaluation

JUL = "2026-07-01"
JAN = "2026-01-01"


def passage(pid: str, edition: str, page: int, text: str) -> corpus.Passage:
    return corpus.Passage(
        passage_id=pid, edition=edition, document_sha256="0" * 64, source_url=None,
        page=page, page_label=None, section="2.1", section_title=None, text=text,
        text_sha256="0" * 64, tokens=len(text.split()), split="sentence",
    )


def small_corpus(passages: list[corpus.Passage]) -> corpus.Corpus:
    documents = tuple(
        corpus.Document(edition=e, path=f"{e}.pdf", sha256="0" * 64, source_url=None,
                        title=None, page_count=9)
        for e in sorted({p.edition for p in passages})
    )
    return corpus.Corpus(documents=documents, passages=tuple(passages), excluded_pages=(),
                         token_budget=256, model_limit=512)


def write_cases(tmp_path: Path, cases: list[dict]) -> Path:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"schema": 1, "cases": cases}), encoding="utf-8")
    return path


def case(case_id: str, editions: list[str], evidence: list[dict]) -> dict:
    return {"id": case_id, "question": "?", "target_editions": editions, "evidence": evidence}


EDITION_OF = {"a": JUL, "b": JAN, "c": JUL, "d": JAN, "e": JUL, "f": JUL}
BOTH = (JAN, JUL)


def test_case_metrics_follow_the_definitions_and_leave_undefined_values_undefined():
    # A: two July items covered by c and by f; top 5 = a b c d e.
    #    recall 1/2, first covering passage c at rank 3 -> MRR 1/3, wrong edition b and d -> 2.
    a = evaluation.case_metrics(
        top=["a", "b", "c", "d", "e"], covers=[{"c"}, {"f"}], item_editions=[JUL, JUL],
        target_editions=(JUL,), corpus_editions=BOTH, edition_of=EDITION_OF,
    )
    # B: no evidence items -> recall and MRR undefined, never 0; wrong edition still counted.
    b = evaluation.case_metrics(
        top=["b", "a", "c", "d", "e"], covers=[], item_editions=[],
        target_editions=(JUL,), corpus_editions=BOTH, edition_of=EDITION_OF,
    )
    # C: items from both editions (d for January, e for July); top 5 = a b c d f.
    #    recall 1/2, MRR 1/4, wrong edition undefined (both editions targeted), coverage 0.
    c = evaluation.case_metrics(
        top=["a", "b", "c", "d", "f"], covers=[{"d"}, {"e"}], item_editions=[JAN, JUL],
        target_editions=BOTH, corpus_editions=BOTH, edition_of=EDITION_OF,
    )
    d = evaluation.case_metrics(
        top=["d", "e"], covers=[{"d"}, {"e"}], item_editions=[JAN, JUL],
        target_editions=BOTH, corpus_editions=BOTH, edition_of=EDITION_OF,
    )

    assert (a.evidence_recall, a.mrr, a.wrong_edition, a.both_edition_coverage) == (
        0.5, pytest.approx(1 / 3), 2, None)
    assert (b.evidence_recall, b.mrr, b.wrong_edition, b.both_edition_coverage) == (
        None, None, 2, None)
    assert (c.evidence_recall, c.mrr, c.wrong_edition, c.both_edition_coverage) == (
        0.5, 0.25, None, 0)
    assert (d.evidence_recall, d.mrr, d.both_edition_coverage) == (1.0, 1.0, 1)

    # Aggregates over A, B, C: recall (0.5 + 0.5) / 2 over 2 defined cases; MRR
    # (1/3 + 1/4) / 2 = 7/24; wrong-edition rate (2 + 2) / (5 + 5) over A and B; coverage C only.
    summary = evaluation.aggregate([a, b, c])
    assert (summary.evidence_recall, summary.recall_cases) == (0.5, 2)
    assert (summary.mrr, summary.mrr_cases) == (pytest.approx(7 / 24), 2)
    assert (summary.wrong_edition_rate, summary.wrong_edition_passages,
            summary.wrong_edition_retrieved, summary.wrong_edition_cases) == (0.4, 4, 10, 2)
    assert (summary.both_edition_coverage, summary.coverage_cases) == (0.0, 1)
    assert evaluation.aggregate([b]).evidence_recall is None


class FixedEmbedder:
    dimension = 2

    def embed(self, text: str) -> list[float]:
        """Shorter texts point closer to the query."""
        return [1.0, float(len(text))]

    def embed_query(self, text: str) -> list[float]:
        """The one fixed query vector."""
        return [1.0, 0.0]


def test_the_record_keeps_every_ranking_and_its_metrics_recompute_from_it(tmp_path):
    import retrieval  # noqa: PLC0415

    built = small_corpus([
        passage("jan/1", JAN, 3, "Auftragstaxe im Januar"),
        passage("jan/2", JAN, 4, "Procalcitonin sinkt"),
        passage("jul/1", JUL, 4, "Auftragstaxe sinkt"),
        passage("jul/2", JUL, 5, "Anderes Thema"),
    ])
    cases = evaluation.load_cases(write_cases(tmp_path, [
        case("D", [JUL], [{"edition": JUL, "page": 4, "quote": "Auftragstaxe sinkt"}]),
        case("U", [JUL], []),
    ]), built)
    retriever = retrieval.Retriever(built.passages, embedder=FixedEmbedder())

    record = json.loads(json.dumps(evaluation.evaluate(built, cases, retriever, k=2)))

    assert len(record["runs"]) == 2 * 3 * 2  # cases x methods x modes
    for run in record["runs"]:
        ids = [pid for pid, _ in run["ranking"]]
        assert len(ids) == (2 if run["mode"] == "edition_filter" else 4)
        if run["mode"] == "edition_filter":
            assert all(pid.startswith("jul/") for pid in ids)
    assert record["cases"][0]["evidence"][0]["covering_passages"] == ["jul/1"]
    assert evaluation.recompute(record) == []

    bm25 = next(r for r in record["runs"]
                if (r["case"], r["method"], r["mode"]) == ("D", "bm25", "edition_filter"))
    assert bm25["ranking"][0][0] == "jul/1"
    bm25["ranking"][0], bm25["ranking"][1] = bm25["ranking"][1], bm25["ranking"][0]
    assert evaluation.recompute(record) == [
        "D bm25 edition_filter: stored mrr 1.0, recomputed 0.5",
        "bm25 edition_filter summary: stored mrr 1.0, recomputed 0.5",
    ]


RESULTS = Path(__file__).resolve().parent / "results"


@pytest.mark.parametrize("name", ["2026-11-14-retrieval.json",
                                  "2026-11-14-retrieval-corrected.json"])
def test_the_recorded_run_recomputes_exactly_and_no_input_was_truncated(name):
    if not (RESULTS / name).exists():
        pytest.skip(f"no recorded run {name}")
    record = json.loads((RESULTS / name).read_text(encoding="utf-8"))

    assert evaluation.recompute(record) == []
    limit = record["run"]["configuration"]["model_limit"]
    assert max(p["tokens"] for p in record["passages"]) <= limit
    assert max(record["run"]["token_counts"]["queries"].values()) <= limit


def toy_record(passages, covering, scores, summary):
    return {
        "k": 5,
        "cases": [
            {"id": "D", "question": "q", "target_editions": [JUL], "evidence": [
                {"edition": JUL, "page": 4, "quote": "x", "covering_passages": covering}]},
            {"id": "U", "question": "u", "target_editions": [JUL], "evidence": []},
        ],
        "passages": [{"passage_id": pid, "text_sha256": h, "context_sha256": None}
                     for pid, h in passages],
        "scores": [{"case": c, "method": m, "mode": "edition_filter", "evidence_recall": r,
                    "mrr": mrr, "wrong_edition": w, "retrieved": 5,
                    "both_edition_coverage": None} for c, m, r, mrr, w in scores],
        "summary": [{"method": "bm25", "mode": "edition_filter", "evidence_recall": s}
                    for s in summary],
    }


def test_compare_records_reports_changes_by_case_and_method_including_regressions():
    before = toy_record(
        [("a", "1"), ("b", "2"), ("h", "3")], ["b"],
        [("D", "bm25", 1.0, 0.5, 0), ("D", "dense", 0.0, 0.0, 0), ("D", "hybrid", 1.0, 1.0, 0),
         ("U", "bm25", None, None, 2)], [0.5],
    )
    after = toy_record(
        [("a", "1"), ("b", "9"), ("c", "4")], ["c"],
        [("D", "bm25", 1.0, 1.0, 0), ("D", "dense", 0.0, 0.0, 0), ("D", "hybrid", 1.0, 0.5, 0),
         ("U", "bm25", None, None, 1)], [0.75],
    )

    diff = evaluation.compare_records(before, after)

    assert diff["settings_differ"] == []
    assert diff["passages"] == {"removed": ["h"], "added": ["c"], "changed": ["b"], "unchanged": 1}
    assert diff["evidence"] == [{"case": "D", "item": 1, "before": ["b"], "after": ["c"]}]
    assert [(r["case"], r["method"], r["change"], r["wrong_edition"]) for r in diff["cases"]] == [
        ("D", "bm25", "improved", [0, 0]),
        ("D", "dense", "unchanged failure", [0, 0]),
        ("D", "hybrid", "regressed", [0, 0]),
        ("U", "bm25", "no evidence items", [2, 1]),
    ]
    assert diff["summary"] == [
        {"method": "bm25", "mode": "edition_filter", "evidence_recall": [0.5, 0.75]}
    ]
    changed_k = dict(after, k=10)
    assert evaluation.compare_records(before, changed_k)["settings_differ"] == ["k"]


def test_load_cases_refuses_every_reference_the_corpus_does_not_support(tmp_path):
    built = small_corpus([
        passage("jul/p3/1", JUL, 3, "Die Position 1779.00 ist nicht kumulierbar."),
        passage("jul/p3/2", JUL, 3, "Sie ist auch nicht mit 1474.10 kumulierbar."),
        passage("jan/p3/1", JAN, 3, "Der Tarif sinkt auf 63.3 TP."),
    ])
    path = write_cases(tmp_path, [
        case("ok", [JUL], [{"edition": JUL, "page": 3, "quote": "nicht   kumulierbar."}]),
        case("wrong-page", [JUL], [{"edition": JUL, "page": 4, "quote": "1779.00"}]),
        case("absent", [JUL], [{"edition": JUL, "page": 3, "quote": "64.4 TP"}]),
        case("outside-target", [JUL], [{"edition": JAN, "page": 3, "quote": "63.3 TP"}]),
        case("straddles", [JUL], [{"edition": JUL, "page": 3,
                                   "quote": "kumulierbar. Sie ist auch"}]),
        case("unknown-edition", ["2027-01-01"], []),
    ])

    with pytest.raises(evaluation.CaseError) as refused:
        evaluation.load_cases(path, built)

    assert refused.value.problems == (
        "wrong-page: quote '1779.00' is not on 2026-07-01 page 4 (found on page 3)",
        "absent: quote '64.4 TP' is not in the 2026-07-01 commentary",
        "outside-target: evidence edition 2026-01-01 is not a target edition of the case",
        "straddles: quote 'kumulierbar. Sie ist auch' is on 2026-07-01 page 3 but in no single "
        "passage",
        "unknown-edition: target edition 2027-01-01 has no commentary in the corpus",
    )
    accepted = evaluation.load_cases(write_cases(tmp_path, [
        case("ok", [JUL], [{"edition": JUL, "page": 3, "quote": "nicht   kumulierbar."}]),
        case("none", [JUL], []),
    ]), built)
    assert [(c.case_id, c.evidence) for c in accepted] == [
        ("ok", (evaluation.Evidence(JUL, 3, "nicht kumulierbar."),)),
        ("none", ()),
    ]

