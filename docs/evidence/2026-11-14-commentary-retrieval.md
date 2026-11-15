# BAG commentary retrieval: local measurement on eight dev cases

Measurement record for the first increment of the commentary RAG pilot
([ADR-025](../adr/025-commentary-retrieval.md)): passages of the two BAG commentaries
ranked by BM25, multilingual-e5 and their reciprocal rank fusion. Captured on 2026-11-14 on the
macOS host (Apple Silicon, Python 3.13.12), offline: no API key, no network, no download, no
database. **Retrieval only: no answer was generated, so nothing here measures answer quality,
citation faithfulness or abstention.**

Two runs are recorded. The **baseline** is kept unchanged. The **corrected run** repeats the same
evaluation after three corrections to the passage construction that were made because of the
baseline's D2 and D6 misses: it is a **development-set-informed correction, not held-out
validation**.

## What was and was not done

| Done and measured here | Not done |
|---|---|
| Corpus built from the hash-verified PDFs; every passage within the model's 512-token input | Review of the eight dev cases, their quotes and reference expectations by Erhan (all are AI-drafted) |
| Rankings of every case by BM25, dense and hybrid, with and without the edition filter, in both runs | Any LLM call, generated answer or answer evaluation |
| Evidence Recall@5, MRR@5, wrong-edition passages@5, both-edition coverage@5 | A held-out test set (all eight cases are dev cases) |
| Baseline: two identical runs; corrected run repeated once before generation, identical; all records' metrics recompute exactly; a case-by-case comparison | Runs on another machine or device; a second-model code review |

## Tested revisions

Both runs are uncommitted working trees on top of `88cd681` (branch
`feat/commentary-rag-retrieval`). Each record pins the files it ran with by SHA-256 (first 12
hex digits shown); `run_eval.py` checks nothing against them, so a later edit shows only by
comparing hashes. `cases.json` is identical in both runs.

| File | Baseline | Corrected run |
|---|---|---|
| `tools/commentary_rag/corpus.py` | `3cf42c48cbc4` | `38a1572daf52` |
| `tools/commentary_rag/retrieval.py` | `525324f3b5df` | `7803c83d4f0a` |
| `tools/commentary_rag/evaluation.py` | `4bcdf122837b` | `899ba8e9adb5` |
| `tools/commentary_rag/run_eval.py` | `d3362e8379b3` | `0426def70d8a` |
| `tools/commentary_rag/cases.json` | `9d471418546a` | `9d471418546a` |

Records in `tools/commentary_rag/results/`: `2026-11-14-retrieval.json` (baseline, recorded at
2026-11-14T21:08:52Z, file SHA-256 `094e5268976f...`, unchanged since) and
`2026-11-14-retrieval-corrected.json` (recorded at 2026-11-14T21:28:59Z, labelled as a
development-set-informed correction, naming the baseline file and its hash); the comparison is
`2026-11-14-comparison.json`. Manifest `data/manifests/bag-al.json`, SHA-256 `3a3c98567a51...`.

## Setup (both runs)

- **Sources**: the `commentary_pdf` of each manifest edition, read through the ingestion
  manifest loader and verifier; `pdftotext` 26.02.0 parses the verified bytes on stdin.
  January: SHA-256 `0d335bd46adec025...`, 5 pages, "Kommentar zu den Änderungen des Anhangs 3
  KLV vom 2. Dezember 2025 per 1. Januar 2026 (AS 2025 851 vom 19. Dezember 2025)". July:
  `fe1856df9f7d0023...`, 8 pages, "... vom 9. Juni 2026 per 1. Juli 2026 (AS 2026 336 vom
  24. Juni 2026)". Every content page's printed "Seite N von M" equals its PDF page index.
- **Excluded pages**: page 1 of each document (front matter before the first section heading)
  and page 2 (table of contents).
- **Passages**: one section's text on one page, split when it exceeds the budget of 256 tokens.
  Counts use the loaded model's own tokenizer on the exact embedded string (`passage: ` prefix
  and special tokens included) and agree with SentenceTransformer's own preprocessing.
