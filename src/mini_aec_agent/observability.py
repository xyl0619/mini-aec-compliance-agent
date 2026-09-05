"""OpenTelemetry setup for agent and API traces."""

from __future__ import annotations

from threading import Lock
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

from mini_aec_agent.config import Settings

_configured = False
_configuration_lock = Lock()


def configure_telemetry(settings: Settings) -> bool:
    """Configure an OTLP exporter, or a console exporter, when explicitly enabled."""

    global _configured
    if not settings.telemetry_enabled:
        return False
    with _configuration_lock:
        if _configured:
            return True

        provider = TracerProvider(
            resource=Resource.create({"service.name": settings.otel_service_name})
        )
        if settings.otel_endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint))
            )
        else:
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

        trace.set_tracer_provider(provider)
        _configured = True
    return True


def instrument_fastapi(app: Any, settings: Settings) -> bool:
    """Instrument one FastAPI app when telemetry is enabled."""

    if not configure_telemetry(settings):
        return False
    if getattr(app.state, "mini_aec_telemetry_instrumented", False):
        return True

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    app.state.mini_aec_telemetry_instrumented = True
    return True
