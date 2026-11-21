"""Run the evidence-seeking agent (ADR-026) on one question: offline preparation or one live run.

Two steps, each run from the repository root (commands in the README). Both take exactly one
question, a stable case ID, an explicit edition selection and a finite time budget, check them
before anything is loaded, refuse outputs that already exist, build the hash-verified
commentary corpus with the cached multilingual-e5 model (offline mode forced: a missing model,
package or the 16-dimensional stub is refused, nothing is downloaded), refuse a question longer
than the model's input instead of truncating it, and rank the question afresh: hybrid, the
selected editions only, top 5, the Phase 2 pilot's initial context (ADR-025). The run's input
is the question, its case ID and its editions only: no dev case, gold evidence, rubric or
expected answer is read.

``prepare`` stops there and prints the initial passages by ID and score. It builds no client,
needs no key, sends nothing and writes nothing (no output, no ledger).

``run`` (the live step, never run implicitly) builds the pilot's client (``generation.client``:
fixed base URL, SDK retries off; ``ANTHROPIC_API_KEY`` from the environment, checked before the
model loads) and calls ``evidence_agent.run_case`` exactly once with the same corpus and
retriever for the agent's own searches, ``time.monotonic`` as its clock and the books, limit,
prices and settings fixed in ``evidence_agent`` and ``generation`` (none can be passed here).
That one call may send up to three generation requests, each counted, reserved and settled in
``results/phase3-ledger.jsonl``. The case ID is the case's identity in the books: a case already
there is refused whatever the tag, and nothing is retried or renamed.

Outputs, only when the agent reserved at least one call or may have (a reservation whose ledger
write failed); otherwise nothing of the case is in the books and nothing is written, so a
refused retry publishes nothing:

- ``local/<tag>-question-<case>/`` (git-ignored): the agent's ``requests/`` and ``responses/``
  artifacts, ``answer.json`` (an accepted answer) and ``result.json`` (the question, the answer,
  ``CaseResult.record`` and ``CaseResult.local``);
- ``results/<tag>-question-<case>.json``: provenance (question by SHA-256, settings, corpus and
  tool hashes, books), the initial ranking by ID, named keys of ``CaseResult.record``, answer
  metadata (status, counts, cited IDs, hash; no claim text) and the separate execution, answer
  and accounting statuses.

Each output is written on its own; a failed write leaves the others and the request and response
artifacts in place and never sends anything again. The exit codes are listed in ``EPILOG``.
The deadline is cooperative (ADR-026) and starts when the agent starts, after the corpus and the
model are loaded. The provider contract (request shape, reported usage) is unverified.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import corpus
    import evidence_agent
    import evidence_search
    import generation
    import retrieval
except ModuleNotFoundError as missing:  # the anthropic client or the ingestion package
    print(f"refused: {missing.name} is not installed; run with uv run --project "
          "services/ingestion --extra ai (see the README)", file=sys.stderr)
    raise SystemExit(3) from None  # EXIT_REFUSED

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULTS = HERE / "results"
LOCAL = HERE / "local"
CLOCK = time.monotonic  # the agent's deadline clock
# The initial context of the Phase 2 pilot (ADR-025): hybrid ranking over the selected editions,
# top 5, passages built to a 256-token budget.
METHOD, MODE, TOP_K, TOKEN_BUDGET = evidence_search.METHOD, "edition_filter", 5, 256
TOOL_FILES = ("run_question.py", "evidence_agent.py", "evidence_search.py", "generation.py",
              "retrieval.py", "corpus.py", "run_eval.py", "pricing.json")

EXIT_ANSWER, EXIT_INPUT, EXIT_REFUSED, EXIT_NOT_ANSWERED = 0, 2, 3, 4
EXIT_SPENDING_STOP, EXIT_ACCOUNTING_UNCERTAIN, EXIT_PERSISTENCE = 5, 6, 7
EPILOG = """\
exit codes (when several apply, the higher row wins):
  7  persistence: the agent or the runner could not write the ledger or an output
  5  spending stop: a call cost more than its reservation (an answer is still kept locally)
  6  accounting uncertain: a sent call could not be priced (its reservation stays committed)
     or its settlement is not confirmed in the ledger
  3  refused: by the runner before any provider work, or by the agent's books
  4  not answered: invalid answer, cut-off generation, protocol or provider error, deadline
  0  a structurally accepted answer or abstention (answered, partial or
     insufficient_evidence), persisted, every call priced within its reservation
  2  invalid input, nothing counted or sent: arguments are checked before anything loads,
     an edition the corpus lacks or a question over the model's input once both are loaded
  1  an unexpected error (traceback)
