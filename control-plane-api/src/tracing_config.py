"""OpenTelemetry distributed tracing configuration (CAB-1088).

Bridges structlog context (request_id, tenant_id) with OTel spans,
enabling end-to-end distributed tracing across STOA components.

When LOG_TRACE_EXPORT_ENDPOINT is set, spans are exported via OTLP gRPC
to Grafana Alloy, which forwards them to Tempo. Grafana then provides:
- Service Map (auto-generated from span data)
- Trace-to-Logs correlation (via trace_id in structlog JSON)
- Metrics-to-Traces correlation (via exemplars)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

if TYPE_CHECKING:
    from opentelemetry.context import Context
    from opentelemetry.sdk.trace import ReadableSpan, Span

logger = logging.getLogger(__name__)


class TenantSpanProcessor(SpanProcessor):
    """Enrich every span with tenant_id from structlog request context.

    Auth middleware binds tenant_id via structlog.contextvars.bind_contextvars().
    This processor reads it and sets the ``tenant.id`` span attribute so traces
    can be filtered per-tenant in Grafana Tempo.
    """

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        ctx = structlog.contextvars.get_contextvars()
        tenant_id = ctx.get("tenant_id")
        if tenant_id:
            span.set_attribute("tenant.id", tenant_id)

    def on_end(self, span: ReadableSpan) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def configure_tracing(app, settings) -> None:
    """Configure OpenTelemetry tracing with OTLP export.

    Call this after FastAPI app creation but before adding middleware.
    Auto-instruments FastAPI, httpx, and SQLAlchemy.
    """
    endpoint = settings.LOG_TRACE_EXPORT_ENDPOINT
    if not endpoint:
        logger.info("OTel tracing disabled (LOG_TRACE_EXPORT_ENDPOINT not set)")
        return

    resource = Resource.create(
        {
            "service.name": "control-plane-api",
            "service.version": settings.VERSION,
            "deployment.environment": settings.ENVIRONMENT,
        }
    )

    provider = TracerProvider(resource=resource)

    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(TenantSpanProcessor())
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Auto-instrument FastAPI (creates spans for every request)
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)

    # Auto-instrument httpx (traces outgoing HTTP calls to Keycloak, GitLab, gateway adapters, etc.)
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
