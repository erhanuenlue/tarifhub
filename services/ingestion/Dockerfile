# syntax=docker/dockerfile:1
# Multi-stage build for the tarifhub ingestion service (Python 3.12).

# --- builder: install into a self-contained virtualenv ---
# Base image pinned by digest 2026-06-11 (python:3.12-slim manifest-list digest).
FROM python:3.12-slim@sha256:a39549e211a16149edf74e5fdc9ef03a6767e46cd987c5048b6659b6c9904c94 AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only what is needed to resolve and install the package.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

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
