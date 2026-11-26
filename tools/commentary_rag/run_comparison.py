"""Compare the three Phase 3 conditions on a set of questions (ADR-026): an offline plan or one run.

The conditions are fixed in code (``evidence_agent.CONDITIONS``): A ``fixed5``, the Phase 2
request of ADR-025 with the question's hybrid top 5, and B ``fixed10``, the same request with the
top 10, each answered once without any tool; C ``agent``, the evidence-seeking agent with the top
5 as its fixed context and its bounded search. Every cell (one case under one condition) goes
through ``evidence_agent.run_case``: the same books, ceiling, admission, reservations,
settlements, persistence, lock and answer checks, under the accounting identity (case,
condition) with the call IDs ``<case>-<condition>-call<n>``. A cell already in the books is
refused there, whatever the tag or the entry point (the one-question runner books the agent
under the same identity), and so is a case booked before with another question or editions.
``run`` pairs new cells only with booked cells that recorded the same question and editions:
it refuses a case whose booked cells were asked something else or recorded no question (the D1
run of 2026-11-20 recorded none), before the model loads.

Two designs, chosen by name (``--design``): ``phase3`` (the default) runs A, B and C as above;
``phase4`` runs B, C and D (``coverage``: the agent with the explicit coverage decision of
Phase 4, frozen in ``phase4/conditions.md``), D with C's top 5, and its public record names no
passage: it keeps codes, counts, hashes, usage and amounts, while rankings, supplied, cited and
returned passages and D's coverage text stay in the local record.

Under ``phase4`` the cells are booked in Phase 4's own books (``evidence_agent.PHASE4_LEDGER``,
USD 40; ``phase4/amendments.md``, O1) under repetition 1, the one those books admit, and the
cases file must be the frozen runner input (``PHASE4_RUNNER_INPUT_SHA256``): one invocation runs
the frozen cases in their order, B, C and D per case, and no batch split or reordering reaches the
books. Admission is per case: before each cell, under the lock, the worst case of the case's
cells still to run (every call at the input cap: USD 10.3488 for B, C and D of a fresh case) must
fit beside everything committed in those books, so a case that does not fit stops the run before
anything of it is sent. A rerun after an interruption skips every cell already in the books and
goes on in the frozen order; a cell whose booking is unresolved (a reservation without a
settlement: sending unknown) is never sent again, and its case stays incomplete.

The input is a cases file holding each case's ID, question and editions and nothing else: any
other field (a reference answer, gold evidence, a rubric) is refused before the file is used, so
nothing that scores an answer can reach a request.

``plan`` is offline: no corpus, no model, no client, nothing counted, sent or written. It reads
the books without the lock and prints the matrix in its order, each condition's bounds, the
admission check (the worst case of every cell still to run beside everything committed, under
the aggregate limit, a bound; under ``phase4`` the next case's beside the Phase 4 books) and
ESTIMATES from earlier usage settlements, labelled as such.

``run`` is the live step and runs only when explicitly authorised. It checks the cases, refuses
existing outputs and a local output folder that is a symbolic link, builds the client (the key's
presence only), refuses when the plan's worst case (under ``phase4``: the next case's) does
not fit or a case cannot be paired, loads the verified corpus and the cached e5 model
once (as the one-question runner does), checks every case's editions and question length and
ranks every case (hybrid over its editions only) before any cell runs. Then it runs the matrix
case by case, a case's A, B and C one after the other: A receives the top 5, B the top 10 and C
the top 5 of the case's ranking, each cell with the same time budget, which C shares across its
calls and searches. The matrix
stops after a cell that needs a person (a failed write, a cost above its reservation, a call kept
at its reservation, a refusal other than a cell already in the books); nothing is retried.
A cell already in the books is skipped and sets the exit code only when no cell ran. Outputs,
only when a cell reserved a call, and written for every cell that ended even when an unexpected
error stops the matrix: ``local/<tag>-comparison/`` (git-ignored: each call's
request and response, ``result.json`` with questions, answers and traces) and
``results/<tag>-comparison.json`` (metadata only: hashes, IDs, scores, codes, counts, amounts).
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import platform
import subprocess
import sys
import time
from datetime import UTC, date, datetime
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import evidence_agent
    import evidence_search
    import generation
    import retrieval
    import run_question
except ModuleNotFoundError as missing:  # the anthropic client or the ingestion package
    print(
        f"refused: {missing.name} is not installed; run with uv run --project "
        "services/ingestion --extra ai (see the README)",
        file=sys.stderr,
    )
    raise SystemExit(3) from None  # EXIT_REFUSED

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULTS = HERE / "results"
LOCAL = HERE / "local"
CLOCK = time.monotonic  # every cell's deadline clock
ORDER = ("fixed5", "fixed10", "agent")  # within a case: A, B, C (the Phase 3 design)
# The designs, chosen by name: Phase 3 (A, B, C) and Phase 4 (B, C, D; phase4/conditions.md).
DESIGNS = {"phase3": ORDER, "phase4": ("fixed10", "agent", "coverage")}
LABELS = {"fixed5": "A", "fixed10": "B", "agent": "C", "coverage": "D"}
# Phase 4 (phase4/amendments.md, O1): the one repetition its books admit, and the frozen runner
# input (results/2026-11-25-phase4-freeze.json, role "runner input"), the only cases file a
# Phase 4 plan or run reads.
PHASE4_REPETITION = evidence_agent.PHASE4_REPETITIONS[0]
PHASE4_RUNNER_INPUT_SHA256 = (
    "034e6947153b6344de73ddea4ab8d3fd1715e2ad6f962b8de946a685e583e15e"
)
# One ranking per case, deep enough for every condition's fixed context (B's top 10).
TOP_K = max(c.passages for c in evidence_agent.CONDITIONS.values())
CASE_KEYS = ("id", "question", "editions")
TOOL_FILES = (*run_question.TOOL_FILES, "run_comparison.py")
# The one refusal that skips a cell: it is already in the books, so it is never sent again.
# Any other refusal, a call ID that another case's reservation holds among them, stops the matrix.
CELL_REFUSALS = ("already_run",)
(
    EXIT_ANSWER,
    EXIT_INPUT,
    EXIT_REFUSED,
    EXIT_NOT_ANSWERED,
    EXIT_SPENDING_STOP,
    EXIT_ACCOUNTING_UNCERTAIN,
    EXIT_PERSISTENCE,
) = (
    run_question.EXIT_ANSWER,
    run_question.EXIT_INPUT,
    run_question.EXIT_REFUSED,
    run_question.EXIT_NOT_ANSWERED,
    run_question.EXIT_SPENDING_STOP,
    run_question.EXIT_ACCOUNTING_UNCERTAIN,
    run_question.EXIT_PERSISTENCE,
)
PRECEDENCE = (
    EXIT_PERSISTENCE,
    EXIT_SPENDING_STOP,
    EXIT_ACCOUNTING_UNCERTAIN,
    EXIT_REFUSED,
    EXIT_NOT_ANSWERED,
    EXIT_ANSWER,
)
STOPS = (EXIT_PERSISTENCE, EXIT_SPENDING_STOP, EXIT_ACCOUNTING_UNCERTAIN)
EPILOG = """\
exit codes of run (the codes of the cells that ran, the first row present wins; each cell's
code as in run_question.py; a cell already in the books is skipped and counts only when no
cell ran):
  7  persistence: a ledger or output write failed
  5  spending stop: a call cost more than its reservation
  6  accounting uncertain: a sent call could not be priced or its settlement is not confirmed
  3  refused: by the runner before any provider work (a case that cannot be paired with its
     cells in the books among them), or a cell by the books; a repeated run, whose cells are
     all in the books, exits 3 and sends nothing again
  4  not answered: a cell ended without an accepted answer
  0  every cell that ran gave a structurally accepted answer or abstention, every call priced
  2  invalid input, nothing loaded, counted or sent
  1  an unexpected error (traceback; the outputs of the cells that ended are still written)
