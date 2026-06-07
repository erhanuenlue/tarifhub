"""Deterministic TARMED→TARDOC cross-walk + the offline ai_rule_suggest seam."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tarifiq.crosswalk.tarmed_tardoc import (
    CROSSWALK_HASH,
    ai_rule_suggest,
    lookup_crosswalk,
)
from tarifiq.main import create_app
from tarifiq.models.rule_model import CrosswalkMappingType


def test_one_to_one_lookup():
    result = lookup_crosswalk("00.0010")
    assert result.found is True
    assert result.entry is not None
    assert result.entry.mapping_type is CrosswalkMappingType.ONE_TO_ONE
    assert result.entry.tardoc_codes == ["AA.00.0010"]


def test_one_to_many_lookup():
    result = lookup_crosswalk("00.0510")
    assert result.entry is not None
    assert result.entry.mapping_type is CrosswalkMappingType.ONE_TO_MANY
    assert result.entry.tardoc_codes == ["AA.00.0010", "AA.00.0050"]


def test_no_equivalent_lookup():
    result = lookup_crosswalk("39.0015")
    assert result.found is True
    assert result.entry is not None
    assert result.entry.mapping_type is CrosswalkMappingType.NO_EQUIVALENT
    assert result.entry.tardoc_codes == []


def test_unknown_code_not_found():
    result = lookup_crosswalk("99.9999")
    assert result.found is False
    assert result.entry is None


def test_crosswalk_hash_is_stable():
    assert len(CROSSWALK_HASH) == 64
    assert lookup_crosswalk("00.0010").crosswalk_hash == CROSSWALK_HASH


def test_ai_rule_suggest_is_offline_placeholder_for_known_code():
    suggestion = ai_rule_suggest("00.0010")
    assert suggestion.needs_human_review is True
    assert suggestion.deterministic_placeholder is True
    assert suggestion.suggested_by == "ai_rule_suggest:placeholder"
    assert suggestion.suggested_tardoc_codes == ["AA.00.0010"]


def test_ai_rule_suggest_unknown_code_even_with_key_is_placeholder():
    # A configured key must NOT trigger a live call in this skeleton — still a placeholder.
    suggestion = ai_rule_suggest("77.7777", anthropic_api_key="sk-not-used-offline")
    assert suggestion.needs_human_review is True
    assert suggestion.deterministic_placeholder is True
    assert suggestion.mapping_type is CrosswalkMappingType.NO_EQUIVALENT


def test_endpoint_crosswalk(monkeypatch):
    monkeypatch.setenv("TARIFIQ_OFFLINE", "1")
    with TestClient(create_app()) as client:
        ok = client.get("/v1/crosswalk/00.0010")
        missing = client.get("/v1/crosswalk/99.9999")
    assert ok.status_code == 200, ok.text
    assert ok.json()["entry"]["tardoc_codes"] == ["AA.00.0010"]
    assert missing.status_code == 404
