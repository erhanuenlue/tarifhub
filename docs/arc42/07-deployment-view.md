# 7. Deployment View

## Local

- `docker-compose up` starts PostgreSQL 16 + pgvector and MinIO.
- Ingestion (L0) runs as a Python process (FastAPI/uvicorn) or its container image.
- Serving (L1) runs via `mvn quarkus:dev` or its JVM container image.
- Intelligence / TarifIQ (L2) runs as a Python process (`tarifiq` on :8070) or via the
  opt-in compose `services` profile.
- The L3 apps (TarifGuard, KassenFlow, MeldePilot) run via `npm run dev` (:3000/:3001/:3002)
  or the opt-in compose `apps` profile.

## Kubernetes (Helm)

`deploy/helm/tarifhub` deploys:

```
            ┌────────────── Ingress ──────────────┐
            │  /api  → serving      /ingest → ingestion │
            └───────────────────────────────────────────┘
                      │                     │
              ┌───────▼───────┐     ┌───────▼────────┐
              │  serving (n)  │     │ ingestion (1)  │
              │  Quarkus JVM  │     │  FastAPI       │
              └───────┬───────┘     └───────┬────────┘
                      └─────────┬───────────┘
                          ┌─────▼──────┐
                          │ postgres   │  (pgvector, PVC-backed)
                          └────────────┘
```

- `helm install tarifhub deploy/helm/tarifhub`
- The chart also deploys the downstream consumers — each a Deployment + Service, toggled
  by its `*.enabled` flag:
  - **TarifMCP** (`mcp.enabled`) — routed under `/mcp` on the platform host.
  - **TarifIQ / intelligence** (`intelligence.enabled`, on by default) — on its own host
    (`ingress.intelligenceHost`) so its `/v1/*` paths do not collide with serving `/api`;
    runs with `TARIFIQ_OFFLINE=0` so it reads live frozen records from serving.
  - **TarifGuard** (`tarifguard.enabled`) — on its own host (`ingress.appHost`) so its
    same-origin `/api/*` route handlers do not collide with the serving `/api` path.
  - **KassenFlow / MeldePilot** (`kassenflow.enabled` / `meldepilot.enabled`, **off by
    default** — stubs) — each on its own host.
  Every consumer receives `SERVING_BASE_URL` (and the apps also `TARIFIQ_BASE_URL`)
  pointing at the in-cluster Services.
- Images are built and pushed to GHCR by CI; `values.yaml` selects image tags,
  replicas, resources, the optional in-cluster Postgres, and the ingress hosts/TLS.
- Target demo environment: a managed Kubernetes cluster in Switzerland (data
  sovereignty); k3s/kind locally.

## Build artifacts

- Ingestion (L0): multi-stage Python image (`services/ingestion/Dockerfile`).
- Serving (L1): multi-stage JVM image (`services/serving/Dockerfile`); native image optional.
- MCP server (L1): multi-stage Python image (`services/mcp/Dockerfile`).
- Intelligence / TarifIQ (L2): multi-stage Python image (`services/intelligence/Dockerfile`).
- TarifGuard (L3): multi-stage Node image, Next.js standalone (`apps/tarifguard/Dockerfile`).
- KassenFlow (L3): multi-stage Node image (`apps/kassenflow/Dockerfile`).
- MeldePilot (L3): multi-stage Node image (`apps/meldepilot/Dockerfile`).
