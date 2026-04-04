"""Tests for Tempo Service — CAB-1984

Unit tests for tempo_service.py: Tempo API proxy, circuit breaker, span mapping.
Uses httpx.MockTransport for realistic HTTP mocking (Boundary Integrity Rule).
"""

import json
import time

import httpx
import pytest

from src.services.tempo_service import (
    _CB_RESET_SECONDS,
    _CB_THRESHOLD,
    _map_spans,
    _map_trace_to_summary,
    _ns_to_iso,
    _ns_to_ms,
    _status_from_code,
    get_trace,
    search_traces,
)


# ---------------------------------------------------------------------------
# Unit tests: helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_ns_to_iso_converts_correctly(self):
        # 2024-04-02 00:00:00 UTC in nanoseconds
        ns = 1712016000_000_000_000
        result = _ns_to_iso(ns)
        assert result.startswith("2024-04-02")
        assert result.endswith("+00:00")

    def test_ns_to_ms(self):
        assert _ns_to_ms(150_000_000) == 150
        assert _ns_to_ms(0) == 0
        assert _ns_to_ms("500000000") == 500

    def test_status_from_code(self):
        assert _status_from_code(200) == "success"
        assert _status_from_code(201) == "success"
        assert _status_from_code(400) == "error"
        assert _status_from_code(500) == "error"
        assert _status_from_code(504) == "timeout"


# ---------------------------------------------------------------------------
# Unit tests: trace mapping
# ---------------------------------------------------------------------------


class TestTraceMapping:
    def test_map_trace_to_summary_basic(self):
        trace = {
            "traceID": "abc123",
            "rootServiceName": "stoa-gateway",
            "rootTraceName": "GET /v1/apis",
            "startTimeUnixNano": 1712000000000000000,
            "durationMs": 150,
            "spanCount": 4,
        }
        summary = _map_trace_to_summary(trace)
        assert summary.id == "abc123"
        assert summary.trace_id == "abc123"
        assert summary.api_name == "stoa-gateway"
        assert summary.method == "GET"
        assert summary.path == "/v1/apis"
        assert summary.total_duration_ms == 150
        assert summary.spans_count == 4

    def test_map_trace_to_summary_no_space_in_name(self):
        trace = {
            "traceID": "def456",
            "rootServiceName": "svc",
            "rootTraceName": "/health",
            "startTimeUnixNano": 0,
            "durationMs": 5,
            "spanCount": 1,
        }
        summary = _map_trace_to_summary(trace)
        assert summary.method == "GET"  # default
        assert summary.path == "/health"

    def test_map_spans_builds_waterfall(self):
        data = {
            "batches": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "stoa-gateway"}}
                        ]
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "name": "ingress",
                                    "spanId": "s1",
                                    "parentSpanId": "",
                                    "startTimeUnixNano": "1000000000",
                                    "endTimeUnixNano": "1050000000",
                                    "status": {"code": 1},
                                    "attributes": [
                                        {"key": "http.method", "value": {"stringValue": "POST"}},
                                        {"key": "http.status_code", "value": {"intValue": 201}},
                                    ],
                                },
                                {
                                    "name": "backend",
                                    "spanId": "s2",
                                    "parentSpanId": "s1",
                                    "startTimeUnixNano": "1050000000",
                                    "endTimeUnixNano": "1100000000",
                                    "status": {"code": 1},
                                    "attributes": [],
                                },
                            ]
                        }
                    ],
                }
            ]
        }
        spans, root_info = _map_spans(data)
        assert len(spans) == 2
        assert spans[0].name == "ingress"
        assert spans[0].start_offset_ms == 0
        assert spans[0].duration_ms == 50
        assert spans[1].name == "backend"
        assert spans[1].start_offset_ms == 50
        assert root_info["method"] == "POST"
        assert root_info["status_code"] == 201

    def test_map_spans_empty_batches(self):
        spans, root_info = _map_spans({"batches": []})
        assert spans == []
        assert root_info == {}

    def test_map_spans_error_status(self):
        data = {
            "batches": [
                {
                    "resource": {"attributes": []},
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "name": "fail",
                                    "spanId": "s1",
                                    "parentSpanId": "",
                                    "startTimeUnixNano": "1000000000",
                                    "endTimeUnixNano": "1050000000",
                                    "status": {"code": 2},  # ERROR
                                    "attributes": [],
                                }
                            ]
                        }
                    ],
                }
            ]
        }
        spans, _ = _map_spans(data)
        assert spans[0].status == "error"


# ---------------------------------------------------------------------------
# Integration tests: search_traces with httpx.MockTransport
# ---------------------------------------------------------------------------


