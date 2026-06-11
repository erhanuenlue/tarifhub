"""Postgres round-trip regression for audit_log.validation_ok (True/False/None).

Owner-required regression for the 2026-06-11 freeze-line fix: psycopg must
receive a native bool (an int arrives as smallint and Postgres rejects it for
the boolean column). Opt-in integration test — the offline suite never touches
a network DB: set TARIFHUB_PG_TEST_URL (e.g. the compose db,
postgresql://tarifhub:tarifhub@localhost:5432/tarifhub) to enable.
"""

from __future__ import annotations

import os

import pytest

from tarifhub_ingest.audit.audit_logger import AuditLogger
from tarifhub_ingest.storage.db import Database

PG_URL = os.environ.get("TARIFHUB_PG_TEST_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL, reason="set TARIFHUB_PG_TEST_URL to run the Postgres integration test"
)


@pytest.fixture()
def pg_conn():
    db = Database.from_url(PG_URL)
    conn = db.connect()
    db.init_schema(conn)
    yield conn, db
    conn.close()


@pytest.mark.parametrize("flag", [True, False, None])
def test_validation_ok_roundtrips_on_postgres(pg_conn, flag):
    conn, db = pg_conn
    audit = AuditLogger(conn, db)

    event = audit.log(
        event_type="pg_roundtrip_test",
        record=None,
        source_file="test_audit_pg_roundtrip.py",
        parser_version="test/0",
        confidence=1.0,
        validation_ok=flag,
        detail={"flag": repr(flag)},
    )
    assert event["validation_ok"] is flag

    cur = conn.execute(
        "SELECT validation_ok FROM audit_log WHERE event_type = %s "
        "ORDER BY id DESC LIMIT 1",
        ("pg_roundtrip_test",),
    )
    # The Database facade now opens Postgres connections with psycopg's dict_row factory
    # (so the repository's dict(row) read path works) — rows are mapping-only, access by
    # column name rather than position.
    stored = cur.fetchone()["validation_ok"]
    assert stored is flag or stored == flag  # boolean column: True/False/None
