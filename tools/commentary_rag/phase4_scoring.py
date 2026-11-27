"""Deterministic Phase 4 scoring of comparison runs against the frozen gold parts (offline).

It implements the frozen rubric (``phase4/rubric-and-thresholds.md``) on the trace the frozen
condition contract describes (``phase4/conditions.md``, section 5):

- ``strata``: a case's stratum from the shared top 10 and the frozen sets of equivalent
  passages (S1, S2, S3 or G, flagged when fact and gap parts are mixed).
- ``decision_points``: per generation call of a C (``agent``) or D (``coverage``) cell, its
  capacity, anomaly flag, action and, at a decision point, its kind, the search measure it counts
  towards and its yield. Capacity alone decides: never the tool choice sent (a disagreement is an
  anomaly) and never D's own coverage record. B (``fixed10``) has none.
- ``score`` merges the local results of one repetition (a resumed run gives several) per case
  and condition: a cell ran when its record shows a generation call sent (one refused or
  stopped before any call is not run; one refused after a sent call ran and failed); the cell
  that ran is scored, two that ran are refused, and a case is complete when B, C and D all ran.
  ``summary`` gives counts only, which may be shown. D's coverage record enters only its
  exploratory diagnostics (counts), never a measure or a threshold.
- ``t1`` to ``t5``, ``r1``, ``r2``, ``primary_outcome`` and ``reference_outcome``: the decision
  thresholds and both outcome tables as pure functions.
- ``a1``: amendment A1 (``phase4/amendments.md``), reported beside T3 and never a threshold:
  unnecessary search attempts, an executed search or a refused search request at a
  no-search-needed decision point (once per point, for C and D alike), executed and refused
  apart, over T3's own denominator. ``search_thresholds`` gives T3, A1 and T4 from one
  ``summary``, whose completeness is the scoring's own, never a caller's.

A cell an unexpected error or an interruption ended inside the agent's loop is recorded by the
runner from the books (``run_comparison._aborted``, outcome ``aborted``): ``generation_calls``
counts the calls the books show as sent, so with one it ran and failed (a non-success, as the
rubric counts it); a reservation without a confirmed send confirms nothing. Its searches and
decisions were never recorded (``trace`` ``not_recorded``), so it has no decision point and adds
nothing to any search measure: no action is inferred for it, and the summary counts such cells
apart (``aborted``).

Every record names its repetition (Phase 4's books, ``evidence_agent.PHASE4_REPETITIONS``) and
its time budget (a finite number of seconds above 0); one scoring holds one repetition. The
repetition is complete when every gold case is complete in it, and the command line takes the
frozen gold file only (``FROZEN_GOLD_SHA256``), so neither a split batch nor a trimmed gold
file can look complete. A search refused for want of rounds (``refused_rounds``) is accepted
only after both rounds were used.

The trace: the generation calls are the sent ones, calls 1 to ``generation_calls`` (a call
reserved but stopped before sending is none). Every generation call except one that ended the
cell ended in a tool use that ran one search request, so ``record["searches"][i]`` belongs to
call i + 1. The initial passages are the first ``len(supplied)`` minus all returned passages of
``record["supplied"]``, and must be the top 5 of the case's ranking (a B cell's supplied passages
its top 10). Before call k come those and what the searches of calls 1 to k - 1 returned, in
order; the rounds used before it are those searches whose round is not None. A cell can end
after a search, before its next call was recorded: that call is no decision point. A record
that disagrees with its case or cannot be rebuilt is refused, never scored in part.

No model, provider, network or books: it reads JSON files and writes one new file, never in
``results/`` and in the repository only under this module's git-ignored ``local/`` folder,
which must be a real folder, not a symbolic link; stdout carries the counts, T3, A1 and T4 and
the label only.

    UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" uv run \\
        --project services/ingestion --frozen --offline --extra ai --extra dev \\
        python tools/commentary_rag/phase4_scoring.py --result <local result.json> \\
        [--result <the result.json of a resumed run> ...] --gold <the frozen gold file> \\
        --out <a new file under local/ or outside the repository> [--label SIMULATED]

Exit codes: 0 written, 2 invalid input (nothing written).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import evidence_agent
import evidence_search

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULTS = HERE / "results"  # public: case-level scoring is never written here
LOCAL = (
    HERE / "local"
)  # git-ignored: the one folder of the repository a scoring may go to
EXIT_OK, EXIT_INPUT = 0, 2
# The frozen gold (results/2026-11-25-phase4-freeze.json, role "private cases and gold"): the
# command line scores against this file and no other.
FROZEN_GOLD_SHA256 = "b4906698acdd439b7a599678b543887c7faf7e19422580f8a0c5b69efd1d541b"
LIMITS = evidence_search.SearchLimits()  # the bounds every comparison cell runs with
TOP = 10  # the shared ranking's depth: the strata's horizon
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
NOT_SENT = (
    "deadline",
    "persistence_error",
)  # how a cell ends with its last call unsent
ABORTED = "aborted"  # a cell the runner recorded from the books after an unexpected stop
CHECKS = (
    "ok",
    "malformed",
    "passage_reference",
    "search_for",
)  # D's coverage check codes
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


def _number(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _count(value, name: str) -> int:
    if not _number(value) or value < 0:
        raise ValueError(f"{name} must be a count (a non-negative integer)")
    return value


def _flag(value, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false")
    return value


def _condition(name: str):
    """A condition's bounds (``evidence_agent.CONDITIONS``); D's are C's (conditions.md,
    section 4) for as long as ``evidence_agent.CONDITIONS`` does not name D."""
    known = evidence_agent.CONDITIONS
    return known[name] if name in known else known["agent"]


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
    """Refuse a record that is not one ``evidence_agent`` writes for this condition, or, for an
    aborted cell, one ``run_comparison._aborted`` writes."""
    if not isinstance(record, dict) or record.get("condition") != condition:
        raise ValueError("a cell's record must be a record of the cell's condition")
    if record.get("outcome") == ABORTED:
        _checked_aborted(record)
        _checked_identity(record)
        return
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
    if not _number(sent) or not max(len(calls) - 1, 0) <= sent <= len(calls):
        raise ValueError(
            "generation_calls counts the calls sent: all calls, or all but the last"
        )
    if sent < len(calls) and record["outcome"] not in NOT_SENT:
        raise ValueError(
            "a reserved call stays unsent only when the deadline or a write stops it"
        )
    if condition not in SEARCHING and searches:
        raise ValueError("a fixed condition never searches")
    _checked_identity(record)


def _checked_aborted(record: dict) -> None:
    """Refuse an aborted record that is not one the runner writes: the calls the books show as
    sent, numbered from 1 and counted by ``generation_calls``, the unconfirmed ones apart, and
    no trace (no search, supplied or cited passage, coverage or answer count)."""
    calls, unconfirmed = record.get("calls"), record.get("unconfirmed_calls")
    if (
        record.get("trace") != "not_recorded"
        or not isinstance(calls, list)
        or not isinstance(unconfirmed, list)
        or any(
            key in record
            for key in ("searches", "supplied", "cited", "coverage", "schema_problems")
        )
    ):
        raise ValueError(
            "an aborted record holds the calls the books show as sent and no trace"
        )
    if not all(
        isinstance(call, dict) and call.get("call") == number and call.get("sent") is True
        for number, call in enumerate(calls, start=1)
    ):
        raise ValueError("an aborted record's calls are numbered from 1, each one sent")
    if not _number(record.get("generation_calls")) or record["generation_calls"] != len(
        calls
    ):
        raise ValueError("an aborted record's generation_calls counts its sent calls")
    if not all(
        isinstance(call, dict) and call.get("call") == number
        for number, call in enumerate(unconfirmed, start=len(calls) + 1)
    ):
        raise ValueError("an aborted record's unconfirmed calls follow its sent calls")


def _checked_identity(record: dict) -> None:
    """Refuse a record without a valid time budget or an admitted repetition."""
    if not evidence_agent._seconds(record.get("budget_s")):  # overflow included
        raise ValueError("a record's budget_s must be a finite number of seconds above 0")
    repetition = record.get("repetition")
    if (
        isinstance(repetition, bool)
        or not isinstance(repetition, int)
        or repetition not in evidence_agent.PHASE4_REPETITIONS
    ):
        raise ValueError(
            "a record names its repetition, one Phase 4's books admit "
            f"({', '.join(str(r) for r in evidence_agent.PHASE4_REPETITIONS)})"
        )


def _trace(record, condition: str) -> tuple[list, list, list]:
    """The sent calls, searches and initial passages of a C or D record, refused when the trace
    cannot be rebuilt as conditions.md, section 5, states it."""
    _checked_record(record, condition)
    calls, searches, supplied = record["calls"], record["searches"], record["supplied"]
    sent = calls[: record["generation_calls"]]
    if any(call.get("tool_choice") not in ("auto", "none") for call in calls):
        raise ValueError(
            "every call of a searching cell sent the tool choice auto or none"
        )
    if (
        len(searches) not in (len(sent) - 1, len(sent))
        or (len(searches) == len(sent) and record["outcome"] in ANSWERED)
        or (len(sent) < len(calls) and len(searches) != len(sent))
    ):
        raise ValueError(
            "every sent call except one that ended the cell ran one search request"
        )
    returned, rounds = [], 0
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
        if bool(search["returned"]) != (outcome == "passages"):
            raise ValueError(
                "a search returns passages exactly when its outcome is passages"
            )
        counted = search.get("round")
        if outcome == "refused_rounds":  # no round left: only after both were used
            numbered = counted is None and rounds == LIMITS.max_rounds
        else:
            rounds += 1
            numbered = (
                _number(counted) and counted == rounds and rounds <= LIMITS.max_rounds
            )
        if not numbered:
            raise ValueError(
                "counted search rounds are numbered 1 and 2, in order; a request "
                "refused for want of rounds has none and comes only after both"
            )
        if sent[number - 1]["tool_choice"] != "auto":
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
    return sent, searches, supplied[:first]


def _decisions(record, checked, condition: str) -> tuple[list[dict], list[str]]:
    """The decision points of a C or D record and its initial passages."""
    sent, searches, initial = _trace(record, condition)
    facts = [(part_id, support) for part_id, kind, support in checked if kind == "fact"]
    gaps = any(kind == "gap" for _, kind, _ in checked)
    supplied, rounds, points = list(initial), 0, []
    for number, call in enumerate(sent, start=1):
        search = searches[number - 1] if number <= len(searches) else None
        capacity = (
            number < _condition(condition).calls
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
    return points, list(initial)


def decision_points(record, parts, condition: str) -> list[dict]:
    """One entry per generation call (sent) of a C or D cell (rubric, Search opportunities).

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
    return _decisions(record, checked, condition)[0]


