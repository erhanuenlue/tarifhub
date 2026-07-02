"""Review write-back API tests via FastAPI TestClient — offline, cross-engine.

Persistence assertions run against BOTH the SQLite mirror and (when ``TARIFHUB_PG_TEST_URL``
is set) a dedicated Postgres scratch database, through the shared ``engine`` parity fixture
— the same opt-in pattern the read-parity suite uses. The human-in-the-loop write-back must
behave identically on both engines: approve/correct freezes a new immutable version, the
prior version and the audit log are never rewritten, and billing fields cannot be changed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from tarifhub_ingest.main import create_app
from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem
from tarifhub_ingest.storage.tariff_repository import TariffRepository
from tarifhub_ingest.versioning.freeze_record import freeze

_KEY = {"tariff_system": "EAL", "tariff_code": "0010.00"}


def _flagged(**overrides) -> TariffRecord:
    """A frozen, flagged EAL record with an AI-filled FR designation (fr in ai_fields)."""

    data = dict(
        tariff_code="0010.00",
        tariff_system=TariffSystem.EAL,
        designation=Designation(de="Hämatokrit", fr="Hématocrite", it=None),
        category="Hämatologie",
        tax_points=Decimal("8.50"),
        unit="point",
        valid_from=date(2026, 1, 1),
        harmonization_confidence=0.71,
        requires_review=True,
        metadata={
            "ai_assisted": True,
            "ai_model": "claude-opus-4-8",
            "ai_fields": ["designation_fr"],
        },
    )
    data.update(overrides)
    return TariffRecord(**data)


def _seed(engine, *records: TariffRecord) -> None:
    conn = engine.db.connect()
    try:
        engine.db.init_schema(conn)
        repo = TariffRepository(conn, engine.db)
        for record in records:
            repo.add(freeze(record))
    finally:
        conn.close()


def _make_client(engine, monkeypatch) -> TestClient:
    monkeypatch.setenv("TARIFHUB_DB_URL", engine.db_url)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # The 16-dim offline stub embedder does not fit Postgres' vector(1024) column, so the
    # PG leg skips embedding exactly as the read-parity suite does; SQLite stores the stub
    # as JSON text and exercises the real re-embedding write on the review path. Both
    # write seams resolve get_embedder in their OWN module namespace: the sample pipeline
    # in main.py and the review write-back in review_service.py (codex catch: patching
    # only main became a no-op for /review after the orchestration extraction).
    if engine.label == "postgres":
        monkeypatch.setattr("tarifhub_ingest.main.get_embedder", lambda *a, **k: None)
        monkeypatch.setattr("tarifhub_ingest.review_service.get_embedder", lambda *a, **k: None)
    return TestClient(create_app())


def _tariff_rows(engine) -> list[dict]:
    conn = engine.db.connect()
    try:
        cur = conn.execute(
            "SELECT tariff_code, version, requires_review, record_hash, "
            "designation_it FROM tariff ORDER BY tariff_code, version"
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _audit_event_types(engine) -> list[str]:
    conn = engine.db.connect()
    try:
        cur = conn.execute("SELECT event_type FROM audit_log ORDER BY id")
        return [dict(row)["event_type"] for row in cur.fetchall()]
    finally:
        conn.close()


def test_queue_returns_only_flagged(engine, monkeypatch):
    _seed(
        engine,
        _flagged(),
        _flagged(
            tariff_code="0020.00", requires_review=False, harmonization_confidence=0.95, metadata={}
        ),
    )
    with _make_client(engine, monkeypatch) as client:
        resp = client.get("/review/queue")

    assert resp.status_code == 200, resp.text
    queue = resp.json()
    assert [item["tariff_code"] for item in queue] == ["0010.00"]
    item = queue[0]
    assert item["tariff_system"] == "EAL"
    assert item["requires_review"] is True
    assert item["ai_model"] == "claude-opus-4-8"
    assert "harmonization_confidence 0.71 < 0.85" in item["flagged_reason"]
    fields = {f["field"]: f for f in item["fields"]}
    assert fields["designation.fr"]["aiFilled"] is True
    assert fields["designation.fr"]["raw"] is None
    assert fields["designation.fr"]["proposal"] == "Hématocrite"
    assert fields["tax_points"]["billing"] is True
    assert fields["tax_points"]["raw"] == fields["tax_points"]["proposal"]


def test_approve_creates_new_immutable_version(engine, monkeypatch):
    _seed(engine, _flagged())
    before = _tariff_rows(engine)
    assert [r["version"] for r in before] == [1]
    v1_hash = before[0]["record_hash"]

    with _make_client(engine, monkeypatch) as client:
        resp = client.post("/review", json={**_KEY, "action": "approve", "reviewer": "e.unlue"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["action"] == "approve"
    assert body["frozen"] is True
    assert body["version"] == 2
    assert body["record_hash"] and body["record_hash"] != v1_hash
    assert "v2" in body["message"]

    rows = _tariff_rows(engine)
    assert [r["version"] for r in rows] == [1, 2]
    by_version = {r["version"]: r for r in rows}
    # The prior version is immutable: same hash, still flagged.
    assert by_version[1]["record_hash"] == v1_hash
    assert bool(by_version[1]["requires_review"]) is True
    # The new version cleared the flag and carries the returned hash.
    assert bool(by_version[2]["requires_review"]) is False
    assert by_version[2]["record_hash"] == body["record_hash"]
    assert "review_approve" in _audit_event_types(engine)


def test_correct_applies_nonbilling_field_and_leaves_queue(engine, monkeypatch):
    _seed(engine, _flagged())  # designation.it is None

    with _make_client(engine, monkeypatch) as client:
        resp = client.post(
            "/review",
            json={**_KEY, "action": "correct", "corrections": {"designation.it": "Ematocrito"}},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["version"] == 2
        assert "designation.it" in body["message"]
        queue_after = client.get("/review/queue").json()

    assert queue_after == []
    by_version = {r["version"]: r for r in _tariff_rows(engine)}
    assert by_version[2]["designation_it"] == "Ematocrito"
    assert bool(by_version[2]["requires_review"]) is False
    assert "review_correct" in _audit_event_types(engine)


def test_correct_billing_field_is_rejected(engine, monkeypatch):
    _seed(engine, _flagged())

    with _make_client(engine, monkeypatch) as client:
        resp = client.post(
            "/review",
            json={**_KEY, "action": "correct", "corrections": {"tax_points": "99.99"}},
        )

    assert resp.status_code == 400
    assert "billing" in resp.json()["detail"].lower()
    rows = _tariff_rows(engine)
    assert [r["version"] for r in rows] == [1]
    assert bool(rows[0]["requires_review"]) is True


def test_correct_unknown_field_is_rejected(engine, monkeypatch):
    _seed(engine, _flagged())

    with _make_client(engine, monkeypatch) as client:
        resp = client.post(
            "/review",
            json={**_KEY, "action": "correct", "corrections": {"nonsense": "x"}},
        )

    assert resp.status_code == 400
    assert "unknown" in resp.json()["detail"].lower()


def test_review_unknown_record_is_404(engine, monkeypatch):
    _seed(engine, _flagged())

    with _make_client(engine, monkeypatch) as client:
        resp = client.post(
            "/review", json={"tariff_system": "EAL", "tariff_code": "9999.99", "action": "approve"}
        )

    assert resp.status_code == 404


def test_review_unflagged_record_is_409(engine, monkeypatch):
    _seed(engine, _flagged(requires_review=False, harmonization_confidence=0.95, metadata={}))

    with _make_client(engine, monkeypatch) as client:
        resp = client.post("/review", json={**_KEY, "action": "approve"})

    assert resp.status_code == 409


def test_review_stale_record_hash_is_409(engine, monkeypatch):
    _seed(engine, _flagged())

    with _make_client(engine, monkeypatch) as client:
        resp = client.post(
            "/review", json={**_KEY, "record_hash": "stale-hash", "action": "approve"}
        )

    assert resp.status_code == 409


def test_correct_emptying_de_fails_validation_422(engine, monkeypatch):
    _seed(engine, _flagged())

    with _make_client(engine, monkeypatch) as client:
        resp = client.post(
            "/review",
            json={**_KEY, "action": "correct", "corrections": {"designation.de": "   "}},
        )

    assert resp.status_code == 422
    assert [r["version"] for r in _tariff_rows(engine)] == [1]  # nothing persisted


def test_second_approve_is_409_and_no_third_version(engine, monkeypatch):
    _seed(engine, _flagged())

    with _make_client(engine, monkeypatch) as client:
        first = client.post("/review", json={**_KEY, "action": "approve"})
        assert first.status_code == 200, first.text
        second = client.post("/review", json={**_KEY, "action": "approve"})

    assert second.status_code == 409  # the latest version is no longer flagged
    assert [r["version"] for r in _tariff_rows(engine)] == [1, 2]


def test_correct_oversized_value_is_rejected_422(engine, monkeypatch):
    """An oversized correction value is bounded at the boundary (never reaches freeze)."""

    _seed(engine, _flagged())

    with _make_client(engine, monkeypatch) as client:
        resp = client.post(
            "/review",
            json={**_KEY, "action": "correct", "corrections": {"designation.de": "x" * 5000}},
        )

    assert resp.status_code == 422  # pydantic max_length on the correction value
    assert [r["version"] for r in _tariff_rows(engine)] == [1]  # nothing persisted
