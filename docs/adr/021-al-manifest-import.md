# ADR-021: Import dated BAG AL editions from a hash-checked manifest, one transaction per batch

*Status: Accepted · Date: 2026-10-27 · Decider: Erhan (+ AI-assisted analysis)*

## Context
The Change Analyst compares BAG Analysenliste editions, so every frozen AL record must carry the effective date of its edition. The BAG file names carry no machine-readable date, the downloads are local and git-ignored, frozen rows cannot be rewritten, and the code below the freeze line (`versioning/`, `audit/`) must not change. A batch that stops half way, or that races another writer, must therefore never leave a partial or out-of-order edition behind.

## Decision
We import AL editions only through the tracked `data/manifests/bag-al.json`, through `import_manifest(path, conn, db)`:

- The manifest dates each edition and pins every document by repository path, SHA-256 and BAG URL. Every listed document is verified, and only the edition's full tariff list is parsed, from the verified bytes. The manifest supplies `valid_from` and `source_version` (`BAG AL YYYY-MM-DD`) before freeze.
- Unsafe batches are refused before any write: a hash mismatch, a newer or undated stored edition, or conflicting stored content.
- The batch is one transaction: the repository's and the unchanged audit logger's per-row commits are deferred, and any failure rolls everything back. If the rollback itself fails, the connection is closed.
- Manifest paths are NFC. Each path component is matched on disk by its NFC form, so macOS NFD names are found on any file system, and names that differ only in normalisation are refused as ambiguous.

## Alternatives weighed
- **Dates from file names or folders**: the BAG names carry no date, and a renamed or moved copy would change a record's identity.
- **Per-row commits with resume**: a failure or a competing writer leaves committed partial editions, which frozen rows cannot undo.
- **A transaction-aware audit logger**: the audit module is below the freeze line.
- **Renaming the downloads to NFC**: alters the original files; the lookup accepts either form instead.

## Consequences
- (+) An edition's identity does not depend on local file names; a re-import is idempotent; a refused or failed batch writes no tariff or audit row.
- (+) No change below the freeze line, no schema change, no new canonical field. The verification record is [2026-10-27 AL manifest import](../evidence/2026-10-27-al-manifest-import.md).
- (-) The import holds one write transaction for the whole batch (on SQLite other writers wait), and a caller must pass a connection without uncommitted writes of its own.
- (-) Under Postgres READ COMMITTED, a non-colliding row from another writer can still land between the final re-check and the commit. Revisit with a table lock or SERIALIZABLE when concurrent AL imports become real.
- (-) Postgres writes need the e5 embedder (`vector(1024)`). Stored codes stay as the workbook gives them (`4700`), so lookup aliases (`4700.00`), an edition-wide change list and RAG are separate decisions.
