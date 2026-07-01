"""Observe-only OpenTelemetry seam: spans + metrics, fully offline.

No network and no collector. The request path is instrumented in memory via an
``InMemorySpanExporter`` and an ``InMemoryMetricReader`` injected through the
``create_app`` factory, so we can assert a custom ``serving.search`` span and the
``serving.search.duration_ms`` histogram are produced without any exporter reaching
out. The no-op default (no ``OTEL_EXPORTER_OTLP_ENDPOINT``) is asserted directly on
``resolve_exporters`` so the offline suite provably installs nothing.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from tarifhub_ingest.models.tariff_model import TariffSystem
from tarifhub_serving import telemetry
from tarifhub_serving.main import create_app


def _histogram_count(metrics_data, name: str) -> int:
    """Sum the histogram data-point counts for the metric ``name`` in ``metrics_data``.

    Walks resource_metrics -> scope_metrics -> metrics and returns the total ``count``
    across every data point of the matching histogram (0 if the metric is absent).
    """

    total = 0
    for resource_metric in metrics_data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name != name:
                    continue
                for point in metric.data.data_points:
                    total += point.count
    return total


def _system_labels(metrics_data, name: str) -> set:
    """Collect the distinct ``system`` attribute values across the metric's data points."""

    labels = set()
    for resource_metric in metrics_data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name != name:
                    continue
                for point in metric.data.data_points:
                    labels.add(point.attributes.get("system"))
    return labels


def test_request_emits_span_and_metric_offline(seeded_db_url, monkeypatch):
    monkeypatch.setenv("TARIFHUB_DB_URL", seeded_db_url)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    span_exporter = InMemorySpanExporter()
    metric_reader = InMemoryMetricReader()
    app = create_app(
        telemetry_span_exporter=span_exporter, telemetry_metric_reader=metric_reader
    )

    client = TestClient(app)
    response = client.get("/api/v1/search?q=Grundkonsultation&limit=5")
    assert response.status_code == 200

    spans = span_exporter.get_finished_spans()
    assert spans, "expected at least one exported span"
    assert any(span.name == "serving.search" for span in spans), (
        f"no serving.search span among {[s.name for s in spans]}"
    )

    count = _histogram_count(metric_reader.get_metrics_data(), "serving.search.duration_ms")
    assert count >= 1, "expected at least one serving.search.duration_ms data point"

    # Cardinality guard: an unknown ?system= value must bucket to "other" rather than mint a
    # fresh time series per arbitrary input (an unauthenticated-API memory-growth vector
    # otherwise). The first search above used no filter, so it is labelled "all".
    client.get("/api/v1/search?q=Grundkonsultation&limit=5&system=DOESNOTEXIST")
    labels = _system_labels(metric_reader.get_metrics_data(), "serving.search.duration_ms")
    assert "other" in labels, f"unknown system must bucket to 'other', got {labels}"
    # The label ceiling is the full known-systems set (every TariffSystem value) plus the
    # "all" (unfiltered) and "other" (unknown) buckets, never one series per arbitrary input.
    assert labels <= {s.value for s in TariffSystem} | {"all", "other"}, (
        f"metric system labels must stay bounded, got {labels}"
    )


def test_exporter_is_noop_when_endpoint_unset(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    span_processor, metric_reader = telemetry.resolve_exporters()

    assert span_processor is None
    assert metric_reader is None


def test_exporter_configured_when_endpoint_set(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

    # No network happens at construction: the OTLP exporters open a connection only on
    # the first export, which never occurs in this test.
    span_processor, metric_reader = telemetry.resolve_exporters()

    assert span_processor is not None
    assert metric_reader is not None
