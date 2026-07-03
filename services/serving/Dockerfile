# syntax=docker/dockerfile:1
# tarifhub serving service (Python 3.12 + FastAPI). Read-only over frozen records.
# The canonical TariffRecord and the embedder come from the sibling ingestion package,
# which is vendored into the image so there is one canonical model end-to-end.

# Base image pinned by digest 2026-06-11 (python:3.12-slim manifest-list digest).
FROM python:3.12-slim@sha256:a39549e211a16149edf74e5fdc9ef03a6767e46cd987c5048b6659b6c9904c94 AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# The serving package depends on ../ingestion (path dependency). Copy both so the
# editable/local install can resolve the canonical model + embedder.
COPY services/ingestion /app/services/ingestion
COPY services/serving /app/services/serving

RUN pip install --no-cache-dir /app/services/ingestion \
    && pip install --no-cache-dir /app/services/serving

# Opt-in real multilingual-e5 embedder (1024-dim), build-arg gated. With WITH_E5 unset
# or 0 this layer is a no-op and the image is functionally identical to the default; the
# search path keeps falling back to the offline stub. Installs sentence-transformers ONLY
# (matching the `ai` extra's version bound) into the same environment the app runs from —
# NEVER the LLM client; the serving value path must stay LLM-client-free (AST boundary test).
ARG WITH_E5=0
RUN if [ "$WITH_E5" = "1" ]; then pip install --no-cache-dir "sentence-transformers>=2.7"; fi

# Non-root runtime.
RUN useradd --create-home --uid 1001 appuser
USER 1001

EXPOSE 8000
ENV TARIFHUB_DB_URL=postgresql://tarifhub:tarifhub@db:5432/tarifhub

ENTRYPOINT ["uvicorn", "tarifhub_serving.main:app", "--host", "0.0.0.0", "--port", "8000"]