def _counts(points: list[dict], searches: list[dict]) -> dict:
    """The search measures of one C or D cell: counts only."""
    at = [p for p in points if p["capacity"]]
    acted = [p for p in at if p["action"] != "no_action"]
    measures = Counter(p["measure"] for p in at)
    refused = Counter(p["kind"] for p in at if p["action"] == "search_refused")
    # A1: an executed or a refused request at a no-search-needed point, once per point.
    attempts = measures["unnecessary"] + refused["no_search_needed"]
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
        "unnecessary_attempts": {
            "executed": measures["unnecessary"],
            "refused": refused["no_search_needed"],
            "total": attempts,
        },
        "unnecessary_attempt_rate": {
            "k": attempts,
            "n": sum(p["kind"] == "no_search_needed" for p in acted),
        },
        "missed_rate": {
            "k": measures["missed"],
            "n": sum(p["kind"] == "search_needed" for p in acted),
        },
    }


def _coverage(record, points: list[dict]) -> dict:
    """D's coverage diagnostics for one cell (exploratory, counts only, never a measure).

    From ``record["coverage"]`` (conditions.md, 4.8): check codes by action;
    ``missing_not_reported`` as true, false or null; and, at decision points whose entry has
    check ``ok``, the point's kind by whether D marked a part missing. Every entry must name a
    different sent call and carry that call's action.
    """
    diagnostics = {
        "checks": {action: dict.fromkeys(CHECKS, 0) for action in ("search", "answer")},
        "missing_not_reported": {"true": 0, "false": 0, "null": 0},
        "decision_points_with_ok_check": {
            kind: {"marked_missing": 0, "marked_all_covered": 0} for kind in KINDS
        },
        "records_without_coverage": 0,
    }
    entries = record.get("coverage") if record is not None else []
    if entries is None:
        diagnostics["records_without_coverage"] = 1
        return diagnostics
    if not isinstance(entries, list):
        raise ValueError("D's coverage record must be a list of coverage entries")
    by_call, seen = {p["call"]: p for p in points}, set()
    for entry in entries:
        flag = entry.get("missing_not_reported") if isinstance(entry, dict) else None
        if (
            not isinstance(entry, dict)
            or entry.get("action") not in ("search", "answer")
            or entry.get("check") not in CHECKS
            or not (flag is None or isinstance(flag, bool))
        ):
            raise ValueError(
                "a coverage entry needs its action, its check code and "
                "missing_not_reported (true, false or null)"
            )
        call = entry.get("call")
        point = by_call.get(call) if _number(call) else None
        if point is None or call in seen:
            raise ValueError("each coverage entry names a different sent call")
        seen.add(call)
        expected = (
            "search"
            if point["action"] in ("search_run", "search_refused")
            else "answer"
            if point["action"] == "answer"
            else None
        )
        if entry["action"] != expected:
            raise ValueError("a coverage entry's action must be the action of its call")
        diagnostics["checks"][entry["action"]][entry["check"]] += 1
        diagnostics["missing_not_reported"][
            "null" if flag is None else str(flag).lower()
        ] += 1
        if entry["check"] == "ok":
            missing = entry.get("missing")
            if not _number(missing) or missing < 0:
                raise ValueError(
                    "a coverage entry with check ok counts its missing parts"
                )
            if point["capacity"]:
                column = "marked_missing" if missing > 0 else "marked_all_covered"
                diagnostics["decision_points_with_ok_check"][point["kind"]][column] += 1
    return diagnostics


