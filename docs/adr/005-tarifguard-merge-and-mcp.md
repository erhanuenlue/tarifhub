# ADR-005 — Merge TarifGuard, add an MCP server, and fix the de-identification boundary

- Status: Accepted
- Date: 2026-06

## Context

The platform (ingestion + serving) is backend-heavy. A practice-facing front end makes
the frozen data useful at the point of care and adds a second, visible AI surface
(search / coding-check / explain), while the wider ecosystem is converging on the Model
Context Protocol as the way AI agents consume tools. Two questions follow: how should a
practice-facing app and an agent-facing interface attach to TarifHub without weakening
the freeze-line guarantee?

## Decision

Add two **read-only consumers** downstream of the deterministic serving service, in the
same monorepo, each independently containerized:

- **TarifGuard** (`apps/tarifguard`, Next.js App Router): a thin practice-facing front
  end with three screens — semantic search, coding-check (combinability/validation), and
  a natural-language explain / TARMED↔TARDOC cross-walk. It composes existing serving
  endpoints and renders frozen records verbatim.
- **MCP server** (`services/mcp`, FastMCP): three read-only tools — `search_tariffs`,
  `get_tariff`, `explain_crosswalk` — each a thin proxy to serving, returning frozen
  records verbatim.

Both consume the serving API only; neither owns a database, billing logic, or model.

**De-identification boundary.** Any LLM use is on de-identified data and confined to one
marked module per side: `apps/tarifguard/lib/deident.ts` (front end) and the ingestion
mapper's `ai_map()` (pipeline). Patient identifiers never leave Swiss infrastructure;
only de-identified coding context is sent to an LLM, routed via AWS Bedrock EU or Google
Vertex AI EU. TarifGuard performs de-identification server-side (route handlers under
`app/api/*`), so `SERVING_BASE_URL` and raw input never reach the browser. This is
codified as `AGENTS.md` rule 7.

## Consequences

- The freeze line still holds: the new sub-systems are read-only and compute no value,
  so the determinism guarantee is unchanged.
- The merged repo exercises front end, services, persistence, deployment, and AI surfaces
  together, while keeping each sub-system independently buildable and deployable.
- TarifGuard is exposed on its own ingress host so its same-origin `/api/*` route handlers
  do not collide with the serving `/api` path.
- `coding-check` and `explain` lean on deterministic serving endpoints
  (`/api/v1/coding-check`, `/api/v1/explain`); where a build predates them, the app
  degrades to per-position `GET /api/v1/tariffs/{system}/{code}` lookups — never to a
  value computed in the app.
- One more language toolchain (Node/Next.js) joins Python and the JVM.
