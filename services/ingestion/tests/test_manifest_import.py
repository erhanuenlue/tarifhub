"""Manifest-driven import of dated BAG AL editions (offline: temp DBs, committed fixtures).

The edition fixtures are four real positions copied from the BAG 1 January and 1 July
2026 workbooks by ``tests/fixtures/eal/make_edition_fixtures.py``. Like the downloads,
their names carry no ``analysenliste_YYYY-MM-DD`` date, so every date must come from the
manifest. Expected values are the BAG figures, not recomputed ones.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import sqlite3
import unicodedata
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from tarifhub_ingest.adapters import bag_eal
from tarifhub_ingest.audit.audit_logger import AuditLogger
from tarifhub_ingest.config import get_settings
from tarifhub_ingest.embeddings.embedder import E5_DIMENSION, HashingEmbedder
from tarifhub_ingest.ingestion.manifest import ManifestError, import_manifest
from tarifhub_ingest.ingestion.pipeline import run_pipeline
from tarifhub_ingest.ingestion.source_loader import SourceSpec
from tarifhub_ingest.mappers.tariff_mapper import map_raw
from tarifhub_ingest.models.tariff_model import TariffSystem
from tarifhub_ingest.review import ReviewDecision
from tarifhub_ingest.review_service import apply_review_decision
from tarifhub_ingest.storage.db import Database
from tarifhub_ingest.storage.tariff_repository import TariffRepository
from tarifhub_ingest.versioning.freeze_record import freeze

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "eal"
_EAL_URL = "https://www.bag.admin.ch/de/analysenliste-al"
_JAN = date(2026, 1, 1)
_JUL = date(2026, 7, 1)
_EDITION_FIXTURES = {
    _JAN: _FIXTURES / "Analysenliste per 1. Januar 2026_fixture.xlsx",
    _JUL: _FIXTURES / "Analysenliste per 1. Juli 2026_fixture.xlsx",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stage(root: Path, effective: date, name: str | None = None) -> dict:
    """Copy an edition fixture under ``root`` and return its manifest edition entry."""
    source = _EDITION_FIXTURES[effective]
    target = root / "data" / "raw" / "bag" / "al" / effective.isoformat() / (name or source.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return {
        "effective_date": effective.isoformat(),
        "documents": [
            {
                "kind": "full_list_xlsx",
                "path": target.relative_to(root).as_posix(),
                "sha256": _sha256(target),
                "source_url": "https://www.bag.admin.ch/dam/de/sd-web/fixture/al.xlsx",
            }
        ],
    }


def _write_manifest(root: Path, editions: list[dict], **extra) -> Path:
    body = {"manifest_version": 1, "tariff_system": "EAL", "editions": editions, **extra}
    return _write_text(root, json.dumps(body, ensure_ascii=False))


def _write_text(root: Path, text: str) -> Path:
    manifest = root / "data" / "manifests" / "bag-al.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(text, encoding="utf-8")
    return manifest


@pytest.fixture()
def store(engine, monkeypatch):
    """Repository, connection and database on an isolated, schema-initialised DB, no API key."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    conn = engine.db.connect()
    try:
        yield TariffRepository(conn, engine.db), conn, engine.db
    finally:
        conn.close()


def _history(repo: TariffRepository, code: str) -> list[tuple]:
    return [
        (r.version, r.valid_from, r.source_version, r.tax_points)
        for r in repo.list_all()
        if r.tariff_code == code
    ]


def test_january_then_july_import_creates_one_dated_version_per_edition(tmp_path, store):
    repo, conn, db = store
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), _stage(tmp_path, _JUL)])

    import_manifest(manifest, conn, db)

    assert _history(repo, "4700") == [
        (1, _JAN, "BAG AL 2026-01-01", Decimal("21.6")),
        (2, _JUL, "BAG AL 2026-07-01", Decimal("16.6")),
    ]
    assert _history(repo, "1368") == [
        (1, _JAN, "BAG AL 2026-01-01", Decimal("59.4")),
        (2, _JUL, "BAG AL 2026-07-01", Decimal("64.4")),
    ]
    assert _history(repo, "1779") == [(1, _JUL, "BAG AL 2026-07-01", Decimal("73.3"))]


def test_reversed_manifest_order_still_imports_oldest_edition_first(tmp_path, store):
    repo, conn, db = store
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JUL), _stage(tmp_path, _JAN)])

    report = import_manifest(manifest, conn, db)

    assert [o.effective_date for o in report.editions] == [_JAN, _JUL]
    assert _history(repo, "4700") == [
        (1, _JAN, "BAG AL 2026-01-01", Decimal("21.6")),
        (2, _JUL, "BAG AL 2026-07-01", Decimal("16.6")),
    ]


def _snapshot(repo: TariffRepository) -> list[tuple]:
    return [(r.tariff_code, r.version, r.record_hash) for r in repo.list_all()]


