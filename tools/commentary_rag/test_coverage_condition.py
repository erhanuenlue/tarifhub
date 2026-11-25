"""Offline tests for condition D, the coverage decision (Phase 4), and for B and C staying as they were.

Condition D (``coverage``) is the Phase 3 agent with three differences fixed in the frozen
contract ``phase4/conditions.md``: its appended instruction, the input schema of its search tool
and its answer format ``{"coverage": [...], "answer": {...}}``. Every test runs the real loop at
the provider's HTTP boundary with the fixtures of ``test_evidence_agent`` (temporary books, a
stand-in clock, the synthetic two-edition corpus of ``test_evidence_search``). The frozen texts
and schemas are checked against the SHA-256 values the contract recorded before D existed.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import evidence_agent
import evidence_search
import generation
from test_evidence_agent import (
    TOOL,
    Clock,
    Provider,
    _message,
    books,
    events,
    final,
    run,
    search_call,
    task,
)
from test_evidence_search import JAN, JUL

# SHA-256 values frozen in phase4/conditions.md on 2026-11-25, before D was implemented.
FROZEN = {
    "instruction": "f3ee7de1a3da73c247a2a4a05c9ba1b92443bcce06e6d81fcf0b052bdeb37aa8",
    "system_prompt": "d3bd0662f15d0d84407fe2c0334e8bf59b8b2d19dac433c2a63f705ab5867cbb",
    "answer_format": "3911567f07f71cc3917ac93636db78480997e62d7d1c015f2917ff0fe05348b5",
    "tool_july": "0185766bd6ab22522dce2ed552e647e0adabf5e4b005022df4e27c91c3ad36f4",
    "refusal_reasons": "1f36c824c57b9637cdbce4506bceacd9833b6428cc698be6b223b4660d8d2ec7",
    "c_system_prompt": "9d066f4966a56f8d53a8a3899262a5e64f1f0a5ccc151bbdc98e275faa92db83",
    "c_tool_july": "b250fc03a052aa9225cbf749e5537af8cb5b2f085e6042b8b7e53d10ad94121c",
    "answer_schema": "31f86409999f8e88212d79079edf199437d133db9bc9d0c977c2b6d288452d4c",
}
# The request bodies B and C sent in these tests before D existed (code of 8aacf99).
PINNED_C = [
    "790057702112a2f28243126e191fc997a832c2397a46835105bfc614f65e7647",
    "0bda2b7a893e2c4056784abb14c0d3ab61bc055d904e53a78dc36d968b0d6952",
]
PINNED_B = ["e391314ce9162c066050d7d8a2df83caef4c038cad6c42646256d110da2083a3"]
TEN = (
    "jul/k",
    "jul/c",
    "jul/h",
    "jul/b",
    "jul/a",
    "jul/f",
    "jul/l",
    "jul/d",
    "jul/e",
    "jul/g",
)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """No live credential; the books in a temporary folder, the pinned hash restored after."""
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(evidence_agent, "BOOKS", tmp_path / "books")
    monkeypatch.setattr(
        evidence_agent, "HISTORICAL_SHA256", evidence_agent.HISTORICAL_SHA256
    )


@pytest.fixture
def spending() -> evidence_agent.Spending:
    return books()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value) -> str:
    return _sha(json.dumps(value, sort_keys=True, ensure_ascii=False))


def part(name: str, status: str, *passages: str) -> dict:
    return {"part": name, "status": status, "passages": list(passages)}


def coverage_answer(
    coverage,
    *claims: tuple[str, list[str]],
    status: str = "answered",
    missing=(),
    raw: dict | None = None,
) -> dict:
    """D's final message: coverage beside the unchanged answer object (or ``raw`` as given)."""
    answer = {
        "status": status,
        "claims": [{"text": t, "citations": c} for t, c in claims],
        "missing_evidence": list(missing),
    }
    body = raw if raw is not None else {"coverage": coverage, "answer": answer}
    return _message(
        [
            {"type": "thinking", "thinking": "", "signature": "sig-final"},
            {"type": "text", "text": json.dumps(body, ensure_ascii=False)},
        ],
        "end_turn",
    )


