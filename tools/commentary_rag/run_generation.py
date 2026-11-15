"""The recorded generation pilot: retrieval rerun, plan, run, record and review sheet.

Three steps, each run from the repository root:

``prepare`` (no network, the e5 model must be cached) reruns the frozen corrected retrieval
through ``run_eval``'s own code path, writes the rerun record, compares its rankings, scores and
passages with the saved corrected record, checks every rubric support quote against the corpus,
and writes the local contexts file (hybrid RRF, edition filter, top 5, with passage text).
It refuses to write contexts when a top 5 differs from the saved record::

    HF_HUB_OFFLINE=1 uv run --project services/ingestion --frozen --offline --extra ai \\
        --extra dev python tools/commentary_rag/run_generation.py prepare

``plan`` and ``run`` need ``ANTHROPIC_API_KEY``, loaded from the root ``.env`` by uv (presence
is checked, the value is never printed or stored). ``plan`` reads the model's entry from the
Models API and counts every request with the token-counting endpoint (both free); ``run`` sends
the requests within the ledger's budget and attempt cap and writes the public record and the
local review sheet::

    uv run --project services/ingestion --frozen --offline --extra ai --extra dev \\
        --env-file .env python tools/commentary_rag/run_generation.py plan|run

Public outputs (``results/``) hold metrics, hashes, usage and calculated cost; full request
contexts, raw responses, answers and the review sheet stay in ``local/`` (git-ignored).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import anthropic
import answers
import evaluation
import generation

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULTS = HERE / "results"
LOCAL = HERE / "local"
CORRECTED = RESULTS / "2026-11-14-retrieval-corrected.json"
LEDGER = RESULTS / "generation-ledger.jsonl"
METHOD, MODE = "hybrid", "edition_filter"
TOOL_FILES = ("corpus.py", "retrieval.py", "evaluation.py", "run_eval.py", "cases.json",
              "generation.py", "answers.py", "run_generation.py", "rubric.json", "pricing.json")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path)


def _refuse_existing(*paths: Path) -> None:
    """A step never replaces what an earlier run wrote: its records are evidence."""

    existing = [_rel(p) for p in paths if p.exists()]
    if existing:
        raise SystemExit(f"refused: {', '.join(existing)} already exists; a step never "
                         "overwrites an earlier output (use a new --tag, or move the file "
                         "deliberately)")


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:  # never replaces an earlier output
        handle.write(json.dumps(value, ensure_ascii=False, indent=1) + "\n")


def _paths(tag: str, prepared: str) -> dict[str, Path]:
    """Prepared inputs carry the date of ``prepare``; the run's outputs carry the run's date."""

    return {
        "rerun": RESULTS / f"{prepared}-retrieval-rerun.json",
        "contexts": LOCAL / f"{prepared}-contexts.json",
        "plan": RESULTS / f"{tag}-generation-plan.json",
        "record": RESULTS / f"{tag}-generation.json",
        "artifacts": LOCAL / f"{tag}-generation",
        "sheet": LOCAL / f"{tag}-review-sheet.md",
        "result": LOCAL / f"{tag}-generation" / "run-result.json",
    }


def _top(record: dict) -> dict[str, list[str]]:
    k = record["k"]
    return {r["case"]: [pid for pid, _ in r["ranking"][:k]] for r in record["runs"]
            if r["method"] == METHOD and r["mode"] == MODE}


def reproduction(saved: dict, rerun: dict) -> dict:
    """How far a rerun reproduces a saved record: rankings, scores, metrics, passages."""

    later = {(r["case"], r["method"], r["mode"]): r["ranking"] for r in rerun["runs"]}
    same_order = 0
    worst = 0.0
    for run in saved["runs"]:
        new = later[(run["case"], run["method"], run["mode"])]
        same_order += [pid for pid, _ in run["ranking"]] == [pid for pid, _ in new]
        scores = dict(new)
        worst = max([worst, *(abs(score - scores.get(pid, float("inf")))
                              for pid, score in run["ranking"])])
    diff = evaluation.compare_records(saved, rerun)
    return {
        "rankings_identical": f"{same_order}/{len(saved['runs'])}",
        "max_abs_score_difference": worst,
        "metrics_identical": saved["scores"] == rerun["scores"]
        and saved["summary"] == rerun["summary"],
        "settings_differ": diff["settings_differ"],
        "passages": {key: value for key, value in diff["passages"].items()},
        "context_top_k_identical": _top(saved) == _top(rerun),
    }


def prepare(args: argparse.Namespace) -> int:
    paths = _paths(args.tag, args.tag)
    _refuse_existing(paths["rerun"], paths["contexts"])
    import corpus  # noqa: PLC0415 - prepare alone needs the e5 stack
    import run_eval  # noqa: PLC0415

    saved = json.loads(CORRECTED.read_text(encoding="utf-8"))
    rerun = run_eval._run(argparse.Namespace(  # the same code path as the saved run
        manifest=args.manifest, cases=HERE / "cases.json", token_budget=256, k=5,
        label="pre-generation rerun of the corrected retrieval (same code, cases and settings)",
        baseline=CORRECTED))
    _write_json(paths["rerun"], rerun)
    check = reproduction(saved, rerun)
    print(json.dumps(check, indent=1))
    if not check["context_top_k_identical"] or check["passages"]["changed"] or \
            check["passages"]["added"] or check["passages"]["removed"]:
        print("refused: the rerun does not reproduce the saved contexts; investigate first")
        return 2
    _, model = run_eval._e5()
    built = corpus.build_corpus(args.manifest,
                                count_passage_tokens=run_eval._counter(model, "passage"),
                                token_budget=256, model_limit=model.max_seq_length)
    by_id = {p.passage_id: p for p in built.passages}
    hashes = {p["passage_id"]: p["text_sha256"] for p in saved["passages"]}
    if {pid: p.text_sha256 for pid, p in by_id.items()} != hashes:
        print("refused: the rebuilt corpus differs from the saved record's passages")
        return 2
    titles = {d.edition: d.title for d in built.documents}
    rubric = {c["id"]: c for c in json.loads((HERE / "rubric.json").read_text("utf-8"))["cases"]}
    problems: list[str] = []

    def covering(case_id: str, support: list[dict]) -> list[str]:
        ids: list[str] = []
        for quote in support:
            item = evaluation.Evidence(quote["edition"], quote["page"],
                                       corpus.normalize(quote["quote"]))
            found = evaluation.covering(item, built)
            if not found:
                problems.append(f"{case_id}: rubric quote not in one passage on "
                                f"{item.edition} p. {item.page}: {item.quote!r}")
            ids += found
        return ids

    top = _top(saved)
    items = []
    for case in saved["cases"]:
        r = rubric[case["id"]]
        items.append({
            "case": case["id"], "question": case["question"], "editions": case["target_editions"],
            "passages": [
                {"rank": n, "passage_id": pid, "edition": by_id[pid].edition,
                 "page": by_id[pid].page, "page_label": by_id[pid].page_label,
                 "section": by_id[pid].section, "section_title": by_id[pid].section_title,
                 "document_title": titles[by_id[pid].edition], "text": by_id[pid].text,
                 "context": by_id[pid].context, "text_sha256": by_id[pid].text_sha256}
                for n, pid in enumerate(top[case["id"]], start=1)],
            # Scoring only: never part of a request (generation.request reads none of these).
            "evidence": [e["covering_passages"] for e in case["evidence"]],
            "rubric": {
                "expected_status": r["expected_status"],
                "required": [{"id": c["id"], "claim": c["claim"], "support": c["support"],
                              "covering": covering(case["id"], c["support"]),
                              "terms": c["check_terms"]} for c in r["required_claims"]],
                "optional": [{"claim": c["claim"], "support": c["support"],
                              "covering": covering(case["id"], c["support"])}
                             for c in r["optional_background"]],
                "review_focus": r["review_focus"]},
        })
    if problems:
        print("refused: rubric support not found in the corpus:\n" + "\n".join(problems))
        return 2
    _write_json(paths["contexts"], {"corrected_record_sha256": _sha256_file(CORRECTED),
                                    "rerun_record_sha256": _sha256_file(paths["rerun"]),
                                    "reproduction": check, "items": items})
    print(f"contexts for {len(items)} cases written to {_rel(paths['contexts'])}")
    return 0


def _items(paths: dict[str, Path]) -> tuple[list[dict], dict]:
    """The prepared contexts, checked again against the saved corrected record."""

    data = json.loads(paths["contexts"].read_text(encoding="utf-8"))
    saved = json.loads(CORRECTED.read_text(encoding="utf-8"))
    meta = {p["passage_id"]: p for p in saved["passages"]}
    cases = {c["id"]: c for c in saved["cases"]}
    titles = {d["edition"]: d["title"] for d in saved["run"]["documents"]}
    top = _top(saved)
    for it in data["items"]:
        case = cases.get(it["case"])
        if case is None or (it["question"], it["editions"]) != (case["question"],
                                                                 case["target_editions"]):
            raise SystemExit(f"refused: {it['case']} question or editions differ from the "
                             "saved record")
        if [p["passage_id"] for p in it["passages"]] != top[it["case"]]:
            raise SystemExit(f"refused: {it['case']} context differs from the saved record's top 5")
        for p in it["passages"]:  # everything the request carries, not only the text
            m = meta[p["passage_id"]]
            if not (_sha256_text(p["text"]) == p["text_sha256"] == m["text_sha256"]
                    and (_sha256_text(p["context"]) if p["context"] else None)
                    == m["context_sha256"]
                    and all(p[k] == m[k] for k in ("edition", "page", "page_label", "section",
                                                   "section_title"))
                    and p["edition"] in case["target_editions"]
                    and p["document_title"] == titles[p["edition"]]):
                raise SystemExit(f"refused: {it['case']} passage {p['passage_id']} does not match "
                                 "the saved record")
    return data["items"], data


def _client(config: generation.Config):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("refused: ANTHROPIC_API_KEY is not set; load it with uv run "
                         "--env-file .env (the value is never printed)")
    return generation.client(key, config, workspace_id=os.environ.get("ANTHROPIC_WORKSPACE_ID"))


def _model_info(client, config: generation.Config) -> dict:
    """The model's Models API entry, or a clean stop on an access or model blocker."""

    try:
        raw = client.models.with_raw_response.retrieve(config.model)
    except anthropic.APIStatusError as exc:
        raise SystemExit(f"stopped before any generation: models.retrieve {config.model} "
                         f"http_{exc.status_code}: {generation.error_text(exc)}") from None
    return json.loads(raw.http_response.text)


