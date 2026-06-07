# TarifHub Architecture

TarifHub is an AI-assisted harmonization platform for Swiss ambulatory tariff data. It
ingests public tariff sources, harmonizes them through an AI-assisted, human-in-the-loop
pipeline, **freezes** each record as an immutable, versioned, hashed fact, and serves
those facts deterministically over adaptive APIs.

This site is the [arc42](https://arc42.org) architecture documentation, plus the
architecture decision records (ADRs).

## The one rule that shapes everything

> AI may assist **before** the freeze (and for search/discovery/explanation in serving),
> but **AI never computes or mutates a billing-relevant value**. Every authoritative
> value returned is an unaltered, frozen, versioned record served deterministically.

## Four sub-systems, one freeze line

| Sub-system | Stack | Side of the line |
|---|---|---|
| Ingestion | Python 3.12, FastAPI, Pydantic v2 | Pre-freeze (AI-assisted harmonization) |
| Serving | Java 21, Quarkus, Hibernate/Panache | Post-freeze (deterministic) + langchain4j search |
| MCP server | Python 3.12, FastMCP | Read-only tools over serving (downstream) |
| TarifGuard | Next.js, React, Tailwind | Practice-facing front end over serving (downstream) |

The MCP server and TarifGuard are read-only consumers: they relay frozen records and
never compute a value.

## Contents

- arc42 sections 1–12 (see the navigation).
- ADRs 001–005 (two-service split, AI-before-freeze, canonical model, Quarkus serving,
  TarifGuard merge + MCP).
- C4 diagrams in `diagrams/` (context + container).