def _zero(condition: str) -> dict | None:
    """The counts of a cell that did not run (None for B: the measures do not apply)."""
    if condition not in SEARCHING:
        return None
    counts = _counts([], [])
    if condition == "coverage":
        counts["coverage_diagnostics"] = _coverage(None, [])
    return counts


def _scored_record(
    record, case_id: str, ranking: list, checked, condition: str
) -> dict:
    """One record, checked against its case and the case's ranking, with its decision points,
    counts and (for D) coverage diagnostics; refused when anything disagrees."""
    _checked_record(record, condition)
    if record.get("case") != case_id:
        raise ValueError("a cell's record must name the cell's case")
    if record["outcome"] == ABORTED:  # no trace recorded: no decision point, nothing inferred
        return {"points": [], "counts": _zero(condition)}
    top = ranking[: _condition(condition).passages]
    if condition not in SEARCHING:
        if record["supplied"] != top:
            raise ValueError("a B cell's passages must be the case's top 10")
        return {"points": [], "counts": None}
    points, initial = _decisions(record, checked, condition)
    if initial != top:
        raise ValueError("a C or D cell's initial passages must be the case's top 5")
    counts = _counts(points, record["searches"])
    if condition == "coverage":
        counts["coverage_diagnostics"] = _coverage(record, points)
    return {"points": points, "counts": counts}


