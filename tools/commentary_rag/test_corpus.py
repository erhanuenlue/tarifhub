"""Offline tests for the commentary corpus: manifest-verified PDF bytes to page-bounded passages.

Each test writes a tiny real PDF and a manifest into a temporary repository, so the manifest
loader, the hash check and pdftotext run end to end. Token counts come from a stand-in counter
(one token per word); the real e5 tokenizer is exercised in the recorded evaluation run.

    uv run --project services/ingestion --frozen --offline --extra ai --extra dev \\
        python -m pytest tools/commentary_rag -q
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import corpus
import retrieval

JUL = "2026-07-01"
JAN = "2026-01-01"


def make_pdf(pages: list[list[str]]) -> bytes:
    """A minimal valid PDF: one Helvetica text line per entry, top to bottom, per page."""

    def esc(line: str) -> bytes:
        raw = line.encode("cp1252")
        return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")

    page_ids = [4 + 2 * i for i in range(len(pages))]
    kids = " ".join(f"{p} 0 R" for p in page_ids)
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    for pid, lines in zip(page_ids, pages, strict=True):
        body = b"BT /F1 10 Tf 14 TL 56 790 Td " + b" ".join(
            b"(" + esc(line) + b") Tj T*" for line in lines
        ) + b" ET"
        objects[pid] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {pid + 1} 0 R >>"
        ).encode()
        objects[pid + 1] = f"<< /Length {len(body)} >>\nstream\n".encode() + body + b"\nendstream"
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objects[num] + b"\nendobj\n"
    xref = len(out)
    size = max(objects) + 1
    out += f"xref\n0 {size}\n0000000000 65535 f \n".encode()
    for num in range(1, size):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def make_repo(
    tmp_path: Path,
    commentaries: dict[str, list[list[str]] | None],
    *,
    tamper: frozenset[str] = frozenset(),
) -> Path:
    """Write the PDFs and a manifest under ``tmp_path``; return the manifest path.

    ``None`` lists an edition without a commentary_pdf. An edition in ``tamper`` gets a
    manifest hash that does not match its bytes.
    """

    editions = []
    for n, (edition, pages) in enumerate(sorted(commentaries.items())):
        documents = [
            {
                "kind": "full_list_xlsx",
                "path": f"data/raw/{edition}/list.xlsx",
                "sha256": f"{n:064x}",
            }
        ]
        if pages is not None:
            data = make_pdf(pages)
            relative = f"data/raw/{edition}/Kommentar {edition}.pdf"
            (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / relative).write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            if edition in tamper:
                digest = hashlib.sha256(b"other bytes " + edition.encode()).hexdigest()
            documents.append(
                {
                    "kind": "commentary_pdf",
                    "path": relative,
                    "sha256": digest,
                    "source_url": f"https://www.bag.admin.ch/dam/{edition}.pdf",
                }
            )
        editions.append({"effective_date": edition, "documents": documents})
    manifest = tmp_path / "data" / "manifests" / "test.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({"manifest_version": 1, "tariff_system": "EAL", "editions": editions}),
        encoding="utf-8",
    )
    return manifest


def words(text: str) -> int:
    """Stand-in token counter: one token per whitespace-separated word."""

    return len(text.split())


def build(manifest: Path, *, budget: int = 400, limit: int = 512) -> corpus.Corpus:
    return corpus.build_corpus(
        manifest, count_passage_tokens=words, token_budget=budget, model_limit=limit
    )


SIMPLE = [
    ["Kommentar zu den Änderungen", "per 1. Juli 2026"],
    ["2.1 Position 1779.00 PlGF", "Die Position 1779.00 ist neu.", "Seite 2 von 2"],
]


JULY_PAGES = [
    ["Bundesamt für Gesundheit BAG", "Kommentar zu den Änderungen des Anhangs 3 KLV vom",
     "9. Juni 2026 per 1. Juli 2026"],
    ["Inhaltsverzeichnis", "1.", "Einleitung", "3", "Seite 2 von 4"],
    ["1.", "Einleitung", "Dieses Dokument enthält Erläuterungen.",
     "2.1 Position 1779.00 PlGF", "Die Position 1779.00 ist nicht kumulierbar mit 1777.00.",
     "2.2 Position 1368.00 Neugeborenen-Screening", "Der Tarif wird erhöht.", "Seite 3 von 4"],
    ["Der Tarif bleibt bis 30. Juni 2028 in Evaluation.", "Seite 4 von 4"],
]
JANUARY_PAGES = [
    ["Kommentar zu den Änderungen des Anhangs 3 KLV vom", "2. Dezember 2025 per 1. Januar 2026"],
    ["2.2 Position 1619.00 Procalcitonin", "Der Tarif sinkt auf 63.3 TP.", "Seite 2 von 2"],
]


def test_passages_carry_edition_document_page_and_section_provenance(tmp_path):
    manifest = make_repo(tmp_path, {JUL: JULY_PAGES, JAN: JANUARY_PAGES})
    july_sha = hashlib.sha256(make_pdf(JULY_PAGES)).hexdigest()

    built = build(manifest)

    assert [(p.passage_id, p.page, p.page_label, p.section, p.section_title, p.text)
            for p in built.passages] == [
        ("2026-01-01/p2/s2.2/1", 2, "Seite 2 von 2", "2.2", "Position 1619.00 Procalcitonin",
         "2.2 Position 1619.00 Procalcitonin Der Tarif sinkt auf 63.3 TP."),
        ("2026-07-01/p3/s1/1", 3, "Seite 3 von 4", "1", "Einleitung",
         "1. Einleitung Dieses Dokument enthält Erläuterungen."),
        ("2026-07-01/p3/s2.1/1", 3, "Seite 3 von 4", "2.1", "Position 1779.00 PlGF",
         "2.1 Position 1779.00 PlGF Die Position 1779.00 ist nicht kumulierbar mit 1777.00."),
        ("2026-07-01/p3/s2.2/1", 3, "Seite 3 von 4", "2.2",
         "Position 1368.00 Neugeborenen-Screening",
         "2.2 Position 1368.00 Neugeborenen-Screening Der Tarif wird erhöht."),
        # A section continuing on the next page keeps its section; the page is the new one.
        ("2026-07-01/p4/s2.2/1", 4, "Seite 4 von 4", "2.2",
         "Position 1368.00 Neugeborenen-Screening",
         "Der Tarif bleibt bis 30. Juni 2028 in Evaluation."),
    ]
    july = [p for p in built.passages if p.edition == JUL]
    assert {(p.document_sha256, p.source_url) for p in july} == {
        (july_sha, f"https://www.bag.admin.ch/dam/{JUL}.pdf")
    }
    assert [(e.edition, e.page, e.reason) for e in built.excluded_pages] == [
        (JAN, 1, "front matter before the first section heading"),
        (JUL, 1, "front matter before the first section heading"),
        (JUL, 2, "table of contents"),
    ]
    assert [(d.edition, d.title, d.page_count) for d in built.documents] == [
        (JAN, "Kommentar zu den Änderungen des Anhangs 3 KLV vom 2. Dezember 2025 per 1. "
              "Januar 2026", 2),
        (JUL, "Kommentar zu den Änderungen des Anhangs 3 KLV vom 9. Juni 2026 per 1. Juli 2026",
         4),
    ]


def single_page(lines: list[str]) -> list[list[str]]:
    return [["Kommentar zu den Änderungen"], [*lines, "Seite 2 von 2"]]


def test_a_section_over_budget_splits_at_sentences_not_at_abbreviations_or_dates(tmp_path):
    lines = ["2.4 Tarif", "Vitamin B12 bzw. Cobalamin sinkt um 20 %.",
             "Ferritin sinkt per 1. Juli 2026 um 10 %.", "Die Gründe folgen."]
    manifest = make_repo(tmp_path, {JUL: single_page(lines)})

    built = build(manifest, budget=12)

    assert [(p.passage_id, p.text, p.tokens, p.split) for p in built.passages] == [
        ("2026-07-01/p2/s2.4/1", "2.4 Tarif Vitamin B12 bzw. Cobalamin sinkt um 20 %.", 10,
         "sentence"),
        ("2026-07-01/p2/s2.4/2", "Ferritin sinkt per 1. Juli 2026 um 10 %. Die Gründe folgen.",
         12, "sentence"),
    ]


TABLE = ["2.4 Tarif", "Die folgenden Positionen sind von der Kürzung betroffen:",
         "Bezeichnung", "Pos.-Nr.", "Kürzung um (in %)",
         "Vitamin D", "1006.00", "20",
         "Ferritin", "1314.00", "10",
         "C-reaktives Protein", "(CRP)", "1245.00", "10",
         "Die Gründe folgen."]
TABLE_HEAD = ("2.4 Tarif Die folgenden Positionen sind von der Kürzung betroffen: "
              "Bezeichnung Pos.-Nr. Kürzung um (in %)")


def test_a_table_that_fits_the_budget_stays_one_passage_with_its_heading(tmp_path):
    manifest = make_repo(tmp_path, {JUL: single_page(TABLE)})

    # 31 words in all: over the budget of 29, while the table with its heading is 28.
    built = build(manifest, budget=29)

    assert [(p.text, p.context, p.tokens, p.split) for p in built.passages] == [
        (f"{TABLE_HEAD} Vitamin D 1006.00 20 Ferritin 1314.00 10 "
         "C-reaktives Protein (CRP) 1245.00 10", None, 28, "table"),
        ("Die Gründe folgen.", None, 3, "whole"),
    ]


def test_each_part_of_a_split_table_carries_its_heading_and_column_names(tmp_path):
    manifest = make_repo(tmp_path, {JUL: single_page(TABLE)})

    built = build(manifest, budget=22)

    assert [(p.text, p.context, p.tokens, p.split) for p in built.passages] == [
        (f"{TABLE_HEAD} Vitamin D 1006.00 20", None, 20, "table"),
        ("Ferritin 1314.00 10", TABLE_HEAD, 19, "table"),
        ("C-reaktives Protein (CRP) 1245.00 10", TABLE_HEAD, 21, "table"),
        ("Die Gründe folgen.", None, 3, "whole"),
    ]
    # The texts are the page in order, nothing repeated; the context is verbatim page text.
    page_text = " ".join(p.text for p in built.passages)
    assert page_text == " ".join(TABLE)
    assert all(p.context is None or p.context in page_text for p in built.passages)
    assert {(p.edition, p.page) for p in built.passages} == {(JUL, 2)}
    assert all(p.tokens == words(p.indexed_text) <= 22 for p in built.passages)
    # The heading travels with every part, so the table's meaning still retrieves them.
    hits = retrieval.Retriever(built.passages).rank("Kürzung", method="bm25", editions=[JUL])
    assert {h.passage_id for h in hits[:3]} == {
        "2026-07-01/p2/s2.4/1", "2026-07-01/p2/s2.4/2", "2026-07-01/p2/s2.4/3"
    }
    assert hits[3].score == 0.0


def test_a_heading_without_text_of_its_own_never_becomes_a_passage(tmp_path):
    pages = [
        ["Kommentar"],
        ["2.", "Inhaltliche Änderungen", "2.1 Position 1779.00", "Text eins.",
         "3.", "Abgelehnte Anträge", "Seite 2 von 3"],
        ["3.1 GAAD", "Text zwei.", "Seite 3 von 3"],
    ]
    manifest = make_repo(tmp_path, {JUL: pages})

    built = build(manifest)

    # The heading joins the text it heads on the same page, verbatim and in page order.
    assert [(p.passage_id, p.section, p.text) for p in built.passages] == [
        ("2026-07-01/p2/s2.1/1", "2.1", "2. Inhaltliche Änderungen 2.1 Position 1779.00 Text eins."),
        ("2026-07-01/p3/s3.1/1", "3.1", "3.1 GAAD Text zwei."),
    ]
    # A heading at the foot of a page cannot join text on the next page; it is recorded.
    assert (JUL, 2, "heading without text on this page: 3. Abgelehnte Anträge") in [
        (e.edition, e.page, e.reason) for e in built.excluded_pages
    ]
    hits = retrieval.Retriever(built.passages).rank(
        "Inhaltliche Änderungen", method="bm25", editions=[JUL]
    )
    assert hits[0].passage_id == "2026-07-01/p2/s2.1/1"


def test_a_compound_abbreviation_such_as_pos_nr_does_not_end_a_sentence(tmp_path):
    # Split wrongly after "Pos.-Nr.", "Die Pos.-Nr." would pack into the first passage.
    lines = ["2.4 Tarif", "Erster Satz hier.", "Die Pos.-Nr. Spalte nennt die Position."]
    manifest = make_repo(tmp_path, {JUL: single_page(lines)})

    built = build(manifest, budget=8)

    assert [p.text for p in built.passages] == [
        "2.4 Tarif Erster Satz hier.",
        "Die Pos.-Nr. Spalte nennt die Position.",
    ]


def test_a_sentence_over_budget_splits_at_words_and_no_text_is_lost(tmp_path):
    codes = "6203.56, 6203.60, 6204.56, 6204.60, 6205.56, 6205.61"
    manifest = make_repo(tmp_path, {JUL: single_page(["2.3 Liste", codes])})

    built = build(manifest, budget=4)

    assert [(p.text, p.tokens, p.split) for p in built.passages] == [
        ("2.3 Liste 6203.56, 6203.60,", 4, "word"),
        ("6204.56, 6204.60, 6205.56, 6205.61", 4, "word"),
    ]
    assert " ".join(p.text for p in built.passages) == f"2.3 Liste {codes}"


def test_refuses_a_budget_above_the_model_limit_and_a_word_the_tokenizer_cannot_fit(tmp_path):
    manifest = make_repo(tmp_path, {JUL: single_page(["2.3 Liste", "kurz UNTEILBAR kurz"])})

    with pytest.raises(corpus.CorpusError, match="token budget 600 exceeds the model limit 512"):
        build(manifest, budget=600, limit=512)

    def counter(text: str) -> int:
        return 999 if "UNTEILBAR" in text else len(text.split())

    with pytest.raises(corpus.CorpusError) as refused:
        corpus.build_corpus(
            manifest, count_passage_tokens=counter, token_budget=10, model_limit=512
        )
    assert "page 2, section 2.3: 999 tokens in one word" in str(refused.value)


def test_one_refusal_names_every_missing_commentary(tmp_path):
    manifest = make_repo(tmp_path, {JAN: None, JUL: SIMPLE})
    (tmp_path / f"data/raw/{JUL}/Kommentar {JUL}.pdf").unlink()

    with pytest.raises(corpus.CorpusError) as refused:
        build(manifest)

    assert refused.value.problems == (
        f"edition {JAN} lists 0 commentary_pdf documents; expected 1",
        f"data/raw/{JUL}/Kommentar {JUL}.pdf: file not found",
    )


def test_refuses_a_printed_page_number_that_contradicts_the_pdf_page(tmp_path):
    pages = [["Kommentar"], ["2.1 Position", "Text.", "Seite 3 von 2"]]
    manifest = make_repo(tmp_path, {JUL: pages})

    with pytest.raises(corpus.CorpusError, match="PDF page 2 of 2 is printed as 'Seite 3 von 2'"):
        build(manifest)


def test_refuses_a_commentary_whose_bytes_do_not_match_the_manifest_hash(tmp_path):
    manifest = make_repo(tmp_path, {JUL: SIMPLE}, tamper=frozenset({JUL}))

    with pytest.raises(corpus.CorpusError) as refused:
        build(manifest)

    assert "sha256 mismatch" in str(refused.value)
    assert f"Kommentar {JUL}.pdf" in str(refused.value)



# A commentary-source manifest keys each PDF by a source ID, so that commentaries sharing an
# effective date, or covering two, stay apart (corpus.build_commentaries).


def source_entries(
    tmp_path: Path, sources: list[tuple[str, list[str], list[list[str]]]]
) -> list[dict]:
    """Write each source's PDF under ``tmp_path``; return the manifest entries in order.

    A source is ``(source_id, effective_dates, pages)``. Its declared title is the text of its
    page 1, and its path is unique even when two entries repeat a source ID.
    """

    entries = []
    for n, (source_id, dates, pages) in enumerate(sources):
        data = make_pdf(pages)
        relative = f"data/raw/{n:02d}/Kommentar {source_id}.pdf"
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_bytes(data)
        entries.append(
            {
                "source_id": source_id,
                "effective_dates": dates,
                "title": " ".join(pages[0]),
                "path": relative,
                "sha256": hashlib.sha256(data).hexdigest(),
                "source_url": f"https://www.bag.admin.ch/dam/{source_id}.pdf",
            }
        )
    return entries


def write_sources(
    tmp_path: Path, entries: list[dict], *, drop: tuple[str, ...] = (), **top: object
) -> Path:
    """Write the commentary-source manifest of ``entries`` under ``tmp_path``; ``top`` replaces
    and ``drop`` removes top-level keys. Returns the manifest path."""

    body = {
        "manifest_version": 1,
        "kind": "commentary_sources",
        "tariff_system": "EAL",
        "sources": entries,
        **top,
    }
    manifest = tmp_path / "data" / "manifests" / "sources.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({k: v for k, v in body.items() if k not in drop}), encoding="utf-8"
    )
    return manifest


def make_sources(
    tmp_path: Path, sources: list[tuple[str, list[str], list[list[str]]]]
) -> Path:
    """The PDFs and the commentary-source manifest of ``sources``; returns the manifest path."""

    return write_sources(tmp_path, source_entries(tmp_path, sources))


def build_sources(manifest: Path, *, budget: int = 400, limit: int = 512) -> corpus.Corpus:
    return corpus.build_commentaries(
        manifest, count_passage_tokens=words, token_budget=budget, model_limit=limit
    )


REGULAR = [
    ["Kommentar zu den Änderungen per 1. Januar 2023"],
    ["2.1 Position 1111.00 Neu", "Die Position 1111.00 ist neu.", "Seite 2 von 2"],
]
URGENT = [
    ["Kommentar zu den dringenden Änderungen per 1. Januar 2023"],
    ["2.1 Position 2222.00 Dringend", "Die Position 2222.00 wird angepasst.", "Seite 2 von 2"],
]
JOINT = [
    ["Kommentar zu den Änderungen des Anhangs 3 KLV", "per 1. Januar 2022 und 1. Februar 2022"],
    ["2.1 Position 3333.00 Zwei Daten", "Die Position 3333.00 gilt ab Februar.", "Seite 2 von 2"],
]
EXPLAINED = [
    ["Erläuterungen zu den Änderungen per 1. Juli 2021"],
    ["2.1 Position 4444.00 Erläutert", "Die Position 4444.00 wird erläutert.", "Seite 2 von 2"],
]
ONE_DATE = [
    ("2023-01-01", ["2023-01-01"], REGULAR),
    ("2023-01-01-urgent", ["2023-01-01"], URGENT),
]


def test_sources_of_one_date_keep_their_ids_and_a_joint_source_is_one_document(tmp_path):
    manifest = make_sources(
        tmp_path,
        [
            ("2023-01-01-urgent", ["2023-01-01"], URGENT),
            ("2022-01-01", ["2022-01-01", "2022-02-01"], JOINT),
            ("2023-01-01", ["2023-01-01"], REGULAR),
            ("2021-07-01", ["2021-07-01"], EXPLAINED),
        ],
    )

    built = build_sources(manifest)

    # Read in (first effective date, source ID) order, whatever the manifest's order.
    assert [(d.edition, d.effective_dates, d.page_count) for d in built.documents] == [
        ("2021-07-01", ("2021-07-01",), 2),
        ("2022-01-01", ("2022-01-01", "2022-02-01"), 2),
        ("2023-01-01", ("2023-01-01",), 2),
        ("2023-01-01-urgent", ("2023-01-01",), 2),
    ]
    # The source ID stands where build_corpus puts the edition date.
    assert [(p.passage_id, p.edition, p.section, p.text) for p in built.passages] == [
        ("2021-07-01/p2/s2.1/1", "2021-07-01", "2.1",
         "2.1 Position 4444.00 Erläutert Die Position 4444.00 wird erläutert."),
        ("2022-01-01/p2/s2.1/1", "2022-01-01", "2.1",
         "2.1 Position 3333.00 Zwei Daten Die Position 3333.00 gilt ab Februar."),
        ("2023-01-01/p2/s2.1/1", "2023-01-01", "2.1",
         "2.1 Position 1111.00 Neu Die Position 1111.00 ist neu."),
        ("2023-01-01-urgent/p2/s2.1/1", "2023-01-01-urgent", "2.1",
         "2.1 Position 2222.00 Dringend Die Position 2222.00 wird angepasst."),
    ]
    # The parser's own title detection is unchanged: none for a document of "Erläuterungen".
    joint = "Kommentar zu den Änderungen des Anhangs 3 KLV per 1. Januar 2022 und 1. Februar 2022"
    assert [(d.title, d.declared_title) for d in built.documents] == [
        (None, "Erläuterungen zu den Änderungen per 1. Juli 2021"),
        (joint, joint),
        ("Kommentar zu den Änderungen per 1. Januar 2023",
         "Kommentar zu den Änderungen per 1. Januar 2023"),
        ("Kommentar zu den dringenden Änderungen per 1. Januar 2023",
         "Kommentar zu den dringenden Änderungen per 1. Januar 2023"),
    ]
    assert [(e.edition, e.page, e.reason) for e in built.excluded_pages] == [
        (source, 1, corpus.FRONT_MATTER)
        for source in ("2021-07-01", "2022-01-01", "2023-01-01", "2023-01-01-urgent")
    ]
    urgent = built.documents[3]
    assert (urgent.path, urgent.sha256, urgent.source_url) == (
        "data/raw/00/Kommentar 2023-01-01-urgent.pdf",
        hashlib.sha256(make_pdf(URGENT)).hexdigest(),
        "https://www.bag.admin.ch/dam/2023-01-01-urgent.pdf",
    )
    assert built.editions == ("2021-07-01", "2022-01-01", "2023-01-01", "2023-01-01-urgent")


def test_build_corpus_leaves_the_new_document_fields_at_their_defaults(tmp_path):
    built = build(make_repo(tmp_path, {JUL: SIMPLE}))

    assert [(d.edition, d.effective_dates, d.declared_title) for d in built.documents] == [
        (JUL, (), None)
    ]


def _set(index: int, **values: object):
    return lambda entries: entries[index].update(values)


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        pytest.param(_set(1, source_id="2023-01-01"),
                     "source_id 2023-01-01 appears more than once", id="duplicate-source-id"),
        pytest.param(_set(1, source_id="2023-01-02-urgent"),
                     "source_id 2023-01-02-urgent must start with its first effective date "
                     "2023-01-01", id="id-not-starting-with-first-date"),
        pytest.param(_set(0, effective_dates=["2023-01-01", "2023-01-01"]),
                     "sources.0.effective_dates: Value error, must be strictly increasing",
                     id="repeated-date"),
        pytest.param(_set(0, effective_dates=["2023-01-01", "2022-12-01"]),
                     "sources.0.effective_dates: Value error, must be strictly increasing",
                     id="decreasing-dates"),
        pytest.param(_set(0, effective_dates=[]),
                     "sources.0.effective_dates: Value error, must list at least one date",
                     id="no-date"),
        pytest.param(_set(0, effective_dates=["2023-02-30"]),
                     "sources.0.effective_dates: Value error, 2023-02-30 is not a valid date",
                     id="impossible-date"),
        pytest.param(_set(0, effective_dates=["1.1.2023"]),
                     "sources.0.effective_dates.0: String should match pattern", id="not-iso"),
        pytest.param(_set(0, source_id="2023-01-01_regular"),
                     "sources.0.source_id: String should match pattern", id="malformed-id"),
        pytest.param(_set(0, note="x"), "sources.0.note: Extra inputs are not permitted",
                     id="unknown-key"),
        pytest.param(lambda entries: entries[0].pop("source_url"),
                     "sources.0.source_url: Field required", id="missing-key"),
        pytest.param(_set(0, source_url=None), "sources.0.source_url: Input should be a valid",
                     id="null-url"),
        pytest.param(_set(0, source_url="https://example.org/k.pdf"), "bag.admin.ch",
                     id="url-off-bag"),
        pytest.param(_set(0, sha256="A" * 64), "sources.0.sha256: String should match pattern",
                     id="uppercase-hash"),
        pytest.param(_set(0, path="../Kommentar.pdf"), "repository-relative POSIX path",
                     id="parent-path"),
        pytest.param(_set(0, path="/tmp/Kommentar.pdf"), "repository-relative POSIX path",
                     id="absolute-path"),
        pytest.param(_set(0, title=" "), "sources.0.title: Value error, must not be empty",
                     id="empty-title"),
        pytest.param(lambda entries: entries[1].update(path=entries[0]["path"].upper()),
                     "appears more than once", id="duplicate-path"),
        pytest.param(lambda entries: entries[1].update(sha256=entries[0]["sha256"]),
                     "appears more than once", id="duplicate-hash"),
    ],
)
def test_refuses_a_source_entry_that_breaks_the_schema(tmp_path, change, problem):
    entries = source_entries(tmp_path, ONE_DATE)
    change(entries)

    with pytest.raises(corpus.CorpusError) as refused:
        build_sources(write_sources(tmp_path, entries))

    assert problem in str(refused.value)


@pytest.mark.parametrize(
    ("top", "drop", "problem"),
    [
        ({"manifest_version": True}, (), "manifest_version: Value error, must be the integer 1"),
        ({"manifest_version": 2}, (), "manifest_version: Input should be 1"),
        ({"kind": "editions"}, (), "kind: Input should be 'commentary_sources'"),
        ({"tariff_system": "TARDOC"}, (), "tariff_system: Input should be 'EAL'"),
        ({"sources": []}, (), "sources is empty"),
        ({"editions": []}, (), "editions: Extra inputs are not permitted"),
        ({}, ("kind",), "kind: Field required"),
    ],
)
def test_refuses_a_manifest_that_is_not_a_commentary_source_manifest(tmp_path, top, drop, problem):
    entries = source_entries(tmp_path, ONE_DATE)

    with pytest.raises(corpus.CorpusError) as refused:
        build_sources(write_sources(tmp_path, entries, drop=drop, **top))

    assert problem in str(refused.value)


def test_one_refusal_lists_the_problems_of_every_source(tmp_path):
    entries = source_entries(tmp_path, ONE_DATE)
    entries[0]["note"] = "x"
    del entries[1]["title"]

    with pytest.raises(corpus.CorpusError) as refused:
        build_sources(write_sources(tmp_path, entries))

    assert refused.value.problems == (
        "sources.0.note: Extra inputs are not permitted",
        "sources.1.title: Field required",
    )


def test_refuses_a_repeated_key_and_a_manifest_outside_data_manifests(tmp_path):
    entries = source_entries(tmp_path, ONE_DATE)
    manifest = write_sources(tmp_path, entries)
    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(text.replace('"kind"', '"kind": "x", "kind"', 1), encoding="utf-8")

    with pytest.raises(corpus.CorpusError, match="duplicate key 'kind'"):
        build_sources(manifest)

    elsewhere = tmp_path / "sources.json"
    elsewhere.write_text(text, encoding="utf-8")
    with pytest.raises(corpus.CorpusError, match="must live in <repository>/data/manifests/"):
        build_sources(elsewhere)


def test_refuses_a_hash_mismatch_and_a_file_outside_the_root_in_one_refusal(tmp_path):
    repo = tmp_path / "repo"
    entries = source_entries(repo, [*ONE_DATE, ("2022-01-01", ["2022-01-01", "2022-02-01"], JOINT)])
    entries[0]["sha256"] = hashlib.sha256(b"other bytes").hexdigest()
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(make_pdf(URGENT))
    link = repo / entries[1]["path"]
    link.unlink()
    link.symlink_to(outside)  # the manifest hash matches, but the file is not the repository's

    with pytest.raises(corpus.CorpusError) as refused:
        build_sources(write_sources(repo, entries))

    first, second = refused.value.problems
    assert first.startswith(f"{entries[0]['path']}: sha256 mismatch")
    assert second == f"{entries[1]['path']}: resolves outside the repository root"


def test_refuses_a_declared_title_that_is_not_on_page_1(tmp_path):
    entries = source_entries(tmp_path, [("2022-01-01", ["2022-01-01", "2022-02-01"], JOINT)])
    entries[0]["title"] = "2.1 Position 3333.00 Zwei Daten"  # the heading on page 2

    with pytest.raises(corpus.CorpusError) as refused:
        build_sources(write_sources(tmp_path, entries))

    assert refused.value.problems == (
        f"{entries[0]['path']}: the declared title of 2022-01-01 is not in the text of page 1",
    )
