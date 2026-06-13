# ADR-009: Docker images + Kubernetes via Helm; compose for local

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
The sub-systems (ingestion, serving, MCP, intelligence, apps) must be independently deployable, the hosting target is Switzerland, and local development must be reproducible for a solo operator. Graders review code and documentation only: distribution is proven by Dockerfiles, compose, Helm and CI builds in the repo, not by a live cluster; the K8s proof runs on k3d and is captured into `docs/`.

## Decision
We package each sub-system as its own Docker image, deploy them with one Helm chart (`deploy/helm/tarifhub`) to Kubernetes (k3d for the CAS proof; Exoscale/Infomaniak as the CH production target), and use `deploy/docker-compose.yml` with profiles for local development. Components that have not shipped stay disabled by default in the chart values (today the L3 stubs KassenFlow and MeldePilot, `enabled: false`).

## Alternatives weighed
- **Cloud-only managed PaaS**: couples deployment to one vendor's runtime; portable container + chart artifacts are what the repo can evidence and what CH residency is easiest to prove with.
- **Monolithic container**: one image for everything erases the sub-system boundaries, prevents independent scaling and deployment, and fails the "independently deployable containers" criterion outright.

## Consequences
- (+) Clean deploy/scale boundaries per sub-system; the distribution criterion is satisfied by artifacts a grader can read (Dockerfiles, compose, chart, CI image builds).
- (+) Local dev stays light: compose default is the database alone; `--profile objects` adds MinIO; nothing else is required for the offline test suite.
- (+) Operational surface stays small for a solo operator because unshipped components ship `enabled: false`.
- (–) A Helm chart is one more artifact to keep in sync with the services, and k3d evidence must be captured as screenshots since nothing is deployed for grading. Revisit when a paying production target exists (managed-K8s sizing, TLS, secret management beyond the demo defaults).

*Lineage: new, no legacy counterpart.*