an exit 0 says the answer matches the schema and cites only passages it was given; it does
not establish answer quality. The time budget is cooperative (a request already sent is not
interrupted) and starts when the agent starts, after the corpus and the model are loaded."""

# The keys of ``CaseResult.record`` a public record carries: codes, counts, IDs, hashes, usage
# and amounts (see evidence_agent); question, answer, passage, search and error text stay local.
PUBLIC_RECORD = ("case", "condition", "budget_s", "generation_calls", "calls", "searches",
                 "spending",
                 "outcome", "detail", "elapsed_s", "supplied", "schema_problems",
                 "citations_outside_supplied", "cited")
NOTES = ("An answer is accepted when it matches the answer schema and cites only passages "
         "supplied to the model; that is a deterministic check, not evidence that its claims "
         "are correct or supported, which needs human review against the cited passages.",
         "Costs are calculated from reported usage and pricing.json, or kept at the "
         "reservation where nothing could be priced; they are not an invoice.")


class _Stop(Exception):
    """The runner stops before any provider work: nothing sent, nothing written."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _E5:
    """The e5 boundary: the embedder, its exact token count per kind, its input limit."""

    embedder: object  # embed (passage) and embed_query (query), the repository's own port
    counters: dict  # kind ("passage" or "query") -> count of the exact string embedded
    limit: int  # the model's max_seq_length: anything longer would be cut silently
    provenance: dict

    def count(self, text: str, kind: str) -> int:
        """The tokens of ``text`` as the model embeds it for ``kind``."""

        try:
            return self.counters[kind](text)
        except SystemExit as exc:  # run_eval's refusal when two tokenizations disagree
            raise _Stop(EXIT_REFUSED, str(exc.code)) from None


@dataclass(frozen=True)
class _Prepared:
    """The question ranked afresh over the verified corpus, with what ranked it."""

    retriever: retrieval.Retriever
    passages: dict[str, dict]  # every corpus passage as a request takes it
    ranking: list[retrieval.Hit]  # the initial top 5
    built: corpus.Corpus
    query_tokens: int  # the question's e5 tokens, within the model's limit
    embedder: dict  # which model ranked it


def _e5() -> _E5:
    """The repository's multilingual-e5 embedder from the local Hugging Face cache only.

    Offline mode is forced before anything imports ``huggingface_hub`` and checked to hold, so
    a missing model is refused, never downloaded; so is the 16-dimensional stub that
    ``get_embedder`` falls back to.
    """

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        from huggingface_hub import constants, try_to_load_from_cache  # noqa: PLC0415
        import run_eval  # noqa: PLC0415 - its e5 loader and exact token counter
    except ImportError as exc:
        raise _Stop(EXIT_REFUSED, f"refused: {exc.name} is not installed; run with the "
                    "ingestion ai extra") from None
    if not constants.HF_HUB_OFFLINE:  # imported earlier, before offline mode was set
        raise _Stop(EXIT_REFUSED, "refused: Hugging Face offline mode is not in effect; set "
                    "HF_HUB_OFFLINE=1 so that no model can be downloaded")
    try:
        embedder, model = run_eval._e5()  # refuses the stub fallback
        counters = {kind: run_eval._counter(model, kind) for kind in ("passage", "query")}
        config = try_to_load_from_cache(run_eval.MODEL_ID, "config.json")
        provenance = {
            "model": run_eval.MODEL_ID, "device": str(model.device),
            "cache_revision": Path(config).parent.name if isinstance(config, str) else None,
            "max_seq_length": model.max_seq_length,
            "packages": {n: metadata.version(n) for n in (
                "sentence-transformers", "transformers", "tokenizers", "torch")}}
    except SystemExit as exc:
        raise _Stop(EXIT_REFUSED, str(exc.code)) from None
    except Exception as exc:  # noqa: BLE001 - a model file or package missing, however it fails
        raise _Stop(EXIT_REFUSED, "refused: the cached e5 model could not be loaded "
                    f"({type(exc).__name__}: {exc}); nothing is downloaded") from None
    return _E5(embedder=embedder, counters=counters, limit=model.max_seq_length,
               provenance=provenance)


