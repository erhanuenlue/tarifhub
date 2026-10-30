"""Edition comparison of dated BAG AL editions (offline: temp DBs, committed fixtures).

The seams are ``compare_editions`` over databases that ``import_manifest`` filled (states the
import refuses to create come from the pipeline and repository write paths the import tests
use) and the CLI's ``main``. Expected values are the BAG figures of the four fixture
positions, read from the workbooks with openpyxl, never recomputed by the code under test.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import types
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest
from test_bag_eal import GERMAN_TEXT_COLUMNS, TEXT_FIXTURES
from test_manifest_import import (
    _EAL_URL,
    _EDITION_FIXTURES,
    _JAN,
    _JUL,
    _audit_count,
    _legacy_import,
    _snapshot,
    _stage,
    _write_manifest,
)

from tarifhub_ingest.adapters import bag_eal
from tarifhub_ingest.audit.audit_logger import AuditLogger
from tarifhub_ingest.config import get_settings
from tarifhub_ingest.ingestion.edition_comparison import EditionComparisonError, compare_editions
from tarifhub_ingest.ingestion.manifest import import_manifest
from tarifhub_ingest.ingestion.pipeline import run_pipeline
from tarifhub_ingest.ingestion.source_loader import SourceSpec
from tarifhub_ingest.mappers.tariff_mapper import AIRefinement, map_raw
from tarifhub_ingest.models.tariff_model import TariffSystem
from tarifhub_ingest.review import ReviewDecision
from tarifhub_ingest.review_service import apply_review_decision
from tarifhub_ingest.storage.tariff_repository import TariffRepository
from tarifhub_ingest.versioning.freeze_record import freeze


@pytest.fixture()
def store(engine, monkeypatch):
    """Repository, connection and database on an isolated, schema-initialised DB, no API key."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    conn = engine.db.connect()
    try:
        yield TariffRepository(conn, engine.db), conn, engine.db
    finally:
        conn.close()


def _stage_file(root: Path, effective: date, source: Path) -> dict:
    """Copy ``source`` under ``root`` as the full list of edition ``effective``."""
    target = root / "data" / "raw" / "bag" / "al" / effective.isoformat() / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    document = {
        "kind": "full_list_xlsx",
        "path": target.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }
    return {"effective_date": effective.isoformat(), "documents": [document]}


def _variant(root: Path, effective: date, source: Path, edit) -> dict:
    """Stage an edited copy of ``source`` (``edit`` runs on every sheet) as ``effective``."""
    workbook = openpyxl.load_workbook(source)
    for sheet in workbook.worksheets:
        edit(sheet)
    edited = root / "variants" / effective.isoformat() / source.name
    edited.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(edited)
    return _stage_file(root, effective, edited)


def _imported(root, store) -> Path:
    """Import both fixture editions from a manifest under ``root``; return the manifest."""
    _, conn, db = store
    manifest = _write_manifest(root, [_stage(root, _JAN), _stage(root, _JUL)])
    import_manifest(manifest, conn, db)
    return manifest


def _text_editions(root, store, january=None, july=None) -> Path:
    """Import the text fixture pair (or the staged ``january``/``july`` variants of it)."""
    _, conn, db = store
    january = january or _stage_file(root, _JAN, TEXT_FIXTURES[_JAN])
    july = july or _stage_file(root, _JUL, TEXT_FIXTURES[_JUL])
    manifest = _write_manifest(root, [january, july])
    import_manifest(manifest, conn, db)
    return manifest


def _unlisted_position(manifest: Path, repo: TariffRepository) -> None:
    """Store a January-dated position that no fixture workbook lists (as the import tests)."""
    seed = {
        "tariff_code": "9999",
        "designation_de": "Nicht in dieser Ausgabe",
        "tax_points": "1.0",
        "valid_from": _JAN,
        "source_version": "BAG AL 2026-01-01",
    }
    repo.add(freeze(map_raw(seed, system=TariffSystem.EAL, source_url=_EAL_URL)))


def test_positions_are_classified_as_added_removed_changed_or_unchanged(tmp_path, store):
    _, conn, db = store
    manifest = _imported(tmp_path, store)

    result = compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)

    assert [p.tariff_code for p in result.added] == ["1779"]
    assert result.removed == ()
    assert [p.tariff_code for p in result.changed] == ["1368", "4700"]
    assert result.unchanged == ("1000",)


def test_changed_positions_carry_exact_values_and_their_members_record_hashes(tmp_path, store):
    repo, conn, db = store
    manifest = _imported(tmp_path, store)
    stored = {(r.tariff_code, r.valid_from): r for r in repo.list_all()}

    result = compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)

    changed = {p.tariff_code: p for p in result.changed}
    assert [c.model_dump() for c in changed["1368"].changes] == [
        {"field": "tax_points", "from_value": "59.4", "to_value": "64.4"}
    ]
    assert [c.model_dump() for c in changed["4700"].changes] == [
        {"field": "tax_points", "from_value": "21.6", "to_value": "16.6"}
    ]
    for code in ("1368", "4700"):
        before, after = changed[code].from_record, changed[code].to_record
        assert (before.version, before.record_hash) == (1, stored[(code, _JAN)].record_hash)
        assert (after.version, after.record_hash) == (2, stored[(code, _JUL)].record_hash)