def _pricing() -> tuple[generation.Pricing, dict]:
    data = json.loads((HERE / "pricing.json").read_text(encoding="utf-8"))
    return generation.Pricing(**{k: data[k] for k in (
        "input", "output", "cache_write_5m", "cache_write_1h", "cache_read", "source",
        "retrieved")}), data


def _configuration(config: generation.Config) -> dict:
    return {
        "provider": "Anthropic Messages API, direct", "base_url": generation.BASE_URL,
        "model": config.model, "effort": config.effort, "thinking": {"type": "adaptive"},
        "thinking_display": "API default (omitted)", "max_tokens": config.max_tokens,
        "max_tokens_bounds": "thinking and answer together", "timeout_s": config.timeout_s,
        "client_max_retries": 0, "max_attempts": config.max_attempts,
        "retry_policy": "after every case had one attempt, a failed case is retried while the "
                        "ledger has fewer than max_attempts attempts; valid answers are never "
                        "repeated; any other 4xx or a returned model that differs stops the run",
        "budget_usd": config.budget_usd, "input_margin": config.input_margin,
        "workspace_header": "sent (value not recorded)" if os.environ.get(
            "ANTHROPIC_WORKSPACE_ID") else "not sent",
        "not_sent": "tools, web search, MCP servers, server-side fallbacks, sampling "
                    "parameters, prompt caching, inference_geo, fast mode",
        "system_prompt_sha256": _sha256_text(generation.SYSTEM_PROMPT),
        "answer_schema_sha256": _sha256_text(json.dumps(generation.ANSWER_SCHEMA,
                                                        sort_keys=True)),
        "retrieval": {"method": METHOD, "mode": MODE, "k": 5, "token_budget": 256},
    }


