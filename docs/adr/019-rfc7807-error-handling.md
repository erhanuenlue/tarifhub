# ADR-019: Centralised RFC 7807 error handling in the serving API

*Status: Accepted · Date: 2026-06-19 · Decider: Erhan (+ AI-assisted analysis)*

## Context
The serving API raised `HTTPException` inline at roughly eight sites and had no application-level exception handler. An unexpected repository or driver error therefore surfaced as a bare, unstructured HTTP 500, and the error envelope was defined route by route rather than once. For a read API that is part of the graded deliverable, error responses are part of the contract and need one predictable, documented shape (crosscutting concept "error handling", arc42 §8).

## Decision
We centralise error handling in `tarifhub_serving/errors.py`: a small domain-exception vocabulary (`TariffNotFound` to 404, `SearchBackendUnavailable` to 501) plus four handlers registered on the FastAPI app that render every failure as an RFC 7807 `application/problem+json` document (`type`, `title`, `status`, `detail`, `instance`), with a catch-all on `Exception` that turns any unexpected error into a structured 500 carrying a correlation id and no leaked internals.

## Alternatives weighed
- **Keep inline `HTTPException` per route**: no central place for the status mapping, and the catch-all 500 stays bare and unstructured.
- **A bespoke custom JSON error shape (not RFC 7807)**: works, but problem+json is the documented IETF standard for HTTP problem details, recognised by tooling and reviewers without bespoke explanation.

## Consequences
- (+) One consistent, standard error envelope across every route; an unexpected error is now a structured 500 whose correlation id ties the caller's report to a server-side log line.
- (+) The status-to-condition mapping lives in one module and routes read more clearly (`raise TariffNotFound(...)`); the `detail` strings stay the existing per-route messages, so the change is contract-preserving.
- (–) The handler layer is serving-only for now; if the MCP service grows its own failure modes we would revisit sharing the envelope. The errors module imports no LLM client, so the serving determinism boundary (`test_serving_boundary.py`) is unaffected.
