# Crosscutting Concepts

> **Concepts of the chosen framework and of modern application development, applied appropriately: for example dependency injection, REST interfaces, configuration, and error handling.**

This chapter is the scope of that statement. All four named concepts are implemented in this repository: dependency injection via FastAPI's `Depends` graph (`services/serving/src/tarifhub_serving/main.py`), REST interfaces with a generated OpenAPI document (the `/api/v1` routes, each with a declared `response_model`), env-only configuration injection (`tarifhub_ingest/config.py`, `tarifhub_serving/config.py`), and centralised error handling (one RFC 7807 `application/problem+json` handler layer, applied uniformly across the serving, ingestion and intelligence services and the TarifGuard BFF: declarative 422s, mapped domain errors, and a catch-all that turns any unexpected error into a structured 500 with a correlation id). Each is detailed in the [Modern application concepts](#modern-application-concepts) catalogue below.

The concept that cuts across every layer is the determinism boundary:

> **No AI computes or mutates a billing value at serve time.**

![The freeze line and its enforcement](../img/diagrams/freeze-line-boundary.png)

> **Figure: The determinism boundary.** Above the freeze line, the pre-freeze ai_map seam and the read-only search and explain seams. Below it, the immutable hashed records and the deterministic serving path. The pre-tool guard hook and the AST boundary tests are the two enforcement points.

It is enforced structurally, not by convention: AST boundary tests (`services/ingestion/tests/test_determinism_boundary.py`, `services/serving/tests/test_serving_boundary.py`) fail CI if an LLM client becomes importable on the value path, and a write-guard hook (`.claude/hooks/guard_frozen.sh`) protects `versioning/`, `audit/` and applied migrations. Everything below assumes this boundary. The full set of autonomous quality gates that lets AI assistance run with full autonomy above this line while never crossing it (the freeze-line guard, the fitness ratchet and the merge green-contract) is described in [the AI-SE framework chapter](../method/ai-se-framework.md).

## Modern application concepts

The enterprise application concepts taught in the Modulplan, each as implemented in this repository.

### Dependency injection

FastAPI's `Depends` graph wires the serving service: `get_repository` in `services/serving/src/tarifhub_serving/main.py` yields a read-only `ServingRepository` for the request and releases its connection on completion, a per-request lifecycle managed by the framework. On Postgres the connection is borrowed from a shared `psycopg_pool.ConnectionPool` (warmed once in the app `lifespan`, sized from `Settings`) and returned to the pool when the request ends, so the read path reuses connections instead of opening a fresh one each time. On the offline SQLite mirror there is no pool: a cheap file-local connection is opened and closed per request. The `Annotated` aliases `RepoDep` and `SettingsDep` make injected dependencies explicit in every route signature. The ingestion service makes the matching choice in its own `create_app` lifespan, holding one connection for the app's lifetime rather than per request.

### Declarative validation

Pydantic v2 models are the contract. The canonical `TariffRecord` (`services/ingestion/src/tarifhub_ingest/models/tariff_model.py`) declares `ConfigDict(extra="forbid", validate_assignment=True)` plus field constraints (`tax_points`/`price_chf` ≥ 0 as `Decimal`, `harmonization_confidence` bounded 0 to 1). Query parameters are validated declaratively too (`Query(ge=1, le=MAX_LIST_LIMIT)` in `main.py`). Validation happens at system boundaries only: inside the pipeline, data is already parsed, never re-checked by hand. The TarifGuard BFF applies the same validate-at-the-boundary principle on the Node side: its API routes parse request bodies through zod schemas (for example `ReviewDecisionBody` in `apps/tarifguard/app/api/review/route.ts`, alongside `app/api/explain` and `app/api/coding-check`) before any upstream call, and a `safeParse` failure becomes a `problem+json` 400 (`problemFromZod`), so the same declarative-validation-at-boundaries rule holds on the BFF surface too.

### Persistence abstraction

Repository pattern over parameterised SQL, deliberately no ORM. Ingestion writes through `TariffRepository` (`services/ingestion/src/tarifhub_ingest/storage/tariff_repository.py`). Serving reads through `ServingRepository` (`services/serving/src/tarifhub_serving/repository.py`), which never writes. A small dialect-aware `Database` facade (`tarifhub_serving/db.py`: `dialect`, `placeholder`) plus the dialect-agnostic `_row_to_record` mapper let the same code run on Postgres 16 and the offline SQLite mirror.

### REST + OpenAPI

