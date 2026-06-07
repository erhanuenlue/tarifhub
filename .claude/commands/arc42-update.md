---
description: Update the arc42 architecture docs (and an ADR when a decision changed) to match a code/architecture change, then refresh the MkDocs nav. Keeps docs in lockstep with the four-layer reality.
argument-hint: <what changed, e.g. "added cumulation rules to TarifIQ">
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
model: claude-opus-4-8
---

Bring the architecture docs in line with this change: **$ARGUMENTS**

TarifHub documents architecture with **arc42** (chapters in `docs/arc42/01..12`) plus
**ADRs** (`docs/adr/NNN-*.md`), published as an MkDocs Material site (`docs/mkdocs.yml`).
Keep prose-first, factual, and aligned with the brand/layer names already in `README.md`.

## Do this

1. **Identify the affected chapters.** Common targets:
   - `05-building-block-view.md` — when a service/app/module is added or restructured
     (the four layers: L0 ingestion, L1 serving + mcp, L2 intelligence/TarifIQ, L3 apps:
     TarifGuard, KassenFlow, MeldePilot).
   - `06-runtime-view.md` — when a flow changes (ingest→freeze→serve, a crosswalk lookup,
     a combinability check).
   - `07-deployment-view.md` — new container, Helm value, or port.
   - `08-crosscutting-concepts.md` — anything touching the determinism boundary, hashing,
     de-identification, or security.
   - `09-architecture-decisions.md` — link any new ADR here.
   Read the target chapter(s) before editing; make minimal, additive edits.

2. **Add or update an ADR when a *decision* was made.** Next number after the latest in
   `docs/adr/` (currently up to `006-four-layer-product.md`). Use the existing ADR style:
   Context → Decision → Consequences → Status. Reference it from
   `docs/arc42/09-architecture-decisions.md`.

3. **Update the MkDocs nav** in `docs/mkdocs.yml` if you added an ADR or page (note: the
   nav currently lists ADR-001..005 — add new ADRs there).

4. **Verify the site builds:** `mkdocs build -f docs/mkdocs.yml --strict` (or
   `mkdocs serve -f docs/mkdocs.yml` to preview). Fix any broken links the strict build flags.

5. Summarize which chapters/ADRs changed. When ready to ship the docs, use `/ship`.

Keep the determinism story accurate: AI assists pre-freeze and for search/explain only;
authoritative values are frozen, versioned, hashed records. Do not overstate AI's role.
