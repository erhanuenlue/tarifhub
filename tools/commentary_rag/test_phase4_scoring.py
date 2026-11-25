"""Offline tests for the deterministic Phase 4 scorer (``phase4_scoring.py``).

Synthetic records and gold parts only: no model, no network, no books, and nothing written
outside pytest's tmp_path (the results/ guard is tested by refusal, the folder listed before and
after). Passage IDs follow the synthetic test corpus (``test_evidence_search.world``, July
passages ``jul/a`` to ``jul/l``); C's and D's initial context is ``jul/k``, ``jul/h``, ``jul/a``,
``jul/l``, ``jul/i`` (conditions.md, section 7). Expected values are worked out by hand from
the frozen rubric (phase4/rubric-and-thresholds.md); the outcome tables are checked against row
predicates written here from the rubric. Two tests compare scorer output with scorer output
instead: the same trace read as C and as D, with D's coverage record present, absent or
contradictory, and the command line's file and stdout against ``score`` and ``summary``.

    UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" uv run \\
        --project services/ingestion --frozen --offline --extra ai --extra dev \\
        python -m pytest tools/commentary_rag/test_phase4_scoring.py -q
"""

from __future__ import annotations

import copy
import itertools
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import phase4_scoring as ps

SCRIPT = Path(__file__).resolve().parent / "phase4_scoring.py"
JUL = "2026-07-01"
NA = "not_assessable"
INITIAL = ("jul/k", "jul/h", "jul/a", "jul/l", "jul/i")
# The shared top 10 of every synthetic case: ranks 1 to 5 are C's and D's initial context, ranks
# 6 to 10 are c f b d e; g and j are not in it.
RANKING = [*INITIAL, "jul/c", "jul/f", "jul/b", "jul/d", "jul/e"]


def fact(part_id: str, *passages: str) -> dict:
    """A fact part whose frozen set of equivalent supporting passages is ``passages``."""
    return {
        "id": part_id,
        "kind": "fact",
        "statement": "synthetic",
        "support": [{"passage_id": p, "quote": "synthetic"} for p in passages],
    }


def gap(part_id: str) -> dict:
    return {
        "id": part_id,
        "kind": "gap",
        "statement": "synthetic",
        "gap_justification": "synthetic",
    }


COVERED = [fact("R1", "jul/k"), fact("R2", "jul/h")]  # both stated by the initial five
MISSING = [
    fact("R1", "jul/k"),
    fact("R2", "jul/c", "jul/f"),
]  # R2 needs c or f (ranks 6, 7)
GAP = [fact("R1", "jul/k"), gap("R2")]
GAP_ONLY = [gap("R1")]
# D's own coverage entry for a direct answer it calls complete (conditions.md, 4.8 and 7.1).
COMPLETE = {
    "call": 1,
    "action": "answer",
    "check": "ok",
    "parts": 2,
    "covered": 2,
    "missing": 0,
    "search_for": None,
    "missing_not_reported": False,
}


def search(rounds: int | None, outcome: str, *returned: str) -> dict:
    """One search record as ``evidence_search`` writes it (the fields the scorer reads)."""
    return {
        "round": rounds,
        "outcome": outcome,
        "method": "hybrid",
        "window": 10,
        "returned": [
            {"passage_id": p, "rank": n, "score": 0.5}
            for n, p in enumerate(returned, start=1)
        ],
        "already_supplied": [],
    }


def record(
    condition: str,
    choices: list,
    searches=(),
    outcome: str = "answer",
    initial: tuple = INITIAL,
) -> dict:
    """A cell's record as ``evidence_agent._case`` leaves it: one call per tool choice."""
    searches = [copy.deepcopy(s) for s in searches]
    return {
        "case": "X-01",
        "condition": condition,
        "budget_s": 600.0,
        "generation_calls": len(choices),
        "calls": [
            {
                "call": n,
                "attempt": f"X-01-{condition}-call{n}",
                "tool_choice": choice,
                "reserved_usd": 1.5,
                "cost_usd": 0.5,
                "cost_basis": "usage",
            }
            for n, choice in enumerate(choices, start=1)
        ],
        "searches": searches,
        "outcome": outcome,
        "detail": None,
        "supplied": [
            *initial,
            *(r["passage_id"] for s in searches for r in s["returned"]),
        ],
    }


def changed(rec: dict, **values) -> dict:
    """A copy of a record with some fields replaced."""
    copied = copy.deepcopy(rec)
    copied.update(values)
    return copied


def view(points: list[dict], *keys: str) -> list[tuple]:
    return [tuple(p[k] for k in keys) for p in points]


def cell(condition: str, rec: dict | None) -> dict:
    """One cell of a LOCAL result.json as ``run_comparison`` keeps it."""
    status = {
        "execution": rec["outcome"] if rec else "not_run",
        "detail": None if rec else "matrix_stopped",
        "answer": None,
        "accounting": "settled" if rec else "nothing_reserved",
    }
    return {
        "condition": condition,
        "status": status,
        "answer": None,
        "record": rec,
        "local": {} if rec else None,
    }


def one_cell(rec: dict | None, parts: list, condition: str) -> dict:
    """The scored cell of a one-case result that holds only this cell."""
    result = {
        "cases": [
            {
                "case": "X-01",
                "question": "synthetic",
                "editions": [JUL],
                "ranking": RANKING,
                "cells": [cell(condition, rec)],
            }
        ]
    }
    gold = {
        "cases": [
            {
                "id": "X-01",
                "editions": [JUL],
                "expected_status": "answered",
                "parts": parts,
            }
        ]
    }
    return ps.score(result, gold)["cases"][0]["cells"][0]


