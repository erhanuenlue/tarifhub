"""Offline tests for the pilot's step commands: a step never overwrites what an earlier run wrote.

The recorded run's public record, plan, rerun record and ledger are evidence, and the local
review sheet is what the human review was checked against, so running a step again must refuse
instead of replacing them. Output folders are temporary; no key, no network, no model.

    uv run --project services/ingestion --frozen --offline --extra ai --extra dev \\
        python -m pytest tools/commentary_rag -q
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import threading
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generation
import run_generation

TAG = "2026-01-01"


@pytest.fixture
def folders(tmp_path, monkeypatch):
    """Point the step outputs at empty temporary folders; the live key is never present."""
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_WORKSPACE_ID"):
        monkeypatch.delenv(name, raising=False)
    results, local = tmp_path / "results", tmp_path / "local"
    results.mkdir()
    local.mkdir()
    monkeypatch.setattr(run_generation, "RESULTS", results)
    monkeypatch.setattr(run_generation, "LOCAL", local)
    monkeypatch.setattr(run_generation, "LEDGER", results / "generation-ledger.jsonl")
    return results, local


def test_report_refuses_to_overwrite_a_recorded_run(folders):
    results, _ = folders
    record = results / f"{TAG}-generation.json"
    record.write_text("recorded\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="refused: .*already exists"):
        run_generation.main(["report", "--tag", TAG, "--prepared", TAG])

    assert record.read_text(encoding="utf-8") == "recorded\n"


@pytest.mark.parametrize(("argv", "folder", "name"), [
    (["prepare"], "results", f"{TAG}-retrieval-rerun.json"),
    (["prepare"], "local", f"{TAG}-contexts.json"),
    (["plan"], "results", f"{TAG}-generation-plan.json"),
    (["run"], "local", f"{TAG}-generation/run-result.json"),
    (["run"], "results", f"{TAG}-generation.json"),
    (["run"], "local", f"{TAG}-review-sheet.md"),
    (["report", "--sheet-only"], "local", f"{TAG}-review-sheet.md"),
])
def test_every_step_refuses_before_any_work_when_its_output_exists(folders, argv, folder, name):
    existing = dict(zip(("results", "local"), folders, strict=True))[folder] / name
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("recorded\n", encoding="utf-8")

    # No key, no contexts, no model: a step that went on would fail differently.
    with pytest.raises(SystemExit, match="refused: .*already exists"):
        run_generation.main([*argv, "--tag", TAG, "--prepared", TAG])

    assert existing.read_text(encoding="utf-8") == "recorded\n"


JUL, JAN = "2026-07-01", "2026-01-01"
TEXTS = {"jul/p6/1": "Der Tarif der Position 1368.00 steigt auf 64.4 TP.",
         "jul/p7/1": "Diese Änderung tritt per 1. Juli 2026 in Kraft."}
QUESTION = "Was gilt für 1368.00?"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def passage(pid: str, rank: int) -> dict:
    page = int(pid.split("/p")[1].split("/", maxsplit=1)[0])
    return {"rank": rank, "passage_id": pid, "edition": JUL, "page": page,
            "page_label": str(page), "section": "2.5", "section_title": "Screening",
            "document_title": "Kommentar per 01.07.26", "text": TEXTS[pid], "context": None,
            "text_sha256": sha256(TEXTS[pid])}


ITEM = {"case": "D", "question": QUESTION, "editions": [JUL],
        "passages": [passage("jul/p6/1", 1), passage("jul/p7/1", 2)],
        "evidence": [["jul/p6/1"]],
        "rubric": {"expected_status": "answered", "review_focus": "the new tariff",
                   "required": [{"id": "D-R1", "claim": "Der Tarif steigt auf 64.4 TP.",
                                 "support": [{"edition": JUL, "page": 6, "quote": "64.4 TP"}],
                                 "covering": ["jul/p6/1"], "terms": [["64.4"]]}],
                   "optional": []}}


@pytest.fixture
def prepared(folders, tmp_path, monkeypatch):
    """A saved retrieval record and the contexts prepared from it, as ``prepare`` leaves them."""
    saved = {
        "k": 5,
        "passages": [{k: p[k] for k in ("passage_id", "edition", "page", "page_label", "section",
                                        "section_title", "text_sha256")} | {"context_sha256": None}
                     for p in ITEM["passages"]],
        "cases": [{"id": "D", "question": QUESTION, "target_editions": [JUL]}],
        "runs": [{"case": "D", "method": "hybrid", "mode": "edition_filter",
                  "ranking": [["jul/p6/1", 0.032], ["jul/p7/1", 0.031]]}],
        "run": {"documents": [{"edition": JUL, "title": "Kommentar per 01.07.26"}]},
    }
    corrected = tmp_path / "corrected.json"
    corrected.write_text(json.dumps(saved), encoding="utf-8")
    monkeypatch.setattr(run_generation, "CORRECTED", corrected)
    results, local = folders

    def write(item: dict) -> None:
        (local / f"{TAG}-contexts.json").write_text(json.dumps({
            "corrected_record_sha256": "0" * 64, "rerun_record_sha256": "0" * 64,
            "reproduction": {}, "items": [item]}), encoding="utf-8")

    write(ITEM)
    return results, local, write


def tampered(change: str) -> dict:
    item = copy.deepcopy(ITEM)
    first, second = item["passages"]
    if change == "table context":  # text of another edition slipped in as a table heading
        second["context"] = "Kommentar per 01.01.26: Tabelle der Januar-Ausgabe"
    elif change == "edition":
        first["edition"] = JAN
    elif change == "page":
        first["page"] = 9
    elif change == "section title":
        first["section_title"] = "Another section"
    elif change == "document title":
        first["document_title"] = "Kommentar per 01.01.26"
    elif change == "question":
        item["question"] = "Was gilt für 1034.00?"
    elif change == "editions":
        item["editions"] = [JAN, JUL]
    return item


@pytest.mark.parametrize("change", ["table context", "edition", "page", "section title",
                                    "document title", "question", "editions"])
def test_run_refuses_a_context_that_differs_from_the_saved_record_in_any_part(prepared, change):
    _, _, write = prepared
    write(tampered(change))

    with pytest.raises(SystemExit, match="refused: D .*saved record"):
        run_generation.main(["run", "--tag", TAG, "--prepared", TAG])


def test_run_accepts_contexts_equal_to_the_saved_record(prepared):
    # It passes every context check and stops only at the missing key: nothing is sent.
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY is not set"):
        run_generation.main(["run", "--tag", TAG, "--prepared", TAG])


ANSWER = {"status": "answered", "missing_evidence": [],
          "claims": [{"text": "Der Tarif steigt auf 64.4 TP.", "citations": ["jul/p6/1"]}]}


def response(answer: dict) -> str:
    return json.dumps({"model": "claude-opus-5-5", "stop_reason": "end_turn", "content": [
        {"type": "text", "text": json.dumps(answer, ensure_ascii=False)}]}, ensure_ascii=False)


def finished(prepared, *, saved_here: bool, in_result: bool) -> tuple:
    """D answered validly as D-1, its request and response saved under this tag or elsewhere,
    and listed in this tag's run result or not (an earlier run, or an interrupted one)."""
    results, local, _ = prepared
    text = response(ANSWER)
    settle = {"event": "settle", "attempt": "D-1", "case": "D", "outcome": "valid",
              "status": "answered", "usage": {"input_tokens": 1000, "output_tokens": 2000},
              "cost_usd": 0.044, "response_sha256": sha256(text), "at": "2026-01-01T00:00:00+00:00"}
    (results / "generation-ledger.jsonl").write_text(
        json.dumps({"event": "reserve", "attempt": "D-1", "case": "D", "reserved_usd": 0.6444})
        + "\n" + json.dumps(settle) + "\n", encoding="utf-8")
    artifacts = local / f"{TAG}-generation"
    (artifacts / "responses").mkdir(parents=True)
    if saved_here:  # a run saves an attempt's request and response before settling it
        (artifacts / "requests").mkdir()
        (artifacts / "requests" / "D-1.json").write_text("{}", encoding="utf-8")
        (artifacts / "responses" / "D-1.json").write_text(text, encoding="utf-8")
    attempts = [{k: v for k, v in settle.items() if k not in ("event", "at")}] if in_result else []
    skipped = [] if in_result else [{"case": "D", "reason": "already answered validly (D-1)"}]
    (artifacts / "run-result.json").write_text(json.dumps({
        "started_at": "s", "finished_at": "f", "plan": [], "attempts": attempts,
        "not_attempted": skipped, "retries_skipped": [], "stopped": None}), encoding="utf-8")
    return results / f"{TAG}-generation.json", local / f"{TAG}-review-sheet.md", artifacts


