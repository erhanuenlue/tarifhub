# TarifHub: Architecture Documentation

**AI-assisted harmonisation above a deterministic freeze line; one versioned tariff API below it.**

This site is the project-thesis deliverable for the FFHS CAS *AI-Assisted Software Engineering* (FS26). The PDF hand-in is the [Full document (PDF)](print_page/) export of this site; the source code lives in the public Git repository at [github.com/erhanuenlue/tarifhub](https://github.com/erhanuenlue/tarifhub).

## Contents

**Architecture (arc42)**

1. [Introduction & Goals](arc42/01-introduction-goals.md)
2. [Constraints](arc42/02-constraints.md)
3. [Context & Scope](arc42/03-context-scope.md)
4. [Solution Strategy](arc42/04-solution-strategy.md)
5. [Building Blocks](arc42/05-building-block-view.md)
6. [Runtime View](arc42/06-runtime-view.md)
7. [Deployment View](arc42/07-deployment-view.md)
8. [Crosscutting Concepts](arc42/08-crosscutting-concepts.md)
9. [Architecture Decisions](arc42/09-architecture-decisions.md)
10. [Quality Requirements](arc42/10-quality-requirements.md)
11. [Risks & Technical Debt](arc42/11-risks-technical-debt.md)
12. [Glossary](arc42/12-glossary.md)
13. [Test Strategy](arc42/13-test-strategy.md)

**Architecture Decisions** — the full ADR log (ADR-001 … ADR-018) is in the sidebar and summarised in [§9](arc42/09-architecture-decisions.md).

**AI-Assisted Method** — the central contribution of this CAS:

- [The AI-SE Framework](method/ai-se-framework.md)
- [AI Tools & Workflow](method/ai-tools.md)
- [Decision Matrix](method/decision-matrix.md)
- [Journal (excerpts)](method/journal.md)
- [Conclusion](method/fazit.md)

**Reference**

- [Summary](zusammenfassung-de.md)
- [Criterion Map](criterion-map.md) — the grader's index: every grading criterion mapped to its evidence and its location.
- [5-minute presentation](presentation/index.html) — the presentation deck (Reveal.js): the idea and how it was engineered with the AI-assisted auto-loop.

*The one rule that defines this system: no AI computes or mutates a billing value at serve time.*
