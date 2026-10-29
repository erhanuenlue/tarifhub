# syntax=docker/dockerfile:1
# Multi-stage build for the tarifhub MCP server (Python 3.12).

# --- uv: installs exactly what uv.lock pins (hash-checked, never re-resolved) ---
# Image pinned by digest 2026-10-29 (ghcr.io/astral-sh/uv 0.13.6 index digest).
FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv

# --- builder: install the locked dependency set into a self-contained virtualenv ---
# Base image pinned by digest 2026-06-11 (python:3.12-slim manifest-list digest).
FROM python:3.12-slim@sha256:a39549e211a16149edf74e5fdc9ef03a6767e46cd987c5048b6659b6c9904c94 AS builder

COPY --from=uv /uv /bin/uv
# The venv sits where the runtime stage expects it, on the base image's Python (never a
# downloaded one), byte-compiled at install time.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /build

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
# --frozen, not --locked: the lock's dev extra points at ../serving and ../ingestion, which
# this build context does not contain, so uv cannot re-check the lock against them here.
# The install still takes exactly what uv.lock pins and never re-resolves; the CI images
# job runs `uv lock --check` for every service before it builds. --no-editable: the
# runtime stage copies only the venv.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-editable

# --- runtime: minimal image, non-root ---
# Base image pinned by digest 2026-06-11 (python:3.12-slim manifest-list digest).
FROM python:3.12-slim@sha256:a39549e211a16149edf74e5fdc9ef03a6767e46cd987c5048b6659b6c9904c94 AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MCP_TRANSPORT="streamable-http" \
    MCP_HOST="0.0.0.0" \
    MCP_PORT="8090" \
    SERVING_BASE_URL="http://tarifhub-serving:8000"

RUN useradd --create-home --uid 10001 tarifmcp

# The package is installed into the venv (src/ layout), so the runtime stage carries
# no loose source files; the console script is the single entry point.
COPY --from=builder /opt/venv /opt/venv

USER tarifmcp
WORKDIR /app
EXPOSE 8090

# Exposes the read-only tools over MCP streamable-HTTP. Set MCP_TRANSPORT=stdio to run
# as a local stdio server for a single agent instead.
CMD ["tarifhub-mcp"]
