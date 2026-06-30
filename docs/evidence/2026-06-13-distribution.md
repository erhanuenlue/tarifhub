# Distribution evidence: Compose + CI images + k3d/Helm

Verbatim capture behind the [§7 Deployment view](../arc42/07-deployment-view.md)
(criterion 17). The CI-image and Compose captures (sections 1 and 2) were run on 2026-06-13.
The k3d/Helm capture (section 3) was recaptured on 2026-06-30 against the current chart. The
`compose-ps.png` screenshot only illustrates. The quoted text below and in §7 is the evidence.

## 1 · Every sub-system image builds in CI

The `images` job in `.github/workflows/ci.yml` (on `main`, after `python` + `security`)
builds every `services/*/Dockerfile` and `apps/*/Dockerfile`. From CI run log
(`.shipboard/cov/ci_images.log`), the BuildKit "naming to" lines, one per image:

```text
#19 naming to docker.io/library/tarifhub-ingestion:ci      done
#16 naming to docker.io/library/tarifhub-intelligence:ci   done
#17 naming to docker.io/library/tarifhub-mcp:ci            done
#13 naming to docker.io/library/tarifhub-serving:ci        done
#19 naming to docker.io/library/tarifhub-kassenflow:ci     done
#18 naming to docker.io/library/tarifhub-meldepilot:ci     done
#18 naming to docker.io/library/tarifhub-tarifguard:ci     done
```

All seven sub-system images (4 services + 3 apps) build in CI. The serving image is built
from the repo root so it can vendor the sibling `ingestion` package (one canonical
`TariffRecord` end-to-end).

## 2 · Full stack runs under Docker Compose

`docker compose --profile services --profile apps ps` (8 independent containers up,
`db` and `minio` report `healthy`):

```text
SERVICE        IMAGE                    STATUS                    PORTS
db             pgvector/pgvector:pg16   Up (healthy)              0.0.0.0:5432->5432/tcp
serving        tarifhub-serving         Up                        0.0.0.0:8000->8000/tcp
mcp            tarifhub-mcp             Up                        0.0.0.0:8090->8090/tcp
intelligence   tarifhub-intelligence    Up                        0.0.0.0:8070->8070/tcp
tarifguard     tarifhub-tarifguard      Up                        0.0.0.0:3000->3000/tcp
kassenflow     tarifhub-kassenflow      Up                        0.0.0.0:3001->3001/tcp
meldepilot     tarifhub-meldepilot      Up                        0.0.0.0:3002->3002/tcp
minio          minio/minio:latest       Up (healthy)              0.0.0.0:9000-9001->9000-9001/tcp
```

Functional smoke against the live serving container (`:8000`), reading the 11 653 frozen
rows in the compose Postgres:

```text
$ curl -s localhost:8000/health
{"status":"ok"}

$ curl -s localhost:8000/api/v1/tariffs/EAL/1000
{"tariff_system":"EAL","tariff_code":"1000",
 "designation":{"de":"1,25-Dihydroxy-Vitamin D","fr":"1,25-dihydroxy-vitamine D","it":"1,25-diidrossivitamina D"},
 "tax_points":"76.5","version":1,
 "record_hash":"33f658ff57952693dc45b51c2c7b11e567d2d3799278247d3231aa67e40f69a0"}

point-read latency, n=200 warm GETs:   p50 = 10.1 ms   p95 = 15.8 ms   (NFR-4 target < 200 ms)
GET /api/v1/search (embedder-dim mismatch on this leg): HTTP 501 (honest unavailability)
```

## 3 · Chart is valid and deploys on Kubernetes (k3d)

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

A throwaway k3d cluster (recaptured 2026-06-30 against the current chart), the locally built
images imported (`k3d image import`), then `helm install` with value overrides for the local
offline run: the chart image repositories pointed at those images,
`ingestion.env.TARIFHUB_DB_URL` set to a pod-local SQLite mirror with the stub embedder, and the
batch pointed at the bundled SL sample (`ingestion.batch.system=SL`), the same offline path the
Compose batch below uses, since the in-cluster Postgres + pgvector path needs the 1024-dim e5
embedder. The chart's Postgres still starts schema-empty here, so this is a topology and
lifecycle proof, the data-serving proof being section 2 under Compose:

