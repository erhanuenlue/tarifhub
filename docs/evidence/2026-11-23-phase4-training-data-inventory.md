# Phase 4 data feasibility: training material in the 2024 and 2025 BAG commentaries

Inventory of 2026-11-23 for Phase 4 variant 2, fine-tuning the multilingual-e5 embedder of the
commentary retrieval ([feasibility assessment](2026-11-22-phase4-finetuning-feasibility.md), milestone
[#62](https://github.com/erhanuenlue/tarifhub/issues/62)). Nothing was trained, no provider, model API or
GPU was called and nothing was spent: the four public commentaries were downloaded from the BAG,
parsed with the pilot's corpus builder unchanged and counted offline, with the e5 tokenizer only for
the token budget. The frozen 2026 corpus, its run records and every earlier result are unchanged;
no evaluation case, gold evidence or answer was read. The decision on what follows is Erhan's.

**Verdict on the training data: the threshold is not met.** The four commentaries give 56 passages;
4 are introductions, 52 are usable and form 18 change families. The exclusion rule drops 4 families
with 22 passages because they share a position code or a named project with the 2026 material,
which leaves **30 eligible passages in 14 families**: 70 passages short of the proposed 100, while
the family count (at least 10) is met. Every sensitivity of the open choices stays between 24 and 31
eligible passages, and even with no family excluded the four commentaries would give 51 (one of the
52 usable passages repeats 2026 text). The ten earlier commentaries on the same BAG page (2021 to
2023, 40 pages) would add about 57 at the observed average yield, about 87 in total, still short of
100; their eligibility is unmeasured, and the BAG publishes no commentaries before 2021. No review packet was generated, as asked for this
case. **Verdict on the evaluation design: exploratory only**, see
[What the evaluation could establish](#what-the-evaluation-could-establish).

## Sources

The four commentaries, as the BAG lists them on its page of the Analysenliste (retrieved
2026-11-23), pinned with the full lists of the same editions in the separate manifest
`data/manifests/bag-al-2024-2025.json` (the manifest schema requires each edition's full list; the
inventory reads only the commentaries). Each edition was confirmed from the title on page 1.

| Edition | Title on page 1 | Pages | SHA-256 | Source |
|---|---|---|---|---|
| 2024-01-01 | Kommentar zu den Änderungen des Anhang 3 KLV vom 29. November 2023 per 1. Januar 2024 (AS 2023 807 vom 19. Dezember 2023) | 6 | `b0517c510d68…` | [PDF](https://www.bag.admin.ch/dam/de/sd-web/M10rHsjTEvKJ/kommentar_al_01012024.pdf) |
| 2024-07-01 | Kommentar zu den Änderungen des Anhangs 3 KLV vom 17. Juni 2024 per 1. Juli 2024 (AS 2024 303 vom 24. Juni 2024) | 6 | `3e3e9017c4ae…` | [PDF](https://www.bag.admin.ch/dam/de/sd-web/ZgI8A0wqAPPC/al-kommentar-01072024.pdf) |
| 2025-01-01 | Kommentar zu den Änderungen des Anhangs 3 KLV vom 29. November 2024 per 1. Januar 2025 (AS 2024 788 vom 23. Dezember 2024) | 4 | `aa16093c7b5b…` | [PDF](https://www.bag.admin.ch/dam/de/sd-web/wNImkldiaydS/kommentar-aenderungen-al-01012025.pdf) |
| 2025-07-01 | Kommentar zu den Änderungen des Anhangs 3 KLV vom 04. Juni 2025 per 1. Juli 2025 (AS 2025 419 vom 25. Juni 2025) | 5 | `ae9e480c177c…` | [PDF](https://www.bag.admin.ch/dam/de/sd-web/8dMJK4PMfF-t/Kommentar%20zu%20den%20%C3%84nderungen%20des%20Anh.%203%20KLV%20per%201.7.2025.pdf) |

The frozen 2026 reference was rebuilt from `data/manifests/bag-al.json` the same way: its 40
passage IDs and text hashes equal those of `results/2026-11-14-retrieval-corrected.json`, and its
non-introduction sections name the same 167 position codes as in the feasibility assessment.

## Rules, fixed before counting

Written and committed on 2026-11-23, after the parse and the page inspection and before any
family, overlap or eligibility count was computed. One observation came first: three of the four introductions
repeat the 2026 introductions word for word and the fourth nearly, which prompted rule 10; rule 2
excludes them anyway. Rule 7 was reworded on review without the evaluation grouping's family count,
and the last sentence of this paragraph was corrected (it had said that the primary count always
takes the stricter option); no rule changed in substance. They make the exclusion rule of the
[feasibility assessment](2026-11-22-phase4-finetuning-feasibility.md#proposed-split-and-freezing-procedure)
operational; where a choice is open, the primary count takes the option each rule names first and
a sensitivity count the other. The sensitivity is the stricter option for misfiled text, range
expressions and the AL handbook, and the more lenient one for the phases of transAL; the strictest
combination is reported as well.

1. **Material.** The four commentaries pinned in `data/manifests/bag-al-2024-2025.json`, parsed
   by the pilot's corpus builder unchanged (`corpus.build_corpus`), with the e5 tokenizer and the
   256-token budget of the frozen 2026 corpus. The 2026 reference is the frozen corpus of
   `data/manifests/bag-al.json`, rebuilt the same way and checked against the 40 passage IDs and
   text hashes of `results/2026-11-14-retrieval-corrected.json`.
2. **Sections and introductions.** A section is an edition's numbered section as the parser files
   it. A section whose title begins with "Einleitung" is an introduction: it belongs to no family
   and is never eligible, as in the 2026 grouping.
3. **Usable passages.** Every passage the parser produced outside an introduction, unless the page
   inspection finds a material extraction problem: text filed under a section it does not belong
   to, or text lost or garbled. A passage carrying misfiled text stays usable when that text names
   no position code and no named project, since its family is then unaffected; a sensitivity
   count drops every passage with misfiled text.
4. **Position codes.** Every token of the form `dddd.dd`, once per section (the frozen rule).
   Range expressions contribute only their explicit codes. Sensitivity: an `A ff.` series overlaps
   the 2026 material when a 2026 code has A's four-digit number and is not below A; a wildcard
   `xxxx.dd` overlaps when a 2026 code ends in `.dd`.
5. **Named projects.** A named project is a named undertaking of the authorities (a revision
   project, a programme, a national strategy or a measures package) to which the commentary links
   a change. The candidates come from a scan of all six commentaries (2024 to 2026) and are decided
   by that definition: transAL, its phases transAL-1 and transAL-2 counted as one project
   (sensitivity: the phases apart); the round table on cost containment ("Runder Tisch"); the
   national strategy on antibiotic resistance (StAR). Not projects: laws and ordinances (KLV, KVG,
   GUMG, GUMV), commissions and associations, names of analyses and conditions and their acronyms,
   documents (the AL handbook, a fact sheet; sensitivity: the AL handbook counted as a named item)
   and generic words (pilot study, research project, continuing-education programme, cost
   containment on its own).
6. **Families.** The older non-introduction sections of all four editions are grouped together:
   two sections belong to one family when they share a position code or a named project,
   transitively. A section with neither forms a family of its own.
7. **Exclusion.** An older family is dropped as a whole when it shares a position code with the
   2026 material (the codes of the 2026 non-introduction sections, 167 in the frozen and in the
   diagnostic view) or a named project found in a 2026 non-introduction section. No evaluation
   case is used: the evaluation grouping of the feasibility assessment partitions exactly these
   sections, so the union over its families is the union over the sections.
8. **Counts.** Eligible passages are the usable passages of the families that remain; eligible
   families are the remaining families with at least one usable passage, each counted once across
   editions. Before and after counts are given by edition and overall.
9. **Threshold.** At least 100 eligible passages and at least 10 eligible families, both
   required (the feasibility assessment's proposal, a design choice of this project).
10. **Duplicate check (diagnostic).** Every older passage is compared with the 2026 passages: the
    same text hash, or at least half of its word 8-grams inside one 2026 passage. A duplicate
    outside the introductions would be excluded and reported.

## Parse and page inspection

The parser ran unchanged on all four commentaries and refused none: every printed page label
matched its page, page 1 (title) and page 2 (table of contents) of each edition yield no passage,
and every numbered heading of the body was found and agrees with the table of contents (sections
1, 2.1 to 2.4, 3.1, 4.1 and 4.2 in January 2024; 1, 2.1 to 2.4, 3.1, 3.2 and 4.1 in July 2024; 1,
2.1 to 2.3, 3.1 and 4.1 in January 2025; 1, 2.1, 2.2, 3.1, 4.1 and 4.2 in July 2025). The
inspection compared the parser's output with the original pages in two ways: the
[layout probe](2026-11-22-pdfplumber-layout-probe.md) (`layout_probe.py` with pdfplumber 0.11.11 in an
ephemeral environment, given a record of these passages), which found every passage by its text
hash in the Poppler text and reports headings, footnotes and their references by geometry; and
renders of all 21 pages, checked by eye. Probe reports, renders and crops stay local.

- **Continued headings.** Headings run over up to six lines (July 2024 section 2.1). As
  for 2026, the parser keeps the first line as the section title and the rest in the passage text;
  no continuation line and no body line was read as a heading.
- **Footnotes.** Only two pages have any. On page 3 of January 2025, footnote 1 (a link to the BAG
  fact sheet of 2015 on basic and special analyses) is referenced in section 2.1 but follows section
  2.3 in the text, so the parser files it under 2.3, in passage `2025-01-01/p3/s2.3/1`. This is the
  one material problem: text in the wrong section. It names no position code and no project, so the
  family assignment is unaffected; the passage counts as usable (rule 3) and is dropped in the
  strict sensitivity. On page 4 of July 2025, footnotes 1 and 2 (links to the WHO and to the
  national strategy StAR) are referenced in section 3.1 and filed there, correctly.
- **Not material.** The footnote marker in January 2025 section 2.1 hides a sentence end, so the
  long run is split between words (`p3/s2.1/1` and `/2`); in January 2024 section 4.1 the sentence
  splitter breaks after "(vgl." because the parenthesis hides the abbreviation, and the
  superscript ordinals "bis" and "ter" after "Bst. b" come out inline; list bullets ("-" and "o") stand on lines
  of their own in the Poppler text and join the item that follows; the heading of January 2025
  section 2.1 writes "1700" without decimals, but its body names 1700.00, so the code set is
  complete. No text was lost or garbled.

| Edition | Pages (without passages) | Passages | Introductions | Usable | Misfiled text | Families | Dropped families (usable passages) | Eligible families | Eligible passages |
|---|---|---|---|---|---|---|---|---|---|
| 2024-01-01 | 6 (2) | 16 | 1 | 15 | 0 | 7 | 2 (4) | 5 | **11** |
| 2024-07-01 | 6 (2) | 20 | 1 | 19 | 0 | 5 | 2 (10) | 3 | **9** |
| 2025-01-01 | 4 (2) | 10 | 1 | 9 | 1 | 5 | 1 (1) | 4 | **8** |
| 2025-07-01 | 5 (2) | 10 | 1 | 9 | 0 | 4 | 2 (7) | 2 | **2** |
| **All four** | 21 (8) | 56 | 4 | 52 | 1 | 18 | 4 (22) | 14 | **30** |

Families are grouped across editions: one family spans all four editions, so the per-edition family
counts add up to more than the 18 distinct families. The eligible passages hold 48 to 255 tokens
(mean 149.7).

## Families and the exclusion

| Family | Sections (edition/section) | Usable passages | What the sections cover | Shared with 2026 | Result |
|---|---|---|---|---|---|
| F01 | 2024-01-01/2.1 | 2 | SARS-CoV-2 positions 3188.00 and 3189.00, admitted without time limit | none | eligible |
| F02 | 2024-01-01/2.2 | 3 | genetic positions for porphyrias (no position code) | none | eligible |
| F03 | 2024-01-01/2.3; 2024-07-01/2.1, 2.2, 3.2; 2025-01-01/3.1; 2025-07-01/2.1 | 12 | newborn screening 1368.00 (extensions, a refused tariff review, an editorial change, the tariff increase) and the cumulation rule for high-throughput sequencing, linked through the project transAL | 1368.00 (July 2026 section 2.5); transAL (January 2026 section 2.2, July 2026 sections 2.4 and 2.5) | dropped |
| F04 | 2024-01-01/2.4 | 3 | analyses midwives may order (16 codes) | 1034.00, 1314.00, 3333.00 (July 2026 sections 2.4 and 3.1) | dropped |
| F05 | 2024-01-01/3.1 | 2 | refused: point-of-care isothermal amplification test for SARS-CoV-2 (no code) | none | eligible |
| F06 | 2024-01-01/4.1 | 3 | editorial changes after the revised law on genetic testing (1900.00 ff., 6206.55 ff., 6603.50 ff., 6702.63) | none; the series 6206.55 ff. reaches 6206.60 (ranges sensitivity) | eligible |
| F07 | 2024-01-01/4.2 | 1 | gender-neutral language (no code) | none | eligible |
| F08 | 2024-07-01/2.3 | 2 | reticulocytes 1649.00 (and 1648.00) in practice laboratories | none | eligible |
| F09 | 2024-07-01/2.4 | 3 | hereditary breast and ovarian cancer, 6241.55, 6241.56, 6241.60 | 6241.56, 6241.60 (codes of footnote 1 of July 2026, filed under section 2.4 in the frozen view, 2.3 by layout) | dropped |
| F10 | 2024-07-01/3.1 | 6 | refused: ferritin in primary-care practice laboratories (no code) | none | eligible |
| F11 | 2024-07-01/4.1 | 1 | first-trimester test 6700.90 and 6701.90, editorial | none | eligible |
| F12 | 2025-01-01/2.1 | 3 | APTT, fibrinogen, thrombin time and INR (1019.00, 1320.00, 1699.00, 1700.00) from special to basic analysis | none | eligible |
| F13 | 2025-01-01/2.2 | 1 | troponin 1734.01 removed | none | eligible |
| F14 | 2025-01-01/2.3 | 2 | chimerism monitoring 6402.54 (formerly 2346.06); one passage carries the misfiled footnote | none | eligible |
| F15 | 2025-01-01/4.1 | 2 | bioinformatic re-analysis 6010.08, 6011.08, 6012.08 (and 6003.02), with a rule in the AL handbook | none; the AL handbook (handbook sensitivity) | eligible |
| F16 | 2025-07-01/2.2, 3.1 | 4 | procalcitonin 1619.00 and its refused use in practice laboratories (with 1245.00, 1245.01, StAR) | 1245.00, 1619.00 (January 2026 section 2.2, July 2026 section 2.4) | dropped |
| F17 | 2025-07-01/4.1 | 1 | 3340.00 and 3341.00, correction of the Italian version | none | eligible |
| F18 | 2025-07-01/4.2 | 1 | 1690.00 sulfhaemoglobin, correction of the Italian version | none | eligible |

**Example of an exclusion: F03, newborn screening.** Position 1368.00 runs through three of the four
editions: July 2024 admits the screening for severe combined immunodeficiency for good and extends
it to spinal muscular atrophy (sections 2.1 and 2.2) and refuses a review of its tariff, which the
project transAL-2 is to revise (3.2); January 2025 corrects its wording (3.1); July 2025 raises its
tariff until transAL-2 ends (2.1). The cumulation rule of January 2024 (2.3) joins the family
through the project transAL, whose first phase it names. July 2026 section 2.5 names 1368.00 again
(it is also in the public dev case D1), and transAL-2 appears in January 2026 section 2.2 and July
2026 sections 2.4 and 2.5. So the whole family, 12 usable passages in six sections, is dropped, not
only the sections that name 1368.00. The duplicate check shows why this matters: the first passage
of July 2025 section 2.1 shares 73 % of its word 8-grams with `2026-07-01/p6/s2.5/1`, so training on
it would have meant training on test text.

**Duplicate check.** Apart from that passage (in F03), only the introductions match: those of
January 2024, July 2024 and January 2025 are identical to both 2026 introductions (same text hash),
and that of July 2025 shares 83 % of its word 8-grams with them. That copy lies in a dropped family and
introductions are never eligible (rule 2), so the check leaves the primary count unchanged; it
lowers only the bound with no family excluded, from 52 to 51.

**What remains.** The 30 eligible passages are 13 from content changes (section 2) in 6 families, 8
from refused applications (section 3) in 2 families and 9 from editorial adjustments and
miscellanea (section 4) in 6 families. The last group includes gender-neutral wording and two
corrections of the Italian version, which are weak material for German retrieval questions.

## Sensitivities

| Variant (rules 3 to 5) | Eligible passages | Eligible families | Dropped families |
|---|---|---|---|
| **Primary** | **30** | **14** | 4 |
| Every passage with misfiled text dropped | 29 | 14 | 4 |
| Range expressions against the 2026 codes | 27 | 13 | 5 |
| transAL phases counted apart | 31 | 15 | 4 |
| AL handbook counted as a named item | 28 | 13 | 5 |
| Strictest (misfiled, ranges and handbook) | 24 | 12 | 6 |
| No family excluded (upper bound) | 51 | 18 | 0 |

No variant comes near 100 passages, and every variant keeps at least 12 families.

## Shortfall and the next sources

Against the proposed threshold the four commentaries fall short by **70 passages** (30 of 100, a
factor of 3.3); the family requirement (14 of at least 10) is met. With no family excluded they would
still fall short by 49 (51 eligible: rule 10 keeps out the one usable passage that repeats 2026
text).

The BAG page lists ten earlier change commentaries, and states that commentaries exist only from
1 January 2021, earlier changes having been explained in the BAG Bulletin. A screen on 2026-11-23 gives the
figures below (pages from `pdfinfo`; subsection headings are lines of the Poppler text outside the
table of contents that match the parser's heading pattern; position codes are the distinct
`dddd.dd` tokens of the whole text). It used no manifest, no inspection and no families, and its
figures are not in a committed record:

| Commentary | Pages | Subsection headings of the parser's form | Distinct position codes | Of them among the 167 codes of 2026 |
|---|---|---|---|---|
| [per 1 November 2023](https://www.bag.admin.ch/dam/de/sd-web/ugLbCOyBn6Rt/kommentar-aenderungen-al-01112023.pdf) | 4 | 1 | 2 | 0 |
| [per 1 July 2023](https://www.bag.admin.ch/dam/de/sd-web/kTgiv8VUDAIm/kommentar_aenderungen_anh3_010723.pdf) | 4 | 0 | 6 | 0 |
| [per 1 March 2023](https://www.bag.admin.ch/dam/de/sd-web/GGUmWtf3tYik/klv_anh3_kommentar_aenderungen_010323.pdf) | 3 | 0 | 2 | 0 |
| [per 1 January 2023, urgent changes](https://www.bag.admin.ch/dam/de/sd-web/1nkLkL726ycP/alkommentardringendeaenderungenper01012023.pdf) | 3 | 0 | 6 | 1 |
| [per 1 January 2023](https://www.bag.admin.ch/dam/de/sd-web/w7OsaUM9LIwQ/alkommentaraenderungenper01012023.pdf) | 5 | 6 | 50 | 25 |
| [per 1 August 2022](https://www.bag.admin.ch/dam/de/sd-web/RlJy7aAqUU6f/kommentar_aenderungen_al_010822.pdf) | 3 | 1 | 0 | 0 |
| [per 1 July 2022](https://www.bag.admin.ch/dam/de/sd-web/eGN04VvYS3vy/kommentar-aenderungen-al-01072022.PDF) | 6 | 10 | 31 | 4 |
| [per 1 January and 1 February 2022](https://www.bag.admin.ch/dam/de/sd-web/e5D8kW3qmfPg/kommentarzudenaenderungenanhang3per01012022.pdf) | 5 | 2 | 30 | 7 |
| [per 1 July 2021](https://www.bag.admin.ch/dam/de/sd-web/M7xIXAXqhTFl/kommentar-zu-den-aenderungen-per-01.07.2021-des-anhangs-3-der-klv.pdf) | 4 | 0 | 13 | 0 |
| [per 1 February 2021, additional changes](https://www.bag.admin.ch/dam/de/sd-web/wSAkNxpS90s5/KLV-Aenderungen_Anh_3_Erlaeuterungen_01.02.2021_Publikation_DE_DEF.pdf) | 3 | 0 | 2 | 1 |
| **Ten commentaries** | **40** | | | |

At the yield of 2024 and 2025 (30 eligible passages from 21 pages, about 1.4 per page) their 40
pages would add about 57 eligible passages, about 87 in total, still short of 100. This is an
extrapolation, not a count. Reaching 100 would take 70 eligible passages from their 40 pages, 1.75
per page: January 2024 (1.8) and January 2025 (2.0) exceeded that rate, July 2024 (1.5) and July 2025
(0.4) did not. Two signs point lower: the January 2023 commentary names 25 of its 50 codes among the
2026 codes, and five of the ten show no subsection heading of the form the parser recognises and
three only one or two, so their passages would fall under whole top-level sections and their
families would be coarser, which drops more material per overlap. Their parse would need the same
inspection.

Other sources are of a different kind: the BAG Bulletin before 2021 (another publication and
layout), and the position texts of the AL full lists already pinned in both manifests (list entries,
not commentary prose; families would follow single codes, and the 2026 codes would have to be
excluded under a rule of their own). Either would need a decision on whether it is the same kind of
training material.

## What the evaluation could establish

The merged protocol's primary endpoint is a paired hit at 5 per held-out unit with gold evidence
(Evidence Recall@5 above 0), compared between the base and the tuned model by an exact two-sided
sign test at the 5 % level, ties dropped. The power figures come from `sign_test_power.py` (record
`results/2026-11-23-sign-test-power.json`): exact multinomial sums over wins, losses and ties, with
the p-values as fractions. They reproduce the feasibility assessment's 0.57 and 0.31, and an
independent recomputation in the session agreed. 80 % power is the proposed target for Erhan's
decision, not a decided gate.

**Which units are independent.**

- Questions that share a supporting passage are not independent: each is ranked separately, but
  both depend on how each model represents that passage. The protocol already combines them into
  one unit, and the known D, U and E questions are never test units.
- Questions of one change family with different passages are not independent either: a model tuned
  on other families changes how it ranks the family's vocabulary as a whole, so its questions tend to
  win or lose together. For a claim about changes in general, the family is the defensible unit.
- The 2026 material has few families: 11 by shared position codes alone and 9 with the public dev
  cases' gold evidence (frozen view, feasibility assessment); the evaluation grouping, which also
  links the private cases' gold evidence, can have no more. With families as units and no family
  losing, the test rejects only once at least 6 families differ, all in the tuned model's favour:
  with exactly 6 families power is 0.26 at a family win probability of 0.8 and 0.53 at 0.9; 4 or 5 families
  can never reach 5 %; with 9 families power is 0.66 at 0.67 and 0.91 at 0.8, with 11 families 0.50
  at 0.5 and 0.88 at 0.67. A family win probability that high is a large, consistent effect.
- Independence is therefore not shown for questions, even after shared-passage questions are
  combined, so a question-level sign test or bootstrap interval would not be a valid inference:
  per-question differences can only be reported descriptively, with every result also shown per
  family. Inference belongs to families, of which there are at most 11.

**Feasible sample size.** Every answerable unit needs a supporting passage of its own, and the 2026
corpus has 38 non-introduction passages (10 in January, 28 in July), some of them bare lists of
position codes: at most about 38 question units, realistically about 30 (the feasibility
assessment's test threshold). Under the edition filter a January question competes with 11
passages, so a random top 5 already contains a single gold passage with probability 0.455.

**Headroom.** A win needs a question the base model misses at 5. On the six public dev cases with
evidence, dense e5 alone (edition filter) hits at 5 on five (D2 is missed;
`results/2026-11-14-retrieval-corrected.json`), a base miss rate of 1/6. Fresh questions may be
harder, but these are the only measurement. A win rate of 20 % (S1) is already above that miss rate;
S7 is the best case at the measured rate, a tuned model that fixes every base miss and breaks
nothing.

The table shows what a question-level test would need **if the questions were independent**, which
they are not shown to be: its figures are conditional on that assumption, not a formal bound.

| Scenario | Win w | Loss l | Power, 30 units | Power, 38 units | Units for 0.80, two-sided | Units for 0.80, one-sided |
|---|---|---|---|---|---|---|
| S1 | 0.20 | 0.00 | 0.5725 | 0.7996 | 39 | 33 |
| S2 | 0.30 | 0.10 | 0.3071 | 0.4142 | 84 | 67 |
| S3 | 0.10 | 0.00 | 0.0732 | 0.1747 | 78 | 66 |
| S4 | 0.30 | 0.00 | 0.9234 | 0.9863 | 25 | 21 |
| S5 | 0.20 | 0.05 | 0.2354 | 0.3395 | 92 | 74 |
| S6 | 0.40 | 0.10 | 0.5859 | 0.7178 | 46 | 37 |
| S7 | 1/6 | 0.00 | 0.3836 | 0.6248 | 46 | 39 |

S1 and S2 are the scenarios the feasibility assessment documented; S3 to S6 bracket them. In every
scenario the first unit count that reaches 0.80 also keeps it for every larger count (the ties
smooth the saw-tooth of the exact test).

**What it could detect.** Even granting independence, two-sided and with no losses, the smallest win
rate on a grid of 0.01 that reaches 80 % power is 0.26 with 30 questions and 0.21 with 38 (one-sided
0.22 and 0.18); with one loss for every three wins it is 0.75 and 0.66, which is no plausible
fine-tuning effect. Every one of these lies above the base
miss rate of the dev cases, so even a perfect tuned model would reach only 0.38 with 30 questions
and 0.62 with 38 (S7) if fresh questions were like the known ones.

**Verdict: exploratory only.** Questions are not shown to be independent, and even if they were, S1
would need 39 of them, one more than the corpus's 38 non-introduction passages could carry if every
one served, and S2 would need 84; families, the defensible unit, number at most 11 (9 with the
public dev cases' gold evidence). A pilot on this design can report paired differences in hit at 5,
Recall@5 and MRR@5 per question, descriptively, and per family, the metrics the protocol already
lists; a null result would be inconclusive, not evidence that tuning does not help.

**What would have to change to reach 80 %.** Each is a change to the merged protocol and Erhan's
decision:

1. A one-sided test in the tuned model's favour: S1 then needs 33 questions, still at the corpus's
   limit, and the headroom stays as small.
2. A graded primary endpoint instead of hit at 5, such as the rank of the first gold passage or MRR
   at 10 with a paired permutation test, so that a move within the top 5 or from rank 11 to rank 6
   counts. Its power needs a variance assumption that no data here supports yet.
3. A harder ranking with more headroom, such as no edition filter, so that fewer test questions are
   easy for the base model; that changes what the test measures, and the protocol fixed the edition
   filter for both models.
4. More independent test units than the 2026 commentaries can carry, which needs more test material
   or another split, and either takes material from the training side, already short.

## Files

- Committed: the manifest `data/manifests/bag-al-2024-2025.json`; in `tools/commentary_rag/` the
  inventory `training_inventory.py` with its tests and its record
  `results/2026-11-23-training-inventory.json` (IDs, pages, sections, token counts, text hashes,
  codes, projects, families, counts and sensitivities, no passage text; it pins its tool files by
  SHA-256), and the power calculation `sign_test_power.py` with its tests and its record
  `results/2026-11-23-sign-test-power.json`.
- Local and git-ignored: the PDFs and workbooks under `data/raw/bag/al/`, and in
  `tools/commentary_rag/local/2026-11-23-inventory/` the probe reports, the page renders and crops.
  The screen of the ten earlier commentaries read copies outside the repository.

To repeat the inventory, download the four PDFs and workbooks from the source URLs into the
manifest's paths and run, from the repository root (the e5 model must already be in the local
cache; the command reads it offline and never replaces an existing file):

    UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" uv run --project services/ingestion \
        --frozen --offline --extra ai --extra dev python tools/commentary_rag/training_inventory.py \
        --out <a new file>
