"""Offline tests for the evidence-seeking agent's single-case loop, at the provider boundary.

The real ``anthropic`` client talks to an ``httpx.MockTransport`` with a fake key and no network;
the live credential variables are removed for every test. The commentary search is the real S1
tool over the synthetic two-edition corpus of ``test_evidence_search`` (its July hybrid order
is k c h b a f l d e g i j, worked out there by hand). Time is a stand-in monotonic clock that
the provider stand-in and the e5 stand-in advance, so deadlines can be tested exactly. Spending
is accounted in temporary ledgers and artifact folders: a stand-in historical ledger and an
active ledger beside it; the repository's own ledger is only ever read.

Worked prices (the rates of ``pricing.json``, USD per million tokens: input 4, cache writes 5 for
five minutes and 8 for an hour, cache reads 0.2, output 20; the US data-residency multiplier 1.1).
The agent's ceiling prices the margin's input at the dearest input rate, 8, adds the full output
allowance and applies the multiplier, rounded up to a micro-dollar: a request counted at 1,500
tokens reserves (ceil(1,500 x 1.10) = 1,650 x 8 + 32,000 x 20) x 1.1 / 1e6 = 0.71852 USD; one at
the 80,000-token cap (88,000 x 8 + 640,000) x 1.1 / 1e6 = 1.4784 USD, so a case is admitted
against three of those, 4.4352 USD. A response using 1,500 input and 900 output tokens, without
US inference, costs (1,500 x 4 + 900 x 20) / 1e6 = 0.024 USD.
"""

from __future__ import annotations

import dataclasses
import errno
import hashlib
import json
import re
import sys
import threading
from pathlib import Path

import anthropic
import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import evidence_agent
import generation
from test_evidence_search import JAN, JUL, world

TOOL = "search_commentary"
INITIAL = ("jul/k", "jul/h", "jul/a", "jul/l", "jul/i")
# A stand-in historical ledger: one settled request and one reservation never settled.
HISTORY = ({"event": "reserve", "attempt": "H-1", "case": "H", "reserved_usd": 2.0},
           {"event": "settle", "attempt": "H-1", "case": "H", "cost_usd": 1.5},
           {"event": "reserve", "attempt": "H-2", "case": "H", "reserved_usd": 0.6})


@pytest.fixture(autouse=True)
def _no_live_credential(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture(autouse=True)
def folder(tmp_path, monkeypatch) -> Path:
    """The books' folder: the agent accepts no other, so every test moves it somewhere temporary
    (the recorded ledger in ``results/`` is never written). The historical ledger's pinned hash
    is restored after every test; only ``books`` replaces it, for a stand-in history."""

    monkeypatch.setattr(evidence_agent, "BOOKS", tmp_path / "books")
    monkeypatch.setattr(evidence_agent, "HISTORICAL_SHA256", evidence_agent.HISTORICAL_SHA256)
    return tmp_path / "books"


def books(history=()) -> evidence_agent.Spending:
    """A stand-in historical ledger holding ``history``, pinned in the agent's place of the
    recorded one for this test, and the active ledger beside it, not yet begun."""

    folder = evidence_agent.BOOKS
    folder.mkdir(parents=True, exist_ok=True)
    baseline = folder / evidence_agent.HISTORICAL_LEDGER
    baseline.write_text("".join(json.dumps(e) + "\n" for e in history), encoding="utf-8")
    evidence_agent.HISTORICAL_SHA256 = _sha(baseline.read_bytes())  # restored by ``folder``
    return evidence_agent.Spending(ledger=folder / evidence_agent.ACTIVE_LEDGER, baseline=baseline,
                                   baseline_sha256=evidence_agent.HISTORICAL_SHA256,
                                   artifacts=folder.parent / "artifacts")


@pytest.fixture
def spending(folder) -> evidence_agent.Spending:
    return books()


def events(spending: evidence_agent.Spending) -> list[dict]:
    """The active ledger's events, oldest first."""

    return [json.loads(line) for line in spending.ledger.read_text("utf-8").splitlines()]


class Clock:
    """A monotonic stand-in clock that only moves when a test lets time pass."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        """The current reading, in seconds."""
        return self.now

    def advance(self, seconds: float) -> None:
        """Let ``seconds`` pass."""
        self.now += seconds


class Provider:
    """The provider's HTTP side: token counts, then one scripted reply per Messages call.

    A reply is a message dict, an ``httpx.Response`` or an exception; ``(seconds, reply)`` lets
    that much time pass before it is given. ``count_seconds`` passes on every token count.
    """

    def __init__(self, clock: Clock, *replies, count_seconds: float = 0.0,
                 count_reply=None, on_create=None) -> None:
        self.clock = clock
        self.on_create = on_create  # something that happens while a request is being answered
        self.replies = list(replies)
        self.count_seconds = count_seconds
        self.count_reply = count_reply  # a response or exception instead of a token count
        self.counts: list[dict] = []
        self.creates: list[dict] = []
        self.timeouts: list[tuple[str, float]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Answer one request the client sends, noting its timeout."""
        body = json.loads(request.content)
        self.timeouts.append((request.url.path, request.extensions["timeout"]["read"]))
        if request.url.path == "/v1/messages/count_tokens":
            self.counts.append(body)
            self.clock.advance(self.count_seconds)
            if isinstance(self.count_reply, Exception):
                raise self.count_reply
            return self.count_reply or httpx.Response(200, json={"input_tokens": 1500})
        assert request.url.path == "/v1/messages"
        self.creates.append(body)
        if self.on_create:
            self.on_create()
        reply = self.replies.pop(0)
        if isinstance(reply, tuple):
            seconds, reply = reply
            self.clock.advance(seconds)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, httpx.Response):
            return reply
        return httpx.Response(200, json=reply, headers={"request-id": "req_test"})

    def client(self):
        """The pilot's client with a fake key, wired to this provider instead of the network."""
        transport = httpx.MockTransport(self)
        return generation.client("test-key", generation.Config(),
                                 http_client=httpx.Client(transport=transport))


def _message(content: list[dict], stop: str) -> dict:
    return {"id": "msg_test", "type": "message", "role": "assistant",
            "model": generation.MODEL, "stop_reason": stop, "stop_sequence": None,
            "content": content,
            "usage": {"input_tokens": 1500, "output_tokens": 900,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                      # part of output_tokens, which is the billed total
                      "output_tokens_details": {"thinking_tokens": 600}}}


def search_call(query: str, seeking: str, *, tool_id: str = "toolu_1", name: str = TOOL,  # noqa: PLR0913 - keyword-only message builder
                editions: list[str] | None = None, stop: str = "tool_use") -> dict:
    arguments = {"query": query, "seeking": seeking}
    if editions is not None:
        arguments["editions"] = editions
    return _message([{"type": "thinking", "thinking": "", "signature": f"sig-{tool_id}"},
                     {"type": "tool_use", "id": tool_id, "name": name, "input": arguments}],
                    stop)


def final(*claims: tuple[str, list[str]], status: str = "answered", missing=()) -> dict:
    answer = {"status": status, "claims": [{"text": t, "citations": c} for t, c in claims],
              "missing_evidence": list(missing)}
    return _message([{"type": "thinking", "thinking": "", "signature": "sig-final"},
                     {"type": "text", "text": json.dumps(answer, ensure_ascii=False)}],
                    "end_turn")


def task(initial=INITIAL, editions=(JUL,), question="Welche Pauschale gilt und warum?"):
    _, passages, _ = world()
    return evidence_agent.AgentTask(case_id="T1", question=question, editions=editions,
                                    passages=tuple(passages[pid] for pid in initial))


def run(provider: Provider, the_task, spending: evidence_agent.Spending, *,  # noqa: PLR0913
        budget_s: float = 3600.0, config: generation.Config | None = None,
        condition: str | None = None, **world_options):
    retriever, passages, embedder = world(**world_options)
    chosen = {} if condition is None else {"condition": condition}  # None: the default, agent
    result = evidence_agent.run_case(the_task, client=provider.client(), retriever=retriever,
                                     passages=passages, clock=provider.clock, budget_s=budget_s,
                                     spending=spending, config=config, **chosen)
    return result, embedder


def test_every_call_is_reserved_before_it_is_sent_and_settled_once_beside_the_history():
    spending = books(HISTORY)
    provider = Provider(Clock(), search_call("Pauschale", "Begründung der Pauschale"),
                        final(("Die Pauschale ist neu begründet.", ["jul/c", "jul/k"])))

    result, _ = run(provider, task(), spending)

    assert (result.outcome, result.status) == ("answer", "answered")
    baseline, *calls = events(spending)
    # The historical ledger counts with all it committed: 1.5 spent plus 0.6 still reserved.
    assert {k: baseline[k] for k in ("event", "ledger", "sha256", "committed_usd",
                                     "budget_usd")} == {
        "event": "baseline", "ledger": "generation-ledger.jsonl",
        "sha256": spending.baseline_sha256, "committed_usd": 2.1, "budget_usd": 100.0}
    assert [(e["event"], e["attempt"]) for e in calls] == [
        ("reserve", "T1-agent-call1"), ("settle", "T1-agent-call1"), ("reserve", "T1-agent-call2"),
        ("settle", "T1-agent-call2")]
    for n, (reserve, settle) in enumerate(zip(calls[::2], calls[1::2], strict=True), start=1):
        attempt = f"T1-agent-call{n}"
        assert (reserve["case"], reserve["counted_input_tokens"], reserve["reserved_usd"]) == (
            "T1", 1500, 0.71852)
        # 900 output tokens, 600 of them thinking: the thinking is not counted again.
        assert (settle["sent"], settle["cost_usd"], settle["cost_basis"],
                settle["above_reservation"]) == (True, 0.024, "usage", False)
        request = (spending.artifacts / "requests" / f"{attempt}.json").read_bytes()
        response = (spending.artifacts / "responses" / f"{attempt}.json").read_bytes()
        assert json.loads(request) == provider.creates[n - 1]  # saved as it was sent
        assert reserve["request_sha256"] == _sha(request) == \
            result.record["calls"][n - 1]["request_sha256"]
        assert settle["response_sha256"] == _sha(response) == \
            result.record["calls"][n - 1]["response_sha256"]
    assert generation.committed_usd(spending.ledger) == 0.048
    assert result.record["spending"] == {
        "budget_usd": 100.0, "baseline_sha256": spending.baseline_sha256,
        "baseline_committed_usd": 2.1, "committed_before_usd": 2.1, "admission_usd": 4.4352}
    assert _sha(spending.baseline.read_bytes()) == spending.baseline_sha256  # only ever read


