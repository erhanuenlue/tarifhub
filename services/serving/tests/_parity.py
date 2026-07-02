"""Shared cross-engine parity harness for the serving read surface.

Mirrors ``services/ingestion/tests/_parity.py``. The serving service is read-only, so
parity seeds frozen records through the ingestion ``TariffRepository`` (a test-only
import — the serving package itself never imports ingestion storage) and then asserts
the serving API returns identical JSON on SQLite and Postgres.

Offline default preserved: with ``TARIFHUB_PG_TEST_URL`` unset only ``sqlite`` runs and
the suite is fully offline. When set, a ``postgres`` parameter is added; setup creates a
DEDICATED, uniquely-named scratch database, applies ``db/schema.sql``, and teardown
drops it — the shared dev ``tarifhub`` database is never written to.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

# The serving service reuses the ingestion Database facade only here, in tests, to
# provision and seed the parity store; production serving code never imports it.
from tarifhub_ingest.storage.db import Database

PG_URL = os.environ.get("TARIFHUB_PG_TEST_URL")

_SCHEMA_SQL = Path(__file__).resolve().parents[3] / "db" / "schema.sql"

ENGINE_PARAMS = ["sqlite"] + (["postgres"] if PG_URL else [])


@dataclass
class Engine:
    """A provisioned, isolated database one parity run reads/writes against."""

    label: str
    db_url: str
    db: Database


def _scratch_url(base_url: str, dbname: str) -> str:
    parsed = urlparse(base_url)
    return urlunparse(parsed._replace(path=f"/{dbname}"))


def _create_pg_scratch(base_url: str) -> tuple[str, str]:
    import psycopg

    scratch = f"tarifhub_parity_{uuid.uuid4().hex[:12]}"
    admin = psycopg.connect(base_url, autocommit=True)
    try:
        admin.execute(f'CREATE DATABASE "{scratch}"')
    finally:
        admin.close()

    scratch_url = _scratch_url(base_url, scratch)
    conn = psycopg.connect(scratch_url, autocommit=True)
    try:
        conn.execute(_SCHEMA_SQL.read_text(encoding="utf-8"))
    finally:
        conn.close()
    return scratch_url, scratch


def _drop_pg_scratch(base_url: str, scratch: str) -> None:
    import psycopg

    admin = psycopg.connect(base_url, autocommit=True)
    try:
        admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (scratch,),
        )
        admin.execute(f'DROP DATABASE IF EXISTS "{scratch}"')
    finally:
        admin.close()


def make_engine(label: str, tmp_path) -> Iterator[Engine]:
    """Yield a provisioned :class:`Engine` for ``label`` ("sqlite" | "postgres")."""

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