plan exits 0 (printed), 2 (invalid input) or 3 (books refused); it sends and writes nothing."""
NOTES = (
    *run_question.NOTES,
    "The conditions differ by design: A and B send the Phase 2 request with its own system "
    "prompt and no tool, once; C appends the search instruction to that system prompt, "
    "offers its one search tool and may make three calls, sharing one per-cell time budget "
    "across them and its searches. Model, settings, question, editions, initial ranking and "
    "answer checks are shared.",
    "Admission figures are bounds (every call at the input cap), not expected costs; "
    "estimates come from earlier usage settlements of development cases.",
)
NOTES_PHASE4 = (
    *run_question.NOTES,
    "The conditions differ by design: B sends the Phase 2 request with its own system prompt "
    "and no tool, once; C appends the search instruction, offers its one search tool and may "
    "make three calls; D is C with its coverage decision (its own appended instruction, a "
    "search tool that also takes the coverage and the missing part it looks for, and the "
    "answer format coverage beside answer), and reviewers see only its answer object. Model, "
    "settings, question, editions, initial ranking and answer checks are shared.",
    NOTES[-1],
    "Under the Phase 4 design this record names no passage: rankings, supplied, cited and "
    "returned passages and the coverage text stay in the local record.",
)


def _usd(micro: int) -> float:
    return micro / 1_000_000


def _micro(usd: float) -> int:
    return round(usd * 1_000_000)


def _client(config: generation.Config):
    """The pilot's direct client (fixed base URL, no automatic retries), for ``run`` only."""

    return run_question._client(config)


def _cases(path: Path, *, questions: bool) -> list[dict] | str:
    """The cases in ``path`` (ID, question, editions), or why they cannot be used."""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        RecursionError,
    ) as exc:  # nested too deep
        return f"--cases cannot be read as JSON ({type(exc).__name__})"
    if (
        not isinstance(data, dict)
        or set(data) != {"cases"}
        or not isinstance(data["cases"], list)
        or not data["cases"]
    ):
        return "--cases must be an object whose only key, cases, holds a non-empty list"
    seen: set[str] = set()
    for n, item in enumerate(data["cases"], start=1):
        if not isinstance(item, dict):
            return f"case {n} is not an object"
        extra = sorted(set(item) - set(CASE_KEYS))
        if extra:  # names only, escaped and shortened: their values are never read
            shown = ", ".join(repr(name)[:40] for name in extra[:5])
            return (
                f"case {n} has fields other than id, question and editions "
                f"({shown}{', ...' if len(extra) > 5 else ''}): nothing that scores an answer "
                "may be in the input"
            )
        missing = sorted(
            {"id", "editions", *(("question",) if questions else ())} - set(item)
        )
        if missing:
            return f"case {n} lacks {', '.join(missing)}"
        case_id = item["id"]
        if not isinstance(case_id, str) or not evidence_agent.CASE_ID.fullmatch(
            case_id
        ):
            return (
                f"case {n}: the id must be a plain name (letters, digits, '_', '.', '-', "
                "starting with a letter or digit, at most 64 characters)"
            )
        if case_id in seen:
            return f"case {n}: the id {case_id} is given twice"
        seen.add(case_id)
        question = item.get("question")
        if "question" in item and (
            not isinstance(question, str) or not question.strip()
        ):
            return f"case {case_id}: the question must be a non-empty string"
        editions = item["editions"]
        if (
            not isinstance(editions, list)
            or not editions
            or not all(isinstance(e, str) and _edition(e) for e in editions)
        ):
            return f"case {case_id}: editions must be a non-empty list of dates (YYYY-MM-DD)"
        if len(set(editions)) != len(editions):
            return f"case {case_id}: an edition is given twice"
    return [
        {
            "id": c["id"],
            "question": c.get("question"),
            "editions": sorted(c["editions"]),
        }
        for c in data["cases"]
    ]


