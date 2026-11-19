"""Offline tests for the one-question runner of the evidence-seeking agent (ADR-026).

The runner's command is driven end to end: a tiny real commentary corpus (generated PDFs and a
manifest, read by the real corpus builder and ``pdftotext``), the real retriever, the real
agent loop and the real ``anthropic`` client on an ``httpx.MockTransport`` with a fake key. Only
the external boundaries are stand-ins: the e5 model (a vector per text, a word count for tokens)
and the provider's HTTP side. The books are temporary: a stand-in historical ledger and the
active ledger beside it; the repository's ledgers, ``results/`` and ``local/`` are checked to be
unchanged after every test.

The corpus is built so that every ranking is worked out by hand. Each passage has the same
number of terms and the question's only corpus term is ``Pauschale``, so BM25 orders passages by
how often it occurs, equal counts by passage ID. The stand-in embedder gives a passage the
vector ``[n, 1]`` for ``n`` occurrences and the query ``[1, 0]``: the cosine ``n / sqrt(n^2 + 1)``
rises with ``n``, so the dense order is the same and so is their reciprocal rank fusion. July
(page 2, sections 2.1 to 2.7) has 2, 6, 0, 4, 7, 1 and 5 occurrences: the July top 5 is 2.5, 2.2,
2.7, 2.4, 2.1. January's one passage has 9, so it leads whenever January is selected.

    UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" uv run \\
        --project services/ingestion --frozen --extra ai --extra dev \\
        python -m pytest tools/commentary_rag -q
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import types
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import evidence_agent
import run_question
from test_corpus import make_repo
from test_evidence_agent import (Clock, Provider, _dearest, _fail_opening, _message, books, final,
                                 search_call)

JUL, JAN = "2026-07-01", "2026-01-01"
HERE = Path(__file__).resolve().parent
REAL_CLIENT = run_question._client  # before any test replaces it
REAL_E5 = run_question._e5  # the real loader, behind the stand-in every other test uses
QUESTION = "Welche Pauschale gilt?"
PLACES = ["Aarau", "Basel", "Bern", "Chur", "Davos", "Genf", "Lugano", "Luzern"]
# section, title, occurrences of "Pauschale"
JULY_SECTIONS = [("2.1", "Alpha", 2), ("2.2", "Beta", 6), ("2.3", "Gamma", 0),
                 ("2.4", "Delta", 4), ("2.5", "Epsilon", 7), ("2.6", "Zeta", 1),
                 ("2.7", "Eta", 5)]
JUL_TOP5 = [f"{JUL}/p2/s{s}/1" for s in ("2.5", "2.2", "2.7", "2.4", "2.1")]
BOTH_TOP5 = [f"{JAN}/p2/s2.1/1", *JUL_TOP5[:4]]


def _body(hits: int, place: str) -> str:
    return " ".join(["Pauschale"] * hits + ["Analyse"] * (9 - hits) + [place])


def _pages() -> dict[str, list[list[str]]]:
    july = [["Kommentar zu den Änderungen", "per 1. Juli 2026"],
            [line for (section, title, hits), place in zip(JULY_SECTIONS, PLACES, strict=False)
             for line in (f"{section} Position 100{section[-1]}.00 {title}", _body(hits, place))]
            + ["Seite 2 von 2"]]
    january = [["Kommentar zu den Änderungen", "per 1. Januar 2026"],
               ["2.1 Position 2001.00 Theta", _body(9, PLACES[7]), "Seite 2 von 2"]]
    return {JUL: july, JAN: january}


class StandInE5:
    """The e5 boundary: a vector per text from its ``Pauschale`` count, word-count tokens."""

    def __init__(self, limit: int = 512) -> None:
        self.limit = limit
        self.queries: list[str] = []
        self.provenance = {"model": "stand-in e5 (tests)"}

    @property
    def embedder(self):
        """The port the retriever embeds with: this stand-in itself."""
        return self

    def embed(self, text: str) -> list[float]:
        """A passage vector, ``[n, 1]`` for ``n`` occurrences of ``Pauschale``."""
        return [float(text.split().count("Pauschale")), 1.0]

    def embed_query(self, text: str) -> list[float]:
        """The query vector, the same for every question; the question is logged."""
        self.queries.append(text)
        return [1.0, 0.0]

    def count(self, text: str, kind: str) -> int:
        """Stand-in tokens: one per word plus two for the prefix and special tokens."""
        return len(text.split()) + 2


def _tree(folder: Path) -> dict[str, str]:
    """Every file under ``folder`` by relative path, with its SHA-256."""
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Temporary books, outputs and e5; no live credential; the real folders left unchanged."""
    real = {name: _tree(HERE / name) for name in ("results", "local")}
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                 "ANTHROPIC_WORKSPACE_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(evidence_agent, "BOOKS", tmp_path / "books")
    monkeypatch.setattr(evidence_agent, "HISTORICAL_SHA256", evidence_agent.HISTORICAL_SHA256)
    books()  # a stand-in historical ledger, pinned for this test only
    monkeypatch.setattr(run_question, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(run_question, "LOCAL", tmp_path / "local")
    e5 = StandInE5()
    loads: list[int] = []
    monkeypatch.setattr(run_question, "_e5", lambda: loads.append(1) or e5)
    clock = Clock()
    monkeypatch.setattr(run_question, "CLOCK", clock)

    def no_client(config):
        raise AssertionError("this test builds no provider client")

    monkeypatch.setattr(run_question, "_client", no_client)
    manifest = make_repo(tmp_path / "repo", _pages())
    yield {"tmp": tmp_path, "e5": e5, "loads": loads, "clock": clock, "manifest": manifest}
    assert {name: _tree(HERE / name) for name in ("results", "local")} == real


def argv(env, step: str, *, case: str = "Q1", editions=(JUL,),  # noqa: PLR0913 - keyword-only
         question: str = QUESTION, tag: str = "2026-11-18", budget: str = "600") -> list[str]:
    """The command line of one invocation, every argument given explicitly."""
    return [step, "--case-id", case, "--question", question, "--tag", tag,
            "--time-budget-s", budget, "--manifest", str(env["manifest"]),
            *(a for e in editions for a in ("--edition", e))]


def written(env) -> dict[str, str]:
    """Every file the runner or the agent wrote (outside the generated corpus and the
    stand-in historical ledger), with its SHA-256."""
    return {path: digest for path, digest in _tree(env["tmp"]).items()
            if not path.startswith("repo/") and Path(path).name != evidence_agent.HISTORICAL_LEDGER}


@pytest.mark.parametrize(("editions", "top"), [((JUL,), JUL_TOP5), ((JAN, JUL), BOTH_TOP5)],
                         ids=["july_only", "both_editions"])
def test_prepare_ranks_the_question_afresh_in_the_selected_editions_and_sends_and_writes_nothing(
        isolated, capsys, editions, top):
    code = run_question.main(argv(isolated, "prepare", editions=editions))

    assert code == 0
    shown = json.loads(capsys.readouterr().out)
    assert [p["passage_id"] for p in shown["initial_retrieval"]["passages"]] == top
    assert isolated["e5"].queries == [QUESTION]  # ranked for this question, now
    assert written(isolated) == {}  # no output, no active ledger


def live(env, monkeypatch, *replies, **options) -> Provider:
    """The provider's HTTP side for ``run``, scripted with ``replies``, on the test's clock."""
    provider = Provider(env["clock"], *replies, **options)
    monkeypatch.setattr(run_question, "_client", lambda config: provider.client())
    return provider


def ledger(env) -> list[dict]:
    path = env["tmp"] / "books" / evidence_agent.ACTIVE_LEDGER
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def outputs(env, *, tag: str = "2026-11-18", case: str = "Q1") -> tuple[Path, Path]:
    """The public record and the local folder of one run."""
    name = f"{tag}-question-{case}"
    return env["tmp"] / "results" / f"{name}.json", env["tmp"] / "local" / name


def sent_passages(body: dict) -> list[str]:
    """The passage IDs of a request's first (user) message, in the order given."""
    return re.findall(r'<passage id="([^"]+)"', body["messages"][0]["content"])


ANSWERED = (("Die Pauschale Epsilon gilt.", [JUL_TOP5[0]]),)


def test_run_answers_from_the_fresh_top_five_keeps_the_answer_local_and_publishes_metadata(
        isolated, monkeypatch, capsys):
    provider = live(isolated, monkeypatch, final(*ANSWERED))

    code = run_question.main(argv(isolated, "run"))

    assert code == 0
    assert (len(provider.counts), len(provider.creates)) == (1, 1)
    (body,) = provider.creates
    assert sent_passages(body) == JUL_TOP5
    assert f"<frage>{QUESTION}</frage>\n<ausgaben>{JUL}</ausgaben>" in body["messages"][0]["content"]
    assert 'dokument="Kommentar zu den Änderungen per 1. Juli 2026"' in \
        body["messages"][0]["content"]
    public, local = outputs(isolated)
    answer = {"status": "answered", "missing_evidence": [],
              "claims": [{"text": "Die Pauschale Epsilon gilt.", "citations": [JUL_TOP5[0]]}]}
    assert json.loads((local / "answer.json").read_text("utf-8")) == answer
    kept = json.loads((local / "result.json").read_text("utf-8"))
    assert (kept["question"], kept["local"]["requests"]) == (QUESTION, [body])
    record = json.loads(public.read_text("utf-8"))
    assert record["status"] == {"execution": "answer", "detail": None, "answer": "answered",
                                "accounting": "priced"}
    assert [p["passage_id"] for p in record["initial_retrieval"]["passages"]] == JUL_TOP5
    assert record["agent"]["cited"] == [JUL_TOP5[0]]
    assert QUESTION not in public.read_text("utf-8")  # the question is published by hash only
    assert [(e["event"], e.get("attempt")) for e in ledger(isolated)] == [
        ("baseline", None), ("reserve", "Q1-call1"), ("settle", "Q1-call1")]
    shown = json.loads(capsys.readouterr().out)
    assert (shown["exit_code"], shown["answer_status"], shown["accounting"]["status"]) == (
        0, "answered", "priced")


def test_a_case_in_the_books_is_never_sent_again_whatever_the_output_tag(
        isolated, monkeypatch, capsys):
    live(isolated, monkeypatch, final(*ANSWERED))
    assert run_question.main(argv(isolated, "run")) == 0
    before = written(isolated)
    capsys.readouterr()
    again = live(isolated, monkeypatch, final(*ANSWERED))

    code = run_question.main(argv(isolated, "run", tag="2026-11-19"))

    # The case ID is the accounting identity: a new tag names new files, not a new case.
    assert code == 3
    assert (again.counts, again.creates) == ([], [])
    assert written(isolated) == before  # the refused rerun keeps and publishes nothing
    shown = json.loads(capsys.readouterr().out)
    assert (shown["execution"], shown["exit_code"]) == (
        {"outcome": "refused", "detail": "already_run"}, 3)


@pytest.mark.parametrize("step", ["prepare", "run"])
@pytest.mark.parametrize("existing", ["public", "local", "local_file"])
def test_existing_outputs_are_refused_before_the_model_loads_or_anything_is_sent(
        isolated, monkeypatch, step, existing):
    public, local = outputs(isolated)
    if existing == "public":
        public.parent.mkdir(parents=True)
        public.write_text("recorded\n", encoding="utf-8")
    elif existing == "local":  # an earlier run's request and response artifacts
        (local / "requests").mkdir(parents=True)
        (local / "requests" / "Q1-call1.json").write_text("{}", encoding="utf-8")
    else:  # a file where the run's local folder would go
        local.parent.mkdir(parents=True)
        local.write_text("not a folder", encoding="utf-8")
    before = written(isolated)
    provider = live(isolated, monkeypatch, final(*ANSWERED))

    code = run_question.main(argv(isolated, step))

    assert code == 3
    assert (isolated["loads"], provider.counts, provider.creates) == ([], [], [])
    assert written(isolated) == before


def exit_code(argv_: list[str]) -> int:
    """The command's exit code, whether it returns it or argparse exits with it."""
    try:
        return run_question.main(argv_)
    except SystemExit as stop:
        return stop.code


@pytest.mark.parametrize("change", [
    {"budget": "nan"}, {"budget": "inf"}, {"budget": "-inf"}, {"budget": "0"}, {"budget": "-1"},
    {"question": ""}, {"question": "   "},
    {"case": "../Q1"}, {"case": "Q/1"}, {"case": ".Q1"}, {"case": ""},
    {"tag": "../2026-11-18"}, {"tag": "2026/11/18"},
    {"editions": (JUL, JUL)}, {"editions": ("2026-7-1",)}, {"editions": ("Juli",)},
], ids=lambda change: "-".join(f"{k}={v}" for k, v in change.items()))
def test_invalid_input_is_refused_before_the_model_loads_or_anything_is_sent(
        isolated, monkeypatch, change):
    provider = live(isolated, monkeypatch, final(*ANSWERED))

    code = exit_code(argv(isolated, "run", **change))

    assert code == 2
    assert (isolated["loads"], provider.counts, provider.creates) == ([], [], [])
    assert written(isolated) == {}


@pytest.mark.parametrize("change", [
    {"editions": ("2026-04-01",)},  # a well-formed edition the corpus does not have
    {"question": " ".join(["Pauschale"] * 600)},  # 602 stand-in tokens, over the 512 limit
], ids=["unknown_edition", "question_over_the_e5_limit"])
def test_input_the_corpus_or_model_cannot_take_is_refused_unranked_and_untruncated(
        isolated, monkeypatch, change):
    provider = live(isolated, monkeypatch, final(*ANSWERED))

    code = exit_code(argv(isolated, "run", **change))

    assert code == 2
    assert isolated["e5"].queries == []  # never ranked, so never cut to fit
    assert (provider.counts, provider.creates) == ([], [])
    assert written(isolated) == {}


def test_the_live_step_without_a_key_is_refused_before_the_model_loads(
        isolated, monkeypatch, capsys):
    monkeypatch.setattr(run_question, "_client", REAL_CLIENT)  # reads the (absent) key

    code = exit_code(argv(isolated, "run"))

    assert code == 3
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err
    assert (isolated["loads"], written(isolated)) == ([], {})


def test_help_loads_counts_sends_and_writes_nothing(isolated, capsys):
    code = exit_code(["--help"])

    assert code == 0
    shown = capsys.readouterr().out
    assert "prepare" in shown and "run" in shown and "exit codes" in shown
    assert (isolated["loads"], written(isolated)) == ([], {})


UNPRICEABLE = {**final(*ANSWERED)["usage"], "service_tier": "priority"}  # a tier not priced


@pytest.mark.parametrize(("reply", "outcome", "accounting", "code"), [
    ({**final(*ANSWERED), "usage": _dearest(1651)}, "answer", "above_reservation", 5),
    ({**search_call("Pauschale", "Begründung"), "usage": _dearest(1651)}, "spending_stop",
     "above_reservation", 5),
    ({**final(*ANSWERED), "usage": UNPRICEABLE}, "answer", "uncertain", 6),
], ids=["answer_above_its_reservation", "search_above_its_reservation", "answer_unpriceable"])
def test_a_call_not_priced_within_its_reservation_never_exits_0_and_an_answer_stays_local(  # noqa: PLR0913 - parameters
        isolated, monkeypatch, capsys, reply, outcome, accounting, code):
    # Counted at 1,500 tokens, each call reserves 0.71852 USD; the dearest usage one input token
    # beyond the margin costs 0.718529 (test_evidence_agent works both out).
    live(isolated, monkeypatch, reply, final(*ANSWERED))

    assert run_question.main(argv(isolated, "run")) == code

    public, local = outputs(isolated)
    record = json.loads(public.read_text("utf-8"))
    assert (record["status"]["execution"], record["status"]["accounting"]) == (outcome,
                                                                               accounting)
    assert (local / "answer.json").exists() == (outcome == "answer")
    shown = json.loads(capsys.readouterr().out)
    assert (shown["exit_code"], shown["accounting"]["status"]) == (code, accounting)


ERROR = httpx.Response(529, json={"type": "error", "error": {
    "type": "overloaded_error", "message": "SENTINEL provider error text"}})


@pytest.mark.parametrize(("reply", "outcome", "detail", "accounting", "code"), [
    (final(("Januar.", [f"{JAN}/p2/s2.1/1"])), "invalid_answer", "citations_outside_supplied",
     "priced", 4),
    (search_call("Pauschale", "Begründung", name="another_tool"), "protocol_error",
     "unknown_tool", "priced", 4),
    ((700.0, final(*ANSWERED)), "deadline", "after_generation", "priced", 4),
    (ERROR, "provider_error", "http_529", "uncertain", 6),
], ids=["citation_outside_the_supplied_passages", "unknown_tool", "late_answer",
        "provider_error"])
def test_a_failed_case_ends_once_with_a_nonzero_exit_and_is_kept_as_it_ended(  # noqa: PLR0913 - parameters
        isolated, monkeypatch, reply, outcome, detail, accounting, code):
    provider = live(isolated, monkeypatch, reply, final(*ANSWERED))

    assert run_question.main(argv(isolated, "run")) == code  # a 600 s budget

    assert len(provider.creates) == 1  # nothing retried
    public, local = outputs(isolated)
    assert json.loads(public.read_text("utf-8"))["status"] == {
        "execution": outcome, "detail": detail, "answer": None, "accounting": accounting}
    assert not (local / "answer.json").exists()
    assert (local / "responses" / "Q1-call1.json").exists()


SENTINEL_QUESTION = "Welche Pauschale gilt? SENTINEL-FRAGE"


@pytest.mark.parametrize("replies", [
    (search_call("Pauschale SENTINEL-QUERY", "SENTINEL-SEEKING"),
     final(("SENTINEL-ANSWER", [JUL_TOP5[0], f"{JUL}/p2/s2.6/1"]),
           missing=["SENTINEL-MISSING"])),
    (ERROR,),
], ids=["search_then_answer", "provider_error"])
def test_the_public_record_holds_metadata_only_and_everything_else_stays_local(
        isolated, monkeypatch, replies):
    provider = live(isolated, monkeypatch, *replies)

    code = run_question.main(argv(isolated, "run", question=SENTINEL_QUESTION))

    if len(replies) == 2:
        # The search ran over the same corpus and retriever: the question, then the model's
        # query, were embedded; 2.6 (rank 6) came back and its citation was accepted.
        assert code == 0
        assert isolated["e5"].queries == [SENTINEL_QUESTION, "Pauschale SENTINEL-QUERY"]
        result = provider.creates[1]["messages"][-1]["content"][0]
        assert result["type"] == "tool_result"
        assert f'<passage id="{JUL}/p2/s2.6/1"' in result["content"]
    public, local = outputs(isolated)
    text = public.read_text("utf-8")
    record = json.loads(text)
    assert set(record) == {"run", "initial_retrieval", "agent", "answer", "status", "notes"}
    passage_text = _body(7, "Davos")  # section 2.5, ranked first and always sent
    for private in ("SENTINEL", passage_text, "<passage", "Begründung"):
        assert private not in text
    assert record["run"]["question_sha256"] == hashlib.sha256(
        SENTINEL_QUESTION.encode("utf-8")).hexdigest()
    kept = (local / "result.json").read_text("utf-8")
    assert all(s in kept for s in ("SENTINEL-FRAGE", passage_text))
    assert ("SENTINEL-QUERY" in kept and "SENTINEL-ANSWER" in kept) if len(replies) == 2 \
        else "SENTINEL provider error text" in kept
    assert len(provider.creates) == len(replies)


def test_a_dev_case_question_brings_none_of_its_evaluation_data_into_the_run(
        isolated, monkeypatch):
    # The D1 question verbatim: its gold evidence, reference expectation and rubric must not
    # reach the request, the agent or any output. None of these strings is in the corpus.
    case = json.loads((HERE / "cases.json").read_text("utf-8"))["cases"][0]
    rubric = json.loads((HERE / "rubric.json").read_text("utf-8"))["cases"][0]
    assert case["id"] == rubric["id"] == "D1"
    scoring = [case["reference_expectation"], case["context_not_required"],
               *(e["quote"] for e in case["evidence"]), rubric["review_focus"],
               *(c["claim"] for c in rubric["required_claims"] + rubric["optional_background"]),
               *(s["quote"] for c in rubric["required_claims"] + rubric["optional_background"]
                 for s in c["support"])]
    provider = live(isolated, monkeypatch, final(*ANSWERED))

    assert run_question.main(argv(isolated, "run", question=case["question"])) == 0

    (body,) = provider.creates
    sent = sent_passages(body)  # no BM25 term in common with the corpus: ranked by the stand-in
    assert len(sent) == 5 and all(pid.startswith(f"{JUL}/") for pid in sent)
    public, local = outputs(isolated)
    seen = json.dumps(provider.counts + provider.creates, ensure_ascii=False) \
        + public.read_text("utf-8") + (local / "result.json").read_text("utf-8")
    assert [s for s in scoring if s in seen] == []


def test_a_public_record_that_cannot_be_written_keeps_the_local_run_and_resends_nothing(
        isolated, monkeypatch, capsys):
    blocker = isolated["tmp"] / "blocker"
    blocker.write_text("a file where the results folder's parent should be\n", "utf-8")
    monkeypatch.setattr(run_question, "RESULTS", blocker / "results")
    provider = live(isolated, monkeypatch, final(*ANSWERED), final(*ANSWERED))

    code = run_question.main(argv(isolated, "run"))

    assert code == 7
    assert len(provider.creates) == 1  # reporting is never repaired by sending again
    _, local = outputs(isolated)
    assert {p.relative_to(local).as_posix() for p in local.rglob("*.json")} == {
        "requests/Q1-call1.json", "responses/Q1-call1.json", "answer.json", "result.json"}
    shown = json.loads(capsys.readouterr().out)
    assert (shown["exit_code"], shown["answer_status"], shown["accounting"]["status"]) == (
        7, "answered", "priced")
    assert [Path(p["path"]).name for p in shown["not_written"]] == [
        "2026-11-18-question-Q1.json"]


def test_artifacts_the_agent_cannot_save_stop_the_case_before_anything_is_sent(
        isolated, monkeypatch):
    blocker = isolated["tmp"] / "blocker"
    blocker.write_text("a file where the local folder's parent should be\n", "utf-8")
    monkeypatch.setattr(run_question, "LOCAL", blocker / "local")
    provider = live(isolated, monkeypatch, final(*ANSWERED))

    code = run_question.main(argv(isolated, "run"))

    # The request could not be saved, so it was neither reserved nor sent (counting is free).
    assert code == 7
    assert (len(provider.counts), provider.creates) == (1, [])
    assert [e["event"] for e in ledger(isolated)] == ["baseline"]


def test_a_question_stopped_before_its_first_reservation_leaves_nothing_and_can_run_again(
        isolated, monkeypatch, capsys):
    rejected = httpx.Response(400, json={"type": "error", "error": {
        "type": "invalid_request_error", "message": "SENTINEL count rejected"}})
    counting = live(isolated, monkeypatch, count_reply=rejected)

    code = run_question.main(argv(isolated, "run"))

    # Counting is free and reserves nothing, so nothing of the case is in the books.
    assert code == 4
    assert (len(counting.counts), counting.creates) == (1, [])
    assert set(written(isolated)) == {f"books/{evidence_agent.ACTIVE_LEDGER}"}  # the pin only
    assert "SENTINEL count rejected" in capsys.readouterr().err  # shown, kept nowhere
    live(isolated, monkeypatch, final(*ANSWERED))
    assert run_question.main(argv(isolated, "run")) == 0  # same case, same tag


def test_an_answer_that_names_the_missing_evidence_is_a_successful_run(
        isolated, monkeypatch, capsys):
    abstaining = final(status="insufficient_evidence", missing=["Die Pauschale ist nicht belegt."])
    live(isolated, monkeypatch, abstaining)

    code = run_question.main(argv(isolated, "run"))

    # An appropriate abstention is an answer, not a failure: exit 0, kept like any answer.
    assert code == 0
    shown = json.loads(capsys.readouterr().out)
    assert (shown["execution"]["outcome"], shown["answer_status"]) == (
        "answer", "insufficient_evidence")
    _, local = outputs(isolated)
    assert json.loads((local / "answer.json").read_text("utf-8"))["status"] == \
        "insufficient_evidence"


def test_an_answer_with_text_utf_8_cannot_encode_is_still_kept_and_published(
        isolated, monkeypatch):
    # The model's JSON may escape a lone surrogate, which parses but cannot be written as UTF-8.
    answer = {"status": "answered", "missing_evidence": [],
              "claims": [{"text": "Pauschale \ud800", "citations": [JUL_TOP5[0]]}]}
    reply = _message([{"type": "text", "text": json.dumps(answer)}], "end_turn")  # escaped
    live(isolated, monkeypatch, reply)

    assert run_question.main(argv(isolated, "run")) == 0

    public, local = outputs(isolated)
    assert json.loads((local / "answer.json").read_text("utf-8")) == answer  # nothing lost
    assert json.loads(public.read_text("utf-8"))["answer"]["claims"] == 1


def test_a_reservation_the_ledger_may_or_may_not_hold_is_reported_as_uncertain_and_kept(
        isolated, monkeypatch, capsys):
    # The first opening of the new active ledger writes its pin, the second the reservation:
    # that one fails. A failure on closing would leave the line in force, and the runner cannot
    # tell which happened.
    _fail_opening(monkeypatch, evidence_agent.BOOKS.resolve() / evidence_agent.ACTIVE_LEDGER,
                  at=2)
    provider = live(isolated, monkeypatch, final(*ANSWERED))

    code = run_question.main(argv(isolated, "run"))

    assert code == 7
    assert provider.creates == []  # never sent
    shown = json.loads(capsys.readouterr().out)
    assert (shown["execution"], shown["accounting"]["status"]) == (
        {"outcome": "persistence_error", "detail": "reservation_not_saved"}, "uncertain")
    _, local = outputs(isolated)
    assert json.loads((local / "result.json").read_text("utf-8"))["status"]["accounting"] == \
        "uncertain"


class MissingModel:
    """The ``sentence_transformers`` boundary when the model's files are not in the cache:
    with Hugging Face offline, loading raises an OSError instead of downloading."""

    attempts: list[str] = []

    def __init__(self, name: str) -> None:
        MissingModel.attempts.append(f"{name} offline={os.environ.get('HF_HUB_OFFLINE')}")
        raise OSError(f"We couldn't connect to 'https://huggingface.co' to load {name}, and "
                      "couldn't find it in the cached files (offline mode is enabled).")


@pytest.mark.parametrize(("boundary", "reason"), [
    ("model_files_missing", "the cached e5 model could not be loaded (OSError"),
    ("package_missing", "fell back to the 16-dim stub"),
])
def test_an_unavailable_e5_model_is_refused_before_any_request_or_reservation(
        isolated, monkeypatch, capsys, boundary, reason):
    # The runner's real loader, run_eval's and the ingestion embedder's: only the
    # sentence_transformers boundary is replaced, so nothing is loaded or downloaded.
    from huggingface_hub import constants  # noqa: PLC0415 - as the documented command sets it
    from tarifhub_ingest.embeddings import embedder  # noqa: PLC0415

    monkeypatch.setattr(run_question, "_e5", REAL_E5)
    monkeypatch.setattr(constants, "HF_HUB_OFFLINE", True)
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):  # set here, so teardown restores
        monkeypatch.setenv(name, "0")  # them; the runner must turn offline mode on itself
    MissingModel.attempts = []
    fake = types.ModuleType("sentence_transformers")
    fake.SentenceTransformer = MissingModel
    monkeypatch.setitem(sys.modules, "sentence_transformers",
                        fake if boundary == "model_files_missing" else None)
    embedder._cached_embedder.cache_clear()  # no model or stub kept from elsewhere
    provider = live(isolated, monkeypatch, final(*ANSWERED))

    try:
        code = run_question.main(argv(isolated, "run"))
    finally:
        embedder._cached_embedder.cache_clear()  # nor a stub left for later tests

    assert code == 3
    assert reason in capsys.readouterr().err
    assert MissingModel.attempts == (["intfloat/multilingual-e5-large offline=1"]
                                     if boundary == "model_files_missing" else [])
    assert (provider.counts, provider.creates) == ([], [])  # nothing counted or sent
    assert written(isolated) == {}  # no ledger, no reservation, no output
