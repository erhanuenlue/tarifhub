"""Offline tests for the Phase 3 comparison runner (``run_comparison.py``): plan and run.

The harness is the one-question runner's: a tiny real commentary corpus (generated PDFs and a
manifest, read by the real corpus builder and ``pdftotext``), the real retriever, the real
agent loop and the real ``anthropic`` client on an ``httpx.MockTransport`` with a fake key.
Only the e5 model (``test_run_question.StandInE5``) and the provider's HTTP side are
stand-ins. The books are temporary; the repository's ``results/`` and ``local/`` are checked
to be unchanged after every test.

Every ranking is worked out by hand. July (page 2) has twelve sections, each one passage with the
same number of terms; the question's only corpus term is ``Pauschale``, which BM25 counts and
the stand-in embedder turns into the vector ``[n, 1]`` (the cosine with the query ``[1, 0]``
rises with ``n``), so BM25, dense and their fusion all order the passages by count. The counts
by section (2.1 to 2.12) are 3, 9, 0, 11, 6, 1, 10, 4, 8, 2, 7 and 5: the July ranking is 2.4,
2.7, 2.2, 2.9, 2.11, 2.5, 2.12, 2.8, 2.1, 2.10 (the top 10), then 2.6 and 2.3. January's one
passage has 12 and would lead any ranking that let it in.

    UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" uv run \\
        --project services/ingestion --frozen --extra ai --extra dev \\
        python -m pytest tools/commentary_rag -q
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import evidence_agent
import generation
import phase4_scoring
import run_comparison
import run_question
from test_corpus import make_repo
from test_coverage_condition import coverage_search, part, unencodable
from test_evidence_agent import (
    Clock,
    Provider,
    _dearest,
    _fail_opening,
    books,
    final,
    search_call,
)
from test_run_question import StandInE5, _tree

JUL, JAN = "2026-07-01", "2026-01-01"
HERE = Path(__file__).resolve().parent
QUESTION = "Welche Pauschale gilt?"
TITLES = [
    "Alpha",
    "Beta",
    "Gamma",
    "Delta",
    "Epsilon",
    "Zeta",
    "Eta",
    "Theta",
    "Iota",
    "Kappa",
    "Lambda",
    "My",
]
PLACES = [
    "Aarau",
    "Basel",
    "Bern",
    "Chur",
    "Davos",
    "Genf",
    "Lugano",
    "Luzern",
    "Sitten",
    "Thun",
    "Uster",
    "Zug",
    "Olten",
]
COUNTS = [
    3,
    9,
    0,
    11,
    6,
    1,
    10,
    4,
    8,
    2,
    7,
    5,
]  # occurrences of "Pauschale" in 2.1 to 2.12
RANKED = [f"{JUL}/p2/s2.{n}/1" for n in (4, 7, 2, 9, 11, 5, 12, 8, 1, 10, 6, 3)]
TOP5, TOP10 = RANKED[:5], RANKED[:10]
# A stand-in Phase 2 ledger: one request priced from its usage at 0.25 USD (a fixed top 5 call).
HISTORY = (
    {"event": "reserve", "attempt": "H-1", "case": "H", "reserved_usd": 0.7},
    {
        "event": "settle",
        "attempt": "H-1",
        "case": "H",
        "cost_usd": 0.25,
        "cost_basis": "usage",
    },
)


def _pages() -> dict[str, list[list[str]]]:
    july = [
        ["Kommentar zu den Änderungen", "per 1. Juli 2026"],
        [
            line
            for n, (title, hits) in enumerate(zip(TITLES, COUNTS, strict=True), start=1)
            for line in (
                f"2.{n} Position 10{n:02d}.00 {title}",
                " ".join(
                    ["Pauschale"] * hits + ["Analyse"] * (12 - hits) + [PLACES[n - 1]]
                ),
            )
        ]
        + ["Seite 2 von 2"],
    ]
    january = [
        ["Kommentar zu den Änderungen", "per 1. Januar 2026"],
        [
            "2.1 Position 2001.00 Omega",
            " ".join(["Pauschale"] * 12 + [PLACES[12]]),
            "Seite 2 von 2",
        ],
    ]
    return {JUL: july, JAN: january}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Temporary books, outputs and e5; no live credential; the real folders left unchanged."""
    real = {name: _tree(HERE / name) for name in ("results", "local")}
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_WORKSPACE_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(evidence_agent, "BOOKS", tmp_path / "books")
    monkeypatch.setattr(
        evidence_agent, "HISTORICAL_SHA256", evidence_agent.HISTORICAL_SHA256
    )
    books(HISTORY)  # a stand-in historical ledger, pinned for this test only
    monkeypatch.setattr(run_comparison, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(run_comparison, "LOCAL", tmp_path / "local")
    e5 = StandInE5()
    loads: list[int] = []
    monkeypatch.setattr(run_question, "_e5", lambda: loads.append(1) or e5)
    clock = Clock()
    monkeypatch.setattr(run_comparison, "CLOCK", clock)

    def no_client(config):
        raise AssertionError("this test builds no provider client")

    monkeypatch.setattr(run_comparison, "_client", no_client)
    manifest = make_repo(tmp_path / "repo", _pages())
    yield {
        "tmp": tmp_path,
        "e5": e5,
        "loads": loads,
        "clock": clock,
        "manifest": manifest,
    }
    assert {name: _tree(HERE / name) for name in ("results", "local")} == real


def cases_file(env, *cases, name: str = "cases.json") -> Path:
    """A cases file holding ``cases`` (dicts), outside the books and the outputs."""
    path = env["tmp"] / "input" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"cases": list(cases)}, ensure_ascii=False), encoding="utf-8"
    )
    return path


def case(case_id: str = "E1", question: str = QUESTION, editions=(JUL,)) -> dict:
    return {"id": case_id, "question": question, "editions": list(editions)}


def argv(env, step: str, cases: Path, *, tag: str = "2026-11-21", budget: str = "600"):
    """The command line of one invocation, every argument given explicitly."""
    command = [step, "--cases", str(cases)]
    if step == "run":
        command += [
            "--tag",
            tag,
            "--time-budget-s",
            budget,
            "--manifest",
            str(env["manifest"]),
        ]
    return command


def written(env) -> dict[str, str]:
    """Every file the runner or the agent wrote (outside the generated corpus, the cases files
    and the stand-in historical ledger), with its SHA-256."""
    return {
        path: digest
        for path, digest in _tree(env["tmp"]).items()
        if not path.startswith(("repo/", "input/"))
        and Path(path).name != evidence_agent.HISTORICAL_LEDGER
    }


def agent_cell(case_id: str) -> list[dict]:
    """An active ledger's pin and one agent call of ``case_id`` from before conditions
    existed (no condition field), kept at its reservation of 0.5 USD."""
    pin = {
        "event": "baseline",
        "ledger": evidence_agent.HISTORICAL_LEDGER,
        "sha256": evidence_agent.HISTORICAL_SHA256,
        "committed_usd": 0.25,
        "budget_usd": 100.0,
        "at": "2026-11-20T00:00:00+00:00",
    }
    attempt = f"{case_id}-call1"
    return [
        pin,
        {
            "event": "reserve",
            "attempt": attempt,
            "case": case_id,
            "call": 1,
            "request_sha256": "0" * 64,
            "counted_input_tokens": 1500,
            "reserved_usd": 0.5,
            "at": "2026-11-20T00:00:00+00:00",
        },
        {
            "event": "settle",
            "attempt": attempt,
            "case": case_id,
            "sent": True,
            "cost_usd": 0.5,
            "cost_basis": "reservation_retained",
            "above_reservation": False,
            "usage": None,
            "response_sha256": None,
            "at": "2026-11-20T00:00:00+00:00",
        },
    ]


def active(env) -> Path:
    return env["tmp"] / "books" / evidence_agent.ACTIVE_LEDGER


def test_plan_lays_out_the_matrix_its_bounds_and_headroom_and_loads_sends_and_writes_nothing(
    isolated, capsys
):
    ledger = active(isolated)
    ledger.write_text("".join(json.dumps(e) + "\n" for e in agent_cell("E2")), "utf-8")
    before = written(isolated)

    code = run_comparison.main(
        argv(
            isolated,
            "plan",
            cases_file(isolated, case("E1"), case("E2", editions=(JAN, JUL))),
        )
    )

    assert code == 0
    plan = json.loads(capsys.readouterr().out)
    # Case by case, each case's three conditions together, in the fixed order A, B, C.
    assert [(c["case"], c["condition"], c["in_books"]) for c in plan["order"]] == [
        ("E1", "fixed5", False),
        ("E1", "fixed10", False),
        ("E1", "agent", False),
        ("E2", "fixed5", False),
        ("E2", "fixed10", False),
        ("E2", "agent", True),
    ]
    # E2's booked call has no question recorded (written before 2026-11-21): it cannot be paired.
    assert [(c["case"], c["pairing"]) for c in plan["cases"]] == [
        ("E1", "new"),
        ("E2", "unverifiable"),
    ]
    assumptions = plan["assumptions"]
    assert assumptions["label"].startswith("ASSUMPTIONS")
    assert {
        k: assumptions[k]
        for k in (
            "input_cap_tokens",
            "input_margin",
            "max_output_tokens",
            "us_multiplier",
            "ceiling_input_usd_per_mtok",
        )
    } == {
        "input_cap_tokens": 80000,
        "input_margin": 1.1,
        "max_output_tokens": 32000,
        "us_multiplier": 1.1,
        "ceiling_input_usd_per_mtok": 8.0,
    }
    assert assumptions["prices_usd_per_mtok"] == {
        "input": 4.0,
        "output": 20.0,
        "cache_write_5m": 5.0,
        "cache_write_1h": 8.0,
        "cache_read": 0.2,
    }
    assert plan["order"][4]["editions"] == [JAN, JUL]
    assert {
        name: {
            k: c[k]
            for k in (
                "label",
                "initial_passages",
                "most_passages",
                "calls",
                "searches",
                "search_tool",
                "admission_usd",
            )
        }
        for name, c in plan["conditions"].items()
    } == {
        "fixed5": {
            "label": "A",
            "initial_passages": 5,
            "most_passages": 5,
            "calls": 1,
            "searches": 0,
            "search_tool": False,
            "admission_usd": 1.4784,
        },
        "fixed10": {
            "label": "B",
            "initial_passages": 10,
            "most_passages": 10,
            "calls": 1,
            "searches": 0,
            "search_tool": False,
            "admission_usd": 1.4784,
        },
        "agent": {
            "label": "C",
            "initial_passages": 5,
            "most_passages": 10,
            "calls": 3,
            "searches": 2,
            "search_tool": True,
            "admission_usd": 4.4352,
        },
    }
    # Worst case of the five cells still to run: 2 x (1.4784 + 1.4784) + 4.4352 = 10.3488 USD,
    # beside 0.25 (history) + 0.5 (the E2 agent call) = 0.75 USD committed under USD 100.
    admission = plan["admission"]
    assert {
        k: admission[k]
        for k in (
            "limit_usd",
            "committed_usd",
            "headroom_usd",
            "worst_case_usd",
            "fits",
            "headroom_after_worst_case_usd",
        )
    } == {
        "limit_usd": 100.0,
        "committed_usd": 0.75,
        "headroom_usd": 99.25,
        "worst_case_usd": 10.3488,
        "fits": True,
        "headroom_after_worst_case_usd": 88.9012,
    }
    assert admission["call_ceiling_at_input_cap_usd"] == 1.4784
    # Estimates are labelled and come only from calls priced from usage: the history's one call
    # (a fixed5 cell), nothing for fixed10 (the fixed5 estimate plus five passages' input,
    # 1,280 tokens at 4 USD per million) and nothing for the agent (E2's call was kept at its
    # reservation), so the matrix has no estimate.
    estimates = plan["estimates"]
    assert estimates["label"].startswith("ESTIMATE")
    assert {
        name: (c["observed_cells"], c["usd_per_cell"])
        for name, c in estimates["per_condition"].items()
    } == {"fixed5": (1, 0.25), "fixed10": (0, 0.25512), "agent": (0, None)}
    assert (estimates["cells_to_run"], estimates["matrix_usd"]) == (5, None)
    assert (
        plan["planned"]["active_ledger_sha256"]
        == before[f"books/{evidence_agent.ACTIVE_LEDGER}"]
    )
    assert (isolated["loads"], written(isolated)) == (
        [],
        before,
    )  # no model, nothing written


def live(env, monkeypatch, *replies, **options) -> Provider:
    """The provider's HTTP side for ``run``, scripted with ``replies``, on the test's clock."""
    provider = Provider(env["clock"], *replies, **options)
    monkeypatch.setattr(run_comparison, "_client", lambda config: provider.client())
    return provider


def ledger(env) -> list[dict]:
    return [json.loads(line) for line in active(env).read_text("utf-8").splitlines()]


def sent(body: dict) -> list[str]:
    """The passage IDs of a request's first (user) message, in the order given."""
    return re.findall(r'<passage id="([^"]+)"', body["messages"][0]["content"])


def outputs(env, *, tag: str = "2026-11-21") -> tuple[Path, Path]:
    """The public record and the local folder of one run."""
    name = f"{tag}-comparison"
    return env["tmp"] / "results" / f"{name}.json", env["tmp"] / "local" / name


def exit_code(argv_: list[str]) -> int:
    """The command's exit code, whether it returns it or argparse exits with it."""
    try:
        return run_comparison.main(argv_)
    except SystemExit as stop:
        return stop.code


def answers() -> tuple[dict, ...]:
    """A, B and C each answer at once, citing the top passage."""
    return tuple(final((f"{label}.", [TOP5[0]])) for label in "ABC")


def test_run_gives_each_condition_its_passages_from_one_ranking_and_books_every_cell_once(
    isolated, monkeypatch, capsys
):
    provider = live(
        isolated,
        monkeypatch,
        final(("A.", [TOP5[0]])),
        final(("B.", [TOP10[9]])),  # B may cite its tenth passage
        search_call("Pauschale", "Begründung"),
        final(("C.", [TOP5[0], RANKED[5]])),
    )  # C cites a passage it found

    code = run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E1"))))

    assert code == 0
    a, b, c1, c2 = provider.creates
    assert sent(a) == TOP5  # A: the top 5 in rank order
    assert sent(b) == TOP10  # B: the top 10 in rank order; rank 11 (2.6) is left out
    assert (
        sent(c1) == TOP5 and c1["messages"][0] == a["messages"][0]
    )  # C starts where A does
    for key in ("model", "max_tokens", "thinking", "output_config"):  # shared settings
        assert a[key] == b[key] == c1[key]
    # A and B are the Phase 2 request; only C adds its instruction and offers its one tool.
    assert a["system"] == b["system"] == generation.SYSTEM_PROMPT
    assert not {"tools", "tool_choice"} & (set(a) | set(b))
    assert c1["system"].startswith(generation.SYSTEM_PROMPT) and len(
        c1["system"]
    ) > len(generation.SYSTEM_PROMPT)
    assert [t["name"] for t in c1["tools"]] == ["search_commentary"]
    # C keeps its bounds: its search returned ranks 6 to 10 of the same ranking, which filled
    # the 10-passage budget, so its last call offered no tool.
    (found,) = c2["messages"][2]["content"]
    assert re.findall(r'<passage id="([^"]+)"', found["content"]) == RANKED[5:10]
    assert c2["tool_choice"] == {"type": "none"}
    assert isolated["e5"].queries == [
        QUESTION,
        "Pauschale",
    ]  # ranked once, then C's query
    assert [(e["event"], e.get("attempt")) for e in ledger(isolated)] == [
        ("baseline", None),
        ("reserve", "E1-fixed5-call1"),
        ("settle", "E1-fixed5-call1"),
        ("reserve", "E1-fixed10-call1"),
        ("settle", "E1-fixed10-call1"),
        ("reserve", "E1-agent-call1"),
        ("settle", "E1-agent-call1"),
        ("reserve", "E1-agent-call2"),
        ("settle", "E1-agent-call2"),
    ]
    public, local = outputs(isolated)
    record = json.loads(public.read_text("utf-8"))
    (planned,) = record["cases"]
    assert [r["passage_id"] for r in planned["ranking"]] == TOP10
    cells = planned["cells"]
    assert [
        (
            c["condition"],
            c["label"],
            c["status"]["execution"],
            c["status"]["answer"],
            c["status"]["accounting"],
        )
        for c in cells
    ] == [
        ("fixed5", "A", "answer", "answered", "priced"),
        ("fixed10", "B", "answer", "answered", "priced"),
        ("agent", "C", "answer", "answered", "priced"),
    ]
    # One budget: each cell's admission counted the history (0.25) and the cells before it.
    assert [c["agent"]["spending"]["committed_before_usd"] for c in cells] == [
        0.25,
        0.274,
        0.298,
    ]
    assert [len(c["agent"]["supplied"]) for c in cells] == [5, 10, 10]
    assert (
        record["run"]["configuration"]["conditions"]["fixed5"]["system_prompt_sha256"]
        == record["run"]["configuration"]["conditions"]["fixed10"][
            "system_prompt_sha256"
        ]
    )
    assert QUESTION not in public.read_text(
        "utf-8"
    )  # the question is published by hash only
    kept = json.loads((local / "result.json").read_text("utf-8"))
    assert kept["cases"][0]["question"] == QUESTION
    assert json.loads(capsys.readouterr().out)["exit_code"] == 0


