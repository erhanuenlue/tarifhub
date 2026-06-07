# ADR-004 — Quarkus for deterministic serving

- Status: Accepted
- Date: 2026-06

## Context

The serving path must be deterministic, strongly typed, fast to start, observable, and
comfortable with REST content negotiation and FHIR-grade interoperability on the JVM.

## Decision

Implement serving with **Quarkus 3.x (Java 21)**: Jakarta REST (quarkus-rest) with
Jackson + JAXB for JSON/XML content negotiation, Hibernate ORM with Panache over
PostgreSQL, `quarkus-langchain4j` (confined to the search package) for semantic search
over pgvector, SmallRye OpenAPI/Health, and Micrometer/OpenTelemetry for observability.

## Consequences

- Fast startup and low memory; optional native image for deployment.
- Strong typing and a read-only entity make the deterministic value path explicit.
- langchain4j stays isolated to one package, keeping the AI boundary enforceable.
- Adds a JVM toolchain alongside Python (accepted in ADR-001).
