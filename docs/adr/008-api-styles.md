# ADR-008: API styles: REST primary, FHIR R4 and MCP built; GraphQL and XML designed

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
Integrators differ: software vendors want REST/OpenAPI or flexible queries, healthcare interop expects FHIR, the incumbents publish fixed XML, and AI agents consume tools over MCP. The incumbents' one-format distribution is exactly the gap tarifhub targets: breadth of API style is product, not polish.

## Decision
We serve frozen records over REST (primary, OpenAPI), a FHIR R4 adapter (ChargeItemDefinition/CodeSystem, bridging BAG's FHIR R5 source), and MCP (FastMCP, read-only tools): the three built facades, all thin layers over one shared, read-only service layer. GraphQL (Strawberry) and XML for incumbent parity are designed, not built: forward-looking facades over the same layer, scheduled for after the CAS deliverable freezes (see Consequences).

## Alternatives weighed
- **REST only**: simplest, but cedes FHIR-expecting healthcare integrations and AI-agent distribution, the two channels the incumbents don't serve.
- **GraphQL as primary**: flexible, but a poor fit for the dominant "give me this frozen record" lookup; caching and contract guarantees are weaker than OpenAPI for billing data.
- **A second protocol stack (SOAP/custom RPC) for incumbent parity**: XML representations on the existing routes achieve parity without another stack.

## Consequences
- (+) Broad reach plus AI-native distribution. Every style serves the same frozen records through one shared read-only layer, so the rule **"No AI computes or mutates a billing value at serve time"** holds across all facades; contract tests guard the shared layer.
- (-) More surface to maintain: accepted, mitigated by the single service layer underneath.
- (-) Honest status (2026-06-12): live are REST (`/api/v1/tariffs` with `?as_of=`, `/api/v1/tariffs/{system}/{code}` with `?as_of=`, `/api/v1/tariffs/{system}/{code}/diff`, `/api/v1/search`, `/api/v1/explain`), the FHIR R4 read adapter (`/api/v1/fhir/ChargeItemDefinition/{system}/{code}`, `/api/v1/fhir/CodeSystem/{system}`) and MCP (`search_tariffs`, `get_tariff`, `explain_crosswalk`, all three proxy live endpoints). Search ranks offline on SQLite via a deterministic in-process cosine fallback ([ADR-017](017-deterministic-search-fallback-explain.md)). GraphQL, XML and webhooks remain designed, not built: revisit scope after the CAS deliverable freezes.

*Lineage: extends legacy/005's MCP decision.*
