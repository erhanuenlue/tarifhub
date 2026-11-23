# Phase 4 data feasibility: the ten 2021 to 2023 BAG commentaries and the fourteen-document inventory

Inventory of 2026-11-23 for Phase 4 variant 2, fine-tuning the multilingual-e5 embedder of the
commentary retrieval. It carries out the second option of the decision Erhan took on
2026-11-23 in milestone [#62](https://github.com/erhanuenlue/tarifhub/issues/62): measure the ten
earlier BAG change commentaries before deciding whether to fine-tune. It extends the
[training-data inventory](2026-11-23-phase4-training-data-inventory.md) of the four 2024 and 2025
commentaries and applies the rules of that page and of the
[feasibility assessment](2026-11-22-phase4-finetuning-feasibility.md). Nothing was trained, no
provider, model API or GPU was called and nothing was spent (budget USD 0): the ten commentaries
were downloaded from the BAG, verified, parsed with the pilot's parser unchanged and counted offline,
with the e5 tokenizer only for the token budget. The frozen 2026 corpus, its run records, the
ledgers, ratings and every earlier result are unchanged; no evaluation case, gold evidence, rating or
trace was read for the count. The decision on what follows is Erhan's.

<!-- verdict: written after the count -->

## Sources

The ten commentaries as the BAG lists them on its page of the Analysenliste (retrieved 2026-11-23),
each re-downloaded on 2026-11-23 from the link below and identical, by SHA-256, to the copy of the
preliminary screen. They are pinned in the commentary-source manifest
`data/manifests/bag-al-commentaries-2021-2023.json`; the corpus builder refuses a source whose
bytes differ from its hash or whose declared title is not on its page 1. The BAG labels the second
source of 1 January 2023 "Kommentar zu den dringenden Änderungen der AL vom 21. Dezember 2022 per 1.
Januar 2023" and the source of 1 March 2023 a commentary on extraordinary changes.

| Source ID | Effective dates | Title on page 1 | Pages | SHA-256 | Source |
|---|---|---|---|---|---|
| `2021-02-01` | 2021-02-01 | Erläuterungen zu den zusätzlichen Änderungen des Anhangs 3 der Krankenpflege-Leistungsverordnung (KLV) per 1. Februar 2021 (AS 2021 44, Nr. 11 vom 26. Januar 2021) | 3 | `a7c96207da38…` | [PDF](https://www.bag.admin.ch/dam/de/sd-web/wSAkNxpS90s5/KLV-Aenderungen_Anh_3_Erlaeuterungen_01.02.2021_Publikation_DE_DEF.pdf) |
| `2021-07-01` | 2021-07-01 | Erläuterungen zu den Änderungen des Anhangs 3 per 1. Juli 2021 (AS 2021 392 vom 25 Juni 2021) | 4 | `c76525fc43e0…` | [PDF](https://www.bag.admin.ch/dam/de/sd-web/M7xIXAXqhTFl/kommentar-zu-den-aenderungen-per-01.07.2021-des-anhangs-3-der-klv.pdf) |
| `2022-01-01` | 2022-01-01, 2022-02-01 | Kommentar zu den Änderungen des Anhang 3 (Analysenliste, AL) der Krankenpflege-Leistungsverordnung (KLV) vom 1. Dezember 2021 per 1. Januar 2022 und 1. Februar 2022 (AS 2021 885 und 886, Nr. 203 vom 17. Dezember 2021) | 5 | `b78ec1085364…` | [PDF](https://www.bag.admin.ch/dam/de/sd-web/e5D8kW3qmfPg/kommentarzudenaenderungenanhang3per01012022.pdf) |
| `2022-07-01` | 2022-07-01 | Kommentar zu den Änderungen des Anhang 3 KLV vom 2. Juni 2022 per 1. Juli 2022 (AS 2022 369 vom 23. Juni 2022) | 6 | `2e6597805068…` | [PDF](https://www.bag.admin.ch/dam/de/sd-web/eGN04VvYS3vy/kommentar-aenderungen-al-01072022.PDF) |
| `2022-08-01` | 2022-08-01 | Kommentar zu den Änderungen des Anhangs 3 KLV vom 2. Juni 2022 per 1. August 2022 (AS 2022 371 vom 23. Juni 2022) | 3 | `54035bcea99d…` | [PDF](https://www.bag.admin.ch/dam/de/sd-web/RlJy7aAqUU6f/kommentar_aenderungen_al_010822.pdf) |
| `2023-01-01` | 2023-01-01 | Kommentar zu den Änderungen des Anhang 3 KLV vom 28. November 2022 per 1. Januar 2023 (AS 2022 840 vom 22 Dezember 2022) | 5 | `84e9faeba521…` | [PDF](https://www.bag.admin.ch/dam/de/sd-web/w7OsaUM9LIwQ/alkommentaraenderungenper01012023.pdf) |
| `2023-01-01-urgent` | 2023-01-01 | Kommentar zu den Änderungen des Anhang 3 KLV vom 21. Dezember 2022 per 1. Januar 2023 (AS 2022 858 vom 27. Dezember 2022) | 3 | `cea4474d4e30…` | [PDF](https://www.bag.admin.ch/dam/de/sd-web/1nkLkL726ycP/alkommentardringendeaenderungenper01012023.pdf) |
| `2023-03-01` | 2023-03-01 | Kommentar zu den Änderungen des Anhang 3 KLV vom 27. Januar 2023 per 1. März 2023 (AS 2023 75, Nr. 27 vom 17. Februar 2023) | 3 | `46df5eae462b…` | [PDF](https://www.bag.admin.ch/dam/de/sd-web/GGUmWtf3tYik/klv_anh3_kommentar_aenderungen_010323.pdf) |
| `2023-07-01` | 2023-07-01 | Kommentar zu den Änderungen des Anhang 3 KLV vom 16. Juni 2023 per 1. Juli 2023 (AS 2023 313 vom 23. Juni 2023) | 4 | `3757f895997a…` | [PDF](https://www.bag.admin.ch/dam/de/sd-web/kTgiv8VUDAIm/kommentar_aenderungen_anh3_010723.pdf) |
| `2023-11-01` | 2023-11-01 | Kommentar zu den Änderungen des Anhang 3 KLV vom 17. Oktober 2023 per 1. November 2023 (AS 2023 603 vom 25. Oktober 2023) | 4 | `23247baa8e6e…` | [PDF](https://www.bag.admin.ch/dam/de/sd-web/ugLbCOyBn6Rt/kommentar-aenderungen-al-01112023.pdf) |

## Source identity

The pilot's corpus builder keys every passage and section by the edition date of the ingestion
manifest, and that manifest admits one commentary per edition, needs each edition's full list and
refuses a repeated date. Two of the ten do not fit: the regular and the urgent commentary of 1
January 2023 share a date, and one commentary covers 1 January and 1 February 2022. The smallest
change that represents them faithfully is a separate, commentary-only manifest (`kind`
`commentary_sources`) read by a new `corpus.build_commentaries`: each PDF has a **source ID** that
begins with its first effective date (`2023-01-01` and `2023-01-01-urgent`; `2022-01-01` with the
dates 2022-01-01 and 2022-02-01, counted once), verified by the ingestion loader's own read and parsed
by the same parser, which puts the source ID where it puts the edition date. Passage IDs are
`<source ID>/p<page>/s<section>/<n>`, sections are keyed `<source ID>/<section>`, and the inventory's
per-source tallies are keyed by source ID. A repeated source ID, path, hash or JSON key is refused by
the manifest, and a repeated source or passage ID by the merge of two corpora, so no passage, section
or output row of one source can collide with another's. The original four-document command is
unchanged: re-run on 2026-11-23 from the branch, it writes the committed record
`results/2026-11-23-training-inventory.json` again, identical apart from its environment block.

## Rules for the older commentaries, fixed before counting

Written after the parse, the page inspection and the named-project scan, and committed before the
count of the record named under [Files](#files). One disclosure: a smoke run of the new tool on the
real PDFs, made before these rules and before the inspection annotations existed, printed a
provisional total per view; the lead saw those totals and nothing else of it. The rules below follow
from the inspection and the scan; none was changed after the count.

Rules 1 to 10 of the [training-data inventory](2026-11-23-phase4-training-data-inventory.md#rules-fixed-before-counting)
apply unchanged: the frozen 2026 reference, the 256-token chunking with the e5 tokenizer, the
explicit `dddd.dd` codes, the families, the whole-family exclusion against the 2026 material, the
counts, the threshold and the duplicate check, with every sensitivity. They are extended as follows.

11. **Material and identity.** The ten commentaries of the commentary-source manifest, each under its
    source ID. A source that covers two dates is one source; two sources of one date are two.
12. **Unresolved sources.** A source that the unchanged parser cannot section (it reads no numbered
    heading, so its body text is dropped as front matter) is unresolved: it is left out of every count
    and grouping and listed, never counted as zero, and its possible contribution is bounded apart.
13. **Combined sections.** Where the parser files printed subsections under their parent section
    (headings printed "2.1." with a trailing dot, or with the number on a line of its own), rule 2
    keeps the section as the parser files it: one section, whose passages stay usable, since no text
    leaves the top-level section it belongs to. Two sensitivities, which run only in the new views,
    bracket the effect, using the 25 subsection annotations of the inspection (exact text and printed
    subsection): **printed sections** counts each annotated fragment under its printed subsection,
    text left with the parent section decides nothing unless it names a code or a project, and a
    passage whose parts fall in two families is not eligible; **subsection text as misfiled** applies
    rule 3 to that text, so a passage carrying subsection text that names a code or a project is not
    usable.
14. **Named projects.** Rule 5 applied to the ten texts. The only existing project they name is
    transAL (2022-08-01 section 2.1, which also names transAL-2); the round table and StAR do not
    occur. One alias is added: `transAL1` and `transAL2`, the spelling the text extraction gives
    when a line break drops the hyphen, counted as transAL (with the phases apart, as transAL-1 and
    transAL-2). Not projects: "eine Revision der Analysenliste" (a description of transAL in the same
    sentence), the structure of the AL in force since 1 January 2021 (the list itself, a document),
    "lineare Tarifsenkung", "Übergangstarif" and "Tarifüberprüfung" (generic words, all in the
    transAL section), a Health Technology Assessment (the assessment of one analysis, and its report),
    the Covid-19 ordinance 3 and the Covid-19 law, the federal coverage of test costs and measures
    against the pandemic (unnamed arrangements), pilot projects and a continuing-education programme
    (generic), the reference document (a document), DRG and the evaluation of positions. Neither the
    alias nor any candidate occurs in the four 2024 and 2025 commentaries, so the published count is
    unaffected.
15. **Views.** **Baseline**: the four 2024 and 2025 commentaries, as published. **Older**: the ten
    alone, their families formed among themselves. **Combined**: all fourteen, the families rebuilt
    transitively across every source and each family that shares a code or a project with the 2026
    reference dropped as a whole. Merging sections can only join families, so a baseline passage can
    only lose eligibility in the combined view; every change is listed with the codes or projects that
    link the older sections in and those that cause the exclusion. The threshold (rule 9) is applied
    to the combined view.
16. **Code forms.** Rule 4 is unchanged: 2022-07-01 section 2.2 writes 1774, 1775 and 1776 without
    decimals and so names no code (none of these numbers occurs in the 2026 commentaries); its
    section 2.1 holds the wildcards `xxxx.00` and `xxxx.10`, which count in the ranges sensitivity;
    the dash range 1901.00 to 1901.40 of section 2.6 is read by its two end codes, and no 2026 code
    lies inside it.

## Parse and page inspection

The parser ran unchanged on all ten sources and refused none: every printed page label matched its
page. The inspection compared its output with the original pages in three ways: a coverage check of
every Poppler line against the passages of its page, the
[layout probe](2026-11-22-pdfplumber-layout-probe.md) (pdfplumber 0.11.11 in an ephemeral
environment; on 2023-07-01 and 2023-11-01 its tag outline fails inside pdfplumber, so that one
function was bypassed, and the two unresolved sources have no passage to probe), and renders of all
40 pages, each checked by eye (the inspection worker read every page; the lead re-checked the
deciding pages). Renders, probe reports and the inspection notes stay local.

| Source | Pages (without passages) | Passages | Sections as the parser files them | Finding |
|---|---|---|---|---|
| `2021-02-01` | 3 (3) | 0 | none | **unresolved**: unnumbered headings, body text of page 3 dropped |
| `2021-07-01` | 4 (4) | 0 | none | **unresolved**: unnumbered headings, body text of pages 3 and 4 dropped |
| `2022-01-01` | 5 (2) | 11 | 1, 2, 3.1, 4.1 | subsections 2.1 to 2.5 combined under 2 |
| `2022-07-01` | 6 (2) | 17 | 1, 2.1 to 2.7, 3.1 to 3.3 | as printed |
| `2022-08-01` | 3 (2) | 3 | 1, 2.1 | as printed |
| `2023-01-01` | 5 (2) | 14 | 1, 2.1 to 2.4, 3.1, 4.1 | as printed |
| `2023-01-01-urgent` | 3 (2) | 4 | 1, 2 | its only subsection 2.1 filed as 2 (label only) |
| `2023-03-01` | 3 (2) | 3 | 1, 2 | its only subsection 2.1 filed as 2 (label only) |
| `2023-07-01` | 4 (2) | 8 | 1, 2 | subsections 2.1 to 2.3 combined under 2 |
| `2023-11-01` | 4 (2) | 5 | 1, 2.1 | as printed |
| **Ten** | 40 (23) | 65 | | |

- **Unresolved.** The two 2021 commentaries ("Erläuterungen", not "Kommentar") use unnumbered bold
  headings, which the parser does not read, so it starts no section: their whole body (13 lines on page
  3 of 2021-02-01; 52 lines on pages 3 and 4 of 2021-07-01) is dropped as front matter and they yield no
  passage. They are unresolved under rule 12, not empty. Their dropped text names one change in
  2021-02-01 (4700.00 and 4707.00) and seven in 2021-07-01 (among them 6605.64, 1734.00, 1734.01 and
  3186.00); of all these codes only 4700.00 is among the 167 codes of 2026.
- **Combined sections.** 2022-01-01 prints its subsection headings "2.1." to "2.5." with a trailing dot,
  and 2023-07-01 sets the numbers 2.1 to 2.3 on a line of their own (for 2.3 after the heading text);
  the parser reads neither form, so it files five and three changes under section 2, in 7 passages
  each, and some passages carry text of two subsections. No text is lost: the heading lines stay in the
  passage text. In 2023-01-01-urgent and 2023-03-01 the same happens to the only subsection 2.1 of
  section 2, which changes the label, not the grouping. Rule 13 and its two sensitivities apply.
- **Continued headings.** As for 2024 to 2026, a heading over several lines keeps its first line as
  the section title and the rest in the passage text (up to nine lines, 2022-07-01 section 2.5);
  2023-01-01 section 2.3 keeps a word split by a hyphen ("hämatopoeti- sche"). No body line was read as
  a heading.
- **Footnotes.** None on any of the 40 pages, so no footnote text is filed under a wrong section, and no
  passage is misfiled or unusable in the sense of rule 3.
- **Not material.** Where a line ends in a hyphen before a capitalised word, the extraction drops the
  hyphen (`SARS-CoV2`, `Covid-19Verordnung`, `transAL2`, rule 14); list bullets stand on their own
  lines; one long sentence of 2023-01-01 section 4.1 is split between words by design. Every body line
  of the eight parsed sources lies in a passage, and no passage crosses a page.

<!-- counts: written after the count -->