def test_a_repeated_run_sends_nothing_again_and_writes_nothing_whatever_the_tag(
    isolated, monkeypatch, capsys
):
    cases = cases_file(isolated, case("E1"))
    live(isolated, monkeypatch, *answers())
    assert run_comparison.main(argv(isolated, "run", cases)) == 0
    before = written(isolated)
    capsys.readouterr()
    again = live(isolated, monkeypatch, *answers())

    code = run_comparison.main(argv(isolated, "run", cases, tag="2026-11-22"))

    # The (case, condition) pair is the accounting identity: a new tag is not a new cell.
    assert code == 3
    assert (again.counts, again.creates) == ([], [])
    assert written(isolated) == before
    shown = json.loads(capsys.readouterr().out)
    assert [(c["condition"], c["execution"], c["detail"]) for c in shown["cells"]] == [
        (name, "refused", "already_run") for name in ("fixed5", "fixed10", "agent")
    ]


def test_a_cell_the_one_question_runner_booked_is_the_same_cell_in_the_comparison(
    isolated, monkeypatch, capsys
):
    monkeypatch.setattr(run_question, "RESULTS", isolated["tmp"] / "results")
    monkeypatch.setattr(run_question, "LOCAL", isolated["tmp"] / "local")
    monkeypatch.setattr(run_question, "CLOCK", isolated["clock"])
    single = Provider(isolated["clock"], final(("C.", [TOP5[0]])))
    monkeypatch.setattr(run_question, "_client", lambda config: single.client())
    assert (
        run_question.main(
            [
                "run",
                "--case-id",
                "E1",
                "--question",
                QUESTION,
                "--tag",
                "2026-11-21",
                "--time-budget-s",
                "600",
                "--manifest",
                str(isolated["manifest"]),
                "--edition",
                JUL,
            ]
        )
        == 0
    )
    capsys.readouterr()
    provider = live(
        isolated, monkeypatch, final(("A.", [TOP5[0]])), final(("B.", [TOP5[0]]))
    )

    code = run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E1"))))

    # E1's agent cell is in the books already, asked the same question over the same editions:
    # A and B run, C is never sent again, and the skipped cell does not mask the cells that ran.
    assert code == 0
    assert len(provider.creates) == 2
    shown = json.loads(capsys.readouterr().out)
    assert [(c["condition"], c["execution"], c["detail"]) for c in shown["cells"]] == [
        ("fixed5", "answer", None),
        ("fixed10", "answer", None),
        ("agent", "refused", "already_run"),
    ]
    assert [e.get("attempt") for e in ledger(isolated) if e["event"] == "reserve"] == [
        "E1-agent-call1",
        "E1-fixed5-call1",
        "E1-fixed10-call1",
    ]


@pytest.mark.parametrize(
    "field",
    [
        "reference_expectation",
        "evidence",
        "rubric",
        "expected_status",
        "required_claims",
    ],
)
@pytest.mark.parametrize("step", ["plan", "run"])
def test_a_cases_file_carrying_anything_that_scores_an_answer_is_refused_before_it_is_used(
    isolated, monkeypatch, capsys, field, step
):
    provider = live(isolated, monkeypatch, *answers())
    cases = cases_file(isolated, {**case("E1"), field: "SENTINEL-REFERENCE"})

    code = exit_code(argv(isolated, step, cases))

    assert code == 2
    assert (isolated["loads"], provider.counts, provider.creates) == ([], [], [])
    assert written(isolated) == {}
    assert (
        "SENTINEL" not in capsys.readouterr().err
    )  # the field is named, its value never read


def test_no_reference_text_of_a_dev_case_reaches_any_condition(isolated, monkeypatch):
    # The D1 question verbatim under a new case ID: its gold evidence, reference expectation and
    # rubric must reach no request, count or output of A, B or C. None is in the corpus.
    dev = json.loads((HERE / "cases.json").read_text("utf-8"))["cases"][0]
    rubric = json.loads((HERE / "rubric.json").read_text("utf-8"))["cases"][0]
    assert dev["id"] == rubric["id"] == "D1"
    claims = rubric["required_claims"] + rubric["optional_background"]
    scoring = [
        dev["reference_expectation"],
        dev["context_not_required"],
        *(e["quote"] for e in dev["evidence"]),
        rubric["review_focus"],
        *(c["claim"] for c in claims),
        *(s["quote"] for c in claims for s in c["support"]),
    ]
    provider = live(
        isolated,
        monkeypatch,
        final(("A.", [TOP5[0]])),
        final(("B.", [TOP5[0]])),
        search_call("Pauschale", "Begründung"),
        final(("C.", [TOP5[0]])),
    )

    assert (
        run_comparison.main(
            argv(
                isolated,
                "run",
                cases_file(isolated, case("E1", question=dev["question"])),
            )
        )
        == 0
    )

    assert len(provider.creates) == 4
    public, local = outputs(isolated)
    seen = (
        json.dumps(provider.counts + provider.creates, ensure_ascii=False)
        + public.read_text("utf-8")
        + (local / "result.json").read_text("utf-8")
    )
    assert [s for s in scoring if s in seen] == []


def test_a_matrix_whose_worst_case_does_not_fit_is_refused_before_the_model_loads(
    isolated, monkeypatch, capsys
):
    # 92.608 USD committed: one case's worst case (1.4784 + 1.4784 + 4.4352 = 7.392) reaches
    # exactly 100 USD and fits; a second case's would not.
    books(
        (
            {"event": "reserve", "attempt": "H-1", "case": "H", "reserved_usd": 92.608},
            {
                "event": "settle",
                "attempt": "H-1",
                "case": "H",
                "cost_usd": 92.608,
                "cost_basis": "usage",
            },
        )
    )
    provider = live(isolated, monkeypatch, *answers())
    one, two = (
        cases_file(
            isolated,
            *(case(f"E{n}") for n in range(1, count + 1)),
            name=f"{count}.json",
        )
        for count in (1, 2)
    )

    assert run_comparison.main(argv(isolated, "plan", one)) == 0
    fits = json.loads(capsys.readouterr().out)["admission"]
    code = run_comparison.main(argv(isolated, "run", two))

    assert (
        fits["worst_case_usd"],
        fits["fits"],
        fits["headroom_after_worst_case_usd"],
    ) == (7.392, True, 0.0)
    assert code == 3
    assert "does not fit" in capsys.readouterr().err
    assert (isolated["loads"], provider.counts, provider.creates) == ([], [], [])
    assert written(isolated) == {}


OVERLOADED = httpx.Response(
    529,
    json={
        "type": "error",
        "error": {
            "type": "overloaded_error",
            "message": "SENTINEL provider error text",
        },
    },
)


def test_a_cell_whose_accounting_needs_a_person_stops_the_matrix_and_nothing_after_it_is_sent(
    isolated, monkeypatch, capsys
):
    provider = live(isolated, monkeypatch, OVERLOADED, *answers())

    code = run_comparison.main(
        argv(isolated, "run", cases_file(isolated, case("E1"), case("E2")))
    )

    # A's error response could not be priced, so its reservation stays committed: the matrix
    # stops there, and nothing after it is counted or sent.
    assert code == 6
    assert (len(provider.counts), len(provider.creates)) == (1, 1)
    shown = json.loads(capsys.readouterr().out)
    assert shown["stopped_after"] == {"case": "E1", "condition": "fixed5"}
    assert [
        (c["case"], c["condition"], c["execution"], c["accounting"])
        for c in shown["cells"]
    ] == [
        ("E1", "fixed5", "provider_error", "uncertain"),
        *(
            (case_id, name, "not_run", "nothing_reserved")
            for case_id, name in (
                ("E1", "fixed10"),
                ("E1", "agent"),
                ("E2", "fixed5"),
                ("E2", "fixed10"),
                ("E2", "agent"),
            )
        ),
    ]
    public, _ = outputs(isolated)
    assert "SENTINEL" not in public.read_text("utf-8")  # provider text stays local


def test_every_case_is_ranked_before_any_cell_is_sent(isolated, monkeypatch, capsys):
    second = "Welche Pauschale gilt im zweiten Fall?"
    stand_in = isolated["e5"]
    embed_query = stand_in.embed_query

    def failing(
        text: str,
    ) -> list[float]:  # the e5 model fails on the second question only
        if text == second:
            raise RuntimeError("stand-in e5 model failed")
        return embed_query(text)

    monkeypatch.setattr(stand_in, "embed_query", failing)
    provider = live(isolated, monkeypatch, *answers())

    code = run_comparison.main(
        argv(
            isolated,
            "run",
            cases_file(isolated, case("E1"), case("E2", question=second)),
        )
    )

    # E2 cannot be ranked, so nothing of E1 is sent either: no cell spends before every case
    # has its ranking.
    assert code == 3
    assert "E2" in capsys.readouterr().err
    assert (provider.counts, provider.creates) == ([], [])
    assert written(isolated) == {}


USAGE = {
    "input_tokens": 1500,
    "output_tokens": 900,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
    "cache_creation_1h_input_tokens": 0,
    "us_inference": False,
}  # 0.024 USD at the recorded prices


def _reserve(case_id: str, condition: str, call: int) -> dict:
    return {
        "event": "reserve",
        "attempt": f"{case_id}-{condition}-call{call}",
        "case": case_id,
        "condition": condition,
        "call": call,
        "request_sha256": "0" * 64,
        "counted_input_tokens": 1500,
        "reserved_usd": 0.71852,
        "question_sha256": "0" * 64,  # every reservation with a condition records both
        "editions": [JUL],
        "at": "2026-11-21T00:00:00+00:00",
    }


def _settle(case_id: str, condition: str, call: int) -> dict:
    return {
        "event": "settle",
        "attempt": f"{case_id}-{condition}-call{call}",
        "case": case_id,
        "condition": condition,
        "sent": True,
        "cost_usd": 0.024,
        "cost_basis": "usage",
        "above_reservation": False,
        "usage": USAGE,
        "response_sha256": "0" * 64,
        "at": "2026-11-21T00:00:00+00:00",
    }


def test_estimates_count_only_cells_whose_every_call_was_priced_from_usage(
    isolated, capsys
):
    pin = agent_cell("E2")[0]
    rows = [
        pin,
        _reserve("E3", "agent", 1),
        _settle("E3", "agent", 1),
        _reserve("E3", "agent", 2),  # still open: E3's cost is not known yet
        _reserve("E4", "fixed5", 1),
        _settle("E4", "fixed5", 1),
        _reserve("E6", "agent", 1),
        _settle("E6", "agent", 1),
        _reserve("E6", "agent", 2),
        _settle("E6", "agent", 2),
    ]
    active(isolated).write_text("".join(json.dumps(e) + "\n" for e in rows), "utf-8")

    assert (
        run_comparison.main(argv(isolated, "plan", cases_file(isolated, case("E5"))))
        == 0
    )

    estimates = json.loads(capsys.readouterr().out)["estimates"]["per_condition"]
    # fixed5: the history's one call (0.25) and E4 (0.024), mean 0.137; fixed10 that plus
    # 0.00512; the agent: E6's two calls (0.048), not E3, which still holds an open reservation.
    assert {
        name: (c["observed_cells"], c["usd_per_cell"]) for name, c in estimates.items()
    } == {"fixed5": (2, 0.137), "fixed10": (0, 0.14212), "agent": (1, 0.048)}


def test_a_case_whose_booked_cells_were_asked_something_else_is_refused_before_the_model_loads(
    isolated, monkeypatch, capsys
):
    # The one-question runner books E1's agent cell for one question on July; a comparison then
    # asks E1 another question over both editions. A and B must not be paired with that C.
    monkeypatch.setattr(run_question, "RESULTS", isolated["tmp"] / "results")
    monkeypatch.setattr(run_question, "LOCAL", isolated["tmp"] / "local")
    monkeypatch.setattr(run_question, "CLOCK", isolated["clock"])
    single = Provider(isolated["clock"], final(("C.", [TOP5[0]])))
    monkeypatch.setattr(run_question, "_client", lambda config: single.client())
    assert (
        run_question.main(
            [
                "run",
                "--case-id",
                "E1",
                "--question",
                QUESTION,
                "--tag",
                "2026-11-21",
                "--time-budget-s",
                "600",
                "--manifest",
                str(isolated["manifest"]),
                "--edition",
                JUL,
            ]
        )
        == 0
    )
    capsys.readouterr()
    books_before = active(isolated).read_bytes()
    loads = len(isolated["loads"])
    provider = live(isolated, monkeypatch, *answers())

    code = run_comparison.main(
        argv(
            isolated,
            "run",
            cases_file(
                isolated,
                case(
                    "E1",
                    question="Welche Pauschale gilt ab Januar?",
                    editions=(JAN, JUL),
                ),
            ),
        )
    )

    assert code == 3
    assert "E1" in capsys.readouterr().err
    assert (provider.counts, provider.creates) == ([], [])
    assert len(isolated["loads"]) == loads  # refused before the model loads
    assert active(isolated).read_bytes() == books_before


def test_a_case_whose_booked_cell_recorded_no_question_is_refused_before_the_model_loads(
    isolated, monkeypatch, capsys
):
    active(isolated).write_text(
        "".join(json.dumps(e) + "\n" for e in agent_cell("E2")), "utf-8"
    )
    before = written(isolated)
    provider = live(isolated, monkeypatch, *answers())

    code = run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E2"))))

    assert code == 3
    assert "E2" in capsys.readouterr().err
    assert (isolated["loads"], provider.counts, provider.creates) == ([], [], [])
    assert written(isolated) == before