def test_added_position_lists_its_compared_values_and_record(tmp_path, store):
    repo, conn, db = store
    manifest = _imported(tmp_path, store)
    july_1779 = next(r for r in repo.list_all() if r.tariff_code == "1779")

    result = compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)

    (added,) = result.added
    assert added.values == {
        "category": "Chemie",
        "designation.de": "Placental Growth Factor (PlGF)",
        "designation.fr": "Placental Growth Factor (PlGF)",
        "designation.it": "Fattore di crescita placentare (placental growth factor, PlGF)",
        "price_chf": None,
        "tax_points": "73.3",
        "unit": "point",
    }
    assert (added.record.version, added.record.record_hash) == (1, july_1779.record_hash)


def test_editions_cite_their_manifest_documents_source_version_and_size(tmp_path, store):
    _, conn, db = store
    january, july = _stage(tmp_path, _JAN), _stage(tmp_path, _JUL)
    manifest = _write_manifest(tmp_path, [january, july])
    import_manifest(manifest, conn, db)

    result = compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)

    assert result.from_edition.model_dump(mode="json") == {
        "effective_date": "2026-01-01",
        "source_version": "BAG AL 2026-01-01",
        "positions": 3,
        "documents": january["documents"],
    }
    assert result.to_edition.model_dump(mode="json") == {
        "effective_date": "2026-07-01",
        "source_version": "BAG AL 2026-07-01",
        "positions": 4,
        "documents": july["documents"],
    }


# The German header of both fixture workbooks (the real BAG layout), minus the three columns
# the parser carries, the seven discipline flags it reads only to pick the category and the
# columns compared as published text (GERMAN_TEXT_COLUMNS).
_GERMAN_COLUMNS_NOT_COMPARED = (
    "Kapitel / Unterkapitel",
    "Analysentechnik",
    "Probenmaterial",
    "Resultat",
    "Anwendungen pro Primärprobe",
    "Hebammen",
    "Chiropraktoren oder Chiropraktorinnen",
    "Aufnahme (Datum)",
    "letzte Änderung (Datum)",
)


def test_result_declares_compared_fields_and_the_workbook_columns_it_cannot_see(tmp_path, store):
    _, conn, db = store
    manifest = _imported(tmp_path, store)

    result = compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)

    assert result.compared_fields == (
        "category",
        "designation.de",
        "designation.fr",
        "designation.it",
        "price_chf",
        "tax_points",
        "unit",
    )
    scope = result.scope_limitation
    assert scope.columns_compared == {
        "Deutsch": ("Pos.-Nr.", "TP", "Bezeichnung"),
        "Français": ("No. Pos.", "Dénomination"),
        "Italiano": ("No. pos.", "Denominazione"),
    }
    assert scope.columns_compared_only_as_category == {
        "Deutsch": (
            "Chemie",
            "Hämatologie",
            "Immunologie",
            "Genetik",
            "Mikrobiologie",
            "Spezialanalyse",
            "Basisanalyse",
        )
    }
    assert scope.columns_compared_as_text == {
        "Deutsch": tuple(name for name, _ in GERMAN_TEXT_COLUMNS)
    }
    assert scope.columns_not_compared["Deutsch"] == _GERMAN_COLUMNS_NOT_COMPARED
    for sheet, carried in (("Français", "Dénomination"), ("Italiano", "Denominazione")):
        assert {"Limitation", "Limitazioni"} & set(scope.columns_not_compared[sheet])
        assert carried not in scope.columns_not_compared[sheet]


def test_review_correction_is_cited_without_replacing_the_member_or_blocking(
    tmp_path, store, monkeypatch
):
    repo, conn, db = store
    monkeypatch.setenv("TARIFHUB_REVIEW_THRESHOLD", "1.01")  # flag every record for review
    if db.dialect == "postgresql":  # vector(1024) rejects the 16-dim stub (as test_review_api)
        monkeypatch.setattr("tarifhub_ingest.review_service.get_embedder", lambda *a, **k: None)
    settings = get_settings()
    january, july = _stage(tmp_path, _JAN), _stage(tmp_path, _JUL)
    import_manifest(_write_manifest(tmp_path, [january]), conn, db, settings=settings)
    decision = ReviewDecision(
        tariff_system=TariffSystem.EAL,
        tariff_code="4700",
        action="correct",
        corrections={"designation.de": "Auftragstaxe (korrigiert)"},
    )
    apply_review_decision(decision, repo=repo, audit=AuditLogger(conn, db), settings=settings)
    manifest = _write_manifest(tmp_path, [january, july])
    import_manifest(manifest, conn, db, settings=settings)

    result = compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)

    (position,) = [p for p in result.changed if p.tariff_code == "4700"]
    assert [c.field for c in position.changes] == ["tax_points"]  # no designation change
    assert (position.from_record.version, position.from_record.successor_versions) == (1, (2,))
    assert (position.to_record.version, position.to_record.successor_versions) == (3, ())


