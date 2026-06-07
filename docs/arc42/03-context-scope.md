# 3. Context and Scope

## Business context

```
[ Public tariff sources ]            [ Consumers ]
  BAG EAL (XLSX)        \           /  PIS/HIS vendor systems
  BAG ePL (FHIR R5)      ─▶ TarifHub ─▶  Internal apps / analysts
  (future: OAAT, cantons)/           \  Semantic search clients
```

- **Inputs:** publicly available tariff datasets in heterogeneous formats (tabular XLSX,
  FHIR bundles, later XML/PDF). No PII, no patient data in the core.
- **Outputs:** canonical frozen tariff records over REST (JSON/XML), plus ranked search
  results that are themselves frozen records.

## Technical context

| Neighbour | Interface | Direction |
|---|---|---|
| Source providers (BAG, …) | File/API fetch (offline samples in repo) | in |
| Ingestion service | FastAPI admin/read API; writes frozen rows | in/out |
| PostgreSQL + pgvector | SQL; system of record + vectors | in/out |
| Serving service | REST (JSON/XML) + semantic search | out |
| Observability stack | Prometheus metrics, OpenTelemetry traces | out |

## Scope

In scope: the TarifHub core — two services, AI harmonization (pre-freeze), AI search
(serving), the canonical model, and deployment. Out of scope: commercial application
layers built on top of the core (future phases).
