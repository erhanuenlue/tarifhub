# Live compose smoke: NFR-4 and NFR-5 measured on the real engine

Verbatim runtime capture behind the [arc42 §7 Deployment view](../arc42/07-deployment-view.md)
(runnability, criterion 17) and the [§10 quality requirements](../arc42/10-quality-requirements.md)
(NFR-4 read latency, NFR-5 freshness). Capture date 2026-07-03. Every number below is a real
measurement taken against running containers, not a design budget. The stack was built and booted
with the opt-in e5 overlay so that the ingestion and serving images carry the real 1024-dim
multilingual-e5-large embedder, which is what lets Postgres + pgvector serve a real semantic
ranking and a real review write-back round-trip fully in-container:

```text
$ docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.e5.yml --profile app up -d --build
```

Measurement machine: Apple M1 Pro, Docker Desktop on macOS (arm64 Linux containers). These are
host-loopback, single-replica measurements, not load tests (see the per-section caveats). The full
raw transcript, including every command and response, is retained alongside this capture.

## 1. Stack boot and healthy ps

Build and boot returned exit 0. Wall clock from build start to the `up -d --build` return was
2 minutes 18 seconds (05:15:33Z to 05:17:51Z); all four services then reached `healthy`:

```text
$ docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.e5.yml --profile app ps
NAME                  IMAGE                    COMMAND                  SERVICE      CREATED          STATUS                    PORTS
tarifhub-db           pgvector/pgvector:pg16   "docker-entrypoint.s…"   db           32 seconds ago   Up 31 seconds (healthy)   0.0.0.0:5432->5432/tcp, [::]:5432->5432/tcp
tarifhub-ingestion    tarifhub-ingestion       "uvicorn tarifhub_in…"   ingestion    32 seconds ago   Up 26 seconds (healthy)   0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp
tarifhub-serving      deploy-serving           "uvicorn tarifhub_se…"   serving      32 seconds ago   Up 26 seconds (healthy)   0.0.0.0:8001->8000/tcp, [::]:8001->8000/tcp
tarifhub-tarifguard   deploy-tarifguard        "docker-entrypoint.s…"   tarifguard   32 seconds ago   Up 20 seconds (healthy)   0.0.0.0:3000->3000/tcp, [::]:3000->3000/tcp
```

The stack was started from a clean slate: `docker compose -f deploy/docker-compose.yml down -v`
removed the `tarifhub-pgdata` volume first, so Postgres re-applied `db/schema.sql` on initdb.

## 2. NFR-5: trigger to served (full EAL source version)

The full local EAL source (`analysenliste_2026-01-01.xlsx`) was ingested in-container against the
compose Postgres, with the e5 embedder writing the `vector(1024)` column. A background poller
timestamped the first HTTP 200 for `EAL/1375` from the serving container. Two figures, both real:

- (a) First record frozen and served while ingest still streams: 60 seconds. The poller saw the
  first HTTP 200 for `EAL/1375` at 05:20:13Z, 60 seconds after the trigger at 05:19:13Z, while the
  batch was still processing the rest of the file. This evidences the ADR-002 freeze-to-serve
  immediacy: a frozen record is already the serving contract.
- (b) Full 1279-record source version processed, frozen and served: about 273 seconds. The batch
  ran to completion (exit 0) at 05:23:45Z, that is 4 minutes 32.92 seconds of wall clock from the
  trigger (the `time` total below). This is the conservative NFR-5 headline.

Both are orders of magnitude inside the 24 hour freshness goal. Note this is the in-container e5
(1024-dim) path on CPU, which is deliberately slower than the host, stub-embedder ingest figure
recorded earlier (EAL 70.6 s): the embedder and the environment differ, and the point of this
capture is the real Postgres + pgvector engine.

```text
TRIGGER T0 = 2026-07-03T05:19:13Z
$ INGEST_BATCH_DB_URL=postgresql://tarifhub:tarifhub@db:5432/tarifhub docker compose \
    -f deploy/docker-compose.yml -f deploy/docker-compose.e5.yml --profile batch \
    run --rm ingestion-batch python -m tarifhub_ingest.cli \
    --path /data-host/raw/eal/analysenliste_2026-01-01.xlsx --system EAL
{"system": "EAL", "path": "/data-host/raw/eal/analysenliste_2026-01-01.xlsx", "refill": false, "processed": 1279, "frozen": 1279, "skipped_existing": 0, "flagged_for_review": 0, "parse_failures": 0}
docker compose ...    0.09s user 0.09s system 0% cpu 4:32.92 total
BATCH_EXIT=0
SERVED T1 = 2026-07-03T05:20:13Z
TRIGGER_TO_SERVED_WALL_SECONDS (record EAL/1375) = 60
```