@pytest.mark.parametrize(
    ("from_date", "to_date", "problem"),
    [
        (_JAN, date(2026, 4, 1), "edition 2026-04-01 is not listed in the manifest"),
        (_JUL, _JAN, "2026-07-01 is not before 2026-01-01"),
        (_JAN, _JAN, "2026-01-01 is not before 2026-01-01"),
    ],
    ids=["unlisted", "reversed", "same"],
)
def test_editions_must_be_listed_and_in_date_order(tmp_path, store, from_date, to_date, problem):
    _, conn, db = store
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), _stage(tmp_path, _JUL)])

    with pytest.raises(EditionComparisonError, match=re.escape(problem)):
        compare_editions(manifest, conn, db, from_date=from_date, to_date=to_date)


def _off_hash(manifest: Path) -> Path:
    body = json.loads(manifest.read_text(encoding="utf-8"))
    body["editions"][1]["documents"][0]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(body), encoding="utf-8")
    return manifest


@pytest.mark.parametrize(
    ("breakage", "problem"),
    [
        (_off_hash, "sha256 mismatch"),
        (lambda manifest: manifest.with_name("missing.json"), "manifest not found"),
    ],
    ids=["document-hash", "manifest-file"],
)
def test_manifest_and_document_problems_refuse_the_comparison(tmp_path, store, breakage, problem):
    _, conn, db = store
    manifest = breakage(_imported(tmp_path, store))

    with pytest.raises(EditionComparisonError, match=problem):
        compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)


def test_incomplete_stored_edition_is_refused_so_absence_is_never_guessed(tmp_path, store):
    repo, conn, db = store
    january = _stage(tmp_path, _JAN)
    path = tmp_path / january["documents"][0]["path"]
    first = next(r for r in bag_eal.parse(path) if r["tariff_code"] == "1000")
    partial = SourceSpec(
        system=TariffSystem.EAL,
        kind="bag_eal",
        path=path,
        source_url=_EAL_URL,
        valid_from=_JAN,
        source_version="BAG AL 2026-01-01",
        rows=(first,),
    )
    run_pipeline([partial], repo, AuditLogger(conn, db))  # as if an import stopped after 1000
    july_only = tmp_path / "july-only"
    import_manifest(_write_manifest(july_only, [_stage(july_only, _JUL)]), conn, db)
    manifest = _write_manifest(tmp_path, [january, _stage(tmp_path, _JUL)])

    with pytest.raises(
        EditionComparisonError,
        match=r"edition 2026-01-01: 2 of 3 position\(s\) of its full list are not stored "
        r"\(e\.g\. 1368, 4700\)",
    ):
        compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)


def test_stored_position_its_full_list_does_not_name_is_refused(tmp_path, store):
    repo, conn, db = store
    manifest = _imported(tmp_path, store)
    _unlisted_position(manifest, repo)

    with pytest.raises(
        EditionComparisonError,
        match=r"edition 2026-01-01: 1 stored position\(s\) of that date are not in its full "
        r"list \(e\.g\. 9999\)",
    ):
        compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)


def test_stored_member_with_other_content_than_its_full_list_is_refused(tmp_path, store):
    repo, conn, db = store
    seed = {
        "tariff_code": "4700",
        "designation_de": "Auftragstaxe",
        "tax_points": "99.9",
        "valid_from": _JAN,
        "source_version": "BAG AL 2026-01-01",
    }
    repo.add(freeze(map_raw(seed, system=TariffSystem.EAL, source_url=_EAL_URL)))
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), _stage(tmp_path, _JUL)])

    with pytest.raises(
        EditionComparisonError,
        match=r"edition 2026-01-01: 1 stored position\(s\) differ from its full list "
        r"\(e\.g\. 4700\)",
    ):
        compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)


def _undated_rows(root: Path, store) -> None:
    _, conn, db = store
    january = _stage(root, _JAN)  # the BAG file name carries no date, so the rows stay undated
    _legacy_import(conn, db, root / january["documents"][0]["path"])


def _billing_successor(root: Path, store) -> None:
    repo, _, _ = store
    _imported(root, store)
    member = next(r for r in repo.list_all() if (r.tariff_code, r.valid_from) == ("4700", _JAN))
    repo.add(freeze(member.model_copy(update={"tax_points": Decimal("99.9"), "record_hash": None})))


@pytest.mark.parametrize(
    ("history", "problem"),
    [
        (_undated_rows, "have no valid_from"),
        (_billing_successor, "changes a billing or edition field"),
    ],
    ids=["undated", "billing-successor"],
)
def test_inconsistent_stored_history_is_refused(tmp_path, store, history, problem):
    _, conn, db = store
    history(tmp_path / "setup", store)
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), _stage(tmp_path, _JUL)])

    with pytest.raises(EditionComparisonError, match=problem):
        compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)


def _code_1000_as_text(sheet) -> None:
    for row in sheet.iter_rows():
        if len(row) > 1 and row[1].value == 1000:
            row[1].value = "1000.00"  # the same position, written as BAG documents cite it


def test_one_position_number_written_two_ways_is_refused(tmp_path, store):
    _, conn, db = store
    july = _variant(tmp_path, _JUL, _EDITION_FIXTURES[_JUL], _code_1000_as_text)
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), july])
    import_manifest(manifest, conn, db)

    with pytest.raises(EditionComparisonError, match=r"\(e\.g\. 1000 and 1000\.00\)"):
        compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)


