"""Deterministic Phase 4 scoring of a comparison run against the frozen gold parts (offline).

It implements the frozen rubric (``phase4/rubric-and-thresholds.md``) on the trace the frozen
condition contract describes (``phase4/conditions.md``, section 5):

- ``strata``: a case's stratum from the shared top 10 and the frozen sets of equivalent
  passages (S1, S2, S3 or G, flagged when fact and gap parts are mixed).
- ``decision_points``: per recorded call of a C (``agent``) or D (``coverage``) cell, its
  capacity, anomaly flag, action and, at a decision point, its kind, the search measure it counts
  towards and its yield. Capacity alone decides: never the tool choice sent (a disagreement is an
  anomaly) and never D's own coverage record, which is not read. B (``fixed10``) has none.
- ``score`` (case level, local only: case, part and passage IDs) and ``summary`` (per-condition
  counts only, which may be shown).
- ``t1`` to ``t5``, ``r1``, ``r2``, ``primary_outcome`` and ``reference_outcome``: the decision
  thresholds and both outcome tables as pure functions.

The trace: every call of a cell except one that ended it ended in a tool use that ran one search
request, so ``record["searches"][i]`` belongs to call i + 1. The initial passages are the first
``len(supplied)`` minus all returned passages of ``record["supplied"]``. Before call k come those
and what the searches of calls 1 to k - 1 returned, in order; the rounds used before it are those
searches whose round is not None. A cell can end after a search, before its next call was
recorded (the deadline, or a refusal before the reservation): that call is not in the trace and
is no decision point. A trace that cannot be rebuilt is refused, never scored in part.

No model, provider, network or books: it reads two JSON files and writes one new file outside
``results/``; stdout carries the per-condition counts and the label only.

    UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" uv run \\
        --project services/ingestion --frozen --offline --extra ai --extra dev \\
        python tools/commentary_rag/phase4_scoring.py --result <local result.json> \\
        --gold <gold file> --out <a new file outside results/> [--label SIMULATED]

Exit codes: 0 written, 2 invalid input (nothing written).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import evidence_agent
import evidence_search

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"  # public: case-level scoring is never written here
EXIT_OK, EXIT_INPUT = 0, 2
LIMITS = evidence_search.SearchLimits()  # the bounds every comparison cell runs with
TOP = 10  # the shared ranking: B's fixed context and the strata's horizon
FIRST = 5  # C's and D's initial context: S1 is support within ranks 1 to 5
MIN_POINTS = 5  # T3 and T4: decision points with an action D needs
MIN_GAP_PARTS = 3  # T5
MIN_R1_CASES = 3  # R1
CONDITIONS = ("fixed10", "agent", "coverage")  # B, C, D
SEARCHING = ("agent", "coverage")
KINDS = ("search_needed", "gap_check", "no_search_needed")
RUN = (
    "passages",
    "no_new_passages",
    "tool_error",
)  # a search request that was executed
ANSWERED = (
    "answer",
    "invalid_answer",
)  # the call ended in an answer turn, accepted or not
ENDED = (
    "incomplete_generation",
    "protocol_error",
    "provider_error",
    "deadline",
    "refused",
    "persistence_error",
    "spending_stop",
)  # every other way evidence_agent ends a cell
# The search measure a decision point counts towards, by its kind and action (rubric).
MEASURES = {
    ("search_needed", "search_run"): "warranted",
    ("search_needed", "answer"): "missed",
    ("search_needed", "search_refused"): "missed",
    ("no_search_needed", "search_run"): "unnecessary",
    ("gap_check", "search_run"): "gap_check_search",
}
STATUSES = ("met", "failed", "not_assessable")
STRATA = ("S1", "S2", "S3", "G")
NO_VERDICT = "not established"  # repetition 1 incomplete: no verdict (rubric)
PRIMARY = {
    "supported": "D supported: propose the coverage decision for the agent's UC2 use "
    "(ADR-027, proposed)",
    "not_adopted": "D not adopted",
    "no_benefit": "No benefit shown",
    "exploratory": "Not established, reported as exploratory",
    "no_verdict": NO_VERDICT,
}
REFERENCE = {
    "no_recommendation": "No reference recommendation",
    "fixed10_everywhere": "Fixed top 10 stays the default for every question",
    "d_beyond_top10": "D recommended for UC2 questions whose evidence may lie beyond the top "
    "10; fixed top 10 stays the default otherwise",
    "no_gain": "Fixed top 10 stays the default for every question; no gain of D over B shown",
    "beyond_not_established": "Fixed top 10 stays the default; the beyond-top-10 benefit is "
    "not established",
    "no_verdict": NO_VERDICT,
}


def _text(value) -> bool:
    return isinstance(value, str) and bool(value)


def _ids(value) -> bool:
    """Whether ``value`` is a list of distinct, non-empty strings."""
    return (
        isinstance(value, list)
        and all(_text(v) for v in value)
        and len(set(value)) == len(value)
    )


def _count(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a count (a non-negative integer)")
    return value


def _flag(value, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false")
    return value


def _calls(condition: str) -> int:
    """The generation calls of a searching condition; D's are C's (conditions.md, section 4)
    for as long as ``evidence_agent.CONDITIONS`` does not name D."""
    known = evidence_agent.CONDITIONS
    return (known[condition] if condition in known else known["agent"]).calls


def _parts(parts) -> list[tuple[str, str, frozenset]]:
    """The frozen parts of one case as (id, kind, supporting passage IDs); a gap has none."""
    if not isinstance(parts, list) or not 1 <= len(parts) <= 4:
        raise ValueError("a case has 1 to 4 required parts")
    checked = []
    for part in parts:
        if (
            not isinstance(part, dict)
            or not _text(part.get("id"))
            or part.get("kind") not in ("fact", "gap")
        ):
            raise ValueError("every part needs an id and the kind fact or gap")
        support = part.get("support", [])
        if not isinstance(support, list) or not all(
            isinstance(s, dict) and _text(s.get("passage_id")) for s in support
        ):
            raise ValueError("a part's support lists passages by their passage_id")
        if bool(support) != (part["kind"] == "fact"):
            raise ValueError(
                "a fact part has supporting passages and a gap part has none"
            )
        checked.append(
            (part["id"], part["kind"], frozenset(s["passage_id"] for s in support))
        )
    if len({part_id for part_id, _, _ in checked}) != len(checked):
        raise ValueError("the parts of a case need distinct ids")
    return checked


def strata(parts, ranking) -> dict:
    """The stratum of one case from its frozen parts and the shared ranking (rubric, Strata).

    ``best_rank`` gives each fact part the best rank of a supporting passage within the top 10,
    or None. S1: every fact part within ranks 1 to 5; S2: every one within 1 to 10, some only at
    6 to 10; S3: some fact part not within 1 to 10; G: every part a gap. A case of fact and gap
    parts takes its fact parts' stratum and is flagged ``mixed``.
    """
    checked = _parts(parts)
    if not _ids(ranking):
        raise ValueError("a ranking is a list of distinct passage IDs")
    rank = {passage: n for n, passage in enumerate(ranking[:TOP], start=1)}
    best = {
        part_id: min((rank[s] for s in support if s in rank), default=None)
        for part_id, kind, support in checked
        if kind == "fact"
    }
    if not best:
        stratum = "G"
    elif None in best.values():
        stratum = "S3"
    elif all(r <= FIRST for r in best.values()):
        stratum = "S1"
    else:
        stratum = "S2"
    mixed = bool(best) and any(kind == "gap" for _, kind, _ in checked)
    return {"stratum": stratum, "mixed": mixed, "best_rank": best}


def _checked_record(record, condition: str) -> None:
    """Refuse a record that is not one ``evidence_agent`` writes for this condition."""
    if not isinstance(record, dict) or record.get("condition") != condition:
        raise ValueError("a cell's record must be a record of the cell's condition")
    calls, searches = record.get("calls"), record.get("searches")
    if (
        not isinstance(calls, list)
        or not isinstance(searches, list)
        or not _ids(record.get("supplied"))
    ):
        raise ValueError(
            "a record needs its calls, its searches and the supplied passage IDs"
        )
    if record.get("outcome") not in ANSWERED + ENDED:
        raise ValueError(
            "a record's outcome must be one evidence_agent ends a cell with"
        )
    if not all(
        isinstance(call, dict) and call.get("call") == number
        for number, call in enumerate(calls, start=1)
    ):
        raise ValueError("a record's calls are numbered from 1, in order")
    sent = record.get("generation_calls")
    if (
        isinstance(sent, bool)
        or not isinstance(sent, int)
        or not 0 <= sent <= len(calls)
    ):
        raise ValueError("a record's generation_calls counts the calls it sent")
    if condition not in SEARCHING and searches:
        raise ValueError("a fixed condition never searches")


def _trace(record, condition: str) -> tuple[list, list, list]:
    """The calls, searches and initial passages of a C or D record, refused when the trace
    cannot be rebuilt as conditions.md, section 5, states it."""
    _checked_record(record, condition)
    calls, searches, supplied = record["calls"], record["searches"], record["supplied"]
    if any(call.get("tool_choice") not in ("auto", "none") for call in calls):
        raise ValueError(
            "every call of a searching cell sent the tool choice auto or none"
        )
    if len(searches) not in (len(calls) - 1, len(calls)) or (
        len(searches) == len(calls) and record["outcome"] in ANSWERED
    ):
        raise ValueError(
            "every call except one that ended the cell ran one search request"
        )
    returned = []
    for number, search in enumerate(searches, start=1):
        if not isinstance(search, dict) or not isinstance(search.get("returned"), list):
            raise ValueError(
                "a search record needs its outcome, round and returned passages"
            )
        outcome = search.get("outcome")
        if not isinstance(outcome, str) or (
            outcome not in RUN and not outcome.startswith("refused_")
        ):
            raise ValueError(
                "a search outcome is passages, no_new_passages, tool_error or refused_*"
            )
        counted = search.get("round")
        if outcome == "refused_rounds":
            numbered = counted is None
        else:
            numbered = (
                isinstance(counted, int)
                and not isinstance(counted, bool)
                and counted > 0
            )
        if not numbered:
            raise ValueError(
                "a search has a round unless it was refused for want of rounds"
            )
        if calls[number - 1]["tool_choice"] != "auto":
            raise ValueError("a search belongs to a call that was offered the tool")
        returned += [
            r.get("passage_id") if isinstance(r, dict) else None
            for r in search["returned"]
        ]
    first = len(supplied) - len(returned)
    if first < 0 or supplied[first:] != returned:
        raise ValueError(
            "the supplied passages must end with what the searches returned"
        )
    return calls, searches, supplied[:first]


def decision_points(record, parts, condition: str) -> list[dict]:
    """One entry per recorded call of a C or D cell (rubric, Search opportunities).

    Each entry: ``capacity`` (a decision point: not the condition's last call, a search round
    left and fewer than 10 passages supplied before it), ``anomaly`` (capacity and a tool choice
    of ``auto`` disagree), ``supplied_before``, ``rounds_before``, the fact parts
    ``missing_before`` (no passage of their frozen set supplied before the call), the ``action``
    (``search_run``, ``search_refused``, ``answer`` or ``no_action``) and the search outcome. At
    a decision point also its ``kind`` (``search_needed``, ``gap_check`` or ``no_search_needed``),
    the ``measure`` it counts towards (``warranted``, ``unnecessary``, ``gap_check_search``,
    ``missed`` or None) and, for a warranted search, its ``yield`` (a missing fact part covered
    by what it returned); otherwise these are None. A B cell, or one without a record, has none.
    """
    if condition not in CONDITIONS:
        raise ValueError("the condition must be fixed10, agent or coverage")
    checked = _parts(parts)
    if record is None or condition not in SEARCHING:
        return []
    calls, searches, initial = _trace(record, condition)
    facts = [(part_id, support) for part_id, kind, support in checked if kind == "fact"]
    gaps = any(kind == "gap" for _, kind, _ in checked)
    supplied, rounds, points = list(initial), 0, []
    for number, call in enumerate(calls, start=1):
        search = searches[number - 1] if number <= len(searches) else None
        capacity = (
            number < _calls(condition)
            and rounds < LIMITS.max_rounds
            and len(supplied) < LIMITS.max_passages
        )
        before = set(supplied)
        missing = [part_id for part_id, support in facts if not support & before]
        returned = [r["passage_id"] for r in search["returned"]] if search else []
        if search is None:  # the call that ended the cell
            action = "answer" if record["outcome"] in ANSWERED else "no_action"
        else:
            action = "search_run" if search["outcome"] in RUN else "search_refused"
        kind = measure = found = None
        if capacity:
            kind = (
                "search_needed"
                if missing
                else "gap_check"
                if gaps
                else "no_search_needed"
            )
            measure = MEASURES.get((kind, action))
            if measure == "warranted":
                found = any(
                    support & set(returned)
                    for part_id, support in facts
                    if part_id in missing
                )
        points.append(
            {
                "call": number,
                "capacity": capacity,
                "anomaly": capacity != (call["tool_choice"] == "auto"),
                "tool_choice": call["tool_choice"],
                "supplied_before": len(supplied),
                "rounds_before": rounds,
                "missing_before": missing,
                "kind": kind,
                "action": action,
                "search_outcome": search["outcome"] if search else None,
                "measure": measure,
                "yield": found,
            }
        )
        supplied += returned
        if search is not None and search["round"] is not None:
            rounds += 1
    return points


def _counts(points: list[dict], searches: list[dict]) -> dict:
    """The search measures of one C or D cell: counts only."""
    at = [p for p in points if p["capacity"]]
    acted = [p for p in at if p["action"] != "no_action"]
    measures = Counter(p["measure"] for p in at)
    refused = Counter(p["kind"] for p in at if p["action"] == "search_refused")
    return {
        "searches": len(searches),
        "tool_errors": sum(s["outcome"] == "tool_error" for s in searches),
        "refused_searches": {
            "total": sum(s["outcome"].startswith("refused_") for s in searches),
            **{kind: refused[kind] for kind in KINDS},
        },
        "decision_points": {
            kind: {
                "with_action": sum(p["kind"] == kind for p in acted),
                "without_action": sum(
                    p["kind"] == kind and p["action"] == "no_action" for p in at
                ),
            }
            for kind in KINDS
        },
        "warranted": measures["warranted"],
        "unnecessary": measures["unnecessary"],
        "gap_check_searches": measures["gap_check_search"],
        "missed": measures["missed"],
        "yield": {"k": sum(p["yield"] is True for p in at), "n": measures["warranted"]},
        "anomalies": sum(p["anomaly"] for p in points),
        "unnecessary_rate": {
            "k": measures["unnecessary"],
            "n": sum(p["kind"] == "no_search_needed" for p in acted),
        },
        "missed_rate": {
            "k": measures["missed"],
            "n": sum(p["kind"] == "search_needed" for p in acted),
        },
    }


def _gold(gold) -> dict[str, dict]:
    """The gold cases by ID, every case's editions and parts checked."""
    cases = gold.get("cases") if isinstance(gold, dict) else None
    if not isinstance(cases, list) or not all(
        isinstance(c, dict)
        and _text(c.get("id"))
        and _ids(c.get("editions"))
        and c["editions"]
        for c in cases
    ):
        raise ValueError(
            "a gold file holds a list of cases, each with an id and its editions"
        )
    frozen = {case["id"]: case for case in cases}
    if len(frozen) != len(cases):
        raise ValueError("the gold file names a case twice")
    for case in cases:
        _parts(case.get("parts"))
    return frozen


