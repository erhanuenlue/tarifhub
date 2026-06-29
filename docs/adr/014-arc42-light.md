# ADR-014: arc42-light retained as the documentation framework

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
The dossier is itself a graded deliverable: the CAS criteria expect requirements, quality goals, architecture views, and recorded decisions, and there is one maintainer working against a fixed deadline. The constraint that makes this a decision: the framework must map onto the grading criteria without demanding more writing than one person can sustain.

## Decision
We keep arc42 in a light profile (all 12 chapters present, only load-bearing sections filled), combined with C4 diagrams and this ADR register, published via MkDocs Material.

## Alternatives weighed
- **Diátaxis**: optimised for product documentation (tutorials/how-tos), the wrong cut for a graded architecture dossier.
- **Pure C4 + ADRs**: covers structure and decisions but has no home for requirements, quality, or risks (criteria 1 to 3).
- **Astro Starlight**: a prettier site, but a second JS toolchain for zero grading value, against Python-first minimalism.

## Consequences
- (+) Chapters map roughly 1:1 onto the grading criteria (see [criterion-map](../criterion-map.md)). Graders navigate a standard they already know.
- (-) Some chapters stay thin, which is acceptable in the light profile. Revisit if a grader or reviewer cannot locate a criterion's evidence via the criterion map.

*Reference: fuller reasoning to appear in CAS Dossier §5 (forthcoming). This ADR is self-contained. Lineage: new.*
