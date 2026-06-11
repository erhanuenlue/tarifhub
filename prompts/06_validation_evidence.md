# 06 — Validation & distribution evidence (Block 2)

Read AGENTS.md and CLAUDE.md. This session produces the artifacts criteria 13, 14 and 17 score — the points teams routinely leave on the table. Almost no new features; maximum legibility.

1. **Coverage to target:** fill unit-test gaps on core modules (model, freeze, pipeline, mapper, serving routes) to >80% line coverage. No test theater — each new test asserts behaviour, not implementation.
2. **Test-results artifact** (`docs/arc42/10-quality-requirements.md`, "Results" section): the CI run link + a screenshot of the green run with the determinism boundary test visible in the log; the coverage figure (tool output, not prose); the harmonisation report table (both sources: in/out, review rate); one diff-query output example; the NFR table from §13 of the architecture doc with a "measured" column filled where measurable offline (hash idempotency, boundary test, coverage) and "captured at compose-up" for latency.
3. **Distribution evidence** (criterion 17, code-only review): verify every sub-system image builds in CI (`docker build` matrix); capture one `docker compose up` + `docker ps` screenshot showing the independent containers; optionally one local k3d `helm install` + `kubectl get pods` screenshot. Embed both in the deployment chapter with the Helm chart structure explained in six lines.
4. **Decision matrix** (`vault/decision-matrix.md` → also into the docs AI chapter): fill the skeleton — Vibe vs Spec-Driven vs Agentic against this project's constraints, each cell grounded in a dated journal incident or a course-literature reference ([1] Osmani, [9] O'Reilly). Conclusion argued, not asserted.

Constraints: nothing below the freeze line; no new endpoints; the screenshots go into the repo (`docs/img/`) so the site and PDF are self-contained.

Done means: a grader can verify criteria 13/14/17 without leaving the PDF. Verifier pass framed as that grader. `/ship`; journal curated.