def _audit_count(conn) -> int:
    """Read-only audit_log count: there is no audit read API (agreed for refusal tests)."""
    return conn.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"]


def test_hash_mismatch_in_a_later_edition_refuses_the_whole_batch(tmp_path, store):
    repo, conn, db = store
    july = _stage(tmp_path, _JUL)
    july["documents"][0]["sha256"] = "0" * 64
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), july])
    audit_before = _audit_count(conn)

    with pytest.raises(ManifestError, match="sha256 mismatch"):
        import_manifest(manifest, conn, db)

    assert repo.list_all() == []
    assert _audit_count(conn) == audit_before


def _doc(body: dict, edition: int = 0, document: int = 0) -> dict:
    return body["editions"][edition]["documents"][document]


_PDF = {"kind": "commentary_pdf", "path": "data/raw/bag/al/k.pdf", "sha256": "a" * 64}
_OTHER_XLSX = {"kind": "full_list_xlsx", "path": "data/raw/bag/al/x.xlsx", "sha256": "b" * 64}


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        pytest.param(lambda m: _doc(m).update(kind="price_csv"), "kind", id="unknown-kind"),
        pytest.param(lambda m: m.update(comment="x"), "comment", id="unknown-field"),
        pytest.param(lambda m: m.update(manifest_version=2), "manifest_version", id="version"),
        pytest.param(lambda m: m.update(tariff_system="SL"), "tariff_system", id="system"),
        pytest.param(lambda m: _doc(m).update(sha256="abc"), "sha256", id="bad-sha256"),
        pytest.param(lambda m: _doc(m).__delitem__("sha256"), "sha256", id="missing-sha256"),
        pytest.param(
            lambda m: m["editions"][0].update(effective_date="2026-13-01"),
            "effective_date",
            id="bad-date",
        ),
        pytest.param(
            lambda m: m["editions"][0].update(effective_date=20260101),
            "effective_date",
            id="numeric-date",
        ),
        pytest.param(lambda m: _doc(m).update(path="../outside.xlsx"), "path", id="escaping-path"),
        pytest.param(lambda m: _doc(m).update(path="/etc/hosts"), "path", id="absolute-path"),
        pytest.param(
            lambda m: _doc(m).update(path="data/raw/bag/al/absent.xlsx"),
            "file not found",
            id="missing-file",
        ),
        pytest.param(
            lambda m: m["editions"][1].update(effective_date="2026-01-01"),
            "more than once",
            id="duplicate-edition",
        ),
        pytest.param(
            lambda m: m["editions"][1]["documents"].__setitem__(0, dict(_doc(m))),
            "more than once",
            id="same-file-twice",
        ),
        pytest.param(
            lambda m: m["editions"][0]["documents"].append(dict(_OTHER_XLSX)),
            "exactly one full_list_xlsx",
            id="two-tariff-lists",
        ),
        pytest.param(
            lambda m: m["editions"][0].update(documents=[dict(_PDF)]),
            "exactly one full_list_xlsx",
            id="no-tariff-list",
        ),
        pytest.param(
            lambda m: _doc(m).update(source_url="http://example.com/al.xlsx"),
            "source_url",
            id="non-bag-url",
        ),
        pytest.param(
            lambda m: m.update(supporting_documents=[dict(_OTHER_XLSX)]),
            "supporting_documents",
            id="tariff-list-as-supporting-document",
        ),
        pytest.param(lambda m: "{not json", "Invalid JSON", id="not-json"),
        pytest.param(lambda m: json.dumps(m) + " " * 1_100_000, "larger than", id="oversized"),
        pytest.param(lambda m: m.update(editions=[]), "editions", id="no-editions"),
        pytest.param(
            lambda m: json.dumps(m)[:-1] + ', "manifest_version": 1}',
            "duplicate key",
            id="duplicate-key",
        ),
        pytest.param(lambda m: m.update(manifest_version=True), "manifest_version", id="bool"),
        pytest.param(lambda m: m.update(manifest_version=1.0), "manifest_version", id="float"),
        pytest.param(
            lambda m: m["editions"][0].update(effective_date="1767225600"),
            "effective_date",
            id="timestamp-date",
        ),
        pytest.param(
            lambda m: _doc(m).update(path=unicodedata.normalize("NFD", "data/raw/Ä.xlsx")),
            "NFC",
            id="nfd-path",
        ),
        pytest.param(lambda m: _doc(m).update(path="data/raw/a\x00.xlsx"), "path", id="nul-path"),
        pytest.param(
            lambda m: m["editions"][0]["documents"].append(
                {**_PDF, "path": _doc(m)["path"].upper()}
            ),
            "more than once",
            id="case-duplicate-path",
        ),
        pytest.param(
            lambda m: _doc(m, 1).update(sha256=_doc(m)["sha256"]),
            "document sha256",
            id="same-bytes-other-path",
        ),
        pytest.param(
            lambda m: _doc(m).update(source_url="https://u:p@www.bag.admin.ch/al.xlsx"),
            "source_url",
            id="url-credentials",
        ),
        pytest.param(
            lambda m: _doc(m).update(source_url="https://www.bag.admin.ch/al.xlsx?token=x"),
            "source_url",
            id="url-query",
        ),
        pytest.param(
            lambda m: _doc(m).update(source_url="https://evil.example\\@bag.admin.ch/al.xlsx"),
            "source_url",
            id="url-backslash",
        ),
        pytest.param(
            lambda m: _doc(m).update(source_url="https://www.bag.admin.ch/‮gpj.xlsx"),
            "source_url",
            id="url-bidi-override",
        ),
    ],
)
def test_invalid_manifest_is_refused_before_any_write(tmp_path, store, mutate, message):
    repo, conn, db = store
    body = {
        "manifest_version": 1,
        "tariff_system": "EAL",
        "editions": [_stage(tmp_path, _JAN), _stage(tmp_path, _JUL)],
    }
    replaced = mutate(body)
    manifest = _write_text(tmp_path, replaced if isinstance(replaced, str) else json.dumps(body))
    audit_before = _audit_count(conn)

    with pytest.raises(ManifestError, match=message) as refused:
        import_manifest(manifest, conn, db)

    assert "at least 1 item" not in str(refused.value)  # no spurious follow-on problem
    assert repo.list_all() == []
    assert _audit_count(conn) == audit_before


