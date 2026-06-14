# CAS final correctness fixes (run in a FRESH `claude` session at /effort ultracode)

> **Gate-01: pre-approved by the owner (14 Jun).** Produce and log the plan, then proceed. STOP only for: scope beyond this prompt, freeze-line contact, a green-contract/ratchet breach, a destructive op, or the Eraser MCP being unreachable (diagram re-render).

An independent senior audit found a small set of defects that reach the **rendered PDF** plus two CI/security nits. Fix all of them, re-render the affected diagrams, rebuild the PDF, and verify. Docs + diagram sources + `tools/` + `.github/` only; no product value-path code, no freeze-line files, no em-dashes in PDF-bound text, English only (keep the protected cas_check anchors). Branch `docs/final-fixes`, then `/ship`; auto-merge on the green-contract. Source `.env` first for the Eraser token: `set -a; source .env; set +a`.

## 1. (M1) Fix the UC-05 diagram-vs-text contradiction — it's baked into the PDF
`docs/diagrams/use-cases.puml` marks **UC-05 `<<designed>>`** (line ~30) and the legend reads "specified, not yet implemented (UC-02, UC-05)" (line ~50), but the catalogue + acceptance tables say UC-05 is **"live (this release)"** (`docs/arc42/01-introduction-goals.md:67`, `docs/arc42/10-quality-requirements.md:423`). Reconcile: set UC-05's stereotype to match its real status (live), correct the legend (and UC-02 if it is also live now). **Re-render `use-cases.puml` → `use-cases.svg`** (PlantUML; if unavailable, edit the SVG text directly so the rendered figure matches), then it flows into the PDF on rebuild. `cas_check` does not read rendered SVG text, so this only closes by re-rendering.

## 2. (S2) Strip em-dashes from the 3 diagram sources that reach the PDF
These rendered SVGs still contain `—` and are embedded in the PDF: `docs/diagrams/runtime-harmonise-freeze.svg` (3), `docs/diagrams/er-data-model.svg` (2), `docs/diagrams/use-cases.svg` (1). Replace each `—` with a hyphen/colon in the **diagram sources** (the `.svg` and, where applicable, the `.puml`/Eraser source), re-render, and confirm zero `—` in any embedded figure.

## 3. (S3) Fix the future-date stated as past
Today is 2026-06-14, but three PDF-bound spots assert Fable 5 access "ended 22 June 2026" as a completed past event (8 days in the future): `docs/method/ai-se-framework.md:22`, `docs/adr/018-orchestrator-model-lifecycle.md` (title + body ~line 7). Reword to future/planned tense ("scheduled to end 22 Jun 2026" / "the planned switch on 22 Jun 2026"), consistent with the ADR's own 2026-06-13 date.

## 4. (S4) Add ADR-018 to the architecture-decisions register
`docs/arc42/09-architecture-decisions.md` lists ADRs only through 017; ADR-018 (orchestrator model lifecycle) is accepted, in the nav, and cited as evidence but missing from the register table. Add the 018 row in the same format as the others.

## 5. (S5) Reconcile the repo-visibility wording
`docs/index.md:5` states the repo is public (fact); `docs/criterion-map.md:16` says visibility "is enabled by the author at go-live" (future/conditional). The repo IS now public — update the criterion-map line to state it is public and anonymously accessible, so the two agree (criterion 10).

## 6. (H-3) Pin the floating CI security actions
`.github/workflows/ci.yml`: `aquasecurity/trivy-action@master` -> pin to a released tag or commit SHA; `anchore/sbom-action@v0` -> pin to a specific release. A security gate pinned to a moving ref is itself a supply-chain risk.

## 7. (optional, M-3) Widen the ingestion determinism guard
`services/ingestion/tests/test_determinism_boundary.py` AST-scans only 3 named files; the serving guard scans the whole package recursively with an allowlist. If in scope and safe, widen the ingestion test to mirror serving (no value-path code change — test only). Skip if it risks touching protected files.

## 8. Verify + rebuild + ship
- Diagrams: zero `—` in any embedded figure; UC-05 figure now reads "live".
- `python3 tools/cas_check.py` = **63/63**; `mkdocs build -f docs/mkdocs.yml --strict` exit 0; em-dash grep zero on PDF-bound docs.
- `python3 tools/build_pdf.py`; open the PDF and confirm the UC-05 diagram, the corrected dates, the ADR register, and all figures render; no German except proper nouns.
- `/ship`; auto-merge on the green-contract.

## Done means
The UC-05 contradiction, the diagram em-dashes, the future-date, the missing ADR-018 row, and the visibility wording are fixed and visible in the rebuilt PDF; CI actions pinned; `cas_check` 63/63; CI green; merged. Report each fix with its file and the rebuilt-PDF confirmation. Curate the journal entry.
