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
