# 08, AI-Assisted Software Engineering framework chapter (Block 3)

> **Gate-01: pre-approved by the owner (14 Jun).** Produce and log the plan (emit + plan report), then proceed without waiting. STOP only for: scope beyond this prompt, any freeze-line contact, a green-contract or ratchet breach, or a destructive operation.

Read AGENTS.md and CLAUDE.md. Run at `/effort ultracode`. This session turns the owner's framework write-up into the architecture documentation's method chapter, the account of how this project was engineered with AI. It is graded under criterion 15 (AI-tools chapter) and its closing feeds criterion 18 (Fazit transfer).

Source to integrate (owner-curated, authoritative for this chapter):
`tarifhub-fable5/02_CAS/AI_SE_Framework_Chapter.md` (in the strategy bundle beside this repo, path `../../02_CAS/AI_SE_Framework_Chapter.md` relative to the repo root, adjust if needed). It has these sections: project setup, prompt engineering, the /ship pipeline, loop engineering, autonomous quality gates, CI/CD, independent review, observability, documentation and diagrams as code (the Eraser MCP diagram-as-code generation), the human floor, plus a transfer-to-future-practice close. Ensure the integrated AI-tools chapter lists the COMPLETE external tool set used: Claude Code (orchestrator + workers), the OpenAI Codex CLI (independent gpt-5.5 reviewer + journal curation), and the Eraser MCP (autonomous diagram generation). Naming all three is part of the multi-tool evidence for criterion 15.

Do this:

1. **Integrate, do not duplicate.** Fold the framework write-up into the arc42 method documentation as a dedicated chapter "AI-Assisted Software Engineering: the framework", reconciling with the AI-tools chapter prompt 07 already produced. The result is one coherent chapter, not two overlapping ones: keep prompt 07's phase-structured evidence (Generierung, Review, Refactoring, Recherche) and worked examples, and weave in the framework's nine-section system view. No contradictions, no repetition.
2. **Evidence per claim.** Every mechanism named (the /ship phases, the green-contract, the fitness ratchet, the freeze-line guard, the loop, curate via gpt-5.5, the codex second family, the dashboard) must point to the real file or commit that implements it. Use the repo and the journal, not assertions.
3. **Keep the owner's voice in the graded slots.** The Eigenständigkeitserklärung stays his to author (prompt 07 reserved it). The framework prose may be AI-drafted; do not put words in his declaration.
4. **Placement.** Add the chapter to the arc42 docs so it appears on the GitHub Pages site and in the FFHS-LaTeX submission PDF. Cross-link it from the chapters it explains (the pipeline, the boundary).
5. **Reserve diagram slots.** Where a diagram will help (the four-layer architecture, the freeze line, the /ship pipeline, the loop, the quality gates, the CI/CD pipeline, the model+effort map), leave a clearly marked placeholder with a one-line caption and a stable anchor id, so prompt 09 can drop the rendered image in without restructuring. Do NOT create any diagrams here; prompt 09 owns that.
6. **Style law:** no em-dashes anywhere. Sweep this chapter; grep zero before finishing.
7. **Pre-flight:** mkdocs builds strict and clean; the chapter renders in the PDF; em-dash grep zero. Then `/ship` (codex-reviewer reads the chapter as an independent second family).

Constraints: documentation only, no product code. No freeze-line files. Conventional commit, branch `docs/ai-se-framework`, `/ship`; phase 09 auto-merges on the green-contract, else stops for the owner.

Done means: the framework chapter is merged, on the site and in the PDF, evidence-linked, em-dash-free, with diagram placeholders ready for prompt 09. Curate the journal entry.
