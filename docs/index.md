# tarifhub: Architecture Documentation

**AI-assisted harmonisation above a deterministic freeze line; one versioned tariff API below it.**

This site is the Semesterarbeit deliverable for the FFHS CAS *AI-Assisted Software Engineering* (FS26). The PDF hand-in is the [Full document (PDF)](print_page/) export of this site; the source code lives in the public Git repository at [github.com/erhanuenlue/tarifhub](https://github.com/erhanuenlue/tarifhub).

- Start with [Introduction & Goals](arc42/01-introduction-goals.md), then the [Solution Strategy](arc42/04-solution-strategy.md), then the [Decisions](arc42/09-architecture-decisions.md).
- The AI-assisted build method, the heart of this CAS, is documented under **AI-Assisted Method**.
- The [Criterion Map](criterion-map.md) is the grader's index: every grading criterion mapped to its evidence, one click away.

*The one rule that defines this system: no AI computes or mutates a billing value at serve time.*