def test_report_writes_the_record_and_review_sheet_of_a_finished_run(prepared):
    record, sheet, _ = finished(prepared, saved_here=True, in_result=True)

    assert run_generation.main(["report", "--tag", TAG, "--prepared", TAG]) == 0

    written = json.loads(record.read_text(encoding="utf-8"))
    assert [(a["case"], a["status"], a["claims"]) for a in written["answers"]] == [
        ("D", "answered", 1)]
    assert "Der Tarif steigt auf 64.4 TP." in sheet.read_text(encoding="utf-8")


def test_report_refuses_a_saved_response_that_no_longer_matches_its_recorded_hash(prepared):
    record, sheet, artifacts = finished(prepared, saved_here=True, in_result=True)
    altered = {**ANSWER, "claims": [{"text": "Der Tarif sinkt.", "citations": ["jul/p6/1"]}]}
    (artifacts / "responses" / "D-1.json").write_text(response(altered), encoding="utf-8")

    with pytest.raises(SystemExit, match="refused: .*D-1.*recorded hash"):
        run_generation.main(["report", "--tag", TAG, "--prepared", TAG])

    assert not record.exists() and not sheet.exists()


def test_a_run_reports_only_its_own_attempts_not_a_case_answered_in_an_earlier_run(prepared):
    record, _, _ = finished(prepared, saved_here=False, in_result=False)  # saved under another tag

    run_generation.main(["report", "--tag", TAG, "--prepared", TAG])

    written = json.loads(record.read_text(encoding="utf-8"))
    assert (written["attempts"], written["answers"]) == ([], [])
    assert [(c["case"], c["outcome"]) for c in written["checks"]] == [("D", "not_attempted")]
    assert written["run"]["not_attempted"] == [
        {"case": "D", "reason": "already answered validly (D-1)"}]


