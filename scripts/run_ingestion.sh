#!/usr/bin/env bash
#
# Run the ingestion service locally (FastAPI on :8000). Creates a venv and installs
# the package on first run. Defaults to offline SQLite — no Postgres or LLM required.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/services/ingestion"

if [ ! -d .venv ]; then
  echo "Creating virtualenv and installing tarifhub-ingest ..."
  python3 -m venv .venv
  # shellcheck disable=SC1091
  . .venv/bin/activate
  pip install --upgrade pip >/dev/null
  pip install -e .
else
  # shellcheck disable=SC1091
  . .venv/bin/activate
fi

echo "Serving on http://localhost:8000  (POST /ingest/sample to load the bundled samples)"
exec uvicorn tarifhub_ingest.main:app --host 0.0.0.0 --port 8000 "$@"