def coverage_search(coverage, search_for, query: str, seeking: str, **extra) -> dict:
    """D's search request: coverage and search_for before C's arguments; ``extra`` may give
    the tool-use ID (``tool_id``) and an edition selection (``editions``)."""
    tool_id = extra.get("tool_id", "toolu_1")
    arguments = {
        "coverage": coverage,
        "search_for": search_for,
        "query": query,
        "seeking": seeking,
    }
    if "editions" in extra:
        arguments["editions"] = extra["editions"]
    return _message(
        [
            {"type": "thinking", "thinking": "", "signature": f"sig-{tool_id}"},
            {"type": "tool_use", "id": tool_id, "name": TOOL, "input": arguments},
        ],
        "tool_use",
    )


COVERED = [
    part("Pauschale", "covered", "jul/k"),
    part("Begründung", "covered", "jul/h"),
]
ONE_MISSING = [part("Pauschale", "covered", "jul/k"), part("Begründung", "missing")]


def run_d(provider: Provider, spending, the_task=None, **options):
    return run(provider, the_task or task(), spending, condition="coverage", **options)


def tool_result(body: dict) -> dict:
    """The tool result a request carries in its last (user) message."""
    (result,) = body["messages"][-1]["content"]
    return result


# B and C as they were


def test_c_sends_the_same_requests_as_before_d_existed_and_records_no_coverage(
    spending,
):
    provider = Provider(
        Clock(),
        search_call("Pauschale", "Begründung der Pauschale"),
        final(("Die Pauschale ist neu begründet.", ["jul/c", "jul/k"])),
    )

    result, _ = run(provider, task(), spending)

    assert result.outcome == "answer"
    assert [_canonical(body) for body in provider.creates] == PINNED_C
    assert _sha(provider.creates[0]["system"]) == FROZEN["c_system_prompt"]
    assert _canonical(provider.creates[0]["tools"][0]) == FROZEN["c_tool_july"]
    assert "coverage" not in result.record and "coverage" not in result.local


def test_b_sends_the_same_request_as_before_d_existed(spending):
    provider = Provider(Clock(), final(("Antwort.", ["jul/g"])))

    result, _ = run(provider, task(initial=TEN), spending, condition="fixed10")

    assert result.outcome == "answer"
    assert [_canonical(body) for body in provider.creates] == PINNED_B
    assert "coverage" not in result.record


def test_the_conditions_are_the_three_of_phase_3_and_d_beside_them():
    conditions = evidence_agent.CONDITIONS
    assert [
        (c.name, c.passages, c.calls, c.search, c.coverage) for c in conditions.values()
    ] == [
        ("fixed5", 5, 1, False, False),
        ("fixed10", 10, 1, False, False),
        ("agent", 5, 3, True, False),
        ("coverage", 5, 3, True, True),
    ]


# D's frozen request


def test_d_sends_the_frozen_instruction_tool_and_answer_format_and_otherwise_cs_request(
    spending,
):
    provider = Provider(
        Clock(), coverage_answer(COVERED, ("Antwort.", ["jul/k", "jul/h"]))
    )
    c_provider = Provider(Clock(), final(("Antwort.", ["jul/k"])))

    run_d(provider, spending)
    run(c_provider, dataclasses.replace(task(), case_id="T2"), spending)

    (d,), (c,) = provider.creates, c_provider.creates
    assert _sha(evidence_agent.COVERAGE_INSTRUCTION) == FROZEN["instruction"]
    assert (
        d["system"]
        == f"{generation.SYSTEM_PROMPT}\n\n{evidence_agent.COVERAGE_INSTRUCTION}"
    )
    assert _sha(d["system"]) == FROZEN["system_prompt"]
    assert _canonical(d["tools"][0]) == FROZEN["tool_july"]
    assert d["output_config"] == {
        "effort": "max",
        "format": {
            "type": "json_schema",
            "schema": evidence_agent.COVERAGE_ANSWER_SCHEMA,
        },
    }
    assert _canonical(evidence_agent.COVERAGE_ANSWER_SCHEMA) == FROZEN["answer_format"]
    assert (
        _canonical(evidence_agent.COVERAGE_ANSWER_SCHEMA["properties"]["answer"])
        == FROZEN["answer_schema"]
    )
    assert _canonical(evidence_agent.COVERAGE_REFUSALS) == FROZEN["refusal_reasons"]
    # Everything else is C's: the same first message, settings and tool choice.
    for key in ("model", "max_tokens", "thinking", "messages", "tool_choice"):
        assert d[key] == c[key]
    assert d["output_config"]["effort"] == c["output_config"]["effort"]


