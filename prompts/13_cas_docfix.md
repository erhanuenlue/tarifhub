# CAS doc fixes — correctness pass (run in a FRESH `claude` session at /effort ultracode)

> **Gate-01: pre-approved by the owner (14 Jun).** Produce and log the plan, then proceed without waiting. STOP only for: scope beyond this prompt, any freeze-line contact, a green-contract or ratchet breach, or a destructive operation.

This session fixes three correctness defects an independent review found in the CAS submission docs — each is a self-contradiction between the report and the actual repo, all cheap, all worth points (they clear the contradiction and raise criteria 8/13/14). **Documentation + app-config only. No product code, no freeze-line files, no `services/` edits.** No em-dashes (the chapters are PDF-bound). Conventional commits, branch `docs/cas-correctness-fixes`, then `/ship`; phase-09 auto-merges on the green-contract.

Read AGENTS.md and CLAUDE.md first. **Verify every claim against the ACTUAL repo before editing — do not overclaim.**

## 1. Fix the console-test contradiction (most important)
Three PDF-bound chapters still narrate the old "no `test` script / `npm run test --if-present` is a no-op" state, but `apps/tarifguard/package.json` now defines a real `test` script (`vitest run && playwright test`, plus `test:unit`/`test:e2e`) and `.github/workflows/ci.yml` runs it (Chromium installed). Update the prose in:
- `docs/arc42/13-test-strategy.md` (~line 197)
- `docs/arc42/05-building-block-view.md` (~line 69)
- `docs/arc42/11-risks-technical-debt.md` (~line 10)
to state the console tests are now wired and run in CI. **Quote the ACTUAL current result** — run the suite (or read the latest CI run) and cite the real numbers. If everything passes, say so with the count; if anything is skipped or failing, state it honestly. Do not claim a green you have not verified. This removes the report-vs-repo self-contradiction and strengthens criteria 8, 13, 14.

## 2. Remove the phantom `fhir_parser.py`
`docs/arc42/05-building-block-view.md` (~line 39) and `docs/arc42/06-runtime-view.md` (~line 13) reference a `parsers/fhir_parser.py` that does not exist — the real parser inventory under `services/ingestion/src/.../parsers/` is `xlsx_parser.py` only (the ePL/FHIR path is handled elsewhere). Reconcile both references to the actual code: name the real module that handles FHIR/ePL ingestion, or drop the phantom path. Verify against the real file tree before writing.

## 3. Fix the Quarkus / `:8080` references
All three app `.env.example` files — `apps/tarifguard/.env.example`, `apps/kassenflow/.env.example`, `apps/meldepilot/.env.example` — reference a "Quarkus serving service", `mvn quarkus:dev`, and port `:8080`, contradicting the no-JVM constraint (`docs/arc42/02-constraints.md`). The real serving image is Python/FastAPI on `:8000`. Correct the variable comments and values accordingly (`http://localhost:8000`, FastAPI, no Maven/Quarkus).

## 4. Reconcile ADR-013
`docs/adr/013-*.md` and the "console test wiring is planned (ADR-013)" language in `docs/arc42/05` state the wiring is deferred — but the script shipped. Update ADR-013 (or drop the "planned" language) so it reflects that the console test script now exists and runs in CI.

## 5. Pre-flight, rebuild, verify
- `mkdocs build -f docs/mkdocs.yml --strict` exit 0; em-dash grep zero across all PDF-bound docs; no broken internal links in the edited chapters.
- `python3 tools/cas_check.py` still **63/63** (these fixes must not decrease the floor; criteria 8/13/14 hold or improve).
- Rebuild the submission PDF: `python3 tools/build_pdf.py`; confirm the three edited chapters render correctly (the builder silently drops missing images, so eyeball them).
- Then `/ship` (codex-reviewer reads the diff as the independent second family). Auto-merge on the green-contract.

## Done means
The three contradictions are gone, the docs match the actual repo, the PDF is rebuilt and em-dash-free, `cas_check` 63/63, CI green, merged. Report the exact prose changes and the verified test result you cited. Curate the journal entry.