FastAPI generates the OpenAPI document from the code: resource routes (`GET /api/v1/tariffs`, `GET /api/v1/tariffs/{system}/{code}`, `GET /api/v1/search`) each declare a `response_model` (`TariffRecord`, `SearchHit`) and a summary line, so Swagger UI at `/docs` is always in sync with the implementation. The same generated document is exported to a committed `services/serving/openapi.json` and pinned by a test (`test_committed_openapi_matches_generated` in `services/serving/tests/test_openapi.py`) that fails if it ever drifts from `app.openapi()`, so the static schema a grader reads stays identical to the running one.

### Error handling

Error handling is centralised, not scattered across route handlers, and it is uniform across every HTTP surface. The serving, ingestion and intelligence services each register the same four exception handlers (`register_exception_handlers`, called once per app), and the TarifGuard BFF (`apps/tarifguard`) emits and relays the same envelope. Every failure leaves the platform as one consistent shape: an RFC 7807 `application/problem+json` document with the members `type`, `title`, `status`, `detail` and `instance`.

- **Domain errors.** Route handlers raise a small domain vocabulary (`TariffNotFound` to 404, `SearchBackendUnavailable` to 501) instead of constructing an `HTTPException` inline, so the mapping from a business condition to an HTTP status lives in exactly one place. The `detail` carries the same message as before (for example `no frozen record for code=...`), so the existing API contract is preserved: this is centralisation, not an API change.
- **Validation.** A Pydantic model or `Query` constraint violation is translated by the framework into a `RequestValidationError`, which the handler renders as a 422 problem document with the field-level errors attached as an extension member.
- **Any `HTTPException`.** A library- or router-raised `HTTPException` (for example the 404 for an unknown path) is wrapped into the same envelope, so no response is ever a bare, undocumented `{"detail": ...}`.
- **The catch-all.** An unexpected error (a repository fault, a driver error) is caught by a handler registered on `Exception`: instead of a bare, unstructured HTTP 500 it returns a structured 500 problem document carrying a generated correlation id, with no stack trace and no internal string leaked to the caller. The full traceback goes to the server log, keyed by that same id.
- **Every surface, one envelope.** The handler layer is not serving-only. `tarifhub_serving/errors.py`, `tarifhub_ingest/errors.py` and `tarifiq/errors.py` carry the byte-identical problem+json core. The replication is deliberate, not an oversight: the layer is copied per service rather than imported from one shared package so each service stays an independent microservice with no shared runtime dependency, and so each service's value-path import graph stays independently boundary-testable by its own AST boundary test rather than depending on one shared module proven import-clean for every consumer at once (the rationale is recorded in [ADR-019](../adr/019-rfc7807-error-handling.md)). The ingestion review write path, the riskiest mutating surface, raises domain exceptions (`ReviewRecordNotFound`, `ReviewConflict`, `ReviewValidationError`, the billing-field `ReviewError`) rather than a bare `HTTPException`. The Next.js BFF (`apps/tarifguard/lib/problem.ts`) builds the same envelope for its own errors and surfaces an upstream service's problem+json verbatim, so the console sees one shape end to end.

Each handler emits one structured log line (level, method, path, status, correlation id, and `record_hash` when a route has set it on the request state), so a caller-visible correlation id can be matched to a server-side log entry. The correlation id is read from an inbound `X-Request-ID` header when present (trace continuity) and otherwise minted per request. It is echoed in the `X-Correlation-ID` response header on the 500 path. Client-error (4xx) bodies deliberately carry no correlation id, so they stay byte-reproducible, consistent with the determinism boundary. The decision and its envelope are recorded in [ADR-019](../adr/019-rfc7807-error-handling.md). Invalid input still never reaches a route body: declarative `Query` and model constraints fail at the boundary, mirroring the validation concept above.

### Configuration injection

Env-only, twelve-factor: a frozen `Settings` dataclass built fresh by `get_settings()` on every call (`services/ingestion/src/tarifhub_ingest/config.py`, mirrored in `tarifhub_serving/config.py`), so tests reconfigure via `monkeypatch.setenv` with no import-time caching. The configuration settings are `TARIFHUB_DB_URL`, `TARIFHUB_REVIEW_THRESHOLD`, `ANTHROPIC_API_KEY` (presence alone enables the pre-freeze AI seam) and `TARIFHUB_EMBEDDINGS`.

### Health/readiness probes

The serving service exposes `GET /health` (`HealthResponse`, `tarifhub_serving/main.py`). The Helm chart wires it into Kubernetes readiness and liveness probes (`deploy/helm/tarifhub/templates/serving-deploy.yaml`, `httpGet path: /health`). The MCP server is probed at transport level (`tcpSocket` in `mcp-deploy.yaml`), and the compose database carries a `pg_isready` healthcheck (`deploy/docker-compose.yml`).

