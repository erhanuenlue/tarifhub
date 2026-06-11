# 03 — Second source: ePL Spezialitätenliste, FHIR R5 (Block 1)

Run `/new-source ePL Spezialitätenliste (BAG, FHIR R5)`.

Context that matters: this source is the format-diversity proof — hierarchical FHIR R5 against EAL's flat XLSX is the harmonisation thesis in miniature, and the BAG ships SL as FHIR-only from June 2026. Source: the BAG ePL platform (sl.bag.admin.ch; IG at build.fhir.org/ig/bag-epl). BAG = legally clean, in scope.

Beyond the skill's standard steps, this source specifically requires:

- A real sample bundle committed as a golden fixture (trimmed to a few hundred records; note the trim in the fixture README).
- The FHIR parser handles: nested extensions, the IDMP-based structure, DE/FR/IT designations, and both price-carrying and point-carrying entries. Failures fail closed into the review queue.
- `ai_map` runs live on this source too — capture the review rate and three before/after mapping examples for the docs (criterion 16 evidence; the XLSX-vs-FHIR comparison paragraph writes itself from this).
- The harmonisation report table in `docs/arc42/10-quality-requirements.md` gains a second row: records in/out, review rate, confidence histogram per source.

Queued follow-ups from Block 0 — scope them into this plan as their own tasks:

- **Ingestion read-API Postgres parity:** the ingestion service's read endpoints must behave identically on Postgres and the SQLite mirror (the Block-0 proof exposed cross-engine drift; pin it with tests against both engines).
- **FR search-ranking tuning:** French cross-lingual queries rank noticeably below DE/EN (Block-0 pgvector proof); tune (e5 query prefixing / normalization), prove with a small ranked-retrieval table in the evidence doc.

Done means: both sources flow end-to-end in one pipeline run; idempotency test passes across both; the pinned-hash test covers one record from each; the docs table shows both rows. Verifier + determinism-auditor before `/ship`. Journal: what the AI got wrong about FHIR R5 specifically — that comparison is Fazit gold.
