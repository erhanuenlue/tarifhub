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
from test_evidence_agent import Clock, Provider, books, final, search_call
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

    # E1's agent cell is in the books already; A and B run, C is never sent again.
    assert code == 3
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
