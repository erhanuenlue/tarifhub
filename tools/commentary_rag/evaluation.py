"""Dev cases and retrieval metrics for the commentary corpus.

Relevance unit: an evidence item, a verbatim quote (NFC, whitespace folded) on one page of one
edition's commentary. A retrieved passage covers an item when it is from that edition and page
and its text contains the quote. Items are checked against the corpus before any measurement:
a quote missing from its stated page, or split across two passages, refuses the case file.

Metrics over the top ``k`` passages of one ranking (definitions fixed before measuring):

* Evidence Recall@k: covered items / items. Undefined (``None``) for a case without items.
* MRR@k: 1 / rank of the first passage covering any item, 0 if none in the top k. Undefined
  for a case without items.
* Wrong-edition passages@k: top-k passages whose edition is not a target edition of the case.
  Undefined when the case targets every edition of the corpus. Under a strict edition filter
  equal to the target editions it is 0 by construction (no other edition is a candidate).
* Both-edition coverage@k: 1 when the top k cover at least one item of every edition the
  case's items come from, else 0. Defined only for cases with items from two or more editions.

Aggregates average the defined cases only and report their number; the wrong-edition rate is
the wrong passages over all passages retrieved for the defined cases.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from corpus import Corpus, normalize


class CaseError(ValueError):
    """The case file references evidence the corpus does not support."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("cases refused:\n" + "\n".join(f"- {p}" for p in problems))


@dataclass(frozen=True)
class Evidence:
    """One evidence item: a verbatim quote on one page of one edition's commentary."""

    edition: str
    page: int
    quote: str


@dataclass(frozen=True)
class Case:
    """One dev case: a question, its target editions and its evidence items (maybe none)."""

    case_id: str
    question: str
    target_editions: tuple[str, ...]
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class CaseScore:
    """The metrics of one case for one ranking; ``None`` where a metric is undefined."""

    evidence_recall: float | None
    mrr: float | None
    wrong_edition: int | None
    retrieved: int
    both_edition_coverage: int | None


@dataclass(frozen=True)
class Summary:
    """Metrics over cases; each mean is over the cases where the metric is defined."""

    evidence_recall: float | None
    recall_cases: int
    mrr: float | None
    mrr_cases: int
    wrong_edition_rate: float | None
    wrong_edition_passages: int
    wrong_edition_retrieved: int
    wrong_edition_cases: int
    both_edition_coverage: float | None
    coverage_cases: int


def case_metrics(  # noqa: PLR0913 - keyword-only primitives, so a stored record can be rescored
    *,
    top: Sequence[str],
    covers: Sequence[set[str]],
    item_editions: Sequence[str],
    target_editions: Sequence[str],
    corpus_editions: Sequence[str],
    edition_of: Mapping[str, str],
) -> CaseScore:
    """Score one ranking's ``top`` passages; ``covers[i]`` holds the passages covering item i."""

    recall = mrr = None
    if covers:
        recall = sum(1 for c in covers if c & set(top)) / len(covers)
        ranks = [r for r, pid in enumerate(top, start=1) if any(pid in c for c in covers)]
        mrr = 1 / ranks[0] if ranks else 0.0
    wrong = None
    if set(target_editions) != set(corpus_editions):
        wrong = sum(1 for pid in top if edition_of[pid] not in target_editions)
    coverage = None
    if len(set(item_editions)) >= 2:
        covered = {e for e, c in zip(item_editions, covers, strict=True) if c & set(top)}
        coverage = int(covered == set(item_editions))
    return CaseScore(recall, mrr, wrong, len(top), coverage)


def aggregate(scores: Sequence[CaseScore]) -> Summary:
    """Average each metric over the cases where it is defined."""

    def mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    recalls = [s.evidence_recall for s in scores if s.evidence_recall is not None]
    mrrs = [s.mrr for s in scores if s.mrr is not None]
    wrong = [s for s in scores if s.wrong_edition is not None]
    coverage = [s.both_edition_coverage for s in scores if s.both_edition_coverage is not None]
    passages = sum(s.wrong_edition for s in wrong)
    retrieved = sum(s.retrieved for s in wrong)
    return Summary(
        evidence_recall=mean(recalls),
        recall_cases=len(recalls),
        mrr=mean(mrrs),
        mrr_cases=len(mrrs),
        wrong_edition_rate=passages / retrieved if retrieved else None,
        wrong_edition_passages=passages,
        wrong_edition_retrieved=retrieved,
        wrong_edition_cases=len(wrong),
        both_edition_coverage=mean([float(c) for c in coverage]),
        coverage_cases=len(coverage),
    )


MODES = ("edition_filter", "no_filter")