### Observability

Decided, not yet instrumented: [ADR-011](../adr/011-opentelemetry-observability.md) selects OpenTelemetry to Prometheus/Grafana plus Sentry. The instrumentation is pending. The traceability primitive that already exists is the append-only `audit_log` (`db/schema.sql`, written via `AuditLogger` in `services/ingestion/src/tarifhub_ingest/audit/audit_logger.py`), which records pipeline events keyed by `record_hash`.

### Container-first packaging

Per-service images on digest-pinned `python:3.12-slim` bases, each running as a non-root user: the MCP and ingestion Dockerfiles are multi-stage (builder venv to minimal runtime), the serving image vendors the ingestion package, so one canonical model ships end-to-end. Compose keeps the default profile to the database and puts MinIO behind an `objects` profile, and the Helm chart (`deploy/helm/tarifhub/`) deploys the stack to k3d.

### Dependency advisories and the runtime boundary

The npm dependency tree for the TarifGuard console reports seven advisories (`npm audit`: five moderate, one high, one critical), and the full triage is recorded in [`apps/tarifguard/SECURITY.md`](https://github.com/erhanuenlue/tarifhub/blob/main/apps/tarifguard/SECURITY.md). None is reachable on the request-serving path, which is the property that matters here, and they fall into two groups. The high and critical findings (a `vite` `server.fs.deny` bypass and a `vitest` UI file-read) belong to the Vitest test stack (`vitest`, `vite`, `esbuild`, `@vitest/mocker`, `vite-node`). These are `devDependencies` and additionally require the Vite or Vitest dev server to be listening, which happens only during local `npm test`, never in CI's headless `vitest run` and never in production. The remaining finding is a PostCSS CSS-stringify XSS reachable only by running PostCSS over untrusted CSS, and PostCSS runs only at build time over the project's own trusted Tailwind sources, never at serve time. The console's own PostCSS was upgraded to the patched 8.5.x line, so the one copy still below the fix is the one `next` bundles internally.

The two groups differ in what reaches the image, and the claim is one of reachability, not of absence from the image. The Vitest test stack is installed only in the build stage and is never traced into the standalone bundle, so `vite`, `vitest` and `esbuild` are absent from the running container (the production image, `apps/tarifguard/Dockerfile`, is a Next.js `output: "standalone"` build whose runtime stage copies only the traced server, `.next/static` and `public`). The PostCSS copy bundled inside `next` does travel into that bundle, because `next` is a runtime dependency, which is also why `npm audit` lists `next` among the flagged packages, but `next start` never invokes PostCSS's CSS stringifier on request input, so the advisory stays off the serve path. The npm-suggested `npm audit fix --force` is deliberately not applied, because it would downgrade `next` from 15.5 to 9.3.3 and force `vite`/`vitest` major bumps, trading a real, shipped App Router runtime for the cosmetic removal of advisories that are already unreachable. The supply chain is gated independently in CI by Trivy (image CVEs) and gitleaks (secrets), per [ADR-010](../adr/010-github-actions-devsecops.md).

### Dev-mode reload

Development runs uvicorn with live reload via `scripts/run_serving.sh` (`uvicorn tarifhub_serving.main:app --reload` on :8000). The production container ENTRYPOINT (`services/serving/Dockerfile`) starts uvicorn without reload, so dev convenience never leaks into the image.

### Async

The MCP server (`services/mcp/server.py`) is fully async: each tool (`search_tariffs`, `get_tariff`, `explain_crosswalk`) awaits an `httpx` async client proxying to the serving API. The serving handlers themselves are plain `def`: FastAPI executes them in its worker threadpool, which is the appropriate execution model for their short, blocking DB reads.

## Why Python-first

The workload is a read-mostly serving API in front of a write-time, AI-assisted harmonisation pipeline, and Python owns the AI/data tooling that dominates that pipeline. One canonical Pydantic `TariffRecord` travels end-to-end (parser → freeze → DB row → API response → MCP tool), removing the cross-language mapping defects a polyglot backend would invite. One toolchain (uv, pytest, ruff) keeps a solo engineer fast under a fixed CAS deadline. The strengths of heavier enterprise runtimes (JVM-class concurrency, large-team modularity) are immaterial at this scale and load.

These concepts are stack-portable. This dossier implements them in the Python stack chosen in [ADR-001](../adr/001-python-first-core.md).

Reference: per the Modulplan reading list, item [5] (the FastAPI text, Apress) covers these concepts as taught, and this chapter maps each of them to its implementation in this repository.