def test_unreadable_listed_file_is_listed_as_a_problem_not_a_crash(tmp_path, store):
    repo, conn, db = store
    january = _stage(tmp_path, _JAN)
    target = tmp_path / january["documents"][0]["path"]
    target.chmod(0)
    try:
        with pytest.raises(ManifestError, match="PermissionError"):
            import_manifest(_write_manifest(tmp_path, [january]), conn, db)
    finally:
        target.chmod(0o644)

    assert repo.list_all() == []


def test_refusal_messages_stay_short_for_huge_unknown_keys(tmp_path, store):
    repo, conn, db = store
    body = {"manifest_version": 1, "tariff_system": "EAL", "editions": [_stage(tmp_path, _JAN)]}
    manifest = _write_text(tmp_path, json.dumps({**body, "k" * 50_000: 1}))

    with pytest.raises(ManifestError) as refused:
        import_manifest(manifest, conn, db)

    assert len(str(refused.value)) < 1_000


def test_unreadable_manifest_is_refused_not_a_crash(tmp_path, store):
    repo, conn, db = store
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN)])
    manifest.chmod(0)
    try:
        with pytest.raises(ManifestError, match="PermissionError"):
            import_manifest(manifest, conn, db)
    finally:
        manifest.chmod(0o644)

    assert repo.list_all() == []


def test_manifest_outside_data_manifests_is_refused(tmp_path, store):
    repo, conn, db = store
    manifest = tmp_path / "bag-al.json"
    manifest.write_text(
        json.dumps({"manifest_version": 1, "tariff_system": "EAL", "editions": []}),
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="data/manifests"):
        import_manifest(manifest, conn, db)


def test_symlink_escaping_the_repository_root_is_refused(tmp_path, store):
    repo, conn, db = store
    root = tmp_path / "repo"
    outside = _stage(tmp_path / "elsewhere", _JAN)
    target = tmp_path / "elsewhere" / outside["documents"][0]["path"]
    link = root / "data" / "raw" / "bag" / "al" / "link.xlsx"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)
    outside["documents"][0]["path"] = "data/raw/bag/al/link.xlsx"
    manifest = _write_manifest(root, [outside])

    with pytest.raises(ManifestError, match="outside the repository"):
        import_manifest(manifest, conn, db)

    assert repo.list_all() == []


@pytest.mark.parametrize("breakage", ["symlink loop", "unsearchable folder"])
@pytest.mark.parametrize("where", ["manifest", "document"])
def test_unusable_paths_are_refused_not_a_crash(tmp_path, store, where, breakage):
    repo, conn, db = store
    january = _stage(tmp_path, _JAN)
    manifest = _write_manifest(tmp_path, [january])
    target = manifest if where == "manifest" else tmp_path / january["documents"][0]["path"]
    if breakage == "symlink loop":
        target.unlink()
        target.symlink_to(target.name)  # the entry points at itself
    elif os.geteuid() == 0:
        pytest.skip("root ignores folder permissions")
    else:
        target.parent.chmod(0o644)  # listable, but its entries cannot be reached
    try:
        with pytest.raises(ManifestError):
            import_manifest(manifest, conn, db)
    finally:
        target.parent.chmod(0o755)

    assert (repo.list_all(), _audit_count(conn)) == ([], 0)


