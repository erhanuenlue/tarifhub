# tarifhub: Architecture Documentation

**AI-assisted harmonisation above a deterministic freeze line; one versioned tariff API below it.**

This site is the project-thesis deliverable for the FFHS CAS *AI-Assisted Software Engineering* (FS26), together with the source code in the public Git repository at [github.com/erhanuenlue/tarifhub](https://github.com/erhanuenlue/tarifhub).

- Start with [Introduction & Goals](arc42/01-introduction-goals.md), then the [Solution Strategy](arc42/04-solution-strategy.md), then the [Decisions](arc42/09-architecture-decisions.md).
- The AI-assisted build method, the central contribution of this CAS, is documented under **AI-Assisted Method**.
- The [Criterion Map](criterion-map.md) is the evidence index: each assessment criterion mapped to where it is addressed.
- The [5-minute presentation](presentation/index.html) is the presentation deck (Reveal.js): the idea and how it was engineered with the AI-assisted auto-loop.

*The one rule that defines this system: no AI computes or mutates a billing value at serve time.*
