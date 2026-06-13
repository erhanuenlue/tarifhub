# Fazit notes (raw, running)

> One dated line whenever a tool surprises you — good or bad. The Fazit (6 pts) gets written from these in Block 3.

- 2026-06-10: workspace rebuilt lean for Fable 5; hypothesis to test — fewer agents + outcome prompts beat the 10-agent zoo on review burden.

↩ [[00-index]]

## 2026-06-13
- Veto moment: I rejected parallel implementation worktrees for Block-05 and kept the tightly-coupled console contract and brand truth-up in the orchestrator.
- Correction: codex gpt-5.5 found the client-only billing-field guard that earlier AI reviews missed, and I accepted the finding by adding server-side `BILLING_FIELDS` rejection in `app/api/review/route.ts` (commit 0524f9a).
