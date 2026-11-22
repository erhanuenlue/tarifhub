# Phase 4 feasibility: fine-tuning the multilingual-e5 embedder for the commentary retrieval

Assessment of 2026-11-22, before any Phase 4 spending: nothing was trained and no provider or GPU
was called. The corpus counts, sections, position codes and change families below were re-derived
on 2026-11-22 on the macOS host from the code of `main` at `05aba9b`: the corpus was rebuilt
with the pilot's own corpus builder and the cached e5 model (offline), and its 40 passage IDs and
text hashes are identical to `tools/commentary_rag/results/2026-11-14-retrieval-corrected.json`.
Retrieval scores are read from the recorded runs. The decision to run a pilot, and its budget, are
Erhan's.

**Verdict: no-go for an embedding fine-tuning pilot on the current corpus alone.** Grouped so that
related changes stay together, the two 2026 commentaries form 6 change families, one of which holds
more than half of the 40 passages. Inside the corpus a family-disjoint split is therefore
lopsided: one side gets that family, the other fewer than 20 passages in five small families, too
narrow a training source or too small a test to show a difference
([headroom](#headroom-and-what-a-test-could-detect)). A pilot needs its training data from
elsewhere and becomes a go once the two offline data steps in
[Smallest useful data work](#smallest-useful-data-work) meet their thresholds; the lopsided
in-corpus split stays the fallback if they fail. Selective evidence
search ([variant 1](#alternative-selective-evidence-search-variant-1)) needs no training data and
could start sooner, but its live runs would cost more in API calls than the pilot (cost table
below). The course extract lists fine-tuning among the module's required contents, so whether
variant 1 alone suffices is a question for the lecturer before choosing it.

## Why embedding fine-tuning, and what changed since Zwischenbericht 1

Zwischenbericht 1 (6 October 2026) planned fine-tuning as a **Change Extractor**: a QLoRA adapter
on `Qwen3-4B-Instruct-2507` turning commentary passages into structured change records (type,
position, validity), hypothesis H2 "a LoRA adapter improves the structured extraction over the
same base model without adapter", measured by field accuracy, change-type macro-F1 and
evidence-span F1 on up to 500 records split by change family and year. Phases 2 and 3 then
showed where the system actually fails: retrieval. Dev case D1 failed end to end because its gold
passages ranked 6 and 7 ([generation evidence](2026-11-15-commentary-generation.md)); on E2 to E6
the hybrid top 5 held 7 of 13 gold evidence items, while the agent, searching beyond them, had
all 13 in context ([comparison evidence](2026-11-21-phase3-E-comparison.md)). No change record has been labelled,
and the extractor feeds no component that exists. The lecturer accepts fine-tuning the embedding
model, compared with the starting model (Erhan, 2026-11-22), so the candidate is the component
whose misses the agent compensates: `intfloat/multilingual-e5-large` inside the commentary
retrieval of [ADR-025](../adr/025-commentary-retrieval.md). The serving embedder and the frozen
records are out of scope; a tuned model would live only in `tools/` as a second, separate index.

## The current pipeline

| Item | Value (sources: the run record of `2026-11-14-retrieval-corrected.json`, `retrieval.py`, the ingestion embedder) |
|---|---|
| Model | `intfloat/multilingual-e5-large`, cache revision `3d7cfbdacd47`, 1024 dimensions, `max_seq_length` 512, prefixes `query: ` and `passage: `, cosine, local on `mps` |
| Passages | page-bounded, at most 256 tokens counted with the e5 tokenizer (prefix and special tokens included); 16 to 254 tokens, mean 186.6 |
| Lexical and fused ranking | BM25 (k1 1.2, b 0.75); hybrid by reciprocal rank fusion (k 60); exact in memory, no vector store |
| Filter | the question's editions (edition filter); the generator and the agent use hybrid, edition filter |
| Evaluation code | `evaluation.py`: Evidence Recall@5 and MRR@5 per question, undefined (not 0) for questions without supporting evidence |

## Corpus, editions and change families

The manifest `data/manifests/bag-al.json` pins two editions. Each has the full Analysenliste as
XLSX and PDF and one commentary PDF; July also has the amendment PDF, and the AL handbook is a
supporting document. Only the two commentaries form the retrieval corpus.

| Edition | Commentary passages | Sections (of which introductions) |
|---|---|---|
| 2026-01-01 | 11 | 6 (1) |
| 2026-07-01 | 29 | 10 (1) |
| Both | 40 | 16 (2) |

The passages name 167 distinct position codes, 144 of them in July section 2.4 (tariff cut after
the round table on cost containment).

**Change family**, the split unit proposed here: introductions aside, two sections belong to one
family when they name a common position code or when one question's gold evidence cites both
(the same change described in two places). Paraphrases of a question belong to its family.

- By shared position codes alone (public PDFs only): 11 families of 13, 6, 4, 4, 3, 2, 2, 1, 1, 1
  and 1 passages.
- Adding the public dev cases' gold evidence (D6 cites January 2.2, July 2.4 and July 2.5): 9
  families of 20, 4, 4, 3, 2, 2, 1, 1 and 1 passages.
- Adding the frozen E cases' gold evidence as well: **6 families**. Their sizes and composition
  stay local, since they reveal which sections the frozen E cases target.

The known questions (D1 to D6, U1, U2, E1 to E6) touch 5 of the 6 families, either through gold
evidence or, for questions without supporting evidence, through a position code they name (U1
names 1034.00, which only July section 3.1 mentions). The one untouched family is a single passage
(July 2.6, the update of the AL handbook). 37 of the 38 non-introduction passages therefore sit in
families that a known question already touches.

## Labelled questions: what exists and what is missing

| Set | Questions | With supporting evidence | Gold evidence items | Status |
|---|---|---|---|---|
| Dev D1 to D6, U1, U2 (`tools/commentary_rag/cases.json`, public) | 8 | 6 | 15 | AI-drafted, judged appropriate in Erhan's review of 2026-11-15; used throughout development |
| Frozen E1 to E6 (local, hashes in `results/2026-11-21-phase3-E-freeze.json`) | 6 | 5 | 15 (13 on E2 to E6) | evaluated once in Phase 3; E1 overlaps D1 |
| Fresh held-out questions | 0 | 0 | 0 | to be authored |
| Training pairs (question, passage) | 0 | | | to be authored or generated |

An evidence item is a verbatim quote on one page of one edition; it becomes a (question, passage)
label through the passages that contain it. All 14 existing questions are **known**: they shaped
the retrieval corrections, the agent and the Phase 3 conclusions, so none may serve as the
held-out test of a tuned model. Examples of existing labels (public dev cases):

| Case | Question (abridged) | Gold passages | Dense e5 alone, edition filter |
|---|---|---|---|
| D1 | What changed on 1 July 2026 for positions 4700.00 and 1368.00? | `2026-07-01/p6/s2.5/5`, `2026-07-01/p7/s2.5/1` | Recall@5 0.5, MRR 0.25 |
| D2 | Which analysis positions are cut by 20 % on 1 July 2026? | `2026-07-01/p5/s2.4/1` | Recall@5 0, MRR 0 |
| D3 | With which positions is the new position 1779.00 not cumulable? | `2026-07-01/p3/s2.1/2` | Recall@5 1, MRR 1 |
| D5 | May position 3489.00 be billed for treatment control of onychomycosis? | `2026-01-01/p4/s2.3/3` | Recall@5 1, MRR 1 |

## Headroom and what a test could detect

- **Baseline on the known questions** (edition filter, means over D1 to D6): dense e5 alone
  Recall@5 0.75 and MRR 0.708, hybrid 0.833 and 0.722, BM25 0.875 and 0.875. On E2 to E6 the hybrid
  top 5 held 7 of 13 gold items and the top 10 held 11. There is headroom for dense retrieval, but
  it is measured on known questions only.
- **Chance floor:** with the edition filter, a random top 5 contains a given single gold passage
  with probability 5/11 = 0.455 in January, 5/29 = 0.172 in July and 5/40 = 0.125 over both.
  January questions leave little room to show anything.
- **Detectable difference:** for a paired per-question hit at 5, an exact two-sided sign test at
  the 0.05 level needs at least 6 discordant questions, all in the tuned model's favour
  (p = 0.031). The smallest detectable difference is therefore 6/n: 0.60 for 10 held-out
  questions, 0.30 for 20, 0.20 for 30 and 0.15 for 40, and more as soon as any question gets worse.
  Inside today's corpus a family-disjoint test would cover fewer than 20 passages in five small
  families, and 30 independent fresh questions over them are hard to write without
  near-paraphrases, which count as one.

## Proposed split and freezing procedure

1. **Training source outside the test families.** Because the 2026 corpus cannot supply
   family-disjoint training data, training passages come from earlier public BAG commentaries
   (time-disjoint editions) and the test from the 2026 corpus. An older passage that names a
   position code or a named project (such as transAL-2) of a 2026 test family belongs to that
   family and is dropped from training, so related changes stay on one side.
2. **Known questions are never test questions.** D1 to D6, U1, U2 and E1 to E6 may serve as a
   development check of the training code, reported apart, never as the result.
3. **Fresh held-out questions, frozen before tuning.** At least 30 answerable questions plus a few
   without supporting evidence, over at least 4 of the 2026 families, AI-drafted from the two
   commentaries or written by Erhan and decided by him, each with gold evidence (edition, page,
   quote) and its family; same-family paraphrases are grouped, and any candidate that paraphrases
   a known question is dropped. The file stays local; a freeze record with the SHA-256 of the
   questions, the gold evidence and the family assignment is committed, as for E1 to E6
   (`results/2026-11-21-phase3-E-freeze.json`), before any training data is generated. Nobody
   looks at a tuned model's rankings before the freeze, and the held-out evaluation runs once.
   Families that known questions touch may hold fresh test questions: the known questions are
   neither training nor test data of the tuned model.

## Comparison protocol

- **Models:** the base model at cache revision `3d7cfbdacd47` and one tuned copy (sentence-transformers
  with a multiple-negatives ranking loss, prefixes kept, seed and hyperparameters fixed before the
  run). A second seed shows whether a difference is more than run-to-run noise.
- **Separate indexes, identical inputs:** each model embeds the same corpus build (same passage
  IDs and text hashes, token budget 256) into its own index; every question keeps the same edition
  filter for both.
- **Primary metrics:** Evidence Recall@5 and MRR@5 per held-out question from `evaluation.py`,
  paired by question: per-question differences, the exact sign test above and a bootstrap
  interval over questions, with each family's results also shown.
- **Secondary:** the hybrid ranking (BM25 fused with each dense model by RRF, k 60), the
  configuration the generator and the agent actually use, with the same metrics.
- **Reported apart:** the known questions as a development check, and the cost and time of training.

## Smallest useful data work

Both steps run offline and cost nothing but time; a pilot is a go when both meet their threshold.

1. **Data inventory of earlier commentaries (about 2 to 4 hours):** pin two to four earlier
   public BAG commentaries by SHA-256 in a separate manifest, run the existing corpus builder on
   them, and count passages, families and the passages that remain after dropping those related to
   a 2026 family. Proposed threshold: at least 100 remaining training passages from at least 10
   families. Parser fit to older layouts is a risk this step reveals.
2. **Fresh held-out questions (about 4 to 6 hours with Erhan's decisions):** draft, decide and
   freeze the questions of step 3 above. Proposed threshold: at least 30 answerable questions over
   at least 4 families, so that a 0.20 difference is detectable at all.

If step 1 falls short, the remaining fine-tuning design is the lopsided in-corpus split (train on
the large family, test fresh questions on the others), whose result could at best be weak;
Zwischenbericht 1 already counts a missing advantage of fine-tuning as a usable result. Variant 1
is the other evaluated option, subject to the lecturer's view on whether fine-tuning is mandatory.

## Alternative: selective evidence search (variant 1)

In Phase 3 the agent searched in all six agent cells, also on E4 and E5, where its first five
passages already held all required evidence ([comparison evidence](2026-11-21-phase3-E-comparison.md));
whether it can tell when not to search is untested. A bounded extension decides per question
whether to search, and is evaluated against fixed top 10 and the always-searching agent on fresh
cases, half with evidence inside the top 5 and half beyond rank 10 (under the edition filter the
11 January passages leave room for only one beyond rank 10), with at least three repeats per
cell. It needs no training data and no GPU, only fresh cases, and it runs through the existing
books of [ADR-026](../adr/026-commentary-evidence-search.md).
Its limits are the same small corpus, and that the books admit at most 8 cases of three conditions
per invocation (worst case USD 10.3488 per case).

## Jev's role: one typed decision for the development lead

Jev is TypeSafe's System One model: it returns typed judgements with probabilities (Choice, Noul,
Score) rather than text. It would make exactly one decision, before the freeze in step 3.

- **Decision:** which 2026 change family a candidate held-out question asks about, so that
  paraphrases and related changes land in one family. Erhan still decides admission at the freeze.
- **Minimal inputs:** the candidate question and one description per family built from public
  material only: its sections' titles and position codes, grouped by shared codes and the public
  dev cases (9 families). Never the six-family grouping, which uses the local E gold, and never
  the E questions, gold evidence, rubric or answers.
- **Code first:** position codes in the question decide by lookup without Jev; Jev is asked only
  when a question names none.
- **Allowed outcomes:** `assign` (one family, by code lookup or by a Jev Choice at or above a
  confidence threshold, 0.6 as a placeholder until calibrated) or `needs_erhan` (codes of two
  families, confidence below the threshold, Jev's `none` option, or Jev unavailable).
- **Fallback:** Erhan assigns the family by hand.
- **Offline exercise (2026-11-22, kept locally and git-ignored, not committed):** six illustrative candidates through
  this logic, with Jev's answers hand-written in the response shape of the TypeSafe API
  documentation and **labelled mocked**. Outcomes: one `assign` by code lookup (Jev not called),
  one `assign` from a mocked answer at confidence 0.81, and four `needs_erhan` (two families
  named by codes, mocked confidence 0.42, mocked `none`, simulated outage). This shows the
  control flow only and says nothing about Jev's accuracy. The exercise used the six-family
  grouping locally; a real run would use the nine public descriptions.
- **Before any live call:** a live run would send candidate held-out questions to an external
  provider before they are frozen, and add a provider seam outside the services. Both need Erhan's
  decision (and an ADR if adopted); TypeSafe's prices were not verified.

## Cost estimate (no spending authorised)

Expected values are planning figures, not bounds. A maximum is price × timeout × (1 + retries),
or the books' ceiling where they apply.

| Item | Expected (USD) | Maximum (USD) | Basis |
|---|---|---|---|
| Data inventory and freeze (steps 1, 2) | 0 | 0 | local, offline |
| Training queries drafted in a Claude Code session and decided by Erhan | 0 API | 0 API | no metered API call |
| or: training queries generated by `claude-opus-5-5` at effort `max`, 5 passages per call, N = 100 passages (20 calls) | 4.13 (0.206 per call) | 28.93 (0.72336 per call, one retry each) | `pricing.json`: input 4, output 20 per million tokens, global inference. Expected: about 2,000 input tokens and the median 9,922 output tokens (thinking included) of the 26 calls the Phase 3 ledger settled (range 448 to 25,270). Ceiling as in ADR-026: 2,000 input tokens with a 10 % margin at 8 per million plus 32,000 output tokens, times 1.1 |
| Training on Hugging Face Jobs, `a10g-small` | 0.75 (3 jobs of about 15 minutes) | 3.00 (3 jobs, 30-minute timeout, one retry each) | 1.00 per hour, billed per minute while starting or running (Hugging Face Jobs pricing, retrieved 2026-11-22) |
| or: training locally on the M1 Pro (32 GB, `mps`) | 0 | 0 | to be confirmed by a one-epoch smoke run |
| Evaluation (two indexes, about 40 questions) | 0 | 0 | local, offline |
| Jev live calls (optional) | not estimated | not estimated | prices not verified |
| **Fine-tuning pilot, total (N = 100)** | **about 5** (0.75 if the queries are drafted in a session) | **about 32** (3.00 if drafted in a session) | queries by API, training on `a10g-small`; 0 if both run locally and the queries are drafted in a session |
| Selective evidence search, 10 cases × 3 conditions × 3 repeats | about 23 | 92.939448 (remaining aggregate limit) | Phase 3 calculated means per cell: agent 0.263640, fixed top 10 0.246717 (one run per cell, variance unknown) |

The books hold USD 7.060552 of the USD 100 aggregate limit for Phases 2 and 3. Whether Phase 4
spending counts against that limit, and which provider pays for it, is Erhan's decision.
