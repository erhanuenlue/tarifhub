"""The --refill surfaces: POST /ingest/sample query param + the minimal CLI.

Both are thin wrappers over ``run_pipeline(refill=...)``; the reuse behaviour itself is
covered in test_fill_reuse.py. Here we pin the wiring: the API exposes a ``refill`` bool
query param (default false) and reports it; the CLI builds a SourceSpec from --system and
runs the pipeline. Fully offline (SQLite, bundled sample, no key).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tarifhub_ingest.main import create_app


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("TARIFHUB_DB_URL", f"sqlite:///{tmp_path / 'refill_api.db'}")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return TestClient(create_app())


def test_ingest_sample_defaults_refill_false(tmp_path, monkeypatch):
    """Without the param, refill defaults False and is echoed in the response."""
    with _client(tmp_path, monkeypatch) as client:
        body = client.post("/ingest/sample").json()
    assert body["refill"] is False


def test_ingest_sample_refill_true_reingests(tmp_path, monkeypatch):
    """refill=true bypasses reuse: a second pass with refill re-runs the map (offline
    fallback fills nothing, so identical content still dedupes — but refill is honoured)."""
    with _client(tmp_path, monkeypatch) as client:
        first = client.post("/ingest/sample").json()
        second = client.post("/ingest/sample", params={"refill": "true"}).json()
    assert first["frozen"] > 0
    assert second["refill"] is True
    # Offline (no key) the re-map fills nothing, so the content is unchanged and dedupes.
    assert second["frozen"] == 0
    assert second["skipped_existing"] == first["frozen"]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _bag_eal_workbook(tmp_path):
    """A minimal real-shaped BAG EAL workbook (banner + header + one row)."""
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    de = wb.create_sheet("Deutsch")
    de.append(["Fachbereiche"])
    de.append(["Kapitel", "Pos.-Nr.", "TP", "Bezeichnung", "Chemie"])
    de.append(["k", "1000", 76.5, "Vitamin D", "Ja"])
    path = tmp_path / "analysenliste_2026-01-01.xlsx"
    wb.save(path)
    return path


def test_cli_runs_pipeline_and_prints_report(tmp_path, monkeypatch, capsys):
    """`python -m tarifhub_ingest.cli --path <eal.xlsx> --system EAL` ingests + prints."""
    from tarifhub_ingest.cli import main as cli_main

    path = _bag_eal_workbook(tmp_path)
    monkeypatch.setenv("TARIFHUB_DB_URL", f"sqlite:///{tmp_path / 'cli.db'}")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    rc = cli_main(["--path", str(path), "--system", "EAL"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "frozen" in out


def test_cli_refill_flag_is_accepted(tmp_path, monkeypatch, capsys):
    """The --refill flag is accepted and the run completes (bypasses reuse)."""
    from tarifhub_ingest.cli import main as cli_main

    path = _bag_eal_workbook(tmp_path)
    monkeypatch.setenv("TARIFHUB_DB_URL", f"sqlite:///{tmp_path / 'cli_refill.db'}")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    cli_main(["--path", str(path), "--system", "EAL"])
    rc = cli_main(["--path", str(path), "--system", "EAL", "--refill"])
    assert rc == 0
