# ADR-008 — API styles: REST primary, plus GraphQL, FHIR R4, XML and MCP

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
Integrators differ: software vendors want REST/OpenAPI or flexible queries, healthcare interop expects FHIR, the incumbents publish fixed XML, and AI agents consume tools over MCP. The incumbents' one-format distribution is exactly the gap TarifHub targets — breadth of API style is product, not polish.

## Decision
We serve frozen records over REST (primary, OpenAPI) and add GraphQL (Strawberry), a FHIR R4 adapter (ChargeItemDefinition/CodeSystem, bridging BAG's FHIR R5 source), XML for incumbent parity, and MCP (FastMCP, read-only tools) — all thin facades over one shared, read-only service layer.

## Alternatives weighed
- **REST only** — simplest, but cedes FHIR-expecting healthcare integrations and AI-agent distribution, the two channels the incumbents don't serve.
- **GraphQL as primary** — flexible, but a poor fit for the dominant "give me this frozen record" lookup; caching and contract guarantees are weaker than OpenAPI for billing data.
- **A second protocol stack (SOAP/custom RPC) for incumbent parity** — XML representations on the existing routes achieve parity without another stack.

## Consequences
- (+) Broad reach plus AI-native distribution. Every style serves the same frozen records through one shared read-only layer, so the rule **"No AI computes or mutates a billing value at serve time"** holds across all facades; contract tests guard the shared layer.
- (–) More surface to maintain — accepted, mitigated by the single service layer underneath.
- (–) Honest status (2026-06-11): live today are REST (`/api/v1/tariffs`, `/api/v1/tariffs/{system}/{code}`, `/api/v1/search`) and MCP (`search_tariffs`, `get_tariff`; `explain_crosswalk` currently errors with 404 — the serving endpoint it proxies does not exist yet). GraphQL, FHIR R4, XML, point-in-time/diff queries and webhooks are designed, not yet built — revisit scope after the CAS deliverable freezes.

*Lineage: extends legacy/005's MCP decision.*
