"""Offline tests for condition D, the coverage decision (Phase 4), and for B and C staying as they were.

Condition D (``coverage``) is the Phase 3 agent with three differences fixed in the frozen
contract ``phase4/conditions.md``: its appended instruction, the input schema of its search tool
and its answer format ``{"coverage": [...], "answer": {...}}``. Every test runs the real loop at
the provider's HTTP boundary with the fixtures of ``test_evidence_agent`` (temporary books, a
stand-in clock, the synthetic two-edition corpus of ``test_evidence_search``). The frozen texts
and schemas are checked against the SHA-256 values the contract recorded before D existed. D is
booked in Phase 4's books under repetition 1 (``phase4/amendments.md``, O1); B and C are pinned
on the Phase 2 and 3 books, as they were before D existed.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path

import httpx
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
    phase4_books,
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
    """Phase 4's books, where D is booked (phase4/amendments.md, O1)."""
    return phase4_books()


@pytest.fixture
def phase3_spending() -> evidence_agent.Spending:
    """The Phase 2 and 3 books, on which B's and C's requests were pinned before D existed."""
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
    return run(
        provider,
        the_task or task(),
        spending,
        condition="coverage",
        repetition=1,
        **options,
    )


def tool_result(body: dict) -> dict:
    """The tool result a request carries in its last (user) message."""
    (result,) = body["messages"][-1]["content"]
    return result


# B and C as they were


def test_c_sends_the_same_requests_as_before_d_existed_and_records_no_coverage(
    phase3_spending,
):
    provider = Provider(
        Clock(),
        search_call("Pauschale", "Begründung der Pauschale"),
        final(("Die Pauschale ist neu begründet.", ["jul/c", "jul/k"])),
    )

    result, _ = run(provider, task(), phase3_spending)

    assert result.outcome == "answer"
    assert [_canonical(body) for body in provider.creates] == PINNED_C
    assert _sha(provider.creates[0]["system"]) == FROZEN["c_system_prompt"]
    assert _canonical(provider.creates[0]["tools"][0]) == FROZEN["c_tool_july"]
    assert "coverage" not in result.record and "coverage" not in result.local


