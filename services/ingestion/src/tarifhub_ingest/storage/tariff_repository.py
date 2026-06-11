"""Repository for frozen tariff records (write-once, read-many).

Frozen records are immutable: ``add`` is idempotent on ``record_hash`` (re-ingesting
identical content is a no-op), and the repository never updates a row in place. When
content *changes* for an existing ``(tariff_system, tariff_code)`` the new content is
stored as a fresh version (``MAX(version) + 1``) rather than mutating the prior row.
Reads reconstruct canonical :class:`TariffRecord` objects. No LLM imports — this is the
deterministic value path.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem
from tarifhub_ingest.storage.db import Database

_COLUMNS = (
    "tariff_code",
    "tariff_system",
    "designation_de",
    "designation_fr",
    "designation_it",
    "category",
    "tax_points",
    "price_chf",
    "unit",
    "valid_from",
    "valid_to",
    "source_url",
    "source_version",
    "harmonization_confidence",
    "requires_review",
    "metadata",
    "embedding",
    "record_hash",
    "version",
    "created_at",
)


class TariffRepository:
    """Persistence port for frozen canonical records."""

    def __init__(self, conn, db: Database) -> None:
        self._conn = conn
        self._db = db
        self._ph = db.placeholder

    def add(self, record: TariffRecord, embedding: list[float] | None = None) -> bool:
        """Persist a frozen record. Returns False if an identical hash already exists."""

        if record.record_hash is None:
            raise ValueError("refusing to store an unfrozen record (record_hash is None)")
        if self.exists(record.record_hash):
            return False

        # Changed content for an existing (system, code) supersedes the prior row:
        # frozen records are immutable, so we never UPDATE — we insert a new version
        # at MAX(version) + 1. version is excluded from HASHED_FIELDS, so stamping the
        # bumped value cannot alter record_hash. The record's incoming version is ignored.
        record = record.model_copy(update={"version": self._next_version(record)})

        columns = ", ".join(_COLUMNS)
        markers = ", ".join([self._ph] * len(_COLUMNS))
        values = self._record_to_row(record, embedding)
        self._conn.execute(
            f"INSERT INTO tariff ({columns}) VALUES ({markers})", values
        )
        self._conn.commit()
        return True

    def _next_version(self, record: TariffRecord) -> int:
        """Return MAX(version) + 1 for the record's (tariff_system, tariff_code), or 1.

        New content for an existing key starts a new version; the first row for a key
        starts at 1, ignoring whatever version the incoming record carried.
        """

        cur = self._conn.execute(
            "SELECT MAX(version) FROM tariff "
            f"WHERE tariff_system = {self._ph} AND tariff_code = {self._ph}",
            (record.tariff_system.value, record.tariff_code),
        )
        current_max = cur.fetchone()[0]
        return 1 if current_max is None else int(current_max) + 1

    def exists(self, record_hash: str) -> bool:
        cur = self._conn.execute(
            f"SELECT 1 FROM tariff WHERE record_hash = {self._ph} LIMIT 1", (record_hash,)
        )
        return cur.fetchone() is not None

    def get(self, tariff_code: str, system: TariffSystem | str | None = None) -> TariffRecord | None:
        """Return the highest-version record for a code (optionally scoped to a system)."""

        query = f"SELECT * FROM tariff WHERE tariff_code = {self._ph}"
        params: list[Any] = [tariff_code]
        if system is not None:
            query += f" AND tariff_system = {self._ph}"
            params.append(system.value if isinstance(system, TariffSystem) else str(system))
        query += " ORDER BY version DESC LIMIT 1"
        row = self._conn.execute(query, tuple(params)).fetchone()
        return self._row_to_record(row) if row else None

    def list_all(self) -> list[TariffRecord]:
        """Return all frozen records ordered by system then code."""

        rows = self._conn.execute(
            "SELECT * FROM tariff ORDER BY tariff_system, tariff_code, version"
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    # --- mapping helpers -------------------------------------------------

    def _record_to_row(self, record: TariffRecord, embedding: list[float] | None) -> tuple:
        return (
            record.tariff_code,
            record.tariff_system.value,
            record.designation.de,
            record.designation.fr,
            record.designation.it,
            record.category,
            _decimal_to_text(record.tax_points),
            _decimal_to_text(record.price_chf),
            record.unit,
            record.valid_from.isoformat() if record.valid_from else None,
            record.valid_to.isoformat() if record.valid_to else None,
            record.source_url,
            record.source_version,
            record.harmonization_confidence,
            # Real bool: psycopg must send a boolean for the Postgres column
            # (an int arrives as smallint and is rejected); sqlite3 adapts
            # bools to 0/1 natively, so both engines are happy.
            record.requires_review,
            json.dumps(record.metadata, sort_keys=True, ensure_ascii=False),
            json.dumps(embedding) if embedding is not None else None,
            record.record_hash,
            record.version,
            record.created_at.isoformat(),
        )

    def _row_to_record(self, row: Any) -> TariffRecord:
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
            metadata=json.loads(data["metadata"]) if data["metadata"] else {},
            record_hash=data["record_hash"],
            version=data["version"],
            created_at=datetime.fromisoformat(data["created_at"]),
        )


def _decimal_to_text(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def _text_to_decimal(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value not in (None, "") else None


def _text_to_date(value: Any) -> date | None:
    return date.fromisoformat(str(value)[:10]) if value not in (None, "") else None
