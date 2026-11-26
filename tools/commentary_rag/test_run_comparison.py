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

import json
import re
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import evidence_agent
import generation
import run_comparison
import run_question
from test_corpus import make_repo
from test_evidence_agent import Clock, Provider, _dearest, books, final, search_call
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
    blocker = isolated["tmp"] / "blocker"
    blocker.write_text("a file where the local folder's parent should be\n", "utf-8")
    monkeypatch.setattr(run_comparison, "LOCAL", blocker / "local")
    provider = live(isolated, monkeypatch, *answers())

    code = run_comparison.main(argv(isolated, "run", cases_file(isolated, case("E1"))))

    # A's request could not be saved, so it was neither reserved nor sent, and nothing followed.
    assert code == 7
    assert (len(provider.counts), provider.creates) == (1, [])


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


def test_the_phase4_plan_lays_out_b_c_and_d_and_shows_that_19_cases_do_not_fit(
    isolated, capsys
):
    nineteen = [case(f"P{n:02d}") for n in range(1, 20)]
    before = written(isolated)

    code = run_comparison.main(
        ["plan", "--design", "phase4", "--cases", str(cases_file(isolated, *nineteen))]
    )

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
    # One case is admitted at 1 + 3 + 3 calls at the input cap, 10.3488 USD; the 19 cases
    # need 196.6272 at once, more than the headroom (100 minus the history's 0.25).
    admission = plan["admission"]
    assert (admission["worst_case_usd"], admission["headroom_usd"], admission["fits"]) == (
        196.6272,
        99.75,
        False,
    )
    estimates = plan["estimates"]
    assert list(estimates["per_condition"]) == ["fixed10", "agent", "coverage"]
    assert estimates["per_condition"]["coverage"]["usd_per_cell"] is None
    assert estimates["matrix_usd"] is None
    assert isolated["loads"] == []
    assert written(isolated) == before


def test_the_phase4_run_refuses_19_cases_before_the_model_loads(
    isolated, monkeypatch, capsys
):
    live(isolated, monkeypatch)  # no reply: nothing may be sent
    nineteen = [case(f"P{n:02d}") for n in range(1, 20)]
    argv_ = argv(isolated, "run", cases_file(isolated, *nineteen)) + ["--design", "phase4"]

    assert exit_code(argv_) == 3
    assert "196.6272" in capsys.readouterr().err
    assert isolated["loads"] == []
    assert not active(isolated).exists()


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
    argv_ = argv(isolated, "run", cases_file(isolated, case("E1"))) + ["--design", "phase4"]

    code = run_comparison.main(argv_)

    assert code == 0
    b, c1, _, d = provider.creates
    assert (sent(b), sent(c1), sent(d)) == (TOP10, TOP5, TOP5)
    assert d["messages"][0] == c1["messages"][0]  # D starts where C does
    assert d["system"] == (
        f"{generation.SYSTEM_PROMPT}\n\n{evidence_agent.COVERAGE_INSTRUCTION}"
    )
    assert d["output_config"]["format"]["schema"] == evidence_agent.COVERAGE_ANSWER_SCHEMA
    assert [(e["event"], e.get("attempt")) for e in ledger(isolated)] == [
        ("baseline", None),
        ("reserve", "E1-fixed10-call1"),
        ("settle", "E1-fixed10-call1"),
        ("reserve", "E1-agent-call1"),
        ("settle", "E1-agent-call1"),
        ("reserve", "E1-agent-call2"),
        ("settle", "E1-agent-call2"),
        ("reserve", "E1-coverage-call1"),
        ("settle", "E1-coverage-call1"),
    ]
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
    assert [c["agent"]["supplied"] for c in cells] == [10, 10, 5]
    assert [c["answer"]["cited_passages"] for c in cells] == [1, 2, 1]
    assert cells[1]["agent"]["searches"][0]["returned"] == 5
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


def test_estimates_read_cells_of_every_condition_under_either_design(isolated, capsys):
    rows = [agent_cell("E2")[0]]
    for name, calls in (("fixed5", 1), ("fixed10", 1), ("agent", 2), ("coverage", 1)):
        for n in range(1, calls + 1):
            rows += [_reserve("E3", name, n), _settle("E3", name, n)]
    active(isolated).write_text("".join(json.dumps(e) + "\n" for e in rows), "utf-8")
    cases = str(cases_file(isolated, case("E5")))
    seen = {}

    for design in ("phase3", "phase4"):
        assert run_comparison.main(["plan", "--design", design, "--cases", cases]) == 0
        per = json.loads(capsys.readouterr().out)["estimates"]["per_condition"]
        seen[design] = {n: (c["observed_cells"], c["usd_per_cell"]) for n, c in per.items()}

    # fixed5: the history (0.25) and E3 (0.024), mean 0.137; the other conditions E3 alone.
    assert seen == {
        "phase3": {"fixed5": (2, 0.137), "fixed10": (1, 0.024), "agent": (1, 0.048)},
        "phase4": {"fixed10": (1, 0.024), "agent": (1, 0.048), "coverage": (1, 0.024)},
    }
