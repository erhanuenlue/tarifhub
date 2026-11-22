"""Layout probe: pdfplumber geometry beside the Poppler text the commentary pilot parses.

A standalone diagnostic behind ``docs/evidence/2026-11-22-pdfplumber-layout-probe.md``. The pilot never
imports it and it changes nothing. It reads one manifest-pinned commentary PDF (refusing when the
bytes do not match the manifest's SHA-256), hands the same bytes to ``pdftotext -enc UTF-8 - -``
(the pilot's call) and to pdfplumber, finds every passage of a frozen run record in the Poppler
text by the passage's text SHA-256, and prints what the geometry shows: fonts, heading lines,
the footnote separator, footnote numbers and their in-text references; then, kept apart, the
PDF's own tags.

pdfplumber is not a dependency of this repository. Run the probe in an ephemeral environment
from a checkout that holds the git-ignored BAG PDFs:

    uv run --no-project --with pdfplumber==0.11.11 python tools/commentary_rag/layout_probe.py --edition 2026-07-01 --pages 4,6

``--crops DIR`` also saves PNG crops of the reported regions, for a git-ignored folder such as
``tools/commentary_rag/local/``; never commit them.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import statistics
import subprocess
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

try:
    import pdfplumber
except ImportError:  # deliberately absent from every environment of the pilot
    pdfplumber = None

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RECORD = HERE / "results" / "2026-11-14-retrieval-corrected.json"
COMMENTARY_KIND = "commentary_pdf"
# The pilot's footer pattern, copied from corpus.py: the probe must run without the pilot.
FOOTER = re.compile(r"^Seite (\d+) von (\d+)$")
NUMBER = re.compile(r"^([1-9](?:\.[1-9][0-9]?)?)\.?(?: |$)")
CODE = re.compile(r"^\d{4}\.\d{2}[,.]?$")  # an AL position code such as 6203.56
# A char at most this share of its line's main size is a superscript candidate.
SMALL = 0.75
# The structure elements the tag outline prints.
SHOWN = ("H1", "H2", "H3", "P", "Note", "Table", "L")
HYPHENS = {
    "-": "U+002D",
    chr(0xAD): "U+00AD",
    chr(0x2010): "U+2010",
    chr(0x2011): "U+2011",
}
REFUSAL = (
    "layout_probe needs pdfplumber, which no environment of this repository installs (by "
    "design). Run it in an ephemeral environment instead:\n"
    "  uv run --no-project --with pdfplumber==0.11.11 python tools/commentary_rag/layout_probe.py"
    " --edition 2026-07-01 --pages 4,6"
)


class ProbeError(RuntimeError):
    """The input cannot be probed: missing, not matching its hash, or unreadable."""


@dataclass
class Line:
    """One visual line as pdfplumber groups it, with its main (most frequent) font and size."""

    index: int
    top: float
    bottom: float
    x0: float
    x1: float
    font: str
    size: float
    baseline: float  # median bottom of the main-font chars
    tags: str  # marked-content tags of its chars, most frequent first
    text: str
    raw: str  # pdfplumber's text of the line: its chars plus the spaces it inserts at gaps
    chars: list[dict]  # pdfplumber's chars of the line, in text order (no space chars)


@dataclass
class Token:
    """A run of small chars on one line: a superscript candidate."""

    line: Line
    text: str
    font: str
    size: float
    x0: float
    x1: float
    top: float
    bottom: float
    lift: float  # how far its bottom sits above the line's baseline
    tag: str
    chars: list[dict]


@dataclass
class Rule:
    """A filled rectangle at most 1 pt high: a drawn horizontal line."""

    x0: float
    x1: float
    top: float
    line: Line | None  # the text line it underlines, if it lies within one
    under: str  # the text above it on that line
    under_tags: str


@dataclass
class PageLayout:
    """What the geometry of one page shows."""

    number: int
    body: float  # the page's most frequent char size
    lines: list[Line]
    # heading lines (bold, larger than the body), one run per numbered heading
    runs: list[list[Line]]
    rules: list[Rule]
    separator: Rule | None  # the rule above the footnotes
    tokens: list[Token]


@dataclass
class Footnote:
    """A footnote below the separator, from its number to the next number."""

    number: str
    marker: Token
    lines: list[Line]
    words: list[str]
    refs: list[Token]  # same-number superscripts above the separator


@dataclass
class Located:
    """One page of Poppler text with the frozen passages found in it."""

    lines: list[str]
    label: str | None
    words: list[str]
    spans: list[tuple[str, int, int]]  # passage ID, first word, end word
    owners: list[list[str]]  # passage IDs per Poppler line
    missing: list[str]


def normalize(text: str) -> str:
    """The pilot's normal form: NFC with every whitespace run folded to one space."""

    return " ".join(unicodedata.normalize("NFC", text).split())