def _merged_cell(
    condition: str, cells: list[dict], case_id: str, ranking: list, checked
) -> dict:
    """The cell of one case and condition over every result: every record is checked; a cell
    ran when its record shows at least one generation call sent; two that ran are refused; with
    none that ran the cell is not run (``outcome``: that of the last record seen, if any)."""
    scored = [
        (
            cell["record"],
            _scored_record(cell["record"], case_id, ranking, checked, condition),
        )
        for cell in cells
        if cell.get("record") is not None
    ]
    ran = [  # a generation call was sent: refused or stopped later, the cell still ran
        (record, result) for record, result in scored if record["generation_calls"] >= 1
    ]
    if len(ran) > 1:
        raise ValueError(
            "two cells of one case and condition ran: a cell is never run twice"
        )
    if not ran:
        return {
            "condition": condition,
            "ran": False,
            "outcome": scored[-1][0]["outcome"] if scored else None,
            "calls": None,
            "searches": 0,
            "decision_points": [],
            "counts": _zero(condition),
        }
    record, result = ran[0]
    return {
        "condition": condition,
        "ran": True,
        "outcome": record["outcome"],
        "calls": record["generation_calls"],
        # an aborted cell's searches were not recorded: not counted, never taken as none
        "searches": None if record["outcome"] == ABORTED else len(record["searches"]),
        "decision_points": result["points"],
        "counts": result["counts"],
    }