class Counted(Provider):
    """The provider's HTTP side with one token count per count request, from ``counts``, then
    1,500 for any further count, so a matrix that went on would be seen counting and sending."""

    def __init__(self, clock, *replies, counts) -> None:
        super().__init__(clock, *replies)
        self.planned = list(counts)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Answer one request, the next planned count for a count request."""
        if request.url.path == "/v1/messages/count_tokens":
            count = self.planned.pop(0) if self.planned else 1500
            self.count_reply = httpx.Response(200, json={"input_tokens": count})
        return super().__call__(request)


OUTSIDE = final(
    ("Nicht geliefert.", [RANKED[10]])
)  # rank 11 was never supplied: invalid


def test_a_cost_above_its_reservation_stops_the_matrix(isolated, monkeypatch, capsys):
    provider = live(
        isolated,
        monkeypatch,
        {**final(("A.", [TOP5[0]])), "usage": _dearest(1651)},
        *answers(),
    )

    code = run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E1"))))

    assert code == 5
    assert len(provider.creates) == 1
    assert json.loads(capsys.readouterr().out)["stopped_after"] == {
        "case": "E1",
        "condition": "fixed5",
    }


def test_a_failed_write_stops_the_matrix_before_anything_is_sent(isolated, monkeypatch):
    real = run_comparison._claim

    def claimed_then_blocked(paths, design):  # a file where the run's request folder goes
        refusal, owner = real(paths, design)
        (paths["local"] / "requests").write_text("kein Ordner\n", "utf-8")
        return refusal, owner

    monkeypatch.setattr(run_comparison, "_claim", claimed_then_blocked)
    provider = live(isolated, monkeypatch, *answers())

    code = run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E1"))))

    # A's request could not be saved, so it was neither reserved nor sent, and nothing followed.
    assert code == 7
    assert (len(provider.counts), provider.creates) == (1, [])


def test_a_local_folder_that_cannot_be_created_is_refused_before_anything_loads(
    isolated, monkeypatch, capsys
):
    blocker = isolated["tmp"] / "blocker"
    blocker.write_text("a file where the local folder's parent should be\n", "utf-8")
    monkeypatch.setattr(run_comparison, "LOCAL", blocker / "local")
    provider = live(isolated, monkeypatch, *answers())

    assert run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E1")))) == 3

    assert "cannot be created" in capsys.readouterr().err
    assert (provider.counts, provider.creates, isolated["loads"]) == ([], [], [])


def test_a_refusal_by_the_books_stops_the_matrix(isolated, monkeypatch, capsys):
    provider = live(isolated, monkeypatch, *answers())

    with generation._ledger_lock(
        active(isolated)
    ) as held:  # another invocation holds them
        assert held
        code = run_comparison.main(
            argv(isolated, "run", cases_file(isolated, case("E1")))
        )

    # A is refused by the lock; the matrix stops there, so B and C are never tried.
    assert code == 3
    assert (provider.counts, provider.creates) == ([], [])
    shown = json.loads(capsys.readouterr().out)
    assert shown["stopped_after"] == {"case": "E1", "condition": "fixed5"}
    assert [(c["condition"], c["execution"], c["detail"]) for c in shown["cells"]] == [
        ("fixed5", "refused", "locked"),
        ("fixed10", "not_run", "matrix_stopped"),
        ("agent", "not_run", "matrix_stopped"),
    ]


def test_a_failed_output_write_outranks_the_cell_that_stopped_the_matrix(
    isolated, monkeypatch
):
    blocker = isolated["tmp"] / "blocker"
    blocker.write_text("a file where the results folder's parent should be\n", "utf-8")
    monkeypatch.setattr(run_comparison, "RESULTS", blocker / "results")
    provider = live(isolated, monkeypatch, OVERLOADED, *answers())

    code = run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E1"))))

    # A's error response stops the matrix (6); the public record cannot be written (7).
    assert code == 7
    assert len(provider.creates) == 1


def test_a_case_whose_booked_cells_cover_other_editions_is_refused_before_the_model_loads(
    isolated, monkeypatch, capsys
):
    monkeypatch.setattr(run_question, "RESULTS", isolated["tmp"] / "results")
    monkeypatch.setattr(run_question, "LOCAL", isolated["tmp"] / "local")
    monkeypatch.setattr(run_question, "CLOCK", isolated["clock"])
    single = Provider(isolated["clock"], final(("C.", [TOP5[0]])))
    monkeypatch.setattr(run_question, "_client", lambda config: single.client())
    assert (
        run_question.main(
            [
                "run",
                "--case-id",
                "E1",
                "--question",
                QUESTION,
                "--tag",
                "2026-11-21",
                "--time-budget-s",
                "600",
                "--manifest",
                str(isolated["manifest"]),
                "--edition",
                JUL,
            ]
        )
        == 0
    )
    capsys.readouterr()
    loads = len(isolated["loads"])
    provider = live(isolated, monkeypatch, *answers())

    # The same question, but over both editions: not the case the books hold.
    code = run_comparison.main(
        argv(isolated, "run", cases_file(isolated, case("E1", editions=(JAN, JUL))))
    )

    assert code == 3
    assert "E1 (other)" in capsys.readouterr().err
    assert (provider.counts, provider.creates) == ([], [])
    assert len(isolated["loads"]) == loads


def test_an_unanswered_cell_does_not_stop_the_matrix_and_exits_4(
    isolated, monkeypatch, capsys
):
    provider = live(isolated, monkeypatch, OUTSIDE, *answers()[1:], *answers())

    code = run_comparison.main(
        argv(isolated, "run", cases_file(isolated, case("E1"), case("E2")))
    )

    assert code == 4
    assert len(provider.creates) == 6
    shown = json.loads(capsys.readouterr().out)
    assert shown["stopped_after"] is None
    assert [c["execution"] for c in shown["cells"]] == [
        "invalid_answer",
        *["answer"] * 5,
    ]


@pytest.mark.parametrize(
    ("second", "counts", "code"),
    [
        (OVERLOADED, (1500, 1500), 6),  # B kept at its reservation: 6 outranks A's 4
        (None, (1500, 90000), 3),  # B over the input cap, refused: 3 outranks A's 4
    ],
    ids=["uncertain_over_unanswered", "refused_over_unanswered"],
)
def test_the_matrix_exits_with_the_most_serious_cell_and_stops_after_it(
    isolated, monkeypatch, second, counts, code
):
    provider = Counted(
        isolated["clock"],
        OUTSIDE,
        *((second,) if second else ()),
        *answers(),
        counts=counts,
    )
    monkeypatch.setattr(run_comparison, "_client", lambda config: provider.client())

    assert (
        run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E1"))))
        == code
    )

    assert (len(provider.counts), len(provider.creates)) == (2, 2 if second else 1)


def test_an_output_that_cannot_be_written_exits_7_although_every_cell_answered(
    isolated, monkeypatch
):
    blocker = isolated["tmp"] / "blocker"
    blocker.write_text("a file where the results folder's parent should be\n", "utf-8")
    monkeypatch.setattr(run_comparison, "RESULTS", blocker / "results")
    provider = live(isolated, monkeypatch, *answers())

    code = run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E1"))))

    assert code == 7
    assert len(provider.creates) == 3  # reporting is never repaired by sending again


def test_an_unexpected_failure_keeps_the_outputs_of_the_cells_before_it(
    isolated, monkeypatch
):
    real = evidence_agent.run_case
    began: list[str] = []

    def failing(task, **options):  # the loop fails unexpectedly in B
        began.append(options["condition"])
        if options["condition"] == "fixed10":
            raise RuntimeError("unexpected failure in the loop")
        return real(task, **options)

    monkeypatch.setattr(evidence_agent, "run_case", failing)
    provider = live(isolated, monkeypatch, *answers())

    with pytest.raises(RuntimeError, match="unexpected failure"):
        run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E1"))))

    assert (began, len(provider.creates)) == (["fixed5", "fixed10"], 1)
    public, local = outputs(isolated)
    record = json.loads(public.read_text("utf-8"))
    assert [c["condition"] for c in record["cases"][0]["cells"]] == ["fixed5"]
    assert (local / "result.json").exists()


def test_a_matrix_stopped_by_a_cell_resumes_without_sending_its_cells_again(
    isolated, monkeypatch, capsys
):
    cases = cases_file(isolated, case("E1"))
    live(isolated, monkeypatch, OVERLOADED, *answers())
    assert run_comparison.main(argv(isolated, "run", cases)) == 6
    capsys.readouterr()
    provider = live(isolated, monkeypatch, *answers()[1:])

    code = run_comparison.main(argv(isolated, "run", cases, tag="2026-11-22"))

    # A stays in the books with its reservation; B and C run now, A is never sent again.
    assert code == 0
    assert len(provider.creates) == 2
    shown = json.loads(capsys.readouterr().out)
    assert [(c["condition"], c["execution"]) for c in shown["cells"]] == [
        ("fixed5", "refused"),
        ("fixed10", "answer"),
        ("agent", "answer"),
    ]


def test_plan_refuses_damaged_books(isolated, capsys):
    active(isolated).write_text("not a ledger\n", "utf-8")

    code = run_comparison.main(argv(isolated, "plan", cases_file(isolated, case("E1"))))

    assert code == 3
    assert "ledger_damaged" in capsys.readouterr().err


def test_an_edition_the_corpus_lacks_is_refused_before_anything_is_sent(
    isolated, monkeypatch
):
    provider = live(isolated, monkeypatch, *answers())

    code = exit_code(
        argv(
            isolated, "run", cases_file(isolated, case("E1", editions=("2026-04-01",)))
        )
    )

    assert code == 2
    assert (provider.counts, provider.creates) == ([], [])
    assert written(isolated) == {}


def test_existing_outputs_are_refused_before_the_model_loads(isolated, monkeypatch):
    public, _ = outputs(isolated)
    public.parent.mkdir(parents=True)
    public.write_text("recorded\n", encoding="utf-8")
    before = written(isolated)
    provider = live(isolated, monkeypatch, *answers())

    code = run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E1"))))

    assert code == 3
    assert (isolated["loads"], provider.counts, provider.creates) == ([], [], [])
    assert written(isolated) == before


ABOVE = {
    **final(("Teuer.", [TOP5[0]])),
    "usage": _dearest(1651),
}  # above its reservation


@pytest.mark.parametrize(
    ("replies", "blocked", "code", "sent"),
    [
        (
            (OUTSIDE, ABOVE),
            False,
            5,
            2,
        ),  # B's spending stop (5) outranks A's unanswered 4
        (
            (ABOVE,),
            True,
            7,
            1,
        ),  # a failed output write (7) outranks A's spending stop (5)
    ],
    ids=["spending_stop_over_unanswered", "failed_write_over_spending_stop"],
)
def test_a_spending_stop_ranks_below_a_failed_write_and_above_an_unanswered_cell(  # noqa: PLR0913
    isolated, monkeypatch, replies, blocked, code, sent
):
    if blocked:
        blocker = isolated["tmp"] / "blocker"
        blocker.write_text(
            "a file where the results folder's parent should be\n", "utf-8"
        )
        monkeypatch.setattr(run_comparison, "RESULTS", blocker / "results")
    provider = live(isolated, monkeypatch, *replies, *answers())

    assert (
        run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E1"))))
        == code
    )

    assert len(provider.creates) == sent  # the matrix stopped at the spending stop


def test_a_cases_file_nested_too_deep_to_parse_is_invalid_input(isolated, monkeypatch):
    provider = live(isolated, monkeypatch, *answers())
    path = isolated["tmp"] / "input" / "deep.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")

    code = exit_code(argv(isolated, "run", path))

    assert code == 2  # refused as input, not an unexpected error
    assert (isolated["loads"], provider.counts, provider.creates) == ([], [], [])


def test_an_unknown_field_name_is_shown_escaped(isolated, capsys):
    cases = cases_file(isolated, {**case("E1"), "\x1b[31mrubric": "SENTINEL"})

    code = exit_code(argv(isolated, "plan", cases))

    assert code == 2
    shown = capsys.readouterr().err
    assert (
        "\x1b" not in shown and "\\x1b" in shown
    )  # no terminal control sequence passes
    assert "SENTINEL" not in shown


def _historical_92_608() -> None:
    """A stand-in historical ledger that committed 92.608 USD: one case's worst case (7.392)
    reaches exactly 100 USD."""
    books(
        (
            {"event": "reserve", "attempt": "H-1", "case": "H", "reserved_usd": 92.608},
            {
                "event": "settle",
                "attempt": "H-1",
                "case": "H",
                "cost_usd": 92.608,
                "cost_basis": "usage",
            },
        )
    )


def test_a_matrix_admitted_at_exactly_the_limit_runs_every_cell(isolated, monkeypatch):
    # Each cell's admission holds back the cells still to run after it; cells that settle
    # within their admissions leave room for the rest, so all three run.
    _historical_92_608()
    provider = live(isolated, monkeypatch, *answers())

    code = run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E1"))))

    assert code == 0
    assert len(provider.creates) == 3


def test_a_booking_after_the_check_that_leaves_the_rest_of_the_matrix_no_room_stops_it(
    isolated, monkeypatch, capsys
):
    # The matrix fits exactly when run checks it. While the model loads, another invocation
    # reserves 0.71852 USD, leaving 6.67348: A's own 1.4784 would fit, but not beside the
    # 5.9136 of B and C still to run, so A is refused under the lock and nothing is sent.
    _historical_92_608()
    provider = live(isolated, monkeypatch, *answers())
    rankings = run_comparison._rankings

    def meanwhile(cases, loaded):
        ranked = rankings(cases, loaded)
        pin, other, _ = agent_cell("X1")
        rows = ({**pin, "committed_usd": 92.608}, {**other, "reserved_usd": 0.71852})
        active(isolated).write_text(
            "".join(json.dumps(e) + "\n" for e in rows), "utf-8"
        )  # an open reservation: committed until it settles
        return ranked

    monkeypatch.setattr(run_comparison, "_rankings", meanwhile)

    code = run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E1"))))

    assert code == 3
    shown = json.loads(capsys.readouterr().out)
    assert shown["stopped_after"] == {"case": "E1", "condition": "fixed5"}
    assert [(c["condition"], c["execution"], c["detail"]) for c in shown["cells"]] == [
        ("fixed5", "refused", "admission_budget"),
        ("fixed10", "not_run", "matrix_stopped"),
        ("agent", "not_run", "matrix_stopped"),
    ]
    assert (provider.counts, provider.creates) == ([], [])
    assert [e["event"] for e in ledger(isolated)] == ["baseline", "reserve"]


def test_a_call_id_another_case_holds_stops_the_matrix_instead_of_skipping_the_cell(
    isolated, monkeypatch, capsys
):
    # A reservation from before conditions existed, for a case named E1-fixed5, holds the call
    # ID E1-fixed5-call1 that E1's A cell would use. A never ran, so it is not skipped as a
    # cell already in the books: the matrix stops there and B and C are not sent.
    books_now = active(isolated)
    books_now.write_text(
        "".join(json.dumps(e) + "\n" for e in agent_cell("E1-fixed5")), "utf-8"
    )
    before = books_now.read_bytes()
    provider = live(isolated, monkeypatch, *answers())

    code = run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E1"))))

    assert code == 3
    shown = json.loads(capsys.readouterr().out)
    assert shown["stopped_after"] == {"case": "E1", "condition": "fixed5"}
    assert [(c["condition"], c["execution"], c["detail"]) for c in shown["cells"]] == [
        ("fixed5", "refused", "call_id_taken"),
        ("fixed10", "not_run", "matrix_stopped"),
        ("agent", "not_run", "matrix_stopped"),
    ]
    assert (provider.counts, provider.creates) == ([], [])
    assert books_now.read_bytes() == before


def test_cells_already_in_the_books_are_left_out_of_the_rest_a_resumed_matrix_holds_back(
    isolated, monkeypatch, capsys
):
    # E1's agent cell is already in the books (the one-question runner booked it, settled at
    # 0.024 USD), and the rest of the matrix fits exactly: A's admission holds back only B's
    # 1.4784 USD, 97.0192 + 0.024 + 1.4784 + 1.4784 = 100. Counting the booked C cell in the
    # rest would refuse A.
    books(
        (
            {"event": "reserve", "attempt": "H-1", "case": "H", "reserved_usd": 97.0192},
            {
                "event": "settle",
                "attempt": "H-1",
                "case": "H",
                "cost_usd": 97.0192,
                "cost_basis": "usage",
            },
        )
    )
    asked = {"question_sha256": run_comparison._sha256(QUESTION), "editions": [JUL]}
    rows = (
        {**agent_cell("E2")[0], "committed_usd": 97.0192},
        {**_reserve("E1", "agent", 1), **asked},
        _settle("E1", "agent", 1),
    )
    active(isolated).write_text("".join(json.dumps(e) + "\n" for e in rows), "utf-8")
    provider = live(isolated, monkeypatch, *answers()[:2])

    code = run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E1"))))

    assert code == 0
    shown = json.loads(capsys.readouterr().out)
    assert [(c["condition"], c["execution"], c["detail"]) for c in shown["cells"]] == [
        ("fixed5", "answer", None),
        ("fixed10", "answer", None),
        ("agent", "refused", "already_run"),
    ]
    assert len(provider.creates) == 2


# The Phase 4 design: B, C and D (phase4/conditions.md)


def coverage_reply(*claims: tuple[str, list[str]], coverage=None) -> dict:
    """D's final message: its coverage beside the unchanged answer object."""
    answer = {
        "status": "answered",
        "claims": [{"text": t, "citations": c} for t, c in claims],
        "missing_evidence": [],
    }
    parts = coverage or [{"part": "Pauschale", "status": "covered", "passages": [TOP5[0]]}]
    reply = final(*claims)
    reply["content"][-1]["text"] = json.dumps(
        {"coverage": parts, "answer": answer}, ensure_ascii=False
    )
    return reply


def test_the_phase3_design_is_the_default_and_its_plan_is_unchanged(isolated, capsys):
    cases = str(cases_file(isolated, case("E1")))

    assert run_comparison.main(["plan", "--cases", cases]) == 0
    default = json.loads(capsys.readouterr().out)
    assert run_comparison.main(["plan", "--design", "phase3", "--cases", cases]) == 0
    explicit = json.loads(capsys.readouterr().out)

    for plan in (default, explicit):
        plan["planned"].pop("at")
    assert default == explicit
    assert "design" not in default
    assert [c["condition"] for c in default["order"]] == ["fixed5", "fixed10", "agent"]


def frozen_input(env, monkeypatch, *cases) -> Path:
    """A cases file pinned in the place of the frozen runner input, and the test corpus's PDFs in
    the place of the frozen sources, for this test only."""
    path = cases_file(env, *cases)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(run_comparison, "PHASE4_RUNNER_INPUT_SHA256", digest)
    manifest = json.loads(env["manifest"].read_text("utf-8"))
    sources = {
        edition["effective_date"]: document["sha256"]
        for edition in manifest["editions"]
        for document in edition["documents"]
        if document["kind"] == "commentary_pdf"
    }
    monkeypatch.setattr(evidence_agent, "PHASE4_SOURCES", sources)
    return path


def phase4_path(env) -> Path:
    return env["tmp"] / "books" / evidence_agent.PHASE4_LEDGER


def phase4_ledger(env) -> list[dict]:
    return [json.loads(line) for line in phase4_path(env).read_text("utf-8").splitlines()]


def phase4_books(env, *rows: dict) -> None:
    """Phase 4 books already in use: their pin, then ``rows``."""
    pin = {
        "event": "books",
        "ledger": evidence_agent.PHASE4_LEDGER,
        "budget_usd": 40.0,
        "time_budget_s": 600.0,  # the budget ``phase4_argv`` gives every cell
        "at": "2026-11-26T00:00:00+00:00",
    }
    phase4_path(env).write_text(
        "".join(json.dumps(e) + "\n" for e in (pin, *rows)), "utf-8"
    )


def kept_at(case_id: str, usd: float) -> tuple[dict, dict]:
    """Another case's B call in the Phase 4 books, sent and kept at its whole reservation."""
    attempt = f"{case_id}-fixed10-r1-call1"
    named = {"attempt": attempt, "case": case_id, "condition": "fixed10", "repetition": 1}
    return (
        {
            "event": "reserve",
            **named,
            "question_sha256": "0" * 64,
            "editions": [JUL],
            "call": 1,
            "request_sha256": "0" * 64,
            "counted_input_tokens": 1500,
            "reserved_usd": usd,
            "at": "2026-11-26T00:00:00+00:00",
        },
        {
            "event": "settle",
            **named,
            "sent": True,
            "cost_usd": usd,
            "cost_basis": "reservation_retained",
            "above_reservation": False,
            "usage": None,
            "response_sha256": None,
            "at": "2026-11-26T00:00:00+00:00",
        },
    )


