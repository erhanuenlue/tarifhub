# ADR-010: GitHub Actions CI/CD with DevSecOps gates

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
The codebase is solo-owned and largely AI-produced, so quality and supply-chain assurance cannot rest on human discipline: every gate must be automated and visible in logs a grader can read. Above all, the inviolable rule ("No AI computes or mutates a billing value at serve time.") needs machine enforcement on every push, not a code-review convention.

## Decision
We use GitHub Actions as the single CI/CD pipeline: per-service ruff + pytest (offline suite) with the determinism-boundary tests (`test_determinism_boundary.py`, `test_serving_boundary.py`) as a named, visible step, then the DevSecOps gates (gitleaks for secrets, Trivy filesystem scan failing on HIGH/CRITICAL, Syft SBOM uploaded per run), then, on `main`, sub-system image builds pushed to GHCR followed by a gated Helm deploy.

## Alternatives weighed
- **Manual gates (review-only)**: does not scale to AI-volume diffs and leaves no supply-chain evidence; a human forgetting a scan is exactly the failure mode to design out.
- **Other CI (GitLab CI, Jenkins)**: the repo, reviews and container registry already live on GitHub; a self-hosted Jenkins is operational weight a solo operator should not carry.

## Consequences
- (+) Every push re-proves the freeze line: the AST boundary test fails CI if an LLM client becomes importable on the value path.
- (+) Secrets gate, dependency scan and an SBOM per run: supply-chain evidence readable directly in `ci.yml` and the workflow logs.
- (–) Trivy failing on HIGH/CRITICAL can block unrelated PRs when new CVEs publish; accepted, since the right response is to triage the finding rather than lower the bar.
- (–) The pipeline tail is decided but not fully wired: today `ci.yml` builds all sub-system images on `main` but does not yet push to GHCR, and the gated Helm deploy job does not exist yet. Wire both before the first tagged release.

*Lineage: new, no legacy counterpart (formalises the existing `ci.yml`).*
