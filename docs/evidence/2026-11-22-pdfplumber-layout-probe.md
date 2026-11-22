# pdfplumber layout probe on the July 2026 BAG commentary

Diagnostic record of 2026-11-22 for the commentary pilot of
[ADR-025](../adr/025-commentary-retrieval.md): what pdfplumber's character coordinates show about
two known parsing problems of the pilot's corpus in the July 2026 BAG commentary, set against the
Poppler text the pilot parses. A standalone probe, `tools/commentary_rag/layout_probe.py`,
produced every figure on this page; the pilot does not import it. Nothing in the frozen corpus,
its run records or the Phase 3 evidence changed, and no model, key or paid service was used (uv
fetched pdfplumber and its dependencies from PyPI into a throwaway environment).

**In short.**

- The two problems: a section heading that wraps over five lines (section 2.5, PDF page 6), and a
  footnote whose 132 position codes belong to section 2.3 but are stored as section 2.4 (PDF
  page 4).
- Coordinates recover both. The heading's lines share a bold 11.04 pt font and a hanging indent;
  the footnote sits below a 144 pt rule in 8.04 pt type, and both of its raised references lie
  above the 2.4 heading.
- They do not settle line-end hyphens (one glyph, U+002D, for syllable breaks and compound
  hyphens), nor where a footnote that is referenced twice should go.
- The PDF is tagged: its own structure holds the complete headings and places each footnote after
  the element that references it, and Poppler can read that structure too.
- Recommendation: leave the frozen corpus as it is; any parser change is a new corpus version
  with its own run.

## Question and scope

The pilot reads each commentary with `pdftotext -enc UTF-8 - -` and takes all structure from
the text: a page per form feed, a section from the last numbered heading line, footnotes wherever
Poppler prints them (`corpus.py`). Its README lists two consequences under Limitations: heading
continuation lines are missing from section titles, and the footnote list of HDS positions of
section 2.3 appears as section 2.4 passages on July p. 4. The question here: what do pdfplumber's
coordinates (x0, top, x1, bottom, font name and size of every character) recover in these two
cases, and what could a parser still not decide? Input is the commentary of the 2026-07-01
edition only.

## Method and versions

- **Input.** The `commentary_pdf` of edition 2026-07-01 in `data/manifests/bag-al.json`, read
  once and checked against the manifest's SHA-256
  `fe1856df9f7d0023aac52e13dc61a0055a7105b4810f18cc8822366625af5105` before use; 8 pages, A4
  (595.32 by 841.92 pt).
- **Poppler side, as the pilot does it.** The same bytes on stdin to
  `pdftotext -enc UTF-8 - -`, pages split at form feeds, every line NFC-normalised with
  whitespace folded, empty lines dropped. All 29 July passages of the frozen record
  (`tools/commentary_rag/results/2026-11-14-retrieval-corrected.json`) were found in that text
  by their text SHA-256: the probe sees exactly the text the frozen corpus was cut from and can
  name the passage that holds any word, without the e5 model.
- **pdfplumber side.** The same bytes. Lines as `extract_text_lines` groups them; a line's main
  font is its most frequent font and size. A superscript candidate is a character at most 0.75 of
  its line's main size; its lift is the line's baseline (median bottom of the main-font
  characters) minus the candidate's bottom. A thin rule is a filled rectangle at most 1 pt high
  and at least 20 pt wide. A heading line is bold and larger than the page's most frequent size.
  Coordinates are PDF points from the page's top left corner.
- **Tags apart.** The PDF's marked content and structure tree are reported separately from the
  geometry.
- **Versions.** Python 3.13.12; pdfplumber 0.11.11, pdfminer.six 20260107, pypdfium2 5.15.2,
  Pillow 13.0.0, in an ephemeral `uv run --no-project` environment (added to no
  `pyproject.toml` or lock); Poppler `pdftotext` 26.02.0, the version recorded in the frozen run.

## Case 1: the continued heading of section 2.5 (PDF page 6, printed "Seite 6 von 8")

