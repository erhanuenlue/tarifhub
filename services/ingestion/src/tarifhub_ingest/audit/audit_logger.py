"""Append-only audit / lineage logging. PROTECTED MODULE.

Every freeze writes an immutable audit event capturing source file, parser version,
confidence, validation outcome and the resulting ``record_hash`` — the lineage that
makes a frozen value defensible. Append-only: events are never updated or deleted.
DO NOT add AI / network behaviour here, and change this module only with explicit
human confirmation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from tarifhub_ingest.models.tariff_model import TariffRecord
from tarifhub_ingest.storage.db import Database


class AuditLogger:
    """Writes append-only audit events to the ``audit_log`` table."""

    def __init__(self, conn, db: Database) -> None:
        self._conn = conn
        self._ph = db.placeholder

    def log(
        self,
        *,
        event_type: str,
        record: TariffRecord | None = None,
        source_file: str | None = None,
        parser_version: str | None = None,
        confidence: float | None = None,
        validation_ok: bool | None = None,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record one audit event and return it as a dict."""

        event = {
            "event_time": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "tariff_system": record.tariff_system.value if record else None,
            "tariff_code": record.tariff_code if record else None,
            "record_hash": record.record_hash if record else None,
            "source_file": source_file,
            "parser_version": parser_version,
            "confidence": confidence,
            "validation_ok": validation_ok,
            "detail": json.dumps(detail, sort_keys=True, ensure_ascii=False) if detail else None,
        }
        columns = ", ".join(event.keys())
        markers = ", ".join([self._ph] * len(event))
        self._conn.execute(
            f"INSERT INTO audit_log ({columns}) VALUES ({markers})",
            tuple(event.values()),
        )
        self._conn.commit()
        return event