def _cell(cell: dict, parts) -> dict:
    condition, record = cell["condition"], cell.get("record")
    if record is not None:
        _checked_record(record, condition)
    points = decision_points(record, parts, condition)
    searches = record["searches"] if record else []
    return {
        "condition": condition,
        "recorded": record is not None,
        "outcome": record["outcome"] if record else None,
        "calls": record["generation_calls"] if record else None,
        "searches": len(searches),
        "decision_points": points,
        "counts": _counts(points, searches) if condition in SEARCHING else None,
    }


def _case(case: dict, frozen: dict) -> dict:
    if not _ids(case.get("editions")) or sorted(case["editions"]) != sorted(
        frozen["editions"]
    ):
        raise ValueError("a case's editions must be those of its gold case")
    cells = case.get("cells")
    if not isinstance(cells, list) or not all(
        isinstance(c, dict) and c.get("condition") in CONDITIONS for c in cells
    ):
        raise ValueError(
            "every cell names one of the conditions fixed10, agent and coverage"
        )
    named = [c["condition"] for c in cells]
    if len(set(named)) != len(named):
        raise ValueError("a case has at most one cell per condition")
    kinds = [kind for _, kind, _ in _parts(frozen["parts"])]
    return {
        "case": case["case"],
        **strata(frozen["parts"], case.get("ranking")),
        "fact_parts": kinds.count("fact"),
        "gap_parts": kinds.count("gap"),
        "cells": [_cell(c, frozen["parts"]) for c in cells],
    }


