# BAG ePL (Spezialitätenliste) test fixture

`foph-sl-export-20260601_fixture.ndjson` is a deterministic, **content-verbatim**
slice of the real BAG ePL FHIR R5 bulk export, built by `make_fixture.py`.

| | |
|---|---|
| Source (manifest API) | https://epl.bag.admin.ch/api/sl/public/resources/current → `.fhir.fileUrl` (relative to https://epl.bag.admin.ch/static/) |
| Raw file | `foph-sl-export-20260601.ndjson` (gitignored, lives at repo-root `data/raw/epl/`) |
| Fetch date | 2026-06-11 |
| Full-export SHA-256 | `2dece0dad13f1f54b33c4bb41044ee8bda85b2dc2103108f7462605af916ca18` |
| Full export | 6 763 bundles · 10 408 reimbursed packages (10 299 GTIN-keyable, 109 unkeyable) · ~93 MB · licence CC0-1.0 |

## Trim rule (exact, deterministic)

Selected line indices are the **union, in original file order**, of:

1. the **first 200 bundles** (the bulk happy path);
2. **every** bundle whose `MedicinalProductDefinition` carries **no ATC code**
   (`classification[].coding[].system == http://www.whocc.no/atc` absent) — the real
   `ai_map` category gap (55 such bundles export-wide);
3. the **first multi-package** bundle (>1 `PackagedProductDefinition`);
4. the **first** bundle with `ClinicalUseDefinition` entries (SL Limitationen);
5. the **first** bundle with an SL `priceModel = true` sub-extension;
6. the **first** bundle with an SL `expiryDate` sub-extension.

Bundle JSON is **never mutated** — only whole lines are selected. Re-running
`make_fixture.py` against the same raw file produces a byte-identical fixture.

## Fixture record counts

| | |
|---|---|
| Bundles | 255 |
| Size | ~2.9 MB |
| Reimbursed-package rows (FOPH `RegulatedAuthorization`, type `756000002003`) | 321 |
| GTIN-keyable rows (emit a `TariffRecord`) | 310 |
| Unkeyable packages (PPD without `packaging` → `parse_failures`, no record) | 11 (across 9 bundles) |
| Duplicate GTINs | 0 |

The 11 unkeyable packages are real fail-closed cases: the `PackagedProductDefinition`
is present and referenced by a reimbursement authorisation, but has no
`packaging.identifier` (no GTIN), so no frozen record can be keyed — the pipeline
counts them in `PipelineReport.parse_failures` and emits no row.
