# Report structure

> The written project work, in the module's short formula, is
> **RE + SAD + Projektbeschreibung + Reflexion (KI‑Einsatz) + Fazit**, plus the **solution (code)**
> itself. This page maps each part to where it is in this site and the repository, so the whole
> submission can be read in that order. Requirements (RE) are folded into the architecture
> document, as permitted.

| Part | What it covers | Where to read it |
|---|---|---|
| **RE — Requirements** | Use cases and functional requirements, stakeholders, and the quality requirements (NfA) | [1 · Introduction & Goals](arc42/01-introduction-goals.md) (use‑case catalogue, FR table, stakeholders) · [10 · Quality Requirements](arc42/10-quality-requirements.md) (NfA, acceptance criteria) |
| **SAD — Architecture & solution approach** | The freeze‑line solution strategy, the architecture views, and the decisions behind them | [4 · Solution Strategy](arc42/04-solution-strategy.md) · [5 · Building Blocks](arc42/05-building-block-view.md) · [6 · Runtime View](arc42/06-runtime-view.md) · [7 · Deployment View](arc42/07-deployment-view.md) · [8 · Crosscutting Concepts](arc42/08-crosscutting-concepts.md) · [9 · Architecture Decisions (18 ADRs)](arc42/09-architecture-decisions.md) |
| **Projektbeschreibung — Realisation** | How the SAD was implemented, the code structure, and how it was validated | [5 · Building Blocks](arc42/05-building-block-view.md) (blocks → code) · the four services and the console in [`services/` and `apps/`](https://github.com/erhanuenlue/tarifhub) · [12 · Test Strategy](arc42/13-test-strategy.md) · [10 · Test & pipeline results](arc42/10-quality-requirements.md) |
| **Reflexion — AI use** | How AI was used across software design and development, and the reflection on it | [AI Tools & Workflow](method/ai-tools.md) (per phase: generation, review, refactoring, research) · [The AI‑SE Framework](method/ai-se-framework.md) (the loop and the guardrails) · [Decision Matrix](method/decision-matrix.md) · [Journal](method/journal.md) |
| **Fazit — Conclusion** | What this CAS produced and what is carried into future practice | [Conclusion](method/fazit.md) |
| **Solution — the code** | The running solution itself, which is part of the project work | [`github.com/erhanuenlue/tarifhub`](https://github.com/erhanuenlue/tarifhub): `services/`, `apps/`, `db/`, `deploy/` |

The [Criterion Map](criterion-map.md) cross‑references the same material to the 18 assessment
anchors, and the authorship confirmation is on the [Eigenständigkeit](method/eigenstaendigkeit.md)
page.