"Continued heading" here means a numbered heading whose text runs on over further lines. The
heading of section 2.5 has five.

**What the pilot gets.** Poppler prints line 0
`2.5 Position 1368.00 « Neugeborenen-Screening auf Phenylketonurie, Galaktosämie,` and, as
line 1, the other four lines joined: it joins a line that ends in a hyphen with the next and drops
the hyphen (`Me-`, `Ahorn-`, `Im-`). The heading rule takes line 0 as the title, so the
`section_title` of all six 2.5 passages (`2026-07-01/p6/s2.5/1` to `/5` and
`2026-07-01/p7/s2.5/1`) is the first line only: 7 of the title's 32 words. Both lines open the
text of `p6/s2.5/1`, so the words are in the corpus, under a cut title.

**What the coordinates show.**

| Lines | top (pt) | x0 (pt) | Font and size |
|---|---|---|---|
| heading line 1, `2.5 Position 1368.00 ...` | 67.27 | 103.08 | Arial-BoldMT 11.04 |
| heading lines 2 to 5 | 79.87, 92.46, 105.18, 117.78 (bottom 128.82) | 121.08, 121.08, 121.06, 121.05 | Arial-BoldMT 11.04 |
| first body line | 137.16 (8.34 below) | 85.08 | ArialMT 9.96 |

They recover the heading's extent: five consecutive lines in the heading font (bold 11.04 pt
against the 9.96 pt body), set with a hanging indent (number at 103.08, continuation at 121.08)
and followed by the body font. Joined, the lines give the complete title of 32 words, ending in
`»: Anpassung des Tarifs`.

The same reading over every numbered heading of the document (probe on pages 3 to 8):

| Section | Lines | Pilot title | Passages with this title |
|---|---|---|---|
| 2.1 | 2 | first line only, 10 of 11 words | 3 |
| 2.2 | 2 | first line only, 7 of 13 words | 2 |
| 2.3 | 2 | first line only, 5 of 10 words, plus the footnote number `1` | 2 |
| 2.4 | 2 | complete | 8 |
| 2.5 | 5 | first line only, 7 of 32 words | 6 |
| 2.6, 4.1, 4.2 | 1 each | complete | 1 each |
| 3.1 | 2 | complete | 4 |

So 13 of the 29 July passages carry a cut title. Section 2.4 shows why the others are complete:
its heading wraps as well, but the first line ends in `Kostendämp-`, so Poppler joins it with
`fung` and the pilot's one line holds the whole title (3.1 likewise, `Karzi-` and `noms`).
The four cut titles wrap after a word without a hyphen. The H1 headings 2, 3 and 4 have no text of
their own: no frozen passage is labelled with them, and on p. 3 and p. 7 the H1 line opens the
first passage of 2.1 and 3.1. The title is more than metadata: the request builder in
`generation.py` passes `section` and `section_title` to the model as `abschnitt` and
`abschnittstitel`, and the search tool (`evidence_search.py`) returns passages in the same form.

**What stays ambiguous.**

- **Line-end hyphens.** The three breaks inside the 2.5 heading end in U+002D, the code point and
  font of an ordinary hyphen. On pages 3 to 8 pdfplumber finds 65 lines ending in a hyphen, all
  U+002D; 60 continue with a lowercase letter, 5 do not. Poppler drops the hyphen every time (no
  Poppler line on these pages ends in `-`). For 4 of the 5 that is wrong
  (`NeugeborenenScreening` on p. 6, `Vitamin-DAnalysen` p. 5, `Tyrosinkinase-1Receptor` p. 3,
  `ExcelFormat` p. 8), for one it is right (`EAMGK-MiGeL`, p. 3, where `Mi-` and `GeL` are
  one word). A rule that keeps the hyphen before an uppercase letter repairs the four and breaks
  `MiGeL`; the 60 lowercase cases were not checked one by one. Neither coordinates nor glyphs
  decide this, and the tagged text keeps every such hyphen (`Me-dium`, `Kostendämp-fung`).
