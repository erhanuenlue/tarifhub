"""Structural branches of the pre-freeze rule validator (deterministic, offline).

The existing suite covers the happy path plus the missing-related-code, missing-max and
unknown-code cases. This file pins the remaining branches of ``validate_rule``: empty
identifiers, a self-referential code, the "ignored field" warnings for each relation, and
the empty-code skip in the referential-integrity loop. All pure functions of
(rule, bundled store); no network.
"""

from __future__ import annotations

from tarifiq.models.rule_model import (
    CombinabilityRelation,
    CombinabilityRule,
    TariffSystem,
)
from tarifiq.store.frozen_client import bundled_offline_store
from tarifiq.validators.rule_validator import validate_rule


def _rule(**overrides) -> CombinabilityRule:
    base = {
        "rule_id": "R-TEST-001",
        "system": TariffSystem.TARDOC,
        "relation": CombinabilityRelation.EXCLUSIVE,
        "code": "AA.00.0010",
        "related_code": "AA.00.0030",
        "source": "manual",
    }
    base.update(overrides)
    return CombinabilityRule(**base)


def test_empty_rule_id_and_code_are_reported_as_errors():
    """Blank ``rule_id`` and ``code`` each fail the structural check."""

    result = validate_rule(_rule(rule_id="", code=""))
    assert result.ok is False
    assert "rule_id is empty" in result.errors
    assert "code is empty" in result.errors


def test_code_equal_to_related_code_is_rejected():
    """A relation whose two codes are identical is not a valid pairing."""

    result = validate_rule(_rule(code="AA.00.0010", related_code="AA.00.0010"))
    assert result.ok is False
    assert "code and related_code must differ" in result.errors


def test_max_quantity_on_a_pairwise_relation_warns():
    """``max_quantity`` is meaningless for EXCLUSIVE/REQUIRES and yields a warning, not an error."""

    result = validate_rule(_rule(max_quantity=3), store=bundled_offline_store())
    assert result.ok is True
    assert any("max_quantity is ignored" in w for w in result.warnings)


def test_related_code_on_cumulation_limit_warns():
    """``related_code`` is meaningless for CUMULATION_LIMIT and yields a warning, not an error."""

    result = validate_rule(
        _rule(
            relation=CombinabilityRelation.CUMULATION_LIMIT,
            code="AA.00.0050",
            related_code="AA.00.0010",
            max_quantity=6,
        ),
        store=bundled_offline_store(),
    )
    assert result.ok is True
    assert any("related_code is ignored" in w for w in result.warnings)


def test_blank_code_is_skipped_in_the_referential_check():
    """A blank code cannot be resolved against the store, so it is skipped, not looked up."""

    result = validate_rule(
        _rule(
            relation=CombinabilityRelation.CUMULATION_LIMIT,
            code="   ",
            related_code=None,
            max_quantity=6,
        ),
        store=bundled_offline_store(),
    )
    assert result.ok is False
    assert "code is empty" in result.errors
    # The whitespace code is never handed to the store, so nothing was referentially checked.
    assert result.checked_codes == []
