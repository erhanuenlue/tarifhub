# ADR-020: Codex seat model lifecycle (gpt-5.5, then gpt-5.6-sol from 15 Jul 2026)

**Status:** accepted, switch executed · **Date:** 2026-07-15 · **Owner:** Erhan Ünlü

**Context.** The independent second-model-family seat (every PR review, the final document
review, journal curation, a second opinion on each grade estimate; owner decision 13 Jun)
ran on OpenAI gpt-5.5 via the owner's Codex Pro login. OpenAI released gpt-5.6-sol; the
owner upgraded the Codex CLI (0.144.4) on 15 Jul 2026 and reachability was verified in
session.

**Decision.** The Codex seat is gpt-5.6-sol from 15 Jul 2026 onward, following the same law
as the orchestrator seat (ADR-018): the strongest model available to the owner, never
downgraded to save tokens. `tools/curate.sh` deliberately passes no model flag and rides
the CLI default. Reference points updated: AGENTS.md, CLAUDE.md, the ship skill, the
codex-reviewer agent, tools/curate.sh.

**Consequences.** One-word updates at the reference points; the review contract (every PR,
reviewers launched in one parallel batch) is unchanged. CAS-era evidence citing gpt-5.5
stays as written: it is the contemporaneous record of what actually ran.
