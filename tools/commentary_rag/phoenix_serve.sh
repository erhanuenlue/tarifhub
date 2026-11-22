#!/bin/sh
# Start a local Arize Phoenix for the commentary pilot's tracing demo (trace_demo.py).
# Reuses an installed Phoenix 20.26 (PHOENIX_PYTHON: the Python of that installation) and keeps
# TarifHub's own storage in tools/commentary_rag/local/phoenix (git-ignored). Loopback only: the
# UI, REST API and OTLP/HTTP listen on 127.0.0.1:6016, and the gRPC receiver, which Phoenix 20.26
# binds to all interfaces whatever PHOENIX_HOST says, is disabled. Auth is off, so it must stay
# local. No provider key reaches the process. Stop it with Ctrl-C (or kill its PID).
set -eu
: "${PHOENIX_PYTHON:?set PHOENIX_PYTHON to the python of an installed Phoenix 20.26}"
[ -x "$PHOENIX_PYTHON" ] || { echo "refused: $PHOENIX_PYTHON is not executable" >&2; exit 3; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STORE="$ROOT/tools/commentary_rag/local/phoenix"
mkdir -p "$STORE"
cd "$STORE"
exec env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u OPENAI_API_KEY \
  PHOENIX_WORKING_DIR="$STORE" PHOENIX_SQL_DATABASE_URL="sqlite:///$STORE/phoenix.db" \
  PHOENIX_HOST=127.0.0.1 PHOENIX_PORT=6016 PHOENIX_ENABLE_AUTH=false \
  PHOENIX_ALLOW_EXTERNAL_RESOURCES=false PHOENIX_ENABLE_PROMETHEUS=false \
  PHOENIX_ENABLE_MCP_SERVER=false PHOENIX_DISABLE_AGENT_ASSISTANT=true \
  PHOENIX_AGENTS_DISABLE_BASH=true DO_NOT_TRACK=1 \
  "$PHOENIX_PYTHON" -c 'import sys
import phoenix.server.app as app
original = app.GrpcServer
def http_only(*args, **kwargs):
    kwargs["disabled"] = True
    return original(*args, **kwargs)
app.GrpcServer = http_only
from phoenix.server.main import main
sys.argv = ["phoenix", "serve"]
main()'