def earlier(spending: evidence_agent.Spending, committed: float, *rows: dict) -> None:
    """An active ledger already in use: its pinned baseline, then ``rows``."""

    pin = {"event": "baseline", "ledger": spending.baseline.name,
           "sha256": spending.baseline_sha256, "committed_usd": committed, "budget_usd": 100.0,
           "at": "2026-11-16T08:00:00+00:00"}
    spending.ledger.write_text("".join(json.dumps(e) + "\n" for e in (pin, *rows)), "utf-8")


def reservation(attempt: str, usd: float) -> dict:
    return {"event": "reserve", "attempt": attempt, "case": attempt.partition("-")[0], "call": 1,
            "request_sha256": "0" * 64, "counted_input_tokens": 1500, "reserved_usd": usd,
            "at": "2026-11-16T08:00:00+00:00"}


@pytest.mark.parametrize(("open_usd", "outcome"), [(35.5648, "answer"), (35.564801, "refused")],
                         ids=["exactly_the_limit", "one_microdollar_over"])
def test_a_case_is_admitted_only_when_its_worst_case_fits_beside_all_earlier_spending(
        open_usd, outcome):
    # 60 USD spent in the historical ledger and an open reservation in the active one: with the
    # case's worst case of 4.4352 USD, exactly 100 USD is admitted, a micro-dollar more is not.
    spending = books(({"event": "reserve", "attempt": "H-1", "case": "H", "reserved_usd": 60.0},
                      {"event": "settle", "attempt": "H-1", "case": "H", "cost_usd": 60.0}))
    earlier(spending, 60.0, reservation("P-call1", open_usd))
    before = spending.ledger.read_bytes()
    provider = Provider(Clock(), final(("Antwort.", ["jul/k"])))

    result, _ = run(provider, task(), spending)

    assert result.outcome == outcome
    if outcome == "refused":
        assert result.detail == "admission_budget"
        assert provider.timeouts == []  # nothing counted, nothing sent
        assert spending.ledger.read_bytes() == before
        assert not spending.artifacts.exists()
    else:
        assert result.record["spending"]["committed_before_usd"] == 95.5648
        assert [e["event"] for e in events(spending)][2:] == ["reserve", "settle"]


def test_every_call_of_a_case_admitted_at_the_limit_stays_within_the_one_shared_scope():
    spending = books(({"event": "reserve", "attempt": "H-1", "case": "H", "reserved_usd": 60.0},
                      {"event": "settle", "attempt": "H-1", "case": "H", "cost_usd": 60.0}))
    earlier(spending, 60.0, reservation("P-call1", 35.5648))
    provider = Provider(Clock(), search_call("Pauschale", "Januar", editions=[JAN]),
                        search_call("Pauschale", "Juli", tool_id="toolu_2", editions=[JUL]),
                        final(("Beide Fassungen.", ["jan/c", "jul/f"])))
    the_task = task(initial=("jul/k", "jul/h", "jul/a", "jan/a", "jan/b"), editions=(JAN, JUL))

    result, _ = run(provider, the_task, spending)

    # Admitted at exactly 100 USD: 60 + 35.5648 + 4.4352. Three calls, each reserved at 0.71852
    # and settled once at 0.024 USD.
    assert (result.outcome, result.record["generation_calls"]) == ("answer", 3)
    calls = events(spending)[2:]
    assert [(e["event"], e["attempt"], e.get("reserved_usd", e.get("cost_usd"))) for e in calls] \
        == [(event, f"T1-agent-call{n}", usd) for n in (1, 2, 3)
            for event, usd in (("reserve", 0.71852), ("settle", 0.024))]
    assert generation.committed_usd(spending.ledger) == 35.6368  # 35.5648 + 3 x 0.024
    books_before = spending.ledger.read_bytes()

    # The next case's worst case no longer fits: 60 + 35.6368 + 4.4352 = 100.072 USD.
    second = Provider(Clock(), final(("Nie gesendet.", ["jul/k"])))
    refused, _ = run(second, dataclasses.replace(task(), case_id="T2"), spending)

    assert (refused.outcome, refused.detail) == ("refused", "admission_budget")
    assert second.timeouts == []
    assert spending.ledger.read_bytes() == books_before


@pytest.mark.parametrize("counted", [80_000, 80_001], ids=["at_the_cap", "over_the_cap"])
def test_a_request_counted_over_the_input_cap_is_neither_reserved_nor_sent(spending, counted):
    provider = Provider(Clock(), final(("Antwort.", ["jul/k"])),
                        count_reply=httpx.Response(200, json={"input_tokens": counted}))

    result, _ = run(provider, task(), spending)

    if counted == 80_000:  # (88,000 x 8 + 32,000 x 20) x 1.1 / 1e6 = 1.4784 USD
        assert result.outcome == "answer"
        assert [(e["event"], e.get("reserved_usd")) for e in events(spending)] == [
            ("baseline", None), ("reserve", 1.4784), ("settle", None)]
    else:
        assert (result.outcome, result.detail) == ("refused", "input_over_limit")
        assert provider.creates == []
        assert [e["event"] for e in events(spending)] == ["baseline"]
        assert not spending.artifacts.exists()


@pytest.mark.parametrize(("reply", "outcome", "detail"), [
    ((150.0, final(("Zu spät.", ["jul/k"]))), "deadline", "after_generation"),
    (_message([{"type": "text", "text": "Die Pauschale ist neu."}], "end_turn"),
     "invalid_answer", "schema_invalid"),
    (search_call("Pauschale", "Tarif", name="read_tariff_database"),
     "protocol_error", "unknown_tool"),
], ids=["late_answer", "invalid_answer", "unknown_tool"])
def test_a_rejected_response_is_still_settled_at_the_cost_of_its_usage(
        spending, reply, outcome, detail):
    provider = Provider(Clock(), reply)

    result, _ = run(provider, task(), spending, budget_s=100.0)

    assert (result.outcome, result.detail, result.answer) == (outcome, detail, None)
    reserve, settle = events(spending)[1:]
    assert (reserve["reserved_usd"], settle["sent"], settle["cost_usd"], settle["cost_basis"]) == (
        0.71852, True, 0.024, "usage")
    assert generation.committed_usd(spending.ledger) == 0.024


