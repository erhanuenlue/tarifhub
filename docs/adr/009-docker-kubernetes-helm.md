# ADR-009: Docker images + Kubernetes via Helm, compose for local

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
The sub-systems (ingestion, serving, MCP, intelligence, apps) must be independently deployable, the hosting target is Switzerland, and local development must be reproducible for a solo operator. Graders review code and documentation only: distribution is proven by Dockerfiles, compose, Helm and CI builds in the repo, not by a live cluster. The K8s proof runs on k3d and is captured into `docs/`.

## Decision
We package each sub-system as its own Docker image, deploy them with one Helm chart (`deploy/helm/tarifhub`) to Kubernetes (k3d for the CAS proof, Exoscale/Infomaniak as the CH production target), and use `deploy/docker-compose.yml` with profiles for local development. Components that have not shipped stay disabled by default in the chart values (today the L3 stubs KassenFlow and MeldePilot, `enabled: false`).

## Alternatives weighed
- **Cloud-only managed PaaS**: couples deployment to one vendor's runtime. Portable container + chart artifacts are what the repo can evidence and what CH residency is easiest to prove with.
- **Monolithic container**: one image for everything erases the sub-system boundaries, prevents independent scaling and deployment, and fails the "independently deployable containers" criterion outright.

## Consequences
- (+) Clean deploy/scale boundaries per sub-system. The distribution criterion is satisfied by artifacts a grader can read (Dockerfiles, compose, chart, CI image builds).
- (+) Local dev stays light: compose default is the database alone. `--profile objects` adds MinIO, and nothing else is required for the offline test suite.
- (+) Operational surface stays small for a solo operator because unshipped components ship `enabled: false`.
- (-) A Helm chart is one more artifact to keep in sync with the services, and k3d evidence must be captured as screenshots since nothing is deployed for grading. Revisit when a paying production target exists (managed-K8s sizing, TLS, secret management beyond the demo defaults).

## Addendum (2026-06-19): ingestion is modelled as two workloads

After the crit-16 review API landed, ingestion has two distinct runtime shapes that must be deployed differently, so the single ingestion Deployment is split:

- the **review API** is a long-running HTTP service (the human-in-the-loop review surface the console reaches via `INGEST_BASE_URL`), so it stays a Deployment plus Service with a `/health` readiness and liveness probe and reports 1/1.
- the **batch pipeline** (load, harmonise, freeze) is run-to-completion, so it becomes a Kubernetes Job (a CronJob when `ingestion.batch.schedule` is set, for example a quarterly BAG release cadence). Modelling a run-to-completion batch as a Deployment is what produced the earlier 0/1 not-ready artifact: a Deployment restarts the finished pod forever.

Both share one image (the image's default CMD serves the review API, while the Job overrides the command to run the ingestion CLI). The local Compose stack mirrors the split: the review API under `--profile app`, the batch one-shot under `--profile batch`.

*Lineage: new, no legacy counterpart.*