def score(result, gold) -> dict:
    """The case-level scoring of one comparison run: LOCAL only (case, part and passage IDs).

    ``result`` is the local ``result.json`` of ``run_comparison.py``. Per case its stratum and
    part counts; per cell its outcome, calls sent, searches, ``decision_points`` and ``counts``
    (None for B: the search measures do not apply). Every case of the result must be in the gold
    file with the same editions; a gold case without a result is not scored.
    """
    frozen = _gold(gold)
    cases = result.get("cases") if isinstance(result, dict) else None
    if not isinstance(cases, list) or not all(isinstance(c, dict) for c in cases):
        raise ValueError("a result holds a list of cases")
    names = [case.get("case") for case in cases]
    if not all(_text(name) for name in names) or len(set(names)) != len(names):
        raise ValueError("every case of the result needs its own case ID")
    unknown = sum(name not in frozen for name in names)
    if unknown:
        raise ValueError(f"{unknown} case(s) of the result are not in the gold file")
    return {"cases": [_case(case, frozen[case["case"]]) for case in cases]}


def _histogram(values) -> dict[str, int]:
    """How many cells had each value, keyed by the value as text."""
    return {str(value): number for value, number in sorted(Counter(values).items())}


def _added(total: dict, more: dict) -> dict:
    """Two count dictionaries of the same shape, added key by key."""
    return {
        key: _added(value, more[key]) if isinstance(value, dict) else value + more[key]
        for key, value in total.items()
    }


