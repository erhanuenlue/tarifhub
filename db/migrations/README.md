# db/migrations

Ordered, forward-only SQL migrations: the authoritative DDL for the tarifhub
database. `001_init.sql` is the baseline of this greenfield schema. The schema is
single-version so far, so the baseline is deliberately the only migration; the
next file appears when the schema actually changes, never before.

Conventions:

- **Forward-only.** A schema change lands as a new `NNN_name.sql` file. The
  executable SQL of an applied migration is never changed
  (`.claude/rules/python-services.md`); fixing a mistake costs a new migration.
  Comment-only clarifications must keep the non-comment SQL byte-identical.
- **Filename order is application order.** `scripts/init_db.sh` applies
  `db/migrations/*.sql` in glob order against a running Postgres, and the compose
  files mount each migration into `/docker-entrypoint-initdb.d/` (currently
  `001_init.sql` as `01_init.sql`).
- **Idempotent DDL.** Every statement guards with `IF NOT EXISTS`, because the
  compose entrypoint applies the `db/schema.sql` snapshot first (`00_schema.sql`)
  and the migrations afterwards, and `init_db.sh` may re-run against an existing
  database.
- **`db/schema.sql` is the consolidated current-state snapshot** of this chain,
  updated in the same PR as the migration that changes it. CI's `python-parity`
  job and the Postgres-enabled parity test harnesses apply the snapshot as one
  file; the offline default suite runs against the SQLite mirror provisioned by
  the ingestion service, not by these files.