def fixture() -> tuple[dict, dict]:
    """A result of two cases and its gold file (a third gold case has no result).

    X-01 (S2: R2 only at ranks 6 and 7): B answers; C finds jul/c with one search and answers;
    D answers at once and calls itself complete although R2 is missing. X-02 (G): B answers; C
    searches once at a gap check and answers; D was held back (no record).
    """
    direct = record("coverage", ["auto"])
    direct["coverage"] = [COMPLETE]
    b_cell = record("fixed10", [None], initial=tuple(RANKING))
    result = {
        "cases": [
            {
                "case": "X-01",
                "question": "synthetic one",
                "editions": [JUL],
                "ranking": RANKING,
                "cells": [
                    cell("fixed10", b_cell),
                    cell(
                        "agent",
                        record(
                            "agent", ["auto", "auto"], [search(1, "passages", "jul/c")]
                        ),
                    ),
                    cell("coverage", direct),
                ],
            },
            {
                "case": "X-02",
                "question": "synthetic two",
                "editions": [JUL],
                "ranking": RANKING,
                "cells": [
                    cell("fixed10", copy.deepcopy(b_cell)),
                    cell(
                        "agent",
                        record(
                            "agent", ["auto", "auto"], [search(1, "passages", "jul/g")]
                        ),
                    ),
                    cell("coverage", None),
                ],
            },
        ]
    }
    gold = {
        "cases": [
            {
                "id": "X-01",
                "editions": [JUL],
                "expected_status": "answered",
                "parts": [fact("X-01-R1", "jul/k"), fact("X-01-R2", "jul/c", "jul/f")],
            },
            {
                "id": "X-02",
                "editions": [JUL],
                "expected_status": "insufficient_evidence",
                "parts": [gap("X-02-R1")],
            },
            {
                "id": "X-03",
                "editions": [JUL],
                "expected_status": "answered",
                "parts": [fact("X-03-R1", "jul/b")],
            },
        ]
    }
    return result, gold


# Strata


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        ([fact("R1", "jul/k"), fact("R2", "jul/i")], ("S1", False, {"R1": 1, "R2": 5})),
        ([fact("R1", "jul/k"), fact("R2", "jul/c")], ("S2", False, {"R1": 1, "R2": 6})),
        ([fact("R1", "jul/e")], ("S2", False, {"R1": 10})),
        (
            [fact("R1", "jul/k"), fact("R2", "jul/g", "jul/j")],
            ("S3", False, {"R1": 1, "R2": None}),
        ),
        ([gap("R1"), gap("R2")], ("G", False, {})),
        ([fact("R1", "jul/f"), gap("R2")], ("S2", True, {"R1": 7})),
        ([fact("R1", "jul/g"), gap("R2")], ("S3", True, {"R1": None})),
        (
            [fact("R1", "jul/f", "jul/h")],
            ("S1", False, {"R1": 2}),
        ),  # any passage of the set counts
    ],
    ids=[
        "S1",
        "S2",
        "S2-rank-10",
        "S3",
        "G",
        "mixed-S2",
        "mixed-S3",
        "equivalent-evidence",
    ],
)
def test_strata(parts, expected):
    got = ps.strata(parts, RANKING)
    assert (got["stratum"], got["mixed"], got["best_rank"]) == expected


def test_strata_read_only_the_top_10():
    assert (
        ps.strata([fact("R1", "jul/g")], [*RANKING, "jul/g"])["stratum"] == "S3"
    )  # rank 11
    with pytest.raises(ValueError):
        ps.strata([fact("R1", "jul/k")], ["jul/k", "jul/k"])  # a passage ranked twice


BAD_PARTS = {
    "no-part": [],
    "five-parts": [fact(f"R{n}", "jul/k") for n in range(1, 6)],
    "fact-without-support": [{"id": "R1", "kind": "fact", "support": []}],
    "gap-with-support": [
        {"id": "R1", "kind": "gap", "support": [{"passage_id": "jul/k"}]}
    ],
    "unknown-kind": [{"id": "R1", "kind": "claim"}],
    "same-id-twice": [fact("R1", "jul/k"), gap("R1")],
}


@pytest.mark.parametrize("name", list(BAD_PARTS))
def test_invalid_gold_parts_are_refused(name):
    with pytest.raises(ValueError):
        ps.strata(BAD_PARTS[name], RANKING)


# Decision points, kinds, actions and measures


def test_a_search_where_every_fact_part_is_covered_is_unnecessary():
    rec = record("agent", ["auto", "auto"], [search(1, "passages", "jul/c")])
    points = ps.decision_points(rec, COVERED, "agent")
    assert view(points, "call", "capacity", "anomaly", "kind", "action", "measure") == [
        (1, True, False, "no_search_needed", "search_run", "unnecessary"),
        (2, True, False, "no_search_needed", "answer", None),
    ]
    counts = one_cell(rec, COVERED, "agent")["counts"]
    assert (
        counts["unnecessary"],
        counts["unnecessary_rate"],
        counts["missed_rate"],
    ) == (1, {"k": 1, "n": 2}, {"k": 0, "n": 0})


