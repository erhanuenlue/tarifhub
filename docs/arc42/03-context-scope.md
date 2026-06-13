# 03 · context scope

## Business context

The system boundary separates two roles. **L0** ingests public BAG publications (no other
upstream) and harmonises them into the canonical `TariffRecord`. **L1** serves the frozen
result read-only to three consumer classes: PIS/HIS systems (REST/FHIR), AI agents (MCP),
and console users (TarifGuard). **No patient data crosses the boundary** in either direction:
inputs are public federal tariff lists, outputs are frozen tariff records.

| Communication partner | Interface | Data exchanged | Use cases |
| --- | --- | --- | --- |
| BAG Analysenliste publication | XLSX download → EAL adapter | tariff positions, tax points, DE/FR/IT designations | UC-01 |
| BAG Spezialitätenliste / ePL | FHIR R5 NDJSON manifest → ePL adapter | reimbursed packages, retail prices CHF, trilingual names | UC-01 |
| Operator | CLI / scheduler | pipeline runs, `PipelineReport` | UC-01, UC-03 |
| Tariff expert | TarifGuard console | review queue, corrections | UC-02 |
| Practice user | TarifGuard console | lookup, labelled explanations | UC-08, UC-09 |
| PIS/HIS systems | REST/OpenAPI + FHIR R4 read | frozen tariff records, versions, diffs, search | UC-04, UC-05, UC-06 |
| AI agents | MCP (`search_tariffs`, `get_tariff`, `explain_crosswalk`, read-only) | frozen records verbatim | UC-07 |

## External data sources (L0 ingestion)

The L0 ingestion layer harmonises public Swiss ambulatory tariff publications into the
canonical `TariffRecord`. Each source is wired as an adapter (format reader) feeding the
deterministic mapper. Raw artifacts live under `data/raw/` (gitignored, never committed);
their SHA-256 is recorded so a grader can verify provenance from the code/docs alone.

| Source | Format | URL | Update cadence | Licence / re-use | Raw artifact |
| --- | --- | --- | --- | --- | --- |
| BAG Analysenliste (EAL) | XLSX, 3 sheets DE/FR/IT | https://www.bag.admin.ch/de/analysenliste-al | updates ~semiannual (1.1 / 1.7) + Vorpublikationen | Swiss federal publication, free re-use with attribution | raw artifact `data/raw/eal/` (gitignored), sha256 recorded |
| BAG Spezialitätenliste (SL) | FHIR R5 NDJSON (one `ch-idmp-bundle` per line) | https://epl.bag.admin.ch (manifest API → static file) | monthly, 1st | CC0-1.0 (public domain) | raw artifact `data/raw/epl/` (gitignored), sha256 recorded |
