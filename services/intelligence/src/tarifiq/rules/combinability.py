"""Deterministic combinability & cumulation evaluation.

The rule set below is a FROZEN, versioned, content-hashed table — the same role frozen
records play in L1. Evaluation is a pure function of (submitted positions, frozen rules):
identical input always yields an identical verdict. No AI, no network, no arithmetic on
billing values — only relationships between codes are evaluated.

In production this table is loaded from the canonical store and stamped with the same
freeze/version/hash discipline as tariff records; here it is bundled so the service is
coherent and testable fully offline.
"""

from __future__ import annotations

import hashlib
import json

from tarifiq.models.rule_model import (
    CombinabilityCheckRequest,
    CombinabilityCheckResult,
    CombinabilityRelation,
    CombinabilityRule,
    CombinabilityVerdict,
    Conflict,
    TariffSystem,
)
from tarifiq.store.frozen_client import FrozenStore

RULE_SET_VERSION = "tardoc-combinability/2026.1"

# --- The frozen rule set (TARDOC, illustrative but internally consistent) -------------
COMBINABILITY_RULES: tuple[CombinabilityRule, ...] = (
    CombinabilityRule(
        rule_id="R-EXCL-001",
        system=TariffSystem.TARDOC,
        relation=CombinabilityRelation.EXCLUSIVE,
        code="AA.00.0010",
        related_code="AA.00.0030",
        note="In-person base consultation and phone consultation are mutually exclusive "
        "within the same encounter.",
        source="TARDOC 1.3 Anwendungsregeln (illustrative)",
    ),
    CombinabilityRule(
        rule_id="R-REQ-001",
        system=TariffSystem.TARDOC,
        relation=CombinabilityRelation.REQUIRES,
        code="AA.00.0020",
        related_code="AA.00.0010",
        note="The child surcharge may only be billed together with a base consultation.",
        source="TARDOC 1.3 Anwendungsregeln (illustrative)",
    ),
    CombinabilityRule(
        rule_id="R-CUM-001",
        system=TariffSystem.TARDOC,
        relation=CombinabilityRelation.CUMULATION_LIMIT,
        code="AA.00.0050",
        max_quantity=6,
        note="The 5-minute consultation add-on may be cumulated at most 6 times per session.",
        source="TARDOC 1.3 Anwendungsregeln (illustrative)",
    ),
)


def _content_hash(rules: tuple[CombinabilityRule, ...]) -> str:
    """Deterministic SHA-256 over the canonical rule set (order-independent)."""

    rows = sorted(
        json.dumps(rule.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        for rule in rules
    )
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


RULE_SET_HASH = _content_hash(COMBINABILITY_RULES)


def evaluate_combinability(
    request: CombinabilityCheckRequest,
    *,
    rules: tuple[CombinabilityRule, ...] = COMBINABILITY_RULES,
    store: FrozenStore | None = None,
) -> CombinabilityCheckResult:
    """Evaluate submitted positions against the frozen rule set, deterministically.

    If a ``store`` is supplied, codes unknown to the frozen tariff store are reported and
    force a ``REQUIRES_REVIEW`` verdict — TarifIQ never rules on a code it cannot anchor
    to a frozen fact.
    """

    quantities: dict[str, int] = {}
    for position in request.positions:
        quantities[position.code] = quantities.get(position.code, 0) + position.quantity
    codes = set(quantities)

    conflicts: list[Conflict] = []
    for rule in rules:
        if rule.system != request.system:
            continue
        if rule.relation is CombinabilityRelation.EXCLUSIVE:
            if rule.code in codes and rule.related_code in codes:
                conflicts.append(
                    Conflict(
                        rule_id=rule.rule_id,
                        relation=rule.relation,
                        codes=[rule.code, rule.related_code],
                        message=f"{rule.code} and {rule.related_code} are not combinable: {rule.note}",
                    )
                )
        elif rule.relation is CombinabilityRelation.REQUIRES:
            if rule.code in codes and rule.related_code not in codes:
                conflicts.append(
                    Conflict(
                        rule_id=rule.rule_id,
                        relation=rule.relation,
                        codes=[rule.code, rule.related_code],
                        message=f"{rule.code} requires {rule.related_code}: {rule.note}",
                    )
                )
        elif rule.relation is CombinabilityRelation.CUMULATION_LIMIT:
            qty = quantities.get(rule.code, 0)
            if rule.code in codes and rule.max_quantity is not None and qty > rule.max_quantity:
                conflicts.append(
                    Conflict(
                        rule_id=rule.rule_id,
                        relation=rule.relation,
                        codes=[rule.code],
                        message=(
                            f"{rule.code} billed {qty}× exceeds the cumulation limit of "
                            f"{rule.max_quantity}: {rule.note}"
                        ),
                    )
                )

    unknown_codes: list[str] = []
    if store is not None:
        unknown_codes = sorted(
            code for code in codes if not store.exists(request.system.value, code)
        )

    if conflicts:
        verdict = CombinabilityVerdict.NOT_COMBINABLE
    elif unknown_codes:
        verdict = CombinabilityVerdict.REQUIRES_REVIEW
    else:
        verdict = CombinabilityVerdict.COMBINABLE

    return CombinabilityCheckResult(
        verdict=verdict,
        conflicts=conflicts,
        unknown_codes=unknown_codes,
        rule_set_version=RULE_SET_VERSION,
        rule_set_hash=RULE_SET_HASH,
    )
