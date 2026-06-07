"""Database connection + schema bootstrap.

SQLite by default (offline dev/test); Postgres-ready behind the same small surface
so switching is just a ``TARIFHUB_DB_URL`` change. The canonical Postgres schema —
including the pgvector ``embedding`` column — lives in ``db/schema.sql`` and
``db/migrations``; the SQLite DDL here is a faithful, dependency-free mirror for
local runs (vectors stored as JSON text). This module is on the value-serving path
and therefore never imports an LLM client.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from urllib.parse import urlparse

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS tariff (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    tariff_code              TEXT    NOT NULL,
    tariff_system            TEXT    NOT NULL,
    designation_de           TEXT    NOT NULL,
    designation_fr           TEXT,
    designation_it           TEXT,
    category                 TEXT,
    tax_points               TEXT,            -- Decimal as text to preserve precision
    price_chf                TEXT,
    unit                     TEXT,
    valid_from               TEXT,
    valid_to                 TEXT,
    source_url               TEXT,
    source_version           TEXT,
    harmonization_confidence REAL    NOT NULL,
    requires_review          INTEGER NOT NULL,
    metadata                 TEXT    NOT NULL DEFAULT '{}',
    embedding                TEXT,            -- pgvector(1024) in Postgres
    record_hash              TEXT    NOT NULL,
    version                  INTEGER NOT NULL,
    created_at               TEXT    NOT NULL,
    UNIQUE (tariff_system, tariff_code, version)
);
CREATE INDEX IF NOT EXISTS ix_tariff_code ON tariff (tariff_system, tariff_code);
CREATE UNIQUE INDEX IF NOT EXISTS ux_tariff_hash ON tariff (record_hash);

CREATE TABLE IF NOT EXISTS audit_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_time     TEXT NOT NULL,
    event_type     TEXT NOT NULL,
    tariff_system  TEXT,
    tariff_code    TEXT,
    record_hash    TEXT,
    source_file    TEXT,
    parser_version TEXT,
    confidence     REAL,
    validation_ok  INTEGER,
    detail         TEXT
);
"""


@dataclass(frozen=True)
class Database:
    """Lightweight DB facade that knows its dialect and parameter style."""

    db_url: str
    dialect: str  # "sqlite" | "postgresql"

    @classmethod
    def from_url(cls, db_url: str) -> "Database":
        scheme = urlparse(db_url).scheme.lower()
        if scheme.startswith("sqlite"):
            return cls(db_url=db_url, dialect="sqlite")
        if scheme.startswith("postgres"):
            return cls(db_url=db_url, dialect="postgresql")
        raise ValueError(f"unsupported database URL scheme: {scheme!r}")

    @property
    def placeholder(self) -> str:
        """Parameter marker for the active dialect."""

        return "?" if self.dialect == "sqlite" else "%s"

    def connect(self):
        """Open a DB-API connection for the active dialect."""

        if self.dialect == "sqlite":
            path = self.db_url.replace("sqlite:///", "", 1).replace("sqlite://", "", 1)
            conn = sqlite3.connect(path or ":memory:", check_same_thread=False)
            conn.row_factory = sqlite3.Row
            return conn
        # Postgres: import guarded so SQLite-only runs need no driver installed.
        import psycopg  # noqa: PLC0415

        return psycopg.connect(self.db_url)

    def init_schema(self, conn) -> None:
        """Create tables if absent.

        SQLite runs the mirrored DDL here; Postgres is provisioned from
        ``db/migrations`` (this is a no-op so we never fight Flyway/psql).
        """

        if self.dialect != "sqlite":
            return
        conn.executescript(_SQLITE_SCHEMA)
        conn.commit()
