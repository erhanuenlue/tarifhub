"""TARMED→TARDOC cross-walk: deterministic lookup of a FROZEN mapping table.

``lookup_crosswalk`` is a pure lookup of a frozen, versioned, content-hashed table — no
AI, no network. ``ai_rule_suggest`` is the single, clearly marked, replaceable seam where
a model MAY propose a candidate mapping PRE-FREEZE for a human to review; it returns a
deterministic placeholder and **calls no live API**. Per the determinism boundary test,
this module imports no LLM client: when the seam is wired to a real model, that call must
live behind the optional ``ai`` extra in an isolated module so this value path stays
import-clean, and a suggestion is never authoritative until a human validates and freezes
it (see ``POST /v1/validate``).
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from tarifiq.models.rule_model import (
    CrosswalkEntry,
    CrosswalkMappingType,
    CrosswalkResult,
    CrosswalkSuggestion,
)

CROSSWALK_VERSION = "tarmed-tardoc-crosswalk/2026.1"

# --- The frozen cross-walk table (illustrative but internally consistent) -------------
_CROSSWALK_ENTRIES: tuple[CrosswalkEntry, ...] = (
    CrosswalkEntry(
        tarmed_code="00.0010",
        tardoc_codes=["AA.00.0010"],
        mapping_type=CrosswalkMappingType.ONE_TO_ONE,
        note="Base consultation maps one-to-one.",
        source="TARMED→TARDOC transposition table (illustrative)",
    ),
    CrosswalkEntry(
        tarmed_code="00.0510",
        tardoc_codes=["AA.00.0010", "AA.00.0050"],
        mapping_type=CrosswalkMappingType.ONE_TO_MANY,
        note="Extended consultation splits into the base position plus 5-minute add-ons.",
        source="TARMED→TARDOC transposition table (illustrative)",
    ),
    CrosswalkEntry(
        tarmed_code="00.2510",
        tardoc_codes=["AA.10.0010"],
        mapping_type=CrosswalkMappingType.ONE_TO_ONE,
        note="Small rheumatology status maps one-to-one.",
        source="TARMED→TARDOC transposition table (illustrative)",
    ),
    CrosswalkEntry(
        tarmed_code="39.0015",
        tardoc_codes=[],
        mapping_type=CrosswalkMappingType.NO_EQUIVALENT,
        note="No direct TARDOC equivalent; requires manual transposition.",
        source="TARMED→TARDOC transposition table (illustrative)",
    ),
)

_BY_CODE: dict[str, CrosswalkEntry] = {entry.tarmed_code: entry for entry in _CROSSWALK_ENTRIES}


def _content_hash(entries: tuple[CrosswalkEntry, ...]) -> str:
    """Deterministic SHA-256 over the canonical cross-walk table (order-independent)."""

    rows = sorted(
        json.dumps(entry.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        for entry in entries
    )
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


CROSSWALK_HASH = _content_hash(_CROSSWALK_ENTRIES)


def lookup_crosswalk(tarmed_code: str) -> CrosswalkResult:
    """Look up a TARMED code in the frozen cross-walk table (deterministic)."""

    entry = _BY_CODE.get(tarmed_code)
    return CrosswalkResult(
        tarmed_code=tarmed_code,
        found=entry is not None,
        entry=entry,
        crosswalk_version=CROSSWALK_VERSION,
        crosswalk_hash=CROSSWALK_HASH,
    )


def ai_rule_suggest(
    tarmed_code: str,
    *,
    anthropic_api_key: Optional[str] = None,
) -> CrosswalkSuggestion:
    """PRE-FREEZE seam: *suggest* a candidate cross-walk entry for human review.

    This is the ONE place AI is meant to plug in — and it is deliberately a deterministic
    placeholder that makes no live call. Even with a key configured it returns the marked
    placeholder; wiring a real model is a future, isolated replacement (see module
    docstring). The result is always ``needs_human_review=True`` and never authoritative:
    nothing here freezes a mapping or touches a billing value.
    """

    # NOTE (replaceable): a real implementation would, only when anthropic_api_key is set,
    # call an EU-routed model with a temperature=0 structured-output prompt to PROPOSE
    # candidate TARDOC codes, then hand the proposal to a human + POST /v1/validate before
    # freeze. It must never auto-apply and never emit a price. Until then: placeholder.
    _ = anthropic_api_key  # intentionally unused by the offline placeholder

    existing = _BY_CODE.get(tarmed_code)
    if existing is not None:
        return CrosswalkSuggestion(
            tarmed_code=tarmed_code,
            suggested_tardoc_codes=list(existing.tardoc_codes),
            mapping_type=existing.mapping_type,
            rationale=(
                "A frozen cross-walk entry already exists; re-proposing it verbatim for "
                "review (placeholder — no model was called)."
            ),
        )
    return CrosswalkSuggestion(
        tarmed_code=tarmed_code,
        suggested_tardoc_codes=[],
        mapping_type=CrosswalkMappingType.NO_EQUIVALENT,
        rationale=(
            "No frozen entry found. Placeholder suggestion proposes manual transposition; "
            "a wired model would propose candidate TARDOC codes here for human review."
        ),
    )