def _edition(value: str) -> bool:
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _plan(cases: list[dict], design: str = "phase3") -> dict:
    """The matrix in its order (the conditions of ``design``), its bounds and its admission
    beside the books now; estimates labelled. Raises ValueError when the books cannot be used
    as they are."""

    if design == "phase4":
        return _plan_phase4(cases)
    state = evidence_agent.spending_state()
    ceiling = _micro(state["call_ceiling_at_input_cap_usd"])
    limits = evidence_search.SearchLimits()
    in_books = {(cell["case"], cell["condition"]) for cell in state["cells"]}
    booked: dict[str, list] = {}
    for cell in state["cells"]:
        booked.setdefault(cell["case"], []).append(cell)
    conditions = {}
    for name in DESIGNS[design]:
        c = evidence_agent.CONDITIONS[name]
        conditions[name] = {
            "label": LABELS[name],
            "initial_passages": c.passages,
            "most_passages": limits.max_passages if c.search else c.passages,
            "calls": c.calls,
            "searches": limits.max_rounds if c.search else 0,
            "search_tool": c.search,
            "admission_usd": _usd(c.calls * ceiling),
        }
    order = [
        {
            "case": c["id"],
            "condition": name,
            "label": LABELS[name],
            "editions": c["editions"],
            "in_books": (c["id"], name) in in_books,
        }
        for c in cases
        for name in DESIGNS[design]
    ]
    worst = sum(
        _micro(conditions[o["condition"]]["admission_usd"])
        for o in order
        if not o["in_books"]
    )
    limit, committed = _micro(state["limit_usd"]), _micro(state["committed_usd"])
    return {
        "order": order,
        "conditions": conditions,
        "admission": {
            "label": (
                "BOUND, not an expected cost: every call of every cell still to run at "
                "the input cap, beside everything committed, under the aggregate limit"
            ),
            "limit_usd": state["limit_usd"],
            "committed_usd": state["committed_usd"],
            "historical_committed_usd": state["historical_committed_usd"],
            "active_committed_usd": state["active_committed_usd"],
            "headroom_usd": _usd(limit - committed),
            "call_ceiling_at_input_cap_usd": _usd(ceiling),
            "worst_case_usd": _usd(worst),
            "fits": committed + worst <= limit,
            "headroom_after_worst_case_usd": _usd(limit - committed - worst),
        },
        "cases": [
            {
                "case": c["id"],
                "editions": c["editions"],
                "booked": [cell["condition"] for cell in booked.get(c["id"], [])],
                "pairing": _pairing(c, booked.get(c["id"], [])),
            }
            for c in cases
        ],
        "assumptions": {
            "label": (
                "ASSUMPTIONS of the bounds, fixed in code and pricing.json: "
                "each call's ceiling is its counted input with the margin at "
                "the dearest input rate, plus every output token, times the "
                "US multiplier; prices as recorded, not a billing guarantee"
            ),
            **state["assumptions"],
        },
        "estimates": _estimates(state, order, design),
    }


def _bounds(design: str, ceiling: int) -> dict:
    """Each condition of ``design``: its label, passages, calls, searches and admission."""

    limits = evidence_search.SearchLimits()
    conditions = {}
    for name in DESIGNS[design]:
        c = evidence_agent.CONDITIONS[name]
        conditions[name] = {
            "label": LABELS[name],
            "initial_passages": c.passages,
            "most_passages": limits.max_passages if c.search else c.passages,
            "calls": c.calls,
            "searches": limits.max_rounds if c.search else 0,
            "search_tool": c.search,
            "admission_usd": _usd(c.calls * ceiling),
        }
    return conditions


