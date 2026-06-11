# syntax=docker/dockerfile:1
# Multi-stage build for the TarifHub MCP server (Python 3.12).

# --- builder: install into a self-contained virtualenv ---
# Base image pinned by digest 2026-06-11 (python:3.12-slim manifest-list digest).
FROM python:3.12-slim@sha256:a39549e211a16149edf74e5fdc9ef03a6767e46cd987c5048b6659b6c9904c94 AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md ./
COPY server.py config.py ./
RUN pip install --upgrade pip && pip install .

# --- runtime: minimal image, non-root ---
# Base image pinned by digest 2026-06-11 (python:3.12-slim manifest-list digest).
FROM python:3.12-slim@sha256:a39549e211a16149edf74e5fdc9ef03a6767e46cd987c5048b6659b6c9904c94 AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MCP_TRANSPORT="streamable-http" \
    MCP_HOST="0.0.0.0" \
    MCP_PORT="8090" \
    SERVING_BASE_URL="http://tarifhub-serving:8080"

RUN useradd --create-home --uid 10001 tarifmcp

COPY --from=builder /opt/venv /opt/venv
COPY server.py config.py /app/

USER tarifmcp
WORKDIR /app
EXPOSE 8090

# Exposes the read-only tools over MCP streamable-HTTP. Set MCP_TRANSPORT=stdio to run
# as a local stdio server for a single agent instead.
CMD ["python", "server.py"]