def test_sources_stored_under_nfd_names_are_found_through_their_nfc_paths(tmp_path, store):
    repo, conn, db = store
    nfd = unicodedata.normalize("NFD", "Analysenliste Übersicht 2026.xlsx")  # as macOS saves it
    january = _stage(tmp_path, _JAN, name=nfd)
    commentary = unicodedata.normalize("NFD", "Kommentar zu den Änderungen.pdf")
    january["documents"].append(_stage_pdf(tmp_path, commentary, "commentary_pdf"))
    for document in january["documents"]:  # a manifest spells every path in NFC
        document["path"] = unicodedata.normalize("NFC", document["path"])

    import_manifest(_write_manifest(tmp_path, [january]), conn, db)

    assert _history(repo, "4700") == [(1, _JAN, "BAG AL 2026-01-01", Decimal("21.6"))]


def test_two_files_whose_names_differ_only_in_normalisation_are_refused(tmp_path, store):
    repo, conn, db = store
    january = _stage(tmp_path, _JAN)
    name = unicodedata.normalize("NFC", "Kommentar zu den Änderungen.pdf")
    commentary = _stage_pdf(tmp_path, name, "commentary_pdf")
    _stage_pdf(tmp_path, unicodedata.normalize("NFD", name), "commentary_pdf")  # its twin
    folder = (tmp_path / commentary["path"]).parent
    if sum(unicodedata.normalize("NFC", entry.name) == name for entry in folder.iterdir()) < 2:
        pytest.skip("this file system folds Unicode normalisation (macOS); the case needs Linux")
    january["documents"].append(commentary)

    with pytest.raises(ManifestError, match="differ only in Unicode normalisation"):
        import_manifest(_write_manifest(tmp_path, [january]), conn, db)

    assert (repo.list_all(), _audit_count(conn)) == ([], 0)


def test_filename_date_conflicting_with_the_manifest_is_refused(tmp_path, store):
    repo, conn, db = store
    july = _stage(tmp_path, _JUL, name="analysenliste_2026-01-01.xlsx")
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), july])
    audit_before = _audit_count(conn)

    with pytest.raises(ManifestError, match="conflicts with the explicit edition 2026-07-01"):
        import_manifest(manifest, conn, db)

    assert repo.list_all() == []
    assert _audit_count(conn) == audit_before


def test_edition_without_tariff_positions_is_refused(tmp_path, store):
    from openpyxl import Workbook

    repo, conn, db = store
    empty = tmp_path / "data" / "raw" / "bag" / "al" / "2026-01-01" / "Analysenliste leer.xlsx"
    empty.parent.mkdir(parents=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Deutsch"
    sheet.append(["Fachbereiche"])
    sheet.append(["Kapitel", "Pos.-Nr.", "TP", "Bezeichnung", "Chemie"])  # header, no rows
    workbook.save(empty)
    document = {
        "kind": "full_list_xlsx",
        "path": empty.relative_to(tmp_path).as_posix(),
        "sha256": _sha256(empty),
    }
    edition = {"effective_date": "2026-01-01", "documents": [document]}

    with pytest.raises(ManifestError, match="no tariff positions"):
        import_manifest(_write_manifest(tmp_path, [edition]), conn, db)

    assert repo.list_all() == []


class _OnFirstEmbed(HashingEmbedder):
    """The offline stub at the pgvector width (1024), running ``action`` on its first call.

    The pipeline embeds each record just before storing it, so ``action`` runs inside the
    import, after planning and before the first write.
    """

    def __init__(self, action) -> None:
        super().__init__(dimension=E5_DIMENSION)
        self._action = action

    def embed(self, text: str) -> list[float]:
        if self._action is not None:
            action, self._action = self._action, None
            action()
        return super().embed(text)


def test_file_swapped_during_the_import_cannot_change_what_is_frozen(tmp_path, store):
    repo, conn, db = store
    july = _stage(tmp_path, _JUL)
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), july])
    target = tmp_path / july["documents"][0]["path"]
    swap = _OnFirstEmbed(lambda: shutil.copyfile(_EDITION_FIXTURES[_JAN], target))

    import_manifest(manifest, conn, db, embedder=swap)

    assert _history(repo, "4700")[-1] == (2, _JUL, "BAG AL 2026-07-01", Decimal("16.6"))


def test_competing_import_during_the_run_is_reported(tmp_path, store):
    repo, conn, db = store
    other = tmp_path / "other"
    july_manifest = _write_manifest(other, [_stage(other, _JUL)])
    competitor = db.connect()

    def compete():  # another importer commits July after this run planned January
        import_manifest(july_manifest, competitor, db)

    january = _write_manifest(tmp_path, [_stage(tmp_path, _JAN)])
    try:
        with pytest.raises(ManifestError, match="changed during the import"):
            import_manifest(january, conn, db, embedder=_OnFirstEmbed(compete))
    finally:
        competitor.close()
    assert _history(repo, "4700") == [(1, _JUL, "BAG AL 2026-07-01", Decimal("16.6"))]