def summary(scored: dict) -> dict:
    """Per-condition counts of a ``score`` result: no case ID, no passage ID, no list in case
    order. Calls per cell are the generation calls sent and searches per cell include refused
    requests, both over the cells with a record; B gets its cells and calls only."""
    conditions = {}
    for condition in CONDITIONS:
        cells = [
            c
            for case in scored["cases"]
            for c in case["cells"]
            if c["condition"] == condition
        ]
        recorded = [c for c in cells if c["recorded"]]
        entry = {
            "cells": len(cells),
            "without_record": len(cells) - len(recorded),
            "calls_per_cell": _histogram(c["calls"] for c in recorded),
        }
        if condition in SEARCHING:
            total = _counts([], [])
            for c in cells:
                total = _added(total, c["counts"])
            entry.update(
                total, searches_per_cell=_histogram(c["searches"] for c in recorded)
            )
        conditions[condition] = entry
    return {"conditions": conditions}


def _rate(entry, name: str) -> tuple[int, int]:
    """(k, n) of one rate of a ``summary`` entry, checked."""
    rate = entry.get(name) if isinstance(entry, dict) else None
    if not isinstance(rate, dict):
        raise ValueError(f"a summary entry with {name} is needed")
    k, n = _count(rate.get("k"), f"{name} k"), _count(rate.get("n"), f"{name} n")
    if k > n:
        raise ValueError(f"{name}: k cannot exceed n")
    return k, n


