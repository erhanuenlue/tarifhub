# Report structure

> The written project work, in the module's short formula, is
> **RE + SAD + Project Description + Reflection (AI use) + Conclusion**, plus the **solution (code)**
> itself. This page maps each part to where it is in this site and the repository, so the whole
> submission can be read in that order. Requirements (RE) are folded into the architecture
> document, as permitted.

| Part | What it covers | Where to read it |
|---|---|---|
| **RE (Requirements Engineering): Requirements** | Use cases and functional requirements, stakeholders, and the quality requirements (NFR) | [1 · Introduction & Goals](arc42/01-introduction-goals.md) (use‑case catalogue, FR table, stakeholders) · [10 · Quality Requirements](arc42/10-quality-requirements.md) (NFR, acceptance criteria) |
| **SAD (Software Architecture Document): Architecture & solution approach** | The freeze‑line solution strategy, the architecture views, and the decisions behind them | [4 · Solution Strategy](arc42/04-solution-strategy.md) · [5 · Building Blocks](arc42/05-building-block-view.md) · [6 · Runtime View](arc42/06-runtime-view.md) · [7 · Deployment View](arc42/07-deployment-view.md) · [8 · Crosscutting Concepts](arc42/08-crosscutting-concepts.md) · [9 · Architecture Decisions (19 ADRs)](arc42/09-architecture-decisions.md) |
| **Project Description: Realisation** | How the SAD was implemented, the code structure, and how it was validated | [5 · Building Blocks](arc42/05-building-block-view.md) (blocks → code) · the four services and the console in [`services/` and `apps/`](https://github.com/erhanuenlue/tarifhub) · [12 · Test Strategy](arc42/13-test-strategy.md) · [10 · Test & pipeline results](arc42/10-quality-requirements.md) |
| **Reflection: AI use** | How AI was used across software design and development, and the reflection on it | [AI Tools & Workflow](method/ai-tools.md) (per phase: generation, review, refactoring, research) · [The AI‑SE Framework](method/ai-se-framework.md) (the loop and the guardrails) · [Decision Matrix](method/decision-matrix.md) · [Journal](method/journal.md) |
| **Conclusion** | What this CAS produced and what is carried into future practice | [Conclusion](method/fazit.md) |
| **Solution: the code** | The running solution itself, which is part of the project work | [`github.com/erhanuenlue/tarifhub`](https://github.com/erhanuenlue/tarifhub): `services/`, `apps/`, `db/`, `deploy/` |

## What the assessment weights most

Four things carry the most weight in the assessment. This is where each is answered, most directly.

1. **How AI was used to reach the goal** (criteria 15 and 16). The goal, a trustworthy deterministic tariff platform where no AI computes or mutates a billing value, and the AI apparatus built to serve it, are in [The AI‑SE Framework](method/ai-se-framework.md), with the worked, phase‑by‑phase evidence in [AI Tools & Workflow](method/ai-tools.md) and the mode analysis in the [Decision Matrix](method/decision-matrix.md).
2. **What I learned, the experience report** (criterion 9). The contemporaneous events are in the [Journal](method/journal.md), and the synthesised lessons drawn from them are in [What these events taught me](method/journal.md#what-these-events-taught-me).
3. **The conclusion** (criterion 18). The reflective close, the three non‑delegated vetoes, the honest limits and the single transfer rule, is the [Conclusion](method/fazit.md).
4. **The solution, not only the code** (criteria 3 and 4). The problem, the strategic response and the value each choice delivers to a stakeholder are in [4 · Solution Strategy](arc42/04-solution-strategy.md), with the problem and stakeholders set out in [1 · Introduction & Goals](arc42/01-introduction-goals.md). The running solution itself is in the repository (`services/`, `apps/`, `db/`, `deploy/`).

The [Evidence Index](criterion-map.md) cross‑references the same material to the 18 assessment
anchors, and the authorship confirmation is on the [Selbständigkeitserklärung](method/eigenstaendigkeit.md)
page.