def plan(args: argparse.Namespace) -> int:
    paths = _paths(args.tag, args.prepared)
    _refuse_existing(paths["plan"])
    items, _ = _items(paths)
    config = generation.Config()
    pricing, pricing_data = _pricing()
    client = _client(config)
    info = _model_info(client, config)
    result = generation.run(items, client=client, config=config, pricing=pricing,
                            ledger=LEDGER, plan_only=True)
    if result["stopped"]:
        print(f"stopped: {result['stopped']}")
        return 2
    ceilings = [row["ceiling_usd"] for row in result["plan"]]
    record = {
        "recorded_at": _now(), "model_info": info, "configuration": _configuration(config),
        "pricing": pricing_data, "rubric_sha256": _sha256_file(HERE / "rubric.json"),
        "rows": result["plan"], "not_attempted": result["not_attempted"],
        "totals": {"first_pass_ceiling_usd": round(sum(ceilings), 6),
                   "worst_case_ceiling_usd": round(config.max_attempts * max(ceilings), 6)
                   if ceilings else 0.0,
                   "committed_before_usd": generation.committed_usd(LEDGER),
                   "budget_usd": config.budget_usd},
    }
    _write_json(paths["plan"], record)
    print(json.dumps({k: record[k] for k in ("rows", "totals")}, indent=1))
    print(f"model: requested {config.model}, Models API id {info.get('id')}, "
          f"max_tokens {info.get('max_tokens')}, max_input_tokens {info.get('max_input_tokens')}")
    return 0