def _block(path: Path) -> None:
    """A regular file where a folder is needed, so nothing can be written below it."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("kein Ordner", encoding="utf-8")


def _fail_opening(monkeypatch, target: Path, *, at: int = 1, writing: bool = True) -> None:
    """The ``at``-th opening of ``target`` for writing (or for reading) fails with an I/O error,
    as a full or failing disk would, whoever runs the tests: file permissions do not stop root."""

    real, seen = Path.open, 0

    def opening(self, mode="r", *args, **kwargs):
        nonlocal seen
        if self == target and any(c in mode for c in "wax+") == writing:
            seen += 1
            if seen == at:
                raise OSError(errno.EIO, "simulated I/O failure")
        return real(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opening)


def _files(folder: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def test_a_baseline_pin_that_cannot_be_saved_stops_the_case_before_anything_is_counted(
        spending, monkeypatch):
    kept = spending.artifacts / "requests" / "P-call1.json"  # an artifact of an earlier run
    kept.parent.mkdir(parents=True)
    kept.write_text('{"frage": "früher"}', encoding="utf-8")
    history = spending.baseline.read_bytes()
    _fail_opening(monkeypatch, spending.ledger)  # the new ledger's first line, its pin
    provider = Provider(Clock(), final(("Nie gesendet.", ["jul/k"])))

    result, _ = run(provider, task(), spending)

    assert (result.outcome, result.detail) == ("persistence_error", "baseline_not_saved")
    assert provider.timeouts == []  # nothing counted, nothing sent
    assert not spending.ledger.exists()
    assert spending.baseline.read_bytes() == history
    assert _files(spending.artifacts) == {kept: '{"frage": "früher"}'.encode()}

    # Nothing half-written is left behind: once the disk works, the same case starts cleanly.
    retried, _ = run(Provider(Clock(), final(("Antwort.", ["jul/k"]))), task(), spending)
    assert retried.outcome == "answer"
    assert [e["event"] for e in events(spending)] == ["baseline", "reserve", "settle"]


@pytest.mark.parametrize(("failure", "detail", "sent", "books"), [
    ("requests", "request_not_saved", 0, ["baseline"]),
    ("ledger_before", "reservation_not_saved", 0, ["baseline"]),
    ("responses", "response_not_saved", 1, ["baseline", "reserve"]),
    ("ledger_during", "settlement_not_saved", 1, ["baseline", "reserve"]),
], ids=["request_not_saved", "reservation_not_saved", "response_not_saved",
        "settlement_not_saved"])
def test_a_failed_write_stops_the_case_and_a_sent_call_stays_reserved(  # noqa: PLR0913 - parameters
        spending, failure, detail, sent, books, monkeypatch):
    earlier(spending, 0.0)
    if failure in ("requests", "responses"):
        _block(spending.artifacts / failure)
    elif failure.startswith("ledger"):  # the reservation is the first line written, then its
        _fail_opening(monkeypatch, spending.ledger,  # settlement
                      at=1 if failure == "ledger_before" else 2)
    provider = Provider(Clock(), search_call("Pauschale", "Begründung"),
                        final(("Nie gesendet.", ["jul/k"])))

    result, embedder = run(provider, task(), spending)

    assert (result.outcome, result.detail, result.answer) == ("persistence_error", detail, None)
    assert len(provider.creates) == sent and embedder.queries == []
    assert [e["event"] for e in events(spending)] == books
    # Never sent: nothing committed. Sent but not settled: the whole ceiling stays committed,
    # and the record claims no settlement the ledger does not hold.
    assert generation.committed_usd(spending.ledger) == (0.71852 if sent else 0.0)
    assert [c.get("cost_basis") for c in result.record["calls"]] == [None] * sent
    requests = spending.artifacts / "requests" / "T1-agent-call1.json"
    assert requests.exists() == (failure != "requests")
    if failure == "ledger_during":  # the raw response was saved before settling failed
        assert (spending.artifacts / "responses" / "T1-agent-call1.json").exists()
    assert str(spending.artifacts) not in json.dumps(result.record)


@pytest.mark.parametrize("reached", ["by_the_same_path", "through_a_symlink_elsewhere"])
def test_a_second_invocation_is_refused_while_the_first_holds_the_books(spending, tmp_path,
                                                                        reached):
    theirs = spending
    if reached == "through_a_symlink_elsewhere":  # the same active ledger, from another folder
        alias = tmp_path / "elsewhere" / evidence_agent.ACTIVE_LEDGER
        alias.parent.mkdir()
        alias.symlink_to(spending.ledger)
        theirs = dataclasses.replace(spending, ledger=alias)
    entered, release = threading.Event(), threading.Event()

    def held() -> None:
        entered.set()
        release.wait(10)

    first = Provider(Clock(), final(("Antwort.", ["jul/k"])), on_create=held)
    second = Provider(Clock(), final(("Antwort.", ["jul/k"])))
    done: dict = {}
    worker = threading.Thread(target=lambda: done.update(result=run(first, task(), spending)[0]))
    worker.start()
    assert entered.wait(10)
    try:
        other = dataclasses.replace(task(), case_id="T2")
        result, _ = run(second, other, theirs)
    finally:
        release.set()
        worker.join(10)

    # Admission, reservation and settlement never interleave with another invocation's.
    assert (result.outcome, result.detail) == ("refused", "locked")
    assert second.timeouts == []
    assert not (spending.artifacts / "requests" / "T2-agent-call1.json").exists()
    assert done["result"].outcome == "answer"
    assert [e.get("case") for e in events(spending)] == [None, "T1", "T1"]


@pytest.mark.parametrize("first_ended", ["answer", "response_not_saved"])
def test_a_repeated_invocation_neither_resends_nor_recounts_a_case_already_in_the_books(
        spending, first_ended):
    if first_ended == "response_not_saved":  # sent, never settled: financially unresolved
        _block(spending.artifacts / "responses")
    first, _ = run(Provider(Clock(), final(("Antwort.", ["jul/k"]))), task(), spending)
    assert first.detail == (None if first_ended == "answer" else first_ended)
    books_before = spending.ledger.read_bytes()
    artifacts_before = {p: p.read_bytes() for p in spending.artifacts.rglob("*") if p.is_file()}
    again = Provider(Clock(), final(("Antwort.", ["jul/k"])))

    result, _ = run(again, task(), spending)

    assert (result.outcome, result.detail) == ("refused", "already_run")
    assert again.timeouts == []
    assert spending.ledger.read_bytes() == books_before
    assert {p: p.read_bytes() for p in spending.artifacts.rglob("*") if p.is_file()} == \
        artifacts_before


# Usage as the agent saves it: 10,000 output tokens at 20 USD per million cost 0.2 USD.
SAVED_USAGE = {"input_tokens": 0, "output_tokens": 10_000, "cache_creation_input_tokens": 0,
               "cache_read_input_tokens": 0, "cache_creation_1h_input_tokens": 0,
               "us_inference": False}


def _settled(attempt: str) -> dict:
    """A call settled at the 0.2 USD its saved usage costs."""

    return {"event": "settle", "attempt": attempt, "case": attempt.partition("-")[0], "sent": True,
            "cost_usd": 0.2, "cost_basis": "usage", "above_reservation": False,
            "usage": SAVED_USAGE, "response_sha256": None, "at": "2026-11-16T08:00:00+00:00"}


def _damage(spending: evidence_agent.Spending, kind: str) -> evidence_agent.Spending:
    """Spoil the books in one way after an earlier question used them correctly."""

    earlier(spending, 0.0, reservation("P-call1", 0.5), _settled("P-call1"))
    text = spending.ledger.read_text("utf-8")
    lines = text.splitlines(keepends=True)
    if kind == "truncated":
        spending.ledger.write_text(text[:-25], "utf-8")
    elif kind == "blank_line":
        spending.ledger.write_text("".join([*lines[:2], "\n", *lines[2:]]), "utf-8")
    elif kind == "not_finite":
        spending.ledger.write_text(text.replace("0.2,", "NaN,"), "utf-8")
    elif kind == "negative":
        spending.ledger.write_text(text.replace("0.2,", "-0.2,"), "utf-8")
    elif kind == "finer_than_a_microdollar":
        spending.ledger.write_text(text.replace("0.2,", "0.2000001,"), "utf-8")
    elif kind == "reserved_twice":
        spending.ledger.write_text(text + lines[1], "utf-8")
    elif kind == "settled_twice":
        spending.ledger.write_text(text + lines[2], "utf-8")
    elif kind == "settled_unreserved":
        spending.ledger.write_text("".join([lines[0], lines[2]]), "utf-8")
    elif kind == "no_baseline_first":
        spending.ledger.write_text("".join(lines[1:]), "utf-8")
    elif kind == "not_an_object":
        spending.ledger.write_text(text + "[]\n", "utf-8")
    elif kind == "emptied":  # an existing ledger with nothing in it is not a new one
        spending.ledger.write_text("", "utf-8")
    elif kind == "retained_reservation_released":
        spending.ledger.write_text(text.replace(
            '"cost_usd": 0.2, "cost_basis": "usage"', '"cost_usd": 0.0, '
            '"cost_basis": "reservation_retained"'), "utf-8")
    elif kind == "never_sent_but_charged":
        spending.ledger.write_text(text.replace('"cost_basis": "usage"', '"cost_basis": "not_sent"'),
                                   "utf-8")
    elif kind == "unknown_basis":
        spending.ledger.write_text(text.replace('"cost_basis": "usage"', '"cost_basis": "invoice"'),
                                   "utf-8")
    elif kind == "usage_cost_lowered":  # the saved usage still costs 0.2 USD
        spending.ledger.write_text(text.replace('"cost_usd": 0.2, "cost_basis": "usage"',
                                                '"cost_usd": 0.0, "cost_basis": "usage"'), "utf-8")
    elif kind == "thinking_above_output":  # output and cost lowered together, thinking left
        spending.ledger.write_text(text.replace('"cost_usd": 0.2,', '"cost_usd": 0.0,').replace(
            json.dumps(SAVED_USAGE),
            json.dumps({**SAVED_USAGE, "output_tokens": 0, "thinking_tokens": 600})), "utf-8")
    elif kind == "usage_missing":  # priced from usage that is not there
        spending.ledger.write_text(text.replace(json.dumps(SAVED_USAGE), "null"), "utf-8")
    elif kind == "reserved_under_another_case":  # the call ID names case P, its case field Q
        spending.ledger.write_text(text.replace('"case": "P", "call": 1', '"case": "Q", "call": 1'),
                                   "utf-8")
    elif kind == "settled_under_another_case":
        spending.ledger.write_text(text.replace('"case": "P", "sent"', '"case": "Q", "sent"'),
                                   "utf-8")
    elif kind == "attempt_not_a_name":
        spending.ledger.write_text(text.replace('"attempt": "P-call1"', '"attempt": []'), "utf-8")
    elif kind == "history_changed":
        spending.baseline.write_text(json.dumps(HISTORY[0]) + "\n", "utf-8")
    elif kind == "history_unreadable":  # pinned as it now is: damaged, not changed
        spending.baseline.write_text("kaputt\n", "utf-8")
        evidence_agent.HISTORICAL_SHA256 = _sha(spending.baseline.read_bytes())
        return dataclasses.replace(spending, baseline_sha256=evidence_agent.HISTORICAL_SHA256)
    elif kind == "pinned_other_history":
        spending.ledger.write_text(text.replace(spending.baseline_sha256, "f" * 64), "utf-8")
    elif kind == "pinned_other_limit":
        spending.ledger.write_text(text.replace('"budget_usd": 100.0', '"budget_usd": 200.0'),
                                   "utf-8")
    elif kind == "pinned_other_amount":
        spending.ledger.write_text(text.replace('"committed_usd": 0.0', '"committed_usd": 1.0'),
                                   "utf-8")
    return spending


DAMAGE = ["truncated", "blank_line", "not_finite", "negative", "finer_than_a_microdollar",
          "reserved_twice", "settled_twice", "settled_unreserved", "no_baseline_first",
          "not_an_object", "attempt_not_a_name", "usage_cost_lowered", "thinking_above_output",
          "usage_missing",
          "reserved_under_another_case",
          "settled_under_another_case", "emptied", "retained_reservation_released",
          "never_sent_but_charged", "unknown_basis", "history_unreadable"]
DRIFT = ["history_changed", "pinned_other_history", "pinned_other_amount"]


@pytest.mark.parametrize("kind", [*DAMAGE, *DRIFT, "pinned_other_limit", "unreadable"])
def test_damaged_or_changed_books_are_refused_as_they_are_and_nothing_is_sent(
        spending, kind, monkeypatch):
    spending = _damage(spending, kind)
    books_before, history_before = spending.ledger.read_bytes(), spending.baseline.read_bytes()
    provider = Provider(Clock(), final(("Antwort.", ["jul/k"])))
    if kind == "unreadable":  # the active ledger cannot be read the next time it is opened
        _fail_opening(monkeypatch, spending.ledger, writing=False)

    result, _ = run(provider, task(), spending)

    detail = ("ledger_damaged" if kind in DAMAGE else "baseline_changed" if kind in DRIFT
              else "budget_changed" if kind == "pinned_other_limit" else "books_unreadable")
    assert (result.outcome, result.detail) == ("refused", detail)
    assert provider.timeouts == []
    assert (spending.ledger.read_bytes(), spending.baseline.read_bytes()) == (
        books_before, history_before)  # nothing truncated, repaired or appended
    assert not spending.artifacts.exists()


RECORDED = Path(__file__).resolve().parent / "results" / "generation-ledger.jsonl"
RECORDED_SHA256 = "e0d031ac4b648f5cd1e086c85ae55c3778254b1b70afcc5a9be461a8a4cf5caa"


def _recorded_books(folder: Path, data: bytes, sha256: str) -> evidence_agent.Spending:
    """Books holding ``data`` as the historical ledger, vouched for by the caller with ``sha256``
    (the agent's own pinned hash is left as it is in the code)."""

    folder.mkdir(exist_ok=True)
    copy = folder / RECORDED.name
    copy.write_bytes(data)
    return evidence_agent.Spending(ledger=folder / evidence_agent.ACTIVE_LEDGER, baseline=copy,
                                   baseline_sha256=sha256, artifacts=folder.parent / "artifacts")


@pytest.mark.parametrize("vouched", ["by_the_caller", "as_recorded"])
def test_altered_historical_bytes_are_refused_before_any_count_whatever_hash_the_caller_gives(
        folder, vouched):
    recorded = RECORDED.read_bytes()
    altered = recorded.replace(b'"cost_usd": 0.536252', b'"cost_usd": 0.0')
    assert altered != recorded  # one settled cost lowered: still valid JSON lines, 0.54 less
    spending = _recorded_books(folder, altered, _sha(altered) if vouched == "by_the_caller"
                               else RECORDED_SHA256)
    provider = Provider(Clock(), final(("Nie gesendet.", ["jul/k"])))

    if vouched == "by_the_caller":  # the caller's hash matches the bytes, not the record
        with pytest.raises(ValueError, match="historical ledger"):
            run(provider, task(), spending)
    else:
        result, _ = run(provider, task(), spending)
        assert (result.outcome, result.detail) == ("refused", "baseline_changed")

    assert provider.timeouts == []  # nothing counted, nothing sent
    assert spending.baseline.read_bytes() == altered
    assert not spending.ledger.exists() and not spending.artifacts.exists()


def test_the_recorded_phase_2_ledger_is_the_baseline_with_all_it_committed(folder):
    # A byte copy of the recorded ledger (which is only read), under the hash pinned in the code.
    spending = _recorded_books(folder, RECORDED.read_bytes(), RECORDED_SHA256)

    result, _ = run(Provider(Clock(), final(("Antwort.", ["jul/k"]))), task(), spending)

    # Eight settled requests of the 2026-11-15 run, none left reserved: 1.930804 USD.
    pin = events(spending)[0]
    assert (pin["sha256"], pin["committed_usd"], pin["budget_usd"]) == (
        RECORDED_SHA256, 1.930804, 100.0)
    assert result.record["spending"]["committed_before_usd"] == 1.930804
    assert _sha(RECORDED.read_bytes()) == RECORDED_SHA256


def test_a_search_supplies_new_passages_and_an_answer_citing_one_of_them_is_accepted(spending):
    clock = Clock()
    provider = Provider(clock, search_call("Pauschale", "Begründung der Pauschale"),
                        final(("Die Pauschale ist neu begründet.", ["jul/c", "jul/k"])))

    result, embedder = run(provider, task(), spending)

    assert (result.outcome, result.status) == ("answer", "answered")
    assert embedder.queries == ["Pauschale"]
    first, second = provider.creates
    # The first request is the Phase 2 request for the same question and passages, with the
    # search instruction appended to its system prompt and the tool offered.
    phase2 = generation.request({"question": task().question, "editions": [JUL],
                                 "passages": list(task().passages)}, generation.Config())
    assert first["messages"] == phase2["messages"]
    assert first["system"].startswith(generation.SYSTEM_PROMPT)
    assert len(first["system"]) > len(generation.SYSTEM_PROMPT)
    for key in ("model", "max_tokens", "thinking", "output_config"):
        assert first[key] == phase2[key]
    assert [t["name"] for t in first["tools"]] == [TOOL]
    assert first["tools"][0]["strict"] is True
    assert first["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    # The second request appends the whole assistant turn and the tool result, rewrites
    # nothing before them, and keeps the system prompt and tool definition.
    assert second["messages"][:1] == first["messages"]
    assert second["messages"][1] == {"role": "assistant",
                                     "content": search_call("Pauschale", "Begründung der "
                                                            "Pauschale")["content"]}
    (result_block,) = second["messages"][2]["content"]
    assert second["messages"][2]["role"] == "user"
    assert (result_block["type"], result_block["tool_use_id"], result_block["is_error"]) == (
        "tool_result", "toolu_1", False)
    assert '<passage id="jul/c" ausgabe="2026-07-01"' in result_block["content"]
    assert (second["system"], second["tools"]) == (first["system"], first["tools"])
    # Five initial plus five found fill the passage budget, so the last call offers no search.
    assert second["tool_choice"] == {"type": "none"}
    assert provider.counts == [{k: v for k, v in body.items() if k != "max_tokens"}
                               for body in provider.creates]
    assert result.record["generation_calls"] == 2
    assert [s["outcome"] for s in result.record["searches"]] == ["passages"]
    assert [r["passage_id"] for r in result.record["searches"][0]["returned"]] == [
        "jul/c", "jul/b", "jul/f", "jul/d", "jul/e"]
    assert result.record["supplied"] == [*INITIAL, "jul/c", "jul/b", "jul/f", "jul/d", "jul/e"]
    assert result.record["cited"] == ["jul/c", "jul/k"]


def test_a_deadline_passed_during_a_search_stops_the_case_before_any_further_provider_call(
        spending):
    clock = Clock()
    provider = Provider(clock, (10.0, search_call("Pauschale", "Begründung")),
                        final(("Nie gesendet.", ["jul/k"])))

    # 10 s for the first call, then 95 s inside the search: 105 s of a 100 s budget.
    result, embedder = run(provider, task(), spending, budget_s=100.0,
                           on_query=lambda: clock.advance(95))

    assert (result.outcome, result.status, result.detail) == ("deadline", None, "after_search")
    assert result.answer is None
    assert embedder.queries == ["Pauschale"]
    assert len(provider.creates) == 1 and len(provider.counts) == 1
    assert [s["outcome"] for s in result.record["searches"]] == ["passages"]
    assert result.record["generation_calls"] == 1
    assert (result.record["budget_s"], result.record["elapsed_s"]) == (100.0, 105.0)


def test_an_immediate_insufficient_evidence_answer_is_accepted_without_a_search(spending):
    clock = Clock()
    provider = Provider(clock, final(status="insufficient_evidence",
                                     missing=["Der Tarif wird nicht genannt."]))

    result, embedder = run(provider, task(), spending)

    assert (result.outcome, result.status, result.detail) == (
        "answer", "insufficient_evidence", None)
    assert result.answer["missing_evidence"] == ["Der Tarif wird nicht genannt."]
    assert embedder.queries == []
    assert [c["tool_choice"] for c in result.record["calls"]] == ["auto"]
    assert result.record["searches"] == []


def test_two_searches_use_up_the_rounds_and_the_third_call_offers_no_search(spending):
    clock = Clock()
    provider = Provider(clock, search_call("Pauschale", "Januar", editions=[JAN]),
                        search_call("Pauschale", "Juli", tool_id="toolu_2", editions=[JUL]),
                        final(("Beide Fassungen.", ["jan/c", "jul/f"])))
    the_task = task(initial=("jul/k", "jul/h", "jul/a", "jan/a", "jan/b"), editions=(JAN, JUL))

    result, _ = run(provider, the_task, spending)

    # January alone ranks a b c d: c and d are new. July then has k c h b a f l d e g, with
    # c b f l d e g new, but only 10 - 7 = 3 fit: c b f.
    assert (result.outcome, result.status) == ("answer", "answered")
    assert [[r["passage_id"] for r in s["returned"]] for s in result.record["searches"]] == [
        ["jan/c", "jan/d"], ["jul/c", "jul/b", "jul/f"]]
    assert [body["tool_choice"]["type"] for body in provider.creates] == ["auto", "auto", "none"]
    third = provider.creates[2]["messages"]
    assert [m["role"] for m in third] == ["user", "assistant", "user", "assistant", "user"]
    assert third[4]["content"][0]["tool_use_id"] == "toolu_2"
    assert len(result.record["supplied"]) == 10
    assert [(e["event"], e["attempt"]) for e in events(spending)[1:]] == [
        (event, f"T1-agent-call{n}") for n in (1, 2, 3) for event in ("reserve", "settle")]
    assert generation.committed_usd(spending.ledger) == 0.072  # 3 x 0.024, each once


def test_refused_and_failed_searches_return_as_error_results_and_use_their_rounds(spending):
    clock = Clock()
    provider = Provider(clock, search_call("Pauschale", "Januar", editions=[JAN]),
                        search_call("Pauschale", "Juli", tool_id="toolu_2"),
                        final(("Nur die ersten Passagen.", ["jul/k"])))

    # January is not selected for this question; the first July search hits a failing model.
    result, embedder = run(provider, task(), spending, failing=1)

    assert (result.outcome, result.status) == ("answer", "answered")
    assert [s["outcome"] for s in result.record["searches"]] == ["refused_editions", "tool_error"]
    assert embedder.queries == ["Pauschale"]
    second, third = provider.creates[1], provider.creates[2]
    refused = second["messages"][2]["content"][0]
    failed = third["messages"][4]["content"][0]
    assert (refused["tool_use_id"], refused["is_error"]) == ("toolu_1", True)
    assert refused["content"].startswith("Search refused:")
    assert (failed["tool_use_id"], failed["is_error"]) == ("toolu_2", True)
    assert failed["content"].startswith("Search failed:")
    assert "not loaded" not in failed["content"]
    assert [body["tool_choice"]["type"] for body in provider.creates] == ["auto", "auto", "none"]
    assert result.record["supplied"] == list(INITIAL)


TWO_CALLS = _message([{"type": "thinking", "thinking": "", "signature": "sig"},
                      {"type": "tool_use", "id": "toolu_1", "name": TOOL,
                       "input": {"query": "Pauschale", "seeking": "eins"}},
                      {"type": "tool_use", "id": "toolu_2", "name": TOOL,
                       "input": {"query": "Analyse", "seeking": "zwei"}}], "tool_use")


@pytest.mark.parametrize(("replies", "outcome", "detail", "queries"), [
    ([search_call("Pauschale", "Tarif", name="read_tariff_database")],
     "protocol_error", "unknown_tool", []),
    ([TWO_CALLS], "protocol_error", "several_tool_uses", []),
    ([search_call("Pauschale", "Begründung"), search_call("Analyse", "mehr", tool_id="toolu_2")],
     "protocol_error", "tool_use_not_offered", ["Pauschale"]),
    ([search_call("Pauschale", "Begründung", stop="max_tokens")],
     "incomplete_generation", "stop_max_tokens", []),
    ([_message([{"type": "thinking", "thinking": "", "signature": "sig"}], "refusal")],
     "incomplete_generation", "stop_refusal", []),
    ([_message([{"type": "tool_use", "name": TOOL, "input": {"query": "Pauschale",
                                                             "seeking": "ohne ID"}}],
               "tool_use")], "protocol_error", "tool_use_without_id", []),
], ids=["unknown_tool", "two_tool_calls", "tool_use_after_none", "cut_off", "refusal",
        "no_tool_use_id"])
def test_an_invalid_or_incomplete_tool_response_stops_the_case_without_running_it(
        replies, outcome, detail, queries, spending):
    clock = Clock()
    provider = Provider(clock, *replies, final(("Nie gesendet.", ["jul/k"])))

    result, embedder = run(provider, task(), spending)

    assert (result.outcome, result.status, result.detail) == (outcome, None, detail)
    assert result.answer is None
    assert embedder.queries == queries
    assert len(provider.creates) == len(replies)
    assert len(provider.replies) == 1  # the answer that would have followed was never asked for


def _text(text: str) -> dict:
    return _message([{"type": "text", "text": text}], "end_turn")


@pytest.mark.parametrize(("replies", "detail"), [
    # jul/g is in the corpus but was never given to the model.
    ([final(("Aus dem Korpus.", ["jul/g"]))], "citations_outside_supplied"),
    # jul/g ranked 10th in the search window but did not fit the five returned.
    ([search_call("Pauschale", "Begründung"), final(("Aus dem Fenster.", ["jul/c", "jul/g"]))],
     "citations_outside_supplied"),
    ([_text('{"status": "answered", "claims": []}')], "schema_invalid"),
    ([_text("Die Pauschale ist neu.")], "schema_invalid"),
], ids=["corpus_passage", "window_passage", "missing_field", "not_json"])
def test_an_answer_off_schema_or_citing_an_unsupplied_passage_is_not_accepted(
        replies, detail, spending):
    clock = Clock()
    provider = Provider(clock, *replies)

    result, _ = run(provider, task(), spending)

    assert (result.outcome, result.status, result.detail) == ("invalid_answer", None, detail)
    assert result.answer is None


@pytest.mark.parametrize(("budget_s", "count_seconds", "reply", "detail", "creates"), [
    (0.0, 0.0, final(("Zu spät.", ["jul/k"])), "before_count", 0),
    (100.0, 150.0, final(("Zu spät.", ["jul/k"])), "before_send", 0),
    (100.0, 0.0, (150.0, search_call("Pauschale", "Begründung")), "after_generation", 1),
    (100.0, 0.0, (150.0, final(("Zu spät.", ["jul/k"]))), "after_generation", 1),
], ids=["no_budget", "during_count", "search_returned_late", "answer_returned_late"])
def test_once_the_deadline_has_passed_nothing_more_is_counted_sent_searched_or_accepted(  # noqa: PLR0913 - parameters
        budget_s, count_seconds, reply, detail, creates, spending):
    clock = Clock()
    provider = Provider(clock, reply, count_seconds=count_seconds)

    result, embedder = run(provider, task(), spending, budget_s=budget_s)

    assert (result.outcome, result.status, result.detail) == ("deadline", None, detail)
    assert result.answer is None
    assert embedder.queries == []
    assert len(provider.creates) == creates
    assert len(provider.counts) == (0 if detail == "before_count" else 1)


def test_a_reservation_the_deadline_overtakes_is_recorded_as_never_sent_and_released(spending):
    provider = Provider(Clock(), final(("Zu spät.", ["jul/k"])), count_seconds=150.0)

    result, _ = run(provider, task(), spending, budget_s=100.0)

    assert (result.outcome, result.detail) == ("deadline", "before_send")
    assert provider.creates == []
    reserve, settle = events(spending)[1:]
    assert (settle["attempt"], settle["sent"], settle["cost_usd"], settle["cost_basis"]) == (
        reserve["attempt"], False, 0.0, "not_sent")
    assert generation.committed_usd(spending.ledger) == 0.0
    assert (spending.artifacts / "requests" / "T1-agent-call1.json").exists()
    assert not (spending.artifacts / "responses").exists()


def test_a_release_that_cannot_be_saved_leaves_the_reservation_committed(spending, monkeypatch):
    earlier(spending, 0.0)  # pinned: the reservation is the first line written, the release next
    _fail_opening(monkeypatch, spending.ledger, at=2)
    provider = Provider(Clock(), final(("Zu spät.", ["jul/k"])), count_seconds=150.0)

    result, _ = run(provider, task(), spending, budget_s=100.0)

    assert (result.outcome, result.detail) == ("persistence_error", "release_not_saved")
    assert provider.creates == []
    assert [e["event"] for e in events(spending)] == ["baseline", "reserve"]
    assert generation.committed_usd(spending.ledger) == 0.71852  # not released, still committed
    (call,) = result.record["calls"]
    assert "cost_basis" not in call and "cost_usd" not in call  # no release claimed either
    request = spending.artifacts / "requests" / "T1-agent-call1.json"
    assert _files(spending.artifacts) == {request: request.read_bytes()}
    books_before = spending.ledger.read_bytes()

    # Unresolved, the case is not sent again, and the next case counts its reservation.
    again = Provider(Clock(), final(("Nie gesendet.", ["jul/k"])))
    repeated, _ = run(again, task(), spending)
    assert (repeated.outcome, repeated.detail, again.timeouts) == ("refused", "already_run", [])
    assert spending.ledger.read_bytes() == books_before
    later, _ = run(Provider(Clock(), final(("Antwort.", ["jul/k"]))),
                   dataclasses.replace(task(), case_id="T2"), spending)
    assert later.record["spending"]["committed_before_usd"] == 0.71852


def test_every_request_timeout_is_the_smaller_of_the_request_limit_and_the_time_left(spending):
    clock = Clock()
    provider = Provider(clock, (20.0, search_call("Pauschale", "Begründung")),
                        final(("Rechtzeitig.", ["jul/c"])), count_seconds=30.0)

    # Budget 100 s: count at 0 s (100 left), takes 30; generate at 30 s (70 left), takes 20;
    # the search takes 5; count at 55 s (45 left), takes 30; generate at 85 s (15 left).
    result, _ = run(provider, task(), spending, budget_s=100.0,
                     on_query=lambda: clock.advance(5))

    assert (result.outcome, result.status) == ("answer", "answered")
    assert provider.timeouts == [("/v1/messages/count_tokens", 100.0), ("/v1/messages", 70.0),
                                 ("/v1/messages/count_tokens", 45.0), ("/v1/messages", 15.0)]

    roomy = Provider(Clock(), final(("Rechtzeitig.", ["jul/k"])))
    run(roomy, dataclasses.replace(task(), case_id="T2"), spending, budget_s=3600.0)
    assert roomy.timeouts == [("/v1/messages/count_tokens", 1200.0), ("/v1/messages", 1200.0)]


def _error(status: int, kind: str) -> httpx.Response:
    return httpx.Response(status, json={"type": "error", "error": {
        "type": kind, "message": f"Anbieterfehler-Text {kind}"}})


ANSWER = final(("Nie angenommen.", ["jul/k"]))
OTHER_MODEL = {**ANSWER, "model": "claude-other-model"}


@pytest.mark.parametrize(("replies", "count_reply", "outcome", "detail", "creates"), [
    ([_error(529, "overloaded_error")], None, "provider_error", "http_529", 1),
    ([ANSWER], _error(400, "invalid_request_error"), "provider_error", "http_400", 0),
    ([httpx.ReadTimeout("timed out")], None, "provider_error", "timeout", 1),
    ([httpx.ConnectError("refused")], None, "provider_error", "connection_error", 1),
    ([OTHER_MODEL], None, "provider_error", "model_mismatch", 1),
    ([httpx.Response(200, text="kein JSON")], None, "provider_error", "unreadable_response", 1),
    ([httpx.Response(200, json=[])], None, "provider_error", "unreadable_response", 1),
    ([{**ANSWER, "content": ["kein Block"]}], None, "provider_error", "unreadable_response", 1),
    ([ANSWER], httpx.Response(200, json={}), "provider_error", "unreadable_count", 0),
    ([ANSWER], httpx.Response(200, json=[]), "provider_error", "unreadable_count", 0),
    # The read timeout arrives 150 s into a 100 s budget: the deadline, not the provider.
    ([(150.0, httpx.ReadTimeout("timed out"))], None, "deadline", "after_generation", 1),
], ids=["overloaded", "count_rejected", "timeout", "connection", "other_model", "unreadable",
        "not_an_object", "block_not_an_object", "count_missing", "count_not_an_object",
        "late_timeout"])
def test_a_provider_failure_ends_the_case_once_without_retry_and_apart_from_a_deadline(  # noqa: PLR0913 - parameters
        replies, count_reply, outcome, detail, creates, spending):
    clock = Clock()
    provider = Provider(clock, *replies, count_reply=count_reply)

    result, embedder = run(provider, task(), spending, budget_s=100.0)

    assert (result.outcome, result.status, result.detail) == (outcome, None, detail)
    assert result.answer is None
    assert len(provider.creates) == creates
    assert embedder.queries == []
    assert "Anbieterfehler-Text" not in json.dumps(result.record, ensure_ascii=False)
    if detail.startswith("http_"):
        assert "Anbieterfehler-Text" in " ".join(result.local["errors"])


def _with_usage(**usage) -> dict:
    return {**ANSWER, "usage": {**ANSWER["usage"], **usage}}


@pytest.mark.parametrize(("reply", "outcome", "detail", "saved"), [
    (httpx.ReadTimeout("timed out"), "provider_error", "timeout", False),
    (httpx.ConnectError("refused"), "provider_error", "connection_error", False),
    (_error(529, "overloaded_error"), "provider_error", "http_529", True),
    (httpx.Response(200, text="kein JSON"), "provider_error", "unreadable_response", True),
    (httpx.Response(200, text="[" * 200_000), "provider_error", "unreadable_response", True),
    (OTHER_MODEL, "provider_error", "model_mismatch", True),
    ({k: v for k, v in ANSWER.items() if k != "usage"}, "answer", None, True),
    (_with_usage(output_tokens="900"), "answer", None, True),
    (_with_usage(output_tokens_details={"thinking_tokens": 901}), "answer", None, True),
    (_with_usage(service_tier="priority"), "answer", None, True),
    (_with_usage(server_tool_use={"web_search_requests": 1}), "answer", None, True),
    (_with_usage(cache_read_input_tokens=""), "answer", None, True),
    (_with_usage(cache_creation=[]), "answer", None, True),
    (_with_usage(server_tool_use=[]), "answer", None, True),
    (_with_usage(cache_creation={"ephemeral_5m_input_tokens": 10_000,
                                 "ephemeral_1h_input_tokens": 0}), "answer", None, True),
], ids=["timeout", "connection", "error_response", "unreadable", "nested_too_deep", "other_model",
        "no_usage",
        "usage_not_a_count", "thinking_above_output", "other_price_tier", "server_tool_use",
        "empty_text_count", "cache_breakdown_not_an_object", "server_tools_not_an_object",
        "cache_breakdown_disagrees"])
def test_a_sent_call_without_priceable_usage_keeps_its_whole_reservation_as_exposure(
        spending, reply, outcome, detail, saved):
    provider = Provider(Clock(), reply)

    result, _ = run(provider, task(), spending, budget_s=100.0)

    # Accounting does not decide acceptance: an answer without usage is still an answer.
    assert (result.outcome, result.detail) == (outcome, detail)
    reserve, settle = events(spending)[1:]
    assert (settle["sent"], settle["cost_usd"], settle["cost_basis"], settle["usage"]) == (
        True, reserve["reserved_usd"], "reservation_retained", None)
    assert generation.committed_usd(spending.ledger) == 0.71852
    assert result.record["calls"][0]["cost_basis"] == "reservation_retained"
    response = spending.artifacts / "responses" / "T1-agent-call1.json"
    assert response.exists() == saved
    assert settle["response_sha256"] == (_sha(response.read_bytes()) if saved else None)


def test_optional_usage_fields_given_as_null_are_priced_as_zero(spending):
    nulls = _with_usage(cache_creation_input_tokens=None, cache_read_input_tokens=None,
                        cache_creation=None, output_tokens_details=None, inference_geo=None,
                        service_tier="standard", server_tool_use={"web_search_requests": 0})

    result, _ = run(Provider(Clock(), nulls), task(), spending)

    assert result.outcome == "answer"
    settle = events(spending)[-1]
    assert (settle["cost_usd"], settle["cost_basis"]) == (0.024, "usage")


def test_a_later_case_counts_what_earlier_cases_left_in_the_same_books(spending):
    timed_out, _ = run(Provider(Clock(), httpx.ReadTimeout("timed out")), task(), spending)
    later, _ = run(Provider(Clock(), final(("Antwort.", ["jul/k"]))),
                   dataclasses.replace(task(), case_id="T2"), spending)

    assert (timed_out.detail, later.outcome) == ("timeout", "answer")
    # The first case's whole reservation stays committed when the second is admitted.
    assert later.record["spending"]["committed_before_usd"] == 0.71852
    assert [(e["event"], e.get("case")) for e in events(spending)] == [
        ("baseline", None), ("reserve", "T1"), ("settle", "T1"), ("reserve", "T2"),
        ("settle", "T2")]
    assert generation.committed_usd(spending.ledger) == 0.74252


def _dearest(input_tokens: int) -> dict:
    """The dearest usage the settlement prices: every input token an hour's cache write, the
    whole output allowance, US inference."""

    return {"input_tokens": 0, "output_tokens": 32_000,
            "cache_creation_input_tokens": input_tokens, "cache_read_input_tokens": 0,
            "cache_creation": {"ephemeral_5m_input_tokens": 0,
                               "ephemeral_1h_input_tokens": input_tokens},
            "inference_geo": "us"}


@pytest.mark.parametrize(("input_tokens", "cost", "above"), [
    (1650, 0.71852, False), (1651, 0.718529, True)], ids=["within_the_margin", "one_token_beyond"])
def test_the_dearest_usage_within_the_margin_is_covered_by_its_reservation(
        spending, input_tokens, cost, above):
    provider = Provider(Clock(), {**ANSWER, "usage": _dearest(input_tokens)})

    result, _ = run(provider, task(), spending)

    # Counted at 1,500 tokens, the margin allows ceil(1,500 x 1.10) = 1,650 input tokens. As hour
    # cache writes (8 USD per million) with 32,000 output tokens (20) and the US multiplier:
    # (1,650 x 8 + 32,000 x 20) x 1.1 / 1e6 = 0.71852 USD, the reservation exactly; one input
    # token more is (1,651 x 8 + 640,000) x 1.1 / 1e6 = 0.7185288, calculated as 0.718529.
    assert result.outcome == "answer"
    reserve, settle = events(spending)[1:]
    assert (reserve["reserved_usd"], settle["cost_usd"], settle["cost_basis"],
            settle["above_reservation"]) == (0.71852, cost, "usage", above)


@pytest.mark.parametrize(("reply", "outcome", "detail"), [
    ({**search_call("Pauschale", "Begründung"), "usage": _dearest(1651)}, "spending_stop",
     "cost_above_reservation"),
    ({**ANSWER, "usage": _dearest(1651)}, "answer", None),
], ids=["before_a_search", "with_the_answer"])
def test_a_cost_above_the_reservation_is_recorded_in_full_and_no_further_call_follows(
        spending, reply, outcome, detail):
    provider = Provider(Clock(), reply, final(("Nie gesendet.", ["jul/k"])))

    result, embedder = run(provider, task(), spending)

    # Usage beyond the margin: 0.718529 USD against 0.71852 reserved, recorded as calculated,
    # not capped, and nothing more is sent.
    assert (result.outcome, result.detail) == (outcome, detail)
    reserve, settle = events(spending)[1:]
    assert (reserve["reserved_usd"], settle["cost_usd"], settle["above_reservation"]) == (
        0.71852, 0.718529, True)
    assert generation.committed_usd(spending.ledger) == 0.718529
    assert len(provider.creates) == 1 and embedder.queries == []


def test_the_loop_sends_once_even_with_a_client_that_would_retry(spending):
    clock = Clock()
    provider = Provider(clock, _error(529, "overloaded_error"), ANSWER, ANSWER)
    retrying = anthropic.Anthropic(api_key="test-key", base_url=generation.BASE_URL,
                                   http_client=httpx.Client(transport=httpx.MockTransport(provider)))
    assert retrying.max_retries > 0  # the SDK default
    retriever, passages, _ = world()

    result = evidence_agent.run_case(task(), client=retrying, retriever=retriever,
                                     passages=passages, clock=clock, budget_s=100.0,
                                     spending=spending)

    assert (result.outcome, result.detail) == ("provider_error", "http_529")
    assert len(provider.creates) == 1


def test_the_record_holds_metadata_while_raw_text_stays_in_the_local_artifacts(spending):
    question = "Welche Pauschale gilt? Marke-Frage"
    clock = Clock()
    answered = Provider(clock, search_call("Pauschale Marke-Suche", "Marke-Lücke"),
                        final(("Marke-Aussage", ["jul/c"])))
    invalid = Provider(Clock(), final(("Marke-Aussage", ["Marke-Zitat"])))

    first, _ = run(answered, task(question=question), spending)
    second, _ = run(invalid, dataclasses.replace(task(question=question), case_id="T2"), spending)

    assert (first.outcome, second.outcome) == ("answer", "invalid_answer")
    for result, provider in ((first, answered), (second, invalid)):
        public = json.dumps(result.record, ensure_ascii=False)
        assert "Marke" not in public
        assert "Analyse" not in public  # passage text
        local = json.dumps(result.local, ensure_ascii=False)
        assert "Marke-Frage" in local and "Marke-Aussage" in local
        for call, raw in zip(result.record["calls"], result.local["responses"], strict=True):
            assert call["response_sha256"] == hashlib.sha256(raw.encode("utf-8")).hexdigest()
            assert len(call["request_sha256"]) == 64
            assert call["usage"]["output_tokens"] == 900
    assert "Marke-Suche" in json.dumps(first.local["searches"], ensure_ascii=False)
    assert second.record["citations_outside_supplied"] == 1


MARKED = {**ANSWER, "stop_reason": "Marke-stop", "stop_details": {"reason": "Marke-detail"},
          "usage": {**ANSWER["usage"], "inference_geo": "Marke-geo", "Marke-key": 1}}


@pytest.mark.parametrize(("reply", "outcome", "detail"), [
    (httpx.Response(200, json=MARKED, headers={"request-id": "Marke-request"}),
     "incomplete_generation", "stop_unknown"),
    ({**ANSWER, "model": "Marke-model"}, "provider_error", "model_mismatch"),
    (httpx.Response(500, json={"type": "error", "error": {"type": "Marke-type",
                                                          "message": "Marke-error"}}),
     "provider_error", "http_500"),
], ids=["stop_reason_and_usage", "returned_model", "error_body"])
def test_public_records_carry_codes_and_counts_never_text_the_provider_wrote(
        spending, reply, outcome, detail):
    provider = Provider(Clock(), reply)

    result, _ = run(provider, task(), spending)

    assert (result.outcome, result.detail) == (outcome, detail)
    public = json.dumps(result.record, ensure_ascii=False) + spending.ledger.read_text("utf-8")
    assert "Marke" not in public
    (call,) = result.record["calls"]
    if outcome != "provider_error" or detail == "model_mismatch":
        assert (call["returned_model"], call["stop_reason"]) in (
            (generation.MODEL, "unknown"), ("other", "end_turn"))
    raw = (spending.artifacts / "responses" / "T1-agent-call1.json").read_text("utf-8")
    assert "Marke" in raw  # kept as it came, in the local artifact only


@pytest.mark.parametrize("initial", [
    ("jul/k", "jul/h", "jul/a", "jul/l", "jan/a"),
    ("jul/k", "jul/h", "jul/a", "jul/l", "jul/k"),
    tuple(f"jul/{c}" for c in "abcdefghijk"),
], ids=["unselected_edition", "repeated_passage", "over_the_budget"])
def test_initial_passages_outside_the_question_or_its_budget_are_refused_before_any_request(
        initial, spending):
    provider = Provider(Clock(), final(("Nie gesendet.", ["jul/k"])))

    with pytest.raises(ValueError, match="initial passages"):
        run(provider, task(initial=initial), spending)

    assert provider.timeouts == []  # nothing was counted or sent


@pytest.mark.parametrize("change", ["ledger_elsewhere", "second_ledger", "history_renamed",
                                    "copied_books", "no_history", "limit_raised",
                                    "margin_lowered", "case_id_as_path"])
def test_books_or_a_case_id_that_cannot_be_kept_safely_are_refused_before_any_request(
        tmp_path, folder, change):
    spending, the_task, config = books(), task(), None
    if change == "ledger_elsewhere":  # one folder lock must cover both ledgers
        spending = dataclasses.replace(
            spending, ledger=tmp_path / "other" / evidence_agent.ACTIVE_LEDGER)
    elif change == "second_ledger":  # a second file beside it would start from nothing
        spending = dataclasses.replace(spending, ledger=folder / "other.jsonl")
    elif change == "history_renamed":
        renamed = spending.baseline.rename(folder / "other-history.jsonl")
        spending = dataclasses.replace(spending, baseline=renamed)
    elif change == "copied_books":  # a byte copy in another folder would be a second allowance
        (tmp_path / "other").mkdir()
        copy = tmp_path / "other" / evidence_agent.HISTORICAL_LEDGER
        copy.write_bytes(spending.baseline.read_bytes())
        spending = dataclasses.replace(
            spending, baseline=copy, ledger=tmp_path / "other" / evidence_agent.ACTIVE_LEDGER)
    elif change == "no_history":
        spending.baseline.unlink()
    elif change == "limit_raised":  # a fresh ledger must not pin a higher limit either
        config = generation.Config(budget_usd=200.0)
    elif change == "margin_lowered":  # smaller ceilings would admit more than the limit allows
        config = generation.Config(input_margin=1.0)
    else:
        the_task = dataclasses.replace(the_task, case_id="../T1")
    provider = Provider(Clock(), final(("Nie gesendet.", ["jul/k"])))

    with pytest.raises(ValueError, match="ledger|limit|case id"):
        run(provider, the_task, spending, config=config)

    assert provider.timeouts == []
    assert not spending.artifacts.exists() and not spending.ledger.exists()
    assert not (tmp_path / "other" / evidence_agent.ACTIVE_LEDGER).exists()


def test_there_is_no_way_to_run_a_case_without_its_books():
    provider = Provider(Clock(), final(("Nie gesendet.", ["jul/k"])))
    retriever, passages, _ = world()

    with pytest.raises(TypeError, match="spending"):
        evidence_agent.run_case(task(), client=provider.client(), retriever=retriever,  # noqa: PLE1125
                                passages=passages, clock=provider.clock, budget_s=100.0)

    assert provider.timeouts == []


def test_the_search_instruction_and_tool_carry_nothing_specific_to_a_case(spending):
    provider = Provider(Clock(), final(("Antwort.", ["jul/k"])))

    run(provider, task(), spending)

    (body,) = provider.creates
    added = body["system"][len(generation.SYSTEM_PROMPT):]
    (tool,) = body["tools"]
    words = json.dumps({**tool, "input_schema": {**tool["input_schema"], "properties": {
        k: {**v, "items": None} for k, v in tool["input_schema"]["properties"].items()}}},
        ensure_ascii=False)
    for text in (added, words):
        assert not re.search(r"\d{4}\.\d{2}", text)  # no position number
        assert not re.search(r"/p\d", text)  # no passage ID
        assert not re.search(r"\b[DU]\d\b", text)  # no case label
        assert "2026-" not in text
    assert tool["input_schema"]["properties"]["editions"]["items"]["enum"] == [JUL]



# The comparison conditions (Phase 3): A, the fixed hybrid top 5 (fixed5), B, the fixed top 10
# (fixed10), each answered once without any tool, and C, the agent above (agent). July's hybrid
# order is k c h b a f l d e g i j (worked out in test_evidence_search), so the top 10 ends at g.
TOP10 = ("jul/k", "jul/c", "jul/h", "jul/b", "jul/a", "jul/f", "jul/l", "jul/d", "jul/e", "jul/g")


def test_a_fixed_condition_sends_the_phase_2_request_once_without_any_tool_under_its_own_name(
        spending):
    provider = Provider(Clock(), final(("Die Pauschale gilt.", ["jul/k"])))
    the_task = task(initial=TOP10[:5])

    result, embedder = run(provider, the_task, spending, condition="fixed5")

    assert (result.outcome, result.status) == ("answer", "answered")
    # Exactly the Phase 2 request of ADR-025: its own system prompt, no tools and no tool choice.
    phase2 = generation.request({"question": the_task.question, "editions": [JUL],
                                 "passages": list(the_task.passages)}, generation.Config())
    assert provider.creates == [phase2]
    assert provider.counts == [{k: v for k, v in phase2.items() if k != "max_tokens"}]
    assert embedder.queries == []  # nothing searched
    assert [(e["event"], e.get("attempt"), e.get("case"), e.get("condition"))
            for e in events(spending)] == [
        ("baseline", None, None, None), ("reserve", "T1-fixed5-call1", "T1", "fixed5"),
        ("settle", "T1-fixed5-call1", "T1", "fixed5")]
    assert (spending.artifacts / "requests" / "T1-fixed5-call1.json").exists()
    assert (result.record["case"], result.record["condition"]) == ("T1", "fixed5")
    # Admitted for its one call at the input cap: 1.4784 USD, not the agent's three calls.
    assert result.record["spending"]["admission_usd"] == 1.4784
    assert (result.record["generation_calls"], result.record["searches"]) == (1, [])


def _sent(body: dict) -> list[str]:
    """The passage IDs of a request's first (user) message, in the order given."""
    return re.findall(r'<passage id="([^"]+)"', body["messages"][0]["content"])


def test_the_conditions_of_one_question_share_the_books_and_each_runs_only_once(spending):
    a, _ = run(Provider(Clock(), final(("A.", ["jul/k"]))), task(initial=TOP10[:5]), spending,
               condition="fixed5")
    b_provider = Provider(Clock(), final(("B.", ["jul/g"])))

    b, _ = run(b_provider, task(initial=TOP10), spending, condition="fixed10")

    assert (a.outcome, b.outcome) == ("answer", "answer")
    (body,) = b_provider.creates
    assert _sent(body) == list(TOP10)  # the whole top 10 in rank order; its tenth is citable
    assert b.record["spending"]["committed_before_usd"] == 0.024  # A's cost counts for B
    assert [(e["event"], e.get("attempt"), e.get("condition")) for e in events(spending)][1:] == [
        ("reserve", "T1-fixed5-call1", "fixed5"), ("settle", "T1-fixed5-call1", "fixed5"),
        ("reserve", "T1-fixed10-call1", "fixed10"), ("settle", "T1-fixed10-call1", "fixed10")]
    before = spending.ledger.read_bytes()
    again = Provider(Clock(), final(("Nie gesendet.", ["jul/k"])))
    for name, initial in (("fixed5", TOP10[:5]), ("fixed10", TOP10)):
        refused, _ = run(again, task(initial=initial), spending, condition=name)
        assert (refused.outcome, refused.detail) == ("refused", "already_run")
    assert again.timeouts == []  # nothing counted or sent twice
    assert spending.ledger.read_bytes() == before


ACTIVE_RECORDED = RECORDED.parent / "phase3-ledger.jsonl"
ACTIVE_RECORDED_SHA256 = "ac0bd49ae8d91cd9716bac9bca78a5c1e211f7684b2ce6f9300b05361cfad12b"


@pytest.mark.parametrize(("condition", "outcome"), [
    ("agent", "refused"), ("fixed5", "answer"), ("fixed10", "answer")])
def test_the_recorded_books_refuse_d1_under_the_agent_and_admit_its_other_conditions(
        folder, condition, outcome):
    # Byte copies of both recorded ledgers: the D1 run's calls have no condition (written before
    # conditions existed) and are the agent's, so D1 is never sent to the agent again.
    spending = _recorded_books(folder, RECORDED.read_bytes(), RECORDED_SHA256)
    spending.ledger.write_bytes(ACTIVE_RECORDED.read_bytes())
    before = spending.ledger.read_bytes()
    provider = Provider(Clock(), final(("Antwort.", ["jul/k"])))
    initial = TOP10 if condition == "fixed10" else TOP10[:5]

    result, _ = run(provider, dataclasses.replace(task(initial=initial), case_id="D1"), spending,
                    condition=condition)

    assert result.outcome == outcome
    if outcome == "refused":
        assert result.detail == "already_run"
        assert provider.timeouts == []
        assert spending.ledger.read_bytes() == before
    else:  # Phase 2's 1.930804 and the D1 run's 0.560552 USD are committed before it
        assert result.record["spending"]["committed_before_usd"] == 2.491356
        assert spending.ledger.read_bytes().startswith(before)  # appended to, nothing rewritten
        assert [(e["attempt"], e["condition"]) for e in events(spending)[5:]] == [
            (f"D1-{condition}-call1", condition)] * 2
    assert _sha(ACTIVE_RECORDED.read_bytes()) == ACTIVE_RECORDED_SHA256  # only ever read


def test_case_ids_that_end_like_a_condition_still_name_cells_of_their_own(spending):
    cells = [("E1", "fixed5"), ("E1-fixed5", "agent"), ("E1-fixed5", "fixed5")]
    for case, name in cells:
        provider = Provider(Clock(), final(("Antwort.", ["jul/k"])))
        result, _ = run(provider, dataclasses.replace(task(initial=TOP10[:5]), case_id=case),
                        spending, condition=name)
        assert result.outcome == "answer"

    assert [(e["attempt"], e["case"], e["condition"]) for e in events(spending)
            if e["event"] == "reserve"] == [
        ("E1-fixed5-call1", "E1", "fixed5"), ("E1-fixed5-agent-call1", "E1-fixed5", "agent"),
        ("E1-fixed5-fixed5-call1", "E1-fixed5", "fixed5")]


def test_a_call_id_an_earlier_reservation_holds_is_never_written_twice(spending):
    # A reservation from before conditions existed, for a case named like a cell: its call ID
    # is the one case E1 would use under fixed5.
    earlier(spending, 0.0, {**reservation("E1-fixed5-call1", 0.5), "case": "E1-fixed5"})
    before = spending.ledger.read_bytes()
    provider = Provider(Clock(), final(("Nie gesendet.", ["jul/k"])))

    result, _ = run(provider, dataclasses.replace(task(initial=TOP10[:5]), case_id="E1"),
                    spending, condition="fixed5")

    assert (result.outcome, result.detail) == ("refused", "call_id_taken")
    assert provider.timeouts == []
    assert spending.ledger.read_bytes() == before


@pytest.mark.parametrize(("condition", "count"), [
    ("fixed5", 6), ("fixed10", 11), ("agent", 6)])
def test_a_condition_takes_no_more_initial_passages_than_its_own_bound(
        spending, condition, count):
    july = ("jul/k", "jul/c", "jul/h", "jul/b", "jul/a", "jul/f", "jul/l", "jul/d", "jul/e",
            "jul/g", "jul/i")
    provider = Provider(Clock(), final(("Nie gesendet.", ["jul/k"])))

    with pytest.raises(ValueError, match="initial passages"):
        run(provider, task(initial=july[:count]), spending, condition=condition)

    assert provider.timeouts == []


def test_an_unknown_condition_is_refused_before_any_request(spending):
    provider = Provider(Clock(), final(("Nie gesendet.", ["jul/k"])))

    with pytest.raises(ValueError, match="condition"):
        run(provider, task(), spending, condition="fixed7")

    assert provider.timeouts == []
    assert not spending.ledger.exists()


@pytest.mark.parametrize("condition", ["fixed5", "fixed10"])
def test_a_fixed_condition_runs_no_search_a_model_asks_for(spending, condition):
    provider = Provider(Clock(), search_call("Pauschale", "Begründung"),
                        final(("Nie gesendet.", ["jul/k"])))
    initial = TOP10 if condition == "fixed10" else TOP10[:5]

    result, embedder = run(provider, task(initial=initial), spending, condition=condition)

    assert (result.outcome, result.detail) == ("protocol_error", "tool_use_not_offered")
    assert (len(provider.creates), embedder.queries) == (1, [])  # one call, nothing searched
    assert [e["event"] for e in events(spending)] == ["baseline", "reserve", "settle"]


def _cell_reserve(case: str, condition: str, call: int = 1, attempt: str | None = None) -> dict:
    return {"event": "reserve", "attempt": attempt or f"{case}-{condition}-call{call}",
            "case": case, "condition": condition, "call": call, "request_sha256": "0" * 64,
            "counted_input_tokens": 1500, "reserved_usd": 0.5, "at": "2026-11-21T08:00:00+00:00"}


def _cell_release(case: str, condition: str, attempt: str) -> dict:
    return {"event": "settle", "attempt": attempt, "case": case, "condition": condition,
            "sent": False, "cost_usd": 0.0, "cost_basis": "not_sent", "above_reservation": False,
            "usage": None, "response_sha256": None, "at": "2026-11-21T08:00:00+00:00"}


@pytest.mark.parametrize("rows", [
    [_cell_reserve("E1", "fixed5"), _cell_release("E1", "agent", "E1-fixed5-call1")],
    [_cell_reserve("E1", "fixed5"), {**_cell_release("E1", "fixed5", "E1-fixed5-call1"),
                                     "condition": None}],
    [_cell_reserve("E1", "fixed7")],
    [_cell_reserve("E1", "fixed5", call=2)],
    [_cell_reserve("E1", "fixed5", attempt="E1-call1")],
    [{**_cell_reserve("E1", "agent"), "condition": None}],
    [{**_cell_reserve("E1", "fixed5"), "question_sha256": "not a hash"}],
    [{**_cell_reserve("E1", "fixed5"), "editions": "2026-07-01"}],
], ids=["settled_under_another_condition", "settled_without_its_condition", "unknown_condition",
        "second_call_of_a_one_call_condition", "call_id_without_its_condition",
        "null_condition", "malformed_question_hash", "editions_not_a_list"])
def test_books_whose_conditions_contradict_their_calls_are_refused_as_damaged(spending, rows):
    earlier(spending, 0.0, *rows)
    before = spending.ledger.read_bytes()
    provider = Provider(Clock(), final(("Nie gesendet.", ["jul/k"])))

    result, _ = run(provider, task(), spending)

    assert (result.outcome, result.detail) == ("refused", "ledger_damaged")
    assert provider.timeouts == []
    assert spending.ledger.read_bytes() == before



def test_every_reservation_records_the_question_and_the_editions_it_was_asked(spending):
    provider = Provider(Clock(), final(("Antwort.", ["jul/k"])))
    the_task = task(initial=("jul/k", "jan/a"), editions=(JUL, JAN))  # editions given unsorted

    run(provider, the_task, spending, condition="fixed5")

    (reserve,) = [e for e in events(spending) if e["event"] == "reserve"]
    # The plain SHA-256 of the question's UTF-8, as public records publish it; editions sorted.
    assert reserve["question_sha256"] == hashlib.sha256(
        the_task.question.encode("utf-8")).hexdigest()
    assert reserve["editions"] == [JAN, JUL]


@pytest.mark.parametrize("change", ["question", "editions"])
@pytest.mark.parametrize("condition", ["fixed5", "agent"])
def test_a_case_booked_with_another_question_or_editions_is_refused_under_any_condition(
        spending, change, condition):
    run(Provider(Clock(), final(("Antwort.", ["jul/k"]))), task(), spending, condition="fixed10")
    before = spending.ledger.read_bytes()
    other = (task(question="Eine andere Frage?") if change == "question"
             else task(initial=("jul/k", "jan/a"), editions=(JAN, JUL)))
    provider = Provider(Clock(), final(("Nie gesendet.", ["jul/k"])))

    result, _ = run(provider, other, spending, condition=condition)

    # One case ID names one question over one edition selection, whatever the condition.
    assert (result.outcome, result.detail) == ("refused", "case_redefined")
    assert provider.timeouts == []
    assert spending.ledger.read_bytes() == before


def test_a_case_booked_before_questions_were_recorded_is_not_checked_by_the_books(spending):
    # The D1 run's reservations carry no question: the books cannot compare it, so they let a
    # new condition of that case through (the comparison runner refuses to pair it).
    earlier(spending, 0.0, reservation("T1-call1", 0.5))
    provider = Provider(Clock(), final(("Antwort.", ["jul/k"])))

    result, _ = run(provider, task(question="Eine andere Frage?"), spending, condition="fixed5")

    assert result.outcome == "answer"