Backing figure (b) with a late-frozen record: after the batch exited, a record inserted near the
end of the run also serves 200:

```text
$ curl -s -o /dev/null -w 'EAL/6702.63 -> HTTP %{http_code}\n' http://localhost:8001/api/v1/tariffs/EAL/6702.63
EAL/6702.63 -> HTTP 200
```

## 3. Live point read

The frozen record served verbatim from the serving container (`:8001`), full raw JSON response:

```text
$ curl -s -w '\nHTTP %{http_code}\n' http://localhost:8001/api/v1/tariffs/EAL/1375
{"tariff_code":"1375","tariff_system":"EAL","designation":{"de":"Hämatokrit, zentrifugiert","fr":"Hématocrite, centrifugation","it":"Ematocrito, centrifugato"},"category":"Hämatologie","tax_points":"4.4","price_chf":null,"unit":"point","valid_from":"2026-01-01","valid_to":null,"source_url":"https://www.bag.admin.ch/de/analysenliste-al","source_version":"BAG AL 2026-01-01","harmonization_confidence":1.0,"requires_review":false,"metadata":{"ai_assisted":false,"mapper_version":"tariff-mapper/0.1.0"},"record_hash":"4b68c7f60c7a007d8c0cae2cbe24c8c4f013871778c2a4c5124cdbf621b8ad31","version":1,"created_at":"2026-07-03T05:20:13.533081Z"}
HTTP 200
```

The `created_at` (05:20:13Z) matches the served timestamp T1 in section 2.

## 4. Live semantic ranking (first HTTP 200 search under compose)

This is the first time the compose `/api/v1/search` endpoint returns HTTP 200 with a real ranking.
The earlier distribution capture (2026-06-13) recorded HTTP 501 here, because the default images
ship the 16-dim stub embedder whose dimension does not match the `vector(1024)` column, so search
fails closed rather than faking a result (UC-06). That 501 posture is by design and remains the
default: the e5 overlay is opt-in, and only under it does search return a ranking.

The FR query `hématocrite` returns the documented ranking (1372.01 then 1375 near the top), ranked
hits condensed to (rank, code, DE designation) for readability:

```text
$ curl -s 'http://localhost:8001/api/v1/search?q=h%C3%A9matocrite&limit=5'
{"rank":1,"tariff_code":"1372.01","de":"Hämatogramm III: Erythrozyten, Hämoglobin, Hämatokrit, Indices, Leukozyten, 3 Leukozyten-Subpopulationen und Thrombozyten"}
{"rank":2,"tariff_code":"1375","de":"Hämatokrit, zentrifugiert"}
{"rank":3,"tariff_code":"1372","de":"Hämatogramm III: Erythrozyten, Hämoglobin, Hämatokrit, Indices, Leukozyten, 3 Leukozyten-Subpopulationen und Thrombozyten"}
{"rank":4,"tariff_code":"1371","de":"Hämatogramm II: Erythrozyten, Hämoglobin, Hämatokrit, Indices, Leukozyten und Thrombozyten"}
{"rank":5,"tariff_code":"1374","de":"Hämatogramm V: Erythrozyten, Hämoglobin, Hämatokrit, Indices, Leukozyten, 5 oder mehr Leukozyten-Subpopulationen ..."}
HTTP 200
```

The full raw JSON of the top two hits (the endpoint returns a JSON array of `{rank, record}` objects,
each `record` the full frozen record verbatim):

