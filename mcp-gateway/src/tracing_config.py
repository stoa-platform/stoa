"""OpenTelemetry distributed tracing configuration (CAB-1088).

Bridges structlog context with OTel spans, enabling end-to-end
distributed tracing across STOA components (Gateway → CP-API → backends).

When `otlp_endpoint` is set, spans are exported via OTLP gRPC
to Grafana Alloy, which forwards them to Tempo.
"""

import logging

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


def configure_tracing(app, settings) -> None:  # type: ignore[no-untyped-def]
    """Configure OpenTelemetry tracing with OTLP export.

    Call this after FastAPI app creation but before adding middleware.
    Auto-instruments FastAPI, httpx, and SQLAlchemy.
    """
    endpoint = settings.otlp_endpoint
    if not endpoint:
        logger.info("OTel tracing disabled (otlp_endpoint not set)")
        return

    resource = Resource.create({
        "service.name": settings.otlp_service_name,
        "service.version": settings.app_version,
        "deployment.environment": settings.environment,
    })

    provider = TracerProvider(resource=resource)

    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Auto-instrument FastAPI (creates spans for every request)
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)

    # Auto-instrument httpx (traces outgoing HTTP calls to CP-API, Keycloak, etc.)
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()

    # Auto-instrument SQLAlchemy (traces DB queries)
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument()

    logger.info("OTel tracing enabled, exporting to %s", endpoint)


def get_current_trace_id() -> str | None:
    """Get the current trace_id from the active OTel span.

    Used by metrics middleware to attach exemplars and by
    structlog processors to inject trace_id into log lines.
    """
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.trace_id != 0:
        return format(ctx.trace_id, "032x")
    return None


def shutdown_tracing() -> None:
    """Flush and shut down the tracer provider. Call on app shutdown."""
    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()
