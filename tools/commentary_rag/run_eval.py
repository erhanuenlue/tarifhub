"""Record the retrieval comparison on the real commentaries with the cached multilingual-e5 model.

Builds the corpus from the hash-verified commentary PDFs, ranks every dev case with BM25, e5
dense and RRF hybrid, with and without the edition filter, and writes one JSON record: source,
model and configuration identifiers, every full ranking, and the metrics. No LLM, no network
(the model must already be cached), no database.

    HF_HUB_OFFLINE=1 uv run --project services/ingestion --frozen --extra e5 --extra dev \\
        python tools/commentary_rag/run_eval.py --out tools/commentary_rag/results/<name>.json

``--recompute RECORD`` re-derives every metric from a stored record (no model needed);
``--compare BEFORE AFTER`` compares two records case by case and method by method.

Token counts use the loaded model's own tokenizer on the exact string the embedder encodes
(``passage: `` or ``query: `` prefix, special tokens included), never a character estimate, and
are checked against SentenceTransformer's own tokenization. The run refuses unless every passage
and query fits the model's ``max_seq_length``, so no input is truncated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import corpus
import evaluation
import retrieval

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MODEL_ID = "intfloat/multilingual-e5-large"
TOOL_FILES = ("corpus.py", "retrieval.py", "evaluation.py", "run_eval.py", "cases.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _e5():
    """The repository's own e5 embedder and the SentenceTransformer behind it, or a refusal."""

    from tarifhub_ingest.config import Settings  # noqa: PLC0415
    from tarifhub_ingest.embeddings.embedder import E5_DIMENSION, get_embedder  # noqa: PLC0415

    embedder = get_embedder(Settings(embeddings_backend="e5"))
    if embedder.dimension != E5_DIMENSION:
        raise SystemExit(
            "refused: the e5 model did not load and get_embedder fell back to the 16-dim stub; "
            "run with --extra e5 and the model in the Hugging Face cache"
        )
    model = getattr(embedder, "_model", None)  # the SentenceTransformer the embedder encodes with
    if model is None or not hasattr(model, "tokenizer") or not hasattr(model, "max_seq_length"):
        raise SystemExit("refused: cannot reach the e5 model's tokenizer and max_seq_length")
    return embedder, model


def _counter(model, kind: str):
    from tarifhub_ingest.embeddings.embedder import _e5_input  # noqa: PLC0415

    def count(text: str) -> int:
        encoded = _e5_input(text, kind=kind)
        tokens = len(model.tokenizer(encoded, add_special_tokens=True)["input_ids"])
        # SentenceTransformer's own path (truncates at max_seq_length): equal when it fits.
        own = len(model.preprocess([encoded])["input_ids"][0])
        if tokens <= model.max_seq_length and own != tokens:
            raise SystemExit(f"refused: tokenizer counts disagree ({tokens} vs {own})")
        return tokens

    return count


def _environment(model) -> dict:
    from huggingface_hub import try_to_load_from_cache  # noqa: PLC0415

    config = try_to_load_from_cache(MODEL_ID, "config.json")
    revision = Path(config).parent.name if isinstance(config, str) else None
    pdftotext = shutil.which("pdftotext")
    poppler = subprocess.run(
        [pdftotext, "-v"], capture_output=True, text=True, check=False
    ).stderr.splitlines()[0] if pdftotext else None
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=False
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", "tools/commentary_rag"], cwd=REPO,
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    packages = ("sentence-transformers", "transformers", "tokenizers", "torch", "huggingface-hub")
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "pdftotext": poppler,
        "packages": {name: metadata.version(name) for name in packages},
        "model": {
            "id": MODEL_ID,
            "cache_revision": revision,
            "device": str(model.device),
            "max_seq_length": model.max_seq_length,
            "passage_prefix": "passage: ",
            "query_prefix": "query: ",
        },
        "git_head": head,
        "tool_files_uncommitted": bool(dirty),
        "tool_files_sha256": {name: _sha256(HERE / name) for name in TOOL_FILES},
    }


