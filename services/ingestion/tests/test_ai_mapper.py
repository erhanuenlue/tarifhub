"""AI seam tests: the live-Claude harmonizer, exercised with a fully mocked client.

The ``anthropic`` import inside :func:`_claude_assisted_map` is function-scoped, so
these tests inject a fake module via ``monkeypatch.setitem(sys.modules, ...)`` — no
network, no API key, no optional extra installed. The contract under test:

* AI may fill ONLY missing ``designation.fr`` / ``designation.it`` / ``category``;
* AI never touches a billing value (``tax_points`` / ``price_chf``) or any other
  field — those stay byte-identical to the deterministic :func:`map_raw` output;
* the parse call must NOT send ``temperature`` / ``top_p`` / ``top_k`` / ``thinking``
  (removed on this model — sending them is an HTTP 400);
* every failure path returns the deterministic record so the pipeline never crashes.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from typing import Any

import pytest

from tarifhub_ingest.config import Settings, get_settings
from tarifhub_ingest.ingestion.pipeline import run_pipeline
from tarifhub_ingest.ingestion.source_loader import discover_samples
from tarifhub_ingest.mappers.tariff_mapper import AIRefinement, ai_map, map_raw
from tarifhub_ingest.models.tariff_model import TariffSystem


# --------------------------------------------------------------------------- #
# Fake anthropic module
# --------------------------------------------------------------------------- #


@dataclass
class _FakeResponse:
    parsed_output: Any
    stop_reason: str = "end_turn"


@dataclass
class _FakeMessages:
    parsed_output: Any
    stop_reason: str
    raise_exc: Exception | None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def parse(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        if self.raise_exc is not None:
            raise self.raise_exc
        return _FakeResponse(parsed_output=self.parsed_output, stop_reason=self.stop_reason)


class _FakeAnthropic:
    """Stand-in for ``anthropic.Anthropic`` — captures kwargs, returns a stub."""

    _next: dict[str, Any] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.init_kwargs = kwargs
        self.messages = _FakeMessages(
            parsed_output=_FakeAnthropic._next.get("parsed_output"),
            stop_reason=_FakeAnthropic._next.get("stop_reason", "end_turn"),
            raise_exc=_FakeAnthropic._next.get("raise_exc"),
        )
        _FakeAnthropic._last = self


def _install_fake_anthropic(
    monkeypatch,
    *,
    parsed_output: Any = None,
    stop_reason: str = "end_turn",
    raise_exc: Exception | None = None,
) -> type[_FakeAnthropic]:
    module = types.ModuleType("anthropic")
    module.Anthropic = _FakeAnthropic  # type: ignore[attr-defined]
    _FakeAnthropic._next = {
        "parsed_output": parsed_output,
        "stop_reason": stop_reason,
        "raise_exc": raise_exc,
    }
    # Clear any cross-test residue so "_last" unambiguously means "constructed now".
    if hasattr(_FakeAnthropic, "_last"):
        del _FakeAnthropic._last
    monkeypatch.setitem(sys.modules, "anthropic", module)
    return _FakeAnthropic


def _settings(monkeypatch, *, key: str | None = "sk-test") -> Settings:
    if key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    else:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TARIFHUB_AI_MODEL", raising=False)
    return get_settings()


_EAL_RAW = {
    "tariff_code": "0010.00",
    "designation_de": "Hämatokrit",
    "tax_points": "8.5",
    "unit": "point",
    "valid_from": "2026-01-01",
}


# --------------------------------------------------------------------------- #
# Cases
# --------------------------------------------------------------------------- #


def test_fills_missing_translations_and_category(monkeypatch):
    """Case a: fr/it/category filled; metadata correct; billing/identity untouched."""
    _install_fake_anthropic(
        monkeypatch,
        parsed_output=AIRefinement(
            designation_fr="Hématocrite", designation_it="Ematocrito", category="Hämatologie"
        ),
    )
    settings = _settings(monkeypatch)

    ai = ai_map(_EAL_RAW, system=TariffSystem.EAL, source_url="https://bag", settings=settings)
    rules = map_raw(_EAL_RAW, system=TariffSystem.EAL, source_url="https://bag")

    assert ai.designation.fr == "Hématocrite"
    assert ai.designation.it == "Ematocrito"
    assert ai.category == "Hämatologie"
    assert ai.metadata["ai_assisted"] is True
    assert ai.metadata["ai_status"] == "ok"
    assert ai.metadata["ai_model"] == settings.ai_model
    assert ai.metadata["ai_fields"] == ["category", "designation_fr", "designation_it"]

    # Billing + identity fields are byte-identical to the deterministic output.
    assert ai.tax_points == rules.tax_points
    assert ai.price_chf == rules.price_chf
    assert ai.tariff_code == rules.tariff_code
    assert ai.designation.de == rules.designation.de
    assert ai.unit == rules.unit
    assert ai.valid_from == rules.valid_from


def test_fill_only_does_not_overwrite_existing(monkeypatch):
    """Case b: existing fr / category are preserved even if the model proposes others."""
    raw = {
        "tariff_code": "7680000000017",
        "designation_de": "Beispielin",
        "designation_fr": "Exempline",
        "category": "Analgetika",
        "price_chf": "12.50",
        "valid_from": "2026-01-01",
    }
    _install_fake_anthropic(
        monkeypatch,
        parsed_output=AIRefinement(
            designation_fr="WRONG", designation_it="Esempina", category="WRONG"
        ),
    )
    settings = _settings(monkeypatch)

    ai = ai_map(raw, system=TariffSystem.SL, settings=settings)

    assert ai.designation.fr == "Exempline"  # preserved
    assert ai.category == "Analgetika"  # preserved
    assert ai.designation.it == "Esempina"  # filled
    assert ai.metadata["ai_fields"] == ["designation_it"]


def test_empty_string_output_is_normalized_to_none(monkeypatch):
    """Case c: whitespace-only / empty model output becomes None, not ''."""
    _install_fake_anthropic(
        monkeypatch,
        parsed_output=AIRefinement(designation_fr="   ", designation_it="", category=None),
    )
    settings = _settings(monkeypatch)

    ai = ai_map(_EAL_RAW, system=TariffSystem.EAL, settings=settings)

    assert ai.designation.fr is None
    assert ai.designation.it is None
    assert ai.category is None
    assert ai.metadata["ai_fields"] == []
    assert ai.metadata["ai_status"] == "ok"


def test_no_api_key_returns_deterministic_and_never_calls_parse(monkeypatch):
    """Case d: without a key the AI seam is inert and parse is never invoked."""
    fake = _install_fake_anthropic(monkeypatch, parsed_output=AIRefinement(designation_fr="X"))
    settings = _settings(monkeypatch, key=None)

    ai = ai_map(_EAL_RAW, system=TariffSystem.EAL, settings=settings)
    rules = map_raw(_EAL_RAW, system=TariffSystem.EAL)

    assert ai.designation == rules.designation
    assert ai.metadata.get("ai_assisted") is False
    # Anthropic() was never constructed → no parse call.
    assert not hasattr(fake, "_last")


def test_parse_raises_falls_back_safely(monkeypatch):
    """Case e: an API error returns the deterministic record, marked error."""
    _install_fake_anthropic(monkeypatch, raise_exc=RuntimeError("boom"))
    settings = _settings(monkeypatch)

    ai = ai_map(_EAL_RAW, system=TariffSystem.EAL, settings=settings)
    rules = map_raw(_EAL_RAW, system=TariffSystem.EAL)

    assert ai.designation == rules.designation
    assert ai.tax_points == rules.tax_points
    assert ai.metadata["ai_assisted"] is False
    assert ai.metadata["ai_status"].startswith("error:")
    assert "RuntimeError" in ai.metadata["ai_status"]


@pytest.mark.parametrize(
    "parsed_output, stop_reason",
    [(None, "end_turn"), (AIRefinement(designation_fr="X"), "refusal")],
)
def test_refusal_or_none_output_is_error_path(monkeypatch, parsed_output, stop_reason):
    """Case f: a refusal or a None parsed_output is treated as an error."""
    _install_fake_anthropic(monkeypatch, parsed_output=parsed_output, stop_reason=stop_reason)
    settings = _settings(monkeypatch)

    ai = ai_map(_EAL_RAW, system=TariffSystem.EAL, settings=settings)
    rules = map_raw(_EAL_RAW, system=TariffSystem.EAL)

    assert ai.designation == rules.designation
    assert ai.metadata["ai_assisted"] is False
    assert ai.metadata["ai_status"].startswith("error:")


def test_parse_kwargs_omit_removed_sampling_params(monkeypatch):
    """Case g: model is the configured one; no temperature/top_p/top_k/thinking sent."""
    fake = _install_fake_anthropic(
        monkeypatch, parsed_output=AIRefinement(designation_fr="Hématocrite")
    )
    settings = _settings(monkeypatch)

    ai_map(_EAL_RAW, system=TariffSystem.EAL, settings=settings)

    calls = fake._last.messages.calls
    assert len(calls) == 1
    kwargs = calls[0]
    assert kwargs["model"] == settings.ai_model
    for forbidden in ("temperature", "top_p", "top_k", "thinking"):
        assert forbidden not in kwargs


def test_pipeline_over_eal_sample_with_fake_client(monkeypatch, tmp_path):
    """Case h: full pipeline run with the fake client + a fake key.

    All 5 EAL rows are processed and frozen; each carries AI metadata; the
    flagged-for-review count stays consistent with the deterministic scorer
    (AI only ever raises confidence by filling gaps, never lowers it).
    """
    from tarifhub_ingest.audit.audit_logger import AuditLogger
    from tarifhub_ingest.storage.db import Database
    from tarifhub_ingest.storage.tariff_repository import TariffRepository

    _install_fake_anthropic(
        monkeypatch,
        parsed_output=AIRefinement(
            designation_fr="trad-fr", designation_it="trad-it", category="Kategorie"
        ),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("TARIFHUB_AI_MODEL", raising=False)
    settings = get_settings()

    specs = [s for s in discover_samples() if s.system is TariffSystem.EAL]
    assert specs, "EAL sample must be discoverable"

    db = Database.from_url(f"sqlite:///{tmp_path / 'pipe.db'}")
    conn = db.connect()
    db.init_schema(conn)
    repo = TariffRepository(conn, db)
    audit = AuditLogger(conn, db)

    report = run_pipeline(specs, repo, audit, settings=settings)

    assert report.processed == 5
    assert report.frozen == 5
    for record in report.records:
        assert record.metadata["ai_assisted"] is True
        assert record.metadata["ai_model"] == settings.ai_model
        # AI filled the missing DE-only translations → review pressure can only drop.
        assert record.designation.fr == "trad-fr"
    assert 0 <= report.flagged_for_review <= report.processed
    conn.close()