def _gold(gold) -> dict[str, dict]:
    """The gold cases by ID, every case's question, editions and parts checked."""
    cases = gold.get("cases") if isinstance(gold, dict) else None
    if not isinstance(cases, list) or not all(
        isinstance(c, dict)
        and _text(c.get("id"))
        and _text(c.get("question"))
        and _ids(c.get("editions"))
        and c["editions"]
        for c in cases
    ):
        raise ValueError(
            "a gold file holds a list of cases, each with an id, its question and "
            "its editions"
        )
    frozen = {case["id"]: case for case in cases}
    if len(frozen) != len(cases):
        raise ValueError("the gold file names a case twice")
    for case in cases:
        _parts(case.get("parts"))
    return frozen


def _merge(merged: dict, case: dict, frozen: dict) -> None:
    """Add one result's case to the cases merged so far, checked against its gold case."""
    if case.get("question") != frozen["question"]:
        raise ValueError("a case's question must be its gold case's question")
    if not _ids(case.get("editions")) or sorted(case["editions"]) != sorted(
        frozen["editions"]
    ):
        raise ValueError("a case's editions must be its gold case's editions")
    if not _ids(case.get("ranking")):
        raise ValueError("a ranking is a list of distinct passage IDs")
    cells = case.get("cells")
    if not isinstance(cells, list) or not all(
        isinstance(c, dict) and c.get("condition") in CONDITIONS for c in cells
    ):
        raise ValueError(
            "every cell names one of the conditions fixed10, agent and coverage"
        )
    named = [c["condition"] for c in cells]
    if len(set(named)) != len(named):
        raise ValueError("a case of one result has at most one cell per condition")
    known = merged.setdefault(
        case["case"], {"ranking": case["ranking"], "cells": {c: [] for c in CONDITIONS}}
    )
    if known["ranking"] != case["ranking"]:
        raise ValueError("a case must carry the same ranking in every result")
    for c in cells:
        known["cells"][c["condition"]].append(c)


def _case(name: str, merged: dict, frozen: dict) -> dict:
    checked = _parts(frozen["parts"])
    kinds = [kind for _, kind, _ in checked]
    cells = [
        _merged_cell(
            condition, merged["cells"][condition], name, merged["ranking"], checked
        )
        for condition in CONDITIONS
    ]
    return {
        "case": name,
        **strata(frozen["parts"], merged["ranking"]),
        "complete": all(c["ran"] for c in cells),
        "fact_parts": kinds.count("fact"),
        "gap_parts": kinds.count("gap"),
        "cells": cells,
    }