def _run(args: argparse.Namespace) -> dict:
    embedder, model = _e5()
    limit = model.max_seq_length
    built = corpus.build_corpus(
        args.manifest,
        count_passage_tokens=_counter(model, "passage"),
        token_budget=args.token_budget,
        model_limit=limit,
    )
    over = [p.passage_id for p in built.passages if p.tokens > limit]
    if over:
        raise SystemExit(f"refused: passages over the model limit {limit}: {over}")
    cases = evaluation.load_cases(args.cases, built)
    count_query = _counter(model, "query")
    queries = {c.case_id: count_query(c.question) for c in cases}
    if max(queries.values()) > limit:
        raise SystemExit(f"refused: a query is over the model limit {limit}: {queries}")
    retriever = retrieval.Retriever(built.passages, embedder=embedder)
    record = evaluation.evaluate(built, cases, retriever, k=args.k)
    tokens = [p.tokens for p in built.passages]
    record["run"] = {
        "label": args.label,
        "baseline": (
            {"path": str(args.baseline.relative_to(REPO)), "sha256": _sha256(args.baseline)}
            if args.baseline
            else None
        ),
        "recorded_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "manifest": {"path": str(args.manifest.relative_to(REPO)),
                     "sha256": _sha256(args.manifest)},
        "cases_file": str(args.cases.relative_to(REPO)),
        "documents": [
            {"edition": d.edition, "path": d.path, "sha256": d.sha256,
             "source_url": d.source_url, "title": d.title, "page_count": d.page_count}
            for d in built.documents
        ],
        "excluded_pages": [
            {"edition": e.edition, "page": e.page, "reason": e.reason}
            for e in built.excluded_pages
        ],
        "configuration": {
            "token_budget": args.token_budget,
            "model_limit": limit,
            "k": args.k,
            "methods": list(retrieval.METHODS),
            "modes": list(evaluation.MODES),
            "bm25": {"k1": retrieval.BM25_K1, "b": retrieval.BM25_B},
            "rrf_k": retrieval.RRF_K,
        },
        "token_counts": {
            "passages": len(tokens),
            "min": min(tokens),
            "max": max(tokens),
            "mean": round(sum(tokens) / len(tokens), 1),
            "over_model_limit": 0,
            "queries": queries,
        },
        "corpus": {
            "by_edition": dict(Counter(p.edition for p in built.passages)),
            "splits": dict(sorted(Counter(p.split for p in built.passages).items())),
            "with_table_context": sum(1 for p in built.passages if p.context),
        },
        "environment": _environment(model),
        "not_measured": "answer generation, answer quality, abstention, human review",
    }
    return record


def _markdown(record: dict) -> str:
    def fmt(value, digits=3):
        return "n/a" if value is None else f"{value:.{digits}f}"

    lines = [
        "| Method | Mode | Evidence Recall@5 (cases) | MRR@5 (cases) "
        "| Wrong-edition passages@5 (cases) | Both-edition coverage@5 (cases) |",
        "|---|---|---|---|---|---|",
    ]
    for s in record["summary"]:
        lines.append(
            f"| {s['method']} | {s['mode']} | {fmt(s['evidence_recall'])} ({s['recall_cases']}) "
            f"| {fmt(s['mrr'])} ({s['mrr_cases']}) "
            f"| {s['wrong_edition_passages']}/{s['wrong_edition_retrieved']} "
            f"= {fmt(s['wrong_edition_rate'])} ({s['wrong_edition_cases']}) "
            f"| {fmt(s['both_edition_coverage'])} ({s['coverage_cases']}) |"
        )
    lines += ["", "| Case | Method | Mode | Recall@5 | MRR@5 | Wrong-edition@5 | Top 5 |",
              "|---|---|---|---|---|---|---|"]
    tops = {(r["case"], r["method"], r["mode"]): r["ranking"][: record["k"]]
            for r in record["runs"]}
    for s in record["scores"]:
        top = tops[(s["case"], s["method"], s["mode"])]
        wrong = "n/a" if s["wrong_edition"] is None else str(s["wrong_edition"])
        lines.append(
            f"| {s['case']} | {s['method']} | {s['mode']} | {fmt(s['evidence_recall'], 2)} "
            f"| {fmt(s['mrr'], 2)} | {wrong} | {', '.join(pid for pid, _ in top)} |"
        )
    return "\n".join(lines)