def test_d_answering_at_once_with_every_fact_part_covered_needs_no_search():
    rec = record("coverage", ["auto"])
    rec["coverage"] = [COMPLETE]
    points = ps.decision_points(rec, COVERED, "coverage")
    assert view(
        points, "call", "capacity", "kind", "action", "measure", "missing_before"
    ) == [(1, True, "no_search_needed", "answer", None, [])]
    counts = one_cell(rec, COVERED, "coverage")["counts"]
    assert (counts["searches"], counts["unnecessary_rate"], counts["missed_rate"]) == (
        0,
        {"k": 0, "n": 1},
        {"k": 0, "n": 0},
    )


def test_a_direct_d_answer_with_a_retrievable_part_missing_is_missed_whatever_d_recorded():
    rec = record("coverage", ["auto"])
    rec["coverage"] = [COMPLETE]  # D calls itself complete; the frozen sets decide
    points = ps.decision_points(rec, MISSING, "coverage")
    assert view(points, "kind", "action", "measure", "missing_before") == [
        ("search_needed", "answer", "missed", ["R2"])
    ]
    without = copy.deepcopy(rec)
    del without["coverage"]
    contrary = changed(
        rec,
        coverage=[
            {**COMPLETE, "covered": 1, "missing": 1, "missing_not_reported": True}
        ],
    )
    as_c = changed(without, condition="agent")
    for other, condition in (
        (without, "coverage"),
        (contrary, "coverage"),
        (as_c, "agent"),
    ):
        assert ps.decision_points(other, MISSING, condition) == points
    assert one_cell(rec, MISSING, "coverage")["counts"]["missed_rate"] == {
        "k": 1,
        "n": 1,
    }


def test_a_refused_search_at_a_search_needed_point_is_missed_and_uses_its_round():
    rec = record("coverage", ["auto", "auto"], [search(1, "refused_coverage")])
    points = ps.decision_points(rec, MISSING, "coverage")
    keys = (
        "call",
        "capacity",
        "rounds_before",
        "supplied_before",
        "kind",
        "action",
        "search_outcome",
        "measure",
    )
    assert view(points, *keys) == [
        (
            1,
            True,
            0,
            5,
            "search_needed",
            "search_refused",
            "refused_coverage",
            "missed",
        ),
        (2, True, 1, 5, "search_needed", "answer", None, "missed"),
    ]
    counts = one_cell(rec, MISSING, "coverage")["counts"]
    assert counts["refused_searches"] == {
        "total": 1,
        "search_needed": 1,
        "gap_check": 0,
        "no_search_needed": 0,
    }
    assert (counts["missed"], counts["missed_rate"], counts["warranted"]) == (
        2,
        {"k": 2, "n": 2},
        0,
    )


def test_a_refused_search_where_nothing_is_missing_is_an_action_but_not_unnecessary():
    rec = record("coverage", ["auto", "auto"], [search(1, "refused_coverage")])
    counts = one_cell(rec, COVERED, "coverage")["counts"]
    assert (counts["unnecessary"], counts["unnecessary_rate"]) == (0, {"k": 0, "n": 2})
    assert counts["refused_searches"]["no_search_needed"] == 1


def test_a_search_at_a_gap_check_point_is_counted_apart():
    rec = record("agent", ["auto", "auto"], [search(1, "passages", "jul/c", "jul/b")])
    points = ps.decision_points(rec, GAP, "agent")
    assert view(points, "kind", "action", "measure") == [
        ("gap_check", "search_run", "gap_check_search"),
        ("gap_check", "answer", None),
    ]
    counts = one_cell(rec, GAP, "agent")["counts"]
    assert (
        counts["gap_check_searches"],
        counts["unnecessary"],
        counts["warranted"],
    ) == (1, 0, 0)
    assert counts["decision_points"]["gap_check"] == {
        "with_action": 2,
        "without_action": 0,
    }
    assert (counts["unnecessary_rate"], counts["missed_rate"]) == (
        {"k": 0, "n": 0},
        {"k": 0, "n": 0},
    )
    only_gaps = ps.decision_points(record("agent", ["auto"]), GAP_ONLY, "agent")
    assert view(only_gaps, "kind", "action") == [("gap_check", "answer")]


def test_no_new_passages_then_a_second_search_are_two_warranted_searches():
    rec = record(
        "agent",
        ["auto", "auto", "none"],
        [search(1, "no_new_passages"), search(2, "passages", "jul/f")],
    )
    points = ps.decision_points(rec, MISSING, "agent")
    keys = (
        "call",
        "capacity",
        "rounds_before",
        "kind",
        "action",
        "search_outcome",
        "measure",
        "yield",
    )
    assert view(points, *keys) == [
        (
            1,
            True,
            0,
            "search_needed",
            "search_run",
            "no_new_passages",
            "warranted",
            False,
        ),
        (2, True, 1, "search_needed", "search_run", "passages", "warranted", True),
        (3, False, 2, None, "answer", None, None, None),
    ]
    counts = one_cell(rec, MISSING, "agent")["counts"]
    assert (
        counts["warranted"],
        counts["yield"],
        counts["missed_rate"],
        counts["anomalies"],
    ) == (2, {"k": 1, "n": 2}, {"k": 0, "n": 2}, 0)


def test_a_tool_error_is_a_search_run():
    rec = record("agent", ["auto", "auto"], [search(1, "tool_error")])
    points = ps.decision_points(rec, MISSING, "agent")
    assert view(points, "action", "search_outcome", "measure", "yield") == [
        ("search_run", "tool_error", "warranted", False),
        ("answer", None, "missed", None),
    ]
    counts = one_cell(rec, MISSING, "agent")["counts"]
    assert (counts["tool_errors"], counts["searches"], counts["missed_rate"]) == (
        1,
        1,
        {"k": 1, "n": 2},
    )


