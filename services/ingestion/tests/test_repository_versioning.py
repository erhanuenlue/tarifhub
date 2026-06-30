"""Versioning tests for the frozen-record repository.

Re-ingesting *changed* content for an existing ``(tariff_system, tariff_code)`` must
create a new version (n+1), not collide on the ``UNIQUE (tariff_system, tariff_code,
version)`` constraint. Identical content stays idempotent on ``record_hash``. The
version bump is supersession metadata only and must never alter ``record_hash``.

All offline: in-memory SQLite mirror, no network, no embedder.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest

from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem
from tarifhub_ingest.storage.db import Database
from tarifhub_ingest.storage.tariff_repository import TariffRepository
from tarifhub_ingest.versioning.freeze_record import compute_record_hash, freeze


@pytest.fixture
def repo() -> Iterator[TariffRepository]:
    db = Database.from_url("sqlite://")  # in-memory
    conn = db.connect()
    db.init_schema(conn)
    yield TariffRepository(conn, db)
    conn.close()


def _record(**overrides) -> TariffRecord:
    data = dict(
        tariff_code="0010.00",
        tariff_system=TariffSystem.EAL,
        designation=Designation(de="Hämatokrit"),
        category="Hämatologie",
        tax_points=Decimal("8.50"),
        unit="point",
        valid_from=date(2026, 1, 1),
    )
    data.update(overrides)
    return TariffRecord(**data)


def test_add_rejects_unfrozen_record(repo: TariffRepository):
    with pytest.raises(ValueError):
        repo.add(_record())  # record_hash is None


def test_identical_hash_is_idempotent(repo: TariffRepository):
    """Pinned-hash regression: freezing the same content twice stores exactly one row."""

    frozen = freeze(_record())
    assert repo.add(frozen) is True
    assert repo.add(freeze(_record())) is False
    rows = repo._conn.execute("SELECT version FROM tariff").fetchall()
    assert len(rows) == 1
    assert rows[0]["version"] == 1


def test_changed_content_creates_new_version(repo: TariffRepository):
    """Changed content for an existing (system, code) -> version 2, both rows present."""

    first = freeze(_record(designation=Designation(de="Hämatokrit", fr="Hématocrite")))
    second = freeze(_record(designation=Designation(de="Hämatokrit", fr="Hématocrite v2")))

    assert repo.add(first) is True
    assert repo.add(second) is True  # different hash -> new version, not a collision

    rows = repo._conn.execute(
        "SELECT version, record_hash FROM tariff ORDER BY version"
    ).fetchall()
    assert [r["version"] for r in rows] == [1, 2]
    # get() returns the highest version for the code.
    latest = repo.get("0010.00", TariffSystem.EAL)
    assert latest is not None
    assert latest.version == 2
    assert latest.designation.fr == "Hématocrite v2"


def test_version_bump_does_not_change_record_hash(repo: TariffRepository):
    """The stored hash of the bumped record equals the hash stamped at freeze time."""

    repo.add(freeze(_record(designation=Designation(de="Hämatokrit", fr="A"))))
    second = freeze(_record(designation=Designation(de="Hämatokrit", fr="B")))
    repo.add(second)

    stored = repo.get("0010.00", TariffSystem.EAL)
    assert stored is not None
    assert stored.version == 2
    # version is excluded from HASHED_FIELDS -> bumping it cannot change the hash.
    assert stored.record_hash == second.record_hash
    assert compute_record_hash(stored) == second.record_hash


def test_third_distinct_content_becomes_version_three(repo: TariffRepository):
    repo.add(freeze(_record(designation=Designation(de="Hämatokrit", fr="A"))))
    repo.add(freeze(_record(designation=Designation(de="Hämatokrit", fr="B"))))
    repo.add(freeze(_record(designation=Designation(de="Hämatokrit", fr="C"))))

    versions = [
        r["version"]
        for r in repo._conn.execute("SELECT version FROM tariff ORDER BY version").fetchall()
    ]
    assert versions == [1, 2, 3]
    assert repo.get("0010.00", TariffSystem.EAL).version == 3


def test_incoming_version_is_ignored(repo: TariffRepository):
    """Even if the record carries version=99, an empty (system, code) starts at 1."""

    frozen = freeze(_record(version=99))
    assert repo.add(frozen) is True
    stored = repo.get("0010.00", TariffSystem.EAL)
    assert stored is not None
    assert stored.version == 1


def test_distinct_codes_each_start_at_version_one(repo: TariffRepository):
    """Versioning is scoped per (system, code), not global."""

    repo.add(freeze(_record(tariff_code="0010.00")))
    repo.add(freeze(_record(tariff_code="0020.00")))
    assert repo.get("0010.00", TariffSystem.EAL).version == 1
    assert repo.get("0020.00", TariffSystem.EAL).version == 1


def test_pipeline_over_eal_sample_is_idempotent(tmp_path, monkeypatch):
    """Pipeline-level sanity: a second offline run over the sample skips everything."""

    from tarifhub_ingest.audit.audit_logger import AuditLogger
    from tarifhub_ingest.config import get_settings
    from tarifhub_ingest.ingestion.pipeline import run_pipeline
    from tarifhub_ingest.ingestion.source_loader import discover_samples

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    db = Database.from_url(f"sqlite:///{tmp_path / 'pipeline.db'}")
    conn = db.connect()
    db.init_schema(conn)
    repo = TariffRepository(conn, db)
    audit = AuditLogger(conn, db)
    specs = [s for s in discover_samples() if s.system is TariffSystem.EAL]
    assert specs, "expected the bundled EAL sample to exist"
    settings = get_settings()

    first = run_pipeline(specs, repo, audit, settings=settings)
    second = run_pipeline(specs, repo, audit, settings=settings)

    assert first.frozen > 0
    assert second.frozen == 0
    assert second.skipped_existing == first.frozen

    conn.close()