def _plan_phase4(cases: list[dict]) -> dict:
    """The Phase 4 matrix beside Phase 4's own books: its order, bounds and per-case admission
    (the next case's cells still to run at their worst case beside everything committed there,
    under their limit), how the reserved calls stand, and estimates from every earlier usage
    settlement (Phase 2, 3 and 4), labelled."""

    state = evidence_agent.spending_state(books="phase4")
    ceiling = _micro(state["call_ceiling_at_input_cap_usd"])
    conditions = _bounds("phase4", ceiling)
    mine = [c for c in state["cells"] if c["repetition"] == PHASE4_REPETITION]
    in_books = {(cell["case"], cell["condition"]) for cell in mine}
    booked: dict[str, list] = {}
    for cell in state["cells"]:  # every repetition: one case ID, one question and editions
        booked.setdefault(cell["case"], []).append(cell)
    calls: dict[tuple, dict] = {}
    kinds = {"usage": "usage", "reservation_retained": "retained", "not_sent": "released"}
    for call in state["active_calls"]:
        if call["repetition"] == PHASE4_REPETITION:
            tally = calls.setdefault(
                (call["case"], call["condition"]),
                dict.fromkeys(("usage", "retained", "released", "open"), 0),
            )
            tally[kinds.get(call["cost_basis"], "open")] += 1
    order = [
        {
            "case": c["id"],
            "condition": name,
            "label": LABELS[name],
            "editions": c["editions"],
            "in_books": (c["id"], name) in in_books,
            **(
                {"calls_in_books": calls[(c["id"], name)]}
                if (c["id"], name) in calls
                else {}
            ),
        }
        for c in cases
        for name in DESIGNS["phase4"]
    ]
    rest: dict[str, int] = {}
    for o in order:
        if not o["in_books"]:
            rest[o["case"]] = rest.get(o["case"], 0) + _micro(
                conditions[o["condition"]]["admission_usd"]
            )
    following = next((c["id"] for c in cases if c["id"] in rest), None)
    limit, committed = _micro(state["limit_usd"]), _micro(state["committed_usd"])
    case_ceiling = sum(_micro(c["admission_usd"]) for c in conditions.values())
    worst = sum(rest.values())
    earlier = evidence_agent.spending_state()  # Phase 2 and 3: estimates only
    observed = {
        "historical_calls": earlier["historical_calls"],
        "active_calls": earlier["active_calls"]
        + [{**call, "books": "phase4"} for call in state["active_calls"]],
        "input_usd_per_mtok": state["input_usd_per_mtok"],
    }
    return {
        "order": order,
        "conditions": conditions,
        "admission": {
            "label": (
                "BOUND, not an expected cost: a case starts only when every call of its "
                "cells still to run, at the input cap, fits beside everything committed "
                "in the Phase 4 books, under their limit; checked again under the lock "
                "before every cell"
            ),
            "books": state["books"],
            "repetition": PHASE4_REPETITION,
            "limit_usd": state["limit_usd"],
            "committed_usd": state["committed_usd"],
            "booked": state["booked"],
            "headroom_usd": _usd(limit - committed),
            "call_ceiling_at_input_cap_usd": _usd(ceiling),
            "case_ceiling_usd": _usd(case_ceiling),
            "cases_to_run": len(rest),
            "next_case": following,
            "next_case_worst_case_usd": _usd(rest.get(following, 0)),
            "fits": committed + rest.get(following, 0) <= limit,
            "worst_case_usd": _usd(worst),
        },
        "cases": [
            {
                "case": c["id"],
                "editions": c["editions"],
                "booked": [cell["condition"] for cell in booked.get(c["id"], [])],
                "pairing": _pairing(c, booked.get(c["id"], [])),
            }
            for c in cases
        ],
        "assumptions": {
            "label": (
                "ASSUMPTIONS of the bounds, fixed in code and pricing.json: "
                "each call's ceiling is its counted input with the margin at "
                "the dearest input rate, plus every output token, times the "
                "US multiplier; prices as recorded, not a billing guarantee"
            ),
            **state["assumptions"],
        },
        "estimates": _estimates(observed, order, "phase4"),
    }


def _pairing(item: dict, booked: list[dict]) -> str:
    """Whether a case's cells already in the books were asked what this case asks: new (none
    booked), same, other (another question or editions), unverifiable (a cell recorded neither,
    written before 2026-11-21) or question_not_given (a plan without the question)."""

    if not booked:
        return "new"
    if any(
        cell["question_sha256"] is None or cell["editions"] is None for cell in booked
    ):
        return "unverifiable"
    if any(cell["editions"] != item["editions"] for cell in booked):
        return "other"
    if item.get("question") is None:
        return "question_not_given"
    asked = _sha256(item["question"])
    return (
        "same" if all(cell["question_sha256"] == asked for cell in booked) else "other"
    )


def _estimates(state: dict, order: list[dict], design: str = "phase3") -> dict:
    """The mean calculated cost of earlier cells priced from their usage, per condition of
    ``design`` (cells of every condition in the books are read)."""

    # Phase 2's requests were ADR-025's fixed top 5, so each of its cases is a fixed5 cell.
    phase2: dict[str, list] = {}
    for call in state["historical_calls"]:
        phase2.setdefault(call["case"], []).append(call)
    cells: dict[tuple, list] = {}
    for call in state["active_calls"]:  # a cell per books, case, condition and repetition
        key = (call.get("books"), call["case"], call["condition"], call.get("repetition"))
        cells.setdefault(key, []).append(call)

    def priced(calls: list) -> int | None:
        """A cell's cost in micro-dollars when every call it reserved was settled from its
        usage; None while a reservation is open or a call was kept or released."""
        if all(c["cost_basis"] == "usage" for c in calls):
            return sum(_micro(c["cost_usd"]) for c in calls)
        return None

    observed = {name: [] for name in evidence_agent.CONDITIONS}
    for calls in phase2.values():
        observed["fixed5"].append(priced(calls))
    for (_, _, name, _), calls in cells.items():
        observed[name].append(priced(calls))
    per = {}
    for name in evidence_agent.CONDITIONS:
        costs = [c for c in observed[name] if c is not None]
        per[name] = {
            "observed_cells": len(costs),
            "usd_per_cell": _usd(round(sum(costs) / len(costs))) if costs else None,
            "basis": {
                "fixed5": "Phase 2's requests (the historical ledger, ADR-025's "
                "fixed top 5) and fixed5 cells of the active ledger",
                "fixed10": "fixed10 cells of the active ledger",
                "agent": "agent cells of the active ledger (D1 is one)",
                "coverage": "coverage cells of the active ledger (Phase 4, condition D)",
            }[name],
        }
    if (
        not per["fixed10"]["observed_cells"]
        and per["fixed5"]["usd_per_cell"] is not None
    ):
        extra = (
            evidence_agent.CONDITIONS["fixed10"].passages
            - evidence_agent.CONDITIONS["fixed5"].passages
        ) * run_question.TOKEN_BUDGET
        per["fixed10"].update(
            usd_per_cell=_usd(
                _micro(per["fixed5"]["usd_per_cell"])
                + math.ceil(extra * state["input_usd_per_mtok"])
            ),
            basis=(
                f"no observation: the fixed5 estimate plus {extra} input tokens (five more "
                f"passages at the {run_question.TOKEN_BUDGET}-token passage budget) at "
                f"{state['input_usd_per_mtok']:g} USD per million"
            ),
        )
    todo = [o for o in order if not o["in_books"]]
    known = [per[o["condition"]]["usd_per_cell"] for o in todo]
    return {
        "label": (
            "ESTIMATE, not a bound: the mean calculated cost of earlier cells priced "
            "from their usage, on development cases with few observations; not an "
            "invoice and not a prediction for the cases planned"
        ),
        "per_condition": {name: per[name] for name in DESIGNS[design]},
        "cells_to_run": len(todo),
        "matrix_usd": (
            _usd(sum(_micro(k) for k in known))
            if all(k is not None for k in known)
            else None
        ),
    }