def t3(d: dict, c: dict) -> dict:
    """T3, fewer unnecessary searches (``d`` and ``c``: D's and C's ``summary`` entries).

    Met when D's unnecessary searches are at most a third of D's no-search-needed decision
    points with an action and at least 2 fewer than C's; assessable when D has at least 5 such
    decision points.
    """
    d_k, d_n = _rate(d, "unnecessary_rate")
    c_k, _ = _rate(c, "unnecessary_rate")
    if d_n < MIN_POINTS:
        status = "not_assessable"
    else:
        status = "met" if 3 * d_k <= d_n and d_k <= c_k - 2 else "failed"
    return {
        "status": status,
        "d_unnecessary": d_k,
        "d_no_search_needed_with_action": d_n,
        "c_unnecessary": c_k,
    }


def t4(d: dict, c: dict) -> dict:
    """T4, no more missed useful searches (``d`` and ``c``: D's and C's ``summary`` entries).

    Met when D's missed useful searches are at most C's plus 1 and at most a fifth of D's
    search-needed decision points with an action; assessable when D has at least 5 of them.
    """
    d_k, d_n = _rate(d, "missed_rate")
    c_k, _ = _rate(c, "missed_rate")
    if d_n < MIN_POINTS:
        status = "not_assessable"
    else:
        status = "met" if d_k <= c_k + 1 and 5 * d_k <= d_n else "failed"
    return {
        "status": status,
        "d_missed": d_k,
        "d_search_needed_with_action": d_n,
        "c_missed": c_k,
    }