def phase4_answers(label: str = "") -> tuple[dict, ...]:
    """B, C and D of one case each answer at once, citing the top passage."""
    return (
        final((f"B{label}.", [TOP10[0]])),
        final((f"C{label}.", [TOP5[0]])),
        coverage_reply((f"D{label}.", [TOP5[0]])),
    )


def phase4_argv(env, cases: Path, *, tag: str = "2026-11-26") -> list[str]:
    return argv(env, "run", cases, tag=tag) + ["--design", "phase4"]


def untouched(env, history: bytes) -> bool:
    """The Phase 2 and 3 books as they were: the stand-in history, no Phase 3 ledger."""
    baseline = env["tmp"] / "books" / evidence_agent.HISTORICAL_LEDGER
    return baseline.read_bytes() == history and not active(env).exists()


def history(env) -> bytes:
    return (env["tmp"] / "books" / evidence_agent.HISTORICAL_LEDGER).read_bytes()


def gold(*case_ids: str) -> dict:
    """A gold file for the scorer: each case's one fact part stated by the top passage."""
    return {
        "cases": [
            {
                "id": case_id,
                "question": QUESTION,
                "editions": [JUL],
                "parts": [
                    {"id": "p1", "kind": "fact", "support": [{"passage_id": TOP5[0]}]}
                ],
            }
            for case_id in case_ids
        ]
    }


def test_the_triplet_ceiling_is_derived_from_the_pinned_configuration_and_prices():
    config = generation.Config()
    pricing = evidence_agent._prices(config)  # the repository's pricing.json, as recorded
    per_call = evidence_agent._ceiling(pricing, evidence_agent.MAX_INPUT_TOKENS, config)
    calls = sum(
        evidence_agent.CONDITIONS[name].calls for name in evidence_agent.PHASE4_CONDITIONS
    )

    assert (per_call, calls, calls * per_call) == (1_478_400, 7, 10_348_800)  # USD 10.3488
    assert run_comparison.DESIGNS["phase4"] == evidence_agent.PHASE4_CONDITIONS
    assert (evidence_agent.PHASE4_LIMIT_USD, evidence_agent.PHASE4_REPETITIONS) == (40.0, (1,))
    freeze = json.loads(
        (HERE / "results" / "2026-11-25-phase4-freeze.json").read_text("utf-8")
    )
    (runner_input,) = [f for f in freeze["files"] if f["role"] == "runner input"]
    assert run_comparison.PHASE4_RUNNER_INPUT_SHA256 == runner_input["sha256"]


def test_the_phase4_plan_admits_case_by_case_beside_the_phase4_books(
    isolated, monkeypatch, capsys
):
    nineteen = [case(f"P{n:02d}") for n in range(1, 20)]
    cases = frozen_input(isolated, monkeypatch, *nineteen)
    before, earlier = written(isolated), history(isolated)

    code = run_comparison.main(["plan", "--design", "phase4", "--cases", str(cases)])

    assert code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["design"] == "phase4"
    assert len(plan["order"]) == 57
    assert [(c["case"], c["condition"], c["label"]) for c in plan["order"][:3]] == [
        ("P01", "fixed10", "B"),
        ("P01", "agent", "C"),
        ("P01", "coverage", "D"),
    ]
    bounds = ("label", "initial_passages", "most_passages", "calls", "searches")
    assert {
        name: (*(c[k] for k in bounds), c["admission_usd"])
        for name, c in plan["conditions"].items()
    } == {
        "fixed10": ("B", 10, 10, 1, 0, 1.4784),
        "agent": ("C", 5, 10, 3, 2, 4.4352),
        "coverage": ("D", 5, 10, 3, 2, 4.4352),
    }
    # Phase 4's books alone: a fresh case needs 1 + 3 + 3 calls at the input cap, 10.3488 USD,
    # beside nothing committed under 40 USD; the whole matrix's 196.6272 is shown, not used.
    admission = {k: v for k, v in plan["admission"].items() if k != "label"}
    zero = {"calls": 0, "usd": 0.0}
    assert admission == {
        "books": "phase4-ledger.jsonl",
        "repetition": 1,
        "time_budget_s": None,
        "limit_usd": 40.0,
        "committed_usd": 0.0,
        "booked": {"usage": zero, "retained": zero, "released": zero, "open": zero},
        "headroom_usd": 40.0,
        "call_ceiling_at_input_cap_usd": 1.4784,
        "case_ceiling_usd": 10.3488,
        "cases_to_run": 19,
        "next_case": "P01",
        "next_case_worst_case_usd": 10.3488,
        "fits": True,
        "worst_case_usd": 196.6272,
    }
    assert list(plan["estimates"]["per_condition"]) == ["fixed10", "agent", "coverage"]
    assert isolated["loads"] == []
    assert written(isolated) == before
    assert untouched(isolated, earlier)


@pytest.mark.parametrize("step", ["plan", "run"])
def test_phase4_takes_the_frozen_runner_input_only(isolated, monkeypatch, capsys, step):
    live(isolated, monkeypatch)  # no reply: nothing may be sent
    pinned = frozen_input(isolated, monkeypatch, case("E1"), case("E2"))
    subset = cases_file(isolated, case("E1"), name="subset.json")
    reordered = cases_file(isolated, case("E2"), case("E1"), name="reordered.json")
    before = written(isolated)

    for other in (subset, reordered):
        command = (
            ["plan", "--design", "phase4", "--cases", str(other)]
            if step == "plan"
            else phase4_argv(isolated, other)
        )
        assert exit_code(command) == 2
        assert "frozen runner input only" in capsys.readouterr().err

    assert pinned.exists()
    assert isolated["loads"] == []
    assert written(isolated) == before


def test_a_case_fitting_exactly_runs_and_the_next_that_no_longer_fits_stops_the_run(
    isolated, monkeypatch, capsys
):
    # 29.6512 USD are kept at another case's reservation: E1's 10.3488 fits exactly beside
    # them. After E1, E2's worst case no longer fits: the run stops before anything of E2 is
    # counted or sent, and E2's cells stay out of the books.
    phase4_books(isolated, *kept_at("Z9", 29.6512))
    provider = live(isolated, monkeypatch, *phase4_answers())
    cases = frozen_input(isolated, monkeypatch, case("E1"), case("E2"))
    earlier = history(isolated)

    code = run_comparison.main(phase4_argv(isolated, cases))

    assert code == 3
    assert (len(provider.counts), len(provider.creates)) == (3, 3)
    shown = json.loads(capsys.readouterr().out)
    assert [(c["case"], c["condition"], c["execution"], c["detail"]) for c in shown["cells"]] == [
        ("E1", "fixed10", "answer", None),
        ("E1", "agent", "answer", None),
        ("E1", "coverage", "answer", None),
        ("E2", "fixed10", "refused", "admission_budget"),
        ("E2", "agent", "not_run", "matrix_stopped"),
        ("E2", "coverage", "not_run", "matrix_stopped"),
    ]
    assert shown["stopped_after"] == {"case": "E2", "condition": "fixed10"}
    events = phase4_ledger(isolated)
    assert [e.get("attempt") for e in events[3:]] == [
        a for n in ("fixed10", "agent", "coverage")
        for a in (f"E1-{n}-r1-call1",) * 2
    ]
    assert all(e["repetition"] == 1 for e in events[1:])
    assert not [e for e in events if e.get("case") == "E2"]
    assert untouched(isolated, earlier)


def test_a_next_case_one_micro_dollar_short_is_refused_before_the_model_loads(
    isolated, monkeypatch, capsys
):
    phase4_books(isolated, *kept_at("Z9", 29.651201))
    provider = live(isolated, monkeypatch)  # no reply: nothing may be counted or sent
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    before = phase4_path(isolated).read_bytes()

    assert exit_code(phase4_argv(isolated, cases)) == 3

    assert "the next case, E1, needs USD 10.3488" in capsys.readouterr().err
    assert isolated["loads"] == []
    assert (provider.counts, provider.creates) == ([], [])
    assert phase4_path(isolated).read_bytes() == before


