"""Offline tests for the Phase 4 training-data inventory (rules fixed in
docs/evidence/2026-11-23-phase4-training-data-inventory.md).

Synthetic passages and tiny generated PDFs only: no BAG document, model, tokenizer or network.

    uv run --project services/ingestion --frozen --offline --extra ai --extra dev \\
        python -m pytest tools/commentary_rag -q
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import corpus
import training_inventory as ti
from test_corpus import make_repo, words


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
        corpus.Document(e, f"{e}.pdf", "0" * 64, None, None, 4) for e in editions
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