```text
$ kubectl get pods
NAME                                     READY   STATUS      RESTARTS   AGE
tarifhub-ingestion-54d4d4fb9d-mhcbr      1/1     Running     0          44s
tarifhub-ingestion-batch-wrkwg           0/1     Completed   0          44s
tarifhub-intelligence-67db88f8cb-84xsf   1/1     Running     0          44s
tarifhub-intelligence-67db88f8cb-s876s   1/1     Running     0          44s
tarifhub-mcp-86869967b7-4k4nq            1/1     Running     0          44s
tarifhub-postgres-749d46bdb5-4hgmm       1/1     Running     0          44s
tarifhub-serving-595b7f5f8f-hw4pq        1/1     Running     0          44s
tarifhub-serving-595b7f5f8f-jjh2k        1/1     Running     0          44s
tarifhub-tarifguard-6ccc45788f-55gp6     1/1     Running     0          44s
tarifhub-tarifguard-6ccc45788f-w588z     1/1     Running     0          44s

$ kubectl get jobs
NAME                       STATUS     COMPLETIONS   DURATION   AGE
tarifhub-ingestion-batch   Complete   1/1           3s         44s

$ kubectl get deploy
NAME                    READY   UP-TO-DATE   AVAILABLE   AGE
tarifhub-ingestion      1/1     1            1           44s
tarifhub-intelligence   2/2     2            2           44s
tarifhub-mcp            1/1     1            1           44s
tarifhub-postgres       1/1     1            1           44s
tarifhub-serving        2/2     2            2           44s
tarifhub-tarifguard     2/2     2            2           44s

$ kubectl logs job/tarifhub-ingestion-batch
{"system": "SL", "path": "/app/sample-data/input/bag_epl_sample.ndjson", "refill": false, "processed": 3, "frozen": 3, "skipped_existing": 0, "flagged_for_review": 0, "parse_failures": 0}
```

The post-split topology is live on real Kubernetes, with no long-running ingestion Deployment
stuck at `0/1 Running`. The ingestion **review API** is a long-running Deployment at `1/1` (its
`/health` readiness probe passing) and the ingestion **batch** is a `Job` that ran to completion
(`Complete 1/1`, the pod `Completed`, its log showing 3 of 3 bundled SL records frozen and exit
0). The read/serve sub-systems (serving x2, intelligence x2, tarifguard x2, mcp) and Postgres
are all `Running`. Modelling the run-to-completion batch as a Job rather than a Deployment is the
crit-17 fix, and the chart deploys every enabled workload as an independent, individually-scaled
workload.

## The dual ingestion workload (crit-17) also runs under Compose

The chart models ingestion as two distinct workloads (the [ADR-009 addendum](../adr/009-docker-kubernetes-helm.md)):
the long-running **review API** (a Deployment plus Service) and the run-to-completion **batch**
pipeline (a Job, or a CronJob when `ingestion.batch.schedule` is set). Section 3 above captures
both live on k3d (the review API `1/1`, the batch Job `Complete`) and quotes the `helm template`
kinds. The same dual workload runs from the current image under Compose, run 2026-06-19.

### Compose runs the dual workload from current source

```text
# review API: long-running service, healthy (the console's INGEST_BASE_URL target)
$ docker compose -f deploy/docker-compose.yml --profile app ps db ingestion
SERVICE     IMAGE                    STATUS         PORTS
db          pgvector/pgvector:pg16   Up (healthy)   0.0.0.0:5432->5432/tcp
ingestion   tarifhub-ingestion       Up (healthy)   0.0.0.0:8000->8000/tcp

$ curl -s localhost:8000/health       -> {"status":"ok","service":"tarifhub-ingest","version":"0.1.0"}
$ curl -s localhost:8000/review/queue -> []          # crit-16 endpoint live; empty, nothing flagged

# batch: run-to-completion, exits 0
$ docker compose -f deploy/docker-compose.yml --profile batch run --rm ingestion-batch
{"system": "SL", "path": "/app/sample-data/input/bag_epl_sample.ndjson", "refill": false,
 "processed": 3, "frozen": 3, "skipped_existing": 0, "flagged_for_review": 0, "parse_failures": 0}
$ echo $?
0
```

The same image is the long-running review API under its default CMD and a one-shot batch under the CLI
command. The batch writes the offline SQLite mirror with the bundled stub embedder. The shared-Postgres
path needs the e5 (1024-dim) embedder (the `vector(1024)` column rejects the 16-dim stub, the same
dimension limitation section 2 notes for search), so it is the production target rather than the
offline-stub demonstration that runs on k3d and under Compose here.
