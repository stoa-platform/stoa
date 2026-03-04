"""Tests for TenantSpanProcessor — enriches OTel spans with tenant_id."""

from unittest.mock import MagicMock, patch

import structlog

from src.tracing_config import TenantSpanProcessor, configure_tracing


class TestTenantSpanProcessor:
    """TenantSpanProcessor reads tenant_id from structlog contextvars."""

    def setup_method(self):
        structlog.contextvars.clear_contextvars()
        self.processor = TenantSpanProcessor()

    def teardown_method(self):
        structlog.contextvars.clear_contextvars()

    def test_on_start_sets_tenant_id_when_present(self):
        structlog.contextvars.bind_contextvars(tenant_id="acme-corp")
        span = MagicMock()

        self.processor.on_start(span)

        span.set_attribute.assert_called_once_with("tenant.id", "acme-corp")

    def test_on_start_no_op_when_no_tenant(self):
        span = MagicMock()

        self.processor.on_start(span)

        span.set_attribute.assert_not_called()

    def test_on_start_ignores_other_context_vars(self):
        structlog.contextvars.bind_contextvars(request_id="req-123", user_id="u-1")
        span = MagicMock()

        self.processor.on_start(span)

        span.set_attribute.assert_not_called()

    def test_force_flush_returns_true(self):
        assert self.processor.force_flush() is True

    def test_shutdown_is_noop(self):
        self.processor.shutdown()  # should not raise

    def test_on_end_is_noop(self):
        span = MagicMock()
        self.processor.on_end(span)  # should not raise


class TestConfigureTracingIntegration:
    """Verify configure_tracing wires TenantSpanProcessor into the provider."""

    def test_provider_has_tenant_processor(self):
        from opentelemetry import trace as otel_trace

        settings = MagicMock()
        settings.LOG_TRACE_EXPORT_ENDPOINT = "http://localhost:4317"
        settings.VERSION = "test"
        settings.ENVIRONMENT = "test"

        app = MagicMock()

        with (
            patch(
                "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter",
                return_value=MagicMock(),
            ),
            patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor"),
            patch("opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor"),
            patch("opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor"),
        ):
            configure_tracing(app, settings)

        provider = otel_trace.get_tracer_provider()
        # Provider should have both TenantSpanProcessor and BatchSpanProcessor
        processor_types = [type(sp).__name__ for sp in provider._active_span_processor._span_processors]
        assert "TenantSpanProcessor" in processor_types
        assert "BatchSpanProcessor" in processor_types

        # Cleanup: reset global tracer provider
        otel_trace.set_tracer_provider(None)