- **The size rule does not transfer.** Here Arial-BoldMT 11.04 is H2 and nothing else (899
  characters, all tagged H2), but bold 14.04 serves the H1 headings (97 characters) and the title
  page (89), and bold 12.0 the table of contents. A heading rule needs the pilot's existing
  exclusions (front matter, table of contents) and offers no threshold that carries over to
  another document.
- **Boundaries between headings.** An H1 line directly followed by an H2 line (`2.` then
  `2.1`) is told apart only by the size change and the number at the start of the line. The
  continuation lines here happen to start without a section number (`1653.00, ...` in 2.2 does
  not match the pattern); that is a property of these headings, not a rule.

## Case 2: the displaced footnote on PDF page 4 (printed "Seite 4 von 8")

Footnote 1 lists 132 AL position codes (`6203.56` to `6501.60`), the HDS positions whose
reference document section 2.3 updates. It is referenced twice, both times in section 2.3.

**What the pilot gets.** Poppler prints the page in this order: the 2.4 text, the footnote's eleven
lines (Poppler lines 25 to 35), its number `1` alone (line 36), footnote 2 (line 37) and its
number `2` (line 38). Everything after the 2.4 heading on the page becomes section 2.4. The 132
codes are words 397 to 529 of the page and fall into three 2.4 passages, cut at words because the
list has no sentence end:

| Passage | Words of the page | Split, tokens | Codes of footnote 1 |
|---|---|---|---|
| `2026-07-01/p4/s2.4/3` | 373 to 440 | word, 252 | 43, after the last sentence of 2.4 itself (supplements 4707.10 and 4707.20) |
| `2026-07-01/p4/s2.4/4` | 440 to 490 | word, 254 | 50 |
| `2026-07-01/p4/s2.4/5` | 490 to 542 | word, 226 | 39, then `1`, footnote 2 and `2` |

The two references are in `p4/s2.3/1` (the heading, Poppler word 14) and `p4/s2.3/2`
(Poppler word 163). The title of both 2.3 passages carries the number as a word:
`Positionen 1 mittels`.

**What the coordinates show.**

- **Footnote zone.** A rule from x 85.08 to 229.08 (144.00 pt wide, at most 1 pt high) at top
  643.44, 19.95 pt below the last body line (bottom 623.49). Below it only ArialMT 8.04 (body
  9.96): footnote 1 on eleven lines from top 655.76 to bottom 756.67, footnote 2 on one line from
  top 762.92.
- **Footnote numbers.** ArialMT 5.04 at x0 85.08, the start of each footnote line (`1` at top
  655.76, lift 3.97 pt; `2` at top 762.92, lift 3.98 pt).
- **In-text references, raised and small.** `1` in Arial-BoldMT 6.96 at x0 326.04, top 96.82,
  lift 5.49 pt above the 11.04 pt heading line; `1` in ArialMT 6.48 at x0 395.28, top 310.51,
  lift 4.11 pt above a 9.96 pt body line (`Positionen1 angepasst`); `2` in ArialMT 6.48 at x0
  336.48, top 411.79, lift 4.13 pt.
- **Section of each reference.** The last heading that starts above it: both `1`s lie above the
  2.4 heading (top 354.55), in 2.3; the `2` lies below it, in 2.4.

So the coordinates recover that footnote 1 belongs to section 2.3, while the pilot files its text
under 2.4; footnote 2 is filed under its own section. The other footnotes of the document stay in
their section too, but not in the passage that references them, because Poppler prints each
footnote at the end of its page:

| Footnote | Reference in | Footnote text in | Section by layout, by pilot |
|---|---|---|---|
| 1 (p. 4) | `p4/s2.3/1`, `p4/s2.3/2` | `p4/s2.4/3`, `/4`, `/5` | 2.3, 2.4: displaced |
| 2 (p. 4) | `p4/s2.4/1` | `p4/s2.4/5` | 2.4, 2.4 |
| 3 (p. 5) | `p5/s2.4/2` | `p5/s2.4/3` | 2.4, 2.4 |
| 4 (p. 6) | `p6/s2.5/3` | `p6/s2.5/5` | 2.5, 2.5 |