def test_a_decision_point_without_action_is_listed_and_left_out_of_the_rates():
    rec = record("agent", ["auto"], outcome="provider_error")
    points = ps.decision_points(rec, MISSING, "agent")
    assert view(points, "capacity", "kind", "action", "measure") == [
        (True, "search_needed", "no_action", None)
    ]
    counts = one_cell(rec, MISSING, "agent")["counts"]
    assert counts["decision_points"]["search_needed"] == {
        "with_action": 0,
        "without_action": 1,
    }
    assert (counts["missed"], counts["missed_rate"]) == (0, {"k": 0, "n": 0})
    later = record(
        "agent", ["auto", "auto"], [search(1, "passages", "jul/b")], outcome="deadline"
    )
    counts = one_cell(later, MISSING, "agent")["counts"]
    assert counts["decision_points"]["search_needed"] == {
        "with_action": 1,
        "without_action": 1,
    }
    assert (counts["warranted"], counts["yield"], counts["missed_rate"]) == (
        1,
        {"k": 0, "n": 1},
        {"k": 0, "n": 1},
    )
    # The deadline after the reservation, before sending: the call is recorded but not sent.
    unsent = changed(later, generation_calls=1)
    assert ps.decision_points(unsent, MISSING, "agent") == ps.decision_points(
        later, MISSING, "agent"
    )
    assert one_cell(unsent, MISSING, "agent")["calls"] == 1


def test_a_full_passage_budget_after_one_search_ends_the_decision_points():
    rec = record(
        "coverage",
        ["auto", "none"],
        [search(1, "passages", "jul/c", "jul/f", "jul/b", "jul/d", "jul/e")],
    )
    points = ps.decision_points(rec, MISSING, "coverage")
    assert view(
        points, "call", "capacity", "anomaly", "supplied_before", "kind", "measure"
    ) == [
        (1, True, False, 5, "search_needed", "warranted"),
        (2, False, False, 10, None, None),
    ]


def test_a_tool_choice_that_disagrees_with_capacity_is_an_anomaly():
    # Capacity without the tool: still a decision point by capacity alone, here a missed search.
    rec = record("agent", ["none"])
    assert view(
        ps.decision_points(rec, MISSING, "agent"),
        "capacity",
        "anomaly",
        "kind",
        "measure",
    ) == [(True, True, "search_needed", "missed")]
    # The tool offered at D's last call (D has C's three calls): an anomaly, no decision point.
    rec = record(
        "coverage",
        ["auto", "auto", "auto"],
        [search(1, "no_new_passages"), search(2, "no_new_passages")],
    )
    points = ps.decision_points(rec, MISSING, "coverage")
    assert view(points, "call", "capacity", "anomaly") == [
        (1, True, False),
        (2, True, False),
        (3, False, True),
    ]
    assert one_cell(rec, MISSING, "coverage")["counts"]["anomalies"] == 1


def test_a_cell_that_ends_after_a_search_has_no_later_decision_point():
    """The next call was never recorded (the deadline after the search, or a refusal before
    its reservation): it is not in the trace and no decision point."""
    for outcome in ("deadline", "refused"):
        rec = record(
            "agent", ["auto"], [search(1, "passages", "jul/c")], outcome=outcome
        )
        points = ps.decision_points(rec, MISSING, "agent")
        assert view(points, "call", "action", "measure", "yield") == [
            (1, "search_run", "warranted", True)
        ]


def test_a_request_refused_for_want_of_rounds_uses_no_round():
    rec = record(
        "agent",
        ["auto", "auto", "none"],
        [search(None, "refused_rounds"), search(1, "passages", "jul/c")],
    )
    points = ps.decision_points(rec, MISSING, "agent")
    assert view(points, "call", "rounds_before", "action") == [
        (1, 0, "search_refused"),
        (2, 0, "search_run"),
        (3, 1, "answer"),
    ]


def test_cells_without_a_call_or_a_record_and_b_cells_have_no_decision_points():
    b_rec = record("fixed10", [None], initial=tuple(RANKING))
    assert ps.decision_points(None, MISSING, "coverage") == []
    assert (
        ps.decision_points(record("agent", [], outcome="refused"), MISSING, "agent")
        == []
    )
    assert ps.decision_points(b_rec, MISSING, "fixed10") == []
    held = one_cell(None, MISSING, "coverage")
    assert (held["recorded"], held["calls"], held["decision_points"]) == (
        False,
        None,
        [],
    )
    assert held["counts"]["missed_rate"] == {"k": 0, "n": 0}
    b_cell = one_cell(b_rec, MISSING, "fixed10")
    assert (b_cell["calls"], b_cell["decision_points"], b_cell["counts"]) == (
        1,
        [],
        None,
    )


