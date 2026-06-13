"""Storage facade error/edge cases: dialect detection, parameter style, schema guard.

The ``Database`` facade is on the value-serving path. These tests pin its dialect
discrimination and the fail-closed ``ValueError`` on an unsupported URL scheme, plus
the non-sqlite ``init_schema`` no-op (Postgres is provisioned from ``db/migrations``,
never by this module). No live Postgres needed — the postgres ``connect()`` leg is
exercised by the CI ``python-parity`` job against a real pgvector container.
"""

from __future__ import annotations

import pytest

from tarifhub_ingest.storage.db import Database


def test_from_url_detects_sqlite():
    db = Database.from_url("sqlite:///tmp/x.db")
    assert db.dialect == "sqlite"
    assert db.placeholder == "?"


def test_from_url_detects_postgres():
    db = Database.from_url("postgresql://user:pw@host:5432/tarifhub")
    assert db.dialect == "postgresql"
    assert db.placeholder == "%s"


def test_from_url_rejects_unsupported_scheme():
    """An unknown scheme fails closed with a clear error rather than guessing a dialect."""

    with pytest.raises(ValueError, match="unsupported database URL scheme"):
        Database.from_url("mysql://host/db")


def test_init_schema_is_a_noop_on_non_sqlite():
    """Postgres is provisioned from db/migrations; init_schema must not touch the conn.

    A bare sentinel object is passed as the connection: the no-op returns without using
    it. Were the guard to fall through to the SQLite DDL path it would call
    ``conn.executescript`` and raise ``AttributeError`` — so a clean return proves the
    no-op.
    """

    db = Database.from_url("postgresql://user:pw@host/db")
    assert db.init_schema(object()) is None