def evaluate(built: Corpus, cases: Sequence[Case], retriever, *, k: int = 5) -> dict:
    """Rank every case with every method, with and without the edition filter, and score it.

    ``edition_filter`` selects the case's target editions, ``no_filter`` every corpus edition
    (for a case targeting every edition the two runs are the same selection). The record keeps
    passage metadata (no passage text), each item's covering passages, every full ranking with
    its scores, and the metrics, so :func:`recompute` can check the metrics from it alone.
    """

    from retrieval import METHODS  # noqa: PLC0415 - keeps the metric module import-light

    runs = []
    for c in cases:
        for method in METHODS:
            for mode in MODES:
                editions = list(c.target_editions if mode == "edition_filter" else built.editions)
                hits = retriever.rank(c.question, method=method, editions=editions)
                runs.append(
                    {
                        "case": c.case_id,
                        "method": method,
                        "mode": mode,
                        "editions": editions,
                        "ranking": [[h.passage_id, h.score] for h in hits],
                    }
                )
    record = {
        "k": k,
        "corpus_editions": list(built.editions),
        "passages": [
            {
                "passage_id": p.passage_id,
                "edition": p.edition,
                "page": p.page,
                "page_label": p.page_label,
                "section": p.section,
                "section_title": p.section_title,
                "tokens": p.tokens,
                "split": p.split,
                "text_sha256": p.text_sha256,
                "context_sha256": (
                    hashlib.sha256(p.context.encode("utf-8")).hexdigest() if p.context else None
                ),
                "document_sha256": p.document_sha256,
            }
            for p in built.passages
        ],
        "cases": [
            {
                "id": c.case_id,
                "question": c.question,
                "target_editions": list(c.target_editions),
                "evidence": [
                    {
                        "edition": e.edition,
                        "page": e.page,
                        "quote": e.quote,
                        "covering_passages": covering(e, built),
                    }
                    for e in c.evidence
                ],
            }
            for c in cases
        ],
        "runs": runs,
    }
    record.update(_score(record))
    return record


def recompute(record: dict) -> list[str]:
    """Recompute every metric from the record's rankings; list each stored value that differs."""

    fresh = _score(record)
    mismatches: list[str] = []
    for part, label in (("scores", "{case} {method} {mode}"), ("summary", "{method} {mode} summary")):
        stored_rows, fresh_rows = record[part], fresh[part]
        if len(stored_rows) != len(fresh_rows):
            mismatches.append(f"{part}: {len(stored_rows)} stored rows, {len(fresh_rows)} recomputed")
        for stored, new in zip(stored_rows, fresh_rows, strict=False):
            name = label.format(**new)
            mismatches += [
                f"{name}: stored {key} {stored.get(key)}, recomputed {value}"
                for key, value in new.items()
                if stored.get(key) != value
            ]
    return mismatches


_SETTINGS = ("token_budget", "model_limit", "k", "methods", "modes", "bm25", "rrf_k")


def compare_records(before: dict, after: dict) -> dict:
    """Compare two run records case by case and method by method.

    Lists every setting that differs (it should be none: only the corpus may change), the
    passage identities removed, added or changed (same ID, different text or context), the
    evidence items whose covering passages moved, and per case, method and mode the metrics
    before and after with a label: improved, regressed or mixed on Evidence Recall@5 and MRR@5,
    unchanged, unchanged failure (recall 0 both times), or no evidence items.
    """

    differ = [] if before["k"] == after["k"] else ["k"]
    if _case_settings(before) != _case_settings(after):
        differ.append("cases")
    old_config = before.get("run", {}).get("configuration", {})
    new_config = after.get("run", {}).get("configuration", {})
    differ += [key for key in _SETTINGS if key != "k" and old_config.get(key) != new_config.get(key)]

    def identity(record: dict) -> dict:
        return {p["passage_id"]: (p["text_sha256"], p.get("context_sha256"))
                for p in record["passages"]}

    old_ids, new_ids = identity(before), identity(after)
    passages = {
        "removed": sorted(set(old_ids) - set(new_ids)),
        "added": sorted(set(new_ids) - set(old_ids)),
        "changed": sorted(pid for pid in set(old_ids) & set(new_ids)
                          if old_ids[pid] != new_ids[pid]),
        "unchanged": sum(1 for pid in set(old_ids) & set(new_ids)
                         if old_ids[pid] == new_ids[pid]),
    }
    evidence = [
        {"case": old["id"], "item": n, "before": a["covering_passages"],
         "after": b["covering_passages"]}
        for old, new in zip(before["cases"], after["cases"], strict=False)
        for n, (a, b) in enumerate(zip(old["evidence"], new["evidence"], strict=False), start=1)
        if a["covering_passages"] != b["covering_passages"]
    ]
    later = {(s["case"], s["method"], s["mode"]): s for s in after["scores"]}
    cases = []
    for old in before["scores"]:
        new = later[(old["case"], old["method"], old["mode"])]
        cases.append({
            "case": old["case"], "method": old["method"], "mode": old["mode"],
            "change": _change(old, new),
            **{metric: [old[metric], new[metric]] for metric in
               ("evidence_recall", "mrr", "wrong_edition", "both_edition_coverage")},
        })
    summaries = {(s["method"], s["mode"]): s for s in after["summary"]}
    summary = [
        {"method": s["method"], "mode": s["mode"],
         **{key: [value, summaries[(s["method"], s["mode"])][key]]
            for key, value in s.items() if key not in ("method", "mode")}}
        for s in before["summary"]
    ]
    return {"settings_differ": differ, "passages": passages, "evidence": evidence,
            "cases": cases, "summary": summary}