def run(args: argparse.Namespace) -> int:
    paths = _paths(args.tag, args.prepared)
    _refuse_existing(paths["result"], paths["record"], paths["sheet"])
    items, _ = _items(paths)
    config = generation.Config()
    pricing, _ = _pricing()
    client = _client(config)
    started = _now()
    result = generation.run(items, client=client, config=config, pricing=pricing,
                            ledger=LEDGER, artifacts=paths["artifacts"])
    if (result["stopped"] or "").startswith(generation.LOCKED_OUT):  # the other run publishes
        print(f"stopped: {result['stopped']}")
        return 2
    _write_json(paths["result"], {"started_at": started, "finished_at": _now(), **result})
    return report(args)


def report(args: argparse.Namespace) -> int:
    """Rebuild the public record and the review sheet from the ledger and local artifacts."""

    paths = _paths(args.tag, args.prepared)
    sheet_only = getattr(args, "sheet_only", False)
    _refuse_existing(paths["sheet"], *(() if sheet_only else (paths["record"],)))
    items, data = _items(paths)
    config = generation.Config()
    _, pricing_data = _pricing()
    result = json.loads(paths["result"].read_text(encoding="utf-8"))
    if sheet_only:  # re-render the local sheet; the record stays as written
        record = json.loads(paths["record"].read_text(encoding="utf-8"))
    else:
        record = build_record(items, data, result, paths, config, pricing_data)
        _write_json(paths["record"], record)
    _write_review_sheet(paths["sheet"], items, record, paths)
    print(json.dumps({"stopped": result["stopped"], "not_attempted": result["not_attempted"],
                      "retries_skipped": result["retries_skipped"],
                      "attempts": record["attempt_summary"], "checks": record["summary"]},
                     ensure_ascii=False, indent=1))
    print(f"record: {_rel(paths['record'])}; review sheet (local): {_rel(paths['sheet'])}")
    return 0 if not result["stopped"] else 2


def _answer(paths: dict[str, Path], attempt: dict, it: dict) -> dict | None:
    """The saved answer of a settled attempt, refused unless it is the response it recorded."""

    text = (paths["artifacts"] / "responses" / f"{attempt['attempt']}.json").read_text("utf-8")
    if _sha256_text(text) != attempt["response_sha256"]:
        raise SystemExit(f"refused: the saved response of {attempt['attempt']} does not match "
                         "its recorded hash")
    content = json.loads(text).get("content", [])
    body = "".join(b.get("text", "") for b in content if b.get("type") == "text")
    answer, _, _ = generation.validate(body, [p["passage_id"] for p in it["passages"]])
    return answer