BROKEN = {
    "more-searches-than-calls": (
        record(
            "agent",
            ["auto"],
            [search(1, "no_new_passages"), search(2, "no_new_passages")],
        ),
        "agent",
    ),
    "supplied-tail": (
        changed(
            record("agent", ["auto", "auto"], [search(1, "passages", "jul/c")]),
            supplied=[*INITIAL, "jul/f"],
        ),
        "agent",
    ),
    "more-returned-than-supplied": (
        changed(
            record("agent", ["auto", "auto"], [search(1, "passages", "jul/c")]),
            supplied=[],
        ),
        "agent",
    ),
    "duplicate-supplied": (
        changed(record("agent", ["auto"]), supplied=[*INITIAL, "jul/k"]),
        "agent",
    ),
    "unknown-search-outcome": (
        record("agent", ["auto", "auto"], [search(1, "ranked")]),
        "agent",
    ),
    "answer-after-the-last-search": (
        record("agent", ["auto"], [search(1, "passages", "jul/c")]),
        "agent",
    ),
    "search-without-the-tool": (
        record("agent", ["none", "none"], [search(1, "passages", "jul/c")]),
        "agent",
    ),
    "unknown-cell-outcome": (record("agent", ["auto"], outcome="finished"), "agent"),
    "round-missing": (
        record("agent", ["auto", "auto"], [search(None, "passages", "jul/c")]),
        "agent",
    ),
    "round-on-refused-rounds": (
        record("agent", ["auto", "auto"], [search(1, "refused_rounds")]),
        "agent",
    ),
    "tool-choice-missing": (record("agent", [None]), "agent"),
    "calls-out-of-order": (
        changed(record("agent", ["auto"]), calls=[{"call": 2, "tool_choice": "auto"}]),
        "agent",
    ),
    "generation-calls-above-calls": (
        changed(record("agent", ["auto"]), generation_calls=2),
        "agent",
    ),
    "record-of-another-condition": (record("coverage", ["auto"]), "agent"),
    "unknown-condition": (record("agent", ["auto"]), "fixed5"),
}


@pytest.mark.parametrize("name", list(BROKEN))
def test_a_trace_that_cannot_be_rebuilt_is_refused(name):
    rec, condition = BROKEN[name]
    with pytest.raises(ValueError):
        ps.decision_points(rec, MISSING, condition)


# Scoring a run and its summary


def test_score_gives_each_case_its_stratum_and_each_cell_its_decision_points():
    result, gold = fixture()
    scored = ps.score(result, gold)
    assert len(scored["cases"]) == 2  # X-03 has no result: not scored
    one, two = scored["cases"]
    assert (
        one["case"],
        one["stratum"],
        one["mixed"],
        one["best_rank"],
        one["fact_parts"],
        one["gap_parts"],
    ) == ("X-01", "S2", False, {"X-01-R1": 1, "X-01-R2": 6}, 2, 0)
    assert (two["case"], two["stratum"], two["best_rank"], two["gap_parts"]) == (
        "X-02",
        "G",
        {},
        1,
    )
    b_cell, c_cell, d_cell = one["cells"]
    assert (
        b_cell["condition"],
        b_cell["outcome"],
        b_cell["calls"],
        b_cell["counts"],
    ) == ("fixed10", "answer", 1, None)
    assert view(
        c_cell["decision_points"], "call", "kind", "action", "measure", "yield"
    ) == [
        (1, "search_needed", "search_run", "warranted", True),
        (2, "no_search_needed", "answer", None, None),
    ]
    assert view(d_cell["decision_points"], "call", "kind", "action", "measure") == [
        (1, "search_needed", "answer", "missed")
    ]
    assert [c["recorded"] for c in two["cells"]] == [True, True, False]


def test_summary_counts_per_condition_and_names_no_case_or_passage():
    result, gold = fixture()
    counts = ps.summary(ps.score(result, gold))
    none = {"with_action": 0, "without_action": 0}
    no_refusal = {"total": 0, "search_needed": 0, "gap_check": 0, "no_search_needed": 0}
    assert counts == {
        "conditions": {
            "fixed10": {"cells": 2, "without_record": 0, "calls_per_cell": {"1": 2}},
            "agent": {
                "cells": 2,
                "without_record": 0,
                "calls_per_cell": {"2": 2},
                "searches_per_cell": {"1": 2},
                "searches": 2,
                "tool_errors": 0,
                "refused_searches": no_refusal,
                "decision_points": {
                    "search_needed": {"with_action": 1, "without_action": 0},
                    "gap_check": {"with_action": 2, "without_action": 0},
                    "no_search_needed": {"with_action": 1, "without_action": 0},
                },
                "warranted": 1,
                "unnecessary": 0,
                "gap_check_searches": 1,
                "missed": 0,
                "yield": {"k": 1, "n": 1},
                "anomalies": 0,
                "unnecessary_rate": {"k": 0, "n": 1},
                "missed_rate": {"k": 0, "n": 1},
            },
            "coverage": {
                "cells": 2,
                "without_record": 1,
                "calls_per_cell": {"1": 1},
                "searches_per_cell": {"0": 1},
                "searches": 0,
                "tool_errors": 0,
                "refused_searches": no_refusal,
                "decision_points": {
                    "search_needed": {"with_action": 1, "without_action": 0},
                    "gap_check": none,
                    "no_search_needed": none,
                },
                "warranted": 0,
                "unnecessary": 0,
                "gap_check_searches": 0,
                "missed": 1,
                "yield": {"k": 0, "n": 0},
                "anomalies": 0,
                "unnecessary_rate": {"k": 0, "n": 0},
                "missed_rate": {"k": 1, "n": 1},
            },
        }
    }
    text = json.dumps(counts)
    for name in ("X-01", "X-02", "X-03", "jul/", "R1", "R2"):
        assert name not in text
    d, c = counts["conditions"]["coverage"], counts["conditions"]["agent"]
    assert (ps.t3(d, c)["status"], ps.t4(d, c)["status"]) == (
        NA,
        NA,
    )  # D's n is 0 and 1


