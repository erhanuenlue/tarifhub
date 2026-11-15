"""Offline tests for the pilot's step commands: a step never overwrites what an earlier run wrote.

The recorded run's public record, plan, rerun record and ledger are evidence, and the local
review sheet is what the human review was checked against, so running a step again must refuse
instead of replacing them. Output folders are temporary; no key, no network, no model.

    uv run --project services/ingestion --frozen --offline --extra ai --extra dev \\
        python -m pytest tools/commentary_rag -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_generation

TAG = "2026-01-01"


@pytest.fixture
def folders(tmp_path, monkeypatch):
    """Point the step outputs at empty temporary folders; the live key is never present."""
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_WORKSPACE_ID"):
        monkeypatch.delenv(name, raising=False)
    results, local = tmp_path / "results", tmp_path / "local"
    results.mkdir()
    local.mkdir()
    monkeypatch.setattr(run_generation, "RESULTS", results)
    monkeypatch.setattr(run_generation, "LOCAL", local)
    monkeypatch.setattr(run_generation, "LEDGER", results / "generation-ledger.jsonl")
    return results, local


def test_report_refuses_to_overwrite_a_recorded_run(folders):
    results, _ = folders
    record = results / f"{TAG}-generation.json"
    record.write_text("recorded\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="refused: .*already exists"):
        run_generation.main(["report", "--tag", TAG, "--prepared", TAG])

    assert record.read_text(encoding="utf-8") == "recorded\n"


@pytest.mark.parametrize(("argv", "folder", "name"), [
    (["prepare"], "results", f"{TAG}-retrieval-rerun.json"),
    (["prepare"], "local", f"{TAG}-contexts.json"),
    (["plan"], "results", f"{TAG}-generation-plan.json"),
    (["run"], "local", f"{TAG}-generation/run-result.json"),
    (["run"], "results", f"{TAG}-generation.json"),
    (["run"], "local", f"{TAG}-review-sheet.md"),
    (["report", "--sheet-only"], "local", f"{TAG}-review-sheet.md"),
])
def test_every_step_refuses_before_any_work_when_its_output_exists(folders, argv, folder, name):
    existing = dict(zip(("results", "local"), folders, strict=True))[folder] / name
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("recorded\n", encoding="utf-8")

    # No key, no contexts, no model: a step that went on would fail differently.
    with pytest.raises(SystemExit, match="refused: .*already exists"):
        run_generation.main([*argv, "--tag", TAG, "--prepared", TAG])

    assert existing.read_text(encoding="utf-8") == "recorded\n"