def test_a_step_reads_the_contexts_prepared_under_its_own_tag_by_default(prepared):
    # prepare --tag T wrote T's contexts; run --tag T must use them, not another day's.
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY is not set"):
        run_generation.main(["run", "--tag", TAG])


def test_a_resumed_run_still_reports_an_answer_settled_before_its_interruption(prepared):
    # D-1 was saved under this tag and settled, then the run stopped before writing its result;
    # the resumed run skipped D as already answered.
    record, sheet, _ = finished(prepared, saved_here=True, in_result=False)

    run_generation.main(["report", "--tag", TAG, "--prepared", TAG])

    written = json.loads(record.read_text(encoding="utf-8"))
    assert [a["attempt"] for a in written["attempts"]] == ["D-1"]
    assert [(c["case"], c["outcome"]) for c in written["checks"]] == [("D", "valid")]
    assert "Der Tarif steigt auf 64.4 TP." in sheet.read_text(encoding="utf-8")


def test_a_run_refused_by_another_runs_lock_publishes_nothing(prepared, monkeypatch):
    results, local, _ = prepared
    entered, release = threading.Event(), threading.Event()

    def provider(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/messages/count_tokens":
            return httpx.Response(200, json={"input_tokens": 1000})
        entered.set()
        release.wait(10)
        return httpx.Response(200, headers={"request-id": "req_test"}, json={
            **json.loads(response(ANSWER)), "id": "msg_test", "type": "message",
            "role": "assistant", "stop_sequence": None,
            "usage": {"input_tokens": 1000, "output_tokens": 2000}})

    monkeypatch.setattr(run_generation, "_client", lambda config: generation.client(
        "test-key", config, http_client=httpx.Client(transport=httpx.MockTransport(provider))))
    outputs = (local / f"{TAG}-generation" / "run-result.json", results / f"{TAG}-generation.json",
               local / f"{TAG}-review-sheet.md")
    done: dict = {}
    first = threading.Thread(target=lambda: done.update(code=run_generation.main(["run", "--tag", TAG])))
    first.start()
    assert entered.wait(10)
    try:
        second = run_generation.main(["run", "--tag", TAG])
        published_by_second = [p.name for p in outputs if p.exists()]
    finally:
        release.set()
        first.join(10)

    assert (second, published_by_second) == (2, [])
    assert done["code"] == 0
    record = json.loads(outputs[1].read_text(encoding="utf-8"))
    assert [(a["case"], a["status"]) for a in record["answers"]] == [("D", "answered")]
