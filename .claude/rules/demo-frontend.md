---
paths:
  - "apps/**"
---

# TarifGuard Console rules (loaded only when touching apps/)

- **ADR-13 scope guards are law:** master-detail + review form + explain panel — exactly four components (list, detail, review form, explain). No auth, no patient data, no benchmarking. If a fifth concept appears, stop and flag it.
- The review form is the only write path, and it goes through the ingestion API's review endpoint — never the DB, never `freeze()` directly.
- **The original Convergence brand + its visual law are review-blocking** — tokens from `docs/brand/tokens.css`, reference `docs/brand/README.md`:
  - **Frozen/deterministic values: navy `#0C4A6E` + JetBrains Mono 600 tabular** (`.value-certified`), with version + truncated `record_hash` chips visible.
  - **Every AI output on a labelled surface** (`.ai-content` — "AI-generated — not a billing value"), slate regular weight. Never styled like a frozen value, never blended in one component.
  - Semantic states: success `#059669` · warning `#D97706` · error `#DC2626`.
- Brand tokens only (sky `#0EA5E9`, navy `#0C4A6E`, blue `#2563EB`, cyan, slate; Inter + JetBrains Mono via Tailwind config from the tokens file) — **no new colors, no new fonts**. Sky is a signal, not a text colour; white text only on navy/blue/ink-black.
- The logo (`docs/brand/assets/logo-primary.svg`) appears exactly once (header). Sub-products use the naming system + wayfinding accents per the guide — never their own marks.
- Component/smoke tests must assert the visual law: the AI panel renders its label; frozen values render in navy mono with provenance chips.