def test_an_interrupted_run_resumes_in_frozen_order_and_never_sends_a_cell_twice(
    isolated, monkeypatch, capsys
):
    cases = frozen_input(isolated, monkeypatch, case("E1"), case("E2"))
    earlier = history(isolated)

    def interrupt():
        if len(first.creates) == 2:  # C's first call is on the wire
            raise KeyboardInterrupt

    first = live(isolated, monkeypatch, *phase4_answers(), on_create=interrupt)
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))
    capsys.readouterr()
    open_call = phase4_ledger(isolated)[-1]
    assert (open_call["event"], open_call["attempt"]) == ("reserve", "E1-agent-r1-call1")

    second = live(isolated, monkeypatch, phase4_answers()[2], *phase4_answers("2"))
    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-27")) == 0

    shown = json.loads(capsys.readouterr().out)
    assert [(c["case"], c["condition"], c["execution"]) for c in shown["cells"]] == [
        ("E1", "fixed10", "refused"),
        ("E1", "agent", "refused"),
        ("E1", "coverage", "answer"),
        ("E2", "fixed10", "answer"),
        ("E2", "agent", "answer"),
        ("E2", "coverage", "answer"),
    ]
    assert len(second.creates) == 4  # E1's D and E2's three cells; nothing of E1 again
    events = phase4_ledger(isolated)
    reserved = [e["attempt"] for e in events if e["event"] == "reserve"]
    assert len(reserved) == len(set(reserved)) == 6
    settled = {e["attempt"] for e in events if e["event"] == "settle"}
    assert set(reserved) - settled == {"E1-agent-r1-call1"}  # booked, sending unknown: kept

    assert run_comparison.main(["plan", "--design", "phase4", "--cases", str(cases)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["admission"]["booked"]["open"] == {"calls": 1, "usd": 0.71852}
    assert plan["order"][1]["calls_in_books"] == {
        "usage": 0, "retained": 0, "released": 0, "open": 1}
    assert plan["admission"]["cases_to_run"] == 0

    # The interrupted cell is kept with its call unconfirmed (open: sending unknown), so it did
    # not run: E1 stays incomplete and the repetition gives no verdict; E2 is complete.
    results = [
        json.loads((outputs(isolated, tag=tag)[1] / "result.json").read_text("utf-8"))
        for tag in ("2026-11-26", "2026-11-27")
    ]
    interrupted = results[0]["cases"][0]["cells"][1]
    assert (interrupted["status"]["execution"], interrupted["status"]["accounting"]) == (
        "aborted",
        "uncertain",
    )
    assert (interrupted["record"]["generation_calls"], interrupted["record"]["calls"]) == (0, [])
    assert [
        (x["attempt"], x["settlement"]) for x in interrupted["record"]["unconfirmed_calls"]
    ] == [("E1-agent-r1-call1", None)]
    scored = phase4_scoring.score(results, gold("E1", "E2"))
    assert [(c["case"], c["complete"]) for c in scored["cases"]] == [
        ("E1", False), ("E2", True)]
    counts = phase4_scoring.summary(scored)
    assert (counts["repetition"], counts["repetition_complete"]) == (1, False)
    assert untouched(isolated, earlier)


class SlowFirstCount(Provider):
    """The provider's HTTP side whose first token count takes longer than a cell's budget."""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Answer one request; the first count lets 601 seconds pass."""
        if request.url.path == "/v1/messages/count_tokens" and not self.counts:
            self.clock.advance(601)
        return super().__call__(request)


def test_a_call_released_before_sending_stays_never_sent_and_is_never_sent_later(
    isolated, monkeypatch, capsys
):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    provider = SlowFirstCount(isolated["clock"], *phase4_answers()[1:])
    monkeypatch.setattr(run_comparison, "_client", lambda config: provider.client())

    assert run_comparison.main(phase4_argv(isolated, cases)) == 4

    shown = json.loads(capsys.readouterr().out)
    assert [(c["condition"], c["execution"], c["detail"]) for c in shown["cells"]] == [
        ("fixed10", "deadline", "before_send"),
        ("agent", "answer", None),
        ("coverage", "answer", None),
    ]
    released = [e for e in phase4_ledger(isolated) if e.get("attempt") == "E1-fixed10-r1-call1"]
    assert [(e["event"], e.get("sent"), e.get("cost_basis")) for e in released] == [
        ("reserve", None, None), ("settle", False, "not_sent")]
    again = live(isolated, monkeypatch)  # no reply: nothing may be sent
    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-27")) == 3
    assert again.creates == []
    local = outputs(isolated, tag="2026-11-26")[1]
    result = json.loads((local / "result.json").read_text("utf-8"))
    (scored,) = phase4_scoring.score([result], gold("E1"))["cases"]
    assert (scored["complete"], scored["cells"][0]["ran"]) == (False, False)


def test_a_concurrent_invocation_is_refused_by_the_lock_and_sends_or_books_nothing(
    isolated, monkeypatch, capsys
):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    seen = {}

    def meanwhile():  # a second invocation starts while E1's B is on the wire
        if not seen:
            seen["before"] = phase4_path(isolated).read_bytes()
            seen["code"] = exit_code(phase4_argv(isolated, cases, tag="2026-11-27"))
            seen["after"] = phase4_path(isolated).read_bytes()

    provider = live(isolated, monkeypatch, *phase4_answers(), on_create=meanwhile)

    assert run_comparison.main(phase4_argv(isolated, cases)) == 0

    assert seen["code"] == 3
    assert seen["before"] == seen["after"]
    assert not outputs(isolated, tag="2026-11-27")[0].exists()
    assert len(provider.creates) == 3
    out = capsys.readouterr().out
    assert '"detail": "locked"' in out


def test_invocations_interleaving_between_cells_book_and_send_every_cell_once(
    isolated, monkeypatch, capsys
):
    cases = frozen_input(isolated, monkeypatch, case("E1"), case("E2"))
    provider = live(isolated, monkeypatch, *phase4_answers(), *phase4_answers("2"))
    real, state = evidence_agent.run_case, {}

    def between(*args, **kwargs):  # after the first cell, a second invocation runs to its end
        result = real(*args, **kwargs)
        if not state:
            state["running"] = True
            state["code"] = exit_code(phase4_argv(isolated, cases, tag="2026-11-27"))
        return result

    monkeypatch.setattr(evidence_agent, "run_case", between)

    assert run_comparison.main(phase4_argv(isolated, cases)) == 0

    assert state["code"] == 0
    assert len(provider.creates) == 6
    events = phase4_ledger(isolated)
    reserved = [e["attempt"] for e in events if e["event"] == "reserve"]
    assert reserved == [
        f"{c}-{n}-r1-call1" for c in ("E1", "E2") for n in ("fixed10", "agent", "coverage")
    ]
    capsys.readouterr()
    assert run_comparison.main(["plan", "--design", "phase4", "--cases", str(cases)]) == 0
    assert json.loads(capsys.readouterr().out)["admission"]["committed_usd"] == 0.144


def test_the_phase4_run_gives_b_c_and_d_their_passages_and_publishes_no_passage_id(
    isolated, monkeypatch, capsys
):
    provider = live(
        isolated,
        monkeypatch,
        final(("B.", [TOP10[9]])),
        search_call("Pauschale", "Begründung"),
        final(("C.", [TOP5[0], RANKED[5]])),
        coverage_reply(("D.", [TOP5[0]])),
    )
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    earlier = history(isolated)

    code = run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-21"))

    assert code == 0
    b, c1, _, d = provider.creates
    assert (sent(b), sent(c1), sent(d)) == (TOP10, TOP5, TOP5)
    assert d["messages"][0] == c1["messages"][0]  # D starts where C does
    assert d["system"] == (
        f"{generation.SYSTEM_PROMPT}\n\n{evidence_agent.COVERAGE_INSTRUCTION}"
    )
    assert d["output_config"]["format"]["schema"] == evidence_agent.COVERAGE_ANSWER_SCHEMA
    assert [(e["event"], e.get("attempt")) for e in phase4_ledger(isolated)] == [
        ("books", None),
        ("reserve", "E1-fixed10-r1-call1"),
        ("settle", "E1-fixed10-r1-call1"),
        ("reserve", "E1-agent-r1-call1"),
        ("settle", "E1-agent-r1-call1"),
        ("reserve", "E1-agent-r1-call2"),
        ("settle", "E1-agent-r1-call2"),
        ("reserve", "E1-coverage-r1-call1"),
        ("settle", "E1-coverage-r1-call1"),
    ]
    assert untouched(isolated, earlier)
    public, local = outputs(isolated)
    text = public.read_text("utf-8")
    assert not [pid for pid in RANKED if pid in text]  # no passage ID in the public record
    assert QUESTION not in text
    record = json.loads(text)
    (planned,) = record["cases"]
    assert planned["ranked_passages"] == 10
    assert "ranking" not in planned
    cells = planned["cells"]
    assert [(c["condition"], c["label"], c["status"]["execution"]) for c in cells] == [
        ("fixed10", "B", "answer"),
        ("agent", "C", "answer"),
        ("coverage", "D", "answer"),
    ]
    assert [c["agent"]["repetition"] for c in cells] == [1, 1, 1]
    assert [c["agent"]["supplied"] for c in cells] == [10, 10, 5]
    assert [c["answer"]["cited_passages"] for c in cells] == [1, 2, 1]
    assert cells[1]["agent"]["searches"][0]["returned"] == 5
    assert cells[0]["agent"]["spending"] == {
        "books": "phase4-ledger.jsonl",
        "budget_usd": 40.0,
        "committed_before_usd": 0.0,
        "admission_usd": 1.4784,
        "rest_usd": 8.8704,
    }
    assert cells[2]["agent"]["coverage"] == [
        {
            "call": 1,
            "action": "answer",
            "check": "ok",
            "parts": 1,
            "covered": 1,
            "missing": 0,
            "search_for": None,
            "missing_not_reported": False,
        }
    ]
    assert record["run"]["design"] == "phase4"
    assert record["run"]["books"] == {
        "ledger": "phase4-ledger.jsonl",
        "limit_usd": 40.0,
        "repetition": 1,
        "runner_input_sha256": run_comparison.PHASE4_RUNNER_INPUT_SHA256,
    }
    assert record["run"]["configuration"]["budget_usd"] == 40.0  # the cap in force
    conditions = record["run"]["configuration"]["conditions"]
    assert list(conditions) == ["fixed10", "agent", "coverage"]
    assert "answer_format_sha256" in conditions["coverage"]
    assert record["notes"] == list(run_comparison.NOTES_PHASE4)
    kept = json.loads((local / "result.json").read_text("utf-8"))
    (kept_case,) = kept["cases"]
    assert kept_case["ranking"] == TOP10  # the local record keeps every ID
    detail = kept_case["ranking_detail"]  # and the scores the public record leaves out
    assert [(r["rank"], r["passage_id"]) for r in detail] == list(enumerate(TOP10, start=1))
    assert all(isinstance(r["score"], float) for r in detail)
    assert kept_case["cells"][2]["local"]["coverage"][0]["coverage"][0]["passages"] == [
        TOP5[0]
    ]
    assert json.loads(capsys.readouterr().out)["exit_code"] == 0


@pytest.mark.parametrize("linked", ["local", "run"])
def test_a_run_whose_local_folder_is_a_link_is_refused_before_the_model_loads(
    isolated, monkeypatch, capsys, linked
):
    live(isolated, monkeypatch)  # no reply: nothing may be sent
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    elsewhere = isolated["tmp"] / "published"
    elsewhere.mkdir()
    local = isolated["tmp"] / "local"
    if linked == "local":
        local.symlink_to(elsewhere, target_is_directory=True)
    else:
        local.mkdir()
        (local / "2026-11-26-comparison").symlink_to(elsewhere, target_is_directory=True)

    assert exit_code(phase4_argv(isolated, cases)) == 3

    assert "is a symbolic link" in capsys.readouterr().err
    assert isolated["loads"] == []
    assert list(elsewhere.iterdir()) == []
    assert not phase4_path(isolated).exists()


@pytest.mark.parametrize("condition", ["agent", "coverage"])
def test_a_shared_replay_failure_keeps_the_sent_cell_as_run_and_a_restart_sends_nothing_again(
    isolated, monkeypatch, capsys, condition
):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, c, d = phase4_answers()
    replies = (b, unencodable("agent")) if condition == "agent" else (b, c, unencodable(condition))
    live(isolated, monkeypatch, *replies)

    with pytest.raises(UnicodeError) as raised:  # the replay cannot be written: the run ends
        run_comparison.main(phase4_argv(isolated, cases))

    attempt = f"E1-{condition}-r1-call1"
    events = phase4_ledger(isolated)
    assert [(e["event"], e.get("attempt")) for e in events][-2:] == [
        ("reserve", attempt),
        ("settle", attempt),
    ]  # sent, settled from its usage, nothing more reserved
    public, local = outputs(isolated, tag="2026-11-26")
    first = json.loads((local / "result.json").read_text("utf-8"))
    kept_cell = first["cases"][0]["cells"][-1]
    error = raised.type.__name__
    assert (kept_cell["condition"], kept_cell["status"]) == (
        condition,
        {"execution": "aborted", "detail": error, "answer": None, "accounting": "priced"},
    )
    record = kept_cell["record"]
    assert (record["outcome"], record["detail"], "trace" in record) == ("aborted", error, False)
    assert (record["generation_calls"], record["unconfirmed_calls"]) == (1, [])
    assert [(x["attempt"], x["sent"], x["cost_basis"]) for x in record["calls"]] == [
        (attempt, True, "usage")
    ]
    request = (local / "requests" / f"{attempt}.json").read_bytes()
    response = (local / "responses" / f"{attempt}.json").read_bytes()
    assert record["calls"][0]["request_sha256"] == hashlib.sha256(request).hexdigest()
    assert record["calls"][0]["response_sha256"] == hashlib.sha256(response).hexdigest()
    # The search its call ran is kept as the cell recorded it; nothing after it is.
    (search,) = record["searches"]
    ran = "passages" if condition == "agent" else "refused_coverage"  # D named no passage it had
    assert search["outcome"] == ran
    assert record["supplied"] == TOP5 + [r["passage_id"] for r in search["returned"]]
    assert "cited" not in record
    assert len(record["coverage"]) == 1 if condition == "coverage" else "coverage" not in record
    shown = json.loads(public.read_text("utf-8"))["cases"][0]["cells"][-1]
    assert (shown["status"]["execution"], shown["agent"]["generation_calls"]) == ("aborted", 1)
    assert not any(pid in json.dumps(shown) for pid in RANKED)  # no passage ID published
    capsys.readouterr()

    again = live(isolated, monkeypatch, d) if condition == "agent" else live(isolated, monkeypatch)
    code = run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-27"))

    results = [first]
    if condition == "agent":  # D only: B and C are in the books and never sent again
        assert (code, len(again.creates)) == (0, 1)
        second = outputs(isolated, tag="2026-11-27")[1] / "result.json"
        results.append(json.loads(second.read_text("utf-8")))
    else:  # every cell is in the books: nothing counted or sent, nothing written
        assert (code, again.counts, again.creates) == (3, [], [])
        assert not outputs(isolated, tag="2026-11-27")[1].exists()
    scored = phase4_scoring.score(results, gold("E1"))
    (case_,) = scored["cases"]
    assert [(x["condition"], x["ran"]) for x in case_["cells"]] == [
        ("fixed10", True),
        ("agent", True),
        ("coverage", True),
    ]
    assert case_["complete"] is True  # the cell ran and failed: a non-success, but run
    aborted = next(x for x in case_["cells"] if x["condition"] == condition)
    assert (aborted["outcome"], aborted["calls"], aborted["searches"]) == ("aborted", 1, 1)
    # One decision, the one that happened: the search at call 1 (no part was missing); the call
    # the replay never made is no decision point, and no action is invented for it.
    action = "search_run" if condition == "agent" else "search_refused"
    assert [(p["call"], p["kind"], p["action"]) for p in aborted["decision_points"]] == [
        (1, "no_search_needed", action)
    ]
    counts = phase4_scoring.summary(scored)["conditions"][condition]
    assert (counts["aborted"], counts["calls_per_cell"], counts["searches_per_cell"]) == (
        1,
        {"1": 1},
        {"1": 1},
    )
    # T3 counts the executed search alone; the supplementary A1 report counts it, or the
    # refused request, beside it.
    executed = int(condition == "agent")
    assert counts["unnecessary"] == executed
    assert counts["unnecessary_attempts"] == {
        "executed": executed,
        "refused": 1 - executed,
        "total": 1,
    }


def test_estimates_read_cells_of_every_condition_under_either_design(
    isolated, monkeypatch, capsys
):
    rows = [agent_cell("E2")[0]]
    for name, calls in (("fixed5", 1), ("fixed10", 1), ("agent", 2)):
        for n in range(1, calls + 1):
            rows += [_reserve("E3", name, n), _settle("E3", name, n)]
    active(isolated).write_text("".join(json.dumps(e) + "\n" for e in rows), "utf-8")
    d_cell = (_reserve("E4", "coverage", 1), _settle("E4", "coverage", 1))
    phase4_books(  # D is booked in Phase 4's books only
        isolated,
        *({**e, "attempt": "E4-coverage-r1-call1", "repetition": 1} for e in d_cell),
    )
    cases = str(frozen_input(isolated, monkeypatch, case("E5")))
    seen = {}

    for design in ("phase3", "phase4"):
        assert run_comparison.main(["plan", "--design", design, "--cases", cases]) == 0
        per = json.loads(capsys.readouterr().out)["estimates"]["per_condition"]
        seen[design] = {n: (c["observed_cells"], c["usd_per_cell"]) for n, c in per.items()}

    # fixed5: the history (0.25) and E3 (0.024), mean 0.137; B and C E3 alone; D the Phase 4
    # books' E4.
    assert seen == {
        "phase3": {"fixed5": (2, 0.137), "fixed10": (1, 0.024), "agent": (1, 0.048)},
        "phase4": {"fixed10": (1, 0.024), "agent": (1, 0.048), "coverage": (1, 0.024)},
    }


@pytest.mark.parametrize(
    ("step", "case_id"), [("plan", "E1"), ("run", "E1"), ("run", "E9")]
)
def test_the_default_design_refuses_a_frozen_phase4_case_before_anything_loads(
    isolated, monkeypatch, capsys, step, case_id
):
    live(isolated, monkeypatch)  # no reply: nothing may be sent
    question = hashlib.sha256(QUESTION.encode("utf-8")).hexdigest()
    monkeypatch.setattr(evidence_agent, "PHASE4_CASES", {"E1": (question, (JUL,))})
    before = written(isolated)

    # By its ID (a plan has no question) or by its question under another ID.
    assert exit_code(argv(isolated, step, cases_file(isolated, case(case_id)))) == 2

    assert "frozen Phase 4 case" in capsys.readouterr().err
    assert isolated["loads"] == []
    assert written(isolated) == before
    assert not active(isolated).exists()


class FailFirstCount(Provider):
    """The provider's HTTP side whose first token count fails, so nothing is reserved."""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Answer one request; the first count is a server error."""
        if request.url.path == "/v1/messages/count_tokens" and not self.counts:
            self.counts.append({})
            return httpx.Response(500, json={"type": "error", "error": {"type": "api_error"}})
        return super().__call__(request)


def test_a_cell_that_booked_nothing_stops_the_run_so_a_rerun_keeps_the_frozen_order(
    isolated, monkeypatch, capsys
):
    cases = frozen_input(isolated, monkeypatch, case("E1"), case("E2"))
    provider = FailFirstCount(isolated["clock"])
    monkeypatch.setattr(run_comparison, "_client", lambda config: provider.client())

    assert run_comparison.main(phase4_argv(isolated, cases)) == 4

    shown = json.loads(capsys.readouterr().out)
    assert shown["stopped_after"] == {"case": "E1", "condition": "fixed10"}
    assert [c["execution"] for c in shown["cells"]] == ["provider_error"] + ["not_run"] * 5
    assert provider.creates == []
    assert not phase4_path(isolated).exists()  # nothing booked, nothing pinned
    again = live(isolated, monkeypatch, *phase4_answers(), *phase4_answers("2"))
    rerun = argv(isolated, "run", cases, tag="2026-11-27", budget="601")

    # Another time budget is accepted: the attempt that booked nothing pinned none.
    assert run_comparison.main([*rerun, "--design", "phase4"]) == 0

    assert [sent(body)[:1] for body in again.creates][:1] == [[TOP10[0]]]  # B first
    reserved = [e["attempt"] for e in phase4_ledger(isolated) if e["event"] == "reserve"]
    assert reserved[0] == "E1-fixed10-r1-call1"


def test_a_rerun_with_another_time_budget_is_refused_before_the_model_loads(
    isolated, monkeypatch, capsys
):
    cases = frozen_input(isolated, monkeypatch, case("E1"), case("E2"))
    live(isolated, monkeypatch, *phase4_answers())

    def stop_after_e1(the_task, **kwargs):  # the first run ends after E1
        if the_task.case_id == "E2":
            raise KeyboardInterrupt
        return real(the_task, **kwargs)

    real = evidence_agent.run_case
    monkeypatch.setattr(evidence_agent, "run_case", stop_after_e1)
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))
    monkeypatch.setattr(evidence_agent, "run_case", real)
    capsys.readouterr()
    again = live(isolated, monkeypatch)  # no reply: nothing may be sent
    loads = len(isolated["loads"])
    command = argv(isolated, "run", cases, tag="2026-11-27", budget="601")

    assert exit_code([*command, "--design", "phase4"]) == 3

    assert "pinned to a time budget of 600.0 s" in capsys.readouterr().err
    assert (again.counts, again.creates) == ([], [])
    assert len(isolated["loads"]) == loads


def test_the_corpus_must_be_the_frozen_one_before_anything_is_counted(
    isolated, monkeypatch, capsys
):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    monkeypatch.setattr(evidence_agent, "PHASE4_SOURCES", {JUL: "0" * 64})
    provider = live(isolated, monkeypatch)  # no reply: nothing may be sent

    assert exit_code(phase4_argv(isolated, cases)) == 3

    assert "the corpus is not the frozen one" in capsys.readouterr().err
    assert (provider.counts, provider.creates) == ([], [])
    assert not phase4_path(isolated).exists()
    assert not outputs(isolated, tag="2026-11-26")[1].exists()  # the claim is given back


def test_a_tag_another_invocation_holds_is_refused_and_an_unused_claim_given_back(
    isolated, monkeypatch, capsys
):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    provider = live(isolated, monkeypatch)  # no reply: nothing may be sent
    held = outputs(isolated, tag="2026-11-26")[1]
    held.mkdir(parents=True)  # claimed, still empty: another invocation's run folder

    assert exit_code(phase4_argv(isolated, cases)) == 3

    assert "already exists" in capsys.readouterr().err
    assert held.is_dir()  # left as it is: it is not this invocation's
    phase4_books(isolated, *kept_at("Z9", 29.651201))  # the next case no longer fits
    assert exit_code(phase4_argv(isolated, cases, tag="2026-11-27")) == 3
    assert not outputs(isolated, tag="2026-11-27")[1].exists()  # claimed, then given back
    assert (provider.counts, provider.creates) == ([], [])


def test_a_linked_request_folder_in_the_run_folder_is_refused(isolated, monkeypatch, capsys):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    live(isolated, monkeypatch)  # no reply: nothing may be sent
    elsewhere = isolated["tmp"] / "published"
    elsewhere.mkdir()
    run = outputs(isolated, tag="2026-11-26")[1]
    run.mkdir(parents=True)
    (run / "requests").symlink_to(elsewhere, target_is_directory=True)

    assert exit_code(phase4_argv(isolated, cases)) == 3

    assert "is a symbolic link" in capsys.readouterr().err
    assert list(elsewhere.iterdir()) == []


def test_a_phase3_run_under_a_tag_a_phase4_run_claimed_is_refused(
    isolated, monkeypatch, capsys
):
    paths = run_comparison._paths("2026-11-26")
    refusal, owner = run_comparison._claim(paths, "phase4")
    assert refusal is None  # a Phase 4 invocation's claim, still unused
    provider = live(isolated, monkeypatch)  # no reply: nothing may be sent
    command = argv(isolated, "run", cases_file(isolated, case("E1")), tag="2026-11-26")

    assert exit_code(command) == 3

    assert "already exists" in capsys.readouterr().err
    assert (provider.counts, provider.creates) == ([], [])
    run_comparison._release(paths, owner)
    assert not paths["local"].exists()  # an unused claim is given back whole, by its owner


def test_an_interruption_before_any_cell_gives_the_claim_back(isolated, monkeypatch):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    live(isolated, monkeypatch)  # no reply: nothing may be sent

    def interrupted(manifest):
        raise KeyboardInterrupt

    monkeypatch.setattr(run_question, "_load", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))

    assert not outputs(isolated, tag="2026-11-26")[1].exists()


# Both designs claim the tag before the model loads (Erhan, 2026-11-27)


