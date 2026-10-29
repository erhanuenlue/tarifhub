# syntax=docker/dockerfile:1
# Multi-stage build for the tarifhub ingestion service (Python 3.12).

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

# Copy only what is needed to install the package.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
# --locked installs the committed lockfile as is and fails, instead of re-resolving, when it
# no longer matches pyproject.toml. --no-editable: the runtime stage copies only the venv.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

# Opt-in real multilingual-e5 embedder (1024-dim), build-arg gated. With WITH_E5 unset
# or 0 this layer is a no-op and the image is functionally identical to the default.
# Installs the `e5` extra ONLY (sentence-transformers, as uv.lock pins it), NEVER the
# `ai` extra, which also bundles the LLM client; no LLM client may enter this image.
ARG WITH_E5=0
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$WITH_E5" = "1" ]; then uv sync --locked --no-editable --extra e5; fi

# --- runtime: minimal image, non-root ---
# Base image pinned by digest 2026-06-11 (python:3.12-slim manifest-list digest).
FROM python:3.12-slim@sha256:a39549e211a16149edf74e5fdc9ef03a6767e46cd987c5048b6659b6c9904c94 AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TARIFHUB_DB_URL="sqlite:////data/tarifhub.db"

RUN useradd --create-home --uid 10001 tarifhub \
    && mkdir -p /data && chown tarifhub:tarifhub /data

COPY --from=builder /opt/venv /opt/venv
COPY sample-data /app/sample-data

USER tarifhub
WORKDIR /app
EXPOSE 8000

# Serves the FastAPI app; the GET endpoints read frozen records, POST /ingest/sample
# runs the offline pipeline over the bundled sample sources.
CMD ["uvicorn", "tarifhub_ingest.main:app", "--host", "0.0.0.0", "--port", "8000"]
