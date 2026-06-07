#!/usr/bin/env bash
#
# Run the Quarkus serving service in dev mode (live reload on :8080).
# Needs a reachable Postgres+pgvector:  docker-compose up -d db && ./scripts/init_db.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/services/serving"

echo "Starting Quarkus dev mode on http://localhost:8080 (Swagger UI at /q/swagger-ui)"
exec mvn quarkus:dev "$@"
