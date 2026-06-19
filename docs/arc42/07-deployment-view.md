# Deployment View

tarifhub ships as a set of independently containerised sub-systems. This chapter shows the
deployment topology, the chosen architecture style and why, and the evidence that the
solution is actually runnable, both under Docker Compose and on Kubernetes. The runtime
proof is captured here as quoted output plus illustrative screenshots, so it can be followed
from the document alone; full verbatim capture is in
[`docs/evidence/2026-06-13-distribution.md`](../evidence/2026-06-13-distribution.md).

## Sub-systems and their containers

Each box in the [building-block view](05-building-block-view.md) maps to exactly one image.
The boundary that matters is the **freeze line**: everything left of it runs pre-freeze and
may use AI; everything right of it is the deterministic value path and ships no LLM client.

![Deployment topology: k3d Kubernetes (Helm) and CI/CD](../img/diagrams/deployment-view.png)

> **Figure: The deployment topology.** The Helm chart for the k3d Kubernetes proof: an nginx ingress in front of the read/serve workloads (serving, MCP, console, TarifIQ) and the ingestion review API, over a Postgres-plus-pgvector store, with two optional L3 stubs off by default. Ingestion runs as two distinct workloads: the long-running review API (a Deployment plus Service the console reaches via INGEST_BASE_URL) and the run-to-completion batch pipeline (a Kubernetes Job, or a CronJob on a schedule). CI builds every image and a gated workflow deploys the docs to Pages; local development uses docker-compose with profiles.

| Sub-system | Layer | Image | Port | Side of freeze line |
|---|---|---|---|---|
| `ingestion` | L0 harmonisation | `tarifhub-ingestion` | 8000 (review API) · batch (Job) | write, pre-freeze (AI seam lives here) |
| `serving` | L1 TarifCore | `tarifhub-serving` | 8000 | read, post-freeze (deterministic) |
| `mcp` | L1 TarifMCP | `tarifhub-mcp` | 8090 | read, post-freeze (proxy) |
| `intelligence` | L2 TarifIQ | `tarifhub-intelligence` | 8070 | read, post-freeze (deterministic rules) |
| `tarifguard` | L3 console | `tarifhub-tarifguard` | 3000 | read (UI over serving) |
| `kassenflow`, `meldepilot` | L3 apps (stubs) | `tarifhub-{kassenflow,meldepilot}` | 3001/3002 | read (UI), `enabled: false` by default |
| `db` | data | `pgvector/pgvector:pg16` | 5432 | system of record |
| `minio` | object store | `minio/minio` | 9000/9001 | raw source artifacts (ADR-007) |

The **graded MVP value path is L0 ingestion → L1 serving/MCP → L3 console**, over the
database. The L2 `intelligence` service and the L3 `kassenflow`/`meldepilot` apps are
post-CAS-scope scaffolds ([§5](05-building-block-view.md)); they are packaged like every
other sub-system so the chart and Compose can bring up the full topology, but they sit
outside the MVP value path (`kassenflow`/`meldepilot` ship `enabled: false` in the chart).
All read-side sub-systems, in or out of the MVP path, stay post-freeze and ship no LLM client.

## Style choice: distributed services along the freeze line

The CAS rubric treats a **modular monolith** as equally valid as
**distributed services**; the choice must simply be justified. tarifhub chooses distributed
services, decomposed along the freeze line ([ADR-002](../adr/002-freeze-line-decomposition.md)):
the value-path invariant ("no AI computes or mutates a billing value at serve time") becomes a
*process boundary* rather than a convention inside one process. The serving image physically
ships no LLM client, so the AST boundary test plus the image contents enforce the rule
mechanically, and the read side scales, deploys and fails independently of the AI-rich write
side, whose quality profile is opposite. The cost is a shared schema as the integration
contract ([ADR-003](../adr/003-canonical-record-model.md)); a modular monolith would have
been a legitimate alternative but would reduce the freeze line to an in-process convention.
Packaging is one image per sub-system, one Helm chart for Kubernetes, and Compose with
profiles for local development ([ADR-009](../adr/009-docker-kubernetes-helm.md)); PostgreSQL 16
+ pgvector is the single store ([ADR-006](../adr/006-postgres-pgvector.md)).

