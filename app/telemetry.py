from __future__ import annotations

import os

from fastapi import FastAPI, Response
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

_configured = False


def setup_telemetry(app: FastAPI, service_name: str) -> None:
    """Wire OTEL tracing + Prometheus metrics into a FastAPI app.

    Idempotent: safe to call multiple times (noop after first call).
    Set OTEL_SDK_DISABLED=true to skip entirely (useful in tests).
    """
    global _configured
    if _configured or os.getenv("OTEL_SDK_DISABLED", "").lower() == "true":
        return
    _configured = True

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    resource = Resource.create({SERVICE_NAME: service_name})

    # Tracing — send spans to OTEL Collector via gRPC
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    # Metrics — expose in Prometheus pull format on /metrics
    prefix = service_name.replace("-", "_")
    reader = PrometheusMetricReader(prefix=prefix)
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)

    # Auto-instrument FastAPI (HTTP spans), httpx (outgoing calls), asyncpg (DB queries)
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="/metrics,/health",
        server_request_hook=None,
    )
    HTTPXClientInstrumentor().instrument()
    AsyncPGInstrumentor().instrument()

    @app.get("/metrics", include_in_schema=False)
    def prometheus_metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
