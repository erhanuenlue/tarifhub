# 12. Glossary

| Term | Definition |
|---|---|
| Freeze | Stamping a record with a deterministic SHA-256 `record_hash`, making it immutable. |
| Freeze line | The boundary after which no AI may influence a value; everything served is frozen. |
| Canonical model | The single, frozen field set every source is harmonized into. |
| Harmonization | Mapping heterogeneous source data into the canonical model (AI-assisted, pre-freeze). |
| Confidence | A deterministic score in [0,1] gating human review. |
| `requires_review` | Flag set when confidence is below threshold or validation failed. |
| Audit log | Append-only lineage of every freeze event. |
| EAL | BAG Analysenliste — lab analyses, tax-point based, German-only. |
| ePL / SL | BAG elektronische Spezialitätenliste — medications, price-based, multilingual (FHIR). |
| Tax points | Tariff value expressed in points (multiplied by a point value for a price). |
| pgvector | PostgreSQL extension for vector similarity search. |
| Adaptive API | A serving interface that matches a consumer's preferred format (JSON/XML/…). |
