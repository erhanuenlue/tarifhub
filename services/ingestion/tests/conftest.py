"""Engine-parameterized fixtures for the ingestion read surface.

The ``engine`` fixture is parameterized over ``["sqlite"]`` offline and
``["sqlite", "postgres"]`` when ``TARIFHUB_PG_TEST_URL`` is set (see ``_parity``).
Parity tests request ``engine`` and assert read-endpoint JSON is identical across
both engines, so Postgres-vs-SQLite drift cannot pass silently.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from _parity import ENGINE_PARAMS, Engine, make_engine


@pytest.fixture(params=ENGINE_PARAMS)
def engine(request, tmp_path) -> Iterator[Engine]:
    """Yield a provisioned, isolated DB engine (sqlite always; postgres when opted in)."""

    yield from make_engine(request.param, tmp_path)
