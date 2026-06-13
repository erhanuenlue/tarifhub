"""Serving DB facade error/edge cases: dialect detection + parameter style.

The serving facade mirrors the ingestion one but is strictly read-only. These pin the
dialect discrimination, the per-dialect parameter marker, and the fail-closed
``ValueError`` on an unsupported URL scheme. The postgres ``connect()`` leg is covered
by the CI ``python-parity`` job against a real pgvector container.
"""

from __future__ import annotations

import pytest

from tarifhub_serving.db import Database


def test_from_url_detects_sqlite():
    db = Database.from_url("sqlite:///x.db")
    assert db.dialect == "sqlite"
    assert db.placeholder == "?"


def test_from_url_detects_postgres():
    db = Database.from_url("postgresql://u:p@h:5432/tarifhub")
    assert db.dialect == "postgresql"
    assert db.placeholder == "%s"


def test_from_url_rejects_unsupported_scheme():
    with pytest.raises(ValueError, match="unsupported database URL scheme"):
        Database.from_url("redis://h")