def _tp_of_4700_beyond_the_scale(sheet) -> None:
    if sheet.title == "Deutsch":
        for row in sheet.iter_rows():
            if len(row) > 2 and row[1].value == 4700:
                row[2].value = 16.60001  # five decimals; tax_points holds four


def test_value_the_canonical_scale_could_not_store_exactly_is_refused(tmp_path, store):
    _, conn, db = store
    july = _variant(tmp_path, _JUL, _EDITION_FIXTURES[_JUL], _tp_of_4700_beyond_the_scale)
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), july])
    import_manifest(manifest, conn, db)

    with pytest.raises(
        EditionComparisonError,
        match=r"edition 2026-07-01: 1 position\(s\) hold a value the canonical scale could not "
        r"store exactly \(e\.g\. 4700: tax_points\)",
    ):
        compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)


class _FillingAnthropic:
    """Stand-in for the ``anthropic`` client: fills the missing Italian designation."""

    def __init__(self, **_) -> None:
        self.messages = self

    def parse(self, **_):
        refinement = AIRefinement(designation_it="Traduzione generata")
        return types.SimpleNamespace(stop_reason="end_turn", parsed_output=refinement)


def _italian_of_1000_blank(sheet) -> None:
    if sheet.title == "Italiano":
        for row in sheet.iter_rows():
            if len(row) > 3 and row[1].value == 1000:
                row[3].value = None  # Denominazione: the gap the AI seam may fill


def test_ai_filled_member_value_is_refused(tmp_path, store, monkeypatch):
    _, conn, db = store
    sdk = types.ModuleType("anthropic")
    sdk.Anthropic = _FillingAnthropic
    monkeypatch.setitem(sys.modules, "anthropic", sdk)  # the SDK boundary; no network
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    january = _variant(tmp_path, _JAN, _EDITION_FIXTURES[_JAN], _italian_of_1000_blank)
    manifest = _write_manifest(tmp_path, [january, _stage(tmp_path, _JUL)])
    import_manifest(manifest, conn, db, settings=get_settings())

    with pytest.raises(
        EditionComparisonError,
        match=r"edition 2026-01-01: 1 position\(s\) carry AI-filled fields "
        r"\(e\.g\. 1000: designation_it\)",
    ):
        compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)


@pytest.mark.parametrize(
    ("setup", "refused"),
    [
        (lambda manifest, repo: None, False),
        (lambda manifest, repo: _off_hash(manifest), True),  # refused before reading rows
        (_unlisted_position, True),  # refused after reading rows
    ],
    ids=["compared", "refused-on-the-documents", "refused-on-the-stored-rows"],
)
def test_comparison_writes_no_tariff_or_audit_row_even_when_refused(
    tmp_path, store, setup, refused
):
    repo, conn, db = store
    manifest = _imported(tmp_path, store)
    setup(manifest, repo)
    before = (_snapshot(repo), _audit_count(conn))

    try:
        compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)
    except EditionComparisonError:
        assert refused
    else:
        assert not refused

    assert (_snapshot(repo), _audit_count(conn)) == before


def _cli(*args: str) -> int:
    from tarifhub_ingest.cli import main as cli_main

    return cli_main(list(args))


def test_cli_compare_prints_the_comparison_as_json(tmp_path, store, engine, monkeypatch, capsys):
    manifest = _imported(tmp_path, store)
    monkeypatch.setenv("TARIFHUB_DB_URL", engine.db_url)

    rc = _cli("--manifest", str(manifest), "--compare", "2026-01-01", "2026-07-01")

    out, err = capsys.readouterr()
    assert (rc, err) == (0, "")
    result = json.loads(out)
    assert list(result) == [  # the frozen-record keys as before, the text comparison after them
        "from_edition",
        "to_edition",
        "compared_fields",
        "scope_limitation",
        "counts",
        "added",
        "removed",
        "changed",
        "unchanged",
        "workbook_text",
    ]
    assert result["counts"] == {"added": 1, "removed": 0, "changed": 2, "unchanged": 1}
    assert [p["tariff_code"] for p in result["changed"]] == ["1368", "4700"]
    assert result["changed"][1]["changes"] == [
        {"field": "tax_points", "from_value": "21.6", "to_value": "16.6"}
    ]
    assert result["unchanged"] == ["1000"]
    # Every requested column compared, and no text of 1000, 1368 or 4700 changed.
    text = result["workbook_text"]
    assert (text["coverage"], text["positions"]) == ("complete", [])
    assert text["counts"] == {
        "positions_compared": 3,
        "positions_with_text_changes": 0,
        "positions_in_changed": 0,
        "cells_changed": 0,
    }


def test_cli_compare_output_is_byte_identical_across_runs(
    tmp_path, store, engine, monkeypatch, capsys
):
    manifest = _imported(tmp_path, store)
    monkeypatch.setenv("TARIFHUB_DB_URL", engine.db_url)

    outputs = []
    for _ in range(2):
        assert _cli("--manifest", str(manifest), "--compare", "2026-01-01", "2026-07-01") == 0
        outputs.append(capsys.readouterr().out)

    assert outputs[0] == outputs[1]