```text
[{"rank":1,"record":{"tariff_code":"1372.01","tariff_system":"EAL","designation":{"de":"Hämatogramm III: Erythrozyten, Hämoglobin, Hämatokrit, Indices, Leukozyten, 3 Leukozyten-Subpopulationen und Thrombozyten","fr":"Hémogramme III : érythrocytes, hémoglobine, hématocrite, indices, leucocytes, 3 sous-populations leucocytaires et thrombocytes","it":"Emogramma III: eritrociti, emoglobina, ematocrito, indici, leucociti, 3 sottopopolazioni leucocitarie e trombociti"},"category":"Hämatologie","tax_points":"17.1","price_chf":null,"unit":"point","valid_from":"2026-01-01","valid_to":null,"source_url":"https://www.bag.admin.ch/de/analysenliste-al","source_version":"BAG AL 2026-01-01","harmonization_confidence":1.0,"requires_review":false,"metadata":{"ai_assisted":false,"mapper_version":"tariff-mapper/0.1.0"},"record_hash":"5402794ceffc1ababce330064b714bc43f18d85406caee2b01837e2e7aa0d0dd","version":1,"created_at":"2026-07-03T05:20:12.999234Z"}},
 {"rank":2,"record":{"tariff_code":"1375","tariff_system":"EAL","designation":{"de":"Hämatokrit, zentrifugiert","fr":"Hématocrite, centrifugation","it":"Ematocrito, centrifugato"},"category":"Hämatologie","tax_points":"4.4","price_chf":null,"unit":"point","valid_from":"2026-01-01","valid_to":null,"source_url":"https://www.bag.admin.ch/de/analysenliste-al","source_version":"BAG AL 2026-01-01","harmonization_confidence":1.0,"requires_review":false,"metadata":{"ai_assisted":false,"mapper_version":"tariff-mapper/0.1.0"},"record_hash":"4b68c7f60c7a007d8c0cae2cbe24c8c4f013871778c2a4c5124cdbf621b8ad31","version":1,"created_at":"2026-07-03T05:20:13.533081Z"}}]
```

(ranks 3 to 5 elided for length; they are in the raw transcript.) A limitation on the search
ranking under this mixed EAL + SL corpus is recorded honestly in section 7.

## 5. Review write-back round-trip (flag, human approve, new immutable version, served)

The SL subset ingest (section 7) flagged 19 low-confidence records for review. The full loop was
exercised against the ingestion review API (`:8000`) and confirmed on the serving API (`:8001`):

```text
$ curl -s http://localhost:8000/review/queue | jq length
19
# first flagged item: SL/4086000006873 "Calshake Schokolade" version 1
#   record_hash c7b87d76..., flagged_reason "harmonization_confidence 0.65 < 0.85"

$ curl -s http://localhost:8001/api/v1/tariffs/SL/4086000006873   # serving, BEFORE approve
{"tariff_code":"4086000006873","version":1,"record_hash":"c7b87d760ad6709e200a27c7b0ca1055e19e1af3462ec55cbc0bf4193fc2cc4e","requires_review":true,"de":"Calshake Schokolade"}

$ curl -s -X POST http://localhost:8000/review -H 'Content-Type: application/json' \
    -d '{"tariff_system":"SL","tariff_code":"4086000006873","action":"approve","reviewer":"e.unlue","note":"live compose smoke 2026-07-03"}'
{"ok":true,"tariff_system":"SL","tariff_code":"4086000006873","action":"approve","frozen":true,"version":2,"record_hash":"af74a95d40c8db90f039fdbf47984d8c8453ff8a292d11c1be92b22b39cc0ca1","message":"Approved the proposal verbatim and froze v2."}

$ curl -s http://localhost:8000/review/queue | jq length   # AFTER approve
18                                                          # item gone

$ curl -s http://localhost:8001/api/v1/tariffs/SL/4086000006873   # serving, AFTER approve
{"tariff_code":"4086000006873","version":2,"record_hash":"af74a95d40c8db90f039fdbf47984d8c8453ff8a292d11c1be92b22b39cc0ca1","requires_review":false,"de":"Calshake Schokolade"}
```

The approval froze a new immutable version 2 with a new `record_hash` (`af74a95d...`, distinct from
the version 1 `c7b87d76...`), the queue shrank from 19 to 18, and the serving read now returns
version 2 with `requires_review:false`. Version 1 was not mutated: a new version was appended.

## 6. NFR-4: read latency (measured)

Corpus in Postgres at measurement time (the two batch ingests of sections 2 and 7):

```text
$ psql -c "SELECT tariff_system, count(*), count(DISTINCT tariff_code), max(version) FROM tariff GROUP BY tariff_system;"
 tariff_system | rows | distinct_codes | max_version
---------------+------+----------------+-------------
 EAL           | 1279 |           1279 |           1
 SL            | 3030 |           3030 |           1
```

That is 4309 frozen records (the one approve of section 5 later took SL/4086000006873 to version 2).
Both latency legs were measured with `tools/bench/search_latency.py` (stdlib only, nearest-rank
percentiles, n=200 timed requests after 10 warmup requests) against the running serving container.

Search leg (12 labelled cross-lingual queries, limit 5, each request includes the e5 query
embedding on CPU in the container): p95 = 170.574 ms, inside the 500 ms search design budget that
§10 previously listed as not yet measured. This capture closes that gap.

