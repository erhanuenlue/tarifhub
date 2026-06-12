# 07 — Documentation, Fazit, submission package (Block 3)

Read AGENTS.md and CLAUDE.md. Final assembly: turn five weeks of evidence into the artifact the grade is read from. The PDF is the product of this session.

1. **AI-tools chapter** (criterion 15 — 12 points, the largest single criterion): describe the working system, concretely — `CLAUDE.md`/`AGENTS.md` as reproducible context sets; the four reviewers (verifier, determinism-auditor, security, Codex as independent second model); the three hooks with `guard_frozen` explained as *governance over the AI, by the AI's own tooling*; the skills (`/ship`, `/new-source`, `/cas-status`); the prompts/ library; Copilot/IDE mention per course tooling. Every claim anchored to a dated journal excerpt or a commit/PR link — at least six worked examples, including two failures and what caught them.
2. **The Fazit** (criterion 18): written from `vault/fazit-notes.md` + the journal, never from memory. Structure: what was delegated and how it went · measured observations (review burden, code-bloat incidents, where agentic beat spec-driven and the reverse) · the central lesson (an enforced, tested determinism boundary is what makes AI usable on billing data) · honest limits (where the AI wasted time, where human judgment was irreplaceable) · two references to course literature. 1.5–2 pages, first person, no triumphalism.
3. **German insurance:** a one-page **deutsche Zusammenfassung** (vision, architecture, AI usage, Fazit-Kernaussage) after the cover, and the Fazit's key paragraph in both languages.
4. **Site + PDF:** mkdocs build --strict clean; the criterion map (CAS Dossier §6 table, updated to final state) as an appendix — the grader's index; export the site to one PDF, **repo URL clickable on the cover**; journal excerpts appendix (representative, not exhaustive).
5. **Pre-flight** (CAS Dossier §8): run every item, report each with evidence, fix what fails. Repo reachable in incognito, gitleaks green, CI green on the submission commit, README cold-start credible.

Constraints: no code changes this session except what pre-flight forces. The Fazit's honesty is its value — a documented 20% review rate beats a hidden one; an AI failure analysed beats a success asserted.

Submission mechanics (confirmed on the Abgabe page, 12 Jun): assignment *"Projektarbeit: Deployment & Abgabe"*, submitted as **Gruppe K**, due **Mon 6 July 2026, 00:00** — PDF upload containing the clickable repo URL. The arc42 §8 page opens with the refreshed criterion-8 wording verbatim (*"Konzepte des gewählten Frameworks und moderner Applikationsentwicklung sachgerecht eingesetzt"* — stack-neutral since the 12 Jun rubric refresh); claim the 10 points directly, no hedging.

Done means: the PDF is uploaded to Moodle and renders; the repo is frozen on the submitted commit; `/cas-status` reports every floor item green. Then stop. Curate the final journal entry — and take the evening off.