def _make_transport(response_json: dict, status_code: int = 200):
    """Create an httpx.MockTransport that returns the given JSON."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            json=response_json,
        )

    return handler


class TestSearchTraces:
    @pytest.fixture(autouse=True)
    def _reset_circuit_breaker(self):
        """Reset circuit breaker state between tests."""
        import src.services.tempo_service as ts

        ts._cb_failures = 0
        ts._cb_open_since = 0.0

    @pytest.mark.asyncio
    async def test_search_traces_success(self, monkeypatch):
        """search_traces returns mapped summaries from Tempo."""
        response_data = {
            "traces": [
                {
                    "traceID": "t1",
                    "rootServiceName": "gw",
                    "rootTraceName": "GET /api",
                    "startTimeUnixNano": 1712000000000000000,
                    "durationMs": 100,
                    "spanCount": 2,
                },
            ]
        }

        transport = httpx.MockTransport(_make_transport(response_data))
        monkeypatch.setattr("src.services.tempo_service.settings.TEMPO_ENABLED", True)
        monkeypatch.setattr("src.services.tempo_service.settings.TEMPO_INTERNAL_URL", "http://tempo:3200")
        monkeypatch.setattr("src.services.tempo_service.settings.TEMPO_TIMEOUT_SECONDS", 5)

        # Patch httpx.AsyncClient to use our transport
        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self_client, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        result = await search_traces(limit=10)
        assert result is not None
        traces, cursor = result
        assert len(traces) == 1
        assert traces[0].trace_id == "t1"

    @pytest.mark.asyncio
    async def test_search_traces_disabled(self, monkeypatch):
        """search_traces returns None when TEMPO_ENABLED=False."""
        monkeypatch.setattr("src.services.tempo_service.settings.TEMPO_ENABLED", False)
        result = await search_traces()
        assert result is None

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_threshold(self, monkeypatch):
        """Circuit breaker opens after _CB_THRESHOLD consecutive failures."""
        import src.services.tempo_service as ts

        monkeypatch.setattr("src.services.tempo_service.settings.TEMPO_ENABLED", True)

        # Simulate failures
        ts._cb_failures = _CB_THRESHOLD
        ts._cb_open_since = time.monotonic()

        result = await search_traces()
        assert result is None  # circuit is open

    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_after_reset(self, monkeypatch):
        """Circuit breaker allows retry after reset period."""
        import src.services.tempo_service as ts

        monkeypatch.setattr("src.services.tempo_service.settings.TEMPO_ENABLED", True)

        ts._cb_failures = _CB_THRESHOLD
        ts._cb_open_since = time.monotonic() - _CB_RESET_SECONDS - 1  # expired

        # CB should be half-open — will try (and fail because no real Tempo)
        # But the point is it doesn't return None from the CB check
        transport = httpx.MockTransport(_make_transport({"traces": []}))
        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self_client, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        monkeypatch.setattr("src.services.tempo_service.settings.TEMPO_INTERNAL_URL", "http://tempo:3200")
        monkeypatch.setattr("src.services.tempo_service.settings.TEMPO_TIMEOUT_SECONDS", 5)

        result = await search_traces()
        assert result is not None
        traces, _ = result
        assert traces == []


class TestGetTrace:
    @pytest.fixture(autouse=True)
    def _reset_circuit_breaker(self):
        import src.services.tempo_service as ts

        ts._cb_failures = 0
        ts._cb_open_since = 0.0

    @pytest.mark.asyncio
    async def test_get_trace_success(self, monkeypatch):
        """get_trace returns mapped APITransaction from Tempo."""
        response_data = {
            "batches": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "stoa-gateway"}}
                        ]
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "name": "ingress",
                                    "spanId": "s1",
                                    "parentSpanId": "",
                                    "startTimeUnixNano": "1000000000",
                                    "endTimeUnixNano": "1050000000",
                                    "status": {"code": 1},
                                    "attributes": [
                                        {"key": "http.method", "value": {"stringValue": "GET"}},
                                        {"key": "http.target", "value": {"stringValue": "/v1/apis"}},
                                        {"key": "http.status_code", "value": {"intValue": 200}},
                                    ],
                                }
                            ]
                        }
                    ],
                }
            ]
        }

        transport = httpx.MockTransport(_make_transport(response_data))
        monkeypatch.setattr("src.services.tempo_service.settings.TEMPO_ENABLED", True)
        monkeypatch.setattr("src.services.tempo_service.settings.TEMPO_INTERNAL_URL", "http://tempo:3200")
        monkeypatch.setattr("src.services.tempo_service.settings.TEMPO_TIMEOUT_SECONDS", 5)

        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self_client, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        result = await get_trace("abc123")
        assert result is not None
        assert result.trace_id == "abc123"
        assert result.method == "GET"
        assert result.path == "/v1/apis"
        assert len(result.spans) == 1

    @pytest.mark.asyncio
    async def test_get_trace_disabled(self, monkeypatch):
        """get_trace returns None when TEMPO_ENABLED=False."""
        monkeypatch.setattr("src.services.tempo_service.settings.TEMPO_ENABLED", False)
        result = await get_trace("abc123")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_trace_empty_batches(self, monkeypatch):
        """get_trace returns None when trace has no spans."""
        transport = httpx.MockTransport(_make_transport({"batches": []}))
        monkeypatch.setattr("src.services.tempo_service.settings.TEMPO_ENABLED", True)
        monkeypatch.setattr("src.services.tempo_service.settings.TEMPO_INTERNAL_URL", "http://tempo:3200")
        monkeypatch.setattr("src.services.tempo_service.settings.TEMPO_TIMEOUT_SECONDS", 5)

        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self_client, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        result = await get_trace("empty-trace")
        assert result is None