def _planned(design: str = "phase3") -> dict:
    """When, from which code and against which books a plan was made."""

    books = evidence_agent.BOOKS.resolve()

    def sha(path: Path) -> str | None:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return {
        "at": _now(),
        "git_head": head,
        "offline": "nothing counted, sent or written; the books read without the lock",
        "historical_ledger_sha256": sha(books / evidence_agent.HISTORICAL_LEDGER),
        "active_ledger_sha256": sha(books / evidence_agent.ACTIVE_LEDGER),
        **(
            {"phase4_ledger_sha256": sha(books / evidence_agent.PHASE4_LEDGER)}
            if design == "phase4"
            else {}
        ),
    }


def _paths(tag: str) -> dict[str, Path]:
    name = f"{tag}-comparison"
    return {"public": RESULTS / f"{name}.json", "local": LOCAL / name}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _system_prompt(condition: evidence_agent.Condition) -> str:
    """The system prompt a condition sends: the Phase 2 prompt, with the agent's or D's
    instruction appended for the conditions that search."""

    if not condition.search:
        return generation.SYSTEM_PROMPT
    instruction = (
        evidence_agent.COVERAGE_INSTRUCTION
        if condition.coverage
        else evidence_agent.INSTRUCTION
    )
    return f"{generation.SYSTEM_PROMPT}\n\n{instruction}"


def _provenance(args: argparse.Namespace, cases: list[dict], loaded) -> dict:
    """Which code, settings, corpus and books the run used, computed before anything is sent."""

    config = generation.Config()
    design = getattr(args, "design", "phase3")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", str(HERE)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return {
        "tag": args.tag,
        **({"design": design} if design != "phase3" else {}),
        "time_budget_s_per_cell": args.time_budget_s,
        "cases": [
            {
                "case": c["id"],
                "editions": c["editions"],
                "question_sha256": _sha256(c["question"]),
            }
            for c in cases
        ],
        "configuration": {
            "model": config.model,
            "effort": config.effort,
            "thinking": {"type": "adaptive"},
            "max_tokens": config.max_tokens,
            "timeout_s": config.timeout_s,
            "client_max_retries": 0,
            "budget_usd": config.budget_usd,
            "input_margin": config.input_margin,
            "max_input_tokens": evidence_agent.MAX_INPUT_TOKENS,
            "search_limits": dataclasses.asdict(evidence_search.SearchLimits()),
            "answer_schema_sha256": _sha256(
                json.dumps(generation.ANSWER_SCHEMA, sort_keys=True)
            ),
            "conditions": {
                name: {
                    "label": LABELS[name],
                    "initial_passages": c.passages,
                    "calls": c.calls,
                    "search_tool": c.search,
                    "system_prompt_sha256": _sha256(_system_prompt(c)),
                    **(
                        {
                            "answer_format_sha256": _sha256(
                                json.dumps(
                                    evidence_agent.COVERAGE_ANSWER_SCHEMA, sort_keys=True
                                )
                            )
                        }
                        if c.coverage
                        else {}
                    ),
                }
                for name, c in ((n, evidence_agent.CONDITIONS[n]) for n in DESIGNS[design])
            },
        },
        "ranking": {
            "method": run_question.METHOD,
            "mode": run_question.MODE,
            "k": TOP_K,
            "token_budget": run_question.TOKEN_BUDGET,
            "embedder": dict(loaded.e5.provenance),
        },
        "corpus": {
            "manifest": {
                "path": run_question._rel(args.manifest),
                "sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
            },
            "documents": [
                {
                    "edition": d.edition,
                    "sha256": d.sha256,
                    "source_url": d.source_url,
                    "page_count": d.page_count,
                }
                for d in loaded.built.documents
            ],
            "passages": len(loaded.built.passages),
        },
        "books": (
            {
                "ledger": evidence_agent.PHASE4_LEDGER,
                "limit_usd": evidence_agent.PHASE4_LIMIT_USD,
                "repetition": PHASE4_REPETITION,
                "runner_input_sha256": PHASE4_RUNNER_INPUT_SHA256,
            }
            if design == "phase4"
            else {
                "historical_ledger": evidence_agent.HISTORICAL_LEDGER,
                "historical_sha256": evidence_agent.HISTORICAL_SHA256,
                "active_ledger": evidence_agent.ACTIVE_LEDGER,
            }
        ),
        "environment": {
            "python": platform.python_version(),
            "packages": {n: metadata.version(n) for n in ("anthropic", "httpx")},
            "git_head": head,
            "tool_files_uncommitted": bool(dirty),
            "tool_files_sha256": {
                n: hashlib.sha256((HERE / n).read_bytes()).hexdigest()
                for n in TOOL_FILES
            },
        },
    }


