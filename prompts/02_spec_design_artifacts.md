# 02 — Specification & design artifacts (Block 0)

Read AGENTS.md and CLAUDE.md, then plan before writing.

Goal: produce the specification and design artifacts that criteria 1–6 and 8 of the grading table score, as files in `docs/`:

1. **Use-case catalogue** (`docs/arc42/01-introduction-goals.md` + a UML use-case diagram as Mermaid or PlantUML source rendered to SVG): trigger ingest · review low-confidence mapping (console form) · freeze record · read tariff by code · point-in-time / diff query · semantic search · MCP get/search · console master-detail lookup · explain. Each with actor, trigger, outcome, and the functional requirement it realises.
2. **Two additional sequence diagrams**: a search request through serving, and the review→freeze loop including the console form and `guard`-protected freeze. Same style as the existing harmonise→freeze sequence.
3. **C4 component view** of `services/ingestion` (the richest service): adapters, parsers, mapper + `ai_map` seam, validator, confidence, review queue, freeze, audit.
4. **The "Modern application concepts" page** (`docs/arc42/08-crosscutting-concepts.md` section): the enterprise concepts the course teaches, each with its implementation here — dependency injection (`Depends`), declarative validation (Pydantic v2), persistence abstraction (SQLAlchemy 2 + repositories), REST + OpenAPI, configuration injection (pydantic-settings), health/readiness probes, OpenTelemetry, container-first packaging, dev-mode reload, async — closed by the ADR-01 reasoning and the Modulplan Lehrmittel-[5] (FastAPI, Apress) citation. Plain architecture content; no JVM comparisons needed beyond one line noting the concepts are stack-portable.
5. **Materialise the ADR register**: `docs/adr/001…013` as files from the Architecture v2.1 register (use `docs/adr/template.md`; each ≤ a page — context, decision, alternatives, consequences), plus **ADR-14** (`docs/adr/014-arc42-light.md`): arc42-light retained over Diátaxis / pure C4+ADR / Starlight — reasoning in CAS Dossier §5. The brain_sync hook will pick them all up into the vault index automatically.

Constraints: no running code needed for any of this — do not refactor code in this session. Diagram sources committed next to rendered SVGs. Use the existing arc42 chapter files; extend, don't fork. Everything must be findable from the docs index in one click.

Done means: the six artifacts exist, render correctly in `mkdocs serve`, and a verifier pass confirms each grading criterion 1–6 + 8 can point at a concrete section. Curate the journal entry: note what the AI drafted vs what you corrected on the diagrams — that delta is criterion-15 material.