def t1(d_successes: int, c_successes: int, complete: bool) -> dict:
    """T1, quality kept: D's full case successes at least C's minus 1 (repetition 1 complete)."""
    d, c = _count(d_successes, "d_successes"), _count(c_successes, "c_successes")
    if _flag(complete, "complete"):
        status = "met" if d >= c - 1 else "failed"
    else:
        status = "not_assessable"
    return {"status": status, "d_successes": d, "c_successes": c}


def t2(d_unsupported: int, c_unsupported: int, complete: bool) -> dict:
    """T2, no added unsupported claims: D's at most C's (repetition 1 complete)."""
    d, c = (
        _count(d_unsupported, "d_unsupported"),
        _count(c_unsupported, "c_unsupported"),
    )
    if _flag(complete, "complete"):
        status = "met" if d <= c else "failed"
    else:
        status = "not_assessable"
    return {"status": status, "d_unsupported": d, "c_unsupported": c}


def t5(d_gaps_ok: int, c_gaps_ok: int, gap_parts: int, complete: bool) -> dict:
    """T5, gaps kept: D's correctly handled gap parts at least C's; assessable with at least 3
    gap parts in the complete repetition."""
    d, c = _count(d_gaps_ok, "d_gaps_ok"), _count(c_gaps_ok, "c_gaps_ok")
    parts = _count(gap_parts, "gap_parts")
    if d > parts or c > parts:
        raise ValueError("correctly handled gap parts cannot exceed the gap parts")
    if _flag(complete, "complete") and parts >= MIN_GAP_PARTS:
        status = "met" if d >= c else "failed"
    else:
        status = "not_assessable"
    return {"status": status, "d_gaps_ok": d, "c_gaps_ok": c, "gap_parts": parts}


def _rows(rows) -> list[tuple[str, bool, bool]]:
    """Rows of (stratum, B's full case success, D's full case success), checked."""
    if not isinstance(rows, (list, tuple)):
        raise ValueError("the rows are a list of (stratum, B success, D success)")
    checked = []
    for row in rows:
        if (
            not isinstance(row, (list, tuple))
            or len(row) != 3
            or row[0] not in STRATA
            or not all(isinstance(v, bool) for v in row[1:])
        ):
            raise ValueError(
                "a row is (stratum, B's full case success, D's full case success)"
            )
        checked.append((row[0], row[1], row[2]))
    return checked


def r1(rows) -> dict:
    """R1, beyond the top 10: n is the S3 cases in which B has no full case success, k those of
    them in which D has; met when 2k is at least n, assessable when n is at least 3."""
    group = [d for stratum, b, d in _rows(rows) if stratum == "S3" and not b]
    n, k = len(group), sum(group)
    if n < MIN_R1_CASES:
        status = "not_assessable"
    else:
        status = "met" if 2 * k >= n else "failed"
    return {"status": status, "k": k, "n": n}


def r2(rows) -> dict:
    """R2, within the top 10: in the S1 and S2 cases, D's full case successes at least B's minus
    1; assessable when the group is not empty."""
    group = [(b, d) for stratum, b, d in _rows(rows) if stratum in ("S1", "S2")]
    b, d = sum(x for x, _ in group), sum(y for _, y in group)
    if not group:
        status = "not_assessable"
    else:
        status = "met" if d >= b - 1 else "failed"
    return {"status": status, "cases": len(group), "b_successes": b, "d_successes": d}