def score(results, gold) -> dict:
    """The case-level scoring of one repetition: LOCAL only (case, part and passage IDs).

    ``results`` is a list of local ``result.json`` files of ``run_comparison.py`` (several when
    a run was resumed), merged per case and condition. For the gold cases in any result, in the
    gold file's order: the stratum, part counts, ``complete`` (B, C and D all ran) and one cell
    per condition with ``ran``, its outcome, calls sent, searches, ``decision_points`` and
    ``counts`` (None for B: the search measures do not apply). Every result case must be in the
    gold file with its question and editions, and carry one ranking in every result; every
    record must name its case and start from the top of that ranking.
    """
    frozen = _gold(gold)
    if not isinstance(results, list) or not results:
        raise ValueError("score takes a list of one or more results")
    listed = []
    for result in results:
        cases = result.get("cases") if isinstance(result, dict) else None
        if not isinstance(cases, list) or not all(isinstance(c, dict) for c in cases):
            raise ValueError("a result holds a list of cases")
        names = [case.get("case") for case in cases]
        if not all(_text(name) for name in names) or len(set(names)) != len(names):
            raise ValueError("every case of a result needs its own case ID")
        listed += cases
    unknown = len({case["case"] for case in listed} - set(frozen))
    if unknown:
        raise ValueError(f"{unknown} case(s) of the results are not in the gold file")
    merged: dict[str, dict] = {}
    for case in listed:
        _merge(merged, case, frozen[case["case"]])
    scored = [
        _case(name, merged[name], frozen[name]) for name in frozen if name in merged
    ]
    # One repetition, one time budget per cell (conditions.md, section 1): the records are
    # checked above, so every cell that sent a call names its budget.
    budgets = {
        cell["record"].get("budget_s")
        for known in merged.values()
        for cells in known["cells"].values()
        for cell in cells
        if cell.get("record") is not None and cell["record"]["generation_calls"] >= 1
    }
    if len(budgets) > 1:
        raise ValueError("the cells of one repetition ran with different time budgets")
    # One scoring, one repetition: the records are checked above, so each names its own.
    repetitions = {
        cell["record"]["repetition"]
        for known in merged.values()
        for cells in known["cells"].values()
        for cell in cells
        if cell.get("record") is not None
    }
    if len(repetitions) > 1:
        raise ValueError("the records of one scoring belong to one repetition")
    # The frozen cohort: the gold names exactly the freeze record's cases, each with its
    # question's SHA-256 and its editions; a subset or another case set gives no verdict.
    cohort = {
        name: (
            hashlib.sha256(case["question"].encode("utf-8")).hexdigest(),
            tuple(sorted(case["editions"])),
        )
        for name, case in frozen.items()
    }
    return {
        "gold_cases": len(frozen),
        "frozen_cohort": cohort == evidence_agent.PHASE4_CASES,
        "repetition": next(iter(repetitions), None),
        "cases": scored,
    }


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
    """Counts of a ``score`` result, safe to show: no case ID, no passage ID, no list in case
    order.

    ``gold_cases``; ``repetition``; ``cases_in_results`` (gold cases in any result);
    ``complete_cases`` (B, C and D all ran) and ``incomplete_cases`` (the other cases in the
    results; a gold case in no result is neither); ``frozen_cohort`` (the gold names exactly
    the freeze record's cases, questions and editions); ``repetition_complete``, true exactly
    when the cohort is the frozen one and ``complete_cases`` equals ``gold_cases``. Per
    condition: its cells (one per case in the results), those ``not_run``,
    calls per cell (generation calls sent) and searches per cell (refused requests included)
    over the cells that ran (an ``aborted`` cell, counted apart, has calls but no recorded
    searches), the search measures of C and D, and D's coverage diagnostics.
    """
    cases = scored["cases"]
    complete = sum(case["complete"] for case in cases)
    conditions = {}
    for condition in CONDITIONS:
        cells = [
            c for case in cases for c in case["cells"] if c["condition"] == condition
        ]
        ran = [c for c in cells if c["ran"]]
        entry = {
            "cells": len(cells),
            "not_run": len(cells) - len(ran),
            # ran and failed, trace not recorded: no decision point, searches not counted
            "aborted": sum(c["outcome"] == ABORTED for c in ran),
            "calls_per_cell": _histogram(c["calls"] for c in ran),
        }
        if condition in SEARCHING:
            total = _zero(condition)
            for c in cells:
                total = _added(total, c["counts"])
            entry.update(
                total,
                searches_per_cell=_histogram(
                    c["searches"] for c in ran if c["searches"] is not None
                ),
            )
        conditions[condition] = entry
    return {
        "gold_cases": scored["gold_cases"],
        "frozen_cohort": scored["frozen_cohort"],
        "repetition": scored["repetition"],
        "cases_in_results": len(cases),
        "complete_cases": complete,
        "incomplete_cases": len(cases) - complete,
        "repetition_complete": scored["frozen_cohort"]
        and scored["repetition"] is not None
        and complete == scored["gold_cases"],
        "conditions": conditions,
    }


