
**Disagreement**

- **Criterion 5: I would not call 7/7 safe as-is.** I would treat it as **4/7 until the stale behavior/interaction artifacts are fixed**. The use-case diagram still says **UC-05 is “specified, not yet implemented”** and **UC-09 serving endpoint is “designed”**, while the catalogue says UC-05 and UC-09 are live in this release: [use-cases.puml](/Users/karakan/Documents/Tarif/tarifhub/docs/diagrams/use-cases.puml:30), [arc42/01](/Users/karakan/Documents/Tarif/tarifhub/docs/arc42/01-introduction-goals.md:58). The runtime/review docs also conflict: §5 says the review form is operable through the console route, while §6 says the console review form and POST endpoint are not implemented: [arc42/05](/Users/karakan/Documents/Tarif/tarifhub/docs/arc42/05-building-block-view.md:67), [arc42/06](/Users/karakan/Documents/Tarif/tarifhub/docs/arc42/06-runtime-view.md:40). That is exactly the kind of diagram/text inconsistency a strict conjunctive read can punish.

**Missed Gaps**

- **Criterion 15 closure is broader than the auditor’s action item.** Updating only `docs/method/ai-tools.md` is insufficient. The LaTeX PDF builder appends a second hardcoded placeholder declaration page: [tools/build_pdf.py](/Users/karakan/Documents/Tarif/tarifhub/tools/build_pdf.py:386). So the fix must replace both the Markdown placeholder and the PDF-builder declaration block, then rebuild and inspect the PDF.

- **Criterion 1 is exposed by the stale use-case diagram.** I would not necessarily dock it if the tables are the grading anchor, but the PDF currently contains contradictory status labels inside the use-case evidence area. That weakens “eindeutig und widerspruchsfrei” for requirements.

- **PDF cleanup gap is larger than `mkdocs.yml`/`brand.css`.** Current diagram sources still contain em dashes, and `pdftotext build/pdf/tarifhub-cas.pdf -` exposes them in the built PDF. Examples are [use-cases.puml](/Users/karakan/Documents/Tarif/tarifhub/docs/diagrams/use-cases.puml:9), [seq-review-freeze.puml](/Users/karakan/Documents/Tarif/tarifhub/docs/diagrams/seq-review-freeze.puml:7), and [runtime-harmonise-freeze.svg](/Users/karakan/Documents/Tarif/tarifhub/docs/diagrams/runtime-harmonise-freeze.svg:3). This is not a direct point anchor, but it is a report/PDF quality risk.

No disagreement with the auditor’s Criterion 10 conditional; I could not verify anonymous GitHub visibility from this environment because GitHub API access failed.
