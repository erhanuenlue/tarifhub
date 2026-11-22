"""A synthetic trace of the evidence-seeking agent in a local Phoenix: offline, no key, no cost.

One synthetic question runs once through the real loop (``evidence_agent.run_case``). The
pilot's own client (``generation.client``, with a placeholder key) talks to a scripted provider
behind an ``httpx.MockTransport``, and the real commentary search ranks the synthetic corpus of
``test_evidence_search``: call 1 asks for one ``search_commentary`` call, call 2 answers. Neither
``evidence_agent`` nor ``evidence_search`` is changed; both are instrumented from outside. A
transport wrapper puts a span around each generation call (``/v1/messages``; token counts pass
without one), and a wrapper stands in for ``evidence_search.search_commentary`` during the run
only and puts one around the search.

The four spans (the case, two generation calls, one search) carry codes, IDs, counts, elapsed
times and SHA-256 prefixes only: no question, passage, query or answer text, and no cost (no
``llm.model_name`` or ``llm.token_count`` attribute, so Phoenix derives none; the books stay the
spending record). The books are a temporary folder with a byte copy of the recorded Phase 2
ledger, which the loop checks against its pinned hash, and a fresh active ledger; they and the
raw request and response artifacts are deleted with the folder. The spans leave the process only
when the run is the scripted one, the traced responses are the ones the loop recorded, and no span
carries any of the run's texts. The export goes over OTLP/HTTP to ``ENDPOINT`` on 127.0.0.1
without proxies, and a guard refuses every Python socket ``connect`` to a non-loopback address.
The latencies are declared synthetic delays (``SYNTHETIC_DELAY_S``), not measurements of a
provider.

    UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" env -u ANTHROPIC_API_KEY \\
        uv run --project services/ingestion --frozen --extra ai --extra dev \\
        --with opentelemetry-sdk --with opentelemetry-exporter-otlp-proto-http \\
        python tools/commentary_rag/trace_demo.py

Exit codes: 0 the trace was exported, 1 the run, a check or the export failed, 3 refused (a
provider credential in the environment, or a package missing).
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import evidence_agent
    import evidence_search
    import generation
    import httpx
    import requests
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import Status, StatusCode
    from test_evidence_search import JUL, world
except ModuleNotFoundError as missing:  # OpenTelemetry, or the ingestion ai or dev extra
    print(f"refused: {missing.name} is not installed; run with the command in this file's "
          "docstring", file=sys.stderr)
    raise SystemExit(3) from None

PROJECT = "tarifhub-evidence-agent"  # the Phoenix project, by resource attribute
ENDPOINT = "http://127.0.0.1:6016/v1/traces"  # the TarifHub Phoenix: OTLP over HTTP, loopback
LOOPBACK = ("127.0.0.1", "::1", "localhost")
CASE_ID = "TRACE-DEMO-1"
# A unique ASCII marker in the question, the search request and the answer: no span may carry it.
MARKER = "TARIFHUB-TRACE-MARKER-7Q4ZP2"
QUESTION = f"Welche Pauschale gilt und warum? {MARKER}"
INITIAL = ("jul/k", "jul/h", "jul/a", "jul/l", "jul/i")  # the agent tests' fixed top five
SEARCH = {"query": "Pauschale", "seeking": f"Begründung der Pauschale {MARKER}"}
ANSWER = {"status": "answered",
          "claims": [{"text": f"Die Pauschale ist neu begründet ({MARKER}).",
                      "citations": ["jul/c", "jul/k"]}],
          "missing_evidence": []}
# Declared delays that make the waterfall readable: each Messages reply waits the first, each
# query embedding of the stand-in embedder the second. The trace measures them; it models no
# provider.
SYNTHETIC_DELAY_S = {"generation_call": 0.4, "query_embedding": 0.05}
BUDGET_S = 120.0  # the case's cooperative deadline, on time.monotonic


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _message(content: list[dict], stop: str, input_tokens: int, output_tokens: int) -> dict:
    """A Messages response in the provider's shape, its usage mocked."""

    return {"id": "msg_synthetic", "type": "message", "role": "assistant",
            "model": generation.MODEL, "stop_reason": stop, "stop_sequence": None,
            "content": content,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}


