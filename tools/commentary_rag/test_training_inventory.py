"""Offline tests for the Phase 4 training-data inventory (rules fixed in
docs/evidence/2026-11-23-phase4-training-data-inventory.md).

Synthetic passages and tiny generated PDFs only: no BAG document, model, tokenizer or network.

    uv run --project services/ingestion --frozen --offline --extra ai --extra dev \\
        python -m pytest tools/commentary_rag -q
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import re
import sys
import types
from collections.abc import Iterable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import corpus
import training_inventory as ti
from test_corpus import make_repo, words
from test_corpus import JOINT, REGULAR, URGENT, make_sources


def passage(pid: str, text: str, title: str = "Titel") -> corpus.Passage:
    """A passage with the ID scheme of the corpus builder: <edition>/p<page>/s<section>/<n>."""

    edition, page, section, _ = pid.split("/")
    return corpus.Passage(
        passage_id=pid,
        edition=edition,
        document_sha256="0" * 64,
        source_url=None,
        page=int(page[1:]),
        page_label=None,
        section=section[1:],
        section_title=title,
        text=text,
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        tokens=len(text.split()),
        split="whole",
    )


def build(*passages: corpus.Passage) -> corpus.Corpus:
    editions = sorted({p.edition for p in passages})
    documents = tuple(
        corpus.Document(e, f"{e}.pdf", hashlib.sha256(e.encode()).hexdigest(), None, None, 4)
        for e in editions
    )
    excluded = tuple(
        corpus.ExcludedPage(e, 2, corpus.TABLE_OF_CONTENTS) for e in editions
    )
    return corpus.Corpus(documents, tuple(passages), excluded, 256, 512)


INTRO = "Dieses Dokument enthält Erläuterungen zu den im Titel genannten Änderungen."
REFERENCE = build(
    passage("2026-01-01/p3/s1/1", INTRO + " Position 5555.00.", "Einleitung"),
    passage(
        "2026-07-01/p6/s2.5/1",
        "Position 1368.00: der Tarif bleibt im Projekt transAL-2.",
    ),
    passage(
        "2026-07-01/p7/s2.6/1",
        "Das Handbuch zur Analysenliste wird aktualisiert, Position 5555.20.",
    ),
)


def older(*extra: corpus.Passage) -> corpus.Corpus:
    return build(
        passage("2024-01-01/p3/s1/1", INTRO, "Einleitung"),
        passage(
            "2024-01-01/p3/s2.1/1",
            "Position 1368.00 wird erweitert, siehe auch 9999.00.",
        ),
        passage("2024-01-01/p4/s2.2/1", "Die Position 9999.00 bleibt unverändert."),
        passage(
            "2024-01-01/p4/s2.3/1", "Position 4444.00 neu. Im Handbuch steht die Regel."
        ),
        passage("2024-07-01/p3/s2.1/1", "Position 4444.00 wird präzisiert."),
        passage("2024-07-01/p4/s3.1/1", "Im Rahmen des Projektes transAL-2 revidiert."),
        passage(
            "2024-07-01/p5/s4.1/1", "Geschlechtergerechte Sprache in der Analysenliste."
        ),
        passage(
            "2024-07-01/p5/s4.2/1",
            "Redaktionelle Anpassung der Positionen [Pos-Nr. 5555.00 ff.].",
        ),
        *extra,
    )


def test_codes_take_only_explicit_position_codes():
    assert ti.codes("Positionen 1700 «INR», 1700.00 und 6241.55; Seite 3") == {
        "1700.00",
        "6241.55",
    }


def test_projects_follow_the_fixed_lexicon():
    text = "Projekt transAL und das Projekt transAL-2; der Runden Tisches; Strategie (StAR)."
    assert ti.projects(text) == {"transAL", "Runder Tisch", "StAR"}
    apart = ti.projects(text, ti.Options(phases_apart=True))
    assert apart == {"transAL", "transAL-2", "Runder Tisch", "StAR"}
    assert ti.projects("Strategie Antibiotikaresistenzen") == {"StAR"}
    assert (
        ti.projects("Massnahmen zur Kostendämpfung, eine Pilotstudie, das Handbuch")
        == set()
    )
    assert ti.projects("Handbuch der Analysenliste", ti.Options(handbook=True)) == {
        "AL handbook"
    }


def test_range_overlaps_reach_series_and_wildcards():
    reference = {"6206.60", "6206.50", "6207.00", "6241.55", "6241.56"}
    assert ti.range_overlaps("[Pos-Nr. 6206.55 ff.]", reference) == {"6206.60"}
    assert ti.range_overlaps("Positionen xxxx.55 Nukleinsäure", reference) == {
        "6241.55"
    }
    assert ti.range_overlaps("Position 6206.55 allein", reference) == set()


def test_families_link_transitively_and_keep_singletons():
    sections = {
        "2024-01-01/2.1": ({"1000.00"}, set()),
        "2024-01-01/2.2": ({"1000.00", "2000.00"}, set()),
        "2024-07-01/2.1": ({"2000.00"}, set()),
        "2024-07-01/3.1": (set(), {"transAL"}),
        "2025-01-01/4.1": (set(), set()),
        "2025-07-01/2.10": (set(), {"transAL"}),
    }
    assert ti.families(sections) == [
        ["2024-01-01/2.1", "2024-01-01/2.2", "2024-07-01/2.1"],
        ["2024-07-01/3.1", "2025-07-01/2.10"],
        ["2025-01-01/4.1"],
    ]


def test_count_drops_whole_families_before_counting():
    result = ti.count(older(), REFERENCE, misfiled=())
    by_section = {s: f for f in result["families"] for s in f["sections"]}
    linked = by_section["2024-01-01/2.1"]
    assert linked["sections"] == [
        "2024-01-01/2.1",
        "2024-01-01/2.2",
    ]  # 9999.00 links them
    assert linked["excluded"] and linked["shared_codes"] == ["1368.00"]
    assert linked["reference_sections"] == ["2026-07-01/2.5"]
    assert by_section["2024-07-01/3.1"]["shared_projects"] == ["transAL"]
    kept = by_section["2024-01-01/2.3"]
    assert (
        kept["sections"] == ["2024-01-01/2.3", "2024-07-01/2.1"]
        and not kept["excluded"]
    )
    # the reference introduction names 5555.00, but introductions are not 2026 material
    assert not by_section["2024-07-01/4.2"]["excluded"]
    overall = result["counts"]["overall"]
    assert overall == {
        "passages": 8,
        "introduction_passages": 1,
        "usable_passages": 7,
        "misfiled_passages": 0,
        "duplicate_passages": 0,
        "families": 5,
        "eligible_families": 3,
        "eligible_passages": 4,
        "excluded_families": 2,
        "excluded_passages": 3,
    }
    january = result["counts"]["by_edition"]["2024-01-01"]
    assert january["eligible_passages"] == 1 and january["eligible_families"] == 1
    assert result["threshold"] == {
        "min_passages": 100,
        "min_families": 10,
        "met": False,
        "shortfall_passages": 96,
        "shortfall_families": 7,
    }
    intro = next(
        p for p in result["passages"] if p["passage_id"] == "2024-01-01/p3/s1/1"
    )
    assert intro["introduction"] and intro["family"] is None and not intro["usable"]


def test_sensitivities_move_in_the_expected_direction():
    base = ti.count(older(), REFERENCE, misfiled=())["counts"]["overall"]
    ranges = ti.count(older(), REFERENCE, ti.Options(ranges=True), misfiled=())
    assert (
        ranges["counts"]["overall"]["eligible_passages"]
        == base["eligible_passages"] - 1
    )
    handbook = ti.count(older(), REFERENCE, ti.Options(handbook=True), misfiled=())
    assert (
        handbook["counts"]["overall"]["eligible_passages"]
        == base["eligible_passages"] - 2
    )
    apart = ti.count(older(), REFERENCE, ti.Options(phases_apart=True), misfiled=())
    assert apart["counts"]["overall"]["eligible_passages"] == base["eligible_passages"]
    open_ = ti.count(older(), REFERENCE, ti.Options(no_exclusion=True), misfiled=())
    assert open_["counts"]["overall"]["eligible_passages"] == 7


def test_misfiled_text_keeps_a_passage_only_when_it_names_nothing():
    note = "1 Vgl. das Faktenblatt zur Unterteilung."
    extra = passage("2024-07-01/p6/s4.3/1", "Position 3333.00 neu. " + note)
    harmless = ti.Misfiled("2024-07-01/p6/s4.3/1", "4.2", note, "footnote 1")
    primary = ti.count(older(extra), REFERENCE, misfiled=(harmless,))
    row = next(p for p in primary["passages"] if p["passage_id"] == extra.passage_id)
    assert row["misfiled"] == ["4.2"] and row["usable"] and row["eligible"]
    strict = ti.count(
        older(extra), REFERENCE, ti.Options(strict_misfiled=True), misfiled=(harmless,)
    )
    row = next(p for p in strict["passages"] if p["passage_id"] == extra.passage_id)
    assert not row["usable"]
    coded = passage(
        "2024-07-01/p6/s4.3/1", "Position 3333.00 neu. 1 Vgl. Position 7777.00."
    )
    naming = ti.Misfiled(
        "2024-07-01/p6/s4.3/1", "4.2", "1 Vgl. Position 7777.00.", "footnote 1"
    )
    row = next(
        p
        for p in ti.count(older(coded), REFERENCE, misfiled=(naming,))["passages"]
        if p["passage_id"] == coded.passage_id
    )
    assert not row["usable"]
    with pytest.raises(ValueError, match="not found"):
        ti.count(
            older(),
            REFERENCE,
            misfiled=(ti.Misfiled("2024-01-01/p4/s2.2/1", "2.1", "x y", "?"),),
        )


def test_duplicates_find_same_and_overlapping_text():
    words8 = "eins zwei drei vier fünf sechs sieben acht neun zehn"
    ref = build(
        passage("2026-07-01/p3/s2.1/1", words8), passage("2026-07-01/p3/s1/1", INTRO)
    )
    old = build(
        passage("2024-01-01/p3/s1/1", INTRO),
        passage("2024-01-01/p3/s2.1/1", words8 + " elf zwölf"),
        passage(
            "2024-01-01/p3/s2.2/1",
            "ganz anderer Text ohne Bezug zu irgendetwas hier und dort",
        ),
        passage("2024-01-01/p3/s2.3/1", "kurz"),
    )
    found = ti.duplicates(old.passages, ref.passages)
    assert found == [
        {
            "passage_id": "2024-01-01/p3/s1/1",
            "reference_passage_id": "2026-07-01/p3/s1/1",
            "same_text": True,
            "share_of_8grams": 1.0,
        },
        {
            "passage_id": "2024-01-01/p3/s2.1/1",
            "reference_passage_id": "2026-07-01/p3/s2.1/1",
            "same_text": False,
            "share_of_8grams": 0.6,
        },
    ]


def test_report_lists_every_sensitivity_and_is_deterministic():
    first = ti.report(older(), REFERENCE, misfiled=())
    assert set(first["sensitivities"]) == set(ti.SENSITIVITIES)
    assert first["sensitivities"]["primary"]["eligible_passages"] == 4
    assert json.dumps(first, sort_keys=True) == json.dumps(
        ti.report(older(), REFERENCE, misfiled=()), sort_keys=True
    )


PAGES = [
    ["Kommentar zu den Änderungen", "per 1. Januar 2024"],
    ["Inhaltsverzeichnis", "1.", "Einleitung", "Seite 2 von 3"],
    [
        "1.",
        "Einleitung",
        "Dieses Dokument enthält Erläuterungen.",
        "2.1 Position 1368.00 Screening",
        "Die Position 1368.00 wird erweitert.",
        "2.2 Position 4444.00 Neu",
        "Die Position 4444.00 ist neu.",
        "Seite 3 von 3",
    ],
]
REF_PAGES = [
    ["Kommentar zu den Änderungen", "per 1. Juli 2026"],
    [
        "1.",
        "Einleitung",
        "Dieses Dokument enthält Erläuterungen.",
        "2.5 Position 1368.00 Screening",
        "Der Tarif wird erhöht.",
        "Seite 2 von 2",
    ],
]


def test_run_builds_both_corpora_and_refuses_a_changed_reference(tmp_path):
    older_manifest = make_repo(tmp_path / "older", {"2024-01-01": PAGES})
    reference_manifest = make_repo(tmp_path / "reference", {"2026-07-01": REF_PAGES})
    rebuilt = corpus.build_corpus(
        reference_manifest,
        count_passage_tokens=words,
        token_budget=256,
        model_limit=512,
    )
    record = tmp_path / "record.json"
    record.write_text(
        json.dumps(
            {
                "passages": [
                    {"passage_id": p.passage_id, "text_sha256": p.text_sha256}
                    for p in rebuilt.passages
                ]
            }
        ),
        encoding="utf-8",
    )
    result = ti.run(older_manifest, reference_manifest, record, words, 512, misfiled=())
    assert result["primary"]["counts"]["overall"]["eligible_passages"] == 1
    assert result["reference"]["passages"] == len(rebuilt.passages)
    assert result["reference"]["matches_record"] is True
    record.write_text(
        json.dumps({"passages": [{"passage_id": "x", "text_sha256": "y"}]})
    )
    with pytest.raises(SystemExit, match="frozen record"):
        ti.run(older_manifest, reference_manifest, record, words, 512, misfiled=())


def test_a_copy_of_2026_text_is_never_eligible_even_in_a_family_that_stays():
    copied = "Der Tarif der Position wird bis zum Abschluss des Projekts erhöht und neu geprüft"
    reference = build(*REFERENCE.passages, passage("2026-07-01/p8/s4.1/1", copied))
    extra = passage("2024-07-01/p6/s4.3/1", "Position 3333.00. " + copied)
    result = ti.count(older(extra), reference, misfiled=())
    row = next(p for p in result["passages"] if p["passage_id"] == extra.passage_id)
    assert row["usable"] and not row["eligible"]
    assert row["duplicate_of"] == "2026-07-01/p8/s4.1/1"
    family = next(f for f in result["families"] if "2024-07-01/4.3" in f["sections"])
    assert not family["excluded"]  # the copy alone keeps it out
    assert result["counts"]["overall"]["duplicate_passages"] == 1
    assert result["counts"]["overall"]["eligible_passages"] == 4


def test_every_inspection_finding_counts_and_lost_text_is_never_usable():
    text = "Position 3333.00 neu. 1 Vgl. das Faktenblatt. 2 Vgl. Position 7777.00."
    extra = passage("2024-07-01/p6/s4.3/1", text)
    harmless = ti.Misfiled(
        extra.passage_id, "4.2", "1 Vgl. das Faktenblatt.", "footnote 1"
    )
    naming = ti.Misfiled(
        extra.passage_id, "4.1", "2 Vgl. Position 7777.00.", "footnote 2"
    )
    for order in ((harmless, naming), (naming, harmless)):
        result = ti.count(older(extra), REFERENCE, misfiled=order)
        row = next(p for p in result["passages"] if p["passage_id"] == extra.passage_id)
        assert row["misfiled"] == ["4.1", "4.2"] and not row["usable"]
    lost = ti.Unusable("2024-01-01/p4/s2.3/1", "text garbled")
    result = ti.count(older(), REFERENCE, misfiled=(), unusable=(lost,))
    row = next(p for p in result["passages"] if p["passage_id"] == lost.passage_id)
    assert (
        row["unusable"] == "text garbled" and not row["usable"] and not row["eligible"]
    )
    with pytest.raises(ValueError, match="not found"):
        ti.count(
            older(), REFERENCE, misfiled=(), unusable=(ti.Unusable("x/p1/s1/1", "?"),)
        )


def test_main_never_replaces_an_existing_record(tmp_path):
    out = tmp_path / "record.json"
    out.write_text("kept", encoding="utf-8")
    with pytest.raises(SystemExit, match="already exists"):
        ti.main(["--out", str(out)])
    assert out.read_text(encoding="utf-8") == "kept"


class MissingModel:
    """The sentence_transformers boundary when the model is not in the cache: with Hugging Face
    offline, loading raises an OSError instead of downloading."""

    attempts: list[str] = []

    def __init__(self, name: str) -> None:
        MissingModel.attempts.append(
            f"{name} offline={os.environ.get('HF_HUB_OFFLINE')}"
        )
        raise OSError(
            f"couldn't find {name} in the cached files (offline mode is enabled)"
        )


@pytest.mark.parametrize(
    ("boundary", "reason"),
    [
        ("model_files_missing", "the cached e5 model could not be loaded (OSError"),
        ("package_missing", "fell back to the 16-dim stub"),
    ],
)
def test_main_refuses_without_the_cached_model_and_downloads_nothing(
    tmp_path, monkeypatch, boundary, reason
):
    from huggingface_hub import constants  # noqa: PLC0415 - as the documented command sets it
    from tarifhub_ingest.embeddings import embedder  # noqa: PLC0415

    monkeypatch.setattr(constants, "HF_HUB_OFFLINE", True)
    for name in (
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
    ):  # set here, so teardown restores
        monkeypatch.setenv(name, "0")  # them; main must turn offline mode on itself
    MissingModel.attempts = []
    fake = types.ModuleType("sentence_transformers")
    fake.SentenceTransformer = MissingModel
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        fake if boundary == "model_files_missing" else None,
    )
    embedder._cached_embedder.cache_clear()
    out = tmp_path / "record.json"
    try:
        with pytest.raises(SystemExit, match="refused") as refused:
            ti.main(["--out", str(out)])
    finally:
        embedder._cached_embedder.cache_clear()
    assert reason in str(refused.value)
    assert MissingModel.attempts == (
        ["intfloat/multilingual-e5-large offline=1"]
        if boundary == "model_files_missing"
        else []
    )
    assert not out.exists()



# The older commentaries: views keyed by source ID, the merge with the baseline and the
# eligibility it changes.

LINKED = (
    # shares 4444.00 with the baseline family 2024-01-01/2.3 and 2024-07-01/2.1
    passage("2022-07-01/p3/s2.1/1", "Die Positionen 4444.00 und 7777.00 werden zusammengelegt."),
    # linked to the section above through 7777.00; shares 5555.20 with 2026
    passage("2022-07-01/p3/s2.2/1", "Position 7777.00 wird neu mit 5555.20 abgerechnet."),
)
SAME_DATE = (
    passage("2023-01-01/p2/s2.1/1", "Position 6666.00 ist neu."),
    passage("2023-01-01-urgent/p2/s2.1/1", "Position 8888.00 wird dringend angepasst."),
)


def older_sources(*extra: corpus.Passage) -> corpus.Corpus:
    return build(*LINKED, *SAME_DATE, *extra)


def combine(
    baseline: corpus.Corpus | None = None, extra: corpus.Corpus | None = None, **findings
) -> dict:
    """``ti.views`` of the synthetic baseline and older sources, without inspection findings
    unless given."""

    findings = {"misfiled": (), "unusable": (), "subsections": (), "unresolved": ()} | findings
    return ti.views(
        older() if baseline is None else baseline,
        older_sources() if extra is None else extra,
        REFERENCE,
        **findings,
    )


def test_a_family_eligible_alone_is_dropped_when_older_sections_link_it_to_2026():
    out = combine()

    baseline = out["views"]["baseline"]["primary"]
    combined = out["views"]["combined"]["primary"]
    alone = next(f for f in baseline["families"] if "2024-01-01/2.3" in f["sections"])
    assert alone["sections"] == ["2024-01-01/2.3", "2024-07-01/2.1"] and not alone["excluded"]
    merged = next(f for f in combined["families"] if "2024-01-01/2.3" in f["sections"])
    assert merged["sections"] == [
        "2022-07-01/2.1",
        "2022-07-01/2.2",
        "2024-01-01/2.3",
        "2024-07-01/2.1",
    ]
    assert merged["excluded"] and merged["shared_codes"] == ["5555.20"]
    assert out["eligibility_changes"]["baseline"] == {
        "passages": [
            {
                "passage_id": pid,
                "alone_family": alone["id"],
                "combined_family": merged["id"],
                "alone_eligible": True,
                "combined_eligible": False,
            }
            for pid in ("2024-01-01/p4/s2.3/1", "2024-07-01/p3/s2.1/1")
        ],
        "families": [
            {
                "alone_family": alone["id"],
                "alone_sections": alone["sections"],
                "combined_family": merged["id"],
                "combined_sections": merged["sections"],
                "added_sections": ["2022-07-01/2.1", "2022-07-01/2.2"],
                "alone_excluded": False,
                "combined_excluded": True,
                "excluding_codes": ["5555.20"],
                "excluding_projects": [],
                "linking_codes": ["4444.00", "7777.00"],
                "linking_projects": [],
            }
        ],
    }
    assert baseline["counts"]["overall"]["eligible_passages"] == 4
    # two baseline passages remain eligible, and the two older sources of 1 January 2023
    assert combined["counts"]["overall"]["eligible_passages"] == 4
    assert list(combined["counts"]["by_edition"]) == [
        "2022-07-01",
        "2023-01-01",
        "2023-01-01-urgent",
        "2024-01-01",
        "2024-07-01",
    ]
    assert out["note"] == ti.SOURCE_NOTE and "source ID" in out["note"]


def test_the_older_view_counts_its_own_families_by_source_id():
    view = combine()["views"]["older"]

    primary = view["primary"]
    assert [(f["sections"], f["excluded"]) for f in primary["families"]] == [
        (["2022-07-01/2.1", "2022-07-01/2.2"], True),
        (["2023-01-01/2.1"], False),
        (["2023-01-01-urgent/2.1"], False),
    ]
    by_source = primary["counts"]["by_edition"]
    assert {k: (v["passages"], v["eligible_passages"]) for k, v in by_source.items()} == {
        "2022-07-01": (2, 0),
        "2023-01-01": (1, 1),
        "2023-01-01-urgent": (1, 1),
    }
    assert [d["source_id"] for d in view["documents"]] == list(by_source)
    assert view["unresolved"] == []


def test_the_baseline_view_is_the_report_of_the_baseline_alone():
    alone = ti.report(older(), REFERENCE, misfiled=(), sensitivities=ti.OLDER_SENSITIVITIES)

    view = combine()["views"]["baseline"]

    assert set(view) == set(alone) | {"subsections", "unresolved"}
    assert {
        k: v for k, v in view.items() if k not in ("documents", "subsections", "unresolved")
    } == {
        k: v for k, v in alone.items() if k != "documents"
    }
    new_keys = ("source_id", "effective_dates", "declared_title")
    assert [
        {"edition": row["source_id"], **{k: v for k, v in row.items() if k not in new_keys}}
        for row in view["documents"]
    ] == alone["documents"]
    assert [(row["effective_dates"], row["declared_title"]) for row in view["documents"]] == [
        (["2024-01-01"], None),
        (["2024-07-01"], None),
    ]


def test_a_finding_applies_only_to_the_views_holding_its_source():
    note = "Sprache in der Analysenliste."
    harmless = ti.Misfiled("2024-07-01/p5/s4.1/1", "4.2", note, "footnote 1")

    out = combine(misfiled=(harmless,))

    for name in ("baseline", "combined"):
        view = out["views"][name]
        assert [m["passage_id"] for m in view["misfiled"]] == [harmless.passage_id]
        row = next(
            p for p in view["primary"]["passages"] if p["passage_id"] == harmless.passage_id
        )
        assert row["misfiled"] == ["4.2"] and row["usable"]
    assert out["views"]["older"]["misfiled"] == []


@pytest.mark.parametrize(
    ("findings", "problem"),
    [
        ({"misfiled": (ti.Misfiled("2023-01-01/p2/s2.1/1", "2.2", "nicht da", "?"),)},
         "misfiled text of 2023-01-01/p2/s2.1/1 not found in that passage"),
        ({"misfiled": (ti.Misfiled("2023-01-01/p2/s2.1/2", "2.2", "Position", "?"),)},
         "2023-01-01/p2/s2.1/2: passage not found in its source"),
        ({"unusable": (ti.Unusable("2023-01-01-urgent/p9/s2.1/1", "?"),)},
         "2023-01-01-urgent/p9/s2.1/1: passage not found in its source"),
        ({"unusable": (ti.Unusable("2019-01-01/p2/s2.1/1", "?"),)},
         "2019-01-01/p2/s2.1/1: its source is in none of the views"),
        ({"unresolved": (ti.Unresolved("2020-01-01", "?"),)},
         "unresolved source 2020-01-01 is in none of the views"),
    ],
)
def test_a_finding_whose_passage_or_source_is_missing_is_refused(findings, problem):
    with pytest.raises(ValueError, match="refused") as refused:
        combine(**findings)

    assert problem in str(refused.value)


def test_an_unresolved_source_is_left_out_of_every_count_and_grouping_and_listed():
    unclear = passage(
        "2021-07-01/p2/s2.1/1", "Position 4444.00 und Position 1368.00 im Projekt transAL."
    )
    extra = build(*SAME_DATE, unclear)
    counted = combine(extra=extra)  # counted, it would link the 4444.00 family to 2026
    assert [p["passage_id"] for p in counted["eligibility_changes"]["baseline"]["passages"]] == [
        "2024-01-01/p4/s2.3/1",
        "2024-07-01/p3/s2.1/1",
    ]

    out = combine(extra=extra, unresolved=(ti.Unresolved("2021-07-01", "reading order unclear"),))

    listed = [{"source_id": "2021-07-01", "reason": "reading order unclear"}]
    assert out["unresolved"] == listed
    assert [out["views"][n]["unresolved"] for n in ("baseline", "older", "combined")] == [
        [],
        listed,
        listed,
    ]
    for name in ("older", "combined"):
        view = out["views"][name]
        primary = view["primary"]
        assert "2021-07-01" not in primary["counts"]["by_edition"]
        assert not [p for p in primary["passages"] if p["edition"] == "2021-07-01"]
        assert not [s for f in primary["families"] for s in f["sections"] if s[:10] == "2021-07-01"]
        # the document is still listed, with its hash, under its source ID
        assert "2021-07-01" in [d["source_id"] for d in view["documents"]]
    # three older passages less the unresolved one; the combined view adds the baseline's eight
    assert [
        out["views"][n]["primary"]["counts"]["overall"]["passages"] for n in ("older", "combined")
    ] == [2, 10]
    assert out["eligibility_changes"] == {
        name: {"passages": [], "families": []} for name in ("baseline", "older")
    }


def test_merge_orders_sources_by_first_date_and_refuses_collisions():
    baseline, extra = older(), older_sources()

    merged = ti.merge(baseline, extra)

    assert [d.edition for d in merged.documents] == [
        "2022-07-01",
        "2023-01-01",
        "2023-01-01-urgent",
        "2024-01-01",
        "2024-07-01",
    ]
    assert merged.passages == (*extra.passages, *baseline.passages)
    assert [e.edition for e in merged.excluded_pages] == [d.edition for d in merged.documents]
    assert ti.merge(extra, baseline) == merged
    with pytest.raises(ValueError, match="source ID 2024-01-01, 2024-07-01 occurs more than once"):
        ti.merge(baseline, older())
    stray = corpus.Corpus(
        (corpus.Document("2023-03-01", "2023-03-01.pdf", "1" * 64, None, None, 2),),
        (passage("2023-01-01/p2/s2.1/1", "Position 6666.00 ist neu."),),
        (),
        256,
        512,
    )
    with pytest.raises(ValueError, match="passage ID 2023-01-01/p2/s2.1/1 occurs more than once"):
        ti.merge(extra, stray)
    with pytest.raises(ValueError, match="token budget and model limit differ"):
        ti.merge(baseline, dataclasses.replace(extra, token_budget=128))


def test_eligibility_changes_are_checked_not_assumed():
    baseline = older()
    combined = ti.merge(baseline, older_sources())
    before = ti.count(baseline, REFERENCE, misfiled=())
    after = ti.count(combined, REFERENCE, misfiled=())
    assert len(ti.eligibility_changes(baseline, combined, before, after)["passages"]) == 2

    risen = copy.deepcopy(after)
    next(p for p in risen["passages"] if p["passage_id"] == "2024-01-01/p3/s2.1/1")[
        "eligible"
    ] = True
    with pytest.raises(ValueError, match="2024-01-01/p3/s2.1/1 became eligible"):
        ti.eligibility_changes(baseline, combined, before, risen)
    fallen = copy.deepcopy(after)
    next(p for p in fallen["passages"] if p["passage_id"] == "2024-07-01/p5/s4.1/1")[
        "eligible"
    ] = False
    with pytest.raises(ValueError, match="2024-07-01/p5/s4.1/1 lost eligibility in a family"):
        ti.eligibility_changes(baseline, combined, before, fallen)


def frozen(tmp_path: Path, reference_manifest: Path) -> Path:
    """A frozen record of the rebuilt reference: its passage IDs and text hashes."""

    rebuilt = corpus.build_corpus(
        reference_manifest, count_passage_tokens=words, token_budget=256, model_limit=512
    )
    record = tmp_path / "frozen.json"
    record.write_text(
        json.dumps(
            {
                "passages": [
                    {"passage_id": p.passage_id, "text_sha256": p.text_sha256}
                    for p in rebuilt.passages
                ]
            }
        ),
        encoding="utf-8",
    )
    return record


def test_run_views_reads_three_manifests_and_counts_each_source_once(tmp_path):
    older_manifest = make_repo(tmp_path / "older", {"2024-01-01": PAGES})
    sources = make_sources(
        tmp_path / "sources",
        [
            ("2023-01-01-urgent", ["2023-01-01"], URGENT),
            ("2023-01-01", ["2023-01-01"], REGULAR),
            ("2022-01-01", ["2022-01-01", "2022-02-01"], JOINT),
        ],
    )
    reference_manifest = make_repo(tmp_path / "reference", {"2026-07-01": REF_PAGES})
    record = frozen(tmp_path, reference_manifest)

    def run() -> dict:
        return ti.run_views(
            older_manifest, sources, reference_manifest, record, words, 512,
            misfiled=(), unusable=(), subsections=(), unresolved=(),
        )

    result = run()

    assert set(result) == {
        "rules", "note", "views", "eligibility_changes", "unresolved", "reference", "inputs"
    }
    assert list(result["views"]) == ["baseline", "older", "combined"]
    combined = result["views"]["combined"]
    by_source = combined["primary"]["counts"]["by_edition"]
    # the two sources of 1 January 2023 count apart; the joint source counts once
    assert {k: v["passages"] for k, v in by_source.items()} == {
        "2022-01-01": 1,
        "2023-01-01": 1,
        "2023-01-01-urgent": 1,
        "2024-01-01": 3,
    }
    assert list(by_source) == ["2022-01-01", "2023-01-01", "2023-01-01-urgent", "2024-01-01"]
    sections = {s for f in combined["primary"]["families"] for s in f["sections"]}
    assert {"2022-01-01/2.1", "2023-01-01/2.1", "2023-01-01-urgent/2.1"} <= sections
    assert [(d["source_id"], d["effective_dates"]) for d in combined["documents"]] == [
        ("2022-01-01", ["2022-01-01", "2022-02-01"]),
        ("2023-01-01", ["2023-01-01"]),
        ("2023-01-01-urgent", ["2023-01-01"]),
        ("2024-01-01", ["2024-01-01"]),
    ]
    assert result["views"]["older"]["primary"]["counts"]["overall"]["eligible_passages"] == 3
    assert result["reference"]["matches_record"] is True
    assert set(result["inputs"]) == {
        "manifest",
        "older_commentaries_manifest",
        "reference_manifest",
        "frozen_record",
        "token_budget",
        "model_limit",
    }
    record.write_text(json.dumps({"passages": []}), encoding="utf-8")
    with pytest.raises(SystemExit, match="frozen record"):
        run()


RECORDED = ti.HERE / "results" / "2026-11-23-training-inventory.json"


def keys(rows: Iterable[dict]) -> set[frozenset]:
    return {frozenset(row) for row in rows}


def test_run_without_older_commentaries_keeps_the_recorded_structure(tmp_path):
    recorded = json.loads(RECORDED.read_text(encoding="utf-8"))
    older_manifest = make_repo(tmp_path / "older", {"2024-01-01": PAGES})
    reference_manifest = make_repo(tmp_path / "reference", {"2026-07-01": REF_PAGES})

    result = ti.run(
        older_manifest, reference_manifest, frozen(tmp_path, reference_manifest), words, 512,
        misfiled=(),
    )

    assert set(result) == set(recorded) - {"environment"}
    primary, kept = result["primary"], recorded["primary"]
    assert set(primary) == set(kept)
    assert set(primary["counts"]) == set(kept["counts"])
    assert set(primary["counts"]["overall"]) == set(kept["counts"]["overall"])
    assert keys(primary["counts"]["by_edition"].values()) == keys(
        kept["counts"]["by_edition"].values()
    )
    assert set(primary["threshold"]) == set(kept["threshold"])
    for name in ("families", "passages"):
        assert keys(primary[name]) == keys(kept[name])
    for name in ("documents", "duplicates"):
        assert keys(result[name]) == keys(recorded[name])
    assert set(result["sensitivities"]) == set(recorded["sensitivities"])
    assert keys(result["sensitivities"].values()) == keys(recorded["sensitivities"].values())
    assert set(result["inputs"]) == set(recorded["inputs"])
    assert set(result["reference"]) == set(recorded["reference"])
    note = "1 Vgl. das Faktenblatt zur Unterteilung."
    extra = passage("2024-07-01/p6/s4.3/1", "Position 3333.00 neu. " + note)
    misfiled = ti.Misfiled(extra.passage_id, "4.2", note, "footnote 1")
    alone = ti.report(older(extra), REFERENCE, misfiled=(misfiled,))
    assert set(alone) == set(recorded) - {"environment", "inputs", "reference"}
    assert keys(alone["misfiled"]) == keys(recorded["misfiled"])


def test_main_with_older_commentaries_never_replaces_an_existing_record(tmp_path):
    out = tmp_path / "record.json"
    out.write_text("kept", encoding="utf-8")

    with pytest.raises(SystemExit, match="already exists"):
        ti.main(["--out", str(out), "--older-commentaries", str(tmp_path / "sources.json")])

    assert out.read_text(encoding="utf-8") == "kept"


def test_main_with_older_commentaries_refuses_without_the_cached_model(tmp_path, monkeypatch):
    from huggingface_hub import constants  # noqa: PLC0415 - as the documented command sets it
    from tarifhub_ingest.embeddings import embedder  # noqa: PLC0415

    monkeypatch.setattr(constants, "HF_HUB_OFFLINE", True)
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        monkeypatch.setenv(name, "0")  # main must turn offline mode on itself
    MissingModel.attempts = []
    fake = types.ModuleType("sentence_transformers")
    fake.SentenceTransformer = MissingModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)
    embedder._cached_embedder.cache_clear()
    out = tmp_path / "record.json"
    try:
        with pytest.raises(SystemExit, match="the cached e5 model could not be loaded"):
            ti.main(["--out", str(out), "--older-commentaries", str(tmp_path / "sources.json")])
    finally:
        embedder._cached_embedder.cache_clear()
    assert MissingModel.attempts == ["intfloat/multilingual-e5-large offline=1"]
    assert not out.exists()



# Printed subsections that the parser files under their parent section (Subsection), the two
# readings of them in the views mode, and the transAL spelling of text extraction.

COMBINED = (
    # the parser misses the headings "2.1." and "2.2." and files both under section 2
    passage(
        "2022-01-01/p2/s2/1",
        "2. Änderungen der AL 2.1. Position 1111.00 wird neu aufgenommen.",
        "Änderungen der AL",
    ),
    passage("2022-01-01/p3/s2/1", "2.2. Position 1368.00 wird angepasst.", "Änderungen der AL"),
    passage("2023-03-01/p2/s2.1/1", "Position 1111.00 wird präzisiert."),
)
PRINTED = (
    ti.Subsection(
        "2022-01-01/p2/s2/1",
        "2.1",
        "2.1. Position 1111.00 wird neu aufgenommen.",
        'printed heading "2.1." with a trailing dot, which the parser does not read',
    ),
    ti.Subsection(
        "2022-01-01/p3/s2/1",
        "2.2",
        "2.2. Position 1368.00 wird angepasst.",
        'printed heading "2.2." with a trailing dot, which the parser does not read',
    ),
)
PRINTED_ONLY = ti.Options(printed_sections=True)


def rows_of(result: dict) -> dict[str, dict]:
    return {row["passage_id"]: row for row in result["passages"]}


def test_printed_sections_keep_a_subsection_shared_with_2026_from_dropping_its_sibling():
    old = build(*COMBINED)

    primary = ti.count(old, REFERENCE, misfiled=(), subsections=PRINTED)
    printed = ti.count(old, REFERENCE, PRINTED_ONLY, misfiled=(), subsections=PRINTED)

    # As the parser files it, section 2 names 1111.00 and 1368.00: the 2026 code drops the
    # whole family, the 2023 section that shares 1111.00 included.
    dropped = next(f for f in primary["families"] if "2023-03-01/2.1" in f["sections"])
    assert dropped["sections"] == ["2022-01-01/2", "2023-03-01/2.1"] and dropped["excluded"]
    assert primary["counts"]["overall"]["eligible_passages"] == 0
    # By printed sections, only 2.2 shares 1368.00; 2.1 and its sibling family stay.
    by_section = {s: f for f in printed["families"] for s in f["sections"]}
    kept = by_section["2022-01-01/2.1"]
    assert kept["sections"] == ["2022-01-01/2.1", "2023-03-01/2.1"] and not kept["excluded"]
    assert by_section["2022-01-01/2.2"]["sections"] == ["2022-01-01/2.2"]
    assert by_section["2022-01-01/2.2"]["excluded"]
    assert "2022-01-01/2" not in by_section  # its heading-only rest names nothing
    rows = rows_of(printed)
    assert [rows[p.passage_id]["eligible"] for p in COMBINED] == [True, False, True]
    assert kept["passages"] == 2 and kept["usable_passages"] == 2
    overall = printed["counts"]["overall"]
    assert (overall["eligible_passages"], overall["eligible_families"]) == (2, 1)


def test_a_passage_straddling_printed_subsections_of_two_families_is_not_eligible():
    straddling = passage(
        "2022-07-01/p2/s2/1",
        "2. Inhaltliche Änderungen 2.1. Position 5551.00 neu. 2.2. Position 6666.00 neu.",
        "Inhaltliche Änderungen",
    )
    following = passage(
        "2022-07-01/p3/s2/1", "2.2. Position 6666.00 bleibt.", "Inhaltliche Änderungen"
    )
    marks = (
        ti.Subsection(straddling.passage_id, "2.1", "2.1. Position 5551.00 neu.", "heading"),
        ti.Subsection(straddling.passage_id, "2.2", "2.2. Position 6666.00 neu.", "heading"),
        ti.Subsection(following.passage_id, "2.2", "2.2. Position 6666.00 bleibt.", "heading"),
    )
    old = build(straddling, following)

    printed = ti.count(old, REFERENCE, PRINTED_ONLY, misfiled=(), subsections=marks)

    rows = rows_of(printed)
    split = rows[straddling.passage_id]
    assert split["usable"] and not split["eligible"] and split["family"] is None
    assert not split["introduction"]
    assert rows[following.passage_id]["eligible"]
    families = {tuple(f["sections"]): f for f in printed["families"]}
    assert families[("2022-07-01/2.1",)]["passages"] == 0  # its one passage is split
    assert families[("2022-07-01/2.2",)]["passages"] == 1  # each passage once
    overall = printed["counts"]["overall"]
    assert (overall["eligible_passages"], overall["eligible_families"]) == (1, 1)
    # As the parser files it, section 2 is one family and both passages are eligible.
    primary = ti.count(old, REFERENCE, misfiled=(), subsections=marks)
    assert primary["counts"]["overall"]["eligible_passages"] == 2


def test_a_heading_only_rest_decides_nothing_and_a_rest_naming_a_code_decides():
    heading_only = passage(
        "2023-07-01/p2/s2/1", "2. Änderungen der AL 2.1. Position 7777.00 neu.", "Änderungen der AL"
    )
    naming = passage(
        "2023-07-01/p3/s2/1",
        "Hinweis zu Position 8888.00. 2.2. Position 9990.00 neu.",
        "Änderungen der AL",
    )
    unnamed = passage(
        "2023-03-01/p2/s2/1", "2. Änderungen 2.1. Die Liste wird angepasst.", "Änderungen"
    )
    marks = (
        ti.Subsection(heading_only.passage_id, "2.1", "2.1. Position 7777.00 neu.", "heading"),
        ti.Subsection(naming.passage_id, "2.2", "2.2. Position 9990.00 neu.", "heading"),
        ti.Subsection(unnamed.passage_id, "2.1", "2.1. Die Liste wird angepasst.", "label"),
    )

    printed = ti.count(
        build(heading_only, naming, unnamed), REFERENCE, PRINTED_ONLY, misfiled=(), subsections=marks
    )

    rows = rows_of(printed)
    by_section = {s: f["id"] for f in printed["families"] for s in f["sections"]}
    # "2. Änderungen der AL" names nothing: the fragment 2.1 alone decides
    assert rows[heading_only.passage_id]["family"] == by_section["2023-07-01/2.1"]
    assert rows[heading_only.passage_id]["eligible"]
    # a rest that names 8888.00 counts under section 2 and decides with the fragment 2.2
    assert sorted(s for s in by_section if s.startswith("2023-07-01")) == [
        "2023-07-01/2",
        "2023-07-01/2.1",
        "2023-07-01/2.2",
    ]
    assert rows[naming.passage_id]["family"] is None and not rows[naming.passage_id]["eligible"]
    # nothing named anywhere: the Subsection fragment decides
    assert rows[unnamed.passage_id]["family"] == by_section["2023-03-01/2.1"]
    assert "2023-03-01/2" not in by_section and rows[unnamed.passage_id]["eligible"]


def test_subsections_misfiled_drops_a_passage_whose_subsection_text_names_a_code_or_project():
    coded = passage("2022-01-01/p2/s2/1", "2. Änderungen 2.1. Position 1111.00 neu.", "Änderungen")
    project = passage(
        "2022-01-01/p3/s2/1", "2.2. Die Revision folgt im Projekt transAL2.", "Änderungen"
    )
    plain = passage("2023-03-01/p2/s2/1", "2. Änderungen 2.1. Die Liste wird angepasst.", "Änderungen")
    marks = (
        ti.Subsection(coded.passage_id, "2.1", "2.1. Position 1111.00 neu.", "heading"),
        ti.Subsection(project.passage_id, "2.2", "2.2. Die Revision folgt im Projekt transAL2.", "h"),
        ti.Subsection(plain.passage_id, "2.1", "2.1. Die Liste wird angepasst.", "label"),
    )
    old = build(coded, project, plain)

    strict = ti.count(old, REFERENCE, ti.Options(subsections_misfiled=True), misfiled=(), subsections=marks)

    rows = rows_of(strict)
    assert not rows[coded.passage_id]["usable"] and not rows[project.passage_id]["usable"]
    assert rows[plain.passage_id]["usable"] and rows[plain.passage_id]["eligible"]
    # the families stay as the parser files them
    primary = ti.count(old, REFERENCE, misfiled=(), subsections=marks)
    assert [f["sections"] for f in strict["families"]] == [f["sections"] for f in primary["families"]]
    assert all(rows_of(primary)[p.passage_id]["usable"] for p in (coded, plain))


def test_subsections_change_neither_the_primary_count_nor_an_existing_sensitivity():
    old = build(*COMBINED)

    for name, options in ti.SENSITIVITIES.items():
        assert ti.count(old, REFERENCE, options, misfiled=(), subsections=PRINTED) == ti.count(
            old, REFERENCE, options, misfiled=()
        ), name
    with_marks = ti.report(old, REFERENCE, misfiled=(), subsections=PRINTED)
    assert with_marks == ti.report(old, REFERENCE, misfiled=())
    assert list(with_marks["sensitivities"]) == list(ti.SENSITIVITIES)


FRAGMENTED = passage(
    "2022-01-01/p2/s2/1",
    "2. Änderungen 2.1. Position 1111.00 neu. 2.2. Position 2222.00 neu.",
    "Änderungen",
)
DEEPER = passage("2022-01-01/p3/s2.1/1", "Position 3333.00 neu.")


@pytest.mark.parametrize(
    ("marks", "problem"),
    [
        pytest.param(
            (ti.Subsection("2022-01-01/p9/s2/1", "2.1", "2.1.", "?"),),
            "subsection text of 2022-01-01/p9/s2/1 not found in that passage",
            id="no-passage",
        ),
        pytest.param(
            (ti.Subsection(FRAGMENTED.passage_id, "2.1", "2.1. Position 9999.00", "?"),),
            "subsection text of 2022-01-01/p2/s2/1 not found in that passage",
            id="no-text",
        ),
        pytest.param(
            (ti.Subsection(FRAGMENTED.passage_id, "3.1", "2.1. Position 1111.00 neu.", "?"),),
            "2022-01-01/p2/s2/1: 3.1 is not a subsection of its parser section 2",
            id="other-section",
        ),
        pytest.param(
            (ti.Subsection(FRAGMENTED.passage_id, "2", "2.1. Position 1111.00 neu.", "?"),),
            "2 is not a subsection of its parser section 2",
            id="the-section-itself",
        ),
        pytest.param(
            (ti.Subsection(FRAGMENTED.passage_id, "2.a", "2.1. Position 1111.00 neu.", "?"),),
            "2.a is not a subsection of its parser section 2",
            id="not-a-number",
        ),
        pytest.param(
            (ti.Subsection(DEEPER.passage_id, "2.10", "Position 3333.00 neu.", "?"),),
            "2.10 is not a subsection of its parser section 2.1",
            id="prefix-is-not-parent",
        ),
        pytest.param(
            (
                ti.Subsection(FRAGMENTED.passage_id, "2.1", "2.1. Position 1111.00 neu. 2.2.", "?"),
                ti.Subsection(FRAGMENTED.passage_id, "2.2", "2.2. Position 2222.00 neu.", "?"),
            ),
            "subsection text of 2022-01-01/p2/s2/1 (2.2) overlaps another subsection",
            id="overlapping",
        ),
    ],
)
def test_a_subsection_that_does_not_fit_its_passage_is_refused(marks, problem):
    with pytest.raises(ValueError) as refused:
        ti.count(build(FRAGMENTED, DEEPER), REFERENCE, misfiled=(), subsections=marks)

    assert problem in str(refused.value)


def test_a_deeper_printed_subsection_fits_its_parser_section():
    fits = ti.Subsection(DEEPER.passage_id, "2.1.1", "Position 3333.00 neu.", "heading")

    printed = ti.count(build(FRAGMENTED, DEEPER), REFERENCE, PRINTED_ONLY, misfiled=(), subsections=(fits,))

    assert ["2022-01-01/2.1.1"] in [f["sections"] for f in printed["families"]]


def test_views_apply_subsections_by_source_and_list_them_with_the_two_new_sensitivities():
    mark = ti.Subsection(
        FRAGMENTED.passage_id,
        "2.1",
        "2.1. Position 1111.00 neu.",
        'printed heading "2.1." with a trailing dot, which the parser does not read',
    )
    extra = older_sources(FRAGMENTED)

    out = combine(extra=extra, subsections=(mark,))

    listed = [
        {
            "passage_id": mark.passage_id,
            "section": "2.1",
            "found": mark.found,
            "names_codes": ["1111.00"],
            "names_projects": [],
        }
    ]
    assert [out["views"][n]["subsections"] for n in ("baseline", "older", "combined")] == [
        [],
        listed,
        listed,
    ]
    for name in ("baseline", "older", "combined"):
        assert list(out["views"][name]["sensitivities"]) == list(ti.OLDER_SENSITIVITIES)
    summary = out["views"]["older"]["sensitivities"]
    original = {
        "phases_apart": False,
        "handbook": False,
        "ranges": False,
        "strict_misfiled": False,
        "no_exclusion": False,
    }
    assert summary["primary"]["options"] == original
    assert summary["printed_sections"]["options"] == {**original, "printed_sections": True}
    assert summary["subsections_misfiled"]["options"] == {**original, "subsections_misfiled": True}
    # the primary count of every view ignores the mark
    plain = combine(extra=extra)
    for name in ("baseline", "older", "combined"):
        assert out["views"][name]["primary"] == plain["views"][name]["primary"]
    with pytest.raises(ValueError, match="2019-01-01/p2/s2/1: its source is in none of the views"):
        combine(subsections=(ti.Subsection("2019-01-01/p2/s2/1", "2.1", "x", "?"),))
    with pytest.raises(ValueError, match="3.1 is not a subsection of its parser section 2"):
        combine(extra=extra, subsections=(ti.Subsection(mark.passage_id, "3.1", mark.text, "?"),))


def test_the_extraction_spelling_transal2_is_transal_and_with_phases_apart_transal_2():
    assert ti.projects("im Projekt transAL2, danach transAL1") == {"transAL"}
    assert ti.projects("transAL2, transAL-1 und transAL", ti.Options(phases_apart=True)) == {
        "transAL-2",
        "transAL-1",
        "transAL",
    }
    assert ti.projects("transAL12 und transALX") == set()
    extra = passage("2024-07-01/p6/s4.3/1", "Die Revision folgt im Projekt transAL2.")

    for options, shared in ((None, ["transAL"]), (ti.Options(phases_apart=True), ["transAL-2"])):
        result = ti.count(older(extra), REFERENCE, options, misfiled=())
        family = next(f for f in result["families"] if "2024-07-01/4.3" in f["sections"])
        # linked to 2024-07-01/3.1 (transAL-2) and dropped with it: 2026 names transAL-2
        assert family["sections"] == ["2024-07-01/3.1", "2024-07-01/4.3"]
        assert family["excluded"] and family["shared_projects"] == shared


def test_the_original_mode_keeps_its_sensitivities_and_their_options(tmp_path):
    recorded = json.loads(RECORDED.read_text(encoding="utf-8"))
    older_manifest = make_repo(tmp_path / "older", {"2024-01-01": PAGES})
    reference_manifest = make_repo(tmp_path / "reference", {"2026-07-01": REF_PAGES})

    result = ti.run(
        older_manifest, reference_manifest, frozen(tmp_path, reference_manifest), words, 512,
        misfiled=(),
    )

    assert list(result["sensitivities"]) == list(ti.SENSITIVITIES)
    assert set(result["sensitivities"]) == set(recorded["sensitivities"])
    assert {n: s["options"] for n, s in result["sensitivities"].items()} == {
        n: s["options"] for n, s in recorded["sensitivities"].items()
    }
    assert result["primary"]["options"] == recorded["primary"]["options"]


def test_the_inspection_constants_are_well_formed():
    assert [u.source_id for u in ti.UNRESOLVED] == ["2021-02-01", "2021-07-01"]
    assert all(u.reason.startswith("no numbered heading: ") for u in ti.UNRESOLVED)
    for item in ti.SUBSECTIONS:
        source, page, section, n = item.passage_id.split("/")
        assert re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(-[a-z]+)*", source), item
        assert page[0] == "p" and section[0] == "s" and n.isdigit(), item
        assert re.fullmatch(rf"{re.escape(section[1:])}(\.[0-9]+)+", item.section), item
        assert item.text and item.found, item



def test_a_passage_whose_parts_lie_in_one_family_belongs_to_it_and_counts_once():
    linked = passage(
        "2023-07-01/p3/s2/3",
        "2.1 Position 3565.00 wird mit 3566.00 aufgenommen. 2.2 Position 6605.64 ersetzt 3566.00.",
        "Änderungen der AL",
    )
    with_rest = passage(
        "2023-07-01/p4/s2/1",
        "Hinweis zu Position 1419.00. 2.3 Position 1419.00 und 3188.10 neu.",
        "Änderungen der AL",
    )
    marks = (
        ti.Subsection(
            linked.passage_id, "2.1", "2.1 Position 3565.00 wird mit 3566.00 aufgenommen.", "h"
        ),
        ti.Subsection(linked.passage_id, "2.2", "2.2 Position 6605.64 ersetzt 3566.00.", "h"),
        ti.Subsection(with_rest.passage_id, "2.3", "2.3 Position 1419.00 und 3188.10 neu.", "h"),
    )

    printed = ti.count(
        build(linked, with_rest), REFERENCE, PRINTED_ONLY, misfiled=(), subsections=marks
    )

    rows = rows_of(printed)
    by_section = {s: f for f in printed["families"] for s in f["sections"]}
    # 2.1 and 2.2 share 3566.00: one family, which lists the passage once
    joined = by_section["2023-07-01/2.1"]
    assert joined["sections"] == ["2023-07-01/2.1", "2023-07-01/2.2"]
    assert rows[linked.passage_id]["family"] == joined["id"] and rows[linked.passage_id]["eligible"]
    assert (joined["passages"], joined["usable_passages"]) == (1, 1)
    # a rest naming its fragment's own code decides with it, in the same family
    with_section = by_section["2023-07-01/2.3"]
    assert with_section["sections"] == ["2023-07-01/2", "2023-07-01/2.3"]
    assert rows[with_rest.passage_id]["family"] == with_section["id"]
    assert rows[with_rest.passage_id]["eligible"] and with_section["passages"] == 1
    overall = printed["counts"]["overall"]
    assert (overall["eligible_passages"], overall["eligible_families"]) == (2, 2)


def test_an_older_passage_eligible_alone_that_joins_a_dropped_baseline_family_is_listed():
    late = passage("2022-07-01/p4/s3.1/1", "Position 9999.00 wird redaktionell angepasst.")
    out = combine(extra=older_sources(late))

    alone = rows_of(out["views"]["older"]["primary"])
    merged = rows_of(out["views"]["combined"]["primary"])
    assert alone[late.passage_id]["eligible"] and not merged[late.passage_id]["eligible"]
    changed = out["eligibility_changes"]["older"]["passages"]
    assert [(c["passage_id"], c["alone_eligible"], c["combined_eligible"]) for c in changed] == [
        (late.passage_id, True, False)
    ]
    family = alone[late.passage_id]["family"]
    joined = next(
        g for g in out["eligibility_changes"]["older"]["families"] if g["alone_family"] == family
    )
    assert joined["combined_excluded"] and joined["excluding_codes"] == ["1368.00"]
    assert "9999.00" in joined["linking_codes"]


def test_merge_refuses_the_same_document_under_two_source_ids():
    baseline = older()
    copy = baseline.documents[1]
    twin = corpus.Corpus(
        documents=(corpus.Document("2023-05-01", copy.path, copy.sha256, None, None, 4),),
        passages=(passage("2023-05-01/p3/s2.1/1", "Position 1234.00 neu."),),
        excluded_pages=(),
        token_budget=256,
        model_limit=512,
    )

    with pytest.raises(ValueError, match="document SHA-256 .* occurs more than once"):
        ti.merge(baseline, twin)


def test_a_source_that_yields_no_passage_must_be_listed_as_unresolved():
    blank = corpus.Document("2021-02-01", "2021-02-01.pdf", "f" * 64, None, None, 3)
    sources = older_sources()
    extra = corpus.Corpus(
        (*sources.documents, blank), sources.passages, sources.excluded_pages, 256, 512
    )

    with pytest.raises(ValueError, match="source 2021-02-01 yields no passage"):
        combine(extra=extra)
    out = combine(extra=extra, unresolved=(ti.Unresolved("2021-02-01", "no heading"),))
    assert out["unresolved"] == [{"source_id": "2021-02-01", "reason": "no heading"}]


def straddle(second: str) -> tuple[corpus.Corpus, tuple, corpus.Passage, corpus.Passage]:
    """A passage holding code-free 2.1 text and coded 2.2 text, beside one coded 2.1 passage."""

    title = "Inhaltliche Änderungen"
    first = passage("2023-07-01/p3/s2/1", "2.1 Neuaufnahme der Position 3565.00.", title)
    both = passage("2023-07-01/p3/s2/3", f"Die neuen Positionen gelten. {second}", title)
    marks = (
        ti.Subsection(first.passage_id, "2.1", "2.1 Neuaufnahme der Position 3565.00.", "h"),
        ti.Subsection(both.passage_id, "2.1", "Die neuen Positionen gelten.", "h"),
        ti.Subsection(both.passage_id, "2.2", second, "h"),
    )
    return build(first, both), marks, first, both


def test_a_code_free_subsection_fragment_decides_the_family_too():
    old, marks, first, both = straddle("2.2 Position 6605.64 wird befristet.")

    printed = ti.count(old, REFERENCE, PRINTED_ONLY, misfiled=(), subsections=marks)

    rows = rows_of(printed)
    assert rows[first.passage_id]["eligible"]
    assert rows[both.passage_id]["family"] is None and not rows[both.passage_id]["eligible"]


def test_overall_families_count_a_family_whose_only_passage_is_split():
    old, marks, first, both = straddle("2.2 Position 1368.00 wird befristet.")

    printed = ti.count(old, REFERENCE, PRINTED_ONLY, misfiled=(), subsections=marks)

    overall = printed["counts"]["overall"]
    assert (overall["families"], overall["excluded_families"]) == (2, 1)
    assert (overall["eligible_passages"], overall["eligible_families"]) == (1, 1)