def _client(config: generation.Config):
    """The pilot's direct client (fixed base URL, no automatic retries), for ``run`` only."""

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise _Stop(EXIT_REFUSED, "refused: ANTHROPIC_API_KEY is not set; load it with uv run "
                    "--env-file .env (the value is never printed)")
    return generation.client(key, config, workspace_id=os.environ.get("ANTHROPIC_WORKSPACE_ID"))


def _invalid(args: argparse.Namespace) -> str | None:
    """Why the arguments cannot be run, or None. Case ID and tag become file names."""

    if not math.isfinite(args.time_budget_s) or args.time_budget_s <= 0:
        return "--time-budget-s must be a finite number of seconds above 0"
    if not args.question.strip():
        return "--question must not be empty"
    for flag, value in (("--case-id", args.case_id), ("--tag", args.tag)):
        if not evidence_agent.CASE_ID.fullmatch(value):
            return (f"{flag} must be a plain name (letters, digits, '_', '.', '-', starting "
                    "with a letter or digit, at most 64 characters)")
    for edition in args.editions:
        try:
            iso = date.fromisoformat(edition).isoformat()
        except ValueError:
            iso = None
        if iso != edition:
            return f"--edition {edition!r} is not an edition date (YYYY-MM-DD)"
    if len(set(args.editions)) != len(args.editions):
        return "--edition names an edition twice"
    return None


def _paths(tag: str, case_id: str) -> dict[str, Path]:
    """The run's public record and its local folder (the agent's request and response
    artifacts, the accepted answer and the full result)."""

    name = f"{tag}-question-{case_id}"
    return {"public": RESULTS / f"{name}.json", "local": LOCAL / name}


def _existing(paths: dict[str, Path]) -> list[str]:
    """Outputs an earlier run left: the public record, or any file in the local folder."""

    found = [str(paths["public"])] if paths["public"].exists() else []
    local = paths["local"]
    if local.exists() and (not local.is_dir() or any(p.is_file() for p in local.rglob("*"))):
        found.append(str(local))  # an earlier run's files, or a file where the folder goes
    return found


@dataclass(frozen=True)
class _Loaded:
    """The verified corpus with the e5 model that counts and ranks its questions."""

    e5: _E5
    built: corpus.Corpus


def _load(manifest: Path) -> _Loaded:
    """Build the hash-verified corpus with the cached e5 model; every passage within its limit."""

    e5 = _e5()
    try:
        built = corpus.build_corpus(manifest,
                                    count_passage_tokens=lambda text: e5.count(text, "passage"),
                                    token_budget=TOKEN_BUDGET, model_limit=e5.limit)
    except corpus.CorpusError as exc:
        raise _Stop(EXIT_REFUSED, f"refused: {exc}") from None
    over = [p.passage_id for p in built.passages if p.tokens > e5.limit]
    if over:
        raise _Stop(EXIT_REFUSED, f"refused: passages over the e5 limit {e5.limit}: {over}")
    return _Loaded(e5=e5, built=built)


def _checked(loaded: _Loaded, question: str, editions: list[str]) -> int:
    """The question's e5 tokens, once its editions are in the corpus and it fits the model."""

    unknown = sorted(set(editions) - set(loaded.built.editions))
    if unknown:
        raise _Stop(EXIT_INPUT, f"invalid input: edition(s) {', '.join(unknown)} not in the "
                    f"verified corpus, which has {', '.join(loaded.built.editions)}")
    tokens = loaded.e5.count(question, "query")
    if tokens > loaded.e5.limit:  # the model would cut it silently: refused instead
        raise _Stop(EXIT_INPUT, f"invalid input: the question is {tokens} e5 tokens, over the "
                    f"model's {loaded.e5.limit}; it is never truncated, shorten it")
    return tokens


