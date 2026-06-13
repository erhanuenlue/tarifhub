# ADR-018: Orchestrator model lifecycle (Fable 5 until 22 Jun 2026, then Opus 4.8)

**Status:** accepted, switch executed · **Date:** 2026-06-13 · **Owner:** Erhan Ünlü

**Context.** The pipeline orchestrator (planning, orchestration, merge-gate review, complex
senior-level decisions) ran on Claude Fable 5 through the early blocks. The owner's Fable 5
access ended on 22 Jun 2026; continued use would have been API-billed at roughly twice Opus
prices. All worker and review seats run Opus 4.8 (or inherit the orchestrator); journal
curation and the independent second-family review run on OpenAI gpt-5.5 via the owner's Codex
Pro login.

**Decision.** Through the early blocks the orchestrator was Claude Fable 5. From the model
switch onward the orchestrator is Claude Opus 4.8, then the strongest model available to the
owner, which keeps the quality-before-cost law satisfied. The orchestrator model is pinned in
exactly one place, the "model" key of `.claude/settings.json`; interactive sessions and
`tools/loop.sh` both read it. The switch is executed with `bash tools/switch_model.sh opus`
(rollback if access returns: `fable`). Worker seats stay pinned to Opus 4.8 and are not
affected. Sonnet and Haiku remain excluded from every seat. The Fable command
`/effort ultracode` is retired with the switch; the loop's standing maximum-effort
instruction (ultrathink) covers the Opus orchestrator.

**Consequences.** One pin point, a one-command switch, zero behavioral change elsewhere in
the pipeline (gates, green-contract, hooks, board and CI are model-agnostic). The model
lifecycle itself is documented evidence of operating an AI-assisted engineering process
across a model transition: Fable 5 for the early blocks, Opus 4.8 from the switch onward.