def test_competing_same_dated_position_during_the_run_is_reported(tmp_path, store):
    repo, conn, db = store
    competitor = db.connect()

    def compete():  # another writer adds a 2026-01-01 position the manifest's file lacks
        seed = {
            "tariff_code": "9999",
            "designation_de": "Nicht in dieser Ausgabe",
            "tax_points": "1.0",
            "valid_from": _JAN,
            "source_version": "BAG AL 2026-01-01",
        }
        rival = TariffRepository(competitor, db)
        rival.add(freeze(map_raw(seed, system=TariffSystem.EAL, source_url=_EAL_URL)))

    january = _write_manifest(tmp_path, [_stage(tmp_path, _JAN)])
    try:
        with pytest.raises(ManifestError, match="changed during the import.*does not list"):
            import_manifest(january, conn, db, embedder=_OnFirstEmbed(compete))
    finally:
        competitor.close()
    assert [code for code, _, _ in _snapshot(repo)] == ["9999"]


def _stage_pdf(root: Path, name: str, kind: str) -> dict:
    """Write a small stand-in PDF under ``root`` and return its manifest document entry."""
    target = root / "data" / "raw" / "bag" / "al" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"%PDF-1.4\n% stand-in for " + name.encode() + b"\n")
    return {"kind": kind, "path": target.relative_to(root).as_posix(), "sha256": _sha256(target)}


@pytest.mark.parametrize(
    ("breakage", "message"),
    [
        pytest.param(lambda doc, root: doc.update(sha256="0" * 64), "sha256 mismatch", id="hash"),
        pytest.param(lambda doc, root: (root / doc["path"]).unlink(), "not found", id="missing"),
    ],
)
@pytest.mark.parametrize(
    ("placement", "kind"),
    [("edition", "commentary_pdf"), ("supporting", "handbook_pdf")],
)
def test_every_listed_document_is_verified_before_any_write(
    tmp_path, store, breakage, message, placement, kind
):
    repo, conn, db = store
    january = _stage(tmp_path, _JAN)
    pdf = _stage_pdf(tmp_path, f"{kind}.pdf", kind)
    breakage(pdf, tmp_path)
    if placement == "edition":
        january["documents"].append(pdf)
        manifest = _write_manifest(tmp_path, [january])
    else:
        manifest = _write_manifest(tmp_path, [january], supporting_documents=[pdf])
    audit_before = _audit_count(conn)

    with pytest.raises(ManifestError, match=message):
        import_manifest(manifest, conn, db)

    assert repo.list_all() == []
    assert _audit_count(conn) == audit_before


@pytest.mark.parametrize(
    "content", [b"not a workbook", b"%PDF-1.4\n% a PDF listed as the tariff list\n"]
)
def test_unreadable_workbook_is_listed_as_a_problem_not_a_crash(tmp_path, store, content):
    repo, conn, db = store
    january = _stage(tmp_path, _JAN)
    target = tmp_path / january["documents"][0]["path"]
    target.write_bytes(content)
    january["documents"][0]["sha256"] = _sha256(target)

    with pytest.raises(ManifestError, match="BadZipFile"):
        import_manifest(_write_manifest(tmp_path, [january]), conn, db)

    assert repo.list_all() == []


def test_same_edition_under_another_name_and_folder_is_already_present(tmp_path, store):
    repo, conn, db = store
    first = tmp_path / "a"
    import_manifest(_write_manifest(first, [_stage(first, _JAN)]), conn, db)
    before = _snapshot(repo)

    other = tmp_path / "b"
    renamed = _stage(other, _JAN, name="analysenliste_2026-01-01.xlsx")
    report = import_manifest(_write_manifest(other, [renamed]), conn, db)

    assert [o.action for o in report.editions] == ["already_present"]
    assert _snapshot(repo) == before


def test_older_edition_after_a_newer_one_is_refused_before_any_write(tmp_path, store):
    repo, conn, db = store
    july = _stage(tmp_path, _JUL)
    import_manifest(_write_manifest(tmp_path, [july]), conn, db)
    before, audit_before = _snapshot(repo), _audit_count(conn)

    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), july])
    with pytest.raises(ManifestError, match="newer EAL edition 2026-07-01"):
        import_manifest(manifest, conn, db)

    assert _snapshot(repo) == before
    assert _audit_count(conn) == audit_before


def _legacy_import(conn, db: Database, path: Path) -> None:
    """Freeze a workbook through the pre-manifest path: no explicit edition."""
    spec = SourceSpec(system=TariffSystem.EAL, kind="bag_eal", path=path, source_url=_EAL_URL)
    run_pipeline([spec], TariffRepository(conn, db), AuditLogger(conn, db))


