# syntax=docker/dockerfile:1
# TarifHub serving service (Python 3.12 + FastAPI). Read-only over frozen records.
# The canonical TariffRecord and the embedder come from the sibling ingestion package,
# which is vendored into the image so there is one canonical model end-to-end.

FROM python:3.12-slim AS runtime

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

# Non-root runtime.
RUN useradd --create-home --uid 1001 appuser
USER 1001

EXPOSE 8000
ENV TARIFHUB_DB_URL=postgresql://tarifhub:tarifhub@db:5432/tarifhub

ENTRYPOINT ["uvicorn", "tarifhub_serving.main:app", "--host", "0.0.0.0", "--port", "8000"]
