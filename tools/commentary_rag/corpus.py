"""Commentary corpus: the BAG commentary PDFs of the AL manifest as page-bounded passages.

The manifest (``data/manifests/bag-al.json``) pins each edition's ``commentary_pdf`` by SHA-256.
The corpus reads those documents through the ingestion service's own manifest loader and
verifier, so the bytes handed to ``pdftotext`` (on stdin, never re-read from disk) are exactly
the bytes whose hash matched. It is read-only: nothing here touches the tariff database, frozen
records or any LLM.

Uses two private helpers of ``tarifhub_ingest.ingestion.manifest`` (``_load``, ``_verify``):
they are the existing strict schema, NFC path matching and verify-then-parse read, reused
instead of duplicated. A change to their signatures breaks the tests in this folder.

A passage never crosses a page. Its section is the last numbered heading seen in the document
(``2.5 ...`` or ``1.`` followed by a title line), so a section continuing on the next page keeps
its number. The printed footer ``Seite N von M`` must equal the PDF page index and page count.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tarifhub_ingest.ingestion import manifest as manifest_io

COMMENTARY_KIND = "commentary_pdf"
FRONT_MATTER = "front matter before the first section heading"
TABLE_OF_CONTENTS = "table of contents"
NO_TEXT = "no extractable text"
HEADING_ONLY = "heading without text on this page"

_FOOTER = re.compile(r"^Seite (\d+) von (\d+)$")
_SUBSECTION = re.compile(r"^([1-9]\.[1-9][0-9]?) +([A-ZÄÖÜ«].*)$")
_SECTION = re.compile(r"^([1-9])\.$")
_TITLE_START = "Kommentar"


class CorpusError(ValueError):
    """A commentary source is missing, does not match its manifest hash, or cannot be used."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = tuple(problems)
        super().__init__(
            "commentary corpus refused:\n" + "\n".join(f"- {problem}" for problem in problems)
        )


@dataclass(frozen=True)
class Document:
    """One verified commentary PDF of one AL edition."""

    edition: str
    path: str
    sha256: str
    source_url: str | None
    title: str | None
    page_count: int


@dataclass(frozen=True)
class Passage:
    """A retrievable unit: text of one section on one page of one verified document.

    ``tokens`` is the count reported by the caller's tokenizer for the exact string the
    embedder encodes, :attr:`indexed_text` (see :func:`build_corpus`); ``split`` says how the
    section text on the page was divided: ``whole``, at sentence boundaries, (a sentence over
    budget) at words, or as a ``table`` of position rows. ``text`` is always a contiguous run of
    the page. ``context`` is set only on a later part of a split table: the table's heading and
    column names, verbatim from the same page, so the part stays interpretable.
    """

    passage_id: str
    edition: str
    document_sha256: str
    source_url: str | None
    page: int
    page_label: str | None
    section: str | None
    section_title: str | None
    text: str
    text_sha256: str
    tokens: int
    split: str
    context: str | None = None

    @property
    def indexed_text(self) -> str:
        """What retrieval ranks and the embedder encodes: the context, if any, then the text."""

        return self.text if self.context is None else f"{self.context} {self.text}"


@dataclass(frozen=True)
class ExcludedPage:
    """A page, or a heading on it, that yields no passage, and why."""

    edition: str
    page: int
    reason: str


@dataclass(frozen=True)
class Corpus:
    """The verified documents, their passages in edition/page order, and the excluded pages."""

    documents: tuple[Document, ...]
    passages: tuple[Passage, ...]
    excluded_pages: tuple[ExcludedPage, ...]
    token_budget: int
    model_limit: int

    @property
    def editions(self) -> tuple[str, ...]:
        """The editions with a verified commentary, oldest first."""

        return tuple(d.edition for d in self.documents)


def normalize(text: str) -> str:
    """NFC with every whitespace run folded to one space: the form passages and quotes share."""

    return " ".join(unicodedata.normalize("NFC", text).split())


