# vault rules — what feeds which criterion (read once)

This folder is **not** Claude's memory (auto memory handles that). Everything here feeds rubric criteria directly:

| Item | Feeds | Rule |
|---|---|---|
| `daily/` — AI-workflow journal | "AI tools used + described" (**12 pts**) + the Fazit (6 pts) | One entry per working day, 3–6 honest lines, curated from the hook's draft. **Never backfilled.** |
| `decision-matrix.md` | Competency 1 + the 12-pt criterion | Vibe vs Spec-Driven vs Agentic, scored against this project's constraints, grounded in dated journal incidents. Draft in Block 2. |
| `fazit-notes.md` | The Fazit (**6 pts**) | Running raw notes: tool wins, tool failures, code-bloat observations, boundary lessons. The Fazit is written from these in Block 3 — not from hindsight. |

Journal entry shape (keep it this small):

```
# 2026-06-XX — AI workflow journal
- Delegated: pipeline E2E on EAL to main session; review to verifier
- AI got wrong → caught by: hash drift on Decimal('10.50') → pinned-hash test
- Prompt → diff example: "make ai_map live, designations only" → ai_map.py +84/-12
- Decision: review threshold stays 0.85 (→ no ADR, config)
```

↩ [[00-index]]
