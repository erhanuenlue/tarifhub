# 05 — TarifGuard Console (Block 2)

> **Gate-01: pre-approved by the owner (13 Jun).** Produce and log the plan as usual (emit + plan report), then proceed without waiting for approval. STOP and ask only for: scope beyond this prompt, any freeze-line contact, a green-contract or ratchet breach, or a destructive operation.

Read AGENTS.md, CLAUDE.md and `.claude/rules/demo-frontend.md`, then plan before coding.

Goal: the console at `apps/tarifguard-demo` — the course Frontend block's shape (master-detail + form) carrying the product's trust story. Graders read code and screenshots; nobody will run this. Build accordingly: clean code and captured evidence over runtime polish.

Scope, exactly four components:

1. **Master list:** search box (semantic + code search via TarifCore `/search` and `/tariffs`) → result list showing code, designation (DE), system, current value, version badge.
2. **Detail panel:** the frozen record — value as `.value-certified` (navy + JetBrains Mono 600, tabular) with truncated `record_hash` + version chips, validity window, source provenance link, cross-walk hint where present. The visual law (frozen = navy mono; AI = slate, labelled) is review-blocking — see `docs/brand/README.md`.
3. **Review form** (the human-in-the-loop made operable): list records where `requires_review` → show raw extract vs `ai_map` proposal side by side with confidence → approve / correct (field-level) → submits to the ingestion review endpoint → freeze happens server-side. This is the one write path, and it goes through the API, never the DB.
4. **Explain panel:** an `.ai-content` surface (the built-in "AI-generated — not a billing value" label), backend explain seam only (server route; input = tariff code only), slate styling.

Constraints (ADR-13, law): no auth, no patient data, no benchmarking, no state library — server components + fetch; Tailwind configured **from `docs/brand/tokens.css`** (sky/navy/blue/cyan/slate, Inter + JetBrains Mono), no other colors or fonts. The review form's approve action is where a proposal becomes a frozen record — make that transition visible; it is the product story in UI form. If a fifth component appears, stop and flag.

Done means: `npm run lint && npm test` green (component tests + one Playwright smoke: search → detail renders → review form submits against a mocked API → labels present); **screenshot set captured into `docs/img/console/`** (master-detail, review form, explain panel, provenance detail) and embedded in the arc42 frontend section with two paragraphs of prose. Verifier on the diff; `/ship`; journal: where AI-generated UI needed human taste corrections — name them.