## Local development: Docker Compose with profiles

Two compose files cover the two halves of the stack. The root `docker-compose.yml` layers the
read/serve sub-systems via profiles so the offline test suite needs nothing running:

- default: `db` + `minio` only;
- `--profile services`: adds `serving` (FastAPI) and `intelligence` (TarifIQ);
- `--profile apps`: adds `tarifguard`, `mcp`, `kassenflow`, `meldepilot`.

The wired write-side review loop lives in `deploy/docker-compose.yml`, which makes the two
distinct ingestion workloads explicit (mirroring the Helm Deployment-vs-Job split):

- `--profile app`: `db` + the ingestion **review API** (`GET /review/queue`, `POST /review`)
  + `serving` + the `tarifguard` console. The console reaches the review API through
  `INGEST_BASE_URL` (`http://ingestion:8000`), so the human-in-the-loop write-back
  (console to `POST /review` to validate to freeze to audit) runs end to end. The review API
  carries a `/health` healthcheck and reports healthy: it is a long-running service.
- `--profile batch`: the run-to-completion **batch pipeline** (`ingestion-batch`), the same
  image with its CMD overridden to the ingestion CLI. It loads, harmonises and freezes a
  bundled source into the database, then exits (`restart: "no"`, no healthcheck): a one-shot,
  not a service. Run it with `docker compose -f deploy/docker-compose.yml --profile batch run
  --rm ingestion-batch`.
- `--profile objects`: `minio` for raw source artifacts.

## Evidence 1: every sub-system image builds in CI

The `images` job (`.github/workflows/ci.yml`, on `main` after `python` + `security`) builds
every `services/*/Dockerfile` and `apps/*/Dockerfile`. The BuildKit "naming to" lines from
the CI log, one per image, show all seven building:

```text
naming to docker.io/library/tarifhub-ingestion:ci     done
naming to docker.io/library/tarifhub-intelligence:ci  done
naming to docker.io/library/tarifhub-mcp:ci           done
naming to docker.io/library/tarifhub-serving:ci       done
naming to docker.io/library/tarifhub-kassenflow:ci    done
naming to docker.io/library/tarifhub-meldepilot:ci    done
naming to docker.io/library/tarifhub-tarifguard:ci    done
```

**Interpretation.** Distribution is reproducible from source on every push to `main`: the
four services and three apps each produce an independent image, so the "independently deployable
containers" property is proven by the pipeline, not asserted. The serving image is built
from the repo root because it vendors the sibling `ingestion` package (the canonical
`TariffRecord` + embedder), keeping one model end-to-end.

This image build is one stage of the wider CI/CD and quality-gate machinery that governs the
AI-assisted build: lint and tests, the determinism boundary tests, secrets and vulnerability
scans, and the anchor ratchet. That machinery and the `/ship` pipeline it sits inside are
described in [the AI-SE framework chapter](../method/ai-se-framework.md).

## Evidence 2: the full stack runs under Compose

`docker compose -f docker-compose.yml --profile services --profile apps up -d` brings up eight
independent containers; `db` and `minio` report `healthy`, and the L1 serving container answers over
HTTP against the 11 653 frozen rows in the compose Postgres.

![docker compose ps: eight independent tarifhub containers running, with a live serving smoke and point-read latency](../img/compose-ps.png)