def build_corpus(
    manifest_path: Path,
    *,
    count_passage_tokens: Callable[[str], int],
    token_budget: int,
    model_limit: int,
    pdftotext: str = "pdftotext",
) -> Corpus:
    """Read every edition's commentary PDF from the manifest, verified, into passages.

    ``count_passage_tokens(text)`` must return the token count of the exact input the dense
    embedder encodes for ``text`` (instruction prefix and special tokens included).
    Refuses (:class:`CorpusError`, listing every problem) when a commentary is missing or does
    not match its hash, when ``pdftotext`` fails, or when a printed page number disagrees.
    """

    if not 0 < token_budget <= model_limit:
        raise CorpusError(
            [f"token budget {token_budget} exceeds the model limit {model_limit}"
             if token_budget > model_limit else f"token budget {token_budget} must be positive"]
        )
    try:
        manifest, root = manifest_io._load(manifest_path)
    except manifest_io.ManifestError as exc:
        raise CorpusError(list(exc.problems)) from None
    problems: list[str] = []
    verified: list[tuple[str, manifest_io.ManifestDocument, bytes]] = []
    for edition in sorted(manifest.editions, key=lambda e: e.effective_date):
        date = edition.effective_date.isoformat()
        listed = [d for d in edition.documents if d.kind == COMMENTARY_KIND]
        if len(listed) != 1:
            problems.append(
                f"edition {date} lists {len(listed)} {COMMENTARY_KIND} documents; expected 1"
            )
            continue
        data, found = manifest_io._verify(root, listed[0], keep=True)
        problems += found
        if data is not None:
            verified.append((date, listed[0], data))
    if problems:
        raise CorpusError(problems)

    executable = shutil.which(pdftotext)
    if executable is None:
        raise CorpusError([f"{pdftotext} not found: install poppler to read the commentary PDFs"])
    documents: list[Document] = []
    passages: list[Passage] = []
    excluded: list[ExcludedPage] = []
    for date, listed, data in verified:
        digest = hashlib.sha256(data).hexdigest()
        if digest != listed.sha256:  # the bytes parsed below are the bytes verified
            problems.append(f"{listed.path}: parsed bytes differ from the verified hash")
            continue
        pages, problem = _extract_pages(executable, data)
        if problem:
            problems.append(f"{listed.path}: {problem}")
            continue
        parsed = _parse(date, listed, digest, pages, count_passage_tokens, token_budget)
        problems += parsed.problems
        documents.append(
            Document(
                edition=date,
                path=listed.path,
                sha256=digest,
                source_url=listed.source_url,
                title=parsed.title,
                page_count=len(pages),
            )
        )
        passages += parsed.passages
        excluded += parsed.excluded
    if problems:
        raise CorpusError(problems)
    return Corpus(
        documents=tuple(documents),
        passages=tuple(passages),
        excluded_pages=tuple(excluded),
        token_budget=token_budget,
        model_limit=model_limit,
    )