```text
$ python3 tools/bench/search_latency.py --base-url http://localhost:8001 --n 200 --warmup 10
{
  "mode": "search",
  "endpoint": "/api/v1/search",
  "limit": 5,
  "warmup": 10,
  "n": 200,
  "percentile_method": "nearest-rank on sorted sample (ceil(p/100*n))",
  "p50_ms": 141.531,
  "p95_ms": 170.574,
  "min_ms": 119.8,
  "max_ms": 216.587,
  "mean_ms": 144.6
}
```

Point-read leg (single frozen record, same timing machinery): p95 = 6.464 ms, well inside the
200 ms single-record target, and comparable to the 15.8 ms p95 recorded on 2026-06-13:

```text
$ python3 tools/bench/search_latency.py --point-read --path /api/v1/tariffs/EAL/1375 --n 200 --warmup 10
{
  "mode": "point-read",
  "endpoint": "/api/v1/tariffs/EAL/1375",
  "warmup": 10,
  "n": 200,
  "percentile_method": "nearest-rank on sorted sample (ceil(p/100*n))",
  "p50_ms": 2.976,
  "p95_ms": 6.464,
  "min_ms": 2.295,
  "max_ms": 9.974,
  "mean_ms": 3.519
}
```

Caveat: both are host-loopback, single-replica measurements over warm requests on an Apple M1 Pro
under Docker Desktop. They bound the single-request path, not concurrency, and they are not a load
test.

## 7. Log scan and honest limitations

Log scan over the four running containers (a bare `docker compose logs` without the profile flags
omits the profiled app services, so each container was scanned directly). No unexplained errors:
zero serving 5xx, zero serving 501, and no secret, password or key material in any log. Two match
categories appeared, both self-inflicted by this evidence collection and both benign:

```text
# serving: 59 "status=404 error=TariffNotFound", ALL for EAL/1375
#   -> the NFR-5 poller probing serving once per second during the 60 s pre-freeze window;
#      correct 404-then-200 behaviour (the record did not exist yet).
# db: one "ERROR: unrecognized configuration parameter hnsw.ef_search"
#   -> a manual "SHOW hnsw.ef_search" diagnostic run during this capture, not the application.
$ docker logs tarifhub-serving --since 60m | grep -c "status=5"   ->  0
$ docker logs tarifhub-serving --since 60m | grep -c "status=501" ->  0
```

Limitations, stated honestly:

1. SL leg is a subset. The full SL export is 93 MB / 10299 records; in-container CPU e5 embedding of
   the whole file is too slow for a smoke. A real first-2000-lines subset of the export was ingested
   (`sl-subset-first2000-20260703.ndjson`). It expanded to 3030 records: processed 3030, frozen 3030,
   flagged for review 19, parse_failures 21 (GTIN-less packages fail closed), exit 0, 9 minutes
   14 seconds wall. The 19 flagged records are what made the section 5 round-trip possible.

   ```text
   {"system": "SL", "path": "/data-host/raw/epl/sl-subset-first2000-20260703.ndjson", "refill": false, "processed": 3030, "frozen": 3030, "skipped_existing": 0, "flagged_for_review": 19, "parse_failures": 21}
   ```

2. Search ranking is limit-sensitive on the mixed corpus (a finding, not a blocker for runnability).
   With both systems loaded (1279 EAL + 3030 SL), the DE query `Glukose im Blut` returns only SL
   pharmaceutical products at `limit` 5, 10 and 20, but returns the semantically correct EAL glucose
   tests (1472, 1356.01, 1356, 1359) at `limit` 50, with no SL products in the top 50 at all. The FR
   `hématocrite` control is stable (EAL/1372.01 at both limit 5 and limit 50). Recall at 5 over the
   12 labelled queries on this mixed corpus is 6 of 12. Root cause: the pgvector search path issues
   `ORDER BY embedding <=> query LIMIT k` against an HNSW index (`ix_tariff_embedding`) without
   setting `hnsw.ef_search`, so it uses the pgvector default (40); at small `limit` the approximate
   search returns local (SL-cluster) neighbours rather than the globally nearest records. This does
   not affect the latency numbers in section 6 (latency, not correctness) and does not affect the
   point-read or review paths. It is captured here for follow-up.

3. The e5 overlay is opt-in. The default compose stack ships the 16-dim stub and search fails closed
   with HTTP 501 by design. Every number in this file was taken under the e5 overlay, on an Apple M1
   Pro under Docker Desktop on macOS. No LLM client is present on the value path in any of these
   images: the e5 build installs sentence-transformers only.