def test_score_refuses_a_case_the_gold_file_lacks_without_naming_it():
    result, gold = fixture()
    gold["cases"] = gold["cases"][1:]
    with pytest.raises(ValueError, match="not in the gold file") as refused:
        ps.score(result, gold)
    assert "X-01" not in str(refused.value)


def case_twice(result, gold):
    result["cases"].append(copy.deepcopy(result["cases"][0]))


def phase3_condition(result, gold):
    result["cases"][0]["cells"][0]["condition"] = "fixed5"


def condition_twice(result, gold):
    result["cases"][0]["cells"].append(copy.deepcopy(result["cases"][0]["cells"][1]))


def other_editions(result, gold):
    result["cases"][0]["editions"] = ["2026-01-01"]


def b_searched(result, gold):
    result["cases"][0]["cells"][0]["record"]["searches"] = [
        search(1, "passages", "jul/g")
    ]


def record_of_another_condition(result, gold):
    result["cases"][0]["cells"][1]["record"]["condition"] = "coverage"


def gold_case_twice(result, gold):
    gold["cases"].append(copy.deepcopy(gold["cases"][0]))


def damaged_unscored_gold_case(result, gold):
    gold["cases"][2]["parts"] = []


@pytest.mark.parametrize(
    "damage",
    [
        case_twice,
        phase3_condition,
        condition_twice,
        other_editions,
        b_searched,
        record_of_another_condition,
        gold_case_twice,
        damaged_unscored_gold_case,
    ],
    ids=lambda damage: damage.__name__,
)
def test_score_refuses_a_damaged_result_or_gold_file(damage):
    result, gold = fixture()
    damage(result, gold)
    with pytest.raises(ValueError):
        ps.score(result, gold)


# Thresholds


def entry(unnecessary=(0, 0), missed=(0, 0)) -> dict:
    """The two rates of a summary entry, each given as (k, n)."""
    return {
        "unnecessary_rate": {"k": unnecessary[0], "n": unnecessary[1]},
        "missed_rate": {"k": missed[0], "n": missed[1]},
    }


@pytest.mark.parametrize(
    ("d", "c_k", "expected"),
    [
        ((1, 5), 3, "met"),  # exactly 5 points; within a third; exactly C minus 2
        ((0, 4), 9, NA),  # 4 points: not assessable, whatever the counts
        ((2, 6), 4, "met"),  # exactly a third
        ((2, 5), 9, "failed"),  # more than a third
        ((1, 5), 2, "failed"),  # only 1 fewer than C
        ((0, 5), 2, "met"),  # exactly C minus 2
        ((0, 5), 1, "failed"),  # C below 2: D cannot be 2 fewer
    ],
    ids=[
        "five-points",
        "four-points",
        "a-third",
        "above-a-third",
        "c-minus-1",
        "c-minus-2",
        "c-below-2",
    ],
)
def test_t3(d, c_k, expected):
    got = ps.t3(entry(unnecessary=d), entry(unnecessary=(c_k, 9)))
    assert got == {
        "status": expected,
        "d_unnecessary": d[0],
        "d_no_search_needed_with_action": d[1],
        "c_unnecessary": c_k,
    }


@pytest.mark.parametrize(
    ("d", "c_k", "expected"),
    [
        ((1, 5), 0, "met"),  # exactly 5 points; exactly a fifth; exactly C plus 1
        ((0, 4), 0, NA),  # 4 points
        ((2, 10), 1, "met"),  # exactly a fifth and C plus 1
        ((2, 9), 5, "failed"),  # more than a fifth
        ((2, 10), 0, "failed"),  # C plus 2
    ],
    ids=["five-points", "four-points", "a-fifth", "above-a-fifth", "c-plus-2"],
)
def test_t4(d, c_k, expected):
    got = ps.t4(entry(missed=d), entry(missed=(c_k, 9)))
    assert got == {
        "status": expected,
        "d_missed": d[0],
        "d_search_needed_with_action": d[1],
        "c_missed": c_k,
    }


@pytest.mark.parametrize(
    ("d", "c", "complete", "expected"),
    [
        (4, 5, True, "met"),
        (3, 5, True, "failed"),
        (0, 0, True, "met"),
        (9, 9, False, NA),
    ],
)
def test_t1(d, c, complete, expected):
    assert ps.t1(d, c, complete) == {
        "status": expected,
        "d_successes": d,
        "c_successes": c,
    }


@pytest.mark.parametrize(
    ("d", "c", "complete", "expected"),
    [
        (2, 2, True, "met"),
        (3, 2, True, "failed"),
        (0, 4, True, "met"),
        (0, 0, False, NA),
    ],
)
def test_t2(d, c, complete, expected):
    assert ps.t2(d, c, complete) == {
        "status": expected,
        "d_unsupported": d,
        "c_unsupported": c,
    }


@pytest.mark.parametrize(
    ("d", "c", "gaps", "complete", "expected"),
    [
        (2, 2, 3, True, "met"),
        (1, 2, 3, True, "failed"),
        (2, 2, 2, True, NA),
        (3, 3, 5, False, NA),
    ],
)
def test_t5(d, c, gaps, complete, expected):
    assert ps.t5(d, c, gaps, complete) == {
        "status": expected,
        "d_gaps_ok": d,
        "c_gaps_ok": c,
        "gap_parts": gaps,
    }