```text
SERVICE        IMAGE                    STATUS          PORTS
db             pgvector/pgvector:pg16   Up (healthy)    0.0.0.0:5432->5432/tcp
serving        tarifhub-serving         Up              0.0.0.0:8000->8000/tcp
mcp            tarifhub-mcp             Up              0.0.0.0:8090->8090/tcp
intelligence   tarifhub-intelligence    Up              0.0.0.0:8070->8070/tcp
tarifguard     tarifhub-tarifguard      Up              0.0.0.0:3000->3000/tcp
kassenflow     tarifhub-kassenflow      Up              0.0.0.0:3001->3001/tcp
meldepilot     tarifhub-meldepilot      Up              0.0.0.0:3002->3002/tcp
minio          minio/minio:latest       Up (healthy)    0.0.0.0:9000-9001->9000-9001/tcp
```

**Interpretation.** This is the "runnable via Compose" proof: the module
boundaries from the building-block view are visible as eight running containers with
distinct ports, and `serving` returns a real frozen record verbatim (`EAL/1000`,
`tax_points "76.5"`, trilingual designation) at p95 = 15.8 ms over 200 warm point reads,
inside the NfA-4 target of 200 ms. Semantic search on this leg returns HTTP 501 because the
container's embedder dimension does not match the `vector(1024)` column: honest
unavailability, never a faked ranking (NfA-1). Latency is a host-loopback measurement on a
single replica, not a load test; it bounds the single-record path, not concurrency.

## Evidence 3: the chart deploys on Kubernetes (k3d)

The Helm chart `deploy/helm/tarifhub` comprises: a `Chart.yaml`; a `values.yaml` whose
top-level keys are the sub-systems (`ingestion`, `serving`, `mcp`, `intelligence`,
`tarifguard`, plus `kassenflow`/`meldepilot` shipped `enabled: false`); a Deployment plus
Service template per long-running sub-system under `templates/`; the ingestion split into the
**review API** (a Deployment plus Service) and the **batch** pipeline (a separate
run-to-completion Job, or a CronJob when `ingestion.batch.schedule` is set), so the two
ingestion workloads are modelled honestly rather than as one perpetually-restarting
Deployment; an in-cluster `postgres` Deployment with its `db-secret`; an `ingress` fronting the
platform hosts; and per-sub-system `replicas`, `resources` and image settings. `helm lint`
passes and `helm template` renders the intended kinds, a Job for the batch alongside the review
Deployment plus Service:

```text
$ helm lint deploy/helm/tarifhub
1 chart(s) linted, 0 chart(s) failed

$ helm template tarifhub deploy/helm/tarifhub | grep '^kind:' | sort | uniq -c
   6 kind: Deployment
   1 kind: Ingress
   1 kind: Job
   1 kind: PersistentVolumeClaim
   1 kind: Secret
   6 kind: Service
```

**Interpretation.** The six Deployments are the long-running services (`serving` and
`intelligence` and `tarifguard` at two replicas, `mcp` and `postgres` and the ingestion
**review API** at one); the single Job is the run-to-completion ingestion **batch**; the six
Services front the long-running workloads only (the batch Job has none). This is the fix for
the earlier k3d capture below, where ingestion was a single Deployment and so showed `0/1`.

### The earlier 0/1 artifact, and the fix

A throwaway k3d cluster (2026-06-13) with the locally built images imported and `helm install`
run brought the platform up on real Kubernetes, but the then-single ingestion Deployment showed
`0/1`:

![kubectl get pods on k3d (2026-06-13, before crit-17): ingestion 0/1 because a run-to-completion batch was modelled as a Deployment](../img/k3d-pods.png)

