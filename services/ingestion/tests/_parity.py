"""Shared cross-engine parity harness for ingestion read-surface tests.

PR-2 (feat/ingestion-read-parity): Block-0 proved twice that SQLite-only testing is
structurally blind to Postgres-vs-SQLite drift (a JSONB dict crashed ``json.loads`` and
an ``int`` for a BOOLEAN column was rejected by psycopg). This harness makes that
blindness impossible: every read test runs against BOTH engines and asserts identical
JSON.

Offline default is preserved: with ``TARIFHUB_PG_TEST_URL`` unset only the ``sqlite``
parameter exists and the suite stays fully offline (the established opt-in pattern from
``test_audit_pg_roundtrip.py``). When the env var IS set, a ``postgres`` parameter is
added; its setup creates a DEDICATED, uniquely-named scratch database, applies
``db/schema.sql`` into it, and teardown drops it — the shared dev ``tarifhub`` database
is never written to.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from tarifhub_ingest.storage.db import Database

PG_URL = os.environ.get("TARIFHUB_PG_TEST_URL")

# The canonical Postgres schema (NUMERIC/JSONB/BOOLEAN/TIMESTAMPTZ) lives here.
_SCHEMA_SQL = (
    Path(__file__).resolve().parents[3] / "db" / "schema.sql"
)

# Engine parameters: sqlite always; postgres only when the opt-in URL is set.
ENGINE_PARAMS = ["sqlite"] + (["postgres"] if PG_URL else [])


@dataclass
class Engine:
    """A provisioned, isolated database one parity run reads/writes against."""

    label: str
    db_url: str
    db: Database


def _admin_url_and_dbname(base_url: str, dbname: str) -> tuple[str, str]:
    """Rewrite ``base_url`` to target ``dbname`` (server/credentials unchanged)."""

    parsed = urlparse(base_url)
    new = parsed._replace(path=f"/{dbname}")
    return urlunparse(new), dbname


def _create_pg_scratch(base_url: str) -> tuple[str, str]:
    """CREATE a uniquely-named scratch database; apply db/schema.sql. Returns its URL."""

    import psycopg

    scratch = f"tarifhub_parity_{uuid.uuid4().hex[:12]}"
    # Connect to the base (dev) db only to issue CREATE DATABASE — autocommit required.
    admin = psycopg.connect(base_url, autocommit=True)
    try:
        admin.execute(f'CREATE DATABASE "{scratch}"')
    finally:
        admin.close()

    scratch_url, _ = _admin_url_and_dbname(base_url, scratch)
    schema_sql = _SCHEMA_SQL.read_text(encoding="utf-8")
    conn = psycopg.connect(scratch_url, autocommit=True)
    try:
        conn.execute(schema_sql)
    finally:
        conn.close()
    return scratch_url, scratch


def _drop_pg_scratch(base_url: str, scratch: str) -> None:
    import psycopg

    admin = psycopg.connect(base_url, autocommit=True)
    try:
        # Terminate any lingering backends so DROP cannot block.
        admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (scratch,),
        )
        admin.execute(f'DROP DATABASE IF EXISTS "{scratch}"')
    finally:
        admin.close()


def make_engine(label: str, tmp_path) -> Iterator[Engine]:
    """Yield a provisioned :class:`Engine` for ``label`` ("sqlite" | "postgres").

    SQLite: a fresh temp-file db with the mirrored DDL applied.
    Postgres: a fresh scratch database with ``db/schema.sql`` applied; dropped on
    teardown. Generator so callers can ``yield from`` inside a pytest fixture.
    """

    if label == "sqlite":
        url = f"sqlite:///{tmp_path / 'parity.db'}"
        db = Database.from_url(url)
        conn = db.connect()
        db.init_schema(conn)
        conn.close()
        yield Engine(label=label, db_url=url, db=db)
        return

    if label == "postgres":
        if not PG_URL:  # pragma: no cover - guarded by ENGINE_PARAMS
            raise RuntimeError("postgres engine requested without TARIFHUB_PG_TEST_URL")
        scratch_url, scratch = _create_pg_scratch(PG_URL)
        try:
            db = Database.from_url(scratch_url)
            yield Engine(label=label, db_url=scratch_url, db=db)
        finally:
            _drop_pg_scratch(PG_URL, scratch)
        return

    raise ValueError(f"unknown engine label: {label!r}")  # pragma: no cover