def _case_settings(record: dict) -> list:
    return [
        (c["id"], c["question"], c["target_editions"],
         [(e["edition"], e["page"], e["quote"]) for e in c["evidence"]])
        for c in record["cases"]
    ]


def _change(old: dict, new: dict) -> str:
    if old["evidence_recall"] is None:
        return "no evidence items"
    pairs = [(old[m], new[m]) for m in ("evidence_recall", "mrr")]
    up = any(b > a for a, b in pairs)
    down = any(b < a for a, b in pairs)
    if up and down:
        return "mixed"
    if up or down:
        return "improved" if up else "regressed"
    return "unchanged failure" if new["evidence_recall"] == 0 else "unchanged"


def _score(record: dict) -> dict:
    k = record["k"]
    edition_of = {p["passage_id"]: p["edition"] for p in record["passages"]}
    cases = {c["id"]: c for c in record["cases"]}
    scores: list[dict] = []
    grouped: dict[tuple[str, str], list[CaseScore]] = {}
    for run in record["runs"]:
        c = cases[run["case"]]
        score = case_metrics(
            top=[pid for pid, _ in run["ranking"][:k]],
            covers=[set(item["covering_passages"]) for item in c["evidence"]],
            item_editions=[item["edition"] for item in c["evidence"]],
            target_editions=c["target_editions"],
            corpus_editions=record["corpus_editions"],
            edition_of=edition_of,
        )
        scores.append({"case": run["case"], "method": run["method"], "mode": run["mode"],
                       **asdict(score)})
        grouped.setdefault((run["method"], run["mode"]), []).append(score)
    summary = [
        {"method": method, "mode": mode, **asdict(aggregate(group))}
        for (method, mode), group in grouped.items()
    ]
    return {"scores": scores, "summary": summary}


def load_cases(path: Path, built: Corpus) -> tuple[Case, ...]:
    """Read the case file and check every evidence item against ``built``."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    problems: list[str] = []
    cases: list[Case] = []
    for raw in data["cases"]:
        cid = raw["id"]
        targets = tuple(raw["target_editions"])
        problems += [
            f"{cid}: target edition {e} has no commentary in the corpus"
            for e in targets
            if e not in built.editions
        ]
        items: list[Evidence] = []
        for item in raw["evidence"]:
            evidence = Evidence(item["edition"], int(item["page"]), normalize(item["quote"]))
            problem = _check(cid, evidence, targets, built)
            if problem:
                problems.append(problem)
            items.append(evidence)
        cases.append(Case(cid, raw["question"], targets, tuple(items)))
    if problems:
        raise CaseError(problems)
    return tuple(cases)


def covering(evidence: Evidence, built: Corpus) -> list[str]:
    """IDs of the passages that cover ``evidence``."""

    return [
        p.passage_id
        for p in built.passages
        if p.edition == evidence.edition and p.page == evidence.page and evidence.quote in p.text
    ]


def _check(cid: str, evidence: Evidence, targets: tuple[str, ...], built: Corpus) -> str | None:
    quoted = f"quote '{evidence.quote}'"
    if evidence.edition not in targets:
        return f"{cid}: evidence edition {evidence.edition} is not a target edition of the case"
    pages = sorted(
        page
        for page in {p.page for p in built.passages if p.edition == evidence.edition}
        if evidence.quote in _page_text(built, evidence.edition, page)
    )
    if evidence.page not in pages:
        if pages:
            found = ", ".join(str(p) for p in pages)
            return (
                f"{cid}: {quoted} is not on {evidence.edition} page {evidence.page} "
                f"(found on page {found})"
            )
        return f"{cid}: {quoted} is not in the {evidence.edition} commentary"
    if not covering(evidence, built):
        return f"{cid}: {quoted} is on {evidence.edition} page {evidence.page} but in no single passage"
    return None


def _page_text(built: Corpus, edition: str, page: int) -> str:
    return " ".join(p.text for p in built.passages if p.edition == edition and p.page == page)
