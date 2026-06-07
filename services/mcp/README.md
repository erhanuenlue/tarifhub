# TarifHub MCP server

A small **Model Context Protocol** server (Python, [FastMCP](https://modelcontextprotocol.io))
that exposes TarifHub to AI agents as **read-only** tools. Every tool is a thin proxy to
the deterministic Quarkus serving service and returns its frozen records verbatim.

## Tools

| Tool | Proxies to | Returns |
|---|---|---|
| `search_tariffs(query, system?, limit?)` | `GET /api/v1/search` | ranked hits over frozen records |
| `get_tariff(system, code)` | `GET /api/v1/tariffs/{system}/{code}` | one frozen record |
| `explain_crosswalk(code)` | `GET /api/v1/explain` | frozen records + optional EU-routed NL explanation |

## The determinism guarantee

This server has **no database, no model, and no arithmetic**. It cannot compute, round,
or invent a tariff value — it relays exactly what serving returns, and surfaces an error
when serving cannot answer rather than fabricating a result. The unit tests pin this
contract (mocked HTTP; assert verbatim passthrough and that a missing record raises).

## Run

```bash
cd services/mcp
python3 -m venv .venv && . .venv/bin/activate
pip install -e .

# Point at a running serving API and start the MCP server.
export SERVING_BASE_URL=http://localhost:8080
python server.py                 # streamable-HTTP on :8090 (MCP_PORT)

# Or run as a local stdio server for a single agent:
MCP_TRANSPORT=stdio python server.py
```

## Test

```bash
cd services/mcp && pytest -q     # fully offline; serving is mocked
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `SERVING_BASE_URL` | `http://localhost:8080` | deterministic serving API base URL |
| `MCP_TRANSPORT` | `streamable-http` | `streamable-http` (container) or `stdio` (local agent) |
| `MCP_HOST` / `MCP_PORT` | `0.0.0.0` / `8090` | bind address for the HTTP transport |
| `MCP_HTTP_TIMEOUT` | `10` | per-request timeout (seconds) |
