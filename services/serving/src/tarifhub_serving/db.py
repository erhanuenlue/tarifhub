"""Database connection facade for the read-only serving path.

A small, dialect-aware surface mirroring the ingestion ``Database`` facade so the
serving service can switch between the offline SQLite mirror and Postgres with a
single ``TARIFHUB_DB_URL`` change. This module is on the value-serving path and
therefore never imports an LLM client. It is read-only: no DDL, no writes.

The canonical Postgres schema (including the pgvector ``embedding`` column) lives in
``db/schema.sql``; the SQLite mirror is provisioned by the ingestion service. The
serving service only ever reads.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Database:
    """Lightweight read-only DB facade that knows its dialect and parameter style."""

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

        conn = psycopg.connect(self.db_url, autocommit=True)
        conn.row_factory = psycopg.rows.dict_row
        return conn
