# ADR-023: Compare AL editions in ingestion, against their hash-verified full lists

*Status: Accepted · Date: 2026-10-30 · Decider: Erhan (+ AI-assisted analysis)*

## Context
The Change Analyst needs the positions added, removed or changed between two AL editions. Stored rows alone cannot prove an edition complete: a partial run that names the edition, or a file that follows the filename convention, stamps the same `valid_from` and `source_version` as a full manifest import, and a per-code `version` is no edition. Serving may import only `models` and `embeddings` from ingestion, and its image holds no workbooks. The frozen record carries only some of the workbook's columns.

## Decision
We compare two AL editions read-only in ingestion (`compare_editions`, CLI `--manifest ... --compare FROM TO`), refuse unless both stored editions equal their SHA-256-verified full lists under the import's own member rule, compare only the fields the frozen record carries, and name every other workbook column in the result.

## Alternatives weighed
- **A serving endpoint over the stored rows**: cannot tell an unfinished import from a real absence.
- **A stored completeness marker per edition**: a schema change, not needed while the workbooks are local.
- **Comparing the two workbooks without the database**: loses the frozen `record_hash` of each position.
- **Carrying more workbook columns first**: moves every EAL `record_hash`; a decision of its own.

## Consequences
- (+) A removed position is never inferred from a short or failed import, every entry cites frozen record hashes and the pinned BAG documents, and repeated runs give byte-identical output.
- (-) The comparison needs the git-ignored workbooks locally, as the import does. Limitations, remarks, cumulability and laboratory flags are not compared; on the 2026 editions far more positions differ only there than in the compared fields ([evidence](../evidence/2026-10-30-al-edition-comparison.md)), so the result is not every change BAG published. Revisit when those columns enter the record or when an HTTP or MCP surface is needed.

*Update 2026-10-30: since [ADR-024](024-al-workbook-text.md), the comparison also lists the literal text changes of `Limitationen`, `Bemerkungen`, `Kumulierbarkeit` and the laboratory flags of the German sheet, read from the verified workbooks; the classification by the compared fields and its counts are unchanged.*