def _extract_pages(executable: str, data: bytes) -> tuple[list[str], str | None]:
    """Run pdftotext on the verified bytes (stdin to stdout); one string per PDF page."""

    result = subprocess.run(
        [executable, "-enc", "UTF-8", "-", "-"], input=data, capture_output=True, check=False
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()[:200]
        return [], f"pdftotext exited {result.returncode}: {detail}"
    pages = result.stdout.decode("utf-8").split("\f")
    if pages and not pages[-1].strip():  # pdftotext ends every page with a form feed
        pages.pop()
    return pages, None


@dataclass
class _Parsed:
    passages: list[Passage]
    excluded: list[ExcludedPage]
    problems: list[str]
    title: str | None


def _parse(  # noqa: PLR0913 - one document's identity, its pages and the tokenizer
    edition: str,
    document: manifest_io.ManifestDocument,
    digest: str,
    pages: list[str],
    count: Callable[[str], int],
    budget: int,
) -> _Parsed:
    out = _Parsed(passages=[], excluded=[], problems=[], title=None)
    section: tuple[str, str] | None = None
    front: list[str] = []
    for index, raw in enumerate(pages, start=1):
        lines = [line for line in (normalize(line) for line in raw.splitlines()) if line]
        if not lines:
            out.excluded.append(ExcludedPage(edition, index, NO_TEXT))
            continue
        if lines[0] == "Inhaltsverzeichnis":
            out.excluded.append(ExcludedPage(edition, index, TABLE_OF_CONTENTS))
            continue
        label = None
        footer = _FOOTER.match(lines[-1])
        if footer:
            label = lines.pop()
            if (int(footer[1]), int(footer[2])) != (index, len(pages)):
                out.problems.append(
                    f"{document.path}: PDF page {index} of {len(pages)} is printed as '{label}'"
                )
        # (section, lines, how many of the lines are the section's own heading)
        blocks: list[tuple[tuple[str, str], list[str], int]] = []
        if section is not None:
            blocks.append((section, [], 0))
        page_front = 0
        i = 0
        while i < len(lines):
            heading = _heading(lines, i)
            if heading is not None:
                (number, title), consumed = heading
                section = (number, title)
                blocks.append((section, lines[i : i + consumed], consumed))
                i += consumed
                continue
            if section is None:
                front.append(lines[i])
                page_front += 1
            else:
                blocks[-1][1].append(lines[i])
            i += 1
        made = 0
        heading_only: list[str] = []
        for (number, title), block, heading_lines in blocks:
            if not block:
                continue
            if len(block) == heading_lines:  # a heading with no text of its own on this page
                heading_only += block
                continue
            lead = len(heading_only) + heading_lines  # heading lines at the start of the block
            block = heading_only + block  # it joins the text it heads, in page order
            heading_only = []
            pieces = _pieces(block, lead, count, budget)
            for k, (text, tokens, split, context) in enumerate(pieces, 1):
                if tokens > budget:  # only a lone word or table row can remain over budget
                    unit = "one word" if split == "word" else "one table row with its heading"
                    out.problems.append(
                        f"{document.path}: page {index}, section {number}: {tokens} tokens in "
                        f"{unit}, over the token budget {budget}"
                    )
                    continue
                made += 1
                out.passages.append(
                    Passage(
                        passage_id=f"{edition}/p{index}/s{number}/{k}",
                        edition=edition,
                        document_sha256=digest,
                        source_url=document.source_url,
                        page=index,
                        page_label=label,
                        section=number,
                        section_title=title,
                        text=text,
                        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        tokens=tokens,
                        split=split,
                        context=context,
                    )
                )
        if heading_only:  # at the foot of the page: it never joins text on another page
            out.excluded.append(
                ExcludedPage(edition, index, f"{HEADING_ONLY}: {' '.join(heading_only)}")
            )
        if page_front and not made:
            out.excluded.append(ExcludedPage(edition, index, FRONT_MATTER))
    starts = [n for n, line in enumerate(front) if line.startswith(_TITLE_START)]
    if starts:
        out.title = " ".join(front[starts[0] :])
    return out


def _pieces(
    lines: list[str], lead: int, count: Callable[[str], int], budget: int
) -> list[tuple[str, int, str, str | None]]:
    """The passages of one section's lines on one page: ``(text, tokens, split, context)``.

    A block within the budget stays whole. Over it, a table of position rows becomes its own
    passage with its heading (the line ending in ':' before it, its column names and, when only
    headings precede it, the section heading), split between rows only when even the table
    exceeds the budget; the prose around it is chunked at sentences as before.
    """

    text = " ".join(lines)
    tokens = count(text)
    if tokens <= budget:
        return [(text, tokens, "whole", None)]
    table = _find_table(lines)
    if table is None:
        return [(*chunk, None) for chunk in _chunks(text, count, budget)]
    start, first_row, row_ends = table
    if start <= lead:  # only headings precede the table: they head it
        start = 0
    pieces = [(*chunk, None) for chunk in _chunks(" ".join(lines[:start]), count, budget)] if start else []
    bounds = [first_row, *(end + 1 for end in row_ends[:-1])]
    rows = [" ".join(lines[b : e + 1]) for b, e in zip(bounds, row_ends, strict=True)]
    pieces += _table_pieces(" ".join(lines[start:first_row]), rows, count, budget)
    rest = lines[row_ends[-1] + 1 :]
    return pieces + (_pieces(rest, 0, count, budget) if rest else [])


# A table row in the commentaries: description lines, a position code line, a value line.
_ROW_CODE = re.compile(r"^\d{4}\.\d{2}$")
_ROW_VALUE = re.compile(r"^\d{1,3}(?:[.,]\d+)?$")
_ROW_LINES = 3  # description lines one row may span


def _find_table(lines: list[str]) -> tuple[int, int, list[int]] | None:
    """The first table of position rows: (heading line, first row's line, each row's last line).

    At least two consecutive rows, introduced by a line ending in ':' followed by the column
    names; the first row's description is taken to be the single line before its code.
    """

    ends = [
        i + 1
        for i in range(1, len(lines) - 1)
        if _ROW_CODE.match(lines[i]) and _ROW_VALUE.match(lines[i + 1])
    ]
    if len(ends) < 2:
        return None
    run = ends[:1]
    for end in ends[1:]:
        if end - run[-1] - 2 > _ROW_LINES:
            break
        run.append(end)
    first_row = run[0] - 2
    headings = [i for i in range(first_row) if lines[i].endswith(":")]
    if len(run) < 2 or not headings:
        return None
    return headings[-1], first_row, run


def _table_pieces(
    head: str, rows: list[str], count: Callable[[str], int], budget: int
) -> list[tuple[str, int, str, str | None]]:
    """The table whole when it fits, else row groups; later groups carry ``head`` as context."""

    whole = " ".join([head, *rows])
    tokens = count(whole)
    if tokens <= budget:
        return [(whole, tokens, "table", None)]
    groups: list[list[str]] = [[]]
    for row in rows:
        candidate = [*groups[-1], row]
        if not groups[-1] or count(" ".join([head, *candidate])) <= budget:
            groups[-1] = candidate
        else:
            groups.append([row])
    pieces: list[tuple[str, int, str, str | None]] = []
    for n, group in enumerate(groups):
        body = " ".join(group)
        tokens = count(f"{head} {body}")  # the indexed string of every part is head + rows
        pieces.append((f"{head} {body}", tokens, "table", None) if n == 0 else (body, tokens, "table", head))
    return pieces


def _chunks(
    text: str, count: Callable[[str], int], budget: int
) -> list[tuple[str, int, str]]:
    """Divide one section's text on one page into pieces of at most ``budget`` tokens.

    Whole when it fits; otherwise consecutive sentences packed greedily. Every piece is a
    contiguous run of the text, so joining the pieces with single spaces gives it back.
    """

    tokens = count(text)
    if tokens <= budget:
        return [(text, tokens, "whole")]
    pieces: list[tuple[str, int, str]] = []
    current: tuple[str, int] | None = None
    for sentence in _sentences(text):
        candidate = sentence if current is None else f"{current[0]} {sentence}"
        tokens = count(candidate)
        if tokens <= budget:
            current = (candidate, tokens)
            continue
        if current is not None:
            pieces.append((*current, "sentence"))
            current = None
        tokens = count(sentence)
        if tokens <= budget:
            current = (sentence, tokens)
        else:
            pieces += _words(sentence, count, budget)
    if current is not None:
        pieces.append((*current, "sentence"))
    return pieces


def _words(sentence: str, count: Callable[[str], int], budget: int) -> list[tuple[str, int, str]]:
    """Pack the words of one over-budget sentence greedily; a lone word may stay over budget."""

    pieces: list[tuple[str, int, str]] = []
    current: tuple[str, int] | None = None
    for word in sentence.split(" "):
        candidate = word if current is None else f"{current[0]} {word}"
        tokens = count(candidate)
        if tokens <= budget or current is None:
            current = (candidate, tokens)
            continue
        pieces.append((*current, "word"))
        current = (word, count(word))
    if current is not None:
        pieces.append((*current, "word"))
    return pieces


# A full stop followed by a capitalised word ends a sentence, unless it closes an
# abbreviation (bzw., Abs., z. B., also the last part of a compound such as Pos.-Nr.) or a
# one- or two-digit ordinal (1. Juli, 20. Woche).
_SENTENCE_END = re.compile(r"[.!?] (?=[A-ZÄÖÜ«•(])")
_ABBREVIATIONS = frozenset(
    "a abs art b bst bzw ca d evtl h inkl lit nr pos resp s u usw vgl z ziff".split()
)
_COMPOUND_PART = re.compile(r"[.\-/]")


def _sentences(text: str) -> list[str]:
    sentences: list[str] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        word = text[start : match.start()].rsplit(" ", 1)[-1]
        last = _COMPOUND_PART.split(word)[-1]
        if last.lower() in _ABBREVIATIONS or (word.isdigit() and len(word) <= 2):
            continue
        sentences.append(text[start : match.start() + 1])
        start = match.end()
    sentences.append(text[start:])
    return sentences


def _heading(lines: list[str], i: int) -> tuple[tuple[str, str], int] | None:
    """A numbered heading at ``lines[i]``: ``2.5 Title`` or ``2.`` followed by a title line."""

    sub = _SUBSECTION.match(lines[i])
    if sub:
        return (sub[1], sub[2]), 1
    top = _SECTION.match(lines[i])
    if top and i + 1 < len(lines) and lines[i + 1][:1].isupper():
        return (top[1], lines[i + 1]), 2
    return None
