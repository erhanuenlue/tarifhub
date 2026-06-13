# 09, Architecture diagrams via Eraser (Block 3)

> **Gate-01: pre-approved by the owner (14 Jun).** Produce and log the plan (emit + plan report), then proceed without waiting. STOP only for: scope beyond this prompt, any freeze-line contact, a green-contract or ratchet breach, a destructive operation, or if the Eraser MCP is unavailable (see fallback).

Read AGENTS.md and CLAUDE.md. Run at `/effort ultracode`. This session adds the diagrams the architecture documentation needs, rendered with Eraser, committed as files, and embedded with captions. Diagrams are graded under criterion 4 ("Architektur in Bild und Text"), 5 (perspectives), 7 (code structure). Run prompt 08 first; this fills the placeholders it left.

**Tooling, owner decision (14 Jun): Eraser only, no Mermaid anywhere.** The Eraser MCP is installed and logged in (`@eraserlabs/eraser-mcp`, OAuth). Use the official **`eraser-diagrams`** skill (installed at `~/.agents/skills/eraser-diagrams`; canonical source github.com/eraserlabs/eraser-io/skills) and read it first. Its mechanism: you generate **Eraser diagram-as-code syntax**, then render it via the MCP (`/render/elements`); Eraser's freeform engine honours described layouts, so write precise specs. Prefer the skill's documented flow over raw API calls.

Hard rule, self-contained submission: the graders read static files and run nothing. So every diagram is **rendered to a committed file** under `docs/img/diagrams/<name>.svg` (SVG preferred; also export `.png` for the PDF if the LaTeX path needs raster), and embedded in the docs. The repo and the PDF never call Eraser at view time. Do NOT introduce Mermaid or any other diagram format.

## Diagrams to produce (each: render → commit SVG/PNG → embed with a 1 to 2 sentence caption)

Architecture (arc42):
1. Four-layer architecture (L0 harmonisation, L1 serving + MCP, L2 rules, L3 apps) with the freeze line drawn across it. → §3/§5.
2. The freeze line / determinism boundary: what AI may touch (pre-freeze ai_map, search, explain) vs the immutable value path. → §8.
3. Data flow: source adapter → parse → map_raw → ai_map → validate → score → review → freeze → serve. → §6.
4. Deployment view: containers, Postgres+pgvector, MCP, console, CI to GHCR, Pages. → §7.
5. Console master-detail + review write-path (proposal → frozen). → §5 L3.

AI-SE framework chapter (from prompt 08):
6. The /ship 9-phase pipeline with orchestrator and worker seats per phase.
7. Loop engineering: fixed loop vs self-prompting auto-loop, the completion-contract gate, halt-to-human.
8. Autonomous quality gates: fitness ratchet, freeze-line guard hook, green-contract, secret gate, and where each blocks.
9. CI/CD pipeline: push → PR → parallel jobs (lint, test, gitleaks, Trivy, ratchet) → merge → images/Pages.
10. Model + effort map: who runs what, at which effort, plus the gpt-5.5 second family.

Trim or merge only if a diagram would not add clarity; note any cut in the report.

## Steps

1. Read the Eraser skill. For each diagram, write the layout spec, generate and render via the Eraser MCP, save `docs/img/diagrams/<name>.svg` (+ `.png` where needed). Keep the source/spec for each in `docs/img/diagrams/<name>.eraser` or as the doc-embedded source the skill recommends, so a diagram can be regenerated.
2. Embed each into the correct doc section (filling prompt 08's placeholders) with a concrete caption that carries the "Text" half of "Bild und Text".
3. Rebuild the docs site (mkdocs strict) and the FFHS-LaTeX submission PDF so every diagram appears in both. Confirm each referenced image exists and renders.
4. **Fallback, owner law: if the Eraser MCP is unavailable or a render fails, STOP and report which diagram failed. Do NOT substitute Mermaid or ASCII.** Partial success is fine: commit what rendered, report what did not.
5. Style law: no em-dashes in any caption or doc text; grep zero.
6. Pre-flight: every diagram file present and embedded; site builds strict; PDF embeds them; em-dash grep zero. Then `/ship` (codex-reviewer reviews the doc + diagrams).

Constraints: documentation/assets only, no product code, no freeze-line files. Conventional commit, branch `docs/diagrams`, `/ship`; phase 09 auto-merges on the green-contract, else stops for the owner. Optionally add one fitness element to `tools/cas_check.py` asserting the expected diagram files exist and are embedded, so the ratchet protects them (only if it does not disturb the existing floor).

Done means: the diagrams are merged, rendered as committed SVG/PNG under `docs/img/diagrams/`, embedded with captions across the architecture and framework chapters, present on the site and in the PDF, em-dash-free, Eraser-only. Curate the journal entry.