class ScriptedProvider:
    """The provider's HTTP side: each token count answers 1,500 tokens; Messages call 1 asks for
    one search, call 2 answers. Each Messages reply first waits its synthetic delay."""

    def __init__(self) -> None:
        search = [{"type": "tool_use", "id": "toolu_synthetic_1",
                   "name": evidence_agent.TOOL_NAME, "input": SEARCH}]
        answer = [{"type": "text", "text": json.dumps(ANSWER, ensure_ascii=False)}]
        self.replies = [_message(search, "tool_use", 1500, 120),
                        _message(answer, "end_turn", 2900, 260)]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Answer one request the pilot's client sends."""

        if request.url.path == "/v1/messages/count_tokens":
            return httpx.Response(200, json={"input_tokens": 1500})
        time.sleep(SYNTHETIC_DELAY_S["generation_call"])
        return httpx.Response(200, json=self.replies.pop(0),
                              headers={"request-id": "req_synthetic"})


class TracedTransport(httpx.BaseTransport):
    """One span around each generation call (``/v1/messages``), recording what came back as
    codes and counts; token counts pass through without a span."""

    def __init__(self, inner: httpx.BaseTransport, tracer) -> None:
        self.inner = inner
        self.tracer = tracer
        self.calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Pass ``request`` on and, for a generation call, trace its decision and timing."""

        if request.url.path != "/v1/messages":
            return self.inner.handle_request(request)
        self.calls += 1
        with self.tracer.start_as_current_span(f"generation call {self.calls}",
                                               record_exception=False,
                                               set_status_on_exception=False) as span:
            started = time.perf_counter()
            response = self.inner.handle_request(request)
            response.read()
            elapsed_ms = (time.perf_counter() - started) * 1000
            data = json.loads(response.text)
            asks = any(block.get("type") == "tool_use"
                       and block.get("name") == evidence_agent.TOOL_NAME
                       for block in data.get("content") or [])
            stop = data.get("stop_reason")
            usage = data.get("usage") or {}
            span.set_attributes({
                "openinference.span.kind": "LLM",  # no llm.model_name: Phoenix derives no cost
                "tarifhub.call": self.calls,
                "tarifhub.decision": "search" if asks else "answer",
                "tarifhub.stop_reason": stop if stop in evidence_agent.STOP_REASONS else "unknown",
                "tarifhub.http_status": response.status_code,
                "tarifhub.mocked_usage.input_tokens": usage.get("input_tokens", 0),
                "tarifhub.mocked_usage.output_tokens": usage.get("output_tokens", 0),
                "tarifhub.response_sha256_prefix": _sha256(response.text)[:16],
                "tarifhub.synthetic_delay_ms": SYNTHETIC_DELAY_S["generation_call"] * 1000,
                "tarifhub.elapsed_ms": round(elapsed_ms, 3),
            })
        return response


def traced_search(tracer, search):
    """``search`` (``evidence_search.search_commentary``) inside one span of codes and counts."""

    def traced(arguments, state, *, retriever, passages, limits):
        with tracer.start_as_current_span("search_commentary", record_exception=False,
                                          set_status_on_exception=False) as span:
            started = time.perf_counter()
            result = search(arguments, state, retriever=retriever, passages=passages,
                            limits=limits)
            elapsed_ms = (time.perf_counter() - started) * 1000
            query = arguments.get("query") if isinstance(arguments, Mapping) else None
            span.set_attributes({
                "openinference.span.kind": "TOOL",
                "tool.name": evidence_agent.TOOL_NAME,
                "tarifhub.search.outcome": result.outcome,
                # The model asks for no number: the limit is the tool's own, new passages at most.
                "tarifhub.search.requested_limit": limits.per_search,
                "tarifhub.search.window": limits.window,
                "tarifhub.search.new_passages": len(result.passages),
                "tarifhub.search.passage_ids": list(result.passages),
                "tarifhub.search.rounds_left": result.record["rounds_left"],
                "tarifhub.search.query_sha256_prefix": (_sha256(query)[:16]
                                                        if isinstance(query, str) else "none"),
                "tarifhub.synthetic_delay_ms": SYNTHETIC_DELAY_S["query_embedding"] * 1000,
                "tarifhub.elapsed_ms": round(elapsed_ms, 3),
            })
            return result

    return traced


def _loopback_only() -> None:
    """Refuse, for this process, every Python socket ``connect`` to a non-loopback address."""

    connect = socket.socket.connect

    def guarded(sock: socket.socket, address) -> None:
        if not (isinstance(address, tuple) and address[0] in LOOPBACK):
            raise ConnectionRefusedError(f"refused: {address!r} is not a loopback address")
        connect(sock, address)

    socket.socket.connect = guarded


def _traced_case(tracer, folder: Path) -> tuple[evidence_agent.CaseResult, dict]:
    """Run the synthetic case once under a root span, on temporary books in ``folder``; return
    its result and the synthetic passage records."""

    books = folder / "books"
    books.mkdir()
    baseline = books / evidence_agent.HISTORICAL_LEDGER
    baseline.write_bytes((evidence_agent.BOOKS / evidence_agent.HISTORICAL_LEDGER).read_bytes())
    spending = evidence_agent.Spending(
        ledger=books / evidence_agent.ACTIVE_LEDGER, baseline=baseline,
        baseline_sha256=evidence_agent.HISTORICAL_SHA256, artifacts=folder / "artifacts")
    retriever, passages, _ = world(
        on_query=lambda: time.sleep(SYNTHETIC_DELAY_S["query_embedding"]))
    task = evidence_agent.AgentTask(case_id=CASE_ID, question=QUESTION, editions=(JUL,),
                                    passages=tuple(passages[pid] for pid in INITIAL))
    transport = TracedTransport(httpx.MockTransport(ScriptedProvider()), tracer)
    client = generation.client("offline-placeholder-key", generation.Config(),
                               http_client=httpx.Client(transport=transport))
    saved = evidence_agent.BOOKS, evidence_search.search_commentary
    evidence_agent.BOOKS = books  # the agent accepts no other books: these temporary ones
    evidence_search.search_commentary = traced_search(tracer, evidence_search.search_commentary)
    try:
        with tracer.start_as_current_span("evidence_agent case", record_exception=False,
                                          set_status_on_exception=False) as root:
            started = time.perf_counter()
            result = evidence_agent.run_case(task, client=client, retriever=retriever,
                                             passages=passages, clock=time.monotonic,
                                             budget_s=BUDGET_S, spending=spending)
            elapsed_ms = (time.perf_counter() - started) * 1000
            record = result.record
            root.set_attributes({
                "openinference.span.kind": "AGENT",
                "tarifhub.case": CASE_ID,
                "tarifhub.condition": record["condition"],
                "tarifhub.outcome": result.outcome,
                "tarifhub.detail": result.detail or "none",
                "tarifhub.answer_status": result.status or "none",
                "tarifhub.calls": record["generation_calls"],
                "tarifhub.searches": len(record["searches"]),
                "tarifhub.supplied_passages": len(record["supplied"]),
                "tarifhub.cited_passage_ids": record.get("cited", []),
                "tarifhub.question_sha256_prefix": _sha256(QUESTION)[:16],
                "tarifhub.loop_elapsed_ms": round(record["elapsed_s"] * 1000, 3),
                "tarifhub.synthetic": True,
                "tarifhub.elapsed_ms": round(elapsed_ms, 3),
            })
            root.set_status(Status(StatusCode.OK if result.outcome == "answer"
                                   else StatusCode.ERROR))
    finally:
        evidence_agent.BOOKS, evidence_search.search_commentary = saved
    return result, passages


def _problems(result: evidence_agent.CaseResult, spans: list) -> list[str]:
    """What keeps this run from being the scripted one: one search, then an accepted answer."""

    record = result.record
    calls = [s for s in spans if s.name.startswith("generation call")]
    problems = []
    if (result.outcome, record["generation_calls"]) != ("answer", 2):
        problems.append(f"the case ended {result.outcome} ({result.detail}) after "
                        f"{record['generation_calls']} generation calls")
    if [s["outcome"] for s in record["searches"]] != ["passages"]:
        problems.append("the case did not make exactly one search that returned passages")
    if [s.attributes["tarifhub.decision"] for s in calls] != ["search", "answer"]:
        problems.append("the traced decisions are not a search, then an answer")
    if [s.attributes["tarifhub.response_sha256_prefix"] for s in calls] != [
            (c.get("response_sha256") or "")[:16] for c in record["calls"]]:
        problems.append("the traced responses are not the ones the loop recorded")
    if len(spans) != 4 or len({s.context.trace_id for s in spans}) != 1:
        problems.append("the spans are not one trace of four")
    return problems


def _carriers(spans: list, texts: list[str]) -> list[str]:
    """The names of the spans that carry any of ``texts`` in a name, attribute or event."""

    found = []
    for span in spans:
        values = [span.name, *map(str, span.attributes.values()),
                  *map(str, span.resource.attributes.values()),
                  *(str(v) for event in span.events for v in (event.attributes or {}).values())]
        if any(text in value for text in texts for value in values):
            found.append(span.name)
    return found


def main() -> int:
    if any(os.environ.get(name) for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")):
        print("refused: a provider credential is set; run with env -u ANTHROPIC_API_KEY "
              "-u ANTHROPIC_AUTH_TOKEN", file=sys.stderr)
        return 3
    _loopback_only()
    memory = InMemorySpanExporter()
    tracing = TracerProvider(resource=Resource.create({
        "service.name": "tarifhub-trace-demo", "openinference.project.name": PROJECT}))
    tracing.add_span_processor(SimpleSpanProcessor(memory))
    with tempfile.TemporaryDirectory(prefix="tarifhub-trace-demo-") as folder:
        result, passages = _traced_case(tracing.get_tracer(__name__), Path(folder))
    spans = sorted(memory.get_finished_spans(), key=lambda s: s.start_time)
    tracing.shutdown()
    texts = [MARKER, QUESTION, *SEARCH.values(), *(c["text"] for c in ANSWER["claims"]),
             *(p["text"] for p in passages.values())]
    problems, carriers = _problems(result, spans), _carriers(spans, texts)
    if carriers:
        problems.append(f"run text in span(s) {', '.join(carriers)}")
    if problems:
        for problem in problems:
            print(f"failed, nothing exported: {problem}", file=sys.stderr)
        return 1
    session = requests.Session()
    session.trust_env = False  # no proxy, no netrc: the spans go to ENDPOINT and nowhere else
    exporter = OTLPSpanExporter(endpoint=ENDPOINT, timeout=10, session=session)
    try:
        exported = exporter.export(spans)
    finally:
        exporter.shutdown()
    if exported is not SpanExportResult.SUCCESS:
        print(f"failed: the export to {ENDPOINT} did not succeed", file=sys.stderr)
        return 1
    root = next(s for s in spans if s.parent is None)
    print(json.dumps({
        "project": PROJECT, "endpoint": ENDPOINT, "marker": MARKER,
        "trace_id": format(root.context.trace_id, "032x"),
        "spans": [{"name": s.name, "span_id": format(s.context.span_id, "016x"),
                   "parent_id": format(s.parent.span_id, "016x") if s.parent else None,
                   "attributes": dict(s.attributes)} for s in spans],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