@pytest.mark.parametrize("moment", ["while_loading", "before_its_claim"])
@pytest.mark.parametrize("outer", ["phase3", "phase4"])
def test_overlapping_invocations_of_either_design_leave_the_tag_to_the_first_claim(
    isolated, monkeypatch, capsys, outer, moment
):
    tag = "2026-11-27"
    commands = {
        "phase3": argv(isolated, "run", cases_file(isolated, case("E2"), name="p3.json"), tag=tag),
        "phase4": phase4_argv(isolated, frozen_input(isolated, monkeypatch, case("E1")), tag=tag),
    }
    inner = "phase4" if outer == "phase3" else "phase3"
    # While the outer invocation loads, the tag is already claimed: the inner one is refused.
    # Between the outer one's existing-output check and its claim, the inner one claims first
    # and runs: the outer one is refused at its own claim.
    winner = outer if moment == "while_loading" else inner
    loser = inner if winner == outer else outer
    provider = live(isolated, monkeypatch, *(answers() if winner == "phase3" else phase4_answers()))
    seen: dict = {}
    hooked = "_load" if moment == "while_loading" else "_existing"
    real = getattr(run_question, hooked)

    def meanwhile(value):  # the inner invocation starts here, once
        checked = real(value) if hooked == "_existing" else None  # the outer check, passed
        if "code" not in seen:
            seen["code"] = None
            seen["code"] = exit_code(commands[inner])
        return checked if hooked == "_existing" else real(value)

    monkeypatch.setattr(run_question, hooked, meanwhile)

    codes = {outer: exit_code(commands[outer])}
    codes[inner] = seen["code"]

    assert (codes[winner], codes[loser]) == (0, 3)
    err = capsys.readouterr().err
    assert "already exists" in err
    if moment == "before_its_claim":  # refused by the claim itself, not by an existing file
        assert "of either design" in err
    assert len(isolated["loads"]) == 1  # the loser loaded nothing
    assert len(provider.creates) == 3  # and sent nothing: the winner's cells only
    loser_books = phase4_path(isolated) if loser == "phase4" else active(isolated)
    assert not loser_books.exists()  # nor booked anything
    public, local = outputs(isolated, tag=tag)
    claim = json.loads((local / run_comparison.CLAIM).read_text("utf-8"))
    assert claim["design"] == winner  # the tag stays the winner's
    record = json.loads(public.read_text("utf-8"))
    assert [c["case"] for c in record["cases"]] == (["E2"] if winner == "phase3" else ["E1"])


def test_a_claim_that_cannot_be_written_is_given_back_before_anything_loads(
    isolated, monkeypatch, capsys
):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    provider = live(isolated, monkeypatch)  # no reply: nothing may be sent
    folder = outputs(isolated, tag="2026-11-26")[1]
    _fail_opening(monkeypatch, folder / run_comparison.CLAIM)

    assert exit_code(phase4_argv(isolated, cases)) == 3

    assert "the claim on it cannot be written" in capsys.readouterr().err
    assert not folder.exists()  # this invocation's empty folder goes again
    assert (provider.counts, provider.creates, isolated["loads"]) == ([], [], [])


def test_a_claim_file_another_invocation_wrote_in_the_new_folder_stays(isolated, monkeypatch):
    paths = run_comparison._paths("2026-11-26")
    real = Path.open

    def raced(self, mode="r", *args, **kwargs):  # another invocation's claim appears first
        if self == paths["local"] / run_comparison.CLAIM and "x" in mode:
            monkeypatch.setattr(Path, "open", real)
            with real(self, "x", encoding="utf-8") as handle:
                handle.write('{"design": "phase4", "owner": "theirs"}\n')
        return real(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", raced)
    refusal, owner = run_comparison._claim(paths, "phase3")

    assert owner is None and "the claim on it cannot be written" in refusal
    theirs = paths["local"] / run_comparison.CLAIM
    assert json.loads(theirs.read_text("utf-8"))["owner"] == "theirs"  # left as it is


@pytest.mark.parametrize("design", ["phase3", "phase4"])
def test_a_failure_before_the_first_cell_gives_the_unused_claim_back(
    isolated, monkeypatch, design
):
    command = (
        phase4_argv(isolated, frozen_input(isolated, monkeypatch, case("E1")))
        if design == "phase4"
        else argv(isolated, "run", cases_file(isolated, case("E2")), tag="2026-11-26")
    )
    provider = live(isolated, monkeypatch)  # no reply: nothing may be sent

    def failing(*args, **kwargs):  # the run's provenance cannot be taken
        raise RuntimeError("provenance unavailable")

    monkeypatch.setattr(run_comparison, "_provenance", failing)
    with pytest.raises(RuntimeError, match="provenance unavailable"):
        run_comparison.main(command)

    assert not outputs(isolated, tag="2026-11-26")[1].exists()  # given back whole
    assert (provider.counts, provider.creates) == ([], [])


def test_only_the_owner_gives_back_an_unused_claim_and_never_one_holding_a_file(isolated):
    paths = run_comparison._paths("2026-11-26")
    refusal, owner = run_comparison._claim(paths, "phase3")
    assert refusal is None
    claim_file = paths["local"] / run_comparison.CLAIM
    claim = claim_file.read_bytes()
    assert json.loads(claim)["design"] == "phase3"

    run_comparison._release(paths, "another invocation's token")
    assert claim_file.read_bytes() == claim  # another owner's claim stays
    artifact = paths["local"] / "requests" / "E1-fixed5-call1.json"
    artifact.parent.mkdir()
    artifact.write_text("{}", "utf-8")
    run_comparison._release(paths, owner)
    assert claim_file.read_bytes() == claim and artifact.exists()  # in use: all of it stays
    artifact.unlink()
    artifact.parent.rmdir()
    run_comparison._release(paths, owner)
    assert not paths["local"].exists()  # unused and its own: given back whole


# A Phase 4 cell an unexpected error or an interruption ends: what the books show of it is kept


def test_an_interruption_after_a_sent_call_keeps_the_cell_as_run_with_its_open_call_apart(
    isolated, monkeypatch, capsys
):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, _, d = phase4_answers()

    def interrupt():
        if len(first.creates) == 3:  # C's second call is on the wire
            raise KeyboardInterrupt

    first = live(
        isolated,
        monkeypatch,
        b,
        search_call("Pauschale", "Begründung"),
        final(("C.", [TOP5[0]])),
        on_create=interrupt,
    )
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))

    local = outputs(isolated, tag="2026-11-26")[1]
    kept_cell = json.loads((local / "result.json").read_text("utf-8"))["cases"][0]["cells"][1]
    record = kept_cell["record"]
    assert (kept_cell["status"]["execution"], kept_cell["status"]["accounting"]) == (
        "aborted",
        "uncertain",
    )
    assert (record["generation_calls"], [x["attempt"] for x in record["calls"]]) == (
        1,
        ["E1-agent-r1-call1"],
    )
    assert [(x["attempt"], x["settlement"]) for x in record["unconfirmed_calls"]] == [
        ("E1-agent-r1-call2", None)
    ]  # booked, sending unknown: confirms nothing
    assert [s["outcome"] for s in record["searches"]] == ["passages"]  # call 1's, as recorded
    capsys.readouterr()
    again = live(isolated, monkeypatch, d)

    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-27")) == 0

    assert len(again.creates) == 1  # D only: neither of C's calls is sent again
    results = [
        json.loads((outputs(isolated, tag=tag)[1] / "result.json").read_text("utf-8"))
        for tag in ("2026-11-26", "2026-11-27")
    ]
    (case_,) = phase4_scoring.score(results, gold("E1"))["cases"]
    c_cell = case_["cells"][1]
    assert (c_cell["ran"], c_cell["outcome"], c_cell["calls"]) == (True, "aborted", 1)
    assert [(p["call"], p["action"]) for p in c_cell["decision_points"]] == [(1, "search_run")]
    assert case_["complete"] is True


def test_an_aborted_cell_counts_only_the_calls_this_run_saved(isolated, monkeypatch, capsys):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    named = {"case": "E1", "condition": "agent", "repetition": 1}
    elsewhere = {"attempt": "E1-agent-r1-call1", **named}  # booked and sent by another run
    phase4_books(
        isolated,
        {
            "event": "reserve",
            **elsewhere,
            "question_sha256": hashlib.sha256(QUESTION.encode("utf-8")).hexdigest(),
            "editions": [JUL],
            "call": 1,
            "request_sha256": "0" * 64,
            "counted_input_tokens": 1500,
            "reserved_usd": 0.5,
            "at": "2026-11-26T00:00:00+00:00",
        },
        {
            "event": "settle",
            **elsewhere,
            "sent": True,
            "cost_usd": 0.5,
            "cost_basis": "reservation_retained",
            "above_reservation": False,
            "usage": None,
            "response_sha256": None,
            "at": "2026-11-26T00:00:00+00:00",
        },
    )
    live(isolated, monkeypatch, phase4_answers()[0])
    real = evidence_agent.run_case

    def failing(the_task, **kwargs):  # the loop fails unexpectedly before C books anything
        if kwargs["condition"] == "agent":
            raise RuntimeError("unexpected failure in the loop")
        return real(the_task, **kwargs)

    monkeypatch.setattr(evidence_agent, "run_case", failing)
    with pytest.raises(RuntimeError, match="unexpected failure"):
        run_comparison.main(phase4_argv(isolated, cases))

    local = outputs(isolated, tag="2026-11-26")[1]
    kept_cell = json.loads((local / "result.json").read_text("utf-8"))["cases"][0]["cells"][1]
    assert kept_cell["status"] == {
        "execution": "aborted",
        "detail": "RuntimeError",
        "answer": None,
        "accounting": "nothing_reserved",
    }
    assert kept_cell["record"]["generation_calls"] == 0  # the other run's send is not this one's
    assert (kept_cell["record"]["calls"], kept_cell["record"]["unconfirmed_calls"]) == ([], [])


def test_an_uncertain_first_booking_stops_the_run_before_anything_is_sent(
    isolated, monkeypatch, capsys
):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    provider = live(isolated, monkeypatch, *phase4_answers())
    real = os.link

    def linked_then_failed(source, target, *args, **kwargs):  # in force, reported as failed
        real(source, target, *args, **kwargs)
        raise OSError(errno.EIO, "simulated failure after the link")

    monkeypatch.setattr(os, "link", linked_then_failed)

    # A failed write exits 7 before the accounting's 6 (EPILOG); the run stops either way.
    assert run_comparison.main(phase4_argv(isolated, cases)) == 7

    assert provider.creates == []
    shown = json.loads(capsys.readouterr().out)
    assert [(c["condition"], c["execution"], c["detail"], c["accounting"]) for c in shown["cells"]] == [
        ("fixed10", "persistence_error", "reservation_not_saved", "uncertain"),
        ("agent", "not_run", "matrix_stopped", "nothing_reserved"),
        ("coverage", "not_run", "matrix_stopped", "nothing_reserved"),
    ]
    pin, reserve = phase4_ledger(isolated)  # the pin and the first reservation, whole
    assert (pin["event"], reserve["attempt"]) == ("books", "E1-fixed10-r1-call1")


def test_a_response_saved_before_its_settlement_proves_the_send(isolated, monkeypatch, capsys):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, c, d = phase4_answers()
    live(isolated, monkeypatch, b, c)
    real = generation._append

    def interrupted(ledger, event):  # C's response is saved; its settlement never reaches the books
        if event["event"] == "settle" and event["attempt"] == "E1-agent-r1-call1":
            raise KeyboardInterrupt
        return real(ledger, event)

    monkeypatch.setattr(generation, "_append", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))
    monkeypatch.setattr(generation, "_append", real)

    local = outputs(isolated, tag="2026-11-26")[1]
    kept_cell = json.loads((local / "result.json").read_text("utf-8"))["cases"][0]["cells"][1]
    assert (kept_cell["status"]["execution"], kept_cell["status"]["accounting"]) == (
        "aborted",
        "uncertain",  # its cost is not settled: held at its reservation
    )
    (call,) = kept_cell["record"]["calls"]
    response = (local / "responses" / "E1-agent-r1-call1.json").read_bytes()
    assert (call["sent"], call["cost_basis"], call["response_sha256"]) == (
        True,
        None,
        hashlib.sha256(response).hexdigest(),
    )
    assert kept_cell["record"]["generation_calls"] == 1  # the saved response proves the send
    capsys.readouterr()
    again = live(isolated, monkeypatch, d)

    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-27")) == 0

    assert len(again.creates) == 1  # D only: C is never sent again
    results = [
        json.loads((outputs(isolated, tag=tag)[1] / "result.json").read_text("utf-8"))
        for tag in ("2026-11-26", "2026-11-27")
    ]
    (case_,) = phase4_scoring.score(results, gold("E1"))["cases"]
    c_cell = case_["cells"][1]
    assert (c_cell["ran"], c_cell["outcome"], case_["complete"]) == (True, "aborted", True)
    # Its answer turn was never processed: the call that ended the cell is no decision with an
    # action, so it is listed and left out of every rate, never taken as an answer.
    assert [(p["call"], p["action"]) for p in c_cell["decision_points"]] == [(1, "no_action")]


@pytest.mark.parametrize("first", ["fixed10", "agent"])
def test_a_send_another_run_booked_after_this_one_stopped_is_not_this_ones(
    isolated, monkeypatch, capsys, first
):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, c, d = phase4_answers()
    provider = live(isolated, monkeypatch, b, c, d)
    attempt = f"E1-{first}-r1-call1"
    real_books, real_append = evidence_agent._create_books, generation._append
    real_cell, seen = evidence_agent.phase4_cell, {}

    def stop_before_booking():  # this run saved the request, then stopped before booking it
        if not seen:
            seen["stopped"] = True
            raise KeyboardInterrupt

    def books_once(ledger, events, errors):  # B's booking is the books' first event
        if events[-1]["attempt"] == attempt:
            stop_before_booking()
        return real_books(ledger, events, errors)

    def append_once(ledger, event):  # C's booking is a later reservation
        if event["event"] == "reserve" and event["attempt"] == attempt:
            stop_before_booking()
        return real_append(ledger, event)

    def recovering(*args):  # before this run reads the books, another run books and sends it
        if "other" not in seen:
            seen["other"] = exit_code(phase4_argv(isolated, cases, tag="2026-11-27"))
        return real_cell(*args)

    monkeypatch.setattr(evidence_agent, "_create_books", books_once)
    monkeypatch.setattr(generation, "_append", append_once)
    monkeypatch.setattr(evidence_agent, "phase4_cell", recovering)
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))

    assert seen["other"] == 0 and len(provider.creates) == 3  # each cell sent once in all
    public, local = outputs(isolated, tag="2026-11-26")
    assert (local / "requests" / f"{attempt}.json").exists()  # its own request, kept
    if first == "fixed10":  # this run booked nothing: it writes no record of the matrix
        assert not public.exists() and not (local / "result.json").exists()
    else:
        mine = json.loads((local / "result.json").read_text("utf-8"))["cases"][0]["cells"][1]
        assert mine["status"]["accounting"] == "nothing_reserved"  # not the other run's books
        assert (mine["record"]["generation_calls"], mine["record"]["calls"]) == (0, [])
        assert mine["record"]["unconfirmed_calls"] == []  # the other run's booking is left out
    results = [
        json.loads(path.read_text("utf-8"))
        for path in (outputs(isolated, tag=tag)[1] / "result.json" for tag in ("2026-11-26", "2026-11-27"))
        if path.exists()
    ]
    (case_,) = phase4_scoring.score(results, gold("E1"))["cases"]  # no cell counted twice
    assert [(x["condition"], x["ran"]) for x in case_["cells"]] == [
        ("fixed10", True),
        ("agent", True),
        ("coverage", True),
    ]


def test_a_settlement_cut_short_keeps_the_send_this_run_proves(isolated, monkeypatch, capsys):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, c, d = phase4_answers()
    live(isolated, monkeypatch, b, c)
    real = generation._append

    def cut_short(ledger, event):  # C's settlement reaches the ledger only in part
        if event["event"] == "settle" and event["attempt"] == "E1-agent-r1-call1":
            with ledger.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event)[:40])
            raise KeyboardInterrupt
        return real(ledger, event)

    monkeypatch.setattr(generation, "_append", cut_short)
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))
    monkeypatch.setattr(generation, "_append", real)

    local = outputs(isolated, tag="2026-11-26")[1]
    kept_cell = json.loads((local / "result.json").read_text("utf-8"))["cases"][0]["cells"][1]
    assert kept_cell["status"]["accounting"] == "unknown"  # the books cannot be read
    assert kept_cell["record"]["generation_calls"] == 1  # its own request and response show it
    assert (kept_cell["record"]["calls"][0]["sent"], kept_cell["record"]["calls"][0]["cost_basis"]) == (
        True,
        None,
    )
    capsys.readouterr()
    again = live(isolated, monkeypatch, d)
    assert exit_code(phase4_argv(isolated, cases, tag="2026-11-27")) == 3  # damaged: refused
    assert again.creates == []
    path = phase4_path(isolated)  # Erhan repairs the books: the line cut short is removed
    text = path.read_text("utf-8")
    path.write_text(text[: text.rindex("\n") + 1], "utf-8")

    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-28")) == 0

    assert len(again.creates) == 1  # D only: C is in the books and never sent again
    results = [
        json.loads((outputs(isolated, tag=tag)[1] / "result.json").read_text("utf-8"))
        for tag in ("2026-11-26", "2026-11-28")
    ]
    (case_,) = phase4_scoring.score(results, gold("E1"))["cases"]
    assert (case_["cells"][1]["ran"], case_["complete"]) == (True, True)


