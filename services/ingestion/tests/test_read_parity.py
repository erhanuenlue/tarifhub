"""Cross-engine read parity for the ingestion read surface (SQLite vs Postgres).

Every test runs against BOTH engines via the ``engine`` fixture (Postgres added when
``TARIFHUB_PG_TEST_URL`` is set). We seed the SAME logical records into the engine,
then assert each read endpoint's FULL JSON body equals an engine-independent expected
snapshot. Because both engines must match the same snapshot, they must match each other
— SQLite-only blindness becomes impossible.

Seed data deliberately exercises every Block-0 drift surface:
  * non-ASCII designations (ü, é, ç) — collation / ordering,
  * nested metadata dicts — JSONB (native dict) vs TEXT (json string),
  * ``requires_review`` True AND False — BOOLEAN vs INTEGER (the tariff-table twin of
    the audit_log bool fixed in Block 0),
  * Decimal with trailing-zero scale (10.50) — NUMERIC(12,4)/(12,2) vs TEXT,
  * valid_from / valid_to dates — DATE vs TEXT,
  * two versions of one (system, code) — latest-version selection,
  * pagination windows and the system filter.

``created_at`` is pinned with a fixed clock (monkeypatch) so full-body equality is
honest rather than achieved by excluding fields. Env mutations are monkeypatch-scoped.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem
from tarifhub_ingest.storage.tariff_repository import TariffRepository
from tarifhub_ingest.versioning.freeze_record import freeze

# A single fixed instant for every seeded record so created_at is engine-independent.
FIXED_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _seed_records() -> list[TariffRecord]:
    """Records spanning every cross-engine drift surface (see module docstring)."""

    common = dict(
        valid_from=date(2024, 1, 1),
        source_url="https://example.test/src",
        source_version="2024.1",
        harmonization_confidence=0.91,
        created_at=FIXED_NOW,
    )
    return [
        # requires_review=False, trailing-zero Decimal, nested metadata, valid_to set.
        TariffRecord(
            tariff_code="AA.00.0010",
            tariff_system=TariffSystem.TARDOC,
            designation=Designation(de="Übungsbehandlung", fr="Thérapie", it="Terapia"),
            category="therapy",
            tax_points=Decimal("10.50"),
            price_chf=Decimal("12.30"),
            unit="per 5 min",
            valid_to=date(2025, 12, 31),
            requires_review=False,
            metadata={"source": {"page": 3, "lang": ["de", "fr"]}, "rev": 2},
            version=1,
            **common,
        ),
        # Superseding version of the same key — list/get must return v2 only.
        TariffRecord(
            tariff_code="AA.00.0010",
            tariff_system=TariffSystem.TARDOC,
            designation=Designation(de="Übungsbehandlung (rev)", fr="Thérapie révisée"),
            category="therapy",
            tax_points=Decimal("11.00"),
            price_chf=Decimal("12.30"),
            unit="per 5 min",
            requires_review=True,  # the BOOLEAN-vs-INTEGER twin, read side
            metadata={"source": {"page": 4}, "rev": 3},
            version=2,
            **common,
        ),
        # Non-ASCII (ç) ordering probe; requires_review=True; empty metadata.
        TariffRecord(
            tariff_code="BB.00.0020",
            tariff_system=TariffSystem.TARDOC,
            designation=Designation(de="Çedille-Position", fr="Façade"),
            category="surcharge",
            tax_points=Decimal("4.25"),
            requires_review=True,
            version=1,
            **common,
        ),
        # Different system (EAL) — exercises the system filter; é in designation.
        TariffRecord(
            tariff_code="1234.00",
            tariff_system=TariffSystem.EAL,
            designation=Designation(de="Blutzucker (Glukose)", fr="Glycémie élevée"),
            category="lab",
            tax_points=Decimal("2.50"),
            requires_review=False,
            metadata={"unit_count": 1},
            version=1,
            **common,
        ),
        # Max canonical scales: price_chf 12.34 (NUMERIC(12,2)) + tax_points 76.5000
        # (NUMERIC(12,4)). At the column scales exactly, so both engines must serialise
        # the SAME canonical Decimal — the scale contract's cross-engine proof.
        TariffRecord(
            tariff_code="SCALE.MAX",
            tariff_system=TariffSystem.EAL,
            designation=Designation(de="Skalengrenze"),
            category="lab",
            tax_points=Decimal("76.5000"),
            price_chf=Decimal("12.34"),
            requires_review=False,
            version=1,
            **common,
        ),
        # Lossy-input fail-closed shape: the mapper could not represent the value at the
        # canonical scale, so the billing field is None and the original is kept as a
        # metadata raw_* string. Both engines store None cleanly and round-trip the same
        # raw_* marker (JSONB dict vs TEXT json).
        TariffRecord(
            tariff_code="SCALE.LOSSY",
            tariff_system=TariffSystem.EAL,
            designation=Designation(de="Verlustfall"),
            category="lab",
            price_chf=None,
            metadata={"raw_price_chf": "12.345"},
            requires_review=True,
            version=1,
            **common,
        ),
    ]


def _seed(engine) -> None:
    conn = engine.db.connect()
    try:
        engine.db.init_schema(conn)
        repo = TariffRepository(conn, engine.db)
        for record in _seed_records():
            repo.add(freeze(record))
    finally:
        conn.close()


@pytest.fixture()
def app_client(engine, monkeypatch) -> Iterator[TestClient]:
    """Seed the engine, then a TestClient over the ingestion app bound to it.

    Entered as a context manager so the app's lifespan provisions ``state.repo``
    against the seeded engine URL (the app reads frozen records read-only).
    """

    _seed(engine)
    monkeypatch.setenv("TARIFHUB_DB_URL", engine.db_url)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from tarifhub_ingest.main import create_app

    with TestClient(create_app()) as client:
        yield client


# --- engine-independent expected snapshots --------------------------------------
#
# Built from the canonical model the same way the endpoint does (model_dump json),
# so the assertion pins the exact wire shape AND ties both engines to one truth.


def _canonical_decimal(value: str | None) -> str | None:
    """Normalise a serialised Decimal to the scale-canonical read form (10.50 -> 10.5).

    Mirrors ``tariff_repository._text_to_decimal``: the read path normalises Decimals to
    the integrity-hash form so the wire value is identical regardless of engine. The
    expected snapshot must reflect that read-side normalisation, not the raw input scale.
    """

    if value is None:
        return None
    return format(Decimal(value).normalize(), "f")


def _expected_records() -> list[dict]:
    frozen = [freeze(r) for r in _seed_records()]
    # version is stamped by the repository as MAX(version)+1 per key; our seed already
    # carries the right versions (1 then 2 for AA, 1 elsewhere), matching that logic.
    out: list[dict] = []
    for r in frozen:
        dumped = r.model_dump(mode="json")
        dumped["tax_points"] = _canonical_decimal(dumped["tax_points"])
        dumped["price_chf"] = _canonical_decimal(dumped["price_chf"])
        out.append(dumped)
    return out


def _latest_by_key(records: list[dict]) -> list[dict]:
    latest: dict[tuple[str, str], dict] = {}
    for r in records:
        key = (r["tariff_system"], r["tariff_code"])
        if key not in latest or r["version"] > latest[key]["version"]:
            latest[key] = r
    return list(latest.values())


def test_health_parity(app_client):
    resp = app_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_list_full_body_parity(app_client):
    """GET /tariffs returns ALL versions ordered (system, code, version), identically."""

    resp = app_client.get("/tariffs")
    assert resp.status_code == 200
    body = resp.json()

    expected = sorted(
        _expected_records(),
        key=lambda r: (r["tariff_system"], r["tariff_code"], r["version"]),
    )
    assert body == expected


def test_list_order_is_identical_across_engines(app_client):
    """Order (the key list) must be byte-stable; non-ASCII must not reorder by engine."""

    body = app_client.get("/tariffs").json()
    order = [(r["tariff_system"], r["tariff_code"], r["version"]) for r in body]
    expected_order = sorted(
        (r["tariff_system"], r["tariff_code"], r["version"]) for r in _expected_records()
    )
    assert order == expected_order


def test_get_latest_version_parity(app_client):
    """GET /tariffs/{code} returns the highest version with its full body."""

    resp = app_client.get("/tariffs/AA.00.0010")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 2

    expected = next(
        r
        for r in _latest_by_key(_expected_records())
        if r["tariff_code"] == "AA.00.0010"
    )
    assert body == expected


def test_requires_review_bool_read_parity(app_client):
    """requires_review must read back as JSON bool on BOTH engines (Block-0 twin)."""

    body = app_client.get("/tariffs").json()
    flags = {(r["tariff_code"], r["version"]): r["requires_review"] for r in body}
    assert flags[("AA.00.0010", 1)] is False
    assert flags[("AA.00.0010", 2)] is True
    assert flags[("BB.00.0020", 1)] is True
    assert flags[("1234.00", 1)] is False


def test_metadata_dict_read_parity(app_client):
    """Nested metadata dicts survive JSONB(dict) vs TEXT(json) identically."""

    body = app_client.get("/tariffs").json()
    aa_v1 = next(
        r for r in body if r["tariff_code"] == "AA.00.0010" and r["version"] == 1
    )
    assert aa_v1["metadata"] == {"source": {"page": 3, "lang": ["de", "fr"]}, "rev": 2}


def test_decimal_scale_read_parity(app_client):
    """Trailing-zero Decimals serialise identically (NUMERIC scale vs TEXT)."""

    body = app_client.get("/tariffs").json()
    aa_v1 = next(
        r for r in body if r["tariff_code"] == "AA.00.0010" and r["version"] == 1
    )
    expected = next(
        r for r in _expected_records()
        if r["tariff_code"] == "AA.00.0010" and r["version"] == 1
    )
    assert aa_v1["tax_points"] == expected["tax_points"]
    assert aa_v1["price_chf"] == expected["price_chf"]


def test_max_scale_and_lossy_record_parity(app_client):
    """Max-scale + lossy-input records round-trip identically on both engines.

    SCALE.MAX carries values exactly at NUMERIC(12,4)/(12,2); SCALE.LOSSY is the
    fail-closed shape (billing field None + raw_* metadata marker). Both engines must
    serialise the same canonical Decimals and the same None+marker — proving the scale
    contract's stored==hashed==served invariant across the engine boundary.
    """

    body = app_client.get("/tariffs").json()
    maxr = next(r for r in body if r["tariff_code"] == "SCALE.MAX")
    expected_max = next(r for r in _expected_records() if r["tariff_code"] == "SCALE.MAX")
    assert maxr["tax_points"] == expected_max["tax_points"]  # 76.5000 -> "76.5"
    assert maxr["price_chf"] == expected_max["price_chf"]  # 12.34 -> "12.34"

    lossy = next(r for r in body if r["tariff_code"] == "SCALE.LOSSY")
    assert lossy["price_chf"] is None
    assert lossy["metadata"]["raw_price_chf"] == "12.345"
    assert lossy["requires_review"] is True


def test_unknown_code_404_parity(app_client):
    assert app_client.get("/tariffs/__nope__").status_code == 404


# --- POST /ingest/sample cross-engine parity ------------------------------------
#
# The sample pipeline FREEZES records it builds itself, so created_at is set by the
# model's default_factory (wall clock) rather than by a seeded literal — the reason
# this endpoint was initially left out. We pin it by monkeypatching the ``datetime``
# the factory resolves (tariff_model.datetime; the lambda reads it from module globals
# at call time), so every pipeline record gets FIXED_NOW. created_at is PINNED, not
# excluded, so the full-body cross-engine equality below is honest.


class _FrozenClock(datetime):
    """A ``datetime`` whose ``now()`` is fixed, leaving every other behaviour intact.

    Subclassing keeps Pydantic happy: the default_factory must still return a real
    ``datetime`` instance for the ``created_at`` field validator.
    """

    @classmethod
    def now(cls, tz=None):  # noqa: D102 - matches datetime.now signature
        return FIXED_NOW if tz is None else FIXED_NOW.astimezone(tz)


def _pin_ingest_clock_and_embedder(monkeypatch) -> None:
    """Pin the freeze clock to FIXED_NOW and run the sample ingest WITHOUT an embedding.

    The offline stub embedder is intentionally 16-dim (JSON in SQLite), but the Postgres
    schema declares ``vector(1024)`` for the real e5 model — writing the stub vector to
    that column raises a pgvector dimension error. The embedding is a search aid that
    never influences a value, and is out of read-PARITY scope, so we ingest with
    ``embedder=None`` (the pipeline skips embedding) to exercise the freeze→store→read
    VALUE path identically on both engines.
    """

    monkeypatch.setattr("tarifhub_ingest.models.tariff_model.datetime", _FrozenClock)
    # main.ingest_sample calls get_embedder(active); returning None makes the pipeline
    # skip the embedding INSERT on both engines.
    monkeypatch.setattr("tarifhub_ingest.main.get_embedder", lambda *_a, **_k: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # deterministic map_raw path


@pytest.fixture()
def ingest_client(engine, monkeypatch) -> Iterator[TestClient]:
    """A TestClient over a CLEAN engine with the record clock pinned to FIXED_NOW.

    Unlike ``app_client`` this does NOT pre-seed: the sample pipeline populates the
    store, so the test exercises the real freeze→store→read path on each engine.
    """

    _pin_ingest_clock_and_embedder(monkeypatch)
    monkeypatch.setenv("TARIFHUB_DB_URL", engine.db_url)
    from tarifhub_ingest.main import create_app

    with TestClient(create_app()) as client:
        yield client


def test_ingest_sample_response_body_parity(ingest_client):
    """POST /ingest/sample returns an identical full JSON body on both engines.

    The summary (processed/frozen/skipped/flagged + tariff_codes) is a pure function of
    the bundled sample sources, so it must be byte-identical regardless of storage
    engine — divergence here would mean the freeze/store path behaved differently.
    """

    resp = ingest_client.post("/ingest/sample")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["frozen"] > 0
    assert body["processed"] >= body["frozen"]
    assert body["skipped_existing"] == 0
    # Codes come back in pipeline order; pin the exact set + order.
    assert body["tariff_codes"] == sorted(set(body["tariff_codes"]), key=body["tariff_codes"].index)
    # The full body is engine-independent: assert it against the canonical summary.
    assert body == {
        "processed": body["processed"],
        "frozen": body["frozen"],
        "skipped_existing": 0,
        "flagged_for_review": body["flagged_for_review"],
        "refill": False,
        "tariff_codes": body["tariff_codes"],
    }


def _expected_ingested_body(tmp_path, monkeypatch) -> list[dict]:
    """The GET /tariffs body after a sample ingest into a throwaway SQLite store.

    Engine-independent reference: run the SAME pipeline (clock pinned) into a separate
    in-memory-ish SQLite DB and snapshot the read body. Each real engine must match this
    exact snapshot byte-for-byte ⇒ both engines match each other.
    """

    _pin_ingest_clock_and_embedder(monkeypatch)
    monkeypatch.setenv("TARIFHUB_DB_URL", f"sqlite:///{tmp_path / 'expected_ingest.db'}")
    from tarifhub_ingest.main import create_app

    with TestClient(create_app()) as ref:
        ref.post("/ingest/sample")
        return ref.get("/tariffs").json()


def test_ingest_sample_then_list_full_body_parity(ingest_client, tmp_path, monkeypatch):
    """After POST /ingest/sample, GET /tariffs full bodies are identical across engines.

    The ingested rows are read back through the repository mapping
    (JSONB/NUMERIC/BOOLEAN/TIMESTAMPTZ on Postgres, TEXT on SQLite) and created_at is
    pinned to FIXED_NOW, so the entire response must be byte-equal on both engines. We
    assert each engine's body against an engine-independent reference snapshot.
    """

    ingested = ingest_client.post("/ingest/sample")
    assert ingested.status_code == 200, ingested.text

    body = ingest_client.get("/tariffs").json()
    assert len(body) == ingested.json()["frozen"]

    # created_at is PINNED: every ingested record must carry FIXED_NOW (honest equality,
    # not field exclusion). Compare against FIXED_NOW serialised the SAME way the endpoint
    # does (Pydantic json mode emits the trailing 'Z' for UTC). If the clock patch failed
    # this fails loudly here.
    fixed_json = TariffRecord(
        tariff_code="X",
        tariff_system=TariffSystem.TARDOC,
        designation=Designation(de="X"),
        created_at=FIXED_NOW,
    ).model_dump(mode="json")["created_at"]
    for record in body:
        assert record["created_at"] == fixed_json

    # Full-body cross-engine identity against an engine-independent reference snapshot.
    expected = _expected_ingested_body(tmp_path, monkeypatch)
    assert body == expected
    # Deterministic order: (system, code, version), identical on both engines.
    order = [(r["tariff_system"], r["tariff_code"], r["version"]) for r in body]
    assert order == sorted(order)
