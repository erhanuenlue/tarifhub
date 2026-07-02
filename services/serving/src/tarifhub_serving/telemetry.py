"""Observe-only OpenTelemetry seam for the L1 serving service.

This module instruments the FastAPI app so every request produces a server trace and
adds one custom span plus one histogram on the search path. It OBSERVES only: it never
reads, computes or mutates a billing value, and it imports no LLM client. Those
invariants are enforced statically by ``tests/test_serving_boundary.py`` (the
``opentelemetry`` package trips neither the forbidden-client rule nor the
ingestion-submodule rule, since its root module is ``opentelemetry``).

Exporting is opt-in through ``OTEL_EXPORTER_OTLP_ENDPOINT``: when it is unset (or an
empty string) no span processor or metric reader is installed at all, so the offline
test suite and CI run with a true no-op and need no collector. The providers built here
are app-local (never the global providers), so parallel apps and tests stay isolated.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
)

_SERVICE_NAME = "tarifhub-serving"
_INSTRUMENTATION_SCOPE = "tarifhub.serving"
SEARCH_LATENCY_METRIC = "serving.search.duration_ms"


@dataclass
class Telemetry:
    """Handles the search route uses to record its observe-only span + metric."""

    tracer: trace.Tracer
    search_latency: metrics.Histogram
    tracer_provider: TracerProvider
    meter_provider: MeterProvider


def resolve_exporters(
    *,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
) -> tuple[SpanProcessor | None, MetricReader | None]:
    """Decide which span processor and metric reader to install.

    An explicit override (the offline tests inject in-memory ones) always wins. Failing
    that, export over OTLP/HTTP only when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set to a
    non-empty value. An unset or empty endpoint yields ``(None, None)`` so nothing is
    exported and no collector is required.
    """

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or None

    if span_exporter is not None:
        span_processor: SpanProcessor | None = SimpleSpanProcessor(span_exporter)
    elif endpoint is not None:
        # Lazy import: the OTLP exporter is only needed when an endpoint is configured.
        # Importing it does no network I/O; a connection is opened on the first export.
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # noqa: PLC0415

        span_processor = BatchSpanProcessor(OTLPSpanExporter())
    else:
        span_processor = None

    if metric_reader is not None:
        reader: MetricReader | None = metric_reader
    elif endpoint is not None:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter  # noqa: PLC0415

        reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    else:
        reader = None

    return span_processor, reader


def setup_telemetry(
    app: FastAPI,
    *,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
) -> Telemetry:
    """Instrument ``app`` for observe-only tracing + metrics and return the handles.

    Builds app-local tracer/meter providers carrying ``service.name=tarifhub-serving``,
    wires the resolved exporter/reader (none when no endpoint is configured), then
    instruments every request via ``FastAPIInstrumentor`` and creates the search-latency
    histogram. The resulting ``Telemetry`` is stored on ``app.state.telemetry`` for the
    search route to record against.
    """

    resource = Resource.create({"service.name": _SERVICE_NAME})
    span_processor, reader = resolve_exporters(
        span_exporter=span_exporter, metric_reader=metric_reader
    )

    tracer_provider = TracerProvider(resource=resource)
    if span_processor is not None:
        tracer_provider.add_span_processor(span_processor)

    meter_provider = MeterProvider(
        resource=resource, metric_readers=[reader] if reader is not None else []
    )

    # Explicit providers keep spans/metrics on this app's readers rather than the global
    # (no-op) providers, so injected in-memory exporters capture them in the tests.
    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=tracer_provider, meter_provider=meter_provider
    )

    tracer = tracer_provider.get_tracer(_INSTRUMENTATION_SCOPE)
    meter = meter_provider.get_meter(_INSTRUMENTATION_SCOPE)
    search_latency = meter.create_histogram(
        name=SEARCH_LATENCY_METRIC,
        unit="ms",
        description="Observe-only wall-clock latency of the search embed+rank work.",
    )

    telemetry = Telemetry(
        tracer=tracer,
        search_latency=search_latency,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )
    app.state.telemetry = telemetry
    return telemetry