def test_cli_compare_refusal_exits_2_with_the_problems_and_writes_nothing(
    tmp_path, store, engine, monkeypatch, capsys
):
    repo, conn, _ = store
    manifest = _off_hash(_imported(tmp_path, store))
    before = (_snapshot(repo), _audit_count(conn))
    monkeypatch.setenv("TARIFHUB_DB_URL", engine.db_url)

    rc = _cli("--manifest", str(manifest), "--compare", "2026-01-01", "2026-07-01")

    out, err = capsys.readouterr()
    assert (rc, out) == (2, "")
    refusal = json.loads(err)
    assert refusal["error"] == "edition comparison refused, nothing was written"
    assert any("sha256 mismatch" in problem for problem in refusal["problems"])
    assert (_snapshot(repo), _audit_count(conn)) == before


def test_cli_compare_refuses_a_missing_database_without_creating_it(
    tmp_path, monkeypatch, capsys
):
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), _stage(tmp_path, _JUL)])
    missing = tmp_path / "missing.db"
    monkeypatch.setenv("TARIFHUB_DB_URL", f"sqlite:///{missing}")

    rc = _cli("--manifest", str(manifest), "--compare", "2026-01-01", "2026-07-01")

    assert rc == 2
    problems = json.loads(capsys.readouterr().err)["problems"]
    assert problems == ["the database cannot be opened read-only (OperationalError)"]
    assert not missing.exists()


def _database_state(engine) -> bytes | list[tuple[str, str]]:
    """What a write or a schema would change: the SQLite file's bytes, or every relation
    (table, index, view, sequence) of the Postgres database outside its system schemas."""
    if engine.label == "sqlite":
        return Path(engine.db_url.removeprefix("sqlite:///")).read_bytes()
    conn = engine.db.connect(read_only=True)
    try:
        rows = conn.execute(
            "SELECT n.nspname, c.relname FROM pg_class c"
            " JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname <> 'information_schema' AND left(n.nspname, 3) <> 'pg_'"
        ).fetchall()
    finally:
        conn.close()
    return sorted((row["nspname"], row["relname"]) for row in rows)


def test_cli_compare_refuses_a_database_without_the_schema_and_leaves_it_untouched(
    tmp_path, bare_engine, monkeypatch, capsys
):
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), _stage(tmp_path, _JUL)])
    before = _database_state(bare_engine)
    assert not before  # it exists and holds nothing: an empty SQLite file, no Postgres relation
    monkeypatch.setenv("TARIFHUB_DB_URL", bare_engine.db_url)

    rc = _cli("--manifest", str(manifest), "--compare", "2026-01-01", "2026-07-01")

    out, err = capsys.readouterr()
    assert (rc, out) == (2, "")
    assert json.loads(err) == {
        "error": "edition comparison refused, nothing was written",
        "problems": [
            "the database lacks the required schema (a table the comparison reads is "
            "missing); the comparison never initialises a database"
        ],
    }
    assert _database_state(bare_engine) == before  # unchanged: no schema was initialised


@pytest.mark.parametrize(
    "args",
    [
        ("--compare", "2026-01-01", "2026-07-01"),
        ("--manifest", "m.json", "--compare", "2026-01-01", "2026-07-01", "--path", "x.xlsx"),
        ("--manifest", "m.json", "--compare", "2026-01-01", "2026-07-01", "--system", "EAL"),
        ("--manifest", "m.json", "--compare", "2026-01-01", "2026-07-01", "--refill"),
        ("--manifest", "m.json", "--compare", "2026-01-01", "2026-07-01", "--embeddings", "e5"),
        ("--manifest", "m.json", "--compare", "20260101", "2026-07-01"),
        ("--manifest", "m.json", "--compare", "2026-01-01"),
    ],
    ids=["no-manifest", "path", "system", "refill", "embeddings", "basic-date", "one-date"],
)
def test_cli_compare_usage_errors_exit_2_before_any_work(tmp_path, monkeypatch, args):
    never = tmp_path / "never.db"
    monkeypatch.setenv("TARIFHUB_DB_URL", f"sqlite:///{never}")

    with pytest.raises(SystemExit) as exit_info:
        _cli(*args)

    assert exit_info.value.code == 2
    assert not never.exists()


def test_position_absent_from_the_later_workbook_is_removed_with_its_values(tmp_path, store):
    _, conn, db = store
    later = date(2027, 1, 1)  # the January workbook, dated after the July one: 1779 drops out
    editions = [
        _stage_file(tmp_path, _JUL, _EDITION_FIXTURES[_JUL]),
        _stage_file(tmp_path, later, _EDITION_FIXTURES[_JAN]),
    ]
    manifest = _write_manifest(tmp_path, editions)
    import_manifest(manifest, conn, db)

    result = compare_editions(manifest, conn, db, from_date=_JUL, to_date=later)

    assert result.added == ()
    assert [(p.tariff_code, p.values["tax_points"]) for p in result.removed] == [("1779", "73.3")]
    assert {p.tariff_code: [c.model_dump() for c in p.changes] for p in result.changed} == {
        "1368": [{"field": "tax_points", "from_value": "64.4", "to_value": "59.4"}],
        "4700": [{"field": "tax_points", "from_value": "16.6", "to_value": "21.6"}],
    }


# --------------------------------------------------------------------------- #
# Published text of selected uncarried columns (ADR-024)
# --------------------------------------------------------------------------- #

_PLGF_LIMITATION = (
    "Nicht zur Bestimmung des Placental Growth Factors (PlGF) zum Screening auf Präeklampsie "
    "im ersten Trimester bei asymptomatischen Schwangeren."
)


