
**Disagreements**
- **#5 Perspektiven:** I would not score this as **6**. The official tiers are discrete: `0/1/4/7`. If the UC-05 contradiction is enough to fail the top anchor, the fallback is **4**, not 6. Evidence: UC-05 is marked `<<designed>>` in [use-cases.puml](/Users/karakan/Documents/Tarif/tarifhub/docs/diagrams/use-cases.puml:27), while the catalogue and acceptance table call it live in [arc42/01](/Users/karakan/Documents/Tarif/tarifhub/docs/arc42/01-introduction-goals.md:66) and [arc42/10](/Users/karakan/Documents/Tarif/tarifhub/docs/arc42/10-quality-requirements.md:423).

- **#1 Use-Cases & Anforderungen:** I would also treat the same UC-05 issue as a #1 risk, not only #5. The use-case diagram is embedded in §1 as part of the use-case evidence, so the requirements are not fully `widerspruchsfrei` while it says UC-05 is not implemented. I would score **3 instead of 5** until that diagram is fixed.

- **#15 KI-Werkzeuge:** I would score current state lower than **7** if graded today. The 7-point tier still requires an Eigenständigkeitserklärung to be present. Here the chapter says the declaration is a placeholder, not signed, and “not yet his words” in [ai-tools.md](/Users/karakan/Documents/Tarif/tarifhub/docs/method/ai-tools.md:181); the PDF builder has a second placeholder in [tools/build_pdf.py](/Users/karakan/Documents/Tarif/tarifhub/tools/build_pdf.py:386). I would give **1/12 until the real declaration is inserted**, unless the grader generously treats a placeholder as “vorhanden.”

**Missed Gaps**
- **#2 NfA SMART:** The auditor says every NfA has a governing ADR, but NfA-5 is `n/a` and NfA-6 is an owner-decision reference, not an ADR link, in [arc42/10](/Users/karakan/Documents/Tarif/tarifhub/docs/arc42/10-quality-requirements.md:7). Also, search latency has a target but no measured p95, only “method-defined” while compose search returns 501. Probably not a point loss because enough strong NfAs remain, but it is a cleanup gap.

- **#15, also #4 report consistency:** The method evidence contains impossible chronology for today, 14 Jun 2026: it says Fable access “ended 22 June 2026” in [ai-se-framework.md](/Users/karakan/Documents/Tarif/tarifhub/docs/method/ai-se-framework.md:22) and ADR-018 dated 13 Jun says access “ended on 22 Jun 2026” in [ADR-018](/Users/karakan/Documents/Tarif/tarifhub/docs/adr/018-orchestrator-model-lifecycle.md:3). That weakens evidence honesty in the AI-method chapter.

- **#4/#15 ADR consistency:** ADR-018 exists and is in MkDocs nav, but the consolidated ADR register in [arc42/09](/Users/karakan/Documents/Tarif/tarifhub/docs/arc42/09-architecture-decisions.md:6) stops at ADR-017. If ADR-018 is part of the model-governance evidence, it should be in the register.

I ran `python3 tools/cas_check.py`; it still reports `63/63`, so these are judgment-level gaps, not structural-floor misses.
