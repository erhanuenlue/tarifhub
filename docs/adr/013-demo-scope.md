# ADR-013: TarifGuard console demo scope: master-detail, review form, explain panel

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
L3 must demonstrate that the platform is usable at a real surface without becoming a product build-out. The CAS capstone is due 6 July 2026, and graders review code and documentation only: nothing is deployed or executed by them. The constraint that makes this a decision: every console feature competes directly with documentation and review time on a fixed deadline.

## Decision
We limit the TarifGuard console demo to three interactions: master-detail (search → frozen record detail), the review form for flagged records, and a clearly labelled AI explain panel. That is about four components, with no auth, no patient data, and no benchmarking. KassenFlow and MeldePilot stay stubs.

## Alternatives weighed
- **Full product console** (auth, dashboards, billing workflows): deadline risk for no extra grading value; graders assess concepts, not feature count.
- **No console at all**: loses the interaction-design evidence and the only visible demonstration of the read-only AI seam.

## Consequences
- (+) A scope a reviewer can hold in their head; the explain panel demonstrates the ADR-012 de-identification seam cleanly, with AI output explicitly labelled. The console renders frozen records verbatim, so the inviolable rule ("No AI computes or mutates a billing value at serve time.") is untouched by L3.
- (–) One piece is design scope at the MVP, not implemented: the review POST endpoint with its console review form. Reject scope creep in review; revisit only after the dossier hand-in. *(Update 2026-06-12: the serving `/api/v1/explain` endpoint is live as a deterministic, record-grounded endpoint, see [ADR-017](017-deterministic-search-fallback-explain.md); MCP `explain_crosswalk` now proxies it. The console's AI explain panel keeps its own labelled, de-identified seam unchanged.)*
- (±) The shipped console additionally carries a small **coding-check** page (`apps/tarifguard/app/coding-check/`), a demo extra beyond the three decided interactions; it reads frozen records only and adds no new seam. Acknowledged here so the decided scope and the shipped console match.

*Lineage: refines the console portion of [legacy ADR-005](legacy/005-tarifguard-merge-and-mcp.md); scopes the L3 layer of [legacy ADR-006](legacy/006-four-layer-product.md).*
