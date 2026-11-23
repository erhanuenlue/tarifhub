# Phase 4 data feasibility: training material in the 2024 and 2025 BAG commentaries

Inventory of 2026-11-23 for Phase 4 variant 2 (fine-tuning the multilingual-e5 embedder of the
commentary retrieval), before any training, provider call or GPU job. Work in progress: the rules
below were fixed before the counts.

## Rules, fixed before counting

Written and committed on 2026-11-23, after the parse and the page inspection and before any
family, overlap or eligibility count was computed. They make the exclusion rule of the
[feasibility assessment](2026-11-22-phase4-finetuning-feasibility.md#proposed-split-and-freezing-procedure)
operational; where a choice is open, the primary count takes the stricter option and a
sensitivity count the other.

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
   case is used: the six 2026 evaluation families partition exactly these sections, so the union
   of their codes and projects is the union over the sections.
8. **Counts.** Eligible passages are the usable passages of the families that remain; eligible
   families are the remaining families with at least one usable passage, each counted once across
   editions. Before and after counts are given by edition and overall.
9. **Threshold.** At least 100 eligible passages and at least 10 eligible families, both
   required (the feasibility assessment's proposal, a design choice of this project).
10. **Duplicate check (diagnostic).** Every older passage is compared with the 2026 passages: the
    same text hash, or at least half of its word 8-grams inside one 2026 passage. A duplicate
    outside the introductions would be excluded and reported.