def build_record(items, data, result, paths, config, pricing_data) -> dict:  # noqa: PLR0913
    """The public record: configuration, contexts by hash, every attempt, checks, no answers."""

    # A run's record covers its own attempts: those whose request it saved under its tag (saved
    # before settling, so an attempt settled before an interruption still counts).
    saved = paths["artifacts"] / "requests"
    attempts = [a for a in generation.settled(LEDGER) if (saved / f"{a['attempt']}.json").exists()]
    rows, answer_rows = [], []
    for it in items:
        mine = [a for a in attempts if a["case"] == it["case"]]
        valid = [a for a in mine if a["outcome"] == "valid"]
        final = valid[-1] if valid else (mine[-1] if mine else None)
        answer = _answer(paths, final, it) if valid else None
        rows.append(answers.score_case(
            case_id=it["case"], expected_status=it["rubric"]["expected_status"],
            evidence=[set(c) for c in it["evidence"]],
            required=[{"id": r["id"], "covering": set(r["covering"]), "terms": r["terms"]}
                      for r in it["rubric"]["required"]],
            context=[p["passage_id"] for p in it["passages"]], answer=answer,
            failure=final["outcome"] if final and not answer else None))
        if answer:
            answer_rows.append({
                "case": it["case"], "attempt": final["attempt"], "status": answer["status"],
                "claims": len(answer["claims"]),
                "cited_passages": sorted({c for cl in answer["claims"] for c in cl["citations"]}),
                "missing_evidence_items": len(answer["missing_evidence"]),
                "answer_sha256": _sha256_text(json.dumps(answer, ensure_ascii=False,
                                                         sort_keys=True))})
    plan_record = json.loads(paths["plan"].read_text("utf-8")) if paths["plan"].exists() else {}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                          text=True, check=False).stdout.strip()
    return {
        "run": {
            "run_id": paths["record"].stem,
            "label": "first commentary RAG generation pilot (exploratory, dev cases only)",
            "started_at": result.get("started_at"), "finished_at": result.get("finished_at"),
            "recorded_at": _now(), "configuration": _configuration(config),
            "model_info": plan_record.get("model_info"), "pricing": pricing_data,
            "retrieval": {"saved_record": {"path": _rel(CORRECTED),
                                           "sha256": data["corrected_record_sha256"]},
                          "rerun_record_sha256": data["rerun_record_sha256"],
                          "reproduction": data["reproduction"]},
            "rubric": {"path": _rel(HERE / "rubric.json"),
                       "sha256": _sha256_file(HERE / "rubric.json"),
                       "status": "provisional, AI-drafted before generation, pending review"},
            "ledger": {"path": _rel(LEDGER), "committed_usd": generation.committed_usd(LEDGER)},
            "stopped": result["stopped"], "not_attempted": result["not_attempted"],
            "retries_skipped": result["retries_skipped"],
            "environment": {
                "python": platform.python_version(), "platform": platform.platform(),
                "packages": {n: metadata.version(n) for n in ("anthropic", "httpx")},
                "anthropic_version_header": "2023-06-01 (set by the installed client)",
                "git_head": head,
                "tool_files_sha256": {n: _sha256_file(HERE / n) for n in TOOL_FILES}},
            "human_review": "pending: semantic support of every claim and the rubric itself",
            "cost_note": "calculated from reported usage and the recorded prices, not an invoice",
        },
        "contexts": [{"case": it["case"], "editions": it["editions"],
                      "passages": [{k: p[k] for k in ("rank", "passage_id", "edition", "page",
                                                      "section", "text_sha256")}
                                   for p in it["passages"]],
                      "request_sha256": next((r["request_sha256"] for r in plan_record.get(
                          "rows", []) if r["case"] == it["case"]), None)}
                     for it in items],
        "attempts": attempts,
        "answers": answer_rows,
        "checks": rows,
        "summary": answers.summarize(rows),
        "attempt_summary": answers.attempt_summary(attempts),
    }