def test_undated_legacy_rows_for_the_batch_are_refused(tmp_path, store):
    repo, conn, db = store
    january = _stage(tmp_path, _JAN)
    _legacy_import(conn, db, tmp_path / january["documents"][0]["path"])  # BAG name: undated
    before, audit_before = _snapshot(repo), _audit_count(conn)

    with pytest.raises(ManifestError, match="no valid_from"):
        import_manifest(_write_manifest(tmp_path, [january, _stage(tmp_path, _JUL)]), conn, db)

    assert _snapshot(repo) == before
    assert _audit_count(conn) == audit_before


def test_same_edition_with_different_stored_content_is_refused(tmp_path, store):
    repo, conn, db = store
    seed = {
        "tariff_code": "4700",
        "designation_de": "Auftragstaxe",
        "tax_points": "99.9",
        "valid_from": _JAN,
        "source_version": "BAG AL 2026-01-01",
    }
    repo.add(freeze(map_raw(seed, system=TariffSystem.EAL, source_url=_EAL_URL)))
    before, audit_before = _snapshot(repo), _audit_count(conn)

    with pytest.raises(ManifestError, match=r"different content \(e\.g\. 4700\)"):
        import_manifest(_write_manifest(tmp_path, [_stage(tmp_path, _JAN)]), conn, db)

    assert _snapshot(repo) == before
    assert _audit_count(conn) == audit_before


def test_stored_versions_out_of_date_order_are_refused(tmp_path, store):
    repo, conn, db = store
    july = _stage(tmp_path / "legacy", _JUL, name="analysenliste_2026-07-01.xlsx")
    january = _stage(tmp_path / "legacy", _JAN, name="analysenliste_2026-01-01.xlsx")
    for edition in (july, january):  # convention names imported newest first
        _legacy_import(conn, db, tmp_path / "legacy" / edition["documents"][0]["path"])
    before, audit_before = _snapshot(repo), _audit_count(conn)

    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), _stage(tmp_path, _JUL)])
    with pytest.raises(ManifestError, match="not in effective-date order"):
        import_manifest(manifest, conn, db)

    assert _snapshot(repo) == before
    assert _audit_count(conn) == audit_before


def test_cli_manifest_imports_editions_and_prints_the_report(tmp_path, monkeypatch, capsys):
    from tarifhub_ingest.cli import main as cli_main

    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JUL), _stage(tmp_path, _JAN)])
    monkeypatch.setenv("TARIFHUB_DB_URL", f"sqlite:///{tmp_path / 'cli.db'}")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    rc = cli_main(["--manifest", str(manifest)])

    assert rc == 0
    editions = json.loads(capsys.readouterr().out)["editions"]
    assert [(e["effective_date"], e["action"], e["frozen"]) for e in editions] == [
        ("2026-01-01", "imported", 3),
        ("2026-07-01", "imported", 4),
    ]


def test_cli_manifest_refusal_exits_2_and_writes_nothing(tmp_path, monkeypatch, capsys):
    from tarifhub_ingest.cli import main as cli_main

    july = _stage(tmp_path, _JUL)
    july["documents"][0]["sha256"] = "0" * 64
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), july])
    db_url = f"sqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setenv("TARIFHUB_DB_URL", db_url)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    rc = cli_main(["--manifest", str(manifest)])

    assert rc == 2
    assert "sha256 mismatch" in " ".join(json.loads(capsys.readouterr().err)["problems"])
    db = Database.from_url(db_url)
    conn = db.connect()
    try:
        assert TariffRepository(conn, db).list_all() == []
        assert _audit_count(conn) == 0
    finally:
        conn.close()


def test_cli_manifest_failure_mid_import_rolls_the_whole_batch_back(tmp_path, monkeypatch):
    from tarifhub_ingest.cli import main as cli_main

    db_url = f"sqlite:///{tmp_path / 'cli.db'}"
    db = Database.from_url(db_url)
    conn = db.connect()
    db.init_schema(conn)
    conn.execute(  # a write failure on the last July row, after January and 3 July rows
        "CREATE TRIGGER fail_july BEFORE INSERT ON tariff "
        "WHEN NEW.tariff_code = '4700' AND NEW.valid_from = '2026-07-01' "
        "BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END"
    )
    conn.commit()
    conn.close()
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), _stage(tmp_path, _JUL)])
    monkeypatch.setenv("TARIFHUB_DB_URL", db_url)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(sqlite3.IntegrityError, match="simulated write failure"):
        cli_main(["--manifest", str(manifest)])

    conn = db.connect()
    try:
        assert TariffRepository(conn, db).list_all() == []
        assert _audit_count(conn) == 0
    finally:
        conn.close()


def test_cli_manifest_cannot_be_combined_with_path(tmp_path):
    from tarifhub_ingest.cli import main as cli_main

    with pytest.raises(SystemExit) as exit_info:
        cli_main(["--manifest", str(tmp_path / "m.json"), "--path", str(tmp_path / "x.xlsx")])
    assert exit_info.value.code == 2