The reading order differs by tool. Poppler prints each footnote number on its own line after the
footnote text (p. 4 lines 36 and 38, p. 5 line 51, p. 6 line 35); pdfplumber's line puts it first
(`1 6203.56, ...`, `2www.bag.admin.ch ...`); the tag tree places the note of footnote 1
directly after the 2.3 heading and before the first paragraph of 2.3, and the notes of footnotes 2
and 4 directly after the paragraph that references them.

**What stays ambiguous.**

- **Where a footnote goes.** Footnote 1 is referenced from the heading and from the last sentence
  of 2.3, which are different passages. Whether its 132 codes become a passage of their own,
  context of one 2.3 passage, or part of both is a corpus design decision the coordinates do not
  make. In the tag tree only the heading's reference is a link to the note; the `1` in the body
  is a plain span.
- **A superscript is not always a reference.** `quater` in `Buchstabe bquater KLV` (twice on
  p. 3) has the same size (6.48) and lift (4.13 pt) as the body references. Of the seven
  superscript candidates outside the footnote zones of this document, five are digits with a
  footnote of that number below a rule on the same page; the other two are `quater`. The digit
  test works here; an exponent, or a superscript digit without a footnote, would need another rule.
- **Which thin rule is the separator.** The three separators (p. 4 at top 643.44, p. 5 and p. 6 at
  741.36) are 144.00 pt rules starting at x 85.08. The two link underlines also start at the
  margin (p. 6 at x 85.08, 229.44 pt wide; p. 4 at 87.84, 67.68 pt wide) but lie inside a text
  line, under characters tagged as links; the 36 table rules on p. 5 have body-size text below.
  "No text line at the rule, only smaller text below" separates them here; the 144 pt width is a
  property of this Word template.
- **Footnotes across pages.** None of the four footnotes continues on the next page; that case is
  untested.

## Tags, kept apart from the geometry

The PDF is tagged (`pdfinfo`: `Tagged: yes`, creator `Acrobat PDFMaker 26 pour Word`; the
January 2026 commentary is tagged as well, `Acrobat PDFMaker 24 pour Word`). pdfplumber exposes
the marked content of every character and the document's structure tree:

- every Arial-BoldMT 11.04 character is tagged H2, the in-text references are spans, footnote
  paragraphs are P and the page footers are artifacts;
- the H2 elements hold the complete headings, for example
  `2.3 ... Positionen1 mittels Hochdurchsatz-Sequenzierung: Aktualisierung des Referenzdokumentes «Bonnes Pratiques»`
  and all 32 words of 2.5, with the hyphens of the line breaks kept;
- the Note elements follow the element that references them, as described above.

In pdfplumber 0.11.11, `page.structure_tree` raises `KeyError('P')` on pages 4 and 6 of this
file; the document-level `pdf.structure_tree` works, and the probe uses only that. Poppler reads
the same structure without a new dependency: `pdfinfo -struct-text` prints the tree with its
text (the 2.3 heading with its `1` as a link, then the note), and `pdftohtml -xml` reports font
sizes (in pixels at its default zoom of 1.5, rounded: 17 for the 11.04 pt headings, 15 for the
9.96 pt body), bold markup and positions. Both were checked by hand on this file (`pdftohtml` on
page 4 only); the probe does not use them.

## Recommendation

1. **Leave the frozen corpus as it is.** The probe changes nothing: `corpus.py`,
   `retrieval.py` and `tools/commentary_rag/results/` are untouched, and `corpus.py` still has
   the SHA-256 (`38a1572daf52...`) recorded in the corrected 2026-11-14 run and in the 2026-11-21
   comparison run. All Phase 2 and Phase 3 figures refer to that corpus.
