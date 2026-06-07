"""Deterministic validation of a candidate combinability rule before freeze.

This is the gate every rule must pass before a human freezes it — including any rule a
model *suggested* pre-freeze. Pure function of (rule, frozen store): structural checks
plus referential checks (the codes a rule talks about must exist as frozen tariff facts).
No AI, no network of its own (the optional store does the frozen-fact lookups).
"""

from __future__ import annotations

from tarifiq.models.rule_model import (
    CombinabilityRelation,
    CombinabilityRule,
    RuleValidationResult,
)
from tarifiq.store.frozen_client import FrozenStore


def validate_rule(rule: CombinabilityRule, *, store: FrozenStore | None = None) -> RuleValidationResult:
    """Validate a candidate rule structurally and (if a store is given) referentially."""

    errors: list[str] = []
    warnings: list[str] = []

    if not rule.rule_id.strip():
        errors.append("rule_id is empty")
    if not rule.code.strip():
        errors.append("code is empty")

    if rule.relation in (CombinabilityRelation.EXCLUSIVE, CombinabilityRelation.REQUIRES):
        if not rule.related_code:
            errors.append(f"{rule.relation.value} requires related_code")
        elif rule.related_code == rule.code:
            errors.append("code and related_code must differ")
        if rule.max_quantity is not None:
            warnings.append(f"max_quantity is ignored for {rule.relation.value} relations")
    elif rule.relation is CombinabilityRelation.CUMULATION_LIMIT:
        if rule.max_quantity is None:
            errors.append("CUMULATION_LIMIT requires max_quantity")
        if rule.related_code:
            warnings.append("related_code is ignored for CUMULATION_LIMIT relations")

    if not rule.source.strip():
        warnings.append("no source/provenance given for the rule")

    # Referential integrity: a rule may only be frozen if its codes are frozen facts.
    checked_codes: list[str] = []
    if store is not None:
        candidates = [rule.code]
        if rule.related_code:
            candidates.append(rule.related_code)
        for code in candidates:
            if not code.strip():
                continue
            checked_codes.append(code)
            if not store.exists(rule.system.value, code):
                errors.append(
                    f"{code} is not a frozen {rule.system.value} record (cannot freeze a "
                    "rule that references an unknown code)"
                )

    return RuleValidationResult(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        checked_codes=checked_codes,
    )
