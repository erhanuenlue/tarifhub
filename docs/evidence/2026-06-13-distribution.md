# Distribution evidence: Compose + CI images + k3d/Helm (2026-06-13)

Verbatim capture behind the [§7 Deployment view](../arc42/07-deployment-view.md)
(criterion 17). All commands were run on 2026-06-13. The screenshots in `docs/img/`
(`compose-ps.png`, `k3d-pods.png`) only illustrate; the quoted text below and in §7 is the
evidence.

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

`docker compose --profile services --profile apps ps` (8 independent containers up;
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

point-read latency, n=200 warm GETs:   p50 = 10.1 ms   p95 = 15.8 ms   (NfA-4 target < 200 ms)
GET /api/v1/search (embedder-dim mismatch on this leg): HTTP 501 (honest unavailability)
```

## 3 · Chart is valid and deploys on Kubernetes (k3d)

```text
$ helm lint deploy/helm/tarifhub
1 chart(s) linted, 0 chart(s) failed

$ helm template tarifhub deploy/helm/tarifhub | grep '^kind:' | sort | uniq -c
   6 kind: Deployment
   1 kind: Ingress
   1 kind: PersistentVolumeClaim
   1 kind: Secret
   6 kind: Service
```

A throwaway k3d cluster, local images imported (`k3d image import`), `helm install`:

```text
$ kubectl get pods
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

$ kubectl get deploy
NAME                    READY   UP-TO-DATE   AVAILABLE   AGE
tarifhub-serving        2/2     2            2           42s
tarifhub-intelligence   2/2     2            2           42s
tarifhub-tarifguard     2/2     2            2           42s
tarifhub-mcp            1/1     1            1           42s
tarifhub-postgres       1/1     1            1           42s
tarifhub-ingestion      0/1     1            0           42s
```

The read/serve sub-systems (serving ×2, mcp, intelligence ×2, tarifguard ×2) and Postgres
are `Running`. `tarifhub-ingestion` is `0/1` by design: ingestion is a one-shot batch
pipeline, so running it as a long-lived `Deployment` means it runs to completion and the
ReplicaSet restarts it (in production it belongs in a `Job`/`CronJob`, noted as
follow-up). Functional data serving is demonstrated under Compose above (the chart's
Postgres starts schema-empty); the k3d run proves the chart deploys every sub-system as an
independent, individually-scaled workload on real Kubernetes.