def test_an_interruption_while_the_lock_is_given_back_keeps_the_cells_record(
    isolated, monkeypatch, capsys
):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, _, d = phase4_answers()
    live(isolated, monkeypatch, b, search_call("Pauschale", "Begründung"), final(("C.", [TOP5[0]])))
    real, uses = generation._ledger_lock, []

    @contextlib.contextmanager
    def releasing(ledger):  # C's cell ends, then its lock is interrupted while given back
        uses.append(ledger)
        with real(ledger) as held:
            yield held
        if len(uses) == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(generation, "_ledger_lock", releasing)
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))
    monkeypatch.setattr(generation, "_ledger_lock", real)

    local = outputs(isolated, tag="2026-11-26")[1]
    first = json.loads((local / "result.json").read_text("utf-8"))
    record = first["cases"][0]["cells"][1]["record"]
    assert (record["outcome"], record["ended"], record["generation_calls"]) == ("aborted", "answer", 2)
    assert [s["outcome"] for s in record["searches"]] == ["passages"]
    capsys.readouterr()
    live(isolated, monkeypatch, d)
    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-27")) == 0
    second = json.loads((outputs(isolated, tag="2026-11-27")[1] / "result.json").read_text("utf-8"))
    (case_,) = phase4_scoring.score([first, second], gold("E1"))["cases"]
    points = case_["cells"][1]["decision_points"]
    assert [(p["call"], p["action"]) for p in points] == [(1, "search_run"), (2, "answer")]
    assert case_["complete"] is True


def test_an_aborted_cell_without_its_record_keeps_only_what_the_books_show(
    isolated, monkeypatch, capsys
):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    live(isolated, monkeypatch, *phase4_answers()[:2])
    real = evidence_agent.run_case

    def failing(the_task, **kwargs):  # C ran to its end, then an error without its record
        result = real(the_task, **kwargs)
        if kwargs["condition"] == "agent":
            raise RuntimeError("unexpected failure after the cell")
        return result

    monkeypatch.setattr(evidence_agent, "run_case", failing)
    with pytest.raises(RuntimeError, match="after the cell"):
        run_comparison.main(phase4_argv(isolated, cases))

    local = outputs(isolated, tag="2026-11-26")[1]
    first = json.loads((local / "result.json").read_text("utf-8"))
    record = first["cases"][0]["cells"][1]["record"]
    assert (record["generation_calls"], record["trace"]) == (1, "not_recorded")
    assert not {"searches", "supplied", "cited"} & record.keys()
    (case_,) = phase4_scoring.score([first], gold("E1"))["cases"]
    c_cell = case_["cells"][1]
    assert (c_cell["ran"], c_cell["searches"], c_cell["decision_points"]) == (True, None, [])


def test_an_interruption_while_ds_search_is_ranked_keeps_ds_recorded_coverage_unscored(
    isolated, monkeypatch, capsys
):
    # D's call 1 is sent and settled; D records its coverage decision and asks a valid
    # targeted search for its missing part 2; the search is being ranked (the e5 boundary
    # embeds its query) when the interruption comes, before any search result is recorded.
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, c, _ = phase4_answers()
    query = "Begründung der Pauschale"
    coverage = [part("Pauschale", "covered", TOP5[0]), part("Begründung", "missing")]
    live(isolated, monkeypatch, b, c, coverage_search(coverage, 2, query, "Begründung"))
    real = isolated["e5"].embed_query

    def ranking(text):  # the case's ranking runs before any cell; D's query only here
        if text == query:
            raise KeyboardInterrupt
        return real(text)

    monkeypatch.setattr(isolated["e5"], "embed_query", ranking)
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))

    local = outputs(isolated, tag="2026-11-26")[1]
    first = json.loads((local / "result.json").read_text("utf-8"))
    record = first["cases"][0]["cells"][2]["record"]
    assert (record["outcome"], record["generation_calls"], record["searches"]) == (
        "aborted",
        1,
        [],
    )
    # D's coverage decision of its proven call 1, as the cell recorded it (codes and counts)
    assert record["coverage"] == [
        {
            "call": 1,
            "action": "search",
            "check": "ok",
            "parts": 2,
            "covered": 1,
            "missing": 1,
            "search_for": 2,
            "missing_not_reported": None,
        }
    ]
    (case_,) = phase4_scoring.score([first], gold("E1"))["cases"]
    d_cell = case_["cells"][2]
    assert (d_cell["ran"], d_cell["outcome"], d_cell["calls"], d_cell["searches"]) == (
        True,
        "aborted",
        1,
        0,
    )
    # Every fact part was covered: a no-search-needed point whose search never ran, so no
    # action, no search executed or refused, no passage returned and no T3 or A1 increment.
    assert [(p["call"], p["kind"], p["action"], p["measure"]) for p in d_cell["decision_points"]] == [
        (1, "no_search_needed", "no_action", None)
    ]
    counts = d_cell["counts"]
    assert (counts["searches"], counts["refused_searches"]["total"], counts["unnecessary"]) == (
        0,
        0,
        0,
    )
    assert counts["unnecessary_attempts"] == {"executed": 0, "refused": 0, "total": 0}
    assert counts["unnecessary_rate"] == counts["unnecessary_attempt_rate"] == {"k": 0, "n": 0}
    assert counts["decision_points"]["no_search_needed"] == {"with_action": 0, "without_action": 1}
    diagnostics = counts["coverage_diagnostics"]
    assert diagnostics["checks"]["search"] == {
        "ok": 1,
        "malformed": 0,
        "passage_reference": 0,
        "search_for": 0,
    }
    assert diagnostics["decision_points_with_ok_check"]["no_search_needed"] == {
        "marked_missing": 1,
        "marked_all_covered": 0,
    }
    assert case_["complete"] is True
    capsys.readouterr()
    again = live(isolated, monkeypatch)
    exit_code(phase4_argv(isolated, cases, tag="2026-11-27"))
    assert again.creates == []  # D's call 1 is in the books: never sent again


# An interruption while a response file is written: only the complete response proves a send

CUTS = {
    "empty": lambda text: "",
    "truncated": lambda text: text[: len(text) // 2],
    "other JSON": lambda text: json.dumps({"id": "msg_other", "content": []}),
}


@pytest.mark.parametrize(
    ("call", "keep", "books"),
    [
        (1, "empty", "readable"),
        (1, "truncated", "readable"),
        (1, "other JSON", "readable"),
        (2, "truncated", "readable"),  # call 1 proven, call 2 cut short
        (1, "truncated", "damaged"),  # the books cannot be read when the run recovers
        (1, "truncated", "missing"),  # the ledger is gone when the run recovers
    ],
)
def test_a_response_file_an_interruption_cut_short_proves_no_send(  # noqa: PLR0913
    isolated, monkeypatch, capsys, call, keep, books
):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, c, d = phase4_answers()
    replies = (b, search_call("Pauschale", "Begründung"), c) if call == 2 else (b, c)
    live(isolated, monkeypatch, *replies)
    attempt = f"E1-agent-r1-call{call}"
    real = Path.open

    class Cut:  # C's response file as the interruption leaves it, before any settlement
        def __init__(self, handle) -> None:
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> None:
            self.handle.close()

        def write(self, text: str) -> None:
            self.handle.write(CUTS[keep](text))
            self.handle.flush()
            if books == "damaged":  # meanwhile the books were damaged: they cannot be read
                with phase4_path(isolated).open("a", encoding="utf-8") as books_:
                    books_.write('{"event": "settle"')
            if books == "missing":  # meanwhile the ledger was moved away
                os.replace(phase4_path(isolated), isolated["tmp"] / "kept-ledger.jsonl")
            raise KeyboardInterrupt

    def opening(self, mode="r", *args, **kwargs):
        handle = real(self, mode, *args, **kwargs)
        if self.name == f"{attempt}.json" and self.parent.name == "responses" and "x" in mode:
            return Cut(handle)
        return handle

    monkeypatch.setattr(Path, "open", opening)
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))
    monkeypatch.setattr(Path, "open", real)

    local = outputs(isolated, tag="2026-11-26")[1]
    kept_cell = json.loads((local / "result.json").read_text("utf-8"))["cases"][0]["cells"][1]
    record = kept_cell["record"]
    assert kept_cell["status"]["accounting"] == ("uncertain" if books == "readable" else "unknown")
    # The saved file is not the response the cell recorded: no send proven by it. Its call
    # stays this run's booking, apart and unconfirmed; an earlier proven call stays proven.
    assert (record["generation_calls"], [x["attempt"] for x in record["calls"]]) == (
        call - 1,
        [f"E1-agent-r1-call{n}" for n in range(1, call)],
    )
    assert [(x["attempt"], x["settlement"]) for x in record["unconfirmed_calls"]] == [
        (attempt, None)
    ]
    capsys.readouterr()
    again = live(isolated, monkeypatch, d)
    if books == "missing":  # the same ledger restored before the restart
        os.replace(isolated["tmp"] / "kept-ledger.jsonl", phase4_path(isolated))
    if books == "damaged":  # refused until Erhan repairs the books: the damaged line is removed
        assert exit_code(phase4_argv(isolated, cases, tag="2026-11-27")) == 3
        path = phase4_path(isolated)
        text = path.read_text("utf-8")
        path.write_text(text[: text.rindex("\n") + 1], "utf-8")

    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-28")) == 0

    assert len(again.creates) == 1  # D only: C's call is never sent again
    events = [e["event"] for e in phase4_ledger(isolated) if e.get("attempt") == attempt]
    assert events == ["reserve"]  # its reservation stays open: committed, never released
    results = [
        json.loads((outputs(isolated, tag=tag)[1] / "result.json").read_text("utf-8"))
        for tag in ("2026-11-26", "2026-11-28")
    ]
    (case_,) = phase4_scoring.score(results, gold("E1"))["cases"]
    c_cell = case_["cells"][1]
    assert (c_cell["ran"], c_cell["calls"], case_["complete"]) == (
        (True, 1, True) if call == 2 else (False, None, False)
    )


# A deadline after the cell's last booking was released unsent, then an interrupted lock release


class SlowCount(Provider):
    """The provider's HTTP side whose count number ``slow`` takes longer than a cell's budget."""

    def __init__(self, clock, *replies, slow: int) -> None:
        super().__init__(clock, *replies)
        self.slow = slow

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Answer one request; the count numbered ``slow`` lets 601 seconds pass."""
        if request.url.path == "/v1/messages/count_tokens" and len(self.counts) == self.slow - 1:
            self.clock.advance(601)
        return super().__call__(request)


def deadline_then_interrupted_release(env, monkeypatch, *, after=None) -> Path:
    """Run E1 until C's cell ends: call 1 sent, a search, call 2 reserved past the deadline and
    released unsent (deadline, before_send); then the lock is interrupted while given back.
    ``after`` runs between the cell's end and the interruption. Returns the cases file."""
    cases = frozen_input(env, monkeypatch, case("E1"))
    b = phase4_answers()[0]
    provider = SlowCount(env["clock"], b, search_call("Pauschale", "Begründung"), slow=3)
    monkeypatch.setattr(run_comparison, "_client", lambda config: provider.client())
    real, uses = generation._ledger_lock, []

    @contextlib.contextmanager
    def releasing(ledger):  # B's cell, then C's: C's lock is interrupted while given back
        uses.append(ledger)
        with real(ledger) as held:
            yield held
        if len(uses) == 2:
            if after:
                after()
            raise KeyboardInterrupt

    monkeypatch.setattr(generation, "_ledger_lock", releasing)
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(env, cases))
    monkeypatch.setattr(generation, "_ledger_lock", real)
    return cases


def test_a_deadline_after_the_last_booking_was_released_unsent_stays_the_cells_ending(
    isolated, monkeypatch, capsys
):
    cases = deadline_then_interrupted_release(isolated, monkeypatch)

    released = [e for e in phase4_ledger(isolated) if e.get("attempt") == "E1-agent-r1-call2"]
    assert [(e["event"], e.get("sent"), e.get("cost_basis")) for e in released] == [
        ("reserve", None, None),
        ("settle", False, "not_sent"),
    ]
    public, local = outputs(isolated, tag="2026-11-26")
    first = json.loads((local / "result.json").read_text("utf-8"))
    record = first["cases"][0]["cells"][1]["record"]
    assert (record["outcome"], record.get("ended"), record["generation_calls"]) == (
        "aborted",
        "deadline",
        1,
    )
    (call,) = record["calls"]  # call 1 keeps its proven send; call 2 adds none
    assert (call["attempt"], call["sent"], call["cost_basis"]) == ("E1-agent-r1-call1", True, "usage")
    assert [(x["attempt"], x["settlement"]) for x in record["unconfirmed_calls"]] == [
        ("E1-agent-r1-call2", "not_sent")
    ]
    shown = json.loads(public.read_text("utf-8"))["cases"][0]["cells"][1]["agent"]
    assert (shown["outcome"], "ended" in shown) == ("aborted", False)  # local only
    capsys.readouterr()
    again = live(isolated, monkeypatch, phase4_answers()[2])
    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-27")) == 0
    assert len(again.creates) == 1  # D only: neither of C's calls is sent later
    second = json.loads((outputs(isolated, tag="2026-11-27")[1] / "result.json").read_text("utf-8"))
    (case_,) = phase4_scoring.score([first, second], gold("E1"))["cases"]
    c_cell = case_["cells"][1]
    assert (c_cell["ran"], c_cell["outcome"], c_cell["calls"]) == (True, "aborted", 1)
    assert [(p["call"], p["action"]) for p in c_cell["decision_points"]] == [(1, "search_run")]
    assert case_["complete"] is True


@pytest.mark.parametrize("evidence", ["release not saved", "books unreadable"])
def test_no_ending_or_release_is_inferred_for_a_last_booking_open_or_unknown(
    isolated, monkeypatch, capsys, evidence
):
    real_append = generation._append

    def unsaved(ledger, event):  # the release of C's call 2 never reaches the books
        if event["event"] == "settle" and event.get("sent") is False:
            raise OSError(errno.EIO, "simulated I/O failure")
        return real_append(ledger, event)

    def damaged():  # the release is saved; the books are damaged before the run recovers
        with phase4_path(isolated).open("a", encoding="utf-8") as books_:
            books_.write('{"event": "settle"')

    if evidence == "release not saved":
        monkeypatch.setattr(generation, "_append", unsaved)
    cases = deadline_then_interrupted_release(
        isolated, monkeypatch, after=damaged if evidence == "books unreadable" else None
    )
    monkeypatch.setattr(generation, "_append", real_append)

    kept_cell = json.loads(
        (outputs(isolated, tag="2026-11-26")[1] / "result.json").read_text("utf-8")
    )["cases"][0]["cells"][1]
    record = kept_cell["record"]
    assert kept_cell["status"]["accounting"] == (
        "uncertain" if evidence == "release not saved" else "unknown"
    )
    assert (record["outcome"], "ended" in record, record["generation_calls"]) == (
        "aborted",
        False,
        1,
    )
    assert [(x["attempt"], x["settlement"]) for x in record["unconfirmed_calls"]] == [
        ("E1-agent-r1-call2", None)
    ]
    capsys.readouterr()
    again = live(isolated, monkeypatch, phase4_answers()[2])
    if evidence == "books unreadable":  # refused until the damaged line is removed
        assert exit_code(phase4_argv(isolated, cases, tag="2026-11-27")) == 3
        path = phase4_path(isolated)
        text = path.read_text("utf-8")
        path.write_text(text[: text.rindex("\n") + 1], "utf-8")
    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-28")) == 0
    assert len(again.creates) == 1  # D only: C's call 2 is never sent
    events = [e["event"] for e in phase4_ledger(isolated) if e.get("attempt") == "E1-agent-r1-call2"]
    assert events == (["reserve"] if evidence == "release not saved" else ["reserve", "settle"])


# Round 7: a zero-byte response file, a response that disagrees with its settlement, and books
# that cannot be read for a reason other than a value error


def interrupt_release(monkeypatch, *, use: int = 2, after=None) -> None:
    """Interrupt the lock's release after its ``use``-th cell (B's is the first), running
    ``after`` first."""
    real, uses = generation._ledger_lock, []

    @contextlib.contextmanager
    def releasing(ledger):
        uses.append(ledger)
        with real(ledger) as held:
            yield held
        if len(uses) == use:
            if after:
                after()
            raise KeyboardInterrupt

    monkeypatch.setattr(generation, "_ledger_lock", releasing)


@pytest.mark.parametrize("settled", [False, True])
def test_a_zero_byte_response_file_proves_no_send_even_for_an_empty_body(
    isolated, monkeypatch, capsys, settled
):
    # The provider answers C's call with an empty body, so its complete response is zero bytes:
    # interrupted while that file is written (before any settlement), or after the cell ended
    # with the call settled (while the lock is given back), the file proves no send.
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, _, d = phase4_answers()
    live(isolated, monkeypatch, b, httpx.Response(200, content=b""))
    real = Path.open

    class Cut:  # the empty response's file, the interruption arriving as it is written
        def __init__(self, handle) -> None:
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> None:
            self.handle.close()

        def write(self, text: str) -> None:
            self.handle.write(text)
            raise KeyboardInterrupt

    def opening(self, mode="r", *args, **kwargs):
        handle = real(self, mode, *args, **kwargs)
        if self.name == "E1-agent-r1-call1.json" and self.parent.name == "responses" and "x" in mode:
            return Cut(handle)
        return handle

    real_lock = generation._ledger_lock
    if settled:
        interrupt_release(monkeypatch)
    else:
        monkeypatch.setattr(Path, "open", opening)
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))
    monkeypatch.setattr(Path, "open", real)
    monkeypatch.setattr(generation, "_ledger_lock", real_lock)

    local = outputs(isolated, tag="2026-11-26")[1]
    first = json.loads((local / "result.json").read_text("utf-8"))
    kept_cell = first["cases"][0]["cells"][1]
    assert (local / "responses" / "E1-agent-r1-call1.json").read_bytes() == b""
    assert kept_cell["status"]["accounting"] == "uncertain"
    assert (kept_cell["record"]["generation_calls"], kept_cell["record"]["calls"]) == (0, [])
    assert [(x["attempt"], x["settlement"]) for x in kept_cell["record"]["unconfirmed_calls"]] == [
        ("E1-agent-r1-call1", "reservation_retained" if settled else None)
    ]
    capsys.readouterr()
    again = live(isolated, monkeypatch, d)
    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-27")) == 0
    assert len(again.creates) == 1  # D only: C's call is never sent again
    events = [e["event"] for e in phase4_ledger(isolated) if e.get("attempt") == "E1-agent-r1-call1"]
    assert events == (["reserve", "settle"] if settled else ["reserve"])
    second = json.loads((outputs(isolated, tag="2026-11-27")[1] / "result.json").read_text("utf-8"))
    (case_,) = phase4_scoring.score([first, second], gold("E1"))["cases"]
    assert (case_["cells"][1]["ran"], case_["complete"]) == (False, False)