def _records(loaded: _Loaded) -> dict[str, dict]:
    """Every corpus passage as a request takes it, by passage ID."""

    titles = {d.edition: d.title for d in loaded.built.documents}
    return {p.passage_id: {
        "passage_id": p.passage_id, "edition": p.edition, "page": p.page,
        "page_label": p.page_label, "section": p.section, "section_title": p.section_title,
        "document_title": titles[p.edition], "text": p.text, "context": p.context,
        "text_sha256": p.text_sha256} for p in loaded.built.passages}


def _prepare(args: argparse.Namespace) -> _Prepared:
    """Build the verified corpus and rank the question afresh in the selected editions."""

    loaded = _load(args.manifest)
    tokens = _checked(loaded, args.question, args.editions)
    retriever = retrieval.Retriever(loaded.built.passages, loaded.e5.embedder)
    ranking = retriever.rank(args.question, method=METHOD, editions=args.editions)[:TOP_K]
    return _Prepared(retriever=retriever, passages=_records(loaded), ranking=ranking,
                     built=loaded.built, query_tokens=tokens,
                     embedder=dict(loaded.e5.provenance))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path)


def _initial(prepared: _Prepared) -> dict:
    """The initial retrieval: its settings and the top 5 by ID, score and hash, no text."""

    return {"method": METHOD, "mode": MODE, "k": TOP_K, "token_budget": TOKEN_BUDGET,
            "query_tokens": prepared.query_tokens, "embedder": prepared.embedder,
            "passages": [{"rank": n, "passage_id": hit.passage_id, "score": hit.score,
                          **{k: prepared.passages[hit.passage_id][k]
                             for k in ("edition", "page", "section", "text_sha256")}}
                         for n, hit in enumerate(prepared.ranking, start=1)]}


