"""Offline tests for the generation run at the provider's HTTP boundary.

The real ``anthropic`` client talks to an ``httpx.MockTransport``: no network, no key (the live
credential is removed from the environment), no cost. Expected values are worked out by hand.

    uv run --project services/ingestion --frozen --offline --extra ai --extra dev \\
        python -m pytest tools/commentary_rag -q
"""

from __future__ import annotations

import json
import threading
import sys
from pathlib import Path

import pytest

import anthropic
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generation

JUL = "2026-07-01"
PRICING = generation.Pricing(input=4.0, output=20.0, cache_write_5m=5.0, cache_write_1h=8.0,
                             cache_read=0.2, source="test", retrieved="2026-11-14")


@pytest.fixture(autouse=True)
def _no_live_credential(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


def passage(pid: str, text: str, page: int = 6, title: str = "Neugeborenen-Screening") -> dict:
    return {"passage_id": pid, "edition": JUL, "page": page, "page_label": str(page),
            "section": "2.5", "section_title": title, "text": text, "context": None,
            "document_title": "Kommentar per 01.07.26", "text_sha256": "0" * 64}


def item(case_id: str, question: str, passages: list[dict], **scoring) -> dict:
    """A case as the runner receives it; ``scoring`` fields must never reach the provider."""
    return {"case": case_id, "question": question, "editions": [JUL], "passages": passages,
            **scoring}


D = item("D", "Was gilt für 1368.00?",
         [passage("jul/p6/1", "Der Tarif der Position 1368.00 steigt auf 64.4 TP."),
          passage("jul/p7/1", "Diese Änderung tritt per 1. Juli 2026 in Kraft.", page=7)],
         reference_expectation="SECRET-REFERENCE", expected_status="SECRET-STATUS",
         evidence=[{"quote": "SECRET-GOLD-QUOTE"}])
U = item("U", "Wie hoch ist der Tarif von 1034.00?",
         [passage("jul/p8/1", "Die Analyse AFP (Position 1034.00) wird genannt.", page=8)])


def answer(*claims: tuple[str, list[str]], status: str = "answered") -> dict:
    return {"status": status, "claims": [{"text": t, "citations": c} for t, c in claims],
            "missing_evidence": []}


def message(body: dict | str, *, stop: str = "end_turn", usage=(1000, 2000), model=None) -> dict:
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    return {"id": "msg_test", "type": "message", "role": "assistant",
            "model": model or generation.MODEL, "stop_reason": stop, "stop_sequence": None,
            "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                        {"type": "text", "text": text}],
            "usage": {"input_tokens": usage[0], "output_tokens": usage[1],
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}


class Provider:
    """The provider's HTTP side: answers token counts, then replies to each Messages call."""

    def __init__(self, *replies, input_tokens: int = 1000) -> None:
        self.replies = list(replies)
        self.input_tokens = input_tokens
        self.counts: list[dict] = []
        self.creates: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Answer one request the client sends."""
        body = json.loads(request.content)
        if request.url.path == "/v1/messages/count_tokens":
            self.counts.append(body)
            return httpx.Response(200, json={"input_tokens": self.input_tokens})
        assert request.url.path == "/v1/messages"
        self.creates.append(body)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, httpx.Response):
            return reply
        return httpx.Response(200, json=reply, headers={"request-id": "req_test"})

    def client(self) -> anthropic.Anthropic:
        """The pilot's client, wired to this provider instead of the network."""
        transport = httpx.MockTransport(self)
        return generation.client("test-key", generation.Config(),
                                 http_client=httpx.Client(transport=transport))


def run(provider: Provider, items: list[dict], tmp_path: Path, **config) -> dict:
    return generation.run(items, client=provider.client(), config=generation.Config(**config),
                          pricing=PRICING, ledger=tmp_path / "ledger.jsonl")


def test_each_request_carries_only_its_own_question_and_passages_and_no_tools(tmp_path):
    provider = Provider(message(answer(("Der Tarif steigt auf 64.4 TP.", ["jul/p6/1"]))),
                        message(answer(status="insufficient_evidence")))

    result = run(provider, [D, U], tmp_path)

    first, second = (json.dumps(body, ensure_ascii=False) for body in provider.creates)
    assert "Was gilt für 1368.00?" in first and "jul/p6/1" in first and "jul/p7/1" in first
    assert "1034.00" not in first and "jul/p8/1" not in first
    assert "1034.00" in second and "jul/p6/1" not in second and "1368.00" not in second
    for leaked in ("SECRET-REFERENCE", "SECRET-STATUS", "SECRET-GOLD-QUOTE"):
        assert leaked not in first + second
    body = provider.creates[0]
    assert body["model"] == "claude-opus-5-5"
    assert body["max_tokens"] == 32_000
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"]["effort"] == "max"
    assert body["output_config"]["format"]["type"] == "json_schema"
    for absent in ("tools", "tool_choice", "mcp_servers", "fallbacks", "temperature", "top_p",
                   "top_k", "stop_sequences", "metadata", "speed", "inference_geo"):
        assert absent not in body
    assert "untrusted" in body["system"]
    # The token count is taken on the very request that is then sent.
    assert provider.counts[0] == {k: v for k, v in body.items() if k != "max_tokens"}
    # 1000 input and 2000 output tokens at $4 / $20 per MTok = 0.004 + 0.040.
    d, u = result["attempts"]
    assert (d["case"], d["outcome"], d["status"], d["cost_usd"]) == ("D", "valid", "answered", 0.044)
    assert (d["citations_outside_context"], d["returned_model"]) == ([], "claude-opus-5-5")
    assert (u["case"], u["outcome"], u["status"]) == ("U", "valid", "insufficient_evidence")
    assert result["stopped"] is None


X = item("X", "Welche Positionen werden gekürzt?",
         [passage("jul/p5/1", "Vitamin D 1006.00 20", page=5, title="Tarifanpassung")])


def test_invalid_answers_are_kept_as_failures_and_retried_only_within_the_attempt_cap(tmp_path):
    provider = Provider(
        message(answer(("Der Tarif steigt.", ["jul/p6/1", "jul/p9/9"]))),  # D: outside citation
        message("Kein JSON"),                                                 # U: not JSON
        message('{"status": "answ', stop="max_tokens"),                      # X: cut off
        message(answer(status="insufficient_evidence")),                     # U, second attempt
    )

    result = run(provider, [D, U, X], tmp_path, max_attempts=4)

    assert len(provider.creates) == 4
    assert [(a["attempt"], a["outcome"], a["status"]) for a in result["attempts"]] == [
        ("D-1", "valid", "answered"),
        ("U-1", "schema_invalid", None),
        ("X-1", "stop_max_tokens", None),
        ("U-2", "valid", "insufficient_evidence"),
    ]
    # The out-of-context citation is reported, not dropped, and the answer is not re-asked.
    assert result["attempts"][0]["citations_outside_context"] == ["jul/p9/9"]
    assert result["attempts"][1]["schema_problems"][0].startswith("not JSON")
    # A cut-off answer is billed on its usage like any other response.
    assert result["attempts"][2]["cost_usd"] == 0.044
    assert result["retries_skipped"] == [{"case": "X", "reason": "attempt cap 4 reached"}]
    events = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert [e["event"] for e in events] == ["reserve", "settle"] * 4


def error(status: int, kind: str) -> httpx.Response:
    return httpx.Response(status, json={"type": "error", "error": {"type": kind, "message": kind}})


def test_provider_errors_get_one_call_each_and_a_timeout_is_charged_at_its_reservation(tmp_path):
    provider = Provider(
        error(529, "overloaded_error"),             # D: the client must not retry by itself
        httpx.ReadTimeout("read timed out"),        # U: the provider may have billed it
        message(answer(("Vitamin D wird gekürzt.", ["jul/p5/1"]))),            # X
        message(answer(("Der Tarif steigt.", ["jul/p6/1"]))),                  # D, second
        message(answer(status="insufficient_evidence")),                       # U, second
    )

    result = run(provider, [D, U, X], tmp_path)

    assert len(provider.creates) == 5  # one HTTP call per attempt
    assert [(a["attempt"], a["outcome"]) for a in result["attempts"]] == [
        ("D-1", "http_529"), ("U-1", "timeout"), ("X-1", "valid"), ("D-2", "valid"),
        ("U-2", "valid")]
    d1, u1 = result["attempts"][:2]
    assert (d1["http_status"], d1["cost_usd"], d1["cost_basis"]) == (529, 0.0, "error response")
    # Reservation: ceil(1000 x 1.1) = 1100 input tokens x $4 + 32,000 output tokens x $20,
    # per million: 0.0044 + 0.64.
    assert (u1["cost_usd"], u1["cost_basis"]) == (0.6444, "reservation (no usage reported)")
    assert result["stopped"] is None


@pytest.mark.parametrize(("reply", "outcome"), [
    (error(401, "authentication_error"), "http_401"),
    (error(404, "not_found_error"), "http_404"),
    (message(answer(status="insufficient_evidence"), model="claude-opus-5"), "model_mismatch"),
])
def test_an_access_model_or_configuration_blocker_stops_the_run(tmp_path, reply, outcome):
    provider = Provider(reply)

    result = run(provider, [D, U, X], tmp_path)

    assert len(provider.creates) == 1
    assert [(a["attempt"], a["outcome"]) for a in result["attempts"]] == [("D-1", outcome)]
    assert result["stopped"].startswith(f"D-1 {outcome}")
    assert result["not_attempted"] == [{"case": c, "reason": "run stopped"} for c in ("U", "X")]


def test_a_request_whose_ceiling_would_exceed_the_budget_is_refused_before_it_is_sent(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    earlier = [
        {"event": "reserve", "attempt": "Z-1", "case": "Z", "reserved_usd": 0.6},  # never settled
        {"event": "reserve", "attempt": "Y-1", "case": "Y", "reserved_usd": 1.0},
        {"event": "settle", "attempt": "Y-1", "case": "Y", "cost_usd": 98.9},
    ]
    ledger.write_text("".join(json.dumps(e) + "\n" for e in earlier), encoding="utf-8")
    provider = Provider()

    result = run(provider, [D], tmp_path)

    # Committed: 98.9 spent + 0.6 still reserved = 99.5; D's ceiling 0.6444 would pass 100.
    assert provider.creates == [] and len(provider.counts) == 1
    assert result["attempts"] == []
    assert result["not_attempted"] == [{
        "case": "D", "reason": "budget: 99.5000 committed + 0.6444 ceiling would exceed 100.00 USD"}]
    assert ledger.read_text(encoding="utf-8").count("\n") == 3  # nothing reserved for D


def test_a_rerun_never_repeats_a_case_that_already_has_a_valid_answer(tmp_path):
    first = Provider(message(answer(("Der Tarif steigt.", ["jul/p6/1"]))), error(529, "overloaded"))
    run(first, [D, U], tmp_path, max_attempts=2)
    second = Provider(message(answer(status="insufficient_evidence")))

    result = run(second, [D, U], tmp_path)

    assert [b["messages"][0]["content"].count("1034.00") for b in second.creates] == [2]
    assert [(a["attempt"], a["outcome"]) for a in result["attempts"]] == [("U-2", "valid")]
    assert result["not_attempted"] == [{"case": "D", "reason": "already answered validly (D-1)"}]
    assert [row["case"] for row in result["plan"]] == ["U"]


def test_a_blocker_while_counting_tokens_stops_before_any_answer_is_requested(tmp_path):
    class Refusing(Provider):
        def __call__(self, request):
            if request.url.path == "/v1/messages/count_tokens":
                return error(401, "authentication_error")
            return super().__call__(request)

    provider = Refusing()

    result = run(provider, [D, U], tmp_path)

    assert provider.creates == [] and result["attempts"] == []
    assert result["stopped"] == "count_tokens D http_401: authentication_error: authentication_error"
    assert not (tmp_path / "ledger.jsonl").exists()


def test_a_plan_counts_and_prices_every_request_but_sends_none(tmp_path):
    provider = Provider(input_tokens=2000)

    result = generation.run([D, U], client=provider.client(), config=generation.Config(),
                            pricing=PRICING, ledger=tmp_path / "ledger.jsonl", plan_only=True)

    assert provider.creates == [] and len(provider.counts) == 2
    # ceil(2000 x 1.1) = 2200 x $4 + 32,000 x $20, per million: 0.0088 + 0.64.
    assert [(row["case"], row["input_tokens"], row["ceiling_usd"]) for row in result["plan"]] == [
        ("D", 2000, 0.6488), ("U", 2000, 0.6488)]
    assert result["attempts"] == [] and not (tmp_path / "ledger.jsonl").exists()


def test_a_configured_workspace_is_sent_as_a_header_on_every_request(tmp_path):
    seen: list[str | None] = []
    provider = Provider(message(answer(status="insufficient_evidence")))

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("anthropic-workspace-id"))
        return provider(request)

    scoped = generation.client("test-key", generation.Config(), workspace_id="wrkspc_test",
                               http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    unscoped = generation.client("test-key", generation.Config(),
                                 http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    generation.run([U], client=scoped, config=generation.Config(), pricing=PRICING,
                   ledger=tmp_path / "ledger.jsonl")
    unscoped.messages.count_tokens(model=generation.MODEL,
                                   messages=[{"role": "user", "content": "x"}])

    assert seen == ["wrkspc_test", "wrkspc_test", None]  # count, create; then without


def test_a_valid_answer_is_settled_only_after_its_response_is_saved(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    blocked = tmp_path / "artifacts"
    blocked.write_text("a file, not a folder", encoding="utf-8")  # saving the response fails
    first = Provider(message(answer(("Der Tarif steigt.", ["jul/p6/1"]))))

    with pytest.raises(OSError):
        generation.run([D], client=first.client(), config=generation.Config(), pricing=PRICING,
                       ledger=ledger, artifacts=blocked)

    # Not settled, so still reserved and counted, and not taken for answered on the next run.
    assert [json.loads(line)["event"] for line in ledger.read_text().splitlines()] == ["reserve"]
    assert generation.committed_usd(ledger) == 0.6444
    second = Provider(message(answer(("Der Tarif steigt.", ["jul/p6/1"]))))
    result = generation.run([D], client=second.client(), config=generation.Config(),
                            pricing=PRICING, ledger=ledger, artifacts=tmp_path / "saved")
    assert [(a["attempt"], a["outcome"]) for a in result["attempts"]] == [("D-2", "valid")]
    assert (tmp_path / "saved" / "responses" / "D-2.json").exists()


def test_a_second_run_on_the_same_ledger_is_refused_while_the_first_is_sending(tmp_path):
    entered, release = threading.Event(), threading.Event()

    class Slow(Provider):
        def __call__(self, request):
            if request.url.path == "/v1/messages":
                entered.set()
                release.wait(10)
            return super().__call__(request)

    ledger = tmp_path / "ledger.jsonl"
    first = Slow(message(answer(("Der Tarif steigt.", ["jul/p6/1"]))))
    second = Provider(message(answer(status="insufficient_evidence")))
    done: dict = {}
    worker = threading.Thread(target=lambda: done.update(result=generation.run(
        [D], client=first.client(), config=generation.Config(), pricing=PRICING, ledger=ledger)))
    worker.start()
    assert entered.wait(10)
    try:
        result = generation.run([U], client=second.client(), config=generation.Config(),
                                pricing=PRICING, ledger=ledger)
    finally:
        release.set()
        worker.join(10)

    # Checking the cap and budget and reserving must not interleave with another run's.
    assert second.counts == [] and second.creates == [] and result["attempts"] == []
    assert result["stopped"].startswith("another run")
    assert [a["attempt"] for a in done["result"]["attempts"]] == ["D-1"]


def test_public_diagnostics_never_carry_a_credential_or_generated_text(tmp_path):
    echoed = "key sk-ant-api03-SECRETKEY0123456789 in workspace wrkspc_01SECRETSPACE is not allowed"
    refused = Provider(httpx.Response(403, json={
        "type": "error", "error": {"type": "permission_error", "message": echoed}}))
    rambling = Provider(message({"status": "Die Antwort lautet " + "x" * 200, "claims": [],
                                 "missing_evidence": []}))

    stopped = run(refused, [D], tmp_path / "a")
    invalid = run(rambling, [U], tmp_path / "b")

    public = json.dumps([stopped, invalid]) + "".join(
        (tmp_path / part / "ledger.jsonl").read_text() for part in ("a", "b"))
    for secret in ("SECRETKEY", "SECRETSPACE", "Die Antwort"):
        assert secret not in public
    assert stopped["stopped"].startswith("D-1 http_403: permission_error:")
    assert invalid["attempts"][0]["outcome"] == "schema_invalid"