```text
# 2026-06-13 capture, BEFORE the crit-17 split, kept to show what the change fixes
NAME                                     READY   STATUS    RESTARTS   AGE
tarifhub-postgres-749d46bdb5-7r6rl       1/1     Running   0          41s
tarifhub-serving-595b7f5f8f-krdvk        1/1     Running   0          41s
tarifhub-serving-595b7f5f8f-lzgjg        1/1     Running   0          41s
tarifhub-mcp-86869967b7-lxrr7            1/1     Running   0          41s
tarifhub-intelligence-67db88f8cb-j67wr   1/1     Running   0          41s
tarifhub-intelligence-67db88f8cb-mt2hp   1/1     Running   0          41s
tarifhub-tarifguard-58d7bbb868-lrsjg     1/1     Running   0          41s
tarifhub-tarifguard-58d7bbb868-ncxbq     1/1     Running   0          41s
tarifhub-ingestion-5d5dddc876-njbvx      0/1     Running   3          41s
```

**Interpretation.** The `0/1` was honest but wrong-by-design: a run-to-completion batch
pipeline modelled as a long-lived `Deployment` runs to completion, the readiness probe then
fails, and the ReplicaSet restarts it forever. The crit-17 change (above, [ADR-009 addendum](../adr/009-docker-kubernetes-helm.md))
splits ingestion into the review-API Deployment (which stays a healthy 1/1 long-running
service) and the batch Job (which reports Completed). A re-deployed k3d cluster on the current
chart therefore shows no `0/1`: the review API at `1/1 Running` and `tarifhub-ingestion-batch`
at `Completed`. **TODO (owner):** re-capture the live `kubectl get pods` / `kubectl get
jobs` and refresh `docs/img/k3d-pods.png` against the current chart; the kinds above are the
authoritative manifest proof, and the dual workload is shown running under Compose below. The
in-cluster batch writes to Postgres, whose `vector(1024)` column needs the e5 (1024-dim)
embedder; the offline-stub run is demonstrated under Compose against the SQLite mirror (the
same offline/online split as Evidence 2 above).

### The dual ingestion model runs under Compose (2026-06-19)

`deploy/docker-compose.yml` runs the two ingestion workloads from the current image. The
**review API** is a healthy long-running service (the console's `INGEST_BASE_URL` target); the
**batch** runs to completion and exits. Verbatim:

```text
# review API: long-running, healthy
$ docker compose -f deploy/docker-compose.yml --profile app ps db ingestion
SERVICE     IMAGE                    STATUS                    PORTS
db          pgvector/pgvector:pg16   Up (healthy)              0.0.0.0:5432->5432/tcp
ingestion   tarifhub-ingestion       Up (healthy)              0.0.0.0:8000->8000/tcp

$ curl -s localhost:8000/health        -> {"status":"ok","service":"tarifhub-ingest","version":"0.1.0"}
$ curl -s localhost:8000/review/queue  -> []      # crit-16 endpoint live; empty, nothing flagged

# batch: run-to-completion, exits 0 (NOT a long-running service)
$ docker compose -f deploy/docker-compose.yml --profile batch run --rm ingestion-batch
{"system": "SL", "path": ".../bag_epl_sample.ndjson", "processed": 3, "frozen": 3,
 "skipped_existing": 0, "flagged_for_review": 0, "parse_failures": 0}
$ echo $?   ->  0
```

**Interpretation.** One image, two runtime shapes: with its default CMD it is the long-running
review API (`Up (healthy)`, serving `/review/queue`); with the CLI command it harmonises and
freezes three SL records and exits `0`. That is precisely why Helm models them as a Deployment
plus a Job: a Deployment keeps the process alive and restarts it (right for the API, wrong for
a batch), a Job runs once to completion (right for the batch). The batch here writes the
offline SQLite mirror with the bundled stub embedder; the shared-Postgres path needs the e5
(1024-dim) embedder, matching the search note in Evidence 2.

## Production target

The hosting target is Switzerland for data residency ([ADR-012](../adr/012-data-residency-llm-region.md));
k3d is the local CAS proof and a managed Swiss Kubernetes (Exoscale/Infomaniak) is the
production target ([ADR-009](../adr/009-docker-kubernetes-helm.md)). The demo defaults
(in-cluster Postgres, plaintext secret) are explicitly dev-only and called out in the chart
values for production override.
