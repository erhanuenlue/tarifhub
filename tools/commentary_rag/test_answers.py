"""Offline tests for the answer checks: small examples with denominators worked out by hand.

    uv run --project services/ingestion --frozen --offline --extra ai --extra dev \\
        python -m pytest tools/commentary_rag -q
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import answers


def claim(text: str, *citations: str) -> dict:
    return {"text": text, "citations": list(citations)}


def reply(status: str, *claims: dict) -> dict:
    return {"status": status, "claims": list(claims), "missing_evidence": []}


def required(rid: str, covering: set[str], terms: list[list[str]] | None) -> dict:
    return {"id": rid, "covering": covering, "terms": terms}


# A: evidence retrieved and cited; one required fact checked by its terms, one only by a person.
A = answers.score_case(
    case_id="A", expected_status="answered", evidence=[{"a1"}], context=["a1", "x"],
    required=[required("A-R1", {"a1"}, [["64.4"]]), required("A-R2", {"a1"}, None)],
    answer=reply("answered", claim("Der Tarif steigt auf 64,4 TP.", "a1"), claim("Ohne Beleg.")),
    failure=None)
# B: retrieval miss (neither item retrieved); the generator abstains.
B = answers.score_case(
    case_id="B", expected_status="answered", evidence=[{"b1"}, {"b2"}], context=["y", "z"],
    required=[required("B-R1", {"b1"}, [["59.4"]])],
    answer=reply("insufficient_evidence", claim("Die Passagen nennen nur die Auftragstaxe.", "y")),
    failure=None)
# C: no evidence exists; abstention is expected but the answer is partial, one citation outside.
C = answers.score_case(
    case_id="C", expected_status="insufficient_evidence", evidence=[], context=["c1"], required=[],
    answer=reply("partial", claim("AFP ist die Position 1034.00.", "c1", "zz")), failure=None)
# D: evidence retrieved, but no valid answer came back.
D = answers.score_case(
    case_id="D", expected_status="answered", evidence=[{"d1"}], context=["d1"],
    required=[required("D-R1", {"d1"}, [["1006.00"]])], answer=None, failure="schema_invalid")
# E: retrieval miss, yet the answer states the missing fact: flagged for review, not credited.
E = answers.score_case(
    case_id="E", expected_status="answered", evidence=[{"e1"}], context=["e9"],
    required=[required("E-R1", {"e1"}, [["64.4"]])],
    answer=reply("answered", claim("Der Tarif beträgt 64.4 TP.", "e9")), failure=None)


def test_case_checks_separate_retrieval_misses_generation_failures_and_abstention():
    assert (A["retrieval"], A["evidence_cited"], A["evidence_in_context"]) == (
        "all evidence retrieved", 1, 1)
    assert (A["required_checked"], A["required_stated"], A["required_stated_with_cited_support"],
            A["required_unchecked"], A["uncited_claims"]) == (1, 1, 1, 1, 1)
    assert (B["retrieval"], B["evidence_cited"], B["required_unavailable"], B["abstained"],
            B["false_abstention"]) == ("retrieval miss", None, 1, True, False)
    assert (C["retrieval"], C["citations_outside_context"], C["abstained"],
            C["abstention_expected"]) == ("no evidence items", ["zz"], False, True)
    assert (D["outcome"], D["failure"], D["evidence_in_context"], D["evidence_cited"]) == (
        "generation_failure", "schema_invalid", 1, None)
    assert (E["retrieval"], E["required_unavailable"], E["stated_without_retrieved_support"]) == (
        "retrieval miss", 1, 1)

    summary = answers.summarize([A, B, C, D, E])

    assert (summary["valid_answers"], summary["generation_failures"]) == (4, ["D"])
    # Answers whose citations all lie in their context: A, B, E of A, B, C, E.
    # Citations: A 1, B 1, C 2 (one outside), E 1 -> 4 of 5 in context.
    assert summary["citation_membership"] == {
        "answers_all_in_context": 3, "answers": 4, "citations_in_context": 4, "citations": 5}
    # Evidence citation counts only items retrieved for a valid answer: A's one item.
    # Retrieval misses: B 2 + E 1; D's retrieved item fell to a generation failure.
    assert summary["evidence_citation"] == {
        "cited": 1, "available": 1, "retrieval_missed": 3, "in_failed_generations": 1,
        "in_not_attempted": 0}
    assert summary["required_facts"] == {
        "stated": 1, "stated_with_cited_support": 1, "checked": 1, "unchecked": 1,
        "unavailable": 2, "stated_without_retrieved_support": 1}
    assert summary["abstention"] == {
        "expected": 1, "abstained_when_expected": 0, "false_abstentions": 0,
        "cases_with_available_support": 1,
        "on_retrieval_miss": {"B": "insufficient_evidence", "E": "answered"}}
    assert summary["uncited_claims"] == 1


def test_attempt_summary_counts_schema_compliance_over_completed_responses_only():
    attempts = [{"outcome": o, "cost_usd": c, "usage": u} for o, c, u in [
        ("valid", 0.10, {"input_tokens": 1000, "output_tokens": 4000}),
        ("schema_invalid", 0.05, {"input_tokens": 1000, "output_tokens": 2000}),
        ("stop_max_tokens", 0.64, {"input_tokens": 1000, "output_tokens": 32000}),
        ("timeout", 0.6444, None),
        ("http_529", 0.0, None),
        ("valid", 0.08, {"input_tokens": 900, "output_tokens": 3000}),
    ]]

    summary = answers.attempt_summary(attempts)

    # Completed responses checked against the schema: 2 valid + 1 invalid; the cut-off one is
    # a stop failure, the timeout and the 529 got no response at all.
    assert summary["schema_compliance"] == {"valid": 2, "checked": 3}
    assert summary["outcomes"] == {"valid": 2, "schema_invalid": 1, "stop_max_tokens": 1,
                                   "timeout": 1, "http_529": 1}
    assert summary["usage"] == {"input_tokens": 3900, "output_tokens": 41000}
    assert summary["calculated_cost_usd"] == 1.5144


def test_evidence_of_an_unattempted_case_is_not_counted_as_a_failed_generation():
    # F: evidence retrieved, but the case was never sent (budget or attempt cap).
    unattempted = answers.score_case(
        case_id="F", expected_status="answered", evidence=[{"f1"}], context=["f1"],
        required=[required("F-R1", {"f1"}, [["1006.00"]])], answer=None, failure=None)

    summary = answers.summarize([D, unattempted])

    assert (summary["generation_failures"], summary["not_attempted"]) == (["D"], ["F"])
    # D's one retrieved item fell to a generation failure; F's was never sent.
    assert summary["evidence_citation"] == {
        "cited": 0, "available": 0, "retrieval_missed": 0, "in_failed_generations": 1,
        "in_not_attempted": 1}
