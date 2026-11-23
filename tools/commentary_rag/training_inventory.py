"""Phase 4 training-data inventory: earlier BAG commentaries against the frozen 2026 corpus.

Implements the counting rules of ``docs/evidence/2026-11-23-phase4-training-data-inventory.md``,
fixed before any count. The earlier commentaries pinned in ``data/manifests/bag-al-2024-2025.json``
are parsed by the pilot's corpus builder unchanged; their non-introduction sections are grouped
into change families by shared position codes or named projects; every family that shares a code
or a project with the 2026 material is dropped as a whole; then the usable passages of the
remaining families are counted against the proposed threshold of 100 passages from 10 families.

Read-only and offline: the e5 tokenizer counts tokens for the 256-token budget, as for the frozen
corpus; nothing is embedded, no provider or network is used, and the frozen corpus and every
recorded result stay unchanged. Only public material is read (the BAG commentaries and the frozen
2026 record): no evaluation case, gold evidence or answer. The result record holds IDs, hashes,
codes, projects and counts, never passage text.

The e5 model is read from the local Hugging Face cache only (offline mode is forced and checked),
and an existing output file is never replaced:

    UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" uv run \\
        --project services/ingestion --frozen --offline --extra ai --extra dev \\
        python tools/commentary_rag/training_inventory.py --out <a new file>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import corpus

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OLDER = REPO / "data" / "manifests" / "bag-al-2024-2025.json"
REFERENCE = REPO / "data" / "manifests" / "bag-al.json"
RECORD = HERE / "results" / "2026-11-14-retrieval-corrected.json"
RULES = "docs/evidence/2026-11-23-phase4-training-data-inventory.md#rules-fixed-before-counting"
TOKEN_BUDGET = 256  # the frozen 2026 corpus's budget
MIN_PASSAGES = 100  # the proposed threshold: a design choice of this project
MIN_FAMILIES = 10

CODE = re.compile(r"\b(\d{4}\.\d{2})\b")
SERIES = re.compile(r"\b(\d{4})\.(\d{2})\s*ff\.")
WILDCARD = re.compile(r"\b[xX]{4}\.(\d{2})\b")
INTRODUCTION = "einleitung"
# Rule 5: the named projects with their spellings. transAL's phases share one name unless a
# sensitivity keeps them apart; the AL handbook is a document and counts only in its sensitivity.
PROJECTS = (
    ("transAL", re.compile(r"\btransAL(?:-[12])?\b")),
    ("Runder Tisch", re.compile(r"\bRunde[nr]?\s+Tisch(?:es)?\b")),
    ("StAR", re.compile(r"\bStrategie\s+Antibiotikaresistenzen\b|\bStAR\b")),
)
HANDBOOK = ("AL handbook", re.compile(r"\bHandbuch\w*"))
NGRAM = 8  # duplicate check: word 8-grams of an older passage found in one 2026 passage
NEAR_DUPLICATE = 0.5


@dataclass(frozen=True)
class Misfiled:
    """Text the page inspection found filed under a section it does not belong to."""

    passage_id: str
    belongs_to: str
    text: str
    found: str


@dataclass(frozen=True)
class Unusable:
    """A passage whose text the page inspection found lost or garbled (rule 3)."""

    passage_id: str
    reason: str


# Found by the page inspection of 2026-11-23 (pdfplumber layout probe and renders of all 21
# pages): one misfiled footnote, no text lost or garbled.
UNUSABLE: tuple[Unusable, ...] = ()
MISFILED = (
    Misfiled(
        passage_id="2025-01-01/p3/s2.3/1",
        belongs_to="2.1",
        text=(
            "1 Vgl. www.bag.admin.ch > Versicherungen Krankenversicherung > Leistungen und "
            "Tarife > Analysenliste (AL) > Dokumente > Faktenblatt vom Juli 2015 zur "
            "Unterteilung der Laboranalysen in Basis- und Spezialanalysen."
        ),
        found="footnote 1 of page 3, referenced in section 2.1, follows section 2.3 in the text",
    ),
)


@dataclass(frozen=True)
class Options:
    """One application of the rules: the primary count or one sensitivity."""

    phases_apart: bool = False  # transAL-1 and transAL-2 as two projects
    handbook: bool = False  # the AL handbook as a named item
    ranges: bool = (
        False  # 'A ff.' series and 'xxxx.dd' wildcards against the 2026 codes
    )
    strict_misfiled: bool = False  # drop every passage that carries misfiled text
    no_exclusion: bool = False  # the upper bound: no family is dropped


SENSITIVITIES = {
    "primary": Options(),
    "misfiled_strict": Options(strict_misfiled=True),
    "ranges": Options(ranges=True),
    "transal_phases_apart": Options(phases_apart=True),
    "handbook_named": Options(handbook=True),
    "strictest": Options(strict_misfiled=True, ranges=True, handbook=True),
    "no_exclusion": Options(no_exclusion=True),
}


def codes(text: str) -> set[str]:
    """Explicit position codes (``dddd.dd``), the frozen rule."""

    return set(CODE.findall(text))


def projects(text: str, options: Options | None = None) -> set[str]:
    """The named projects of rule 5 that ``text`` mentions."""

    options = options or Options()
    found = set()
    for name, pattern in PROJECTS:
        for match in pattern.finditer(text):
            found.add(
                match.group(0) if options.phases_apart and name == "transAL" else name
            )
    if options.handbook and HANDBOOK[1].search(text):
        found.add(HANDBOOK[0])
    return found


def range_overlaps(text: str, reference_codes: set[str]) -> set[str]:
    """The 2026 codes an ``A ff.`` series or an ``xxxx.dd`` wildcard in ``text`` reaches."""

    hits = set()
    for stem, decimals in SERIES.findall(text):
        start = f"{stem}.{decimals}"
        hits |= {c for c in reference_codes if c[:4] == stem and c >= start}
    for decimals in WILDCARD.findall(text):
        hits |= {c for c in reference_codes if c[5:] == decimals}
    return hits


def _order(key: str) -> tuple[str, tuple[int, ...]]:
    edition, number = key.split("/")
    return edition, tuple(int(part) for part in number.split("."))


def families(sections: Mapping[str, tuple[set[str], set[str]]]) -> list[list[str]]:
    """Group sections (key → codes, projects) that share a code or a project, transitively.

    A section with neither stays a family of its own. Families come in the order of their first
    section, each listing its sections in edition and section order.
    """

    keys = sorted(sections, key=_order)
    parent = {key: key for key in keys}

    def root(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    owner: dict[tuple[str, str], str] = {}
    for key in keys:
        found, named = sections[key]
        for item in sorted(
            {("code", c) for c in found} | {("project", p) for p in named}
        ):
            if item in owner:
                parent[root(key)] = root(owner[item])
            else:
                owner[item] = key
    groups: dict[str, list[str]] = defaultdict(list)
    for key in keys:
        groups[root(key)].append(key)
    return sorted(groups.values(), key=lambda group: _order(group[0]))


def _grams(text: str) -> set[tuple[str, ...]]:
    words = corpus.normalize(text).split(" ")
    return {tuple(words[i : i + NGRAM]) for i in range(len(words) - NGRAM + 1)}


def duplicates(
    older: Iterable[corpus.Passage], reference: Iterable[corpus.Passage]
) -> list[dict]:
    """Older passages whose text equals a 2026 passage or lies mostly inside one (rule 10)."""

    kept = [(p, _grams(p.text)) for p in reference]
    found = []
    for p in older:
        grams = _grams(p.text)
        for q, other in kept:
            same = p.text_sha256 == q.text_sha256
            share = len(grams & other) / len(grams) if grams else 0.0
            if same or share >= NEAR_DUPLICATE:
                found.append(
                    {
                        "passage_id": p.passage_id,
                        "reference_passage_id": q.passage_id,
                        "same_text": same,
                        "share_of_8grams": round(share, 4),
                    }
                )
    return found


def _key(p: corpus.Passage) -> str:
    if p.section is None:
        raise ValueError(
            f"{p.passage_id}: a passage without a section cannot be grouped"
        )
    return f"{p.edition}/{p.section}"


def _introduction(p: corpus.Passage) -> bool:
    return (p.section_title or "").strip().lower().startswith(INTRODUCTION)


def count(
    older: corpus.Corpus,
    reference: corpus.Corpus,
    options: Options | None = None,
    *,
    misfiled: Iterable[Misfiled] = MISFILED,
    unusable: Iterable[Unusable] = UNUSABLE,
) -> dict:
    """Apply rules 2 to 10 once: families, exclusion, usable and eligible passages, counts."""

    options = options or Options()
    by_id = {p.passage_id: p for p in older.passages}
    flagged: dict[str, list[Misfiled]] = defaultdict(list)
    for item in misfiled:
        if item.passage_id not in by_id or item.text not in by_id[item.passage_id].text:
            raise ValueError(
                f"misfiled text of {item.passage_id} not found in that passage"
            )
        flagged[item.passage_id].append(item)
    lost: dict[str, str] = {}
    for item in unusable:
        if item.passage_id not in by_id:
            raise ValueError(
                f"unusable passage {item.passage_id} not found in the corpus"
            )
        lost[item.passage_id] = item.reason
    copies = {
        found["passage_id"]: found["reference_passage_id"]
        for found in duplicates(older.passages, reference.passages)
    }

    ref_codes: set[str] = set()
    ref_projects: set[str] = set()
    where: dict[tuple[str, str], set[str]] = defaultdict(set)
    for p in reference.passages:
        if _introduction(p):
            continue
        for c in codes(p.text):
            ref_codes.add(c)
            where[("code", c)].add(_key(p))
        for name in projects(p.text, options):
            ref_projects.add(name)
            where[("project", name)].add(_key(p))

    section_codes: dict[str, set[str]] = defaultdict(set)
    section_projects: dict[str, set[str]] = defaultdict(set)
    members: dict[str, list[corpus.Passage]] = defaultdict(list)
    introductions = set()
    for p in older.passages:
        key = _key(p)
        members[key].append(p)
        section_codes[key] |= codes(p.text)
        section_projects[key] |= projects(p.text, options)
        if _introduction(p):
            introductions.add(key)
    grouped = families(
        {
            k: (section_codes[k], section_projects[k])
            for k in members
            if k not in introductions
        }
    )

    def usable(p: corpus.Passage) -> bool:
        """Rule 3: no introduction, no lost or garbled text, and misfiled text only when it
        names no code or project (none in the strict count)."""
        if _introduction(p) or p.passage_id in lost:
            return False
        items = flagged.get(p.passage_id, [])
        if items and options.strict_misfiled:
            return False
        return not any(codes(i.text) or projects(i.text, options) for i in items)

    family_of: dict[str, str] = {}
    rows = []
    for n, sections in enumerate(grouped, 1):
        name = f"F{n:02d}"
        passages = [p for s in sections for p in members[s]]
        found = set().union(*(section_codes[s] for s in sections))
        named = set().union(*(section_projects[s] for s in sections))
        shared_codes = found & ref_codes
        shared_projects = named & ref_projects
        reached = set()
        if options.ranges:
            for p in passages:
                reached |= range_overlaps(p.text, ref_codes)
        touched = set()
        for c in shared_codes | reached:
            touched |= where[("code", c)]
        for name_ in shared_projects:
            touched |= where[("project", name_)]
        excluded = not options.no_exclusion and bool(
            shared_codes or shared_projects or reached
        )
        for s in sections:
            family_of[s] = name
        rows.append(
            {
                "id": name,
                "sections": sections,
                "editions": sorted({s.split("/")[0] for s in sections}),
                "passages": len(passages),
                "usable_passages": sum(usable(p) for p in passages),
                "codes": sorted(found),
                "projects": sorted(named),
                "shared_codes": sorted(shared_codes),
                "shared_projects": sorted(shared_projects),
                "range_codes": sorted(reached),
                "reference_sections": sorted(touched, key=_order),
                "excluded": excluded,
            }
        )
    excluded_families = {r["id"] for r in rows if r["excluded"]}

    passages_out = []
    for p in older.passages:
        key = _key(p)
        family = family_of.get(key)
        ok = usable(p)
        passages_out.append(
            {
                "passage_id": p.passage_id,
                "edition": p.edition,
                "page": p.page,
                "section": p.section,
                "tokens": p.tokens,
                "split": p.split,
                "text_sha256": p.text_sha256,
                "introduction": _introduction(p),
                "misfiled": sorted(
                    {i.belongs_to for i in flagged.get(p.passage_id, [])}
                ),
                "unusable": lost.get(p.passage_id),
                "duplicate_of": copies.get(p.passage_id),
                "family": family,
                "usable": ok,
                "eligible": ok  # rule 8, and rule 10: a copy of 2026 text is never eligible
                and family is not None
                and family not in excluded_families
                and p.passage_id not in copies,
            }
        )

    def tally(rows_in: list[dict]) -> dict:
        fams = {r["family"] for r in rows_in if r["family"] is not None}
        eligible = [r for r in rows_in if r["eligible"]]
        return {
            "passages": len(rows_in),
            "introduction_passages": sum(r["introduction"] for r in rows_in),
            "usable_passages": sum(r["usable"] for r in rows_in),
            "misfiled_passages": sum(bool(r["misfiled"]) for r in rows_in),
            "duplicate_passages": sum(
                r["usable"] and r["duplicate_of"] is not None for r in rows_in
            ),
            "families": len(fams),
            "eligible_families": len({r["family"] for r in eligible}),
            "eligible_passages": len(eligible),
            "excluded_families": len(fams & excluded_families),
            "excluded_passages": sum(
                r["usable"] and r["family"] in excluded_families for r in rows_in
            ),
        }

    by_edition = {
        d.edition: tally([r for r in passages_out if r["edition"] == d.edition])
        for d in older.documents
    }
    overall = tally(passages_out)
    return {
        "options": options.__dict__,
        "reference_codes": len(ref_codes),
        "reference_projects": sorted(ref_projects),
        "families": rows,
        "passages": passages_out,
        "counts": {"by_edition": by_edition, "overall": overall},
        "threshold": {
            "min_passages": MIN_PASSAGES,
            "min_families": MIN_FAMILIES,
            "met": overall["eligible_passages"] >= MIN_PASSAGES
            and overall["eligible_families"] >= MIN_FAMILIES,
            "shortfall_passages": max(0, MIN_PASSAGES - overall["eligible_passages"]),
            "shortfall_families": max(0, MIN_FAMILIES - overall["eligible_families"]),
        },
    }


def report(
    older: corpus.Corpus,
    reference: corpus.Corpus,
    *,
    misfiled: Iterable[Misfiled] = MISFILED,
    unusable: Iterable[Unusable] = UNUSABLE,
) -> dict:
    """The primary count in full, every sensitivity in summary, and the duplicate check."""

    misfiled, unusable = tuple(misfiled), tuple(unusable)
    primary = count(older, reference, misfiled=misfiled, unusable=unusable)
    summary = {}
    for name, options in SENSITIVITIES.items():
        result = (
            primary
            if name == "primary"
            else count(older, reference, options, misfiled=misfiled, unusable=unusable)
        )
        overall = result["counts"]["overall"]
        summary[name] = {
            "options": options.__dict__,
            "eligible_passages": overall["eligible_passages"],
            "eligible_families": overall["eligible_families"],
            "excluded_families": overall["excluded_families"],
            "met": result["threshold"]["met"],
        }
    return {
        "rules": RULES,
        "documents": [
            {
                "edition": d.edition,
                "path": d.path,
                "sha256": d.sha256,
                "source_url": d.source_url,
                "title": d.title,
                "pages": d.page_count,
                "excluded_pages": [
                    {"page": e.page, "reason": e.reason}
                    for e in older.excluded_pages
                    if e.edition == d.edition
                ],
            }
            for d in older.documents
        ],
        "unusable": [
            {"passage_id": u.passage_id, "reason": u.reason} for u in unusable
        ],
        "misfiled": [
            {
                "passage_id": m.passage_id,
                "belongs_to": m.belongs_to,
                "found": m.found,
                "names_codes": sorted(codes(m.text)),
                "names_projects": sorted(projects(m.text)),
            }
            for m in misfiled
        ],
        "primary": primary,
        "sensitivities": summary,
        "duplicates": duplicates(older.passages, reference.passages),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(  # noqa: PLR0913 - the two manifests, the frozen record and the tokenizer
    older_manifest: Path,
    reference_manifest: Path,
    record: Path,
    count_tokens: Callable[[str], int],
    model_limit: int,
    pdftotext: str = "pdftotext",
    *,
    misfiled: Iterable[Misfiled] = MISFILED,
    unusable: Iterable[Unusable] = UNUSABLE,
) -> dict:
    """Build both corpora, check the 2026 rebuild against its frozen record, then report."""

    def build(manifest: Path) -> corpus.Corpus:
        return corpus.build_corpus(
            manifest,
            count_passage_tokens=count_tokens,
            token_budget=TOKEN_BUDGET,
            model_limit=model_limit,
            pdftotext=pdftotext,
        )

    older = build(older_manifest)
    reference = build(reference_manifest)
    recorded = [
        (p["passage_id"], p["text_sha256"])
        for p in json.loads(record.read_text(encoding="utf-8"))["passages"]
    ]
    rebuilt = [(p.passage_id, p.text_sha256) for p in reference.passages]
    if recorded != rebuilt:
        raise SystemExit(
            f"refused: the 2026 rebuild differs from the frozen record {record.name} "
            f"({len(rebuilt)} passages rebuilt, {len(recorded)} recorded)"
        )
    out = report(older, reference, misfiled=misfiled, unusable=unusable)
    out["reference"] = {
        "passages": len(reference.passages),
        "matches_record": True,
        "editions": [d.edition for d in reference.documents],
    }
    out["inputs"] = {
        "manifest": {
            "path": _relative(older_manifest),
            "sha256": _sha256(older_manifest),
        },
        "reference_manifest": {
            "path": _relative(reference_manifest),
            "sha256": _sha256(reference_manifest),
        },
        "frozen_record": {"path": _relative(record), "sha256": _sha256(record)},
        "token_budget": TOKEN_BUDGET,
        "model_limit": model_limit,
    }
    return out


def _relative(path: Path) -> str:
    resolved = path.resolve()
    return (
        resolved.relative_to(REPO).as_posix()
        if resolved.is_relative_to(REPO)
        else path.name
    )


def _e5_model():
    """The e5 model behind the passage-token counter, from the local Hugging Face cache only.

    Offline mode is forced before ``huggingface_hub`` is imported here and checked to hold, so a
    missing model is refused, never downloaded; so is the 16-dimensional stub fallback.
    """

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        from huggingface_hub import constants  # noqa: PLC0415
        import run_eval  # noqa: PLC0415 - the pilot's e5 loader and exact token counter
    except ImportError as exc:
        raise SystemExit(
            f"refused: {exc.name} is not installed; run with the ingestion ai extra"
        )
    if not constants.HF_HUB_OFFLINE:  # imported earlier, before offline mode was set
        raise SystemExit(
            "refused: Hugging Face offline mode is not in effect; set HF_HUB_OFFLINE=1 so that "
            "no model can be downloaded"
        )
    try:
        _, model = run_eval._e5()  # refuses the stub fallback
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - a model file or package missing, however it fails
        raise SystemExit(
            f"refused: the cached e5 model could not be loaded ({type(exc).__name__}: {exc}); "
            "nothing is downloaded"
        ) from None
    return run_eval, model


def main(argv: list[str] | None = None) -> int:
    """Run the inventory with the e5 tokenizer and write a new record (no text, no model call)."""

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--out", type=Path, required=True, help="the new JSON record to write"
    )
    args = parser.parse_args(argv)
    if args.out.exists():  # recorded inventories are evidence, never replaced
        raise SystemExit(
            f"refused: {args.out} already exists; write a new record instead"
        )
    run_eval, model = _e5_model()
    out = run(
        OLDER,
        REFERENCE,
        RECORD,
        run_eval._counter(model, "passage"),
        model.max_seq_length,
    )
    environment = run_eval._environment(model)
    status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            "tools/commentary_rag",
            "data/manifests",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    out["environment"] = {
        "python": environment["python"],
        "pdftotext": environment["pdftotext"],
        "packages": environment["packages"],
        "model": {
            k: environment["model"][k]
            for k in ("id", "cache_revision", "max_seq_length")
        },
        "git_head": environment["git_head"],
        "tool_files_uncommitted": bool(status),
        "tool_files_sha256": {
            name: _sha256(HERE / name)
            for name in ("training_inventory.py", "corpus.py")
        },
    }
    with open(
        args.out, "x", encoding="utf-8"
    ) as handle:  # never replaces an existing file
        handle.write(
            json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        )
    overall = out["primary"]["counts"]["overall"]
    print(
        f"eligible: {overall['eligible_passages']} passages in {overall['eligible_families']} "
        f"families (threshold met: {out['primary']['threshold']['met']}); wrote {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