@pytest.mark.parametrize(
    ("table", "expected"),
    [
        (
            [
                ("S3", False, True),
                ("S3", False, True),
                ("S3", True, False),
                ("S1", False, True),
                ("G", False, True),
            ],
            (NA, 2, 2),
        ),
        (
            [("S3", False, True), ("S3", False, True), ("S3", False, False)],
            ("met", 2, 3),
        ),
        (
            [("S3", False, True), ("S3", False, False), ("S3", False, False)],
            ("failed", 1, 3),
        ),
        (
            [
                ("S3", False, True),
                ("S3", False, True),
                ("S3", False, False),
                ("S3", False, False),
            ],
            ("met", 2, 4),
        ),
        (
            [
                ("S3", False, True),
                ("S3", False, False),
                ("S3", False, False),
                ("S3", False, False),
            ],
            ("failed", 1, 4),
        ),
    ],
    ids=["n-2", "n-3-k-2", "n-3-k-1", "2k-equals-n", "n-4-k-1"],
)
def test_r1(table, expected):
    got = ps.r1(table)
    assert (got["status"], got["k"], got["n"]) == expected


@pytest.mark.parametrize(
    ("table", "expected"),
    [
        ([("S3", True, True), ("G", True, False)], (NA, 0, 0, 0)),
        (
            [
                ("S1", True, True),
                ("S2", True, False),
                ("S1", True, True),
                ("S3", False, True),
            ],
            ("met", 3, 3, 2),
        ),
        (
            [("S1", True, False), ("S2", True, False), ("G", False, True)],
            ("failed", 2, 2, 0),
        ),
    ],
    ids=["empty-group", "b-minus-1", "b-minus-2"],
)
def test_r2(table, expected):
    got = ps.r2(table)
    assert (
        got["status"],
        got["cases"],
        got["b_successes"],
        got["d_successes"],
    ) == expected


INVALID = {
    "negative-count": lambda: ps.t1(-1, 0, True),
    "bool-count": lambda: ps.t2(True, 0, True),
    "complete-not-a-bool": lambda: ps.t1(1, 1, 1),
    "more-gaps-handled-than-gap-parts": lambda: ps.t5(4, 0, 3, True),
    "k-above-n": lambda: ps.t3(entry(unnecessary=(6, 5)), entry()),
    "no-rate": lambda: ps.t4({}, entry()),
    "unknown-stratum": lambda: ps.r1([("S4", False, True)]),
    "success-not-a-bool": lambda: ps.r2([("S1", 1, 0)]),
    "unknown-status": lambda: ps.primary_outcome(
        "met", "met", "met", "met", "pass", True
    ),
    "repetition-not-a-bool": lambda: ps.reference_outcome("met", "met", "yes"),
}


@pytest.mark.parametrize("name", list(INVALID))
def test_invalid_threshold_inputs_are_refused(name):
    with pytest.raises(ValueError):
        INVALID[name]()


# Outcome tables


def primary_rows(t1, t2, t3, t4, t5) -> list[str]:
    """The rows of the primary outcome table that apply, each written from the rubric."""
    supported = (t1, t2, t3, t4) == ("met",) * 4 and t5 in ("met", NA)
    not_adopted = "failed" in (t1, t2, t4, t5)
    no_benefit = (
        t3 in ("failed", NA) and (t1, t2, t4) == ("met",) * 3 and t5 in ("met", NA)
    )
    exploratory = t4 == NA and not (supported or not_adopted or no_benefit)
    rows = (
        ("supported", supported),
        ("not_adopted", not_adopted),
        ("no_benefit", no_benefit),
        ("exploratory", exploratory),
    )
    return [name for name, applies in rows if applies]


def test_every_combination_has_exactly_one_primary_outcome():
    for combo in itertools.product(("met", "failed", NA), repeat=5):
        assert ps.primary_outcome(*combo, False)["outcome"] == "no_verdict", combo
        if (
            NA in combo[:2]
        ):  # with repetition 1 complete, T1 and T2 are always assessable
            with pytest.raises(ValueError):
                ps.primary_outcome(*combo, True)
            continue
        rows = primary_rows(*combo)
        assert len(rows) == 1, combo
        assert ps.primary_outcome(*combo, True)["outcome"] == rows[0], combo


def test_primary_outcome_texts_are_the_rubrics():
    texts = {
        ("met", "met", "met", "met", NA): (
            "supported",
            "D supported: propose the coverage decision for the agent's UC2 use "
            "(ADR-027, proposed)",
        ),
        ("met", "met", "met", "met", "failed"): ("not_adopted", "D not adopted"),
        ("met", "met", NA, "met", "met"): ("no_benefit", "No benefit shown"),
        ("met", "met", "met", NA, "met"): (
            "exploratory",
            "Not established, reported as exploratory",
        ),
    }
    for statuses, (code, text) in texts.items():
        assert ps.primary_outcome(*statuses, True) == {"outcome": code, "text": text}
    assert ps.primary_outcome(*["met"] * 5, False) == {
        "outcome": "no_verdict",
        "text": "not established",
    }
    # the threshold functions' own results are accepted as they are
    assert (
        ps.primary_outcome(
            ps.t1(5, 5, True),
            ps.t2(0, 0, True),
            ps.t3(entry(unnecessary=(0, 6)), entry(unnecessary=(3, 9))),
            ps.t4(entry(missed=(1, 5)), entry(missed=(1, 9))),
            ps.t5(1, 1, 2, True),
            True,
        )["outcome"]
        == "supported"
    )


