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
import math
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
        as_of: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TariffRecord]:
        """Return one frozen record per ``(system, code)``, deterministically ordered.

        Without ``as_of`` this is the latest version per key (byte-identical to the prior
        behaviour). With ``as_of`` the candidate rows are first restricted to those whose
        validity window covers the date — ``valid_from <= as_of`` (a NULL ``valid_from``
        means "valid from the beginning of time", so it always qualifies) and
        ``valid_to IS NULL OR valid_to >= as_of`` — and then the MAX(version) per key is
        chosen among the qualifying rows. Optionally filtered to a single ``system``.
        Pagination is applied over the deterministic ``(tariff_system, tariff_code)``
        order so the same query always returns the same page.
        """

        ph = self._ph
        params: list[Any] = []

        validity_sql, validity_params = self._validity_clause(as_of, alias="")
        inner_where = f" WHERE {validity_sql}" if validity_sql else ""

        outer_filters: list[str] = []
        outer_params: list[Any] = []
        if system is not None:
            outer_filters.append(f"t.tariff_system = {ph}")
            outer_params.append(system)
        # Re-apply the validity predicate on the outer rows: the subquery's MAX(version)
        # is computed over qualifying rows, and the joined row must itself qualify (a
        # later non-qualifying version must not be returned just because it is the max).
        outer_validity_sql, outer_validity_params = self._validity_clause(as_of, alias="t.")
        if outer_validity_sql:
            outer_filters.append(outer_validity_sql)
        where = f"WHERE {' AND '.join(outer_filters)} " if outer_filters else ""

        # The selected version per (system, code) is the row whose version equals the
        # MAX(version) for that key among rows that qualify for ``as_of`` (all rows when
        # ``as_of`` is None). Subquery keeps this dialect-portable.
        query = (
            "SELECT t.* FROM tariff t "
            "JOIN (SELECT tariff_system, tariff_code, MAX(version) AS max_version "
            f"      FROM tariff{inner_where} GROUP BY tariff_system, tariff_code) latest "
            "  ON t.tariff_system = latest.tariff_system "
            " AND t.tariff_code = latest.tariff_code "
            " AND t.version = latest.max_version "
            f"{where}"
            "ORDER BY t.tariff_system, t.tariff_code "
            f"LIMIT {ph} OFFSET {ph}"
        )
        params.extend(validity_params)
        params.extend(outer_params)
        params.extend(outer_validity_params)
        params.extend([limit, offset])
        rows = self._conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_latest(
        self, system: str, code: str, *, as_of: date | None = None
    ) -> TariffRecord | None:
        """Return one frozen record for a ``(system, code)`` key.

        Without ``as_of`` this is the highest-version record. With ``as_of`` the result is
        the highest-version record whose validity window covers the date (see
        :meth:`list_latest` for the window semantics); ``None`` when no version qualifies.
        """

        ph = self._ph
        validity_sql, validity_params = self._validity_clause(as_of, alias="")
        where = f" AND {validity_sql}" if validity_sql else ""
        query = (
            f"SELECT * FROM tariff WHERE tariff_system = {ph} AND tariff_code = {ph}"
            f"{where} ORDER BY version DESC LIMIT 1"
        )
        params = [system, code, *validity_params]
        row = self._conn.execute(query, tuple(params)).fetchone()
        return self._row_to_record(row) if row else None

    def get_version(self, system: str, code: str, version: int) -> TariffRecord | None:
        """Return the frozen record at an exact ``version`` for a ``(system, code)`` key."""

        ph = self._ph
        query = (
            f"SELECT * FROM tariff WHERE tariff_system = {ph} AND tariff_code = {ph} "
            f"AND version = {ph}"
        )
        row = self._conn.execute(query, (system, code, version)).fetchone()
        return self._row_to_record(row) if row else None

    def list_versions_by_code(
        self, code: str, *, system: str | None = None
    ) -> list[TariffRecord]:
        """Return ALL versions of every ``(system, code)`` matching ``code``.

        Optionally scoped to a single ``system``. Deterministically ordered by
        ``(tariff_system, version)`` ascending so an unscoped read (the same code in two
        systems) never depends on row order.
        """

        ph = self._ph
        params: list[Any] = [code]
        where = f"tariff_code = {ph}"
        if system is not None:
            where += f" AND tariff_system = {ph}"
            params.append(system)
        query = f"SELECT * FROM tariff WHERE {where} ORDER BY tariff_system, version"
        rows = self._conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_record(row) for row in rows]

    def count_latest_keys(self, system: str, *, as_of: date | None = None) -> int:
        """Count distinct ``(tariff_system, tariff_code)`` keys in one ``system``.

        Counts keys that have at least one qualifying version (all versions when ``as_of``
        is None; otherwise versions whose validity window covers the date — same predicate
        as :meth:`list_latest`). Used by the FHIR CodeSystem route to report the TOTAL key
        count alongside a windowed concept list, so ``count`` is independent of pagination.
        Parameterised and dialect-portable (``COUNT(DISTINCT ...)`` over a subquery).
        """

        ph = self._ph
        validity_sql, validity_params = self._validity_clause(as_of, alias="")
        where = f"tariff_system = {ph}"
        params: list[Any] = [system]
        if validity_sql:
            where += f" AND {validity_sql}"
            params.extend(validity_params)
        query = (
            "SELECT COUNT(*) AS n FROM ("
            "SELECT tariff_code FROM tariff "
            f"WHERE {where} "
            "GROUP BY tariff_code) keys"
        )
        row = self._conn.execute(query, tuple(params)).fetchone()
        data = dict(row)
        return int(data["n"])

    def _validity_clause(self, as_of: date | None, *, alias: str) -> tuple[str, list[Any]]:
        """Build the point-in-time validity predicate for ``as_of`` (or empty when None).

        ISO date strings compare correctly both as SQLite TEXT and against a Postgres
        DATE column (implicit cast), so the same parameterised literal works on both
        engines. A NULL ``valid_from`` qualifies (valid from the beginning of time).
        """

        if as_of is None:
            return "", []
        ph = self._ph
        iso = as_of.isoformat()
        clause = (
            f"({alias}valid_from IS NULL OR {alias}valid_from <= {ph}) "
            f"AND ({alias}valid_to IS NULL OR {alias}valid_to >= {ph})"
        )
        return clause, [iso, iso]

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

    def search_offline(self, query_vector: list[float], limit: int) -> list[TariffRecord]:
        """Rank latest-version frozen rows by cosine similarity, computed in Python.

        The offline (SQLite) fallback: there is no pgvector, so we fetch the latest
        version of each key that has a stored embedding of matching dimension, compute
        cosine similarity in pure Python, and rank descending. Ties break on
        ``(tariff_system, tariff_code)`` ascending so the order is fully deterministic.
        Rows without an embedding, or whose stored dimension differs from the query
        vector's, are excluded — the ranker never fabricates a value, it only orders
        unaltered frozen rows.
        """

        dim = len(query_vector)
        # Latest version per key, with its raw stored embedding text. The MAX(version)
        # subquery mirrors ``list_latest`` so search ranks current records only.
        query = (
            "SELECT t.*, t.embedding AS _emb FROM tariff t "
            "JOIN (SELECT tariff_system, tariff_code, MAX(version) AS max_version "
            "      FROM tariff GROUP BY tariff_system, tariff_code) latest "
            "  ON t.tariff_system = latest.tariff_system "
            " AND t.tariff_code = latest.tariff_code "
            " AND t.version = latest.max_version "
            "WHERE t.embedding IS NOT NULL "
            "ORDER BY t.tariff_system, t.tariff_code"
        )
        rows = self._conn.execute(query).fetchall()

        scored: list[tuple[float, str, str, Any]] = []
        for row in rows:
            data = dict(row)
            vector = _parse_embedding(data.get("_emb"))
            if vector is None or len(vector) != dim:
                continue
            score = _cosine_similarity(query_vector, vector)
            scored.append((score, data["tariff_system"], data["tariff_code"], row))

        # Rank by similarity desc, then (system, code) asc — negate the score so a single
        # ascending sort gives the deterministic order without a separate reverse pass.
        scored.sort(key=lambda s: (-s[0], s[1], s[2]))
        return [self._row_to_record(row) for _, _, _, row in scored[:limit]]

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


def _parse_embedding(value: Any) -> list[float] | None:
    """Decode a stored embedding into a list of floats (or None when absent).

    SQLite stores the offline embedding as a JSON-encoded list of floats (the form
    ``tariff_repository`` writes). ``None``/empty -> None (no candidate).
    """

    if value in (None, ""):
        return None
    if isinstance(value, str):
        decoded = json.loads(value)
    else:
        decoded = value
    return [float(x) for x in decoded]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors; 0.0 if either is a zero vector."""

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


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
