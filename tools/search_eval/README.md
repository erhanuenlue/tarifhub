# search_eval — cross-lingual ranked-retrieval harness

Quantifies the multilingual-e5 **query/passage prefix** fix for vector search.
Block-0's pgvector proof showed French `hématocrite` ranking the exact record
(EAL 1375, *Hämatokrit, zentrifugiert*) at **3, not 1** — because production embedded
the query through the **passage path** (`embed(q)`, applying the `"passage: "` prefix)
instead of the e5-expected `"query: "` prefix. Passages were indexed correctly; the
query side used the wrong instruction prefix
(see `docs/evidence/2026-06-11-postgres-serving-pgvector.md` §6b).

The harness runs the labelled query set both ways and reports the difference.

## Files

- `queries.yaml` — ~12 labelled queries across DE/FR/IT/EN, each mapping to a real EAL
  `tariff_code` (codes/designations taken from the 2026-06-11 run), with a `why` note.
- `eval.py` — runs each query through the **repo's own** `get_embedder` +
  `ServingRepository.search_by_embedding` (identical ranking SQL to the serving API),
  reports per-query rank + MRR@5 + recall@5, emits a paste-ready Markdown table.
- `test_eval.py` — offline tests for the rank/MRR@5 math and the labelled set (no DB/model).

## Run (live: Postgres+pgvector with the e5 model)

```bash
docker compose -f deploy/docker-compose.yml up -d db   # Postgres 16 + pgvector
# ... ingest the EAL list so frozen records carry e5 embeddings ...

TARIFHUB_DB_URL=postgresql://tarif:tarif@localhost:5432/tarifhub \
TARIFHUB_EMBEDDINGS=e5 \
uv run --project services/serving python tools/search_eval/eval.py --prefix passage  # baseline
TARIFHUB_DB_URL=postgresql://tarif:tarif@localhost:5432/tarifhub \
TARIFHUB_EMBEDDINGS=e5 \
uv run --project services/serving python tools/search_eval/eval.py --prefix query    # the fix
```

`--prefix passage` embeds queries through the passage path (`embed`, `"passage: "`
prefix) — the faithful Block-0 production baseline; `--prefix query` adds the e5-expected
`"query: "` prefix (the fix). A no-prefix ("raw") mode is deliberately omitted: it never
existed in production — we measure what existed (passage-prefixed) vs what ships
(query-prefixed). Paste both tables into the arc42 §10 subsection. The harness refuses to
run against SQLite or the 16-dim offline stub — ranks would be meaningless — so it is
exercised in the e2e phase, not the offline unit suite.

## Offline self-test

```bash
uv run --project services/serving python -m pytest tools/search_eval/test_eval.py -q
```
