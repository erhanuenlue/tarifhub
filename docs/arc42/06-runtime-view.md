# 6. Runtime View

## Harmonize → freeze (ingestion)

For each source record, deterministically:

```
load → parse → map → validate → score → flag → freeze → store → audit
```

1. **load** a source artifact (e.g. the bundled EAL XLSX / ePL FHIR).
2. **parse** it into flat rows (no AI).
3. **map** rows to the canonical model (rules; optional pre-freeze AI on non-billing fields).
4. **validate** the candidate record (errors force review).
5. **score** a deterministic confidence in [0,1].
6. **flag** `requires_review` when confidence < threshold or validation failed.
7. **freeze**: stamp the SHA-256 `record_hash` (idempotent on identical content).
8. **store** the immutable row.
9. **audit**: append a lineage event.

## Serve (deterministic)

```
GET /api/v1/tariffs/{system}/{code}  →  repository read  →  frozen record (JSON/XML)
```

No AI is involved; the response is the stored frozen record, byte-for-byte.

## Search (AI, non-value)

```
GET /api/v1/search?q=...  →  embed query (langchain4j)  →  pgvector nearest neighbours  →  ranked FROZEN records
```

Search ranks and may explain; it never fabricates or alters a value.