def test_text_changes_are_listed_with_their_cells_and_leave_the_classification_alone(
    tmp_path, store
):
    _, conn, db = store
    manifest = _text_editions(tmp_path, store)

    result = compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)

    # Every compared field of 1474.1, 1762 and 4707.1 is equal, so they stay unchanged.
    assert [p.tariff_code for p in result.added] == ["1779"]
    assert (result.removed, result.changed) == ((), ())
    assert result.unchanged == ("1000", "1474.1", "1762", "4707.1")
    assert [p.model_dump(mode="json") for p in result.workbook_text.positions] == [
        {
            "tariff_code": "1474.1",
            "in_changed": False,
            "changes": [
                {
                    "column": "Limitationen",
                    "from_cell": "I4",
                    "to_cell": "I4",
                    "from_text": None,
                    "to_text": _PLGF_LIMITATION,
                },
                {
                    "column": "Kumulierbarkeit",
                    "from_cell": "K4",
                    "to_cell": "K4",
                    "from_text": "Nicht kumulierbar mit 1525.00 und 1526.00",
                    "to_text": "Nicht kumulierbar mit 1525.00, 1526.00 und 1779.00",
                },
            ],
        },
        {
            "tariff_code": "1762",  # the cell's words as written: no entitlement is inferred
            "in_changed": False,
            "changes": [
                {
                    "column": "Gynäkologie und Geburtshilfe",
                    "from_cell": "AG5",
                    "to_cell": "AG5",
                    "from_text": "Oui",
                    "to_text": "Ja",
                }
            ],
        },
        {
            "tariff_code": "4707.1",  # one row lower in July, below the new 1779
            "in_changed": False,
            "changes": [
                {
                    "column": "Kumulierbarkeit",
                    "from_cell": "K6",
                    "to_cell": "K7",
                    "from_text": "Kumulierbar mit 4707.20 bis maximal 18 Taxpunkte pro Tag",
                    "to_text": "Kumulierbar mit 4707.20 bis maximal 13 Taxpunkte pro Tag",
                }
            ],
        },
    ]


def test_full_text_coverage_states_its_columns_counts_and_workbook_sources(tmp_path, store):
    _, conn, db = store
    january = _stage_file(tmp_path, _JAN, TEXT_FIXTURES[_JAN])
    july = _stage_file(tmp_path, _JUL, TEXT_FIXTURES[_JUL])
    manifest = _text_editions(tmp_path, store, january, july)

    text = compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL).workbook_text

    names = tuple(name for name, _ in GERMAN_TEXT_COLUMNS)
    assert (text.interpretation, text.normalization) == (
        "none",
        ("unicode_nfc", "whitespace_folding"),
    )
    assert (text.coverage, text.columns_requested, text.columns_compared) == (
        "complete",
        names,
        names,
    )
    assert text.not_comparable == ()
    assert text.counts == {
        "positions_compared": 4,  # 1000, 1474.1, 1762, 4707.1; 1779 is listed only in July
        "positions_with_text_changes": 3,
        "positions_in_changed": 0,
        "cells_changed": 4,
    }
    changed_cells = {"Limitationen": 1, "Kumulierbarkeit": 2, "Gynäkologie und Geburtshilfe": 1}
    assert list(text.cells_changed_by_column.items()) == [
        (name, changed_cells.get(name, 0)) for name in names
    ]
    for source, staged in ((text.from_source, january), (text.to_source, july)):
        (document,) = staged["documents"]
        assert source.model_dump(mode="json") == {
            "document": {**document, "source_url": None},
            "sheet": "Deutsch",
            "header_row": 2,
            "headers": [
                {"column": name, "cell": cell, "text": name} for name, cell in GERMAN_TEXT_COLUMNS
            ],
        }


_LABORATORY_ON_ORDER = "Auftragslaboratorien nach Artikel 54 Absatz 3 KVV (im Fremdauftrag)"


def _respaced_and_decomposed(sheet) -> None:
    """Rewrite unchanged German texts and a flag only in how they are written: line breaks
    and runs of spaces, a no-break space, padding, decomposed umlauts (NFD)."""
    if sheet.title != "Deutsch":
        return
    for row in sheet.iter_rows(min_row=3):
        if row[1].value == 1762:  # I: Limitationen, with line breaks and umlauts
            text = row[8].value.replace(" \n", "\n  ").replace("Gynäkologie und", "Gynäkologie\xa0und")
            row[8].value = unicodedata.normalize("NFD", text) + " \n"
        elif row[1].value == 1474.1:  # J: Bemerkungen
            row[9].value = "  Für den 1.\nund  2. Parameter\t"
        elif row[1].value == 4707.1:  # I: Limitationen, without its final line break
            row[8].value = row[8].value.rstrip("\n")
        elif row[1].value == 1000:  # S: a laboratory flag
            row[18].value = " Ja\n"


