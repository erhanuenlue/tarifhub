"""Cross-system isolation and the store-less evaluation path (deterministic, offline).

The bundled rule set is entirely TARDOC, so a TARMED check must skip every rule rather
than mis-apply a TARDOC constraint. Also pins that, with no store, no code is looked up
and ``unknown_codes`` stays empty (TarifIQ only anchors to frozen facts when a store is
given). Pure functions of (request, frozen rules); no network.
"""

from __future__ import annotations

from tarifiq.models.rule_model import (
    CombinabilityCheckRequest,
    CombinabilityVerdict,
    Position,
    TariffSystem,
)
from tarifiq.rules.combinability import evaluate_combinability
from tarifiq.store.frozen_client import bundled_offline_store


def test_tarmed_request_is_not_evaluated_against_tardoc_rules():
    """A TARMED check skips the TARDOC rule set: the exclusive pair does not fire."""

    request = CombinabilityCheckRequest(
        system=TariffSystem.TARMED,
        positions=[Position(code="AA.00.0010"), Position(code="AA.00.0030")],
    )
    result = evaluate_combinability(request)
    assert result.conflicts == []
    assert result.verdict is CombinabilityVerdict.COMBINABLE


def test_without_a_store_no_codes_are_flagged_unknown():
    """Absent a store, TarifIQ does not run the referential check, so nothing is unknown."""

    request = CombinabilityCheckRequest(
        system=TariffSystem.TARDOC, positions=[Position(code="ZZ.99.9999")]
    )
    result = evaluate_combinability(request)
    assert result.unknown_codes == []
    assert result.verdict is CombinabilityVerdict.COMBINABLE

    # And with a store the same unknown code IS flagged (contrast, proving the guard).
    with_store = evaluate_combinability(request, store=bundled_offline_store())
    assert with_store.unknown_codes == ["ZZ.99.9999"]
    assert with_store.verdict is CombinabilityVerdict.REQUIRES_REVIEW
