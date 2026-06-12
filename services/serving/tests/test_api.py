"""Endpoint tests for the serving API (offline: SQLite + stub embedder).

Exercises health, list (incl. system filter + pagination + latest-version), get
(incl. 404), and the search 501 path on SQLite. No network, no containers.
"""

from __future__ import annotations


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_returns_latest_version_per_key(client):
    resp = client.get("/api/v1/tariffs")
    assert resp.status_code == 200
    body = resp.json()
    # Latest version per (system, code); the AA.00.0010 v1 and PIT.0001 v1 must not appear.
    keys = {(r["tariff_system"], r["tariff_code"]) for r in body}
    assert keys == {
        ("TARDOC", "AA.00.0010"),
        ("TARDOC", "BB.00.0020"),
        ("TARDOC", "PIT.0001"),
        ("EAL", "1234.00"),
        ("EAL", "PIT.NULLFROM"),
    }
    aa = next(r for r in body if r["tariff_code"] == "AA.00.0010")
    assert aa["version"] == 2
    assert aa["designation"]["de"] == "Grundkonsultation (rev)"
    # PIT.0001 latest is v2 (no as_of filter -> highest version).
    pit = next(r for r in body if r["tariff_code"] == "PIT.0001")
    assert pit["version"] == 2


def test_list_is_deterministically_ordered(client):
    body = client.get("/api/v1/tariffs").json()
    ordered = sorted(body, key=lambda r: (r["tariff_system"], r["tariff_code"]))
    assert body == ordered


def test_list_filters_by_system(client):
    resp = client.get("/api/v1/tariffs", params={"system": "TARDOC"})
    assert resp.status_code == 200
    body = resp.json()
    assert {r["tariff_system"] for r in body} == {"TARDOC"}
    # TARDOC latest keys: AA.00.0010, BB.00.0020, PIT.0001.
    assert {r["tariff_code"] for r in body} == {"AA.00.0010", "BB.00.0020", "PIT.0001"}


def test_list_pagination_limit_and_offset(client):
    page1 = client.get("/api/v1/tariffs", params={"limit": 1, "offset": 0}).json()
    page2 = client.get("/api/v1/tariffs", params={"limit": 1, "offset": 1}).json()
    assert len(page1) == 1 and len(page2) == 1
    assert page1[0]["tariff_code"] != page2[0]["tariff_code"]