# D's two paths


def test_a_direct_answer_is_accepted_as_cs_would_be_and_its_coverage_recorded(spending):
    provider = Provider(
        Clock(), coverage_answer(COVERED, ("Antwort.", ["jul/k", "jul/h"]))
    )

    result, _ = run_d(provider, spending)

    assert (result.outcome, result.status, result.record["generation_calls"]) == (
        "answer",
        "answered",
        1,
    )
    assert result.answer == {
        "status": "answered",
        "missing_evidence": [],
        "claims": [{"text": "Antwort.", "citations": ["jul/k", "jul/h"]}],
    }  # the inner object only
    assert result.record["coverage"] == [
        {
            "call": 1,
            "action": "answer",
            "check": "ok",
            "parts": 2,
            "covered": 2,
            "missing": 0,
            "search_for": None,
            "missing_not_reported": False,
        }
    ]
    assert result.local["coverage"] == [
        {"call": 1, "coverage": COVERED, "search_for": None}
    ]
    assert [
        (e["event"], e["attempt"], e["condition"]) for e in events(spending)[1:]
    ] == [
        ("reserve", "T1-coverage-call1", "coverage"),
        ("settle", "T1-coverage-call1", "coverage"),
    ]
    assert result.record["spending"]["admission_usd"] == 4.4352  # three calls, as C


def test_a_valid_targeted_search_runs_on_cs_arguments_only(spending):
    request = coverage_search(ONE_MISSING, 2, "Pauschale", "Begründung")
    provider = Provider(
        Clock(), request, coverage_answer(COVERED, ("Antwort.", ["jul/c"]))
    )

    result, embedder = run_d(provider, spending)

    assert (result.outcome, result.record["generation_calls"]) == ("answer", 2)
    (searched,) = result.record["searches"]
    assert (searched["outcome"], searched["round"]) == ("passages", 1)
    assert [r["passage_id"] for r in searched["returned"]] == [
        "jul/c",
        "jul/b",
        "jul/f",
        "jul/d",
        "jul/e",
    ]
    assert result.local["searches"][0]["arguments"] == {
        "query": "Pauschale",
        "seeking": "Begründung",
    }
    assert embedder.queries == ["Pauschale"]
    assert result.record["coverage"][0] == {
        "call": 1,
        "action": "search",
        "check": "ok",
        "parts": 2,
        "covered": 1,
        "missing": 1,
        "search_for": 2,
        "missing_not_reported": None,
    }
    # The assistant turn goes back exactly as returned, coverage included.
    assert provider.creates[1]["messages"][1] == {
        "role": "assistant",
        "content": request["content"],
    }


def refused(
    provider: Provider, spending, request: tuple, expected: tuple, the_task=None
):
    """D's first call asks for a search with ``request`` (coverage, search_for); the search is
    refused with ``expected`` (the reason given to the model, the check's code)."""
    coverage, search_for = request
    reason, code = expected
    provider.replies[:0] = [
        coverage_search(coverage, search_for, "Pauschale", "Begründung")
    ]
    result, embedder = run_d(provider, spending, the_task)
    (searched,) = result.record["searches"]
    assert (searched["outcome"], searched["round"], searched["returned"]) == (
        "refused_coverage",
        1,
        [],
    )
    assert embedder.queries == []  # nothing ranked
    second = provider.creates[1]
    assert (
        second["tool_choice"]["type"] == "auto"
    )  # a round, budget and a later call remain
    assert tool_result(second) == {
        "type": "tool_result",
        "tool_use_id": "toolu_1",
        "is_error": True,
        "content": f"Search refused: {reason}. Searches left: 1; passages left: 5.",
    }
    assert result.record["coverage"][0]["check"] == code
    return result