def _status(value, name: str) -> str:
    """A threshold's status, given as the string or as the dict a threshold function returns."""
    status = value.get("status") if isinstance(value, dict) else value
    if not isinstance(status, str) or status not in STATUSES:
        raise ValueError(f"{name} must be met, failed or not_assessable")
    return status


def primary_outcome(t1, t2, t3, t4, t5, repetition_complete) -> dict:  # noqa: PLR0913
    """The primary outcome, D against C, from T1 to T5: exactly one per combination.

    With repetition 1 incomplete there is no verdict ("not established"). With it complete, T1
    and T2 are always assessable, so a T1 or T2 not assessable is refused, not given an outcome.
    """
    s1, s2, s3, s4, s5 = (
        _status(t, f"T{n}") for n, t in enumerate((t1, t2, t3, t4, t5), start=1)
    )
    if not _flag(repetition_complete, "repetition_complete"):
        code = "no_verdict"
    elif "not_assessable" in (s1, s2):
        raise ValueError("with repetition 1 complete, T1 and T2 are assessable")
    elif "failed" in (s1, s2, s4, s5):
        code = "not_adopted"  # whatever T3 shows
    elif s4 == "not_assessable":
        code = "exploratory"  # no rule above applies
    else:
        code = "supported" if s3 == "met" else "no_benefit"
    return {"outcome": code, "text": PRIMARY[code]}


def reference_outcome(r1, r2, repetition_complete) -> dict:
    """The reference outcome, D against B, from R1 and R2: exactly one per combination. It
    informs the single-call default only; with repetition 1 incomplete there is no verdict."""
    s1, s2 = _status(r1, "R1"), _status(r2, "R2")
    if not _flag(repetition_complete, "repetition_complete"):
        code = "no_verdict"
    elif s2 == "not_assessable":
        code = "no_recommendation"
    elif s2 == "failed":
        code = "fixed10_everywhere"
    else:
        code = {
            "met": "d_beyond_top10",
            "failed": "no_gain",
            "not_assessable": "beyond_not_established",
        }[s1]
    return {"outcome": code, "text": REFERENCE[code]}


def _public(path: Path) -> bool:
    """Whether ``path`` lies in ``results/``, however it is spelled (a link, another case)."""
    target = path.resolve()
    if target.is_relative_to(RESULTS.resolve()):
        return True
    return RESULTS.is_dir() and any(
        folder.exists() and os.path.samefile(folder, RESULTS)
        for folder in (target, *target.parents)
    )


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except RecursionError:
        raise ValueError("a JSON input nests too deeply") from None


def _refuse(reason: str) -> int:
    print(f"refused: {reason}", file=sys.stderr)
    return EXIT_INPUT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--result",
        type=Path,
        required=True,
        help="the LOCAL result.json of a comparison run",
    )
    parser.add_argument("--gold", type=Path, required=True, help="the frozen gold file")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="the new JSON file for the case-level scoring, outside results/",
    )
    parser.add_argument(
        "--label", help="a label written with the scoring, e.g. SIMULATED"
    )
    args = parser.parse_args(argv)
    # Both refusals of the output come before any input is read.
    if _public(args.out):
        return _refuse(
            "--out lies in results/, which is public; case-level scoring stays local"
        )
    if args.out.exists() or args.out.is_symlink():
        return _refuse("--out already exists; a scoring never replaces a file")
    if not args.out.parent.is_dir():
        return _refuse("--out must name a file in an existing folder")
    try:
        inputs = (_load(args.result), _load(args.gold))
    except (OSError, ValueError) as exc:
        return _refuse(
            f"--result and --gold must be readable JSON files ({type(exc).__name__})"
        )
    try:
        scored = score(*inputs)
    except ValueError as exc:
        return _refuse(str(exc))
    counts = summary(scored)
    text = json.dumps(
        {"label": args.label, "score": scored, "summary": counts},
        ensure_ascii=False,
        indent=1,
        sort_keys=True,
    )
    try:
        with args.out.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text + "\n")
    except OSError as exc:
        return _refuse(f"--out could not be written ({type(exc).__name__})")
    print(
        json.dumps(
            {"label": args.label, "summary": counts},
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        )
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
