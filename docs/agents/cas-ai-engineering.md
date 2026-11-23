# CAS AI Engineering: project frame for agents

Read by `lead-engineer` and any worker that touches course deliverables. It records which
course a piece of work belongs to, what counts as this course's contribution, and what the
remaining delivery requires. The current milestone is issue
[#62](https://github.com/erhanuenlue/tarifhub/issues/62) (Phase 4, variant 2 through data feasibility); the
earlier milestone [#60](https://github.com/erhanuenlue/tarifhub/issues/60) is closed.

## Two courses, one repository

| | Earlier: CAS AI-Assisted Software Engineering | Current: CAS AI Engineering (DS-C-AI001, HS 2026/27) |
|---|---|---|
| Status | submitted 3 July 2026 | interim reports 1 to 3 written; Phase 4 open |
| Reference point | baseline commit `530f8501a288f8e99cb7480ace326d42bef9a9c8` | squash commits on `main` after the baseline |
| Requirement set | historical: `docs/criterion-map.md`, `tools/cas_check.py` | the course's Moodle pages (see Delivery requirements) |

**Inherited at the baseline** (present in `530f850`): AL import from one file (`bag_eal`), the
EPL source (`bag_epl`, ADR-015),
pre-freeze `ai_map`, frozen hashed versioned records, REST and FHIR queries, point-in-time and
per-record version diff, the rule-based `/explain` (no LLM, ADR-017), pgvector semantic search
with the multilingual-e5 embedder, read-only MCP tools, the `tools/search_eval` harness, the
console and TarifIQ; ADR-001 to ADR-019.

**Contribution of this course** (after the baseline), in squash commits on `main`:

| Phase | What | ADR | PR, squash commit |
|---|---|---|---|
| Data | manifest-dated, multi-edition AL import | ADR-021 | #50, `6cc68da` (its workflow, skills, ADR-022 and CI parts are maintenance) |
| Data | read-only comparison of two dated editions; selected workbook texts | ADR-023, ADR-024 | #51 `b87095f`, #52 `88cd681` |
| 2, RAG | BAG commentary retrieval and cited answers, outside the services | ADR-025 (accepted) | #53, `79edcde` |
| 3, Agent | bounded evidence-seeking agent, spending protection, one-question runner, D1 live run | ADR-026 (proposed, evaluated) | #54 `e1f4ae9`, #55 `df5d20d`, #56 `e68d261` |
| 3, Evaluation | frozen E1 to E6 comparison and blinded review | ADR-026 | #57 `861994b`, #58 `05aba9b` |

Preparation, not contribution: PR #49 (ADR-020, instruction files), the journal commits and
`bb151ff` (a pre-registered measurement design) between the baseline and #50. Label the inherited platform first in every deliverable, then the
new capability and its measured result.

## Current evidence

- Phase 2: [retrieval](../evidence/2026-11-14-commentary-retrieval.md) and
  [generation](../evidence/2026-11-15-commentary-generation.md), Erhan's review of the eight dev
  cases.
- Phase 3: [D1 live run](../evidence/2026-11-20-phase3-d1-agent-run.md) and the
  [E1 to E6 comparison](../evidence/2026-11-21-phase3-E-comparison.md): on E2 to E6 the overall
  verdict was `yes` for the agent on 5 of 5 cases, for fixed top 10 on 4 and for fixed top 5 on
  3; E1 reported apart; one run per cell, one reviewer, partial blinding.
- Phase 4: [feasibility of embedding fine-tuning](../evidence/2026-11-22-phase4-finetuning-feasibility.md)
  (no-go on the current corpus, data work first) and the
  [training-data inventory](../evidence/2026-11-23-phase4-training-data-inventory.md) of 2026-11-23
  (variant 2, chosen by Erhan for the data-feasibility stage: 30 eligible passages in 14 families
  from the 2024 and 2025 commentaries, 70 short of the proposed 100; the evaluation design supports
  only an exploratory comparison; next decision in issue #62).
- Books: USD 7.060552 committed of the USD 100 aggregate limit for Phases 2 and 3.

## Phase 4 options

Per the course, Phase 4 is either variant 1, extend the agentic behaviour (justify, evaluate,
assess), or variant 2, fine-tune a model (justify, evaluate, assess); both end in a demo and a
presentation. In the module forum the lecturer confirmed that the two variants are alternatives
and that an evaluated fine-tuning of the embedding model, compared with the starting model, is
acceptable (the lecturer's forum clarification, relayed by Erhan on 2026-11-22; the post itself is
not reproduced here). This settles what an October note had left open: the extract lists
fine-tuning among the module's contents beside RAG, agents and evaluation, but either variant
completes Phase 4. Zwischenbericht 1 had planned a LoRA Change Extractor instead; the feasibility
page explains the change.

## Delivery requirements

Source: a local extract of the course's Moodle pages dated 2026-10-06, not re-verified since;
check Moodle before relying on a date or a rule.

- **Presentation:** a PDF named `4_Nachname_Vorname.pdf` in the course's results database by the
  Thursday before PVA 5 (PDF only, file names `n_Nachname_Vorname.pdf`).
- **Demo in PVA 5.** Graded: presentation and demo in the last PVA, and the structure and
  traceability of the source code on FFHS-Git. The PVA 5 date is not in the extract.
- **Code on FFHS-Git:** after Block 4, the commented source code in a repository on
  `git.ffhs.ch`, the lecturer with at least Reporter access, and a clickable link to it in
  Moodle. The extract's briefing lists formal criteria "analog Semesterarbeit" whose violation it rates as
  grade 1: code only in the FFHS-Git repository; a project directory whose `README.md` opens with
  an honest declaration of AI use and third-party code; own code only; easy to find; a Jupyter
  notebook with Markdown explanations and executed cells.
- **Every PDF:** a complete list of sources and of AI tools (tool, purpose, affected parts); the
  declaration of independent work is confirmed in Moodle.

Open gaps (planning, not yet decided): this repository is on GitHub and refers to no FFHS-Git copy,
README declaration or executed notebook; whether they exist elsewhere was not checked here.

## Regression check, not requirement set

`python3 tools/cas_check.py --ci` measures the earlier course's structural floor against
`tools/cas_baseline.json`. Keep it green as a regression check on `docs/` changes; it says
nothing about this course's requirements.