def test_a_search_citing_a_passage_not_received_is_refused_and_uses_the_round(spending):
    provider = Provider(
        Clock(),
        coverage_answer(
            ONE_MISSING,
            ("Antwort.", ["jul/k"]),
            status="partial",
            missing=["Begründung"],
        ),
    )
    coverage = [part("Pauschale", "covered", "jul/c"), part("Begründung", "missing")]

    result = refused(
        provider,
        spending,
        (coverage, 2),
        ("the coverage names a passage you have not received", "passage_reference"),
    )

    assert result.outcome == "answer"


def test_a_search_for_a_part_marked_covered_is_refused(spending):
    provider = Provider(
        Clock(),
        coverage_answer(
            ONE_MISSING,
            ("Antwort.", ["jul/k"]),
            status="partial",
            missing=["Begründung"],
        ),
    )

    refused(provider, spending, (ONE_MISSING, 1), (SEARCH_FOR, "search_for"))


def test_search_for_must_be_an_integer_naming_an_existing_part(spending):
    for n, (search_for, recorded) in enumerate(
        [(0, 0), (3, 3), (True, None), ("2", None)]
    ):
        provider = Provider(
            Clock(), coverage_answer(ONE_MISSING, ("Antwort.", ["jul/k"]))
        )
        result = refused(
            provider,
            spending,
            (ONE_MISSING, search_for),
            (SEARCH_FOR, "search_for"),
            dataclasses.replace(task(), case_id=f"S{n}"),
        )
        assert result.record["coverage"][0]["search_for"] == recorded


SEARCH_FOR = "search_for must be the number of a part marked missing in the coverage"
MALFORMED = (
    "the coverage must list 1 to 4 parts, each with part (1 to 300 characters), "
    "status covered or missing, and passages: the ids of received passages that state it, at "
    "least one when covered and none when missing"
)


def test_a_malformed_coverage_refuses_the_search(spending):
    cases = [
        [],  # no part
        [part(f"Teil {n}", "missing") for n in range(5)],  # five parts
        [
            part("Pauschale", "covered"),
            part("Begründung", "missing"),
        ],  # covered without passage
        [part("Pauschale", "missing", "jul/k")],  # missing with a passage
        [part(" ", "missing")],  # blank part
        [part("x" * 301, "missing")],  # part too long
        [{"part": "Pauschale", "status": "unclear", "passages": []}],
        [{"part": "Pauschale", "status": "missing", "passages": [], "note": "x"}],
        [{"part": "Pauschale", "status": "missing", "passages": [1]}],
        "Pauschale",
    ]
    for n, coverage in enumerate(cases):
        provider = Provider(
            Clock(), coverage_answer(ONE_MISSING, ("Antwort.", ["jul/k"]))
        )
        result = refused(
            provider,
            spending,
            (coverage, 1),
            (MALFORMED, "malformed"),
            dataclasses.replace(task(), case_id=f"M{n}"),
        )
        assert {
            k: result.record["coverage"][0][k] for k in ("parts", "covered", "missing")
        } == {"parts": None, "covered": None, "missing": None}


def test_a_part_of_exactly_300_characters_and_four_parts_are_accepted(spending):
    coverage = [part("x" * 300, "missing")] + [
        part(f"Teil {n}", "covered", "jul/k") for n in range(3)
    ]
    provider = Provider(
        Clock(),
        coverage_search(coverage, 1, "Pauschale", "Teil"),
        coverage_answer(COVERED, ("Antwort.", ["jul/k"])),
    )

    result, _ = run_d(provider, spending)

    assert result.record["searches"][0]["outcome"] == "passages"
    assert result.record["coverage"][0]["check"] == "ok"


# Gaps, stopping and the answer path


