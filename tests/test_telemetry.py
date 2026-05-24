"""Tests for OTEL telemetry wiring — /metrics endpoint and trace log patcher."""
from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from app.logging import _add_trace_context
from app.telemetry import setup_telemetry


@pytest.fixture()
def telemetry_app() -> FastAPI:
    """Minimal FastAPI app with telemetry wired — isolated from the global flag."""
    import app.telemetry as tel_module
    # Reset global so setup_telemetry actually runs for this test app
    tel_module._configured = False
    os.environ.pop("OTEL_SDK_DISABLED", None)
    app_ = FastAPI()
    setup_telemetry(app_, "test-service")
    yield app_
    # Restore so subsequent tests that import main.py aren't affected
    tel_module._configured = False


def test_metrics_endpoint_returns_200(telemetry_app: FastAPI) -> None:
    client = TestClient(telemetry_app)
    response = client.get("/metrics")
    assert response.status_code == 200


def test_metrics_content_type_is_prometheus(telemetry_app: FastAPI) -> None:
    client = TestClient(telemetry_app)
    response = client.get("/metrics")
    assert "text/plain" in response.headers["content-type"]


def test_metrics_body_contains_help_lines(telemetry_app: FastAPI) -> None:
    client = TestClient(telemetry_app)
    # Generate traffic so OTEL emits at least one metric
    client.get("/nonexistent")
    response = client.get("/metrics")
    assert b"# HELP" in response.content


def test_trace_patcher_defaults_outside_span() -> None:
    record: dict = {"extra": {}}
    _add_trace_context(record)
    assert record["extra"]["otelTraceID"] == "0" * 32
    assert record["extra"]["otelSpanID"] == "0" * 16
    assert record["extra"]["otelTraceSampled"] is False


def test_trace_patcher_injects_real_ids_inside_span() -> None:
    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("test")

    with tracer.start_as_current_span("test-span"):
        record: dict = {"extra": {}}
        _add_trace_context(record)

    assert record["extra"]["otelTraceID"] != "0" * 32
    assert len(record["extra"]["otelTraceID"]) == 32
    assert len(record["extra"]["otelSpanID"]) == 16


def test_otel_disabled_env_var_skips_setup() -> None:
    import app.telemetry as tel_module
    tel_module._configured = False
    os.environ["OTEL_SDK_DISABLED"] = "true"
    app_ = FastAPI()
    setup_telemetry(app_, "test-service")
    client = TestClient(app_)
    response = client.get("/metrics")
    assert response.status_code == 404  # endpoint was not registered
    del os.environ["OTEL_SDK_DISABLED"]
    tel_module._configured = False
