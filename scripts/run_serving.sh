#!/usr/bin/env bash
#
# Run the TarifHub serving service (FastAPI) in dev mode with live reload on :8000.
# Offline by default (SQLite). For Postgres+pgvector (enables semantic search):
#   docker compose up -d db && export TARIFHUB_DB_URL=postgresql://tarifhub:tarifhub@localhost:5432/tarifhub
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/services/serving"

uv sync --extra dev

echo "Starting FastAPI dev server on http://localhost:8000 (Swagger UI at /docs)"
exec uv run uvicorn tarifhub_serving.main:app --host 0.0.0.0 --port 8000 --reload "$@"