def test_a_justified_gap_is_accepted_and_an_unreported_missing_part_only_flagged(
    spending,
):
    reported = Provider(
        Clock(),
        coverage_answer(
            ONE_MISSING,
            ("Antwort.", ["jul/k"]),
            status="partial",
            missing=["Begründung"],
        ),
    )
    silent = Provider(
        Clock(), coverage_answer(ONE_MISSING, ("Antwort.", ["jul/k"]), status="partial")
    )

    first, _ = run_d(reported, spending)
    second, _ = run_d(silent, spending, dataclasses.replace(task(), case_id="T2"))

    assert (first.outcome, second.outcome) == ("answer", "answer")
    assert first.record["coverage"][0]["missing_not_reported"] is False
    assert second.record["coverage"][0]["missing_not_reported"] is True
    assert second.answer["missing_evidence"] == []


def test_no_new_evidence_then_no_capacity_ends_in_an_answer_on_the_last_call(spending):
    january = task(initial=("jan/a", "jan/b", "jan/c", "jan/d"), editions=(JAN,))
    gap = [part("Pauschale", "covered", "jan/a"), part("Ursprung", "missing")]
    provider = Provider(
        Clock(),
        coverage_search(gap, 2, "Pauschale", "Ursprung"),
        coverage_search(gap, 2, "Ursprung Herkunft", "Ursprung", tool_id="toolu_2"),
        coverage_answer(
            gap, ("Antwort.", ["jan/a"]), status="partial", missing=["Ursprung"]
        ),
    )

    result, _ = run_d(provider, spending, january)

    assert [s["outcome"] for s in result.record["searches"]] == ["no_new_passages"] * 2
    assert [b["tool_choice"]["type"] for b in provider.creates] == [
        "auto",
        "auto",
        "none",
    ]
    assert (result.outcome, result.record["generation_calls"]) == ("answer", 3)
    assert [e["action"] for e in result.record["coverage"]] == [
        "search",
        "search",
        "answer",
    ]


def test_a_full_passage_budget_offers_no_tool_whatever_d_recorded(spending):
    provider = Provider(
        Clock(),
        coverage_search(ONE_MISSING, 2, "Pauschale", "Begründung"),
        coverage_answer(
            ONE_MISSING,
            ("Antwort.", ["jul/k"]),
            status="partial",
            missing=["Begründung"],
        ),
    )

    result, _ = run_d(provider, spending)

    assert len(result.record["supplied"]) == 10
    assert provider.creates[1]["tool_choice"] == {"type": "none"}
    assert result.outcome == "answer"


def test_an_invalid_reference_in_an_answers_coverage_is_recorded_not_rejected(spending):
    coverage = [
        part("Pauschale", "covered", "jul/c"),
        part("Begründung", "covered", "jul/h"),
    ]
    provider = Provider(Clock(), coverage_answer(coverage, ("Antwort.", ["jul/k"])))

    result, _ = run_d(provider, spending)

    assert result.outcome == "answer"
    assert result.record["coverage"][0] == {
        "call": 1,
        "action": "answer",
        "check": "passage_reference",
        "parts": 2,
        "covered": 2,
        "missing": 0,
        "search_for": None,
        "missing_not_reported": None,
    }


def test_an_answer_without_an_answer_object_is_invalid_as_a_c_answer_failing_the_schema(
    spending,
):
    for n, raw in enumerate(({"coverage": []}, ["answer"])):
        provider = Provider(Clock(), coverage_answer(None, raw=raw))
        result, _ = run_d(
            provider, spending, dataclasses.replace(task(), case_id=f"N{n}")
        )
        assert (result.outcome, result.detail) == ("invalid_answer", "schema_invalid")
        assert result.record["coverage"][0]["check"] == "malformed"


def test_an_answer_object_is_validated_exactly_as_cs(spending):
    outside = Provider(Clock(), coverage_answer(COVERED, ("Antwort.", ["jul/c"])))
    no_schema = Provider(
        Clock(),
        coverage_answer(
            COVERED,
            raw={"coverage": COVERED, "answer": {"status": "answered", "claims": []}},
        ),
    )

    first, _ = run_d(outside, spending)
    second, _ = run_d(no_schema, spending, dataclasses.replace(task(), case_id="T2"))

    assert (first.outcome, first.detail) == (
        "invalid_answer",
        "citations_outside_supplied",
    )
    assert (second.outcome, second.detail) == ("invalid_answer", "schema_invalid")
    assert first.record["coverage"][0]["check"] == "ok"  # recorded all the same