2. **Treat any change to the parsing as a new corpus version**: new passage IDs, text hashes, token
   counts and splits, built and evaluated as a run of its own on the frozen cases and compared
   with the frozen record, never as an edit of the existing corpus. It is worth doing only if a
   later phase needs better section titles or footnote attribution.
3. **If such a version is built,** take headings and footnote placement from the tags where a PDF
   has them (both commentaries do), check them against the geometry (heading font and hanging
   indent; rule, smaller type and footnote numbers), and make the hyphen decision an explicit,
   tested rule with a short exception list, since neither source settles it. Poppler
   (`pdfinfo -struct-text`, `pdftohtml -xml`) already provides both signals; if pdfplumber is
   used instead, pin it together with pdfminer.six and keep `page.structure_tree` out of the path.
4. **Measure what changes in that run** rather than assume it: complete titles on the 13 passages
   above, the 132 codes of footnote 1 under section 2.3, footnote numbers out of the passage text
   (`Positionen 1 mittels` and the trailing `1`, `2`, `3`, `4`), and retrieval on the
   frozen cases against the frozen record.

## Reproduce

From a checkout that holds the git-ignored BAG PDFs under `data/raw/`, at the repository root:

```bash
# The probe on the two cases; it refuses on a hash mismatch. The pins are the versions used here.
uv run --no-project --with pdfplumber==0.11.11 --with pdfminer.six==20260107 \
  --with pypdfium2==5.15.2 --with pillow==13.0.0 \
  python tools/commentary_rag/layout_probe.py --edition 2026-07-01 --pages 4,6
# All content pages: the heading table, footnotes 3 and 4, the hyphen census.
uv run --no-project --with pdfplumber==0.11.11 --with pdfminer.six==20260107 \
  --with pypdfium2==5.15.2 --with pillow==13.0.0 \
  python tools/commentary_rag/layout_probe.py --edition 2026-07-01 --pages 3,4,5,6,7,8
# Diagnostic crops, into a git-ignored folder only (never commit them).
uv run --no-project --with pdfplumber==0.11.11 --with pdfminer.six==20260107 \
  --with pypdfium2==5.15.2 --with pillow==13.0.0 \
  python tools/commentary_rag/layout_probe.py --edition 2026-07-01 --pages 4,6 \
  --crops tools/commentary_rag/local/2026-11-22-pdfplumber
# Without pdfplumber, in the pilot's environment, the probe refuses with exit code 2.
UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" uv run --project services/ingestion \
  --frozen --extra ai --extra dev python tools/commentary_rag/layout_probe.py --edition 2026-07-01 --pages 4,6
# Poppler's own view of the tags and fonts, and the hash of the corpus code.
PDF="data/raw/bag/al/2026-07-01/Kommentar zu den Änderungen des Anh. 3 KLV per 01.07.26_final.pdf"
pdfinfo "$PDF"
pdfinfo -struct-text "$PDF"
pdftohtml -xml -i -q -f 4 -l 4 -stdout "$PDF"
shasum -a 256 tools/commentary_rag/corpus.py
```

## Limits

- One document, the July 2026 commentary. The January commentary was not probed; only its tagging
  was read.
- The thresholds (0.75 of the line size, rules at most 1 pt high and at least 20 pt wide, bold and
  larger than the body) were set on this document and checked against all its pages, not tested
  on any other.
- pdfplumber's line grouping and its page-level structure-tree failure are those of version
  0.11.11.

## Files

- Committed: `tools/commentary_rag/layout_probe.py`, the probe (the pilot does not import it; it
  needs pdfplumber in a throwaway environment and exits with code 2 without it), and this page.
- Local and git-ignored: nine PNG crops of the reported regions in
  `tools/commentary_rag/local/2026-11-22-pdfplumber/` (the headings 2.3, 2.4 and 2.5, the
  footnote zones of p. 4 and p. 6, and the lines holding the references). The probe's text output
  is not committed; the commands above reproduce it.
