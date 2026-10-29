# syntax=docker/dockerfile:1
# tarifhub serving service (Python 3.12 + FastAPI). Read-only over frozen records.
# The canonical TariffRecord and the embedder come from the sibling ingestion package,
# which is vendored into the image so there is one canonical model end-to-end.

# --- uv: installs exactly what uv.lock pins (hash-checked, never re-resolved) ---
# Image pinned by digest 2026-10-29 (ghcr.io/astral-sh/uv 0.13.6 index digest).
FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv

# Base image pinned by digest 2026-06-11 (python:3.12-slim manifest-list digest).
FROM python:3.12-slim@sha256:a39549e211a16149edf74e5fdc9ef03a6767e46cd987c5048b6659b6c9904c94 AS runtime

# The app runs from the venv on PATH; uv builds it on the base image's Python (never a
# downloaded one), byte-compiled at install time.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# The serving package depends on ../ingestion (path dependency). Copy both projects'
# build inputs so the install can build the canonical model + embedder; the build context
# is the repository root, narrowed by Dockerfile.dockerignore.
COPY services/ingestion/pyproject.toml services/ingestion/README.md /app/services/ingestion/
COPY services/ingestion/src /app/services/ingestion/src
COPY services/serving/pyproject.toml services/serving/uv.lock services/serving/README.md /app/services/serving/
COPY services/serving/src /app/services/serving/src

# --locked installs the committed lockfile as is and fails, instead of re-resolving, when it
# no longer matches pyproject.toml; both packages install non-editable. uv is mounted for
# the install only, so it does not ship in this single-stage image.
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --project /app/services/serving

# Opt-in real multilingual-e5 embedder (1024-dim), build-arg gated. With WITH_E5 unset
# or 0 this layer is a no-op and the image is functionally identical to the default; the
# search path keeps falling back to the offline stub. Installs the `e5` extra ONLY
# (ingestion's sentence-transformers, as uv.lock pins it) into the same environment the
# app runs from, NEVER the LLM client; the serving value path must stay LLM-client-free
# (AST boundary test).
ARG WITH_E5=0
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    if [ "$WITH_E5" = "1" ]; then \
        uv sync --locked --no-editable --extra e5 --project /app/services/serving; \
    fi

# Non-root runtime.
RUN useradd --create-home --uid 1001 appuser
USER 1001

EXPOSE 8000
ENV TARIFHUB_DB_URL=postgresql://tarifhub:tarifhub@db:5432/tarifhub

ENTRYPOINT ["uvicorn", "tarifhub_serving.main:app", "--host", "0.0.0.0", "--port", "8000"]