def test_a_text_that_is_not_json_is_invalid_and_its_coverage_malformed(spending):
    provider = Provider(
        Clock(), _message([{"type": "text", "text": "kein JSON"}], "end_turn")
    )

    result, _ = run_d(provider, spending)

    assert (result.outcome, result.detail) == ("invalid_answer", "schema_invalid")
    assert result.record["coverage"] == [
        {
            "call": 1,
            "action": "answer",
            "check": "malformed",
            "parts": None,
            "covered": None,
            "missing": None,
            "search_for": None,
            "missing_not_reported": None,
        }
    ]


def test_d_and_c_of_one_case_are_two_cells_in_one_set_of_books(spending):
    d = Provider(Clock(), coverage_answer(COVERED, ("Antwort.", ["jul/k"])))
    c = Provider(Clock(), final(("Antwort.", ["jul/k"])))

    first, _ = run_d(d, spending)
    second, _ = run(c, task(), spending)
    again, _ = run_d(Provider(Clock()), spending)

    assert (first.outcome, second.outcome) == ("answer", "answer")
    assert (again.outcome, again.detail) == ("refused", "already_run")
    assert evidence_agent.spending_state()["cells"] == [
        {
            "case": "T1",
            "condition": "agent",
            "question_sha256": _sha(task().question),
            "editions": [JUL],
        },
        {
            "case": "T1",
            "condition": "coverage",
            "question_sha256": _sha(task().question),
            "editions": [JUL],
        },
    ]


def test_the_coverage_check_is_one_function_for_both_paths():
    supplied = ("jul/k", "jul/h")
    check = evidence_agent.coverage_check
    assert check(COVERED, supplied) == ("ok", {"parts": 2, "covered": 2, "missing": 0})
    assert check([part("A", "covered", "jul/x")], supplied) == (
        "passage_reference",
        {"parts": 1, "covered": 1, "missing": 0},
    )
    assert check(None, supplied) == ("malformed", None)
    assert (
        evidence_search.SearchLimits().max_seeking_chars == 300
    )  # the part limit's sibling


def test_d_sends_coverage_and_search_for_before_cs_arguments(spending):
    provider = Provider(Clock(), coverage_answer(COVERED, ("Antwort.", ["jul/k"])))

    run_d(provider, spending)

    schema = provider.creates[0]["tools"][0]["input_schema"]
    assert list(schema["properties"]) == [
        "coverage",
        "search_for",
        "query",
        "seeking",
        "editions",
    ]
    assert schema["required"] == ["coverage", "search_for", "query", "seeking"]
    answer_format = provider.creates[0]["output_config"]["format"]["schema"]
    assert list(answer_format["properties"]) == ["coverage", "answer"]


def test_the_unreported_flag_needs_an_empty_list_not_an_absent_or_invalid_one(spending):
    inners = (
        {"status": "partial", "claims": []},
        {"status": "partial", "claims": [], "missing_evidence": "Begründung"},
    )
    for n, inner in enumerate(inners):
        raw = {"coverage": ONE_MISSING, "answer": inner}
        provider = Provider(Clock(), coverage_answer(None, raw=raw))
        result, _ = run_d(provider, spending, dataclasses.replace(task(), case_id=f"U{n}"))
        assert (result.outcome, result.detail) == ("invalid_answer", "schema_invalid")
        assert result.record["coverage"][0]["check"] == "ok"
        assert result.record["coverage"][0]["missing_not_reported"] is False


def test_an_integer_past_the_digit_limit_in_the_coverage_keeps_a_valid_answer(spending):
    answer = {
        "status": "answered",
        "claims": [{"text": "Antwort.", "citations": ["jul/k"]}],
        "missing_evidence": [],
    }
    text = (
        '{"coverage": [{"part": ' + "9" * 5000 + ', "status": "covered", '
        '"passages": ["jul/k"]}], "answer": ' + json.dumps(answer) + "}"
    )
    provider = Provider(Clock(), _message([{"type": "text", "text": text}], "end_turn"))

    result, _ = run_d(provider, spending)

    assert (result.outcome, result.answer) == ("answer", answer)
    assert result.record["coverage"][0]["check"] == "malformed"