def test_reviewed_correction_does_not_block_reimport_or_the_next_edition(
    tmp_path, store, monkeypatch
):
    repo, conn, db = store
    monkeypatch.setenv("TARIFHUB_REVIEW_THRESHOLD", "1.01")  # flag every record for review
    if db.dialect == "postgresql":  # vector(1024) rejects the 16-dim stub (as test_review_api)
        monkeypatch.setattr("tarifhub_ingest.review_service.get_embedder", lambda *a, **k: None)
    settings = get_settings()
    january = _stage(tmp_path, _JAN)
    import_manifest(_write_manifest(tmp_path, [january]), conn, db, settings=settings)
    decision = ReviewDecision(
        tariff_system=TariffSystem.EAL,
        tariff_code="4700",
        action="correct",
        corrections={"designation.de": "Auftragstaxe (korrigiert)"},
    )
    apply_review_decision(decision, repo=repo, audit=AuditLogger(conn, db), settings=settings)
    corrected = _snapshot(repo)

    again = import_manifest(_write_manifest(tmp_path, [january]), conn, db, settings=settings)
    assert [o.action for o in again.editions] == ["already_present"]
    assert _snapshot(repo) == corrected

    both = [january, _stage(tmp_path, _JUL)]
    report = import_manifest(_write_manifest(tmp_path, both), conn, db, settings=settings)
    assert [o.action for o in report.editions] == ["already_present", "imported"]
    assert _history(repo, "4700") == [
        (1, _JAN, "BAG AL 2026-01-01", Decimal("21.6")),
        (2, _JAN, "BAG AL 2026-01-01", Decimal("21.6")),  # the correction, kept
        (3, _JUL, "BAG AL 2026-07-01", Decimal("16.6")),
    ]


@pytest.mark.parametrize("selected", [(_JAN,), (_JUL,)], ids=["same-edition", "next-edition"])
def test_same_dated_successor_that_changes_a_billing_value_is_refused(tmp_path, store, selected):
    repo, conn, db = store
    import_manifest(_write_manifest(tmp_path, [_stage(tmp_path, _JAN)]), conn, db)
    stored = next(r for r in repo.list_all() if r.tariff_code == "4700")
    altered = stored.model_copy(update={"tax_points": Decimal("99.9"), "record_hash": None})
    repo.add(freeze(altered))
    before, audit_before = _snapshot(repo), _audit_count(conn)
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, e) for e in selected])

    with pytest.raises(ManifestError, match=r"changes a billing or edition field \(e\.g\. 4700\)"):
        import_manifest(manifest, conn, db)

    assert _snapshot(repo) == before
    assert _audit_count(conn) == audit_before


def test_stored_positions_missing_from_the_edition_file_are_refused(tmp_path, store):
    repo, conn, db = store
    seed = {
        "tariff_code": "9999",
        "designation_de": "Nicht in dieser Ausgabe",
        "tax_points": "1.0",
        "valid_from": _JAN,
        "source_version": "BAG AL 2026-01-01",
    }
    repo.add(freeze(map_raw(seed, system=TariffSystem.EAL, source_url=_EAL_URL)))
    before, audit_before = _snapshot(repo), _audit_count(conn)

    with pytest.raises(ManifestError, match=r"does not list \(e\.g\. 9999\)"):
        import_manifest(_write_manifest(tmp_path, [_stage(tmp_path, _JAN)]), conn, db)

    assert _snapshot(repo) == before
    assert _audit_count(conn) == audit_before


def test_interrupted_import_resumes_with_only_the_missing_positions(tmp_path, store):
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
    run_pipeline([partial], repo, AuditLogger(conn, db))  # as if the import stopped after one position
    stored_1000 = _history(repo, "1000")

    report = import_manifest(_write_manifest(tmp_path, [january]), conn, db)

    assert [(o.action, o.already_stored, o.report.frozen) for o in report.editions] == [
        ("imported", 1, 2)
    ]
    assert _history(repo, "1000") == stored_1000
    assert {code for code, _, _ in _snapshot(repo)} == {"1000", "1368", "4700"}


def test_reimporting_the_same_editions_adds_no_versions(tmp_path, store):
    repo, conn, db = store
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), _stage(tmp_path, _JUL)])
    import_manifest(manifest, conn, db)
    before, audit_before = _snapshot(repo), _audit_count(conn)

    report = import_manifest(manifest, conn, db)

    assert [(o.effective_date, o.action) for o in report.editions] == [
        (_JAN, "already_present"),
        (_JUL, "already_present"),
    ]
    assert (_snapshot(repo), _audit_count(conn)) == (before, audit_before)


