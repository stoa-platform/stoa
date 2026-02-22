"""Tests for tracing_config module (CAB-1388)."""
from unittest.mock import MagicMock, patch

import pytest


class TestConfigureTracingDisabled:
    def test_returns_none_when_no_endpoint(self):
        from src.tracing_config import configure_tracing

        mock_settings = MagicMock()
        mock_settings.LOG_TRACE_EXPORT_ENDPOINT = None

        app = MagicMock()
        result = configure_tracing(app, mock_settings)
        assert result is None

    def test_returns_none_when_empty_endpoint(self):
        from src.tracing_config import configure_tracing

        mock_settings = MagicMock()
        mock_settings.LOG_TRACE_EXPORT_ENDPOINT = ""

        app = MagicMock()
        result = configure_tracing(app, mock_settings)
        assert result is None


def _make_otel_sys_modules():
    """Build sys.modules mocks for optional OTel packages not installed in dev."""
    mock_otlp_exporter_mod = MagicMock()
    mock_fastapi_instr_mod = MagicMock()
    mock_httpx_instr_mod = MagicMock()
    mock_sqla_instr_mod = MagicMock()
    return {
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": mock_otlp_exporter_mod,
        "opentelemetry.exporter.otlp.proto.grpc": mock_otlp_exporter_mod,
        "opentelemetry.exporter.otlp.proto": mock_otlp_exporter_mod,
        "opentelemetry.exporter.otlp": mock_otlp_exporter_mod,
        "opentelemetry.exporter": mock_otlp_exporter_mod,
        "opentelemetry.instrumentation.fastapi": mock_fastapi_instr_mod,
        "opentelemetry.instrumentation.httpx": mock_httpx_instr_mod,
        "opentelemetry.instrumentation.sqlalchemy": mock_sqla_instr_mod,
    }


class TestConfigureTracingEnabled:
    def test_sets_tracer_provider_when_endpoint_set(self):
        import sys
        from src.tracing_config import configure_tracing

        mock_settings = MagicMock()
        mock_settings.LOG_TRACE_EXPORT_ENDPOINT = "http://otel-collector:4317"
        mock_settings.VERSION = "1.0.0"
        mock_settings.ENVIRONMENT = "test"

        mock_provider = MagicMock()

        with patch.dict("sys.modules", _make_otel_sys_modules()):
            with patch("src.tracing_config.TracerProvider", return_value=mock_provider):
                with patch("src.tracing_config.BatchSpanProcessor", return_value=MagicMock()):
                    with patch("src.tracing_config.trace") as mock_trace:
                        app = MagicMock()
                        configure_tracing(app, mock_settings)
                        mock_trace.set_tracer_provider.assert_called_once_with(mock_provider)

    def test_calls_instrument_app(self):
        from src.tracing_config import configure_tracing

        mock_settings = MagicMock()
        mock_settings.LOG_TRACE_EXPORT_ENDPOINT = "http://otel-collector:4317"
        mock_settings.VERSION = "1.0.0"
        mock_settings.ENVIRONMENT = "test"

        mock_modules = _make_otel_sys_modules()
        mock_fastapi_instr = mock_modules["opentelemetry.instrumentation.fastapi"]
        mock_httpx_instr = mock_modules["opentelemetry.instrumentation.httpx"]
        mock_sqla_instr = mock_modules["opentelemetry.instrumentation.sqlalchemy"]

        with patch.dict("sys.modules", mock_modules):
            with patch("src.tracing_config.TracerProvider", return_value=MagicMock()):
                with patch("src.tracing_config.BatchSpanProcessor", return_value=MagicMock()):
                    with patch("src.tracing_config.trace"):
                        app = MagicMock()
                        configure_tracing(app, mock_settings)
                        # FastAPIInstrumentor.instrument_app called with app
                        mock_fastapi_instr.FastAPIInstrumentor.instrument_app.assert_called_once_with(
                            app
                        )
                        # HTTPXClientInstrumentor().instrument() called
                        mock_httpx_instr.HTTPXClientInstrumentor.return_value.instrument.assert_called_once()
                        # SQLAlchemyInstrumentor().instrument() called
                        mock_sqla_instr.SQLAlchemyInstrumentor.return_value.instrument.assert_called_once()


class TestGetCurrentTraceId:
    def test_returns_none_when_no_active_span(self):
        from src.tracing_config import get_current_trace_id

        mock_ctx = MagicMock()
        mock_ctx.trace_id = 0

        mock_span = MagicMock()
        mock_span.get_span_context.return_value = mock_ctx

        with patch("src.tracing_config.trace") as mock_trace:
            mock_trace.get_current_span.return_value = mock_span
            result = get_current_trace_id()
            assert result is None

    def test_returns_none_when_context_is_none(self):
        from src.tracing_config import get_current_trace_id

        mock_span = MagicMock()
        mock_span.get_span_context.return_value = None

        with patch("src.tracing_config.trace") as mock_trace:
            mock_trace.get_current_span.return_value = mock_span
            result = get_current_trace_id()
            assert result is None

    def test_returns_hex_trace_id(self):
        from src.tracing_config import get_current_trace_id

        trace_id_int = 123456789012345678901234567890
        expected = format(trace_id_int, "032x")

        mock_ctx = MagicMock()
        mock_ctx.trace_id = trace_id_int

        mock_span = MagicMock()
        mock_span.get_span_context.return_value = mock_ctx

        with patch("src.tracing_config.trace") as mock_trace:
            mock_trace.get_current_span.return_value = mock_span
            result = get_current_trace_id()
            assert result == expected

    def test_returns_32_char_hex_string(self):
        from src.tracing_config import get_current_trace_id

        mock_ctx = MagicMock()
        mock_ctx.trace_id = 1

        mock_span = MagicMock()
        mock_span.get_span_context.return_value = mock_ctx

        with patch("src.tracing_config.trace") as mock_trace:
            mock_trace.get_current_span.return_value = mock_span
            result = get_current_trace_id()
            assert result is not None
            assert len(result) == 32


class TestShutdownTracing:
    def test_calls_shutdown_when_provider_has_it(self):
        from src.tracing_config import shutdown_tracing

        mock_provider = MagicMock()
        mock_provider.shutdown = MagicMock()

        with patch("src.tracing_config.trace") as mock_trace:
            mock_trace.get_tracer_provider.return_value = mock_provider
            shutdown_tracing()
            mock_provider.shutdown.assert_called_once()

    def test_noop_when_provider_has_no_shutdown(self):
        from src.tracing_config import shutdown_tracing

        mock_provider = object()  # Plain object — no shutdown method

        with patch("src.tracing_config.trace") as mock_trace:
            mock_trace.get_tracer_provider.return_value = mock_provider
            # Should not raise
            shutdown_tracing()
