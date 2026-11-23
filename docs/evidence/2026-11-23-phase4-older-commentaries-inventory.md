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

**Verdict on the training data: the threshold is not met.** The parser sections eight of the ten
commentaries into 65 passages; the two of 2021 are unresolved (rule 12). Alone, the ten give 21
eligible passages in 13 families. All fourteen commentaries of 2021 to 2025 together, with the
families rebuilt across every source and each family that touches the frozen 2026 material dropped as
a whole, give **44 eligible passages in 22 families**: 56 passages short of the proposed 100, while the
family requirement (at least 10) is met with 12 to spare. The figure of about 87 on the
[earlier page](2026-11-23-phase4-training-data-inventory.md#shortfall-and-the-next-sources) was a
forecast at the 2024 and 2025 yield; the measured count is 43 lower. Six of the 30 passages counted
there no longer count, because older sections link their families to the 2026 material, and one older
passage drops the same way. Every rule variant stays between 41 and 54 eligible passages, the two
unresolved commentaries might add about 15 at the busiest page yield seen, and only with no family excluded at all would the
fourteen reach 108. **The evaluation limitation is unchanged:** training material adds no independent
2026 evaluation family, so a comparison stays exploratory, with question-level results descriptive
only ([What the evaluation could establish](#what-the-evaluation-could-establish)).

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
from the inspection and the scan; none was changed after the count. After the independent review,
the printed-sections reading of rule 13 was corrected to follow the rule as written (every subsection
fragment of a passage decides its family) and the record was regenerated; the primary counts did not
change.

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

## Counts

### Three views

| View | Sources (unresolved) | Passages | Introductions | Usable | Families | Dropped families (usable passages) | Eligible families | Eligible passages |
|---|---|---|---|---|---|---|---|---|
| Baseline: the four of 2024 and 2025, reproduced | 4 | 56 | 4 | 52 | 18 | 4 (22) | 14 | **30** |
| Older: the ten of 2021 to 2023 alone | 10 (2) | 65 | 8 | 57 | 19 | 6 (36) | 13 | **21** |
| Combined: all fourteen | 14 (2) | 121 | 12 | 109 | 28 | 6 (65) | 22 | **44** |

A family is counted once however many sources it spans. The duplicate check (rule 10) finds no older
passage outside the introductions that repeats 2026 text; six of the eight older introductions are
identical to the 2026 introductions and two share 83 % of their word 8-grams with them, and
introductions are never eligible. In the combined view the one usable duplicate is the July 2025
passage of the earlier inventory, in a dropped family as before.

### Per source

| Source | Pages | Passages | Usable | Eligible in its own view | Eligible in the combined view |
|---|---|---|---|---|---|
| `2021-02-01` | 3 | 0 | 0 | unresolved | unresolved |
| `2021-07-01` | 4 | 0 | 0 | unresolved | unresolved |
| `2022-01-01` | 5 | 11 | 10 | 3 | 3 |
| `2022-07-01` | 6 | 17 | 16 | 10 | 10 |
| `2022-08-01` | 3 | 3 | 2 | 0 | 0 |
| `2023-01-01` | 5 | 14 | 13 | 6 | 5 |
| `2023-01-01-urgent` | 3 | 4 | 3 | 0 | 0 |
| `2023-03-01` | 3 | 3 | 2 | 2 | 2 |
| `2023-07-01` | 4 | 8 | 7 | 0 | 0 |
| `2023-11-01` | 4 | 5 | 4 | 0 | 0 |
| **Ten older** | 40 | 65 | 57 | 21 | 20 |
| `2024-01-01` | 6 | 16 | 15 | 11 | 6 |
| `2024-07-01` | 6 | 20 | 19 | 9 | 9 |
| `2025-01-01` | 4 | 10 | 9 | 8 | 7 |
| `2025-07-01` | 5 | 10 | 9 | 2 | 2 |
| **Four of 2024 and 2025** | 21 | 56 | 52 | 30 | 24 |
| **Fourteen** | 61 | 121 | 109 | 51 | **44** |

"Own view" is the older view for the ten and the baseline view for the four; their sums, 51 passages
in 27 families, are what the two sets would give if they did not share families.

### Families of the ten older commentaries (older view)

| Family | Sections (source/section) | Usable passages | What the sections cover | Shared with 2026 | Result |
|---|---|---|---|---|---|
| F01 | 2022-01-01/2; 2022-07-01/2.1; 2023-01-01-urgent/2; 2023-07-01/2; 2023-11-01/2.1 | 23 | SARS-CoV-2 positions with the order and presence fees, troponin, HIV resistance, andrology, immunohaematology, bacterial DNA and HLA typing: the combined sections 2 of 2022-01-01 and 2023-07-01, section 2 of the urgent commentary and the troponin change of November 2023, linked through SARS-CoV-2 and troponin codes | 1012.00, 1013.00, 1288.00, 1653.00, 1744.00, 1745.00, 4700.00, 6604.50 | dropped |
| F02 | 2022-01-01/3.1 | 2 | phosphatidylethanol (PEth) in the care of problematic alcohol use | none | eligible |
| F03 | 2022-01-01/4.1 | 1 | editorial corrections of 1297.00, 1375.00, 1532.00 and 1715.00 | none | eligible |
| F04 | 2022-07-01/2.2 | 1 | amyloid beta and tau proteins in cerebrospinal fluid (positions written 1774 to 1776, without decimals) | none | eligible |
| F05 | 2022-07-01/2.3 | 3 | methoxytyramine added to the metanephrines | none | eligible |
| F06 | 2022-07-01/2.4; 2023-01-01/2.2 | 4 | genetic positions: breast-cancer screening extended to preventive analyses, and the new reference document for rare genetic diseases | 22 codes, 6206.56 to 6299.62 | dropped |
| F07 | 2022-07-01/2.5 | 2 | the clinical immunology laboratory added to four positions (1530.00, 1531.00, 1636.00, 1637.00) and removed from five (1326.00, 1369.00, 1422.00, 6700.90, 6701.90) | none | eligible |
| F08 | 2022-07-01/2.6 | 1 | analysis material of 1901.00 to 1901.40 (rare metabolic diseases) | none | eligible |
| F09 | 2022-07-01/2.7 | 2 | limitations for vitamin D (1006.00) | 1006.00 | dropped |
| F10 | 2022-07-01/3.1 | 1 | poliovirus Ig (3147.00), editorial | none | eligible |
| F11 | 2022-07-01/3.2 | 1 | diphtheria toxin (3422.00), editorial | none | eligible |
| F12 | 2022-07-01/3.3 | 1 | Helicobacter pylori (3432.00, 3433.00), editorial | none | eligible |
| F13 | 2022-08-01/2.1 | 2 | linear tariff cut for all positions except the rapid analyses | transAL | dropped |
| F14 | 2023-01-01/2.1 | 1 | quantitative bacteriology (3344.00), its cumulation rule lifted | none | eligible |
| F15 | 2023-01-01/2.3 | 3 | new high-throughput sequencing positions for haematological neoplasms | none | eligible |
| F16 | 2023-01-01/2.4 | 2 | evaluation of limitations for vitamin B12 (1749.00) | 1749.00 | dropped |
| F17 | 2023-01-01/3.1 | 2 | pancreatic stone protein (PSP) | none | eligible |
| F18 | 2023-01-01/4.1 | 3 | a limitation added to four genetic positions: hereditary breast and ovarian cancer (6241.60), Lynch syndrome (6242.60), polyposis coli (6245.60) and retinoblastoma (6246.60), editorial | 6241.60, 6242.60, 6245.60, 6246.60 | dropped |
| F19 | 2023-03-01/2 | 2 | new positions 3191.00 and 3191.10 for the mpox virus | none | eligible |

F01 holds the two combined sections and the urgent commentary's section 2, which names the SARS-CoV-2
positions together with the order fee 4700.00, one of the 2026 codes. The 21 eligible passages lie in
13 families; four of them (F03, F10, F11, F12) are editorial corrections, weak material for German
retrieval questions, as in the earlier inventory.

### What combining the fourteen changes

Families are rebuilt transitively across all fourteen sources and the exclusion is applied again
(rule 15). Against the 51 passages in 27 families of the two separate views, the combined view loses 7
passages and 5 families; the tool checks each change and lists it in the record
(`eligibility_changes`, once for the baseline and once for the older view):

- **Six passages counted on the earlier page.** The SARS-CoV-2 family of January 2024 (2024-01-01
  section 2.1, 2 passages), its editorial family after the revised law on genetic testing (section
  4.1, 3 passages) and the troponin family of January 2025 (2025-01-01 section 2.2, 1 passage) join
  one combined family of 12 sections in 9 sources with 39 usable passages, together with the older
  families F01, F06 and F18 and the already dropped hereditary breast and ovarian cancer family of July
  2024. The links are the SARS-CoV-2 codes 3186.00, 3186.10, 3188.00 and 3189.00, the troponin code
  1734.01, the genetic codes 6206.55, 6241.55, 6241.56, 6241.60, 6247.55 and 6247.56, and 6603.50. The
  family shares 34 codes with the 2026 material: the immunohaematology positions 1012.00, 1013.00,
  1288.00, 1653.00, 1744.00 and 1745.00, the order fee 4700.00, 6604.50 and 26 codes of the series
  6206.56 to 6299.62, so it is dropped whole: three eligible families and six passages fewer.
- **One passage of the ten.** Quantitative bacteriology (2023-01-01 section 2.1, older F14) shares
  3330.00 and 3332.00 with the midwives' family of January 2024, which 2026 codes already exclude.
- **Two eligible families become one.** The clinical immunology section of July 2022 (older F07, 2
  passages) and the first-trimester test of July 2024 (1 passage) share 6700.90 and 6701.90 and stay
  eligible as one family of 3 passages.
- **No effect.** The transAL family takes in the linear tariff cut of August 2022 (2022-08-01 section
  2.1), and the hereditary breast and ovarian cancer family of July 2024 joins the combined family
  above; both were dropped already.

So 51 − 6 − 1 = 44 eligible passages and 27 − 3 − 1 − 1 = 22 eligible families. No eligibility
rises: merging can only join families.

### Sensitivities

Eligible passages and families per rule variant (rules 3 to 5 of the earlier page, rule 13 here):

| Variant | Baseline | Older | Combined |
|---|---|---|---|
| **Primary** | 30 / 14 | 21 / 13 | **44 / 22** |
| Every passage with misfiled text dropped | 29 / 14 | 21 / 13 | 43 / 22 |
| Range expressions against the 2026 codes | 27 / 13 | 21 / 13 | 44 / 22 |
| transAL phases counted apart | 31 / 15 | 21 / 13 | 44 / 22 |
| AL handbook counted as a named item | 28 / 13 | 21 / 13 | 42 / 21 |
| Strictest (misfiled, ranges and handbook) | 24 / 12 | 21 / 13 | 41 / 21 |
| Printed subsections (rule 13) | 30 / 14 | 30 / 17 | 54 / 26 |
| Subsection text read as misfiled (rule 13) | 30 / 14 | 20 / 13 | 43 / 22 |
| No family excluded (upper bound) | 51 / 18 | 57 / 19 | 108 / 28 |

The baseline column repeats the earlier inventory's seven variants exactly; the two rule-13 variants do
not touch it. Read by its printed subsections, the combined view gains 10 passages in 4 families: the
parser's combination of subsections in 2022-01-01 and 2023-07-01 is the largest extraction effect on
the count, and the most favourable reading still gives 54. The upper bound of 108 counts every usable
passage except the one duplicate, with no family excluded; the exclusion rule is what keeps the
training data apart from the 2026 test material.

### The two unresolved commentaries

2021-02-01 and 2021-07-01 are left out (rule 12): the unchanged parser yields no passage from them. Their
body covers three pages with one and seven changes. The one change of February 2021 names the order fee
4700.00, a 2026 code, so it would be dropped; in July 2021 the HLA genotyping (6605.64), troponin
(1734.00, 1734.01) and SARS-CoV-2 (3186.00) changes name codes of the dropped combined family. At the
highest yield any page of the parsed sources shows (5 passages), their three body pages would give
about 15 passages at most, an estimate rather than a count: even if every one of them were eligible,
the combined count would stay below 60 (about 69 with printed subsections).

## Threshold

| Requirement (proposed, a design choice of this project) | Measured, combined view | Margin |
|---|---|---|
| At least 100 eligible passages | 44 | **56 short** (44 %) |
| At least 10 eligible families | 22 | 12 above |

The [earlier page](2026-11-23-phase4-training-data-inventory.md#shortfall-and-the-next-sources) forecast
about 57 eligible passages from these 40 pages, about 87 in total, at the 2024 and 2025 yield of 1.4 per
page; it said so and called it an extrapolation, not a count. Measured, the ten yield 21 eligible
passages alone (0.53 per page), and combined they add 20 while 6 of the 30 earlier ones drop, a net
gain of 14: 44 in total, 43 below the forecast. The measured shortfall of 56 is the verdict. Every rule
variant stays at or below 54; the two unresolved commentaries are not counted, and even if their three
body pages yielded as much as the busiest parsed page (an assumption, not a bound), the total would stay
below about 69. The BAG publishes no change commentary before 2021. Other material (the BAG Bulletin before 2021, the
position texts of the AL full lists) is of another kind and would first need a decision that it counts
as the same training material.

## What the evaluation could establish

Unchanged by this inventory. The evaluation units are fresh questions on the 2026 commentaries, and
training material from earlier editions adds none: by the
[earlier assessment](2026-11-23-phase4-training-data-inventory.md#what-the-evaluation-could-establish),
questions are not shown to be independent, so per-question differences can only be reported
descriptively, with every result also shown per family, and the defensible unit, the family, numbers at
most 11 (9 with the public dev cases' gold evidence). The merged protocol (paired hit at 5, exact sign
test, test questions frozen before any training) stays as it is; this page changes none of its terms.

## Feasibility recommendation

The BAG change commentaries, all fourteen published from 2021 to 2025, do not hold the proposed training
material: 44 eligible passages against 100, about half even in the most favourable reading (54), while the
family requirement is met. A pilot of variant 2 on this material could only be exploratory, in its
training data as already in its evaluation. Whether to run it so, with a lowered training threshold and
the test questions frozen first, or to turn to variant 1, is Erhan's decision.

## Files

- Committed: the commentary-source manifest `data/manifests/bag-al-commentaries-2021-2023.json`; in
  `tools/commentary_rag/` the corpus builder `corpus.build_commentaries`, the three views of
  `training_inventory.py` with its subsection annotations, and their tests; and the record
  `results/2026-11-23-training-inventory-2021-2025.json` (IDs, pages, sections, token counts, text
  hashes, codes, projects, families, counts, sensitivities and eligibility changes per view, no passage
  text; it pins its tool files by SHA-256 and the commit it ran from, with no uncommitted tool
  change).
- Local and git-ignored: the PDFs under `data/raw/bag/al/<source ID>/`, and in
  `tools/commentary_rag/local/2026-11-23-older-inventory/` the page renders, the inspection notes and
  the recovered subsection annotations.

To repeat the count, download the ten PDFs from the source URLs into the manifest's paths (with the four
commentaries and workbooks of the earlier inventory) and run, from the repository root, with the e5 model
already in the local cache (read offline; an existing file is never replaced):

    UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" uv run --project services/ingestion \
        --frozen --offline --extra ai --extra dev python tools/commentary_rag/training_inventory.py \
        --older-commentaries data/manifests/bag-al-commentaries-2021-2023.json --out <a new file>

Without `--older-commentaries` the command writes the four-document record of the earlier page.