def verified_pdf(manifest: Path, root: Path, edition: str) -> tuple[str, str, bytes]:
    """The edition's commentary PDF from the manifest, read once and checked by SHA-256."""

    data = json.loads(manifest.read_text(encoding="utf-8"))
    listed = [
        document
        for entry in data["editions"]
        if entry["effective_date"] == edition
        for document in entry["documents"]
        if document["kind"] == COMMENTARY_KIND
    ]
    if len(listed) != 1:
        raise ProbeError(
            f"edition {edition} lists {len(listed)} {COMMENTARY_KIND} documents"
        )
    entry = listed[0]
    content = _nfc_path(root / entry["path"]).read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != entry["sha256"]:
        raise ProbeError(
            f"{entry['path']}: SHA-256 {digest}, the manifest pins {entry['sha256']}"
        )
    return entry["path"], digest, content


def _nfc_path(path: Path) -> Path:
    if path.exists():
        return path
    wanted = unicodedata.normalize("NFC", path.name)
    if path.parent.is_dir():
        for candidate in path.parent.iterdir():
            if unicodedata.normalize("NFC", candidate.name) == wanted:
                return candidate
    raise ProbeError(
        f"{path.name}: not found under --root (the BAG PDFs are git-ignored)"
    )


def poppler_pages(content: bytes, executable: str) -> list[list[str]]:
    """The pilot's view: pdftotext reads the bytes on stdin; normalised non-empty lines per page."""

    result = subprocess.run(
        [executable, "-enc", "UTF-8", "-", "-"],
        input=content,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()[:200]
        raise ProbeError(f"pdftotext exited {result.returncode}: {detail}")
    pages = result.stdout.decode("utf-8").split("\f")
    if pages and not pages[-1].strip():  # pdftotext ends every page with a form feed
        pages.pop()
    return [
        [ln for ln in (normalize(raw) for raw in page.splitlines()) if ln]
        for page in pages
    ]


def locate(lines: list[str], passages: list[dict]) -> Located:
    """Find each frozen passage of one page in its Poppler words by the passage's text SHA-256.

    A page's passages are contiguous runs of its text in page order (the footer excluded), so
    each one is searched from where the previous one ended; a hash match pins its span exactly.
    """

    label = lines[-1] if lines and FOOTER.match(lines[-1]) else None
    body = lines[:-1] if label else lines
    words = " ".join(body).split(" ") if body else []
    spans: list[tuple[str, int, int]] = []
    missing: list[str] = []
    cursor = 0
    for passage in passages:
        end = _end(words, cursor, passage["text_sha256"])
        if end is None:
            missing.append(passage["passage_id"])
            continue
        spans.append((passage["passage_id"], cursor, end))
        cursor = end
    owners: list[list[str]] = []
    first = 0
    for line in lines:
        last = first + len(line.split(" "))
        owners.append([pid for pid, a, b in spans if a < last and b > first])
        first = last
    return Located(lines, label, words, spans, owners, missing)


def _end(words: list[str], start: int, digest: str) -> int | None:
    text: str | None = None
    for j in range(start, len(words)):
        text = words[j] if text is None else f"{text} {words[j]}"
        if hashlib.sha256(text.encode("utf-8")).hexdigest() == digest:
            return j + 1
    return None


def _font(char: dict) -> str:
    return char["fontname"].split("+")[-1]


def _key(char: dict) -> tuple[str, float]:
    return _font(char), round(char["size"], 2)


def _counts(values: list[str]) -> str:
    return " ".join(f"{value}:{n}" for value, n in Counter(values).most_common())


def layout_lines(page: Any) -> list[Line]:
    """pdfplumber's visual lines of a page with main font, size, baseline and tags."""

    lines: list[Line] = []
    for raw in page.extract_text_lines(layout=False, strip=True, return_chars=True):
        chars = raw["chars"]
        ink = [c for c in chars if c["text"].strip()]
        if not ink:
            continue
        main = Counter(_key(c) for c in ink).most_common(1)[0][0]
        lines.append(
            Line(
                index=len(lines),
                top=raw["top"],
                bottom=raw["bottom"],
                x0=raw["x0"],
                x1=raw["x1"],
                font=main[0],
                size=main[1],
                baseline=statistics.median(c["bottom"] for c in ink if _key(c) == main),
                tags=_counts([str(c.get("tag")) for c in ink]),
                text=normalize(raw["text"]),
                raw=raw["text"],
                chars=chars,
            )
        )
    return lines


def small_tokens(line: Line) -> list[Token]:
    """Runs of chars at most SMALL of the line's main size: superscript candidates."""

    tokens: list[Token] = []
    run: list[dict] = []
    for char in [*line.chars, None]:
        small = (
            char is not None
            and bool(char["text"].strip())
            and char["size"] <= SMALL * line.size
        )
        if small and run and char["x0"] - run[-1]["x1"] > 1.0:
            tokens.append(_token(line, run))
            run = []
        if small:
            run.append(char)
        elif run:
            tokens.append(_token(line, run))
            run = []
    return tokens


def _token(line: Line, run: list[dict]) -> Token:
    bottom = max(c["bottom"] for c in run)
    return Token(
        line=line,
        text="".join(c["text"] for c in run),
        font=_font(run[0]),
        size=round(run[0]["size"], 2),
        x0=run[0]["x0"],
        x1=run[-1]["x1"],
        top=min(c["top"] for c in run),
        bottom=bottom,
        lift=line.baseline - bottom,
        tag=str(run[0].get("tag")),
        chars=run,
    )


def thin_rules(page: Any, lines: list[Line]) -> list[Rule]:
    """Rectangles at most 1 pt high and at least 20 pt wide; an underline lies within a line."""

    rules: list[Rule] = []
    for rect in sorted(page.rects, key=lambda r: r["top"]):
        if rect["height"] > 1.0 or rect["width"] < 20:
            continue
        line = next(
            (
                ln
                for ln in lines
                if ln.top - 1 <= rect["top"] <= ln.bottom + 1
                and rect["x0"] < ln.x1
                and rect["x1"] > ln.x0
            ),
            None,
        )
        under = [
            c
            for c in (line.chars if line else [])
            if c["text"].strip()
            and c["x0"] >= rect["x0"] - 1
            and c["x1"] <= rect["x1"] + 1
        ]
        rules.append(
            Rule(
                x0=rect["x0"],
                x1=rect["x1"],
                top=rect["top"],
                line=line,
                under="".join(c["text"] for c in under),
                under_tags=_counts([str(c.get("tag")) for c in under]),
            )
        )
    return rules


def analyse(page: Any, number: int) -> PageLayout:
    """Lines, heading runs, thin rules, footnote separator and small tokens of one page."""

    lines = layout_lines(page)
    sizes = Counter(
        round(c["size"], 2) for ln in lines for c in ln.chars if c["text"].strip()
    )
    body = sizes.most_common(1)[0][0] if sizes else 0.0
    runs: list[list[Line]] = []
    previous: Line | None = None
    for line in lines:
        heading = "Bold" in line.font and line.size > body + 0.5
        continues = (
            heading
            and previous is not None
            and (line.font, line.size) == (previous.font, previous.size)
            and not NUMBER.match(line.text)
        )
        if continues:
            runs[-1].append(line)
        elif heading:
            runs.append([line])
        previous = line if heading else None
    rules = thin_rules(page, lines)
    separator = next(
        (
            r
            for r in rules
            if r.line is None and all(ln.size < body for ln in lines if ln.top > r.top)
        ),
        None,
    )
    tokens = [t for ln in lines for t in small_tokens(ln)]
    return PageLayout(number, body, lines, runs, rules, separator, tokens)


def plain(line: Line, skip: set[int]) -> str:
    """The line's text, spaced as pdfplumber spaces it, without the chars whose id is in skip."""

    text, out, i = line.raw, [], 0
    for char in line.chars:  # walk pdfplumber's text, keeping the spaces it inserted
        piece = char["text"]
        while i < len(text) and text[i].isspace() and text[i : i + len(piece)] != piece:
            out.append(" ")
            i += 1
        if text[i : i + len(piece)] == piece:
            i += len(piece)
        if id(char) not in skip:
            out.append(piece)
    return normalize("".join(out))


def footnotes(layout: PageLayout) -> list[Footnote]:
    """Footnotes below the separator, each from its leading number to the next number."""

    if layout.separator is None:
        return []
    zone = [
        ln
        for ln in layout.lines
        if ln.top > layout.separator.top and not FOOTER.match(ln.text)
    ]
    indexes = {ln.index for ln in zone}
    markers = [
        t
        for t in layout.tokens
        if t.line.index in indexes and t.text.isdigit() and t.x0 <= t.line.x0 + 0.5
    ]
    above = [
        t
        for t in layout.tokens
        if t.line.top < layout.separator.top and t.text.isdigit()
    ]
    notes: list[Footnote] = []
    for k, marker in enumerate(markers):
        start = next(n for n, ln in enumerate(zone) if ln.index == marker.line.index)
        stop = (
            next(
                n for n, ln in enumerate(zone) if ln.index == markers[k + 1].line.index
            )
            if k + 1 < len(markers)
            else len(zone)
        )
        text = " ".join(
            plain(ln, {id(c) for c in marker.chars}) for ln in zone[start:stop]
        )
        refs = [t for t in above if t.text == marker.text]
        notes.append(
            Footnote(marker.text, marker, zone[start:stop], text.split(), refs)
        )
    return notes


def following(token: Token) -> list[str]:
    """Up to three words with a letter or digit that follow the token on its line."""

    cut = {id(c) for c in token.line.chars if c["x0"] <= token.x0 + 0.01}
    cut |= {id(c) for c in token.chars}
    words = plain(token.line, cut).split()
    return [w for w in words if any(ch.isalnum() for ch in w)][:3]


def joined(run: list[Line], tokens: list[Token]) -> tuple[str, list[str]]:
    """A heading run's text without superscripts; a line-end hyphen is dropped only before a
    lowercase continuation (a heuristic: the glyph is the same U+002D either way)."""

    skip = {id(c) for t in tokens for c in t.chars}
    text = ""
    breaks: list[str] = []
    for line in run:
        part = plain(line, skip)
        if not text:
            text = part
            continue
        tail, head = text.rsplit(" ", 1)[-1], part.split(" ", 1)[0]
        if text.endswith("-") and part[:1].islower():
            breaks.append(
                f"'{tail}' + '{head}': hyphen dropped (lowercase continuation)"
            )
            text = text[:-1] + part
        elif text.endswith("-"):
            breaks.append(
                f"'{tail}' + '{head}': hyphen kept (no lowercase continuation)"
            )
            text += part
        else:
            text = f"{text} {part}"
    return text, breaks


def section_of(layout: PageLayout, top: float, carried: str | None) -> tuple[str, bool]:
    """The number of the last heading run starting above ``top`` on the page."""

    numbers = [
        NUMBER.match(run[0].text)
        for run in layout.runs
        if run[0].top <= top + 0.5 and NUMBER.match(run[0].text)
    ]
    if numbers:
        return numbers[-1][1], False
    return str(carried), True


def _number(line: Line) -> str:
    match = NUMBER.match(line.text)
    return match[1] if match else "?"


def _box(line: Line) -> str:
    return f"{line.top:.2f}-{line.bottom:.2f}, x {line.x0:.2f}-{line.x1:.2f}"


def _tok(token: Token) -> str:
    return (
        f"'{token.text}' {token.font} {token.size} at x0 {token.x0:.2f} top {token.top:.2f}"
        f" bottom {token.bottom:.2f}, lift {token.lift:.2f} above a {token.line.size} line"
        f" (tag {token.tag})"
    )


def hyphen_breaks(layout: PageLayout) -> list[tuple[str, str, str]]:
    """Lines that end in a hyphen glyph: (code point, last word, first word of the next line)."""

    found = []
    for line, after in zip(layout.lines, layout.lines[1:], strict=False):
        end = line.raw.rstrip()[-1:]
        if end in HYPHENS:
            found.append((HYPHENS[end], line.text.split()[-1], after.text.split()[0]))
    return found


def census(pdf: Any, layouts: list[PageLayout], poppler: list[list[str]]) -> list[str]:
    """Fonts, heading runs, superscript candidates, line-end hyphens and thin rules, all pages."""

    fonts: Counter = Counter()
    tags: dict[tuple[str, float], list[str]] = {}
    for page in pdf.pages:
        for char in page.chars:
            if char["text"].strip():
                fonts[_key(char)] += 1
                tags.setdefault(_key(char), []).append(str(char.get("tag")))
    out = [
        "",
        "CENSUS, all pages (geometry and fonts; the tag counts are marked content)",
    ]
    for (font, size), n in fonts.most_common():
        out.append(
            f"  font {font} {size}: {n} chars (tags {_counts(tags[(font, size)])})"
        )
    for layout in layouts:
        sep = layout.separator
        out.append(
            f"  p{layout.number}: body {layout.body}; heading runs "
            + (
                ", ".join(
                    f"'{r[0].text[:28]}' ({len(r)} lines, {r[0].font} {r[0].size}, tags"
                    f" {_counts([str(c.get('tag')) for ln in r for c in ln.chars if c['text'].strip()])})"
                    for r in layout.runs
                )
                or "none"
            )
            + f"; separator {'none' if sep is None else f'{sep.x0:.2f}-{sep.x1:.2f} at {sep.top:.2f}'}"
        )
        breaks = hyphen_breaks(layout)
        upper = [f"'{a}' + '{b}'" for _, a, b in breaks if not b[:1].islower()]
        joined_lines = sum(1 for ln in poppler[layout.number - 1] if ln.endswith("-"))
        out.append(
            f"    line-end hyphens (pdfplumber): {len(breaks)} ({_counts([cp for cp, _, _ in breaks])});"
            f" next line not lowercase: {len(upper)}{': ' + ', '.join(upper) if upper else ''};"
            f" Poppler lines still ending in '-': {joined_lines}"
        )
        for token in layout.tokens:
            context = "".join(
                c["text"] for c in token.line.chars if c["x1"] <= token.x0 + 0.1
            )
            zone = "below" if sep is not None and token.line.top > sep.top else "above"
            out.append(
                f"    small {zone} separator: {_tok(token)} after '{context[-24:]}'"
            )
        others = [r for r in layout.rules if r is not sep and r.line is None]
        for rule in layout.rules:
            if rule is not sep and rule.line is None:
                continue
            kind = (
                "separator"
                if rule is sep
                else f"underline of '{rule.under}' ({rule.under_tags})"
            )
            out.append(
                f"    rule {rule.x0:.2f}-{rule.x1:.2f} ({rule.x1 - rule.x0:.2f} wide) at top"
                f" {rule.top:.2f}: {kind}"
            )
        if others:
            out.append(
                f"    {len(others)} other thin rules, x {min(r.x0 for r in others):.2f}-"
                f"{max(r.x1 for r in others):.2f}, tops {others[0].top:.2f}-{others[-1].top:.2f}:"
                " body-size text below them, so not a footnote separator"
            )
    return out


def detail(
    layout: PageLayout, located: Located, record: list[dict], carried: str | None
) -> list[str]:
    """One page: Poppler lines with their passages, pdfplumber lines, headings, footnotes."""

    n = layout.number
    out = ["", f"PAGE {n} (printed label {located.label!r})"]
    out.append(
        "  Poppler text as the pilot reads it (normalised lines; frozen passages per line):"
    )
    for k, (line, owners) in enumerate(zip(located.lines, located.owners, strict=True)):
        ids = ", ".join(pid.split("/", 1)[1] for pid in owners)
        out.append(f"   {k:>3} | {line} | {ids}")
    by_id = {p["passage_id"]: p for p in record}
    out.append(
        "  frozen passages on this page (record order; word span in the page's Poppler words):"
    )
    for pid, a, b in located.spans:
        p = by_id[pid]
        out.append(
            f"   {pid.split('/', 1)[1]}: words {a}-{b}, split {p['split']}, {p['tokens']} tokens,"
            f" section {p['section']}"
        )
    out.append(
        "  pdfplumber lines (top-bottom and x0-x1 in pt from the top left; main font; tags):"
    )
    for line in layout.lines:
        out.append(
            f"   {_box(line)}  {line.font} {line.size}  {line.tags} | {line.text}"
        )
    titles = {p["section"]: p["section_title"] for p in record}
    out.append(f"  heading runs (bold and larger than the body size {layout.body}):")
    for run in layout.runs:
        number = _number(run[0])
        marks = [t for t in layout.tokens if any(t.line is ln for ln in run)]
        full, breaks = joined(run, marks)
        title = NUMBER.sub("", full, count=1).strip()
        first = NUMBER.sub(
            "", plain(run[0], {id(c) for t in marks for c in t.chars}), count=1
        ).strip()
        pilot = titles.get(number)
        if pilot is None:
            out.append(
                f"   {number}: {len(run)} lines, {run[0].font} {run[0].size}, top {run[0].top:.2f};"
                f" no frozen passage is labelled {number} (a heading without text of its own"
                " joins the next section's first passage)"
            )
            continue
        carried_marks = sorted(
            {w for w in pilot.split() if w in {t.text for t in marks}}
        )
        pilot_words = [w for w in pilot.split() if w not in carried_marks]
        if pilot_words == title.split():
            verdict = "the pilot title is complete"
        elif pilot_words == first.split():
            verdict = (
                f"the pilot title is the first line only: {len(pilot_words)} of"
                f" {len(title.split())} words"
            )
        else:
            verdict = "the pilot title differs"
        out.append(
            f"   {number}: {len(run)} lines, {run[0].font} {run[0].size}, tops "
            + ", ".join(f"{ln.top:.2f}" for ln in run)
            + "; x0 "
            + ", ".join(f"{ln.x0:.2f}" for ln in run)
            + f"; bottom {run[-1].bottom:.2f}"
        )
        out.append(f"     layout title: {title}")
        out.append(f"     pilot title:  {pilot}")
        out.append(
            f"     {verdict}"
            + (
                f"; it also carries footnote number(s) {', '.join(carried_marks)}"
                if carried_marks
                else ""
            )
        )
        carriers = [
            p["passage_id"].split("/", 1)[1] for p in record if p["section"] == number
        ]
        out.append(
            f"     carried by {len(carriers)} frozen passages: {', '.join(carriers)}"
        )
        out += [f"     line break {b}" for b in breaks]
        below = next((ln for ln in layout.lines if ln.top > run[-1].bottom), None)
        if below is not None:
            out.append(
                f"     next line: top {below.top:.2f} ({below.top - run[-1].bottom:.2f} pt below),"
                f" {below.font} {below.size}, x0 {below.x0:.2f}"
            )
    sep = layout.separator
    out.append(
        "  footnote separator: "
        + (
            "none"
            if sep is None
            else f"{sep.x0:.2f}-{sep.x1:.2f} ({sep.x1 - sep.x0:.2f} wide) at top {sep.top:.2f}"
        )
    )
    if sep is not None:
        above = max(
            (ln.bottom for ln in layout.lines if ln.bottom < sep.top), default=None
        )
        if above is not None:
            out.append(
                f"   last line above it ends at {above:.2f} ({sep.top - above:.2f} pt gap)"
            )
    sections = {p["passage_id"]: p["section"] for p in record}
    for note in footnotes(layout):
        sizes = sorted({ln.size for ln in note.lines})
        out.append(
            f"  footnote {note.number}: number {_tok(note.marker)}; {len(note.lines)} lines"
            f" {note.lines[0].top:.2f}-{note.lines[-1].bottom:.2f}, main size {sizes};"
            f" {len(note.words)} words, {sum(1 for w in note.words if CODE.match(w))} position codes"
        )
        out.append(f"     text: {' '.join(note.words)[:160]}")
        start = next(
            (
                s
                for s in range(len(located.words) - len(note.words) + 1)
                if located.words[s : s + len(note.words)] == note.words
            ),
            None,
        )
        if start is None:
            out.append(
                "     pilot: the footnote text is not one contiguous run of the Poppler words"
            )
            pilot_sections: set[str] = set()
        else:
            end = start + len(note.words)
            held = [
                (pid, min(b, end) - max(a, start))
                for pid, a, b in located.spans
                if a < end and b > start
            ]
            pilot_sections = {sections[pid] for pid, _ in held}
            out.append(
                f"     pilot: Poppler words {start}-{end} of the page; passages "
                + ", ".join(
                    f"{pid.split('/', 1)[1]} ({k} of its words)" for pid, k in held
                )
                + f"; section {', '.join(sorted(pilot_sections))}"
            )
        layout_sections = set()
        for ref in note.refs:
            section, continued = section_of(layout, ref.top, carried)
            layout_sections.add(section)
            context = following(ref)
            at = next(
                (
                    s
                    for s in range(len(located.words) - len(context) + 1)
                    if context and located.words[s : s + len(context)] == context
                ),
                None,
            )
            holder = next(
                (pid for pid, a, b in located.spans if at is not None and a <= at < b),
                None,
            )
            out.append(
                f"     reference {_tok(ref)}; section by layout {section}"
                + (" (continued from an earlier page)" if continued else "")
                + f"; followed by {' '.join(context)!r}, Poppler word {at},"
                + f" passage {holder.split('/', 1)[1] if holder else None}"
            )
        if not note.refs:
            out.append(
                "     no reference with this number above the separator on this page"
            )
        verdict = (
            "same section"
            if layout_sections and layout_sections == pilot_sections
            else "displaced: the pilot puts the text in another section"
            if layout_sections and pilot_sections
            else "undecided"
        )
        out.append(
            f"     verdict: layout {sorted(layout_sections)}, pilot {sorted(pilot_sections)}: {verdict}"
        )
    return out


def outline(pdf: Any, numbers: list[int]) -> list[str]:
    """The structure tree's H1, H2, P, Note (...) elements on the given pages, with their text."""

    chars: dict[tuple[int, int], list[tuple[int, dict]]] = {}
    for n in numbers:
        for position, char in enumerate(pdf.pages[n - 1].chars):
            if char.get("mcid") is not None:
                chars.setdefault((n, char["mcid"]), []).append((position, char))
    out = ["", "TAGS (the PDF's own structure, not geometry)"]
    for n in numbers:
        try:
            elements = len(pdf.pages[n - 1].structure_tree)
            out.append(f"  page.structure_tree for page {n}: ok, {elements} elements")
        except KeyError as exc:
            out.append(f"  page.structure_tree for page {n}: raises KeyError({exc})")
    try:
        tree = pdf.structure_tree
    except KeyError as exc:
        return [*out, f"  pdf.structure_tree raises KeyError({exc})"]

    def keys(node: dict) -> list[tuple[int, int]]:
        own = [(node.get("page_number"), m) for m in node.get("mcids") or []]
        return own + [k for child in node.get("children") or [] for k in keys(child)]

    def visit(nodes: list[dict], depth: int) -> None:
        for node in nodes:
            if node.get("type") not in SHOWN:
                visit(node.get("children") or [], depth + 1)
                continue
            found = [
                (p, position, c["text"])
                for p, m in keys(node)
                if p in numbers
                for position, c in chars.get((p, m), [])
            ]
            if found:
                found.sort()
                text = normalize("".join(t for _, _, t in found))
                width = None if node["type"] in ("H1", "H2", "H3") else 110
                out.append(
                    f"  p{found[0][0]} {'  ' * depth}{node['type']}: {text[:width]}"
                )

    visit(tree, 0)
    return out


def save_crops(page: Any, layout: PageLayout, folder: Path) -> list[str]:
    """PNG crops of the heading runs, the footnote zone and each referencing line."""

    folder.mkdir(parents=True, exist_ok=True)
    boxes: list[tuple[str, tuple[float, float, float, float]]] = []
    for run in layout.runs:
        name = f"heading-{_number(run[0])}"
        boxes.append(
            (
                name,
                (
                    min(ln.x0 for ln in run),
                    run[0].top,
                    max(ln.x1 for ln in run),
                    run[-1].bottom,
                ),
            )
        )
    sep = layout.separator
    if sep is not None:
        zone = [
            ln for ln in layout.lines if ln.top > sep.top and not FOOTER.match(ln.text)
        ]
        if zone:
            boxes.append(
                (
                    "footnotes",
                    (sep.x0, sep.top, max(ln.x1 for ln in zone), zone[-1].bottom),
                )
            )
    for note in footnotes(layout):
        for k, ref in enumerate(note.refs, 1):
            line = ref.line
            boxes.append(
                (
                    f"reference-{note.number}-{k}",
                    (line.x0, line.top, line.x1, line.bottom),
                )
            )
    saved = []
    for name, (x0, top, x1, bottom) in boxes:
        box = (
            max(0, x0 - 4),
            max(0, top - 4),
            min(page.width, x1 + 4),
            min(page.height, bottom + 4),
        )
        path = folder / f"p{layout.number}-{name}.png"
        page.crop(box).to_image(resolution=150).save(path)
        saved.append(path.name)
    return saved


def versions(executable: str) -> str:
    """Python, the pdfplumber stack and Poppler, as installed for this run."""

    found = []
    for name in ("pdfplumber", "pdfminer.six", "pypdfium2", "pillow"):
        try:
            found.append(f"{name} {metadata.version(name)}")
        except metadata.PackageNotFoundError:
            found.append(f"{name} missing")
    result = subprocess.run([executable, "-v"], capture_output=True, check=False)
    first = (result.stderr or result.stdout).decode("utf-8", "replace").splitlines()[:1]
    return f"Python {sys.version.split()[0]}; {', '.join(found)}; {' '.join(first)}"


def probe(args: argparse.Namespace) -> list[str]:
    """The whole report, as lines."""

    path, digest, content = verified_pdf(args.manifest, args.root, args.edition)
    executable = shutil.which(args.pdftotext)
    if executable is None:
        raise ProbeError(f"{args.pdftotext} not found: install poppler")
    poppler = poppler_pages(content, executable)
    record = [
        p
        for p in json.loads(args.record.read_text(encoding="utf-8"))["passages"]
        if p["edition"] == args.edition
    ]
    other = sorted({p["document_sha256"] for p in record} - {digest})
    if other:
        raise ProbeError(
            f"{args.record.name}: {args.edition} passages from another PDF ({', '.join(other)})"
        )
    outside = [p["passage_id"] for p in record if not 1 <= p["page"] <= len(poppler)]
    if outside:
        raise ProbeError(f"{args.record.name}: pages outside 1-{len(poppler)}: {', '.join(outside)}")
    located = [
        locate(lines, [p for p in record if p["page"] == n])
        for n, lines in enumerate(poppler, 1)
    ]
    missing = [pid for page in located for pid in page.missing]
    found = sum(len(page.spans) for page in located)
    out = [
        f"edition {args.edition}: {path}",
        f"  SHA-256 {digest} matches the manifest; {len(poppler)} pages in pdftotext",
        f"  {versions(executable)}",
        f"  frozen record {args.record.name}: {len(record)} passages of this edition,"
        f" {found} found by text SHA-256 in the Poppler text,"
        f" {len(missing)} not found{': ' + ', '.join(missing) if missing else ''}",
    ]
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        if len(pdf.pages) != len(poppler):
            out.append(
                f"  page counts differ: pdfplumber {len(pdf.pages)}, pdftotext {len(poppler)}"
            )
        layouts = [analyse(page, n) for n, page in enumerate(pdf.pages, 1)]
        out += census(pdf, layouts, poppler)
        pages = args.pages or list(range(1, len(pdf.pages) + 1))
        for n in pages:
            if not 1 <= n <= len(pdf.pages):
                raise ProbeError(f"page {n} is outside 1-{len(pdf.pages)}")
            # the section in effect where the page starts
            earlier = [p["section"] for p in record if p["page"] < n]
            carried = earlier[-1] if earlier else None
            out += detail(layouts[n - 1], located[n - 1], record, carried)
            if args.crops is not None:
                saved = save_crops(pdf.pages[n - 1], layouts[n - 1], args.crops)
                out.append(f"  crops in {args.crops.name}/: {', '.join(saved)}")
        out += outline(pdf, pages)
    return out


def _pages(text: str) -> list[int]:
    return [int(part) for part in text.split(",") if part.strip()]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--edition", required=True, help="effective date, e.g. 2026-07-01"
    )
    parser.add_argument(
        "--pages", type=_pages, default=None, help="PDF page numbers, e.g. 4,6"
    )
    parser.add_argument(
        "--root", type=Path, default=REPO, help="checkout holding data/raw"
    )
    parser.add_argument(
        "--manifest", type=Path, default=REPO / "data" / "manifests" / "bag-al.json"
    )
    parser.add_argument(
        "--record", type=Path, default=RECORD, help="run record with passages"
    )
    parser.add_argument("--crops", type=Path, default=None, help="folder for PNG crops")
    parser.add_argument("--pdftotext", default="pdftotext")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Print the probe's report; 2 without pdfplumber, 1 when the input is refused."""

    args = _parser().parse_args(argv)
    if pdfplumber is None:
        print(REFUSAL, file=sys.stderr)
        return 2
    try:
        report = probe(args)
    except ProbeError as exc:
        print(f"layout_probe refused: {exc}", file=sys.stderr)
        return 1
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