def _write_review_sheet(path: Path, items: list[dict], record: dict, paths) -> None:
    checks = {r["case"]: r for r in record["checks"]}
    finals = {a["case"]: a for a in record["answers"]}
    box = "[ ] yes  [ ] partly  [ ] no"
    lines = [
        "# Commentary RAG pilot: human review sheet",
        "",
        f"Run `{record['run']['run_id']}`: started {record['run']['started_at']}, finished "
        f"{record['run']['finished_at']}, {record['run']['configuration']['model']} (effort "
        f"{record['run']['configuration']['effort']}). Local file, not committed.",
        "Answers are reproduced unchanged. Ratings below are empty: they are for Erhan; nothing",
        "here is a human judgement yet. Deterministic checks are labelled as checks, not",
        "semantic or legal validation. The rubric is an AI draft pending review. The model",
        "received each passage with its document title, edition, page and section title, so a",
        "claim may rest on those attributes as well as on the passage text; both are shown.",
        "",
    ]
    for it in items:
        c = checks[it["case"]]
        by_id = {p["passage_id"]: p for p in it["passages"]}
        lines += [f"## {it['case']}: {it['question']}", "",
                  f"- Editions selected: {', '.join(it['editions'])}",
                  f"- Retrieval (hybrid, edition filter, top 5): {c['retrieval']}, "
                  f"{c['evidence_in_context']} of {c['evidence_items']} gold items in context",
                  f"- Generation outcome: {c['outcome']}"
                  + (f" ({c['failure']})" if c["failure"] else "")
                  + (f", status {c['status']}" if c["status"] else "")
                  + f"; expected status {c['expected_status']}", ""]
        answer = None
        if it["case"] in finals:
            attempt = next(a for a in record["attempts"]
                           if a["attempt"] == finals[it["case"]]["attempt"])
            answer = _answer(paths, attempt, it)
        if answer:
            lines += ["### Answer (claims as generated)", ""]
            for n, claim in enumerate(answer["claims"], start=1):
                lines += [f"{n}. {claim['text']}",
                          f"   - Cited: {', '.join(claim['citations']) or 'none'}",
                          f"   - Erhan, supported by the cited passages? {box}  Note:"]
            missing = answer["missing_evidence"] or ["(none stated)"]
            lines += ["", "Missing evidence stated by the answer:", *[f"- {m}" for m in missing],
                      "", "### Cited passages", ""]
            cited = [pid for pid in dict.fromkeys(
                c for cl in answer["claims"] for c in cl["citations"])]
            for pid in cited:
                p = by_id.get(pid)
                lines.append(f"- `{pid}`: " + (
                    f"edition {p['edition']}, PDF p. {p['page']} (printed {p['page_label']}), "
                    f"section {p['section']} «{p['section_title']}», document "
                    f"«{p['document_title']}»: {p['text']}"
                    if p else "NOT IN THIS REQUEST'S CONTEXT"))
        lines += ["", "### Rubric (AI draft, pending review)", ""]
        for r in it["rubric"]["required"]:
            available = bool(set(r["covering"]) & set(by_id))
            quotes = "; ".join(f"{s['edition']} p. {s['page']}: \"{s['quote']}\""
                               for s in r["support"])
            check = ("human review only" if not r["terms"] else
                     ("terms stated" if answer and answers.stated(
                         r["terms"], "\n".join(cl["text"] for cl in answer["claims"]))
                      else "terms not stated"))
            lines += [f"- {r['id']}: {r['claim']}",
                      f"  - Support: {quotes}; in context: {'yes' if available else 'no'}; "
                      f"term check: {check}",
                      f"  - Erhan, covered by the answer? {box}"]
        if not it["rubric"]["required"]:
            lines.append("- No required claims: the expected behaviour is to report that the "
                         "selected commentary does not state it.")
        lines += [f"- Review focus: {it['rubric']['review_focus']}", "",
                  f"Erhan, overall: appropriate behaviour for this case? {box}  Note:", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:  # never replaces an earlier sheet
        handle.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", choices=("prepare", "plan", "run", "report"))
    parser.add_argument("--tag", default=datetime.now().astimezone().date().isoformat(),
                        help="date prefix of this step's outputs (default: today)")
    parser.add_argument("--sheet-only", action="store_true",
                        help="report: re-render the local review sheet, keep the record as is")
    parser.add_argument("--prepared",
                        help="date prefix of the prepare outputs that plan, run and report use "
                             "(default: --tag; the 2026-11-15 run used 2026-11-14)")
    parser.add_argument("--manifest", type=Path, default=REPO / "data/manifests/bag-al.json")
    args = parser.parse_args(argv)
    args.manifest = args.manifest.resolve()
    args.prepared = args.prepared or args.tag
    return {"prepare": prepare, "plan": plan, "run": run, "report": report}[args.step](args)


if __name__ == "__main__":
    raise SystemExit(main())