- **Model**: `intfloat/multilingual-e5-large`, cache revision
  `3d7cfbdacd47fdda877c5cd8a79fbcc4f2a574f3`, loaded through the repository's `get_embedder`
  on device `mps:0`; sentence-transformers 5.6.1, transformers 5.11.0, torch 2.12.0.
- **Rankers**: BM25 (`k1` 1.2, `b` 0.75, statistics over the selected editions), cosine on the
  normalised e5 vectors, RRF with `k` 60 over the two full rankings; equal scores ordered by
  passage ID. Top-k 5. Unchanged between the runs.
- **Modes**: `edition_filter` ranks only the case's target editions; `no_filter` ranks both. For
  D6, which targets both editions, the two modes are the same selection.

## Cases and metric definitions (fixed before the baseline; unchanged)

Eight dev cases (`tools/commentary_rag/cases.json`), drafted by Claude from the extracted text:
six with evidence (D1 to D6) and two with no supporting evidence in the selected commentary (U1:
the tariff of 1034.00, named in the July commentary without a tariff; U2: a July change of
1619.00, which only the January commentary discusses). D1 is the Zwischenbericht 1 demo case,
which that report keeps outside its locked test set; nothing here is a held-out test.

An **evidence item** is a verbatim quote on one page of one edition; a passage covers it when it
is from that edition and page and its own text (not its table context) contains the quote. In
both runs, each of the 15 items was checked to lie on its stated page and within exactly one
passage; no quote, case or expectation was changed for the corrected run.

- **Evidence Recall@5**: covered items / items, over the six cases with items. Undefined for U1
  and U2 (no items): reported as n/a, never as 0.
- **MRR@5**: 1 / rank of the first passage covering any item, 0 when none is in the top 5; over
  the same six cases.
- **Wrong-edition passages@5**: top-5 passages from an edition the case does not target, over
  the seven single-edition cases (35 passages). With the edition filter this is **0 by
  construction**: other editions are not candidates, so it shows nothing about the rankers.
- **Both-edition coverage@5**: 1 when the top 5 cover an item of each edition the case's items
  come from. Only D6 has items from both editions, so it rests on one case and establishes
  nothing about two-edition retrieval in general.

## Baseline (preserved)

47 passages (January 13, July 34), 10 to 256 tokens (mean 159.4); splits: 17 whole, 25 at
sentences, 5 at words. Queries: 20 to 47 tokens.

| Method | Mode | Evidence Recall@5 (6 cases) | MRR@5 (6 cases) | Wrong-edition passages@5 (7 cases) | Both-edition coverage@5 (D6) |
|---|---|---|---|---|---|
| BM25 | edition filter | 0.708 | 0.700 | 0/35 (by construction) | 0 |
| BM25 | no filter | 0.708 | 0.700 | 7/35 = 0.200 | 0 |
| Dense | edition filter | 0.708 | 0.700 | 0/35 (by construction) | 0 |
| Dense | no filter | 0.625 | 0.583 | 11/35 = 0.314 | 0 |
| Hybrid | edition filter | 0.667 | 0.667 | 0/35 (by construction) | 1 |
| Hybrid | no filter | 0.667 | 0.583 | 10/35 = 0.286 | 1 |

Three defects of the passage construction showed in the baseline:

- **D2 missed with every ranker.** The splitter did not recognise `Pos.-Nr.` as an abbreviation,
  so the July p. 5 table header ("Die folgenden umsatzstärksten Analysepositionen sind von der
  Kürzung betroffen") ended up in its own passage and the rows (names, codes, percentages) in
  another that shares no word with the question.
- **Heading-only passages.** Five top-level headings without text of their own ("2. Inhaltliche
  Änderungen des Anhangs 3 der KLV" and others, 10 to 16 tokens) were passages; for D6, dense
  ranked two of them at 3 and 4, ahead of the January evidence.
- **D1, the demo case, retrieved weakly**: its evidence sat at ranks 5 to 15.

## Corrections (development-set-informed)

Made after seeing the baseline, through tests at the corpus and retrieval interfaces:

1. A compound abbreviation such as `Pos.-Nr.` no longer ends a sentence.
2. A table of position rows stays one passage with its heading line (ending in ':') and column
   names when it fits the budget; if not, it is split between rows and every later part carries
   that heading as `context` (verbatim, same page, indexed and counted with the part, never used
   for evidence matching). Passage text stays a contiguous run of one page.
3. A heading with no text of its own joins the text it heads on the same page; one at the foot
   of a page would be recorded as excluded (none occurs in these documents).

Questions, evidence quotes, metric definitions, top-k, budget, ranker settings, methods and modes
are the same as in the baseline; the comparison reports no differing setting.

## Corrected run

40 passages (January 11, July 29), 16 to 254 tokens (mean 186.6), none over 512; splits: 12
whole, 24 at sentences, 3 at words, 1 table. The July p. 5 table, with its heading and column
names, is one passage of 238 tokens, so no table part needed context.

Passage identities against the baseline: 32 unchanged; 8 changed (the first passages of January
§2.1 and §3.1 and of July §2.1, §3.1 and §4.1, which now begin with the joined headings, and
July p. 5 §2.4 /1 to /3, rebuilt around the table); 7 removed (the five heading-only passages
and July p. 5 §2.4 /4 and /5). Evidence items whose covering passage moved: the three D2 items
(p. 5 §2.4 /2 to /1, the table passage) and two D6 items (p. 5 §2.4 /5 to /3); all other items
map to the same passage IDs.

| Method | Mode | Evidence Recall@5 (6 cases) | MRR@5 (6 cases) | Wrong-edition passages@5 (7 cases) | Both-edition coverage@5 (D6) |
|---|---|---|---|---|---|
| BM25 | edition filter | 0.708 → 0.875 | 0.700 → 0.875 | 0/35 (by construction) | 0 → 0 |
| BM25 | no filter | 0.708 → 0.875 | 0.700 → 0.875 | 7/35 → 8/35 | 0 → 0 |
| Dense | edition filter | 0.708 → 0.750 | 0.700 → 0.708 | 0/35 (by construction) | 0 → 1 |
| Dense | no filter | 0.625 → 0.750 | 0.583 → 0.617 | 11/35 → 11/35 | 0 → 1 |
| Hybrid | edition filter | 0.667 → 0.833 | 0.667 → 0.722 | 0/35 (by construction) | 1 → 1 |
| Hybrid | no filter | 0.667 → 1.000 | 0.583 → 0.681 | 10/35 → 10/35 | 1 → 1 |

For context, not a measured run: a uniformly random ranking of the selected passages has an
expected Evidence Recall@5 of exactly 5/N per case here (each item is covered by one passage):
0.219 with the edition filter and 0.106 without it for the baseline corpus, 0.259 and 0.125 for
the corrected one (N = 29 July, 11 January, 40 for D6).

Full rank of each case's evidence passages, baseline → corrected (edition filter | no filter;
for D6 one value, both modes being the same selection):

| Case | BM25 | Dense | Hybrid |
|---|---|---|---|
| D1 | 5, 12 \| 5, 13 → 4, 12 \| 4, 13 | 12, 5 \| 15, 6 → 12, 4 \| 15, 5 | 7, 8 \| 9, 6 → 6, 7 \| 5, 4 |
| D2 | 9 \| 8 → 1 \| 1 | 21 \| 26 → 7 \| 7 | 15 \| 15 → 3 \| 3 |
| D3 | 1 \| 1 → 1 \| 1 | 1 \| 2 → 1 \| 2 | 1 \| 2 → 1 \| 2 |
| D4 | 1 \| 1 → 1 \| 1 | 1 \| 1 → 1 \| 1 | 1 \| 1 → 1 \| 1 |
| D5 | 1 \| 1 → 1 \| 1 | 1 \| 1 → 1 \| 1 | 1 \| 1 → 1 \| 1 |
| D6 | 8, 1, 2 → 7, 1, 2 | 6, 1, 2 → 4, 2, 1 | 3, 1, 2 → 3, 1, 2 |

### Changes by case and method

Of the 48 case, method and mode combinations, 11 improved, 22 are unchanged, 3 are unchanged
failures, 12 have no evidence items, and none regressed or changed in mixed directions on
Evidence Recall@5 and MRR@5:

- **Improved**: D2 with BM25 and hybrid (both modes); D6 with dense (both modes, now covering
  both editions); D1 with BM25 (both modes) and dense with the filter (MRR 0.20 to 0.25), with
  dense without the filter (recall 0 to 0.5, MRR 0 to 0.20) and with hybrid without the filter
  (recall 0 to 1, MRR 0 to 0.25).
- **Unchanged failures**: D2 with dense in both modes (the table passage at rank 7) and D1 with
  hybrid and the edition filter (its evidence at ranks 6 and 7, the passage at rank 5 ahead by
  RRF 0.0296 to 0.0295). Without the filter the same two passages reach ranks 5 and 4, because
  BM25's statistics change with the selection: a near tie, not a reason to drop the filter.
- **Regression on another metric**: without the filter, BM25 now puts two January passages in
  D1's top 5 instead of one (wrong-edition rate 0.200 to 0.229).
- **U1 and U2 unchanged**: without the filter all three rankers still rank the January 1619.00
  passage first for the July question U2, and BM25 still ranks the July passage naming AFP
  1034.00 without a tariff first for U1 (dense and hybrid without the filter rank the January
  1619.00 passage first). Wrong-edition counts for U1 and U2 are unchanged.

## Reproducibility

The baseline record was written twice with the same command; passages, cases, all 48 rankings
with their scores, the per-case metrics and the summary were identical (largest score difference
0.0). The corrected run was repeated once before any answer was generated, through the same code
path (`run_generation.py prepare`, record `results/2026-11-14-retrieval-rerun.json`): all 48
rankings, every score (largest difference 0.0), the per-case metrics, the summary and all 40
passage hashes were identical, so the contexts for generation are the saved record's top 5.
`run_eval.py --recompute` re-derives every stored metric of either record from its stored
rankings and reports none different; the offline test suite repeats that check on both recorded
files.

## Assessment

The corrections fixed what they targeted (D2 now retrieved by BM25 and hybrid, no heading-only
passage in any top 5) without lowering Evidence Recall@5 or MRR@5 for any case, method and mode,
at the cost of one more wrong-edition passage for unfiltered BM25 on D1. Because they were made
after seeing these eight cases, the gains are expected on them and say nothing about unseen
questions. On six AI-drafted dev cases the rankers differ by one case or less, BM25 with the
edition filter scoring highest here; that, and D6's both-edition coverage by dense and hybrid,
are pilot observations on one dev set, not evidence that any method is better in general or
that two-edition retrieval works.

## Reproduction

From the repository root (the e5 model must be in the Hugging Face cache):

```bash
uv run --project services/ingestion --no-sync python -m pytest tools/commentary_rag -q
HF_HUB_OFFLINE=1 uv run --project services/ingestion --frozen --offline --extra e5 --extra dev \
  python tools/commentary_rag/run_eval.py --out tools/commentary_rag/results/<name>.json \
  --label "<label>" --baseline tools/commentary_rag/results/2026-11-14-retrieval.json
(cd services/ingestion && uv sync --frozen --offline --extra dev)
uv run --project services/ingestion --no-sync python tools/commentary_rag/run_eval.py \
  --compare tools/commentary_rag/results/2026-11-14-retrieval.json \
            tools/commentary_rag/results/<name>.json
```

## Remaining limitations

- A corpus of two short documents and eight dev cases; no held-out set, no human review yet.
- Section attribution is heuristic: footnotes join the last section on their page (the HDS
  position list of section 2.3 appears as three section 2.4 passages on July p. 4), and heading
  continuation lines are missing from section titles.
- Table detection fits the commentaries' position tables only; the split-table context is
  covered by tests but not used by this corpus.
- Reproducibility is shown on one machine and device (`mps:0`), and for the baseline only.
- No generation: answer quality, citation correctness and abstention remain unmeasured.