def _seed_existing(repo: TariffRepository) -> list:
    """Records stored before the import: an older edition of 4700 and an SL position."""
    older = {
        "tariff_code": "4700",
        "designation_de": "Auftragstaxe",
        "tax_points": "24.0",
        "valid_from": date(2025, 7, 1),
        "source_version": "BAG AL 2025-07-01",
    }
    sl = {"tariff_code": "7680000000017", "designation_de": "Testpräparat", "price_chf": "12.30"}
    repo.add(freeze(map_raw(older, system=TariffSystem.EAL, source_url=_EAL_URL)))
    repo.add(freeze(map_raw(sl, system=TariffSystem.SL, source_url="https://epl.bag.admin.ch")))
    return repo.list_all()


def _committed(db: Database) -> tuple[list, int]:
    """What a fresh connection sees: the committed records and the audit-row count."""
    conn = db.connect()
    try:
        return TariffRepository(conn, db).list_all(), _audit_count(conn)
    finally:
        conn.close()


def _reject_july_4700(conn, db: Database) -> None:
    """Make the database refuse the last July row, after January and three July rows."""
    if db.dialect == "sqlite":
        conn.execute(
            "CREATE TRIGGER fail_july BEFORE INSERT ON tariff "
            "WHEN NEW.tariff_code = '4700' AND NEW.valid_from = '2026-07-01' "
            "BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END"
        )
    else:
        conn.execute(
            "CREATE FUNCTION fail_july() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
            "IF NEW.tariff_code = '4700' AND NEW.valid_from = DATE '2026-07-01' THEN "
            "RAISE EXCEPTION 'simulated write failure'; END IF; RETURN NEW; END $$"
        )
        conn.execute(
            "CREATE TRIGGER fail_july BEFORE INSERT ON tariff "
            "FOR EACH ROW EXECUTE FUNCTION fail_july()"
        )
    conn.commit()


def test_failure_mid_import_rolls_back_a_direct_call_and_keeps_existing_records(
    tmp_path, store
):
    repo, conn, db = store
    existing = _seed_existing(repo)
    _reject_july_4700(conn, db)
    audit_before = _audit_count(conn)
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), _stage(tmp_path, _JUL)])

    with pytest.raises((sqlite3.Error, psycopg.Error), match="simulated write failure"):
        import_manifest(manifest, conn, db)

    assert (repo.list_all(), _audit_count(conn)) == (existing, audit_before)  # rolled back
    assert _committed(db) == (existing, audit_before)  # and nothing reached other readers


def test_import_appends_editions_and_keeps_existing_records_unchanged(tmp_path, store):
    repo, conn, db = store
    existing = _seed_existing(repo)
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), _stage(tmp_path, _JUL)])

    import_manifest(manifest, conn, db)

    committed, _ = _committed(db)  # what other readers see once the import returned
    assert [record for record in committed if record in existing] == existing
    assert [
        (r.version, r.valid_from, r.source_version, r.tax_points)
        for r in committed
        if r.tariff_code == "4700"
    ] == [
        (1, date(2025, 7, 1), "BAG AL 2025-07-01", Decimal("24.0")),
        (2, _JAN, "BAG AL 2026-01-01", Decimal("21.6")),
        (3, _JUL, "BAG AL 2026-07-01", Decimal("16.6")),
    ]


def test_failed_commit_leaves_nothing_of_the_batch_pending(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    db = Database.from_url(f"sqlite:///{tmp_path / 'locked.db'}")
    conn, reader = db.connect(), db.connect()
    try:
        db.init_schema(conn)
        conn.execute("PRAGMA busy_timeout = 0")  # fail at once instead of waiting
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM tariff").fetchone()  # its lock blocks a COMMIT
        manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN)])

        with pytest.raises(sqlite3.OperationalError, match="locked"):
            import_manifest(manifest, conn, db)
        reader.rollback()

        assert TariffRepository(conn, db).list_all() == []  # nothing a later commit could keep
    finally:
        conn.close()
        reader.close()


def test_failed_rollback_still_leaves_nothing_a_later_commit_could_store(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    db = Database.from_url(f"sqlite:///{tmp_path / 'stuck.db'}")
    conn = db.connect()
    db.init_schema(conn)
    _reject_july_4700(conn, db)
    deny_rollback = sqlite3.SQLITE_DENY
    conn.set_authorizer(
        lambda action, arg, *_: (
            deny_rollback
            if action == sqlite3.SQLITE_TRANSACTION and arg == "ROLLBACK"
            else sqlite3.SQLITE_OK
        )
    )
    manifest = _write_manifest(tmp_path, [_stage(tmp_path, _JAN), _stage(tmp_path, _JUL)])
    try:
        with pytest.raises(sqlite3.IntegrityError, match="simulated write failure"):
            import_manifest(manifest, conn, db)  # the original failure, not the rollback's
        with contextlib.suppress(sqlite3.ProgrammingError):  # the import closed it
            conn.commit()  # a caller that keeps using the connection
    finally:
        conn.close()

    assert _committed(db) == ([], 0)
