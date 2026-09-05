from __future__ import annotations

from dataclasses import replace
from typing import Any

from fastapi import FastAPI

import mini_aec_agent.observability as observability
from mini_aec_agent.config import get_settings


class FakeProvider:
    def __init__(self) -> None:
        self.processors: list[Any] = []

    def add_span_processor(self, processor: Any) -> None:
        self.processors.append(processor)


def test_telemetry_is_noop_when_disabled() -> None:
    settings = replace(get_settings(), telemetry_enabled=False)

    assert observability.configure_telemetry(settings) is False
    assert observability.instrument_fastapi(FastAPI(), settings) is False


def test_console_telemetry_is_configured_once(monkeypatch) -> None:
    provider = FakeProvider()
    installed: list[FakeProvider] = []
    monkeypatch.setattr(observability, "_configured", False)
    monkeypatch.setattr(observability, "TracerProvider", lambda resource: provider)
    monkeypatch.setattr(observability.trace, "set_tracer_provider", installed.append)
    settings = replace(get_settings(), telemetry_enabled=True, otel_endpoint=None)

    assert observability.configure_telemetry(settings) is True
    assert observability.configure_telemetry(settings) is True
    assert installed == [provider]
    assert len(provider.processors) == 1


def test_otlp_telemetry_uses_configured_endpoint(monkeypatch) -> None:
    from opentelemetry.exporter.otlp.proto.http import trace_exporter

    provider = FakeProvider()
    exporters: list[str] = []
    monkeypatch.setattr(observability, "_configured", False)
    monkeypatch.setattr(observability, "TracerProvider", lambda resource: provider)
    monkeypatch.setattr(observability.trace, "set_tracer_provider", lambda value: None)
    monkeypatch.setattr(
        trace_exporter,
        "OTLPSpanExporter",
        lambda endpoint: exporters.append(endpoint) or "exporter",
    )
    monkeypatch.setattr(
        observability,
        "BatchSpanProcessor",
        lambda exporter: ("batch", exporter),
    )
    settings = replace(
        get_settings(),
        telemetry_enabled=True,
        otel_endpoint="http://collector:4318/v1/traces",
    )

    assert observability.configure_telemetry(settings) is True
    assert exporters == ["http://collector:4318/v1/traces"]
    assert provider.processors == [("batch", "exporter")]


def test_fastapi_instrumentation_runs_when_enabled(monkeypatch) -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    app = FastAPI()
    instrumented: list[FastAPI] = []
    monkeypatch.setattr(observability, "configure_telemetry", lambda settings: True)
    monkeypatch.setattr(FastAPIInstrumentor, "instrument_app", instrumented.append)

    assert observability.instrument_fastapi(app, get_settings()) is True
    assert instrumented == [app]
