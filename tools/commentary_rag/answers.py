"""Deterministic checks of the generated answers against the retrieval and the answer rubric.

These are checks, not semantic or legal validation: whether a cited passage really supports a
claim is left to human review. Definitions (fixed before any answer was generated):

* Retrieval: a case's gold evidence items (``cases.json``) count as retrieved when a passage
  covering them is in the request's context. Items not retrieved are retrieval misses and never
  count against the generator.
* Generation failure: no schema-valid answer for the case (error, timeout, cut-off, refusal or
  schema violation). Its retrieved items are reported separately, not as uncited evidence.
* Citation membership: cited passage IDs that are in the request's own context.
* Expected-evidence citation: retrieved gold items whose covering passage the answer cites, over
  the retrieved items of cases with a valid answer.
* Required facts (rubric): a required claim is available when a passage covering its support is
  in the context. A claim with check terms is *stated* when every term group has one variant in
  the answer's claim texts (NFC, case-folded, whitespace folded, decimal comma read as point); it
  is *stated with cited support* when the answer also cites a passage covering its support. A
  claim without check terms is left to human review. A term match for an unavailable claim is
  flagged for review (a fact from outside the context, or a negation), never credited.
* Abstention: status ``insufficient_evidence``. Expected for cases without supporting evidence;
  a false abstention is an abstention although a required claim's support was retrieved. On a
  retrieval miss the status is reported as behaviour; an abstention does not repair retrieval.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

ABSTAIN = "insufficient_evidence"
_SPACE = re.compile(r"\s+")
_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d)")


def normalize(text: str) -> str:
    """NFC, case-folded, whitespace folded, decimal comma read as a point."""

    folded = _SPACE.sub(" ", unicodedata.normalize("NFC", text).casefold()).strip()
    return _DECIMAL_COMMA.sub(".", folded)


def stated(terms: list[list[str]], text: str) -> bool:
    """Every term group has at least one variant in ``text``."""

    haystack = normalize(text)
    return all(any(normalize(v) in haystack for v in group) for group in terms)


def score_case(*, case_id: str, expected_status: str, evidence: list[set[str]],  # noqa: PLR0913
               required: list[dict], context: list[str], answer: dict | None,
               failure: str | None) -> dict:
    """The checks for one case's final answer (``None`` with ``failure`` when there is none)."""

    in_context = set(context)
    retrieved = [items for items in evidence if items & in_context]
    available = [r for r in required if r["covering"] & in_context]
    unavailable = [r for r in required if not r["covering"] & in_context]
    row = {
        "case": case_id, "expected_status": expected_status,
        "outcome": "valid" if answer else ("generation_failure" if failure else "not_attempted"),
        "failure": failure, "status": answer["status"] if answer else None,
        "evidence_items": len(evidence), "evidence_in_context": len(retrieved),
        "retrieval": ("no evidence items" if not evidence else
                      "all evidence retrieved" if len(retrieved) == len(evidence) else
                      "retrieval miss" if not retrieved else "partial retrieval miss"),
        "required_claims": len(required), "required_available": len(available),
        "required_checked": sum(1 for r in available if r["terms"]),
        "required_unchecked": sum(1 for r in available if not r["terms"]),
        "required_unavailable": len(unavailable),
        "abstention_expected": expected_status == ABSTAIN,
        "citations": None, "citations_outside_context": None, "uncited_claims": None,
        "evidence_cited": None, "required_stated": None,
        "required_stated_with_cited_support": None, "stated_without_retrieved_support": None,
        "abstained": None, "false_abstention": None,
    }
    if not answer:
        return row
    citations = [c for claim in answer["claims"] for c in claim["citations"]]
    cited = set(citations) & in_context
    text = "\n".join(claim["text"] for claim in answer["claims"])
    checked = [r for r in available if r["terms"]]
    abstained = answer["status"] == ABSTAIN
    row.update({
        "citations": len(citations),
        "citations_outside_context": [c for c in citations if c not in in_context],
        "uncited_claims": sum(1 for claim in answer["claims"] if not claim["citations"]),
        "evidence_cited": sum(1 for items in retrieved if items & cited) if retrieved else None,
        "required_stated": sum(1 for r in checked if stated(r["terms"], text)),
        "required_stated_with_cited_support": sum(
            1 for r in checked if stated(r["terms"], text) and r["covering"] & cited),
        "stated_without_retrieved_support": sum(
            1 for r in unavailable if r["terms"] and stated(r["terms"], text)),
        "abstained": abstained,
        "false_abstention": abstained and bool(available),
    })
    return row


def summarize(rows: list[dict]) -> dict:
    """Totals over the case checks, each with its own denominator."""

    valid = [r for r in rows if r["outcome"] == "valid"]

    def total(key: str, among: list[dict]) -> int:
        return sum(r[key] or 0 for r in among)

    return {
        "cases": len(rows),
        "valid_answers": len(valid),
        "generation_failures": [r["case"] for r in rows if r["outcome"] == "generation_failure"],
        "not_attempted": [r["case"] for r in rows if r["outcome"] == "not_attempted"],
        "citation_membership": {
            "answers_all_in_context": sum(1 for r in valid if not r["citations_outside_context"]),
            "answers": len(valid),
            "citations_in_context": sum(r["citations"] - len(r["citations_outside_context"])
                                        for r in valid),
            "citations": total("citations", valid),
        },
        "uncited_claims": total("uncited_claims", valid),
        "evidence_citation": {
            "cited": total("evidence_cited", valid),
            "available": total("evidence_in_context", valid),
            "retrieval_missed": sum(r["evidence_items"] - r["evidence_in_context"] for r in rows),
            "in_failed_generations": sum(r["evidence_in_context"] for r in rows
                                         if r["outcome"] != "valid"),
        },
        "required_facts": {
            "stated": total("required_stated", valid),
            "stated_with_cited_support": total("required_stated_with_cited_support", valid),
            "checked": total("required_checked", valid),
            "unchecked": total("required_unchecked", valid),
            "unavailable": total("required_unavailable", valid),
            "stated_without_retrieved_support": total("stated_without_retrieved_support", valid),
        },
        "abstention": {
            "expected": sum(1 for r in valid if r["abstention_expected"]),
            "abstained_when_expected": sum(1 for r in valid
                                           if r["abstention_expected"] and r["abstained"]),
            "false_abstentions": sum(1 for r in valid if r["false_abstention"]),
            "cases_with_available_support": sum(1 for r in valid if r["required_available"]),
            "on_retrieval_miss": {r["case"]: r["status"] for r in valid
                                  if r["retrieval"] in ("retrieval miss",
                                                        "partial retrieval miss")},
        },
    }


def attempt_summary(attempts: list[dict]) -> dict:
    """Outcomes, schema compliance over completed responses, reported usage and calculated cost."""

    outcomes = Counter(a["outcome"] for a in attempts)
    usage = Counter()
    for a in attempts:
        for key in ("input_tokens", "output_tokens"):
            usage[key] += (a.get("usage") or {}).get(key, 0)
    return {
        "attempts": len(attempts),
        "outcomes": dict(outcomes),
        "schema_compliance": {"valid": outcomes["valid"],
                              "checked": outcomes["valid"] + outcomes["schema_invalid"]},
        "usage": dict(usage),
        "calculated_cost_usd": round(sum(a["cost_usd"] for a in attempts), 6),
    }
