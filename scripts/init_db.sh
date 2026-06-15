#!/usr/bin/env bash
#
# Apply the tarifhub schema + migrations to a running PostgreSQL (pgvector).
# Start the DB first:  docker-compose up -d db
#
set -euo pipefail

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-tarifhub}"
PGDATABASE="${PGDATABASE:-tarifhub}"
export PGPASSWORD="${PGPASSWORD:-tarifhub}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Applying migrations to ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"
for migration in "$ROOT"/db/migrations/*.sql; do
  echo "  -> $(basename "$migration")"
  psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -v ON_ERROR_STOP=1 -f "$migration"
done
echo "Schema is up to date."