def reference_rows(r1, r2) -> list[str]:
    """The rows of the reference outcome table that apply, each written from the rubric."""
    rows = (
        ("no_recommendation", r2 == NA),
        ("fixed10_everywhere", r2 == "failed"),
        ("d_beyond_top10", r2 == "met" and r1 == "met"),
        ("no_gain", r2 == "met" and r1 == "failed"),
        ("beyond_not_established", r2 == "met" and r1 == NA),
    )
    return [name for name, applies in rows if applies]


def test_every_combination_has_exactly_one_reference_outcome():
    for r1, r2 in itertools.product(("met", "failed", NA), repeat=2):
        rows = reference_rows(r1, r2)
        assert len(rows) == 1, (r1, r2)
        assert ps.reference_outcome(r1, r2, True)["outcome"] == rows[0]
        assert ps.reference_outcome(r1, r2, False)["outcome"] == "no_verdict"


def test_reference_outcome_texts_are_the_rubrics():
    texts = {
        ("met", NA): ("no_recommendation", "No reference recommendation"),
        ("met", "failed"): (
            "fixed10_everywhere",
            "Fixed top 10 stays the default for every question",
        ),
        ("met", "met"): (
            "d_beyond_top10",
            "D recommended for UC2 questions whose evidence may "
            "lie beyond the top 10; fixed top 10 stays the default otherwise",
        ),
        ("failed", "met"): (
            "no_gain",
            "Fixed top 10 stays the default for every question; no "
            "gain of D over B shown",
        ),
        (NA, "met"): (
            "beyond_not_established",
            "Fixed top 10 stays the default; the "
            "beyond-top-10 benefit is not established",
        ),
    }
    for (r1, r2), (code, text) in texts.items():
        assert ps.reference_outcome(r1, r2, True) == {"outcome": code, "text": text}
    assert ps.reference_outcome(ps.r1([]), ps.r2([]), False) == {
        "outcome": "no_verdict",
        "text": "not established",
    }


# The command line


def write_inputs(folder: Path) -> tuple[Path, Path]:
    result, gold = fixture()
    paths = (folder / "result.json", folder / "gold.json")
    for path, value in zip(paths, (result, gold), strict=True):
        path.write_text(json.dumps(value), encoding="utf-8")
    return paths


def test_main_writes_the_scoring_and_prints_only_counts(tmp_path, capsys):
    result_path, gold_path = write_inputs(tmp_path)
    out = tmp_path / "scoring.json"
    args = [
        "--result",
        str(result_path),
        "--gold",
        str(gold_path),
        "--label",
        "SIMULATED",
    ]
    assert ps.main([*args, "--out", str(out)]) == 0
    printed = capsys.readouterr()
    written = json.loads(out.read_text(encoding="utf-8"))
    scored = ps.score(*fixture())
    assert written == {
        "label": "SIMULATED",
        "score": scored,
        "summary": ps.summary(scored),
    }
    assert json.loads(printed.out) == {
        "label": "SIMULATED",
        "summary": written["summary"],
    }
    for name in ("X-01", "X-02", "jul/", "R1", "R2"):
        assert name not in printed.out
        assert name not in printed.err
    again = tmp_path / "again.json"  # as a script from another folder: the same bytes
    run = subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--out", str(again)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert again.read_bytes() == out.read_bytes()
    assert str(tmp_path) not in out.read_text(encoding="utf-8")


def test_main_refuses_results_and_an_existing_out_before_reading_any_input(
    tmp_path, capsys
):
    before = sorted(p.name for p in ps.RESULTS.iterdir())
    absent = tmp_path / "absent.json"  # never read: the refusal comes first
    args = ["--result", str(absent), "--gold", str(absent), "--out"]
    for out in (
        ps.RESULTS / "phase4-scoring-test.json",
        ps.RESULTS / "deeper" / "phase4-scoring-test.json",
        ps.HERE / "RESULTS" / "phase4-scoring-test.json",
    ):  # another letter case
        assert ps.main([*args, str(out)]) == 2
        assert not out.exists()
    assert sorted(p.name for p in ps.RESULTS.iterdir()) == before
    assert capsys.readouterr().err.count("results/") >= 2
    kept = tmp_path / "kept.json"
    kept.write_text("kept", encoding="utf-8")
    assert ps.main([*args, str(kept)]) == 2
    assert kept.read_text(encoding="utf-8") == "kept"
    assert "already exists" in capsys.readouterr().err
    assert ps.main([*args, str(tmp_path / "no-such-folder" / "scoring.json")]) == 2
    assert "existing folder" in capsys.readouterr().err


def test_main_refuses_invalid_inputs_without_writing(tmp_path, capsys):
    result_path, gold_path = write_inputs(tmp_path)
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    gold["cases"] = gold["cases"][1:]  # X-01 is no longer in the gold file
    gold_path.write_text(json.dumps(gold), encoding="utf-8")
    out = tmp_path / "scoring.json"
    args = ["--result", str(result_path), "--gold", str(gold_path), "--out", str(out)]
    assert ps.main(args) == 2
    assert not out.exists()
    err = capsys.readouterr().err
    assert "not in the gold file" in err
    assert "X-01" not in err
    result_path.write_text("{not json", encoding="utf-8")
    assert ps.main(args) == 2
    assert not out.exists()