def _comparison_markdown(diff: dict) -> str:
    def fmt(value):
        return "n/a" if value is None else (str(value) if isinstance(value, int) else f"{value:.3f}")

    def pair(values):
        return f"{fmt(values[0])} → {fmt(values[1])}"

    p = diff["passages"]
    lines = [
        f"Settings that differ: {', '.join(diff['settings_differ']) or 'none'}",
        f"Passages: {len(p['removed'])} removed, {len(p['added'])} added, "
        f"{len(p['changed'])} changed, {p['unchanged']} unchanged",
        "",
        "| Case | Item | Covering passages before | after |",
        "|---|---|---|---|",
    ]
    lines += [f"| {e['case']} | {e['item']} | {', '.join(e['before'])} | {', '.join(e['after'])} |"
              for e in diff["evidence"]]
    lines += ["", "| Method | Mode | Recall@5 | MRR@5 | Wrong-edition rate | Both-edition coverage |",
              "|---|---|---|---|---|---|"]
    lines += [f"| {s['method']} | {s['mode']} | {pair(s['evidence_recall'])} | {pair(s['mrr'])} "
              f"| {pair(s['wrong_edition_rate'])} | {pair(s['both_edition_coverage'])} |"
              for s in diff["summary"]]
    lines += ["", "| Case | Method | Mode | Recall@5 | MRR@5 | Wrong-edition@5 | Change |",
              "|---|---|---|---|---|---|---|"]
    lines += [f"| {c['case']} | {c['method']} | {c['mode']} | {pair(c['evidence_recall'])} "
              f"| {pair(c['mrr'])} | {pair(c['wrong_edition'])} | {c['change']} |"
              for c in diff["cases"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=REPO / "data/manifests/bag-al.json")
    parser.add_argument("--cases", type=Path, default=HERE / "cases.json")
    parser.add_argument("--token-budget", type=int, default=256)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--out", type=Path, help="write the JSON record here")
    parser.add_argument("--recompute", type=Path, help="check the metrics of a stored record")
    parser.add_argument("--label", help="what distinguishes this run, stored in the record")
    parser.add_argument("--baseline", type=Path, help="the record this run is compared with")
    parser.add_argument("--compare", type=Path, nargs=2, metavar=("BEFORE", "AFTER"),
                        help="compare two records; with --out, also write the comparison JSON")
    args = parser.parse_args(argv)
    if args.compare:
        before, after = (json.loads(p.read_text(encoding="utf-8")) for p in args.compare)
        diff = evaluation.compare_records(before, after)
        if args.out:
            args.out.write_text(json.dumps(diff, ensure_ascii=False, indent=1) + "\n",
                                encoding="utf-8")
        print(_comparison_markdown(diff))
        return 0
    if args.recompute:
        record = json.loads(args.recompute.read_text(encoding="utf-8"))
        mismatches = evaluation.recompute(record)
        print("\n".join(mismatches) if mismatches else "all stored metrics recompute exactly")
        return 1 if mismatches else 0
    if args.out is None:
        parser.error("--out is required for a run")
    args.manifest = args.manifest.resolve()
    args.cases = args.cases.resolve()
    args.baseline = args.baseline.resolve() if args.baseline else None
    record = _run(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(_markdown(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
