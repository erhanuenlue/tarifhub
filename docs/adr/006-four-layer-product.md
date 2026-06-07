# ADR-006 — One platform, four layers (TarifIQ + the app suite)

- Status: Accepted
- Date: 2026-06

## Context

The platform started as ingestion (L0) + serving (L1), then gained two read-only
consumers (TarifMCP, TarifGuard — see ADR-005). Two gaps remained. First, the deterministic
*facts* (frozen tariff records) are not the same as the deterministic *reasoning* a
practice needs: whether two positions are combinable, how a TARMED code maps to TARDOC,
whether a proposed rule is even well-formed. Second, the product story is broader than one
front end: payer correspondence (Kostengutsprache) and mandatory reporting (BFS/MARS, ANQ,
interRAI/BESA) are distinct app surfaces with their own users. We want a single, coherent
way to name and place these without weakening the freeze-line guarantee.

## Decision

Frame TarifHub as **one platform, four layers**, each with a product/brand name:

- **L0 — Harmonization Engine** (`services/ingestion`): pre-freeze, AI-assisted pipeline →
  freeze + version + hash + lineage → canonical store.
- **L1 — TarifCore API** (`services/serving`) + **TarifMCP** (`services/mcp`): deterministic
  read API over frozen records + semantic search; read-only MCP tools for AI agents.
- **L2 — TarifIQ** (`services/intelligence`, new): deterministic combinability/cumulation
  rules, the **TARMED↔TARDOC cross-walk**, and rule validation, layered on top of the
  frozen tariff facts. A FastAPI service with `POST /v1/combinability-check`,
  `GET /v1/crosswalk/{tarmed_code}`, and `POST /v1/validate`.
- **L3 — Apps** (`apps/`): **TarifGuard** (practice-facing), plus **KassenFlow** (payer
  correspondence / Kostengutsprache) and **MeldePilot** (mandatory reporting / quality
  data) as new Next.js stubs that ship their planned scope.

TarifIQ's frozen rule and cross-walk tables are versioned and SHA-256 content-hashed, the
same discipline L1 applies to tariff records.

## Determinism boundary (unchanged, extended to L2)

Rule **evaluation is deterministic**: every L2 endpoint is a pure function of the request
and the frozen rule/cross-walk tables, and rules carry **no billing value** — they describe
relationships between codes, never prices. AI may only **suggest** a candidate rule or
cross-walk entry *before* it is frozen, through a single, clearly marked, replaceable seam
(`crosswalk.tarmed_tardoc.ai_rule_suggest`) that a human validates (`POST /v1/validate`)
before freezing. That seam is not wired into any endpoint and imports no model; an AST
boundary test asserts the L2 value path imports no LLM client. The L3 apps remain read-only
over L1 + L2 and confine any LLM-bound payload to their `lib/deident.ts` (AGENTS.md rule 7).

## Consequences

- The freeze line still holds: L2 adds deterministic *reasoning* and L3 adds *surfaces*,
  but nothing downstream of the line computes or mutates a billing value.
- TarifIQ is independently buildable, testable offline (bundled frozen tables + an offline
  frozen-store stub), and deployable (its own image, Service, and ingress host).
- The Helm chart, CI, and docker-compose now cover seven sub-systems; KassenFlow and
  MeldePilot are disabled by default (`*.enabled: false`) while they are stubs.
- A clear brand-name → sub-system map (in `README.md` and arc42 §5) keeps the product
  story and the repo layout in sync.