def test_list_rejects_out_of_range_limit(client):
    assert client.get("/api/v1/tariffs", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/tariffs", params={"limit": 100000}).status_code == 422


def test_get_returns_latest_record(client):
    resp = client.get("/api/v1/tariffs/TARDOC/AA.00.0010")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 2
    # tax_points is normalised to the scale-canonical (engine-independent) form on read,
    # matching the integrity-hash form: 10.10 -> "10.1" (see repository._text_to_decimal).
    assert body["tax_points"] == "10.1"
    assert body["record_hash"]


def test_get_unknown_returns_404(client):
    resp = client.get("/api/v1/tariffs/TARDOC/DOES.NOT.EXIST")
    assert resp.status_code == 404
    assert "no frozen record" in resp.json()["detail"]


def test_search_on_sqlite_returns_ranked_results(client):
    """SQLite now ranks in-process (approved change from the old 501 contract).

    The deterministic offline fallback computes cosine similarity in pure Python over
    stored stub embeddings and returns ranked SearchHit items — no fake values, the
    records are unaltered frozen rows.
    """

    resp = client.get("/api/v1/search", params={"q": "Glukose", "limit": 5})
    assert resp.status_code == 200
    hits = resp.json()
    assert hits, "offline fallback must return ranked hits, not 501"
    # Ranks are 1..n and strictly increasing (deterministic ordering contract).
    assert [h["rank"] for h in hits] == list(range(1, len(hits) + 1))
    # Every hit wraps an unaltered frozen record (has a record_hash, latest version).
    for h in hits:
        assert h["record"]["record_hash"]


def test_search_offline_ranks_matching_designation_first(client):
    """A query equal to the passage text of a seeded record ranks that record first.

    The stub embedder is a pure hash of the text; an identical query/passage text gives
    cosine 1.0, which must out-rank every other record. EAL/1234.00's passage is
    ``"EAL 1234.00 Blutzucker (Glukose)"`` — querying that exact string pins rank 1.
    """

    passage = "EAL 1234.00 Blutzucker (Glukose)"
    hits = client.get("/api/v1/search", params={"q": passage, "limit": 5}).json()
    assert hits[0]["record"]["tariff_system"] == "EAL"
    assert hits[0]["record"]["tariff_code"] == "1234.00"


def test_search_offline_respects_limit(client):
    hits = client.get("/api/v1/search", params={"q": "Konsultation", "limit": 2}).json()
    assert len(hits) == 2


def test_search_offline_is_deterministic(client):
    a = client.get("/api/v1/search", params={"q": "Position", "limit": 5}).json()
    b = client.get("/api/v1/search", params={"q": "Position", "limit": 5}).json()
    assert a == b


def test_search_offline_excludes_rows_without_embeddings(no_embedding_client):
    """Records stored without an embedding are not candidates for the offline ranker."""

    hits = no_embedding_client.get("/api/v1/search", params={"q": "Glukose", "limit": 5}).json()
    assert hits == []


def test_search_offline_empty_db_returns_empty(empty_client):
    hits = empty_client.get("/api/v1/search", params={"q": "anything", "limit": 5}).json()
    assert hits == []


def test_search_requires_query(client):
    # Empty/missing q fails input validation before reaching the 501 path.
    assert client.get("/api/v1/search", params={"q": ""}).status_code == 422
    assert client.get("/api/v1/search").status_code == 422


def test_search_guards_embedding_dimension_mismatch(monkeypatch):
    """On Postgres, a non-1024-dim embedder must 501 BEFORE any SQL is issued.

    No Postgres is needed: the repository dependency is overridden with a stub that
    raises if touched, proving the dimension guard short-circuits ahead of the query.
    The offline stub embedder produces 16 dims, so the 1024 guard fires.
    """

    from fastapi.testclient import TestClient

    from tarifhub_serving.main import app, get_repository

    monkeypatch.setenv("TARIFHUB_DB_URL", "postgresql://u:p@localhost:5432/tarifhub")

    class _ExplodingRepo:
        def search_by_embedding(self, *_a, **_k):  # pragma: no cover - must not run
            raise AssertionError("SQL must not be issued when the dimension guard fires")

    app.dependency_overrides[get_repository] = lambda: _ExplodingRepo()
    try:
        resp = TestClient(app).get("/api/v1/search", params={"q": "glucose", "limit": 3})
    finally:
        app.dependency_overrides.pop(get_repository, None)

    assert resp.status_code == 501
    detail = resp.json()["detail"]
    assert "1024-dim embedder (multilingual-e5)" in detail
    assert "16 dims" in detail


def test_list_on_empty_db_is_empty(empty_client):
    resp = empty_client.get("/api/v1/tariffs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_search_embeds_query_via_query_path(monkeypatch):
    """The search endpoint must embed the user query through ``embed_query`` (e5
    'query: ' prefix), NOT the passage-side ``embed``. A spy embedder records which
    method the endpoint calls; we run on Postgres so the embed step is reached, and
    stop SQL with a 1024-dim spy that returns a real-width vector through a stub repo.
    """

    from fastapi.testclient import TestClient

    import tarifhub_serving.main as serving_main
    from tarifhub_serving.main import app, get_repository

    monkeypatch.setenv("TARIFHUB_DB_URL", "postgresql://u:p@localhost:5432/tarifhub")

    calls: list[str] = []

    class _SpyEmbedder:
        @property
        def dimension(self) -> int:
            return 1024

        def embed(self, text: str):  # pragma: no cover - must NOT be called
            calls.append("embed")
            return [0.0] * 1024

        def embed_query(self, text: str):
            calls.append("embed_query")
            return [0.0] * 1024

    class _StubRepo:
        def search_by_embedding(self, vector, limit):
            assert len(vector) == 1024
            return []

    monkeypatch.setattr(serving_main, "get_embedder", lambda: _SpyEmbedder())
    app.dependency_overrides[get_repository] = lambda: _StubRepo()
    try:
        resp = TestClient(app).get("/api/v1/search", params={"q": "hématocrite", "limit": 5})
    finally:
        app.dependency_overrides.pop(get_repository, None)

    assert resp.status_code == 200
    assert calls == ["embed_query"], "endpoint must use the query path, not the passage path"


# --- Feature 1: point-in-time reads (?as_of=) -----------------------------------


def test_list_as_of_historical_window_returns_old_version(client):
    """as_of inside PIT.0001 v1's window (2022) returns v1, not the latest v2."""

    body = client.get("/api/v1/tariffs", params={"as_of": "2022-06-01"}).json()
    pit = next(r for r in body if r["tariff_code"] == "PIT.0001")
    assert pit["version"] == 1
    assert pit["designation"]["de"] == "Periodenposition alt"


def test_list_as_of_future_returns_current_version(client):
    """as_of in 2024 falls in PIT.0001 v2's open-ended window -> v2."""

    body = client.get("/api/v1/tariffs", params={"as_of": "2024-06-01"}).json()
    pit = next(r for r in body if r["tariff_code"] == "PIT.0001")
    assert pit["version"] == 2
    assert pit["designation"]["de"] == "Periodenposition neu"


def test_list_as_of_gap_date_excludes_record(client):
    """A date before any PIT.0001 window (2021) matches no version of that key."""

    body = client.get("/api/v1/tariffs", params={"as_of": "2021-06-01"}).json()
    assert not any(r["tariff_code"] == "PIT.0001" for r in body)


def test_list_as_of_null_valid_from_is_beginning_of_time(client):
    """PIT.NULLFROM (valid_from NULL, valid_to 2022-06-30) matches an early as_of."""

    early = client.get("/api/v1/tariffs", params={"as_of": "2019-01-01"}).json()
    assert any(r["tariff_code"] == "PIT.NULLFROM" for r in early)
    # After its valid_to it drops out.
    later = client.get("/api/v1/tariffs", params={"as_of": "2023-01-01"}).json()
    assert not any(r["tariff_code"] == "PIT.NULLFROM" for r in later)


def test_list_as_of_with_system_filter(client):
    body = client.get(
        "/api/v1/tariffs", params={"as_of": "2022-06-01", "system": "TARDOC"}
    ).json()
    assert {r["tariff_system"] for r in body} == {"TARDOC"}
    pit = next(r for r in body if r["tariff_code"] == "PIT.0001")
    assert pit["version"] == 1


def test_list_as_of_invalid_date_returns_422(client):
    assert client.get("/api/v1/tariffs", params={"as_of": "not-a-date"}).status_code == 422


def test_get_as_of_returns_versioned_record(client):
    hist = client.get("/api/v1/tariffs/TARDOC/PIT.0001", params={"as_of": "2022-06-01"})
    assert hist.status_code == 200
    assert hist.json()["version"] == 1

    cur = client.get("/api/v1/tariffs/TARDOC/PIT.0001", params={"as_of": "2024-06-01"})
    assert cur.status_code == 200
    assert cur.json()["version"] == 2


def test_get_as_of_gap_date_returns_404(client):
    resp = client.get("/api/v1/tariffs/TARDOC/PIT.0001", params={"as_of": "2021-06-01"})
    assert resp.status_code == 404


def test_get_as_of_invalid_date_returns_422(client):
    resp = client.get("/api/v1/tariffs/TARDOC/PIT.0001", params={"as_of": "13-13-13"})
    assert resp.status_code == 422


def test_list_without_as_of_unchanged(client):
    """Without as_of the list body is byte-identical to the default (latest) behavior."""

    a = client.get("/api/v1/tariffs").json()
    b = client.get("/api/v1/tariffs", params={"limit": 100, "offset": 0}).json()
    assert a == b


# --- Feature 2: version diff ----------------------------------------------------


def test_diff_v1_to_v2_lists_changed_fields(client):
    resp = client.get(
        "/api/v1/tariffs/TARDOC/AA.00.0010/diff", params={"from": 1, "to": 2}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tariff_system"] == "TARDOC"
    assert body["tariff_code"] == "AA.00.0010"
    assert body["from_version"] == 1
    assert body["to_version"] == 2
    assert body["from_record_hash"] and body["to_record_hash"]
    assert body["from_record_hash"] != body["to_record_hash"]

    changed = {c["field"]: (c["from_value"], c["to_value"]) for c in body["changes"]}
    # designation.de changed Grundkonsultation -> Grundkonsultation (rev).
    assert changed["designation.de"] == ("Grundkonsultation", "Grundkonsultation (rev)")
    # tax_points changed 9.57 -> 10.1 (canonical read form).
    assert changed["tax_points"] == ("9.57", "10.1")
    # designation.fr was unchanged -> not in the diff.
    assert "designation.fr" not in changed
    # record_hash / version / created_at are never diffed.
    assert not {"record_hash", "version", "created_at"} & set(changed)


def test_diff_changes_are_sorted_by_field_name(client):
    body = client.get(
        "/api/v1/tariffs/TARDOC/AA.00.0010/diff", params={"from": 1, "to": 2}
    ).json()
    fields = [c["field"] for c in body["changes"]]
    assert fields == sorted(fields)


def test_diff_identical_version_has_no_changes(client):
    body = client.get(
        "/api/v1/tariffs/TARDOC/AA.00.0010/diff", params={"from": 2, "to": 2}
    ).json()
    assert body["changes"] == []
    assert body["from_record_hash"] == body["to_record_hash"]


def test_diff_missing_from_version_returns_404(client):
    resp = client.get(
        "/api/v1/tariffs/TARDOC/AA.00.0010/diff", params={"from": 99, "to": 2}
    )
    assert resp.status_code == 404
    assert "99" in resp.json()["detail"]


def test_diff_missing_to_version_returns_404(client):
    resp = client.get(
        "/api/v1/tariffs/TARDOC/AA.00.0010/diff", params={"from": 1, "to": 99}
    )
    assert resp.status_code == 404
    assert "99" in resp.json()["detail"]


def test_diff_unknown_code_returns_404(client):
    resp = client.get(
        "/api/v1/tariffs/TARDOC/NOPE.NOPE/diff", params={"from": 1, "to": 2}
    )
    assert resp.status_code == 404


def test_diff_rejects_version_below_one(client):
    resp = client.get(
        "/api/v1/tariffs/TARDOC/AA.00.0010/diff", params={"from": 0, "to": 2}
    )
    assert resp.status_code == 422


def test_diff_is_deterministic(client):
    a = client.get("/api/v1/tariffs/TARDOC/AA.00.0010/diff", params={"from": 1, "to": 2}).json()
    b = client.get("/api/v1/tariffs/TARDOC/AA.00.0010/diff", params={"from": 1, "to": 2}).json()
    assert a == b


# --- Feature 4: deterministic explain -------------------------------------------


def test_explain_returns_all_versions_and_labelled_explanation(client):
    resp = client.get("/api/v1/explain", params={"code": "AA.00.0010"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "AA.00.0010"
    # All versions of every matching (system, code), ordered (system, version) asc.
    versions = [(r["tariff_system"], r["version"]) for r in body["records"]]
    assert versions == [("TARDOC", 1), ("TARDOC", 2)]
    # Explanation is deterministic, rule-generated, and labelled as such.
    assert body["explanation"].startswith("[deterministic]")
    # Grounded only in record fields (e.g. the current German designation).
    assert "Grundkonsultation (rev)" in body["explanation"]


def test_explain_with_system_filter(client):
    resp = client.get("/api/v1/explain", params={"code": "PIT.0001", "system": "TARDOC"})
    assert resp.status_code == 200
    body = resp.json()
    assert {r["tariff_system"] for r in body["records"]} == {"TARDOC"}
    assert [r["version"] for r in body["records"]] == [1, 2]


def test_explain_unknown_code_returns_404(client):
    resp = client.get("/api/v1/explain", params={"code": "ZZ.99.9999"})
    assert resp.status_code == 404


def test_explain_requires_code(client):
    assert client.get("/api/v1/explain").status_code == 422


def test_explain_is_deterministic_byte_identical(client):
    a = client.get("/api/v1/explain", params={"code": "AA.00.0010"})
    b = client.get("/api/v1/explain", params={"code": "AA.00.0010"})
    assert a.content == b.content
