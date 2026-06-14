# CAS C5 — add an explicit interface-contract (interaction) view (run AFTER the fully-English conversion, in a FRESH `claude` session at /effort ultracode)

> **Gate-01: pre-approved by the owner (14 Jun).** Produce and log the plan, then proceed. STOP only for: scope beyond this prompt, freeze-line contact, a green-contract/ratchet breach, a destructive op, or **the Eraser MCP being unreachable** (see step 4 fallback).

This session acts on the independent reviewer's (gpt-5.5) criterion-5 finding: the **interaction perspective** should be carried by an **explicit interface/OpenAPI contract view**, not by the use-case diagram. We add that view. The criterion-5 floor anchors are already met; this strengthens the *judgment* quality where a strict grader could otherwise dock. Documentation only — no product code, no freeze-line files, no edits to `tools/cas_check.py`/`tools/cas_baseline.json`, no em-dashes, English prose. Branch `docs/c5-interface-view`, then `/ship`; auto-merge on the green-contract.

Source the Eraser token first (the diagram render needs it): `set -a; source .env; set +a`.

Read first: `docs/arc42/05-building-block-view.md`, `docs/arc42/06-runtime-view.md`, `docs/arc42/03-context-scope.md` (the existing interface table ~line 22), `docs/criterion-map.md` (C5 row), the serving OpenAPI surface (`services/serving/src/.../main.py` routes + `services/serving/tests/test_openapi.py`), and `prompts/09_diagrams.md` (for the Eraser-only diagram convention).

## 1. Add the interface-contract view to the interaction perspective
In the architecture docs (the interaction perspective — `arc42/05` §5 component/interaction or `arc42/06` runtime, wherever it reads most coherently), add an explicit **interface-contract view**:
- A short structured section presenting the **L1 serving surface as a contract**: the REST endpoints (`/api/v1/tariffs`, `/.../{system}/{code}`, `/.../diff`, `/explain`, `/search`), the **FHIR R4** resources (`ChargeItemDefinition`, `CodeSystem`), and the **MCP** read-only tools (`search_tariffs`, `get_tariff`, `explain_crosswalk`) — each with its request/response contract in one line, and the **point-in-time (`as_of`) + versioning + diff** semantics as part of the contract.
- Point to the **machine-readable contract**: the generated OpenAPI spec and `services/serving/tests/test_openapi.py` (the contract is tested, not asserted).
- Make the determinism guarantee explicit at the interface level: the contract never returns a recomputed value; a served value is the frozen, hashed record.

## 2. Render the interface diagram with Eraser (Eraser only, no Mermaid)
Render **one** interface/interaction diagram via the Eraser MCP and commit it under `docs/img/diagrams/` (SVG + PNG, same convention as prompt 09): either an **interface diagram** (the serving component with its REST/FHIR/MCP interface ports and the consumers) or a **representative sequence** (consumer → serving API → frozen-record read → response, showing the contract and the `as_of`/diff path). Embed it in the new section with a 1-2 sentence caption. If both add value, prefer the sequence (it shows the contract in motion); keep it to one diagram.

## 3. Repoint criterion-map C5
Update the `docs/criterion-map.md` C5 (Perspektiven) row so the **interaction** perspective points to this explicit interface-contract view + the OpenAPI evidence, rather than the use-case diagram. Keep the structure and behaviour perspective references intact.

## 4. Eraser fallback (owner law)
If the Eraser MCP is unreachable or a render fails: **STOP and report which diagram failed. Do NOT substitute Mermaid or ASCII.** Rerun when Eraser is back.

## 5. Verify + rebuild + ship
- `python3 tools/cas_check.py` = **63/63** (the C5 anchors — component/sequence/state SVGs + "OpenAPI" in corpus — must stay satisfied; you are adding, not removing). `mkdocs build -f docs/mkdocs.yml --strict` exit 0. Em-dash grep zero on PDF-bound docs.
- Rebuild: `python3 tools/build_pdf.py`; confirm the new interface view + diagram render in the PDF.
- `/ship`; auto-merge on the green-contract.

## Done means
The interaction perspective now carries an explicit, tested interface-contract view with one rendered Eraser diagram; the criterion-map C5 row points to it; `cas_check` 63/63; CI green; merged; PDF rebuilt. Report the new section location, the diagram path, and the C5 map change. Curate the journal entry.
