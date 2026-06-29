# ADR-007: S3-compatible object store for raw source artifacts

*Status: Accepted · Date: 2026-06-11 · Decider: Erhan (+ AI-assisted analysis)*

## Context
Lineage requires keeping the exact bytes ingested: a frozen record is only fully auditable if the source file it came from can be replayed. Raw artifacts (PDF/XLSX/XML/CSV dumps from 20+ sources) are cold, sometimes large, and immutable once fetched: a different access pattern from the hot relational data in ADR-006.

## Decision
We store immutable raw source artifacts in S3-compatible object storage (MinIO in local dev via a compose profile, Exoscale SOS in production) and reference each artifact from the append-only `audit_log`.

## Alternatives weighed
- **In-DB BLOBs (`bytea`)**: bloats the Postgres backup and WAL with cold data, couples artifact retention to database sizing, and slows dump/restore for no relational benefit.
- **Host filesystem paths**: not durable or portable across containers and cluster nodes. A path is not a verifiable reference.

## Consequences
- (+) Full replay from source bytes to frozen record. The audit chain starts at the artifact, not at the parser. CH-resident in production (Exoscale SOS), with local parity via the MinIO compose profile.
- (-) One more infrastructure component and credential set. The database cannot enforce referential integrity into the bucket, so revisit (add a consistency-check job) when the first artifact-reference mismatch surfaces.
- (-) Honest status: the MinIO dev profile exists in `deploy/docker-compose.yml` today. The production wiring (Exoscale SOS, `audit_log` artifact references) is designed, not yet built.

*Lineage: new.*