def _rate(entry, name: str) -> tuple[int, int]:
    """(k, n) of one rate of a ``summary`` entry, checked."""
    rate = entry.get(name) if isinstance(entry, dict) else None
    if not isinstance(rate, dict):
        raise ValueError(f"a summary entry with {name} is needed")
    k, n = _count(rate.get("k"), f"{name} k"), _count(rate.get("n"), f"{name} n")
    if k > n:
        raise ValueError(f"{name}: k cannot exceed n")
    return k, n


def t3(d: dict, c: dict, complete: bool) -> dict:
    """T3, fewer unnecessary searches (``d`` and ``c``: D's and C's ``summary`` entries).

    Met when D's unnecessary searches are at most a third of D's no-search-needed decision
    points with an action and at least 2 fewer than C's; assessable on a complete repetition
    when D has at least 5 such decision points. Two of three repetitions are the caller's rule.
    """
    d_k, d_n = _rate(d, "unnecessary_rate")
    c_k, _ = _rate(c, "unnecessary_rate")
    if not _flag(complete, "complete") or d_n < MIN_POINTS:
        status = "not_assessable"
    else:
        status = "met" if 3 * d_k <= d_n and d_k <= c_k - 2 else "failed"
    return {
        "status": status,
        "d_unnecessary": d_k,
        "d_no_search_needed_with_action": d_n,
        "c_unnecessary": c_k,
    }


def t4(d: dict, c: dict, complete: bool) -> dict:
    """T4, no more missed useful searches (``d`` and ``c``: D's and C's ``summary`` entries).

    Met when D's missed useful searches are at most C's plus 1 and at most a fifth of D's
    search-needed decision points with an action; assessable on a complete repetition when D
    has at least 5 of them. Two of three repetitions are the caller's rule.
    """
    d_k, d_n = _rate(d, "missed_rate")
    c_k, _ = _rate(c, "missed_rate")
    if not _flag(complete, "complete") or d_n < MIN_POINTS:
        status = "not_assessable"
    else:
        status = "met" if d_k <= c_k + 1 and 5 * d_k <= d_n else "failed"
    return {
        "status": status,
        "d_missed": d_k,
        "d_search_needed_with_action": d_n,
        "c_missed": c_k,
    }


def a1(d: dict, c: dict) -> dict:
    """A1 beside T3 (``d`` and ``c``: D's and C's ``summary`` entries), never a threshold.

    Per condition: the executed and the refused unnecessary search attempts, their total and
    T3's denominator (no-search-needed decision points with an action); ``percent`` only when
    that denominator is at least 5. The executed attempts are T3's unnecessary searches.
    """

    def entry(counts: dict, label: str) -> dict:
        k, n = _rate(counts, "unnecessary_attempt_rate")
        t3_k, t3_n = _rate(counts, "unnecessary_rate")
        split = counts.get("unnecessary_attempts")
        if not isinstance(split, dict):
            raise ValueError(f"{label}: a summary entry with unnecessary_attempts is needed")
        executed = _count(split.get("executed"), f"{label} executed attempts")
        refused = _count(split.get("refused"), f"{label} refused attempts")
        total = _count(split.get("total"), f"{label} attempts")
        if executed != t3_k or n != t3_n or executed + refused != total or total != k:
            raise ValueError(
                f"{label}: A1 counts T3's unnecessary searches plus refused requests over "
                "T3's own denominator"
            )
        percent = round(100 * k / n, 1) if n >= MIN_POINTS else None
        return {
            "executed": executed,
            "refused": refused,
            "attempts": k,
            "n": n,
            "percent": percent,
        }

    return {"d": entry(d, "D"), "c": entry(c, "C"), "threshold": None}