# The keys of a cell's record the Phase 4 public record carries as they are: codes, counts,
# hashes, usage and amounts; supplied, cited and searched passages are reduced to counts.
PUBLIC_PHASE4 = ("case", "condition", "repetition", "budget_s", "generation_calls", "calls",
                 "spending",
                 "outcome", "detail", "elapsed_s", "schema_problems",
                 "citations_outside_supplied", "coverage")
SEARCH_PHASE4 = ("round", "outcome", "method", "window", "rounds_left", "passages_left")


def _phase4_record(record: dict) -> dict:
    """A cell's record as the Phase 4 public record carries it: no passage ID."""

    kept = {k: record[k] for k in PUBLIC_PHASE4 if k in record}
    for key in ("supplied", "cited"):
        if key in record:
            kept[key] = len(record[key])
    if "searches" in record:
        kept["searches"] = [
            {
                **{k: s.get(k) for k in SEARCH_PHASE4},
                "returned": len(s.get("returned") or []),
                "already_supplied": len(s.get("already_supplied") or []),
            }
            for s in record["searches"]
        ]
    return kept


def _phase4_answer(answer: dict | None) -> dict | None:
    """An accepted answer's public metadata under the Phase 4 design: cited passages counted."""

    meta = run_question._answer_metadata(answer)
    if meta is not None:
        meta["cited_passages"] = len(meta["cited_passages"])
    return meta


def _phase4_case(item: dict, ranking, cells: list) -> dict:
    """One case of the Phase 4 public record: its question by hash, no passage ID."""

    return {
        "case": item["id"],
        "editions": item["editions"],
        "question_sha256": _sha256(item["question"]),
        "ranked_passages": len(ranking),
        "cells": [
            {
                "condition": name,
                "label": LABELS[name],
                "status": status,
                "exit_code": code,
                "agent": _phase4_record(result.record) if result else None,
                "answer": _phase4_answer(result.answer if result else None),
            }
            for name, result, status, code in cells
        ],
    }


def _cell(result: evidence_agent.CaseResult) -> tuple[dict, int]:
    """A cell's statuses and its exit code, as the one-question runner reads one run."""

    accounting = run_question._accounting(result)
    status = {
        "execution": result.outcome,
        "detail": result.detail,
        "answer": result.status,
        "accounting": accounting,
    }
    return status, run_question._exit_code(result, accounting, persisted=True)