def _provenance(args: argparse.Namespace, prepared: _Prepared) -> dict:
    """Which code, settings, corpus and books a run used; computed before anything is sent,
    so nothing it needs (git, a file) can fail after an answer has come back."""

    config = generation.Config()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                          text=True, check=False).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", str(HERE)], cwd=REPO,
                           capture_output=True, text=True, check=False).stdout.strip()
    return {
        "case": args.case_id, "tag": args.tag, "question_sha256": _sha256(args.question),
        "editions": list(args.editions), "time_budget_s": args.time_budget_s,
        "configuration": {
            "model": config.model, "effort": config.effort, "thinking": {"type": "adaptive"},
            "max_tokens": config.max_tokens, "timeout_s": config.timeout_s,
            "client_max_retries": 0, "budget_usd": config.budget_usd,
            "input_margin": config.input_margin,
            "generation_calls": evidence_agent.GENERATION_CALLS,
            "max_input_tokens": evidence_agent.MAX_INPUT_TOKENS,
            "search_limits": dataclasses.asdict(evidence_search.SearchLimits()),
            "system_prompt_sha256": _sha256(
                f"{generation.SYSTEM_PROMPT}\n\n{evidence_agent.INSTRUCTION}"),
            "answer_schema_sha256": _sha256(json.dumps(generation.ANSWER_SCHEMA,
                                                       sort_keys=True))},
        "corpus": {
            "manifest": {"path": _rel(args.manifest),
                         "sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest()},
            "documents": [{"edition": d.edition, "sha256": d.sha256, "source_url": d.source_url,
                           "page_count": d.page_count} for d in prepared.built.documents],
            "passages": len(prepared.built.passages)},
        "books": {"historical_ledger": evidence_agent.HISTORICAL_LEDGER,
                  "historical_sha256": evidence_agent.HISTORICAL_SHA256,
                  "active_ledger": evidence_agent.ACTIVE_LEDGER},
        "environment": {"python": platform.python_version(),
                        "packages": {n: metadata.version(n) for n in ("anthropic", "httpx")},
                        "git_head": head, "tool_files_uncommitted": bool(dirty),
                        "tool_files_sha256": {n: hashlib.sha256((HERE / n).read_bytes())
                                              .hexdigest() for n in TOOL_FILES}},
        "provider_contract": "unverified before the first live run (ADR-026)",
    }


# A reservation whose append failed: the line may still be in the ledger (an error on closing
# leaves it in force, ADR-026), and the agent records no call for it.
UNCONFIRMED_RESERVATION = "reservation_not_saved"


def _accounting(result: evidence_agent.CaseResult) -> str:
    """How every call the case may have reserved stands in the books."""

    calls = result.record.get("calls", [])
    if result.detail == UNCONFIRMED_RESERVATION:
        return "uncertain"
    if not calls:
        return "nothing_reserved"
    if any(c.get("above_reservation") for c in calls):  # every call's flag, answer or not
        return "above_reservation"
    # Priced from validated usage, or recorded as never sent; anything else is a sent call
    # kept at its whole reservation, or one whose settlement the ledger does not confirm.
    if any(c.get("cost_basis") not in ("usage", "not_sent") for c in calls):
        return "uncertain"
    return "priced"


def _exit_code(result: evidence_agent.CaseResult, accounting: str, *, persisted: bool) -> int:
    """One code per run, by the precedence in ``EPILOG``."""

    if result.outcome == "persistence_error" or not persisted:
        return EXIT_PERSISTENCE
    if result.outcome == "spending_stop" or accounting == "above_reservation":
        return EXIT_SPENDING_STOP
    if accounting == "uncertain":
        return EXIT_ACCOUNTING_UNCERTAIN
    if result.outcome == "refused":
        return EXIT_REFUSED
    return EXIT_ANSWER if result.outcome == "answer" else EXIT_NOT_ANSWERED


def _answer_metadata(answer: dict | None) -> dict | None:
    """What a public record may say about an accepted answer: no claim or missing text."""

    if answer is None:
        return None
    return {"status": answer["status"], "claims": len(answer["claims"]),
            "cited_passages": sorted({c for claim in answer["claims"]
                                      for c in claim["citations"]}),
            "missing_evidence_items": len(answer["missing_evidence"]),
            # canonical JSON with ASCII escapes: any parsed text hashes, a lone surrogate too
            "answer_sha256": _sha256(json.dumps(answer, sort_keys=True))}


def _write(path: Path, value) -> None:
    """Create ``path`` with ``value`` as JSON; never replaces an earlier output."""

    text = json.dumps(value, ensure_ascii=False, indent=1)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:  # text UTF-8 cannot hold (a lone surrogate): escaped, not lost
        text = json.dumps(value, indent=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text + "\n")


def _run(args: argparse.Namespace, prepared: _Prepared, client) -> int:
    """Hand the question to the agent once, then keep and report what came back."""

    paths = _paths(args.tag, args.case_id)
    provenance = _provenance(args, prepared)
    task = evidence_agent.AgentTask(
        case_id=args.case_id, question=args.question, editions=tuple(args.editions),
        passages=tuple(prepared.passages[hit.passage_id] for hit in prepared.ranking))
    books = evidence_agent.BOOKS  # read now: the books are wherever the agent keeps them
    spending = evidence_agent.Spending(
        ledger=books / evidence_agent.ACTIVE_LEDGER,
        baseline=books / evidence_agent.HISTORICAL_LEDGER,
        baseline_sha256=evidence_agent.HISTORICAL_SHA256, artifacts=paths["local"])
    started = _now()
    result = evidence_agent.run_case(task, client=client, retriever=prepared.retriever,
                                     passages=prepared.passages, clock=CLOCK,
                                     budget_s=args.time_budget_s, spending=spending)
    finished = _now()
    status = {"execution": result.outcome, "detail": result.detail, "answer": result.status,
              "accounting": _accounting(result)}
    outputs: list[tuple[Path, object]] = []  # (path, builder): built and written one by one
    # Nothing reserved means nothing of this case is in the books: no output either, so a
    # refused retry publishes nothing and a question stopped before its first reservation
    # can be run again under the same tag. A reservation the ledger may hold counts as made.
    # The local answer first, then the local result, then the public record.
    if result.record.get("calls") or result.detail == UNCONFIRMED_RESERVATION:
        if result.answer is not None:
            outputs.append((paths["local"] / "answer.json", lambda: result.answer))
        outputs.append((paths["local"] / "result.json", lambda: {
            "case": args.case_id, "question": args.question, "editions": list(args.editions),
            "status": status, "answer": result.answer, "record": result.record,
            "local": result.local}))
        outputs.append((paths["public"], lambda: {
            "run": {**provenance, "started_at": started, "finished_at": finished},
            "initial_retrieval": _initial(prepared),
            # Named keys of the agent's publishable record, never the whole CaseResult.
            "agent": {k: result.record[k] for k in PUBLIC_RECORD if k in result.record},
            "answer": _answer_metadata(result.answer), "status": status, "notes": NOTES}))
    elif result.local.get("errors"):  # kept nowhere else: shown once, locally
        message = "errors (local only): " + "; ".join(map(str, result.local["errors"]))
        print(message.encode("utf-8", "backslashreplace").decode("utf-8"), file=sys.stderr)
    done, failed = [], []
    for path, build in outputs:  # each built and written on its own; nothing is sent again
        try:
            _write(path, build())
        except (OSError, TypeError, ValueError) as exc:  # unwritable, or not serializable
            failed.append({"path": str(path), "error": type(exc).__name__})
        else:
            done.append(str(path))
    code = _exit_code(result, status["accounting"], persisted=not failed)
    print(json.dumps({
        "case": args.case_id, "execution": {"outcome": result.outcome, "detail": result.detail},
        "answer_status": result.status,
        "accounting": {"status": status["accounting"], "calls": [
            {k: c.get(k) for k in ("attempt", "reserved_usd", "cost_usd", "cost_basis",
                                   "above_reservation")} for c in result.record.get("calls", [])]},
        "exit_code": code, "written": done, "not_written": failed, "note": NOTES[0]},
        ensure_ascii=False, indent=1))
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], epilog=EPILOG,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=("prepare", "run"),
                        help="prepare: check and rank only, offline; run: the live agent run")
    parser.add_argument("--case-id", required=True,
                        help="the case's identity in the books: a case ID is run at most once")
    parser.add_argument("--question", required=True, help="the one question, used as given")
    parser.add_argument("--edition", dest="editions", action="append", required=True,
                        help="an edition the question may use (YYYY-MM-DD); repeat for several")
    parser.add_argument("--time-budget-s", type=float, required=True,
                        help="the case's cooperative time limit in seconds (not money); it "
                             "starts after the model loads")
    parser.add_argument("--tag", default=datetime.now().astimezone().date().isoformat(),
                        help="date prefix of the output files (default: today); not an identity")
    parser.add_argument("--manifest", type=Path, default=REPO / "data/manifests/bag-al.json",
                        help="the AL manifest that pins the commentary PDFs by SHA-256")
    args = parser.parse_args(argv)
    problem = _invalid(args)
    if problem:
        parser.error(problem)  # exit 2, before anything is loaded, counted or sent
    args.editions = sorted(args.editions)
    args.manifest = args.manifest.resolve()
    paths = _paths(args.tag, args.case_id)
    try:
        existing = _existing(paths)
        if existing:
            raise _Stop(EXIT_REFUSED, f"refused: {', '.join(existing)} already exists; a run "
                        "never overwrites an earlier output, and a new tag does not make a new "
                        "case (the case ID is the identity in the books)")
        # The key is checked before the model loads; the client sends nothing by itself.
        client = _client(generation.Config()) if args.step == "run" else None
        prepared = _prepare(args)
    except _Stop as stop:
        print(stop, file=sys.stderr)
        return stop.code
    if args.step == "run":
        return _run(args, prepared, client)
    print(json.dumps({"case": args.case_id, "editions": args.editions,
                      "question_sha256": _sha256(args.question),
                      "initial_retrieval": _initial(prepared),
                      "run_would_write": {k: _rel(v) for k, v in paths.items()},
                      "sent": "nothing", "written": "nothing"}, ensure_ascii=False, indent=1))
    return EXIT_ANSWER


if __name__ == "__main__":
    raise SystemExit(main())