def search_thresholds(counts: dict) -> dict:
    """T3, A1 beside it, and T4 from one ``summary``: the repetition is complete when the
    summary says so (every gold case complete in one repetition), never on a caller's word."""

    if not isinstance(counts, dict) or not isinstance(counts.get("conditions"), dict):
        raise ValueError("search_thresholds takes a summary")
    complete = _flag(counts.get("repetition_complete"), "repetition_complete")
    d, c = counts["conditions"].get("coverage"), counts["conditions"].get("agent")
    return {
        "repetition": counts.get("repetition"),
        "repetition_complete": complete,
        "T3": t3(d, c, complete),
        "A1": a1(d, c),
        "T4": t4(d, c, complete),
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


def _inside(target: Path, folder: Path) -> bool:
    """Whether the resolved ``target`` lies in ``folder``, however it is spelled (a link,
    another letter case)."""
    if target.is_relative_to(folder.resolve()):
        return True
    return folder.is_dir() and any(
        a.exists() and os.path.samefile(a, folder) for a in (target, *target.parents)
    )


def _placement(path: Path) -> str | None:
    """Why ``path`` may not hold a scoring, or None: never in ``results/``, and in the
    repository only under this module's git-ignored ``local/`` folder."""
    if LOCAL.is_symlink():  # a link would carry case-level scoring wherever it points
        return (
            "tools/commentary_rag/local/ is a symbolic link; case-level scoring goes to "
            "the real, git-ignored folder or outside the repository"
        )
    target = path.resolve()
    if _inside(target, RESULTS):
        return "--out lies in results/, which is public; case-level scoring stays local"
    if _inside(target, REPO) and not _inside(target, LOCAL):
        return (
            "--out lies in the repository outside tools/commentary_rag/local/; write the "
            "scoring there or outside the repository"
        )
    return None


def _load(path: Path):
    return _parsed(path.read_text(encoding="utf-8"))


def _parsed(text: str):
    try:
        return json.loads(text)
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
        action="append",
        required=True,
        help="a LOCAL result.json of the repetition; repeat it for a resumed run",
    )
    parser.add_argument("--gold", type=Path, required=True, help="the frozen gold file")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="the new JSON file for the case-level scoring: under "
        "tools/commentary_rag/local/ or outside the repository",
    )
    parser.add_argument(
        "--label", help="a label written with the scoring, e.g. SIMULATED"
    )
    args = parser.parse_args(argv)
    # Every refusal of the output comes before any input is read.
    placement = _placement(args.out)
    if placement:
        return _refuse(placement)
    if args.out.exists() or args.out.is_symlink():
        return _refuse("--out already exists; a scoring never replaces a file")
    if not args.out.parent.is_dir():
        return _refuse("--out must name a file in an existing folder")
    try:
        raw = args.gold.read_bytes()  # read once: the bytes checked are the bytes used
        if hashlib.sha256(raw).hexdigest() != FROZEN_GOLD_SHA256:
            return _refuse(
                "--gold must be the frozen gold file (its SHA-256 as frozen in "
                "results/2026-11-25-phase4-freeze.json)"
            )
        results = [_load(path) for path in args.result]
        gold = _parsed(raw.decode("utf-8"))
    except (OSError, ValueError) as exc:
        return _refuse(
            f"--result and --gold must be readable JSON files ({type(exc).__name__})"
        )
    try:
        scored = score(results, gold)
        counts = summary(scored)
        thresholds = search_thresholds(counts)
    except ValueError as exc:
        return _refuse(str(exc))
    text = json.dumps(
        {
            "label": args.label,
            "score": scored,
            "summary": counts,
            "search_thresholds": thresholds,
        },
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
            {"label": args.label, "summary": counts, "search_thresholds": thresholds},
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        )
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