def test_texts_differing_only_in_whitespace_or_unicode_form_are_equal(tmp_path, store):
    _, conn, db = store
    july = _variant(tmp_path, _JUL, TEXT_FIXTURES[_JUL], _respaced_and_decomposed)
    manifest = _text_editions(tmp_path, store, july=july)
    january_read = bag_eal.text_cells(TEXT_FIXTURES[_JAN])
    july_read = bag_eal.text_cells(tmp_path / july["documents"][0]["path"])
    for code, column in (
        ("1762", "Limitationen"),
        ("1474.1", "Bemerkungen"),
        ("4707.1", "Limitationen"),
        ("1000", _LABORATORY_ON_ORDER),
    ):  # verbatim, the cells differ
        assert january_read.rows[code][column].text != july_read.rows[code][column].text

    text = compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL).workbook_text

    assert [(p.tariff_code, c.column) for p in text.positions for c in p.changes] == [
        ("1474.1", "Limitationen"),
        ("1474.1", "Kumulierbarkeit"),
        ("1762", "Gynäkologie und Geburtshilfe"),
        ("4707.1", "Kumulierbarkeit"),
    ]


@pytest.mark.parametrize(
    "rewritten",
    [
        "Für den 1. und 3. Parameter",
        "Für den 1. und 2. Parameter.",
        "für den 1. und 2. Parameter",
        "Für den 1. bis 2. Parameter",
        "Fur den 1. und 2. Parameter",
        None,
    ],
    ids=["digit", "punctuation", "case", "word", "diacritic", "cleared"],
)
def test_every_other_difference_in_a_text_is_a_change_shown_verbatim(tmp_path, store, rewritten):
    _, conn, db = store

    def bemerkungen_of_1474_1(sheet) -> None:
        if sheet.title == "Deutsch":
            for row in sheet.iter_rows(min_row=3):
                if row[1].value == 1474.1:
                    row[9].value = rewritten  # J: Bemerkungen, "Für den 1. und 2. Parameter"

    july = _variant(tmp_path, _JUL, TEXT_FIXTURES[_JUL], bemerkungen_of_1474_1)
    manifest = _text_editions(tmp_path, store, july=july)

    text = compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL).workbook_text

    (position,) = [p for p in text.positions if p.tariff_code == "1474.1"]
    assert [c.model_dump() for c in position.changes if c.column == "Bemerkungen"] == [
        {
            "column": "Bemerkungen",
            "from_cell": "J4",
            "to_cell": "J4",
            "from_text": "Für den 1. und 2. Parameter",
            "to_text": rewritten,
        }
    ]


def _limitation_of_4700_reworded(sheet) -> None:
    if sheet.title == "Deutsch":
        for row in sheet.iter_rows(min_row=3):
            if row[1].value == 4700:
                row[8].value = "1. Einmal pro Auftrag verrechenbar.\n"  # I: "... und pro Tag ..."


def test_position_changed_in_a_compared_field_and_in_its_text_is_listed_once_per_section(
    tmp_path, store
):
    _, conn, db = store
    july = _variant(tmp_path, _JUL, _EDITION_FIXTURES[_JUL], _limitation_of_4700_reworded)
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), july])
    import_manifest(manifest, conn, db)

    result = compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)

    assert [p.tariff_code for p in result.changed] == ["1368", "4700"]  # tax_points, as before
    assert [p.model_dump(mode="json") for p in result.workbook_text.positions] == [
        {
            "tariff_code": "4700",
            "in_changed": True,
            "changes": [
                {
                    "column": "Limitationen",
                    "from_cell": "I5",
                    "to_cell": "I6",
                    "from_text": "1. Einmal pro Auftrag und pro Tag verrechenbar.\n",
                    "to_text": "1. Einmal pro Auftrag verrechenbar.\n",
                }
            ],
        }
    ]
    assert result.workbook_text.counts == {
        "positions_compared": 3,
        "positions_with_text_changes": 1,
        "positions_in_changed": 1,
        "cells_changed": 1,
    }


def _blank_row_above_1368_and_its_limitation_extended(sheet) -> None:
    if sheet.title == "Deutsch":
        for row in sheet.iter_rows(min_row=3):
            if row[1].value == 1368:
                row[8].value = "Die Kostenübernahme der Analyse ist in Evaluation bis am 30. Juni 2029."
                sheet.insert_rows(row[1].row)  # the position moves down one row
                return


def test_cells_are_cited_where_each_edition_holds_them_when_rows_shift(tmp_path, store):
    _, conn, db = store
    july = _variant(
        tmp_path, _JUL, _EDITION_FIXTURES[_JUL], _blank_row_above_1368_and_its_limitation_extended
    )
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), july])
    import_manifest(manifest, conn, db)

    result = compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)

    assert [p.model_dump(mode="json") for p in result.workbook_text.positions] == [
        {
            "tariff_code": "1368",
            "in_changed": True,
            "changes": [
                {
                    "column": "Limitationen",
                    "from_cell": "I4",
                    "to_cell": "I5",
                    "from_text": "Die Kostenübernahme der Analyse ist in Evaluation bis am 30. Juni 2028.",
                    "to_text": "Die Kostenübernahme der Analyse ist in Evaluation bis am 30. Juni 2029.",
                }
            ],
        }
    ]


def _kumulierbarkeit_renamed(sheet) -> None:
    if sheet.title == "Deutsch":
        sheet["K2"] = "Kumulierbarkeit (neu)"


def _limitationen_named_twice(sheet) -> None:
    if sheet.title == "Deutsch":
        sheet["AR2"] = "Limitationen"  # beyond the last BAG column, AQ


