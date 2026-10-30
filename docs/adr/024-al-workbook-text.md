# ADR-024: Compare selected uncarried AL columns as published text, read from the verified workbooks

*Status: Accepted · Date: 2026-10-30 · Decider: Erhan (+ AI-assisted analysis)*

## Context
The edition comparison ([ADR-023](023-al-edition-comparison.md)) classifies positions only by the fields the frozen record carries, and on the 2026 editions 161 positions differ only in German columns it does not carry, among them a new limitation (1474.1) and a cumulation cap lowered from 18 to 13 tax points a day (4707.1, 4707.2). Carrying these columns into the record moves every EAL `record_hash` and changes `HASHED_FIELDS` below the freeze line; storing them beside the records is a schema change and a new write path. A cell's text does not say whether its change is editorial or substantive: for 1762, `Oui` became `Ja` while the French and Italian cells and BAG's change date stayed the same.

## Decision
We read `Limitationen`, `Bemerkungen`, `Kumulierbarkeit` and the 21 laboratory flags of the German sheet (the ten columns for the laboratories of Article 54 KVV and the eleven practice-laboratory titles; not the prescriber flags), with their cell references, from each edition's SHA-256-verified full-list bytes at comparison time, compare their texts after Unicode NFC and whitespace folding only, and list each literal change once in a `workbook_text` section beside the unchanged classification, stating which columns could be compared.

## Alternatives weighed
- **Carry the columns into the canonical record**: a canonical-field change ([ADR-003](003-canonical-record-model.md)) below the freeze line that moves every EAL `record_hash`.
- **Store the texts at import, beside the records**: a schema change and an import write path for values nothing serves.
- **Count a text change as a changed position**: a position would be changed while its frozen records are identical.
- **Interpret the values** (`Oui` read as `Ja`, an edit labelled editorial or substantive): a claim the workbook does not make.
- **Refuse when a requested column cannot be read**: a renamed BAG header would also block the frozen-field comparison; the column is reported as not comparable instead, and with no readable column nothing is counted.
- **An opt-in flag for the section**: a second output shape to keep and test, for a section read from bytes the comparison already verifies.

## Consequences
- (+) The 2026 text changes (161 positions, 174 cells, none of them a changed position) are listed with their cells in the hash-pinned workbooks, with no change to frozen records, hashes, schema, `as_of`, the classification or its counts; repeated runs stay byte-identical ([evidence](../evidence/2026-10-30-al-workbook-text.md)).
- (+) Coverage is explicit: the requested and the compared columns, each column an edition does not let the comparison read (missing, named by two headers, or holding a value that is not text), and no count at all when no column could be compared.
- (-) One cell holding a value that is not text excludes its column from the comparison in both editions, and a position number written as a formula refuses the comparison, although the import reads the cell's cached value. With no readable column the comparison still succeeds for the compared fields (exit 0), its text section marked unavailable and nothing counted.
- (-) The texts are published, not frozen: they carry no `record_hash` and need the local workbooks, as the comparison already does. Only the German sheet's selected columns of positions listed in both editions are read: the other uncarried columns (the prescriber flags and BAG's change dates among them), the French and Italian texts, the texts of added and removed positions, cell formatting and the PDFs stay outside, so the result is still not every change BAG published. On the 2026 editions the JSON grows from 33 KB to 417 KB. Revisit when these columns enter the record or a serving surface needs them.