def test_a_response_file_that_disagrees_with_its_settlement_leaves_the_accounting_uncertain(
    isolated, monkeypatch, capsys
):
    # C's call is sent, its response saved and settled from its usage; when the run recovers
    # (the lock's release interrupted), the file no longer holds that response.
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, c, d = phase4_answers()
    live(isolated, monkeypatch, b, c)
    local = outputs(isolated, tag="2026-11-26")[1]

    def altered():
        (local / "responses" / "E1-agent-r1-call1.json").write_text("{}", "utf-8")

    real_lock = generation._ledger_lock
    interrupt_release(monkeypatch, after=altered)
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))
    monkeypatch.setattr(generation, "_ledger_lock", real_lock)

    kept_cell = json.loads((local / "result.json").read_text("utf-8"))["cases"][0]["cells"][1]
    record = kept_cell["record"]
    assert (record["generation_calls"], record["calls"]) == (0, [])  # the file proves nothing
    assert [(x["attempt"], x["settlement"]) for x in record["unconfirmed_calls"]] == [
        ("E1-agent-r1-call1", "usage")
    ]
    # the books charge a send this run cannot show: the conflict stays visible, never "priced"
    assert kept_cell["status"]["accounting"] == "uncertain"
    capsys.readouterr()
    again = live(isolated, monkeypatch, d)
    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-27")) == 0
    assert len(again.creates) == 1  # D only: C's call is never sent again


@pytest.mark.parametrize("damage", ["an amount past float range", "nesting too deep to parse"])
def test_books_that_cannot_be_read_for_any_reason_keep_the_send_the_run_proves(
    isolated, monkeypatch, capsys, damage
):
    # C answered and its call was settled; while its lock is given back the books are damaged
    # by a line their strict reading cannot take (no value error: an overflow, a recursion).
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, c, d = phase4_answers()
    live(isolated, monkeypatch, b, c)
    reservation = {
        "event": "reserve",
        "attempt": "E1-coverage-r1-call1",
        "case": "E1",
        "condition": "coverage",
        "repetition": 1,
        "question_sha256": hashlib.sha256(QUESTION.encode("utf-8")).hexdigest(),
        "editions": [JUL],
        "call": 1,
        "request_sha256": "0" * 64,
        "counted_input_tokens": 1500,
        "reserved_usd": 10**310,
        "at": "2026-11-26T00:00:00+00:00",
    }
    line = (
        json.dumps(reservation)
        if damage == "an amount past float range"
        else "[" * 100_000 + "]" * 100_000
    )

    def damaged():
        with phase4_path(isolated).open("a", encoding="utf-8") as books_:
            books_.write(line + "\n")

    real_lock = generation._ledger_lock
    interrupt_release(monkeypatch, after=damaged)
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))
    monkeypatch.setattr(generation, "_ledger_lock", real_lock)

    local = outputs(isolated, tag="2026-11-26")[1]
    first = json.loads((local / "result.json").read_text("utf-8"))
    cells = first["cases"][0]["cells"]
    assert [cell["condition"] for cell in cells] == ["fixed10", "agent"]  # C's cell is kept
    assert cells[1]["status"]["accounting"] == "unknown"  # the books take no part
    record = cells[1]["record"]
    assert (record["generation_calls"], record.get("ended")) == (1, "answer")
    path = phase4_path(isolated)  # Erhan repairs the books: the damaged line is removed
    text = path.read_text("utf-8")
    path.write_text(text[: text.rindex("\n", 0, len(text) - 1) + 1], "utf-8")
    capsys.readouterr()
    again = live(isolated, monkeypatch, d)
    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-27")) == 0
    assert len(again.creates) == 1  # D only: C is never sent again
    second = json.loads((outputs(isolated, tag="2026-11-27")[1] / "result.json").read_text("utf-8"))
    (case_,) = phase4_scoring.score([first, second], gold("E1"))["cases"]
    assert (case_["cells"][1]["ran"], case_["complete"]) == (True, True)


# The Phase 4 ledger missing when the run recovers: absent books confirm and contradict nothing


def test_a_send_the_run_proves_survives_a_phase4_ledger_missing_at_recovery(
    isolated, monkeypatch, capsys
):
    # C's call is booked, sent, saved and settled; while its lock is given back the Phase 4
    # ledger, there since B's booking, is moved away, so the run recovers without its books.
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, c, d = phase4_answers()
    live(isolated, monkeypatch, b, c)
    books, kept = phase4_path(isolated), isolated["tmp"] / "kept-ledger.jsonl"
    before = {}

    def vanished():
        before["bytes"] = books.read_bytes()
        os.replace(books, kept)

    real_lock = generation._ledger_lock
    interrupt_release(monkeypatch, after=vanished)
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))
    monkeypatch.setattr(generation, "_ledger_lock", real_lock)

    assert not books.exists()  # recovery wrote no books: nothing rebuilt from the run's files
    local = outputs(isolated, tag="2026-11-26")[1]
    first = json.loads((local / "result.json").read_text("utf-8"))
    kept_cell = first["cases"][0]["cells"][1]
    assert kept_cell["status"]["accounting"] == "unknown"  # the books take no part
    record = kept_cell["record"]
    response = (local / "responses" / "E1-agent-r1-call1.json").read_bytes()
    (call,) = record["calls"]
    assert (record["generation_calls"], record["unconfirmed_calls"]) == (1, [])
    assert (call["sent"], call["response_sha256"]) == (True, hashlib.sha256(response).hexdigest())
    # its cost is not known without the books: none is taken from the response's usage
    assert (call["cost_usd"], call["cost_basis"], call["usage"]) == (None, None, None)
    os.replace(kept, books)  # the same ledger restored, byte for byte
    assert books.read_bytes() == before["bytes"]
    capsys.readouterr()
    again = live(isolated, monkeypatch, d)

    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-27")) == 0

    assert len(again.creates) == 1  # D only: C is neither sent nor booked again
    events = [e["event"] for e in phase4_ledger(isolated) if e.get("attempt") == "E1-agent-r1-call1"]
    assert events == ["reserve", "settle"]
    assert books.read_bytes().startswith(before["bytes"])  # only D's lines were added
    second = json.loads((outputs(isolated, tag="2026-11-27")[1] / "result.json").read_text("utf-8"))
    (case_,) = phase4_scoring.score([first, second], gold("E1"))["cases"]
    c_cell = case_["cells"][1]
    assert (c_cell["ran"], c_cell["outcome"], case_["complete"]) == (True, "aborted", True)


@pytest.mark.parametrize("ledger", ["never created", "moved away, no record"])
def test_a_missing_phase4_ledger_alone_proves_nothing(isolated, monkeypatch, capsys, ledger):
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, c, d = phase4_answers()
    books, kept = phase4_path(isolated), isolated["tmp"] / "kept-ledger.jsonl"
    local = outputs(isolated, tag="2026-11-26")[1]
    if ledger == "never created":  # first use: B's request saved, then stopped before booking

        def stopped(*args):
            raise KeyboardInterrupt

        live(isolated, monkeypatch, b, c, d)
        real_books = evidence_agent._create_books
        monkeypatch.setattr(evidence_agent, "_create_books", stopped)
        with pytest.raises(KeyboardInterrupt):
            run_comparison.main(phase4_argv(isolated, cases))
        monkeypatch.setattr(evidence_agent, "_create_books", real_books)

        assert (local / "requests" / "E1-fixed10-r1-call1.json").exists()
        assert not books.exists() and not (local / "result.json").exists()  # nothing booked
        capsys.readouterr()
        again = live(isolated, monkeypatch, b, c, d)
        assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-27")) == 0
        assert len(again.creates) == 3  # a first use as any other: each cell booked and sent once
        reserved = [e["attempt"] for e in phase4_ledger(isolated) if e["event"] == "reserve"]
        assert reserved == ["E1-fixed10-r1-call1", "E1-agent-r1-call1", "E1-coverage-r1-call1"]
        return
    live(isolated, monkeypatch, b, c)
    real = evidence_agent.run_case

    def failing(the_task, **kwargs):  # C ran to its end; the ledger is moved away, then an
        result = real(the_task, **kwargs)  # error without the cell's record ends the run
        if kwargs["condition"] == "agent":
            os.replace(books, kept)
            raise RuntimeError("unexpected failure after the cell")
        return result

    monkeypatch.setattr(evidence_agent, "run_case", failing)
    with pytest.raises(RuntimeError, match="after the cell"):
        run_comparison.main(phase4_argv(isolated, cases))
    monkeypatch.setattr(evidence_agent, "run_case", real)

    assert not books.exists()
    first = json.loads((local / "result.json").read_text("utf-8"))
    kept_cell = first["cases"][0]["cells"][1]
    record = kept_cell["record"]
    # Its complete response file alone proves no send: no record and no books confirm it.
    assert kept_cell["status"]["accounting"] == "unknown"
    assert (record["generation_calls"], record["calls"], record["trace"]) == (0, [], "not_recorded")
    assert [(x["attempt"], x["settlement"]) for x in record["unconfirmed_calls"]] == [
        ("E1-agent-r1-call1", None)
    ]
    os.replace(kept, books)
    capsys.readouterr()
    again = live(isolated, monkeypatch, d)
    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-27")) == 0
    assert len(again.creates) == 1  # D only: C's booking is in the books, never sent again
    second = json.loads((outputs(isolated, tag="2026-11-27")[1] / "result.json").read_text("utf-8"))
    (case_,) = phase4_scoring.score([first, second], gold("E1"))["cases"]
    assert (case_["cells"][1]["ran"], case_["complete"]) == (False, False)


def test_a_digest_conflict_on_a_call_above_its_reservation_stays_uncertain_with_its_overage(
    isolated, monkeypatch, capsys
):
    # C's answer costs more than its reservation (settled from usage, above it); when the run
    # recovers (the lock's release interrupted), its response file no longer holds that answer.
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, _, d = phase4_answers()
    live(isolated, monkeypatch, b, {**final(("C.", [TOP5[0]])), "usage": _dearest(1651)})
    local = outputs(isolated, tag="2026-11-26")[1]

    def altered():
        (local / "responses" / "E1-agent-r1-call1.json").write_text("{}", "utf-8")

    real_lock = generation._ledger_lock
    interrupt_release(monkeypatch, after=altered)
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))
    monkeypatch.setattr(generation, "_ledger_lock", real_lock)

    kept_cell = json.loads((local / "result.json").read_text("utf-8"))["cases"][0]["cells"][1]
    record = kept_cell["record"]
    assert (record["generation_calls"], record["calls"]) == (0, [])
    # The uncertainty is the cell's accounting; the overage stays with its call.
    assert kept_cell["status"]["accounting"] == "uncertain"
    assert [
        (x["attempt"], x["settlement"], x["above_reservation"]) for x in record["unconfirmed_calls"]
    ] == [("E1-agent-r1-call1", "usage", True)]
    capsys.readouterr()
    again = live(isolated, monkeypatch, d)
    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-27")) == 0
    assert len(again.creates) == 1  # D only: C's call is never sent again


def test_an_uncertain_tool_turn_and_a_later_overage_leave_the_cell_uncertain_with_the_overage_on_its_call(
    isolated, monkeypatch, capsys
):
    # C's search turn has no usage to price it by (settled at its whole reservation, the loop
    # goes on); its answer then costs more than its own reservation; the lock's release is
    # interrupted. Uncertainty and overage on different calls: the accounting is uncertain and
    # the overage stays on its call.
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, _, d = phase4_answers()
    unpriced = {**search_call("Pauschale", "Begründung"), "usage": {"input_tokens": "unknown"}}
    dear = {**final(("C.", [TOP5[0]])), "usage": _dearest(1651)}
    live(isolated, monkeypatch, b, unpriced, dear)
    real_lock = generation._ledger_lock
    interrupt_release(monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))
    monkeypatch.setattr(generation, "_ledger_lock", real_lock)

    local = outputs(isolated, tag="2026-11-26")[1]
    kept_cell = json.loads((local / "result.json").read_text("utf-8"))["cases"][0]["cells"][1]
    record = kept_cell["record"]
    assert kept_cell["status"]["accounting"] == "uncertain"
    assert [(x["call"], x["cost_basis"], x["above_reservation"]) for x in record["calls"]] == [
        (1, "reservation_retained", False),
        (2, "usage", True),
    ]
    capsys.readouterr()
    again = live(isolated, monkeypatch, d)
    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-27")) == 0
    assert len(again.creates) == 1  # D only: neither of C's calls is sent again


def test_a_phase4_ledger_gone_only_while_recovery_reads_it_keeps_the_proven_send(
    isolated, monkeypatch, capsys
):
    # C's call is booked, sent, saved and settled; the ledger is away exactly while the recovery
    # reads it (the real reader finds no file) and back before anything else looks.
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, c, d = phase4_answers()
    live(isolated, monkeypatch, b, c)
    kept = isolated["tmp"] / "kept-ledger.jsonl"
    real_ledger = evidence_agent._ledger

    def gone_while_read(path, *args, **kwargs):
        os.replace(path, kept)
        try:
            return real_ledger(path, *args, **kwargs)
        finally:
            os.replace(kept, path)

    real_lock = generation._ledger_lock
    interrupt_release(
        monkeypatch,
        after=lambda: monkeypatch.setattr(evidence_agent, "_ledger", gone_while_read),
    )
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))
    monkeypatch.setattr(generation, "_ledger_lock", real_lock)
    monkeypatch.setattr(evidence_agent, "_ledger", real_ledger)

    first = json.loads((outputs(isolated, tag="2026-11-26")[1] / "result.json").read_text("utf-8"))
    kept_cell = first["cases"][0]["cells"][1]
    assert kept_cell["status"]["accounting"] == "unknown"  # the books it read were not there
    assert kept_cell["record"]["generation_calls"] == 1  # the send the run proves is kept
    capsys.readouterr()
    again = live(isolated, monkeypatch, d)
    assert run_comparison.main(phase4_argv(isolated, cases, tag="2026-11-27")) == 0
    assert len(again.creates) == 1  # D only: C is neither sent nor booked again
    second = json.loads((outputs(isolated, tag="2026-11-27")[1] / "result.json").read_text("utf-8"))
    (case_,) = phase4_scoring.score([first, second], gold("E1"))["cases"]
    assert (case_["cells"][1]["ran"], case_["complete"]) == (True, True)


def test_readable_books_without_the_cells_booking_decide_even_when_gone_after_the_read(
    isolated, monkeypatch, capsys
):
    # The recovery reads an earlier copy of the ledger that holds no booking of C's cell (the
    # books contradict the run's files), and the ledger is gone right after that read: the
    # readable books decide, as for any reservation the run cannot show as its own.
    cases = frozen_input(isolated, monkeypatch, case("E1"))
    b, c, _ = phase4_answers()
    live(isolated, monkeypatch, b, c)
    kept = isolated["tmp"] / "kept-ledger.jsonl"
    real_ledger = evidence_agent._ledger

    def earlier_then_gone(path, *args, **kwargs):
        lines = path.read_bytes().splitlines(keepends=True)
        path.write_bytes(b"".join(x for x in lines if b"E1-agent-r1-call" not in x))
        try:
            return real_ledger(path, *args, **kwargs)
        finally:
            os.replace(path, kept)

    real_lock = generation._ledger_lock
    interrupt_release(
        monkeypatch,
        after=lambda: monkeypatch.setattr(evidence_agent, "_ledger", earlier_then_gone),
    )
    with pytest.raises(KeyboardInterrupt):
        run_comparison.main(phase4_argv(isolated, cases))
    monkeypatch.setattr(generation, "_ledger_lock", real_lock)
    monkeypatch.setattr(evidence_agent, "_ledger", real_ledger)

    kept_cell = json.loads(
        (outputs(isolated, tag="2026-11-26")[1] / "result.json").read_text("utf-8")
    )["cases"][0]["cells"][1]
    record = kept_cell["record"]
    assert kept_cell["status"]["accounting"] == "nothing_reserved"
    assert (record["generation_calls"], record["calls"], record["unconfirmed_calls"]) == (0, [], [])
