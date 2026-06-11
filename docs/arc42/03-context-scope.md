# 03 · context scope

> Stub — populated in Block 0 (prompts/02) from the Architecture baseline v2.1 (`tarifhub-fable5/03_Architecture/`). On Option A, replace this stub with the existing repo chapter, then refresh per v2.1.

## External data sources (L0 ingestion)

The L0 ingestion layer harmonises public Swiss ambulatory tariff publications into the
canonical `TariffRecord`. Each source is wired as an adapter (format reader) feeding the
deterministic mapper. Raw artifacts live under `data/raw/` (gitignored — never committed);
their SHA-256 is recorded so a grader can verify provenance from the code/docs alone.

| Source | Format | URL | Update cadence | Licence / re-use | Raw artifact |
| --- | --- | --- | --- | --- | --- |
| BAG Analysenliste (EAL) | XLSX, 3 sheets DE/FR/IT | https://www.bag.admin.ch/de/analysenliste-al | updates ~semiannual (1.1 / 1.7) + Vorpublikationen | Swiss federal publication, free re-use with attribution | raw artifact `data/raw/eal/` (gitignored), sha256 recorded |
