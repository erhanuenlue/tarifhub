"""Read-only repository over frozen tariff records (the value-serving path).

This is the authoritative value path: every record returned is an unaltered, frozen,
versioned row read straight from the system of record. The serving service NEVER
writes or mutates a row, and NEVER imports an LLM client. All SQL is parameterised.

The canonical :class:`TariffRecord` is imported from the ingestion package so there is
one canonical model end-to-end. The DB facade and the small text<->Decimal/date
helpers are local (deliberately not imported from ``tarifhub_ingest.storage``) so the
serving import graph stays minimal for the determinism boundary test.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem

from tarifhub_serving.db import Database


class ServingRepository:
    """Read-only persistence port for frozen canonical records."""

    def __init__(self, conn, db: Database) -> None:
        self._conn = conn
        self._db = db
        self._ph = db.placeholder

    # --- reads -----------------------------------------------------------

    def list_latest(
        self,
        *,
        system: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TariffRecord]:
        """Return the latest version of each frozen record, deterministically ordered.

        Optionally filtered to a single ``system``. Pagination via ``limit``/``offset``
        is applied over the deterministic ``(tariff_system, tariff_code)`` order so the
        same query always returns the same page.
        """

        ph = self._ph
        params: list[Any] = []
        where = ""
        if system is not None:
            where = f"WHERE t.tariff_system = {ph}"
            params.append(system)

        # The latest version per (system, code) is the row whose version equals the
        # MAX(version) for that key. Subquery keeps this dialect-portable.
        query = (
            "SELECT t.* FROM tariff t "
            "JOIN (SELECT tariff_system, tariff_code, MAX(version) AS max_version "
            "      FROM tariff GROUP BY tariff_system, tariff_code) latest "
            "  ON t.tariff_system = latest.tariff_system "
            " AND t.tariff_code = latest.tariff_code "
            " AND t.version = latest.max_version "
            f"{where} "
            "ORDER BY t.tariff_system, t.tariff_code "
            f"LIMIT {ph} OFFSET {ph}"
        )
        params.extend([limit, offset])
        rows = self._conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_latest(self, system: str, code: str) -> TariffRecord | None:
        """Return the highest-version frozen record for a ``(system, code)`` key."""

        ph = self._ph
        query = (
            f"SELECT * FROM tariff WHERE tariff_system = {ph} AND tariff_code = {ph} "
            "ORDER BY version DESC LIMIT 1"
        )
        row = self._conn.execute(query, (system, code)).fetchone()
        return self._row_to_record(row) if row else None

    def search_by_embedding(self, embedding: list[float], limit: int) -> list[TariffRecord]:
        """Nearest frozen rows by pgvector cosine distance (Postgres only).

        The serving service ranks; it never fabricates or mutates a value. Every field
        in every hit is an unaltered frozen row. SQLite has no pgvector, so semantic
        search is unavailable there (the API surfaces an honest 501 instead).
        """

        if self._db.dialect != "postgresql":
            raise RuntimeError("semantic search requires Postgres+pgvector")

        ph = self._ph
        vector_literal = "[" + ",".join(repr(float(x)) for x in embedding) + "]"
        query = (
            "SELECT t.* FROM tariff t "
            "WHERE t.embedding IS NOT NULL "
            f"ORDER BY t.embedding <=> CAST({ph} AS vector) "
            f"LIMIT {ph}"
        )
        rows = self._conn.execute(query, (vector_literal, limit)).fetchall()
        return [self._row_to_record(row) for row in rows]

    # --- mapping ---------------------------------------------------------

    def _row_to_record(self, row: Any) -> TariffRecord:
        return _row_to_record(row)


def _row_to_record(row: Any) -> TariffRecord:
    """Reconstruct a canonical :class:`TariffRecord` from a DB row (dialect-agnostic).

    Module-level so the mapping is unit-testable without a live connection.
    """

    data = dict(row)
    return TariffRecord(
        tariff_code=data["tariff_code"],
        tariff_system=TariffSystem(data["tariff_system"]),
        designation=Designation(
            de=data["designation_de"],
            fr=data["designation_fr"],
            it=data["designation_it"],
        ),
        category=data["category"],
        tax_points=_text_to_decimal(data["tax_points"]),
        price_chf=_text_to_decimal(data["price_chf"]),
        unit=data["unit"],
        valid_from=_text_to_date(data["valid_from"]),
        valid_to=_text_to_date(data["valid_to"]),
        source_url=data["source_url"],
        source_version=data["source_version"],
        harmonization_confidence=data["harmonization_confidence"],
        requires_review=bool(data["requires_review"]),
        metadata=_parse_metadata(data["metadata"]),
        record_hash=data["record_hash"],
        version=data["version"],
        created_at=_to_datetime(data["created_at"]),
    )


def _parse_metadata(value: Any) -> dict[str, Any]:
    """Normalise the ``metadata`` column into a dict.

    SQLite stores it as a JSON text string; the Postgres JSONB column comes back from
    the driver as a native ``dict`` (or list). Decode only when it is a ``str``; pass a
    native dict through unchanged. ``None``/empty -> ``{}``.
    """

    if value in (None, ""):
        return {}
    if isinstance(value, str):
        return json.loads(value)
    return value


def _text_to_decimal(value: Any) -> Decimal | None:
    """Decode a stored money/points value to a scale-canonical ``Decimal``.

    SQLite stores the writer's exact text (``10.50``); Postgres NUMERIC(12,4)/(12,2)
    coerces to the column scale (``10.5000`` / ``12.30``). Left raw, the two engines
    serialise different JSON strings for the same value. We normalise to the SAME
    canonical form the integrity hash uses (``format(Decimal.normalize(), "f")`` —
    ``10.5000`` -> ``10.5``), so the served value is engine-independent and equals the
    hashed content form.
    """

    if value in (None, ""):
        return None
    return Decimal(format(Decimal(str(value)).normalize(), "f"))


def _text_to_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def _to_datetime(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