def _run(  # noqa: PLR0913
    args: argparse.Namespace, cases: list[dict], client, plan: dict, loaded, ranked
) -> int:
    """Run the matrix once, case by case, then keep and report what came back. The outputs of
    every cell that ended are written even when an unexpected error stops the matrix."""

    paths = _paths(args.tag)
    provenance = _provenance(args, cases, loaded)
    passages = run_question._records(loaded)
    design = getattr(args, "design", "phase3")
    phase4 = design == "phase4"
    books = (
        evidence_agent.BOOKS
    )  # read now: the books are wherever the agent keeps them
    spending = (
        evidence_agent.Spending(
            ledger=books / evidence_agent.PHASE4_LEDGER,
            baseline=None,
            baseline_sha256=None,
            artifacts=paths["local"],
        )
        if phase4
        else evidence_agent.Spending(
            ledger=books / evidence_agent.ACTIVE_LEDGER,
            baseline=books / evidence_agent.HISTORICAL_LEDGER,
            baseline_sha256=evidence_agent.HISTORICAL_SHA256,
            artifacts=paths["local"],
        )
    )
    retriever, rankings = ranked
    # Each cell's admission, under the lock, also holds back the worst case of the cells after
    # it that were not in the books when the matrix was admitted: a booking by another
    # invocation in between stops the matrix at the next cell once the rest no longer fits.
    # Under phase4 the rest is the case's own cells still to run: a case is admitted whole
    # before its first cell, and the next case only when its own worst case fits.
    rest_after, remaining = {}, 0
    for o in reversed(plan["order"]):
        if phase4 and o["condition"] == DESIGNS[design][-1]:
            remaining = 0  # the case's last cell: nothing of its case follows
        rest_after[(o["case"], o["condition"])] = remaining
        if not o["in_books"]:
            remaining += _micro(plan["conditions"][o["condition"]]["admission_usd"])
    repetition = {"repetition": PHASE4_REPETITION} if phase4 else {}
    times = {"started": _now(), "finished": None}
    state = {"stopped": None, "reserved": False}
    rows = []  # (case, ranking, [(name, result or None, status, code)]), filled as cells end

    def ranked_ids(ranking) -> list[dict]:
        return [
            {
                "rank": n,
                "passage_id": hit.passage_id,
                "score": hit.score,
                **{
                    k: passages[hit.passage_id][k]
                    for k in ("edition", "page", "section", "text_sha256")
                },
            }
            for n, hit in enumerate(ranking, start=1)
        ]

    def public() -> dict:
        return {
            "run": {
                **provenance,
                "started_at": times["started"],
                "finished_at": times["finished"],
            },
            "plan": plan,
            "stopped_after": state["stopped"],
            "cases": [
                {
                    "case": item["id"],
                    "editions": item["editions"],
                    "question_sha256": _sha256(item["question"]),
                    "ranking": ranked_ids(ranking),
                    "cells": [
                        {
                            "condition": name,
                            "label": LABELS[name],
                            "status": status,
                            "exit_code": code,
                            # named keys of the agent's publishable record only
                            "agent": (
                                {
                                    k: result.record[k]
                                    for k in run_question.PUBLIC_RECORD
                                    if k in result.record
                                }
                                if result
                                else None
                            ),
                            "answer": run_question._answer_metadata(
                                result.answer if result else None
                            ),
                        }
                        for name, result, status, code in cells
                    ],
                }
                for item, ranking, cells in rows
            ]
            if not phase4
            else [_phase4_case(item, ranking, cells) for item, ranking, cells in rows],
            "notes": NOTES_PHASE4 if phase4 else NOTES,
        }

    def kept() -> dict:
        return {
            "cases": [
                {
                    "case": item["id"],
                    "question": item["question"],
                    "editions": item["editions"],
                    "ranking": [hit.passage_id for hit in ranking],
                    # Phase 4 publishes no ranking: its scores and ranks are kept here instead.
                    **({"ranking_detail": ranked_ids(ranking)} if phase4 else {}),
                    "cells": [
                        {
                            "condition": name,
                            "status": status,
                            "answer": result.answer if result else None,
                            "record": result.record if result else None,
                            "local": result.local if result else None,
                        }
                        for name, result, status, _ in cells
                    ],
                }
                for item, ranking, cells in rows
            ]
        }

    done, failed = [], []
    try:
        for item in cases:
            ranking, cells = rankings[item["id"]], []
            rows.append((item, ranking, cells))
            for name in DESIGNS[design]:
                if state["stopped"]:  # nothing after a cell that needs a person
                    cells.append(
                        (
                            name,
                            None,
                            {
                                "execution": "not_run",
                                "detail": "matrix_stopped",
                                "answer": None,
                                "accounting": "nothing_reserved",
                            },
                            None,
                        )
                    )
                    continue
                condition = evidence_agent.CONDITIONS[name]
                task = evidence_agent.AgentTask(
                    case_id=item["id"],
                    question=item["question"],
                    editions=tuple(item["editions"]),
                    passages=tuple(
                        passages[hit.passage_id]
                        for hit in ranking[: condition.passages]
                    ),
                )
                result = evidence_agent.run_case(
                    task,
                    client=client,
                    retriever=retriever,
                    passages=passages,
                    clock=CLOCK,
                    budget_s=args.time_budget_s,
                    spending=spending,
                    condition=name,
                    matrix_rest_usd=_usd(rest_after[(item["id"], name)]),
                    **repetition,
                )
                status, code = _cell(result)
                cells.append((name, result, status, code))
                state["reserved"] = (
                    state["reserved"]
                    or bool(result.record.get("calls"))
                    or (result.detail == run_question.UNCONFIRMED_RESERVATION)
                )
                if code in STOPS or (
                    result.outcome == "refused" and result.detail not in CELL_REFUSALS
                ):
                    state["stopped"] = {"case": item["id"], "condition": name}
    finally:  # nothing reserved means nothing of the matrix is in the books: no output either
        times["finished"] = _now()
        outputs = (
            [(paths["local"] / "result.json", kept), (paths["public"], public)]
            if state["reserved"]
            else []
        )
        for (
            path,
            build,
        ) in outputs:  # each built and written on its own; nothing sent again
            try:
                run_question._write(path, build())
            except (OSError, TypeError, ValueError) as exc:
                failed.append({"path": str(path), "error": type(exc).__name__})
            else:
                done.append(str(path))
    # A cell already in the books was skipped, not run: it sets the exit code only when no
    # cell ran at all (a repeated run is refused, exit 3).
    codes = {
        code
        for _, _, cells in rows
        for _, _, status, code in cells
        if code is not None
        and not (status["execution"] == "refused" and status["detail"] in CELL_REFUSALS)
    }
    codes |= {EXIT_PERSISTENCE} if failed else set()
    code = next((c for c in PRECEDENCE if c in codes), EXIT_REFUSED)
    print(
        json.dumps(
            {
                "tag": args.tag,
                "cells": [
                    {
                        "case": item["id"],
                        "condition": name,
                        "label": LABELS[name],
                        **status,
                        "exit_code": code_,
                        "calls": [
                            {
                                k: c.get(k)
                                for k in (
                                    "attempt",
                                    "reserved_usd",
                                    "cost_usd",
                                    "cost_basis",
                                    "above_reservation",
                                )
                            }
                            for c in (result.record.get("calls", []) if result else [])
                        ],
                    }
                    for item, _, cells in rows
                    for name, result, status, code_ in cells
                ],
                "stopped_after": state["stopped"],
                "exit_code": code,
                "written": done,
                "not_written": failed,
                "note": NOTES[0],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "step",
        choices=("plan", "run"),
        help="plan: bounds, headroom and estimates, offline; run: the live matrix",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        required=True,
        help='JSON: {"cases": [{"id", "question", "editions"}]}, nothing else',
    )
    parser.add_argument(
        "--tag",
        default=datetime.now().astimezone().date().isoformat(),
        help="date prefix of the output files (default: today); not an identity",
    )
    parser.add_argument(
        "--time-budget-s",
        type=float,
        help="run: each cell's cooperative time limit in seconds (not money)",
    )
    parser.add_argument(
        "--design",
        choices=tuple(DESIGNS),
        default="phase3",
        help="phase3: A, B, C (the default); phase4: B, C, D (phase4/conditions.md)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO / "data/manifests/bag-al.json",
        help="the AL manifest that pins the commentary PDFs by SHA-256",
    )
    args = parser.parse_args(argv)
    if args.step == "run":
        if (
            args.time_budget_s is None
            or not math.isfinite(args.time_budget_s)
            or args.time_budget_s <= 0
        ):
            parser.error(
                "run needs --time-budget-s, a finite number of seconds above 0"
            )
        if not evidence_agent.CASE_ID.fullmatch(args.tag):
            parser.error("--tag must be a plain name (letters, digits, '_', '.', '-')")
    cases = _cases(args.cases, questions=args.step == "run")
    if isinstance(cases, str):
        parser.error(cases)  # exit 2, before anything is loaded, counted or sent
    if (
        args.design == "phase4"
        and hashlib.sha256(args.cases.read_bytes()).hexdigest()
        != PHASE4_RUNNER_INPUT_SHA256
    ):
        parser.error(
            "--design phase4 takes the frozen runner input only (its SHA-256 as frozen in "
            "results/2026-11-25-phase4-freeze.json): no other case set, subset or order"
        )
    if args.step == "plan":
        try:
            plan = _plan(cases, args.design)
        except ValueError as refusal:
            print(
                f"refused: the books cannot be used as they are ({refusal})",
                file=sys.stderr,
            )
            return EXIT_REFUSED
        shown = {"design": args.design} if args.design != "phase3" else {}
        print(
            json.dumps(
                {"planned": _planned(args.design), **shown, **plan},
                ensure_ascii=False,
                indent=1,
            )
        )
        return EXIT_ANSWER
    args.manifest = args.manifest.resolve()
    paths = _paths(args.tag)
    try:
        existing = run_question._existing(paths)
        if existing:
            raise run_question._Stop(
                EXIT_REFUSED,
                f"refused: {', '.join(existing)} already "
                "exists; a run never overwrites an earlier output",
            )
        linked = _linked(paths)
        if linked:
            raise run_question._Stop(
                EXIT_REFUSED,
                f"refused: {linked} is a symbolic link; local outputs (questions, answers, "
                "rankings) stay in the real, git-ignored local/ folder",
            )
        client = _client(
            generation.Config()
        )  # the key is checked before the model loads
        try:
            plan = _plan(cases, args.design)
        except ValueError as refusal:
            raise run_question._Stop(
                EXIT_REFUSED,
                f"refused: the books cannot be used as they are ({refusal})",
            ) from None
        admission = plan["admission"]
        if not admission["fits"] and args.design == "phase4":
            raise run_question._Stop(
                EXIT_REFUSED,
                f"refused: the next case, {admission['next_case']}, needs USD "
                f"{admission['next_case_worst_case_usd']} at its worst case, more than "
                f"the headroom of USD {admission['headroom_usd']} in the Phase 4 books; "
                "nothing was loaded, counted or sent",
            )
        if not admission["fits"]:
            raise run_question._Stop(
                EXIT_REFUSED,
                "refused: the matrix's worst case of USD "
                f"{admission['worst_case_usd']} does not fit the "
                f"headroom of USD {admission['headroom_usd']}",
            )
        unpaired = [
            c for c in plan["cases"] if c["pairing"] in ("other", "unverifiable")
        ]
        if (
            unpaired
        ):  # a cell in the books asked something else cannot be paired with new ones
            raise run_question._Stop(
                EXIT_REFUSED,
                "refused: case(s) with cells in the books "
                "that were asked another question or editions, or whose "
                "question was not recorded, cannot be compared: "
                + ", ".join(f"{c['case']} ({c['pairing']})" for c in unpaired),
            )
        loaded = run_question._load(args.manifest)
        for item in cases:  # every case checked before any cell runs
            run_question._checked(loaded, item["question"], item["editions"])
        ranked = _rankings(cases, loaded)
    except run_question._Stop as stop:
        print(stop, file=sys.stderr)
        return stop.code
    return _run(args, cases, client, plan, loaded, ranked)


def _linked(paths: dict[str, Path]) -> str | None:
    """The first of local/ and the run's folder in it that is a symbolic link, or None: a link
    could carry the local record into a tracked or published folder."""

    for path in (LOCAL, paths["local"]):
        if path.is_symlink():
            return str(path)
    return None


def _rankings(cases: list[dict], loaded) -> tuple:
    """The retriever and every case's ranking (hybrid, its editions only, top 10), all made
    before any cell runs, so no cell spends before every case can be ranked."""

    retriever = retrieval.Retriever(loaded.built.passages, loaded.e5.embedder)
    rankings = {}
    for item in cases:
        try:
            rankings[item["id"]] = retriever.rank(
                item["question"], method=run_question.METHOD, editions=item["editions"]
            )[:TOP_K]
        except Exception as exc:  # noqa: BLE001 - however a ranking fails, nothing is sent
            raise run_question._Stop(
                EXIT_REFUSED,
                f"refused: case {item['id']} could not be ranked "
                f"({type(exc).__name__}); nothing was counted or sent",
            ) from None
    return retriever, rankings


if __name__ == "__main__":
    raise SystemExit(main())