def test_b_sends_the_same_request_as_before_d_existed(phase3_spending):
    provider = Provider(Clock(), final(("Antwort.", ["jul/g"])))

    result, _ = run(provider, task(initial=TEN), phase3_spending, condition="fixed10")

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
    run(c_provider, dataclasses.replace(task(), case_id="T2"), spending, repetition=1)

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
        ("reserve", "T1-coverage-r1-call1", "coverage"),
        ("settle", "T1-coverage-r1-call1", "coverage"),
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
    second, _ = run(c, task(), spending, repetition=1)
    again, _ = run_d(Provider(Clock()), spending)

    assert (first.outcome, second.outcome) == ("answer", "answer")
    assert (again.outcome, again.detail) == ("refused", "already_run")
    assert evidence_agent.spending_state(books="phase4")["cells"] == [
        {
            "case": "T1",
            "condition": "agent",
            "repetition": 1,
            "question_sha256": _sha(task().question),
            "editions": [JUL],
        },
        {
            "case": "T1",
            "condition": "coverage",
            "repetition": 1,
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


# Phase 4's books (phase4/amendments.md, O1)


def test_d_is_refused_in_the_phase2_and_3_books_before_anything_is_counted(
    phase3_spending,
):
    provider = Provider(Clock(), coverage_answer(COVERED, ("Antwort.", ["jul/k"])))
    with pytest.raises(ValueError, match="only in the Phase 4 books"):
        run(provider, task(), phase3_spending, condition="coverage")
    assert (provider.counts, provider.creates) == ([], [])
    assert not phase3_spending.ledger.exists()


@pytest.mark.parametrize(
    ("condition", "repetition", "phase4", "match"),
    [
        ("coverage", 2, True, "admit repetition 1 only"),
        ("coverage", True, True, "admit repetition 1 only"),
        ("coverage", "1", True, "admit repetition 1 only"),
        ("fixed5", 1, True, "B, C and D only"),
        ("agent", 1, False, "no historical ledger"),
        ("agent", None, True, "the books are"),
    ],
    ids=["repetition-2", "true", "text", "a-in-phase4", "phase3-books", "no-repetition"],
)
def test_the_phase4_books_take_repetition_1_and_b_c_and_d_only(  # noqa: PLR0913
    spending, phase3_spending, condition, repetition, phase4, match
):
    provider = Provider(Clock(), final(("Antwort.", ["jul/k"])))
    books_ = spending if phase4 else phase3_spending
    with pytest.raises(ValueError, match=match):
        run(provider, task(), books_, condition=condition, repetition=repetition)
    assert (provider.counts, provider.creates) == ([], [])
    assert not spending.ledger.exists()
    assert not phase3_spending.ledger.exists()


def reservation_r1(**changes) -> dict:
    """A Phase 4 reservation of another case (Z9), changed as given."""
    row = {
        "event": "reserve",
        "attempt": "Z9-agent-r1-call1",
        "case": "Z9",
        "condition": "agent",
        "repetition": 1,
        "question_sha256": "0" * 64,
        "editions": [JUL],
        "call": 1,
        "request_sha256": "0" * 64,
        "counted_input_tokens": 1500,
        "reserved_usd": 0.5,
        "at": "2026-11-26T00:00:00+00:00",
    }
    row.update(changes)
    return row


PIN = {
    "event": "books",
    "ledger": "phase4-ledger.jsonl",
    "budget_usd": 40.0,
    "time_budget_s": 3600.0,  # the budget ``run`` gives every cell
    "at": "2026-11-26T00:00:00+00:00",
}
DAMAGED_PHASE4 = {
    "repetition-2": [PIN, reservation_r1(repetition=2, attempt="Z9-agent-r2-call1")],
    "condition-a": [PIN, reservation_r1(condition="fixed5", attempt="Z9-fixed5-r1-call1")],
    "no-repetition": [
        PIN,
        {k: v for k, v in reservation_r1().items() if k != "repetition"},
    ],
    "id-without-repetition": [PIN, reservation_r1(attempt="Z9-agent-call1")],
    "phase3-pin": [{**PIN, "event": "baseline"}],
    "other-limit": [{**PIN, "budget_usd": 50.0}],
}


@pytest.mark.parametrize("name", list(DAMAGED_PHASE4))
def test_phase4_books_naming_another_repetition_condition_or_limit_are_refused(
    spending, name
):
    rows = DAMAGED_PHASE4[name]
    spending.ledger.write_text("".join(json.dumps(e) + "\n" for e in rows), "utf-8")
    before = spending.ledger.read_bytes()
    provider = Provider(Clock())

    result, _ = run_d(provider, spending)

    detail = "budget_changed" if name == "other-limit" else "ledger_damaged"
    assert (result.outcome, result.detail) == ("refused", detail)
    assert (provider.counts, provider.creates) == ([], [])
    assert spending.ledger.read_bytes() == before


@pytest.mark.parametrize("cell", ["coverage", "repetition"])
def test_the_phase2_and_3_books_refuse_a_d_cell_or_a_repetition_as_damage(
    phase3_spending, cell
):
    pin = {
        "event": "baseline",
        "ledger": evidence_agent.HISTORICAL_LEDGER,
        "sha256": evidence_agent.HISTORICAL_SHA256,
        "committed_usd": 0.0,
        "budget_usd": 100.0,
        "at": "2026-11-26T00:00:00+00:00",
    }
    row = reservation_r1(attempt="Z9-agent-call1")
    if cell == "coverage":
        row = {k: v for k, v in row.items() if k != "repetition"}
        row.update(condition="coverage", attempt="Z9-coverage-call1")
    phase3_spending.ledger.write_text(
        "".join(json.dumps(e) + "\n" for e in (pin, row)), "utf-8"
    )
    provider = Provider(Clock())

    result, _ = run(provider, task(), phase3_spending)

    assert (result.outcome, result.detail) == ("refused", "ledger_damaged")
    assert provider.creates == []


def test_b_and_c_send_their_pinned_requests_in_the_phase4_books_too(spending):
    c = Provider(
        Clock(),
        search_call("Pauschale", "Begründung der Pauschale"),
        final(("Die Pauschale ist neu begründet.", ["jul/c", "jul/k"])),
    )
    b = Provider(Clock(), final(("Antwort.", ["jul/g"])))

    run(c, task(), spending, repetition=1)
    run(b, task(initial=TEN), spending, condition="fixed10", repetition=1)

    assert [_canonical(body) for body in c.creates] == PINNED_C
    assert [_canonical(body) for body in b.creates] == PINNED_B


def test_a_phase4_booking_leaves_the_phase2_and_3_books_as_they_are(
    spending, phase3_spending
):
    history = phase3_spending.baseline.read_bytes()

    result, _ = run_d(
        Provider(Clock(), coverage_answer(COVERED, ("Antwort.", ["jul/k"]))), spending
    )

    assert result.outcome == "answer"
    assert phase3_spending.baseline.read_bytes() == history
    assert not phase3_spending.ledger.exists()
    pin, reserve, settle = events(spending)
    assert {k: pin[k] for k in ("event", "ledger", "budget_usd")} == {
        "event": "books",
        "ledger": "phase4-ledger.jsonl",
        "budget_usd": 40.0,
    }
    assert (reserve["repetition"], settle["repetition"]) == (1, 1)
    assert result.record["repetition"] == 1
    assert result.record["spending"]["books"] == "phase4-ledger.jsonl"


# The limit C and D share: a lone surrogate the model escaped in a tool input


def unencodable(condition: str) -> httpx.Response:
    """A search request whose shared seeking field escapes a lone surrogate: the JSON parses,
    but the turn cannot be written as UTF-8 when it is replayed in the next request."""
    arguments = {"query": "Pauschale", "seeking": "Begründung \ud800"}
    if condition == "coverage":
        arguments = {"coverage": ONE_MISSING, "search_for": 2, **arguments}
    message = _message(
        [
            {"type": "thinking", "thinking": "", "signature": "sig-toolu_1"},
            {"type": "tool_use", "id": "toolu_1", "name": TOOL, "input": arguments},
        ],
        "tool_use",
    )
    return httpx.Response(
        200,
        content=json.dumps(message).encode("ascii"),  # the escape as the provider sends it
        headers={"content-type": "application/json", "request-id": "req_test"},
    )


@pytest.mark.parametrize("condition", ["agent", "coverage"])
def test_c_and_d_fail_alike_on_an_unencodable_replay_with_their_calls_settled(
    spending, condition
):
    provider = Provider(Clock(), unencodable(condition))

    with pytest.raises(UnicodeError):
        run(provider, task(), spending, condition=condition, repetition=1)

    # The same stage for both: the first call was sent and settled from its usage; the
    # replay fails before the next count, so nothing more is reserved or sent.
    assert (len(provider.counts), len(provider.creates)) == (1, 1)
    rows = events(spending)[1:]
    assert [(e["event"], e.get("cost_basis")) for e in rows] == [
        ("reserve", None),
        ("settle", "usage"),
    ]
    assert generation.committed_usd(spending.ledger) == 0.024
    again = Provider(Clock())  # the cell is in the books: it is never sent again
    result, _ = run(again, task(), spending, condition=condition, repetition=1)
    assert (result.outcome, result.detail) == ("refused", "already_run")
    assert again.creates == []


def test_the_frozen_cases_and_sources_are_the_freeze_records():
    freeze = json.loads(evidence_agent.FREEZE_RECORD.read_text(encoding="utf-8"))
    assert len(evidence_agent.PHASE4_CASES) == 19
    assert evidence_agent.PHASE4_CASES == {
        case["id"]: (case["question_sha256"], tuple(sorted(case["editions"])))
        for case in freeze["cases"]
    }
    assert evidence_agent.PHASE4_SOURCES == {
        doc["edition"]: doc["sha256"] for doc in freeze["source_documents"]
    }


@pytest.mark.parametrize(
    ("case_id", "question", "editions", "phase4", "match"),
    [
        ("T1", None, (JUL,), False, "frozen Phase 4 case"),
        ("T9", None, (JUL,), False, "frozen Phase 4 case"),
        ("T1", "Welche Pauschale gilt und warum? ", (JUL,), False, "frozen Phase 4 case"),
        ("T9", None, (JUL,), True, "frozen ID, question and editions only"),
        ("T1", "Welche Pauschale gilt und warum? ", (JUL,), True, "frozen ID"),
        ("T1", None, (JAN, JUL), True, "frozen ID"),
    ],
    ids=["id-and-question", "question", "id", "phase4-other-id", "phase4-other-question",
         "phase4-other-editions"],
)
def test_a_frozen_case_is_booked_in_the_phase4_books_under_its_frozen_identity_only(  # noqa: PLR0913
    phase3_spending, spending, monkeypatch, case_id, question, editions, phase4, match
):
    frozen = task()
    monkeypatch.setattr(
        evidence_agent, "PHASE4_CASES", {"T1": (_sha(frozen.question), (JUL,))}
    )
    asked = dataclasses.replace(
        frozen, case_id=case_id, question=question or frozen.question, editions=editions
    )
    provider = Provider(Clock(), final(("Antwort.", ["jul/k"])))

    with pytest.raises(ValueError, match=match):
        if phase4:
            run(provider, asked, spending, repetition=1)
        else:
            run(provider, asked, phase3_spending)

    assert (provider.counts, provider.creates) == ([], [])
    allowed = Provider(Clock(), final(("Antwort.", ["jul/k"])))
    result, _ = run(allowed, frozen, spending, repetition=1)  # its frozen identity: booked
    assert result.outcome == "answer"


def test_the_first_phase4_cell_pins_the_time_budget_and_another_is_refused(spending):
    failing = Provider(Clock(), count_reply=httpx.Response(500, json={"type": "error"}))
    result, _ = run_d(failing, spending, budget_s=60.0)
    assert result.outcome == "provider_error"
    assert not spending.ledger.exists()  # nothing booked, so no budget pinned
    run_d(Provider(Clock(), coverage_answer(COVERED, ("Antwort.", ["jul/k"]))), spending)
    pin, reserve, _ = events(spending)
    assert (pin["event"], pin["time_budget_s"], reserve["event"]) == (
        "books",
        3600.0,
        "reserve",
    )  # pinned with the first reservation
    other = Provider(Clock())

    result, _ = run(other, task(), spending, repetition=1, budget_s=1800.0)

    assert (result.outcome, result.detail) == ("refused", "time_budget_changed")
    assert (other.counts, other.creates) == ([], [])
    for budget in (float("nan"), float("inf"), 0.0, -1.0):
        with pytest.raises(ValueError, match="time budget"):
            run(Provider(Clock()), task(), spending, repetition=1, budget_s=budget)


def kept_r1(usd: float) -> list[dict]:
    """Another case's B call in Phase 4's books, sent and kept at its whole reservation."""
    named = {"attempt": "Z9-fixed10-r1-call1", "case": "Z9", "condition": "fixed10"}
    reserve = reservation_r1(**named, reserved_usd=usd)
    settle = {
        "event": "settle",
        **named,
        "repetition": 1,
        "sent": True,
        "cost_usd": usd,
        "cost_basis": "reservation_retained",
        "above_reservation": False,
        "usage": None,
        "response_sha256": None,
        "at": "2026-11-26T00:00:00+00:00",
    }
    return [PIN, reserve, settle]


@pytest.mark.parametrize(
    ("kept", "outcome"),
    [(29.6512, "answer"), (29.651201, "refused")],
    ids=["exact-fit", "one-micro-dollar-short"],
)
def test_a_fresh_case_holds_back_its_whole_triplet_whoever_calls(spending, kept, outcome):
    # D called on its own for a fresh case: its 4.4352 would fit beside 29.651201, but B's and
    # C's 5.9136 not yet booked are held back beside it, so the whole 10.3488 must fit.
    rows = kept_r1(kept)
    spending.ledger.write_text("".join(json.dumps(e) + "\n" for e in rows), "utf-8")
    provider = Provider(Clock(), coverage_answer(COVERED, ("Antwort.", ["jul/k"])))

    result, _ = run_d(provider, spending)

    assert result.outcome == outcome
    if outcome == "refused":
        assert result.detail == "admission_budget"
        assert provider.creates == []
    else:
        assert result.record["spending"]["rest_usd"] == 5.9136