def _cell_of(code: float, index: int, value):
    """An edit writing ``value`` into the German cell of position ``code`` at ``index``."""

    def edit(sheet) -> None:
        if sheet.title == "Deutsch":
            for row in sheet.iter_rows(min_row=3):
                if row[1].value == code:
                    row[index].value = value

    return edit


@pytest.mark.parametrize(
    ("day", "edit", "column", "unreadable"),
    [
        (
            _JUL,
            _kumulierbarkeit_renamed,
            "Kumulierbarkeit",
            {"effective_date": "2026-07-01", "reason": "missing", "cells": []},
        ),
        (
            _JAN,
            _limitationen_named_twice,
            "Limitationen",
            {"effective_date": "2026-01-01", "reason": "repeated", "cells": ["I2", "AR2"]},
        ),
        (
            _JAN,
            _cell_of(1474.1, 10, "=1+1"),  # K: written without a cached value
            "Kumulierbarkeit",
            {"effective_date": "2026-01-01", "reason": "not_text", "cells": ["K4"]},
        ),
        (
            _JUL,
            _cell_of(4707.1, 10, 13),  # K: the cap as a number
            "Kumulierbarkeit",
            {"effective_date": "2026-07-01", "reason": "not_text", "cells": ["K7"]},
        ),
        (
            _JUL,
            _cell_of(1762, 32, True),  # AG: a boolean for "Ja"
            "Gynäkologie und Geburtshilfe",
            {"effective_date": "2026-07-01", "reason": "not_text", "cells": ["AG5"]},
        ),
        (
            _JAN,
            _cell_of(1474.1, 8, datetime(2026, 1, 1)),  # I: a date in an empty cell
            "Limitationen",
            {"effective_date": "2026-01-01", "reason": "not_text", "cells": ["I4"]},
        ),
        (
            _JUL,
            _cell_of(1000, 9, "#N/A"),  # J: an error value
            "Bemerkungen",
            {"effective_date": "2026-07-01", "reason": "not_text", "cells": ["J3"]},
        ),
    ],
    ids=["missing", "repeated", "formula", "number", "boolean", "date", "error"],
)
def test_a_requested_column_an_edition_does_not_let_us_read_counts_nowhere(
    tmp_path, store, day, edit, column, unreadable
):
    _, conn, db = store
    edited = _variant(tmp_path, day, TEXT_FIXTURES[day], edit)
    manifest = _text_editions(tmp_path, store, **{"january" if day == _JAN else "july": edited})

    result = compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)

    text = result.workbook_text
    others = tuple(name for name, _ in GERMAN_TEXT_COLUMNS if name != column)
    assert (text.coverage, text.columns_compared) == ("partial", others)
    assert [c.model_dump(mode="json") for c in text.not_comparable] == [
        {"column": column, **unreadable}
    ]
    assert tuple(text.cells_changed_by_column) == others
    assert column not in [c.column for p in text.positions for c in p.changes]
    assert column not in [h.column for s in (text.from_source, text.to_source) for h in s.headers]
    assert result.scope_limitation.columns_compared_as_text == {"Deutsch": others}
    assert column in result.scope_limitation.columns_not_compared["Deutsch"]


def _every_text_header_renamed(sheet) -> None:
    if sheet.title == "Deutsch":
        for name, cell in GERMAN_TEXT_COLUMNS:
            sheet[cell] = f"{name} (umbenannt)"


def test_cli_reports_no_text_comparison_when_no_requested_column_can_be_read(
    tmp_path, store, engine, monkeypatch, capsys
):
    july = _variant(tmp_path, _JUL, TEXT_FIXTURES[_JUL], _every_text_header_renamed)
    manifest = _text_editions(tmp_path, store, july=july)
    monkeypatch.setenv("TARIFHUB_DB_URL", engine.db_url)

    rc = _cli("--manifest", str(manifest), "--compare", "2026-01-01", "2026-07-01")

    out, err = capsys.readouterr()
    assert (rc, err) == (0, "")  # the compared fields were still compared
    result = json.loads(out)
    assert result["counts"] == {"added": 1, "removed": 0, "changed": 0, "unchanged": 4}
    text = result["workbook_text"]
    assert text["columns_requested"] == [name for name, _ in GERMAN_TEXT_COLUMNS]
    assert (text["coverage"], text["columns_compared"]) == ("unavailable", [])
    # Nothing was compared, so nothing is counted, not even as unchanged.
    assert (text["counts"], text["cells_changed_by_column"], text["positions"]) == (
        None,
        None,
        None,
    )
    assert text["not_comparable"] == [
        {"column": name, "effective_date": "2026-07-01", "reason": "missing", "cells": []}
        for name, _ in GERMAN_TEXT_COLUMNS
    ]


def test_a_position_number_written_as_a_formula_refuses_the_comparison(tmp_path, store):
    _, conn, db = store
    january = _variant(tmp_path, _JAN, TEXT_FIXTURES[_JAN], _cell_of(1000, 1, "=999+1"))
    manifest = _text_editions(tmp_path, store, january=january)

    with pytest.raises(EditionComparisonError, match=r"position number in B3 is a formula"):
        compare_editions(manifest, conn, db, from_date=_JAN, to_date=_JUL)
