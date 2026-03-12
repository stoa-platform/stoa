"""Tests for MonitoringService — OpenSearch-backed transaction analytics."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.opensearch.audit_middleware import parse_server_timing
from src.services.monitoring_service import (
    MonitoringService,
    _build_spans_from_timings,
    _extract_api_name,
    _status_from_code,
)

# =============================================================================
# Unit tests for parse_server_timing (audit_middleware)
# =============================================================================


class TestParseServerTiming:
    def test_standard_header(self):
        header = "identity;dur=1.20, auth;dur=3.50, backend_call;dur=45.00"
        result = parse_server_timing(header)
        assert result == {"identity": 1.20, "auth": 3.50, "backend_call": 45.00}

    def test_empty_string(self):
        assert parse_server_timing("") == {}

    def test_single_entry(self):
        assert parse_server_timing("total;dur=100.00") == {"total": 100.00}

    def test_ignores_entries_without_dur(self):
        header = "identity;desc=check, auth;dur=2.00"
        result = parse_server_timing(header)
        assert result == {"auth": 2.00}

    def test_handles_malformed_dur(self):
        header = "identity;dur=abc, auth;dur=2.00"
        result = parse_server_timing(header)
        assert result == {"auth": 2.00}

    def test_extra_whitespace(self):
        header = "  identity;dur=1.00 ,  auth;dur=2.00  "
        result = parse_server_timing(header)
        assert result == {"identity": 1.00, "auth": 2.00}

    def test_multiple_params_per_entry(self):
        header = "identity;desc=check;dur=1.50"
        result = parse_server_timing(header)
        assert result == {"identity": 1.50}


# =============================================================================
# Unit tests for _build_spans_from_timings
# =============================================================================


class TestBuildSpansFromTimings:
    def test_multi_stage_spans(self):
        timings = {
            "identity": 1.0,
            "auth": 3.0,
            "quota": 0.5,
            "backend_call": 40.0,
        }
        spans = _build_spans_from_timings(timings, 50, 200, "/v1/apis")
        assert len(spans) == 4
        assert spans[0].name == "identity"
        assert spans[0].service == "gateway-identity"
        assert spans[0].start_offset_ms == 0
        assert spans[0].duration_ms == 1
        assert spans[0].status == "success"
        assert spans[1].name == "auth"
        assert spans[1].start_offset_ms == 1
        assert spans[1].duration_ms == 3
        assert spans[2].name == "quota"
        assert spans[2].start_offset_ms == 4
        assert spans[3].name == "backend_call"
        assert spans[3].start_offset_ms == 4  # 1 + 3 + 0 (0.5 rounds to 0? no, round(0.5)=0 in python)

    def test_error_status_propagated(self):
        timings = {"auth": 2.0, "backend_call": 10.0}
        spans = _build_spans_from_timings(timings, 15, 500, "/v1/apis")
        for span in spans:
            assert span.status == "error"

    def test_timeout_status(self):
        timings = {"backend_call": 30000.0}
        spans = _build_spans_from_timings(timings, 30000, 504, "/v1/apis")
        assert spans[0].status == "timeout"

    def test_fallback_single_span_when_no_timings(self):
        spans = _build_spans_from_timings({}, 100, 200, "/v1/apis")
        assert len(spans) == 1
        assert spans[0].name == "api_request"
        assert spans[0].service == "control-plane-api"
        assert spans[0].duration_ms == 100
        assert spans[0].status == "success"

    def test_fallback_error_span_uses_error_source(self):
        spans = _build_spans_from_timings({}, 50, 500, "/v1/certificates")
        assert len(spans) == 1
        assert spans[0].service == "certificates"
        assert spans[0].status == "error"

    def test_preserves_stage_order(self):
        # Provide stages out of order — output should follow gateway chain order
        timings = {
            "backend_call": 10.0,
            "identity": 1.0,
            "routing": 2.0,
        }
        spans = _build_spans_from_timings(timings, 20, 200, "/v1/apis")
        names = [s.name for s in spans]
        assert names == ["identity", "routing", "backend_call"]


# =============================================================================
# Unit tests for helpers
# =============================================================================


class TestStatusFromCode:
    def test_success_200(self):
        assert _status_from_code(200) == "success"

    def test_success_201(self):
        assert _status_from_code(201) == "success"

    def test_success_204(self):
        assert _status_from_code(204) == "success"

    def test_success_301(self):
        assert _status_from_code(301) == "success"

    def test_error_400(self):
        assert _status_from_code(400) == "error"

    def test_error_401(self):
        assert _status_from_code(401) == "error"

    def test_error_404(self):
        assert _status_from_code(404) == "error"

    def test_error_500(self):
        assert _status_from_code(500) == "error"

    def test_timeout_504(self):
        assert _status_from_code(504) == "timeout"


class TestExtractApiName:
    def test_v1_path(self):
        assert _extract_api_name("/v1/tenants/123") == "tenants"

    def test_v1_apis(self):
        assert _extract_api_name("/v1/apis/my-api") == "apis"

    def test_no_v1_prefix(self):
        assert _extract_api_name("/health") == "health"

    def test_empty_path(self):
        assert _extract_api_name("/") == ""

    def test_deep_path(self):
        assert _extract_api_name("/v1/monitoring/transactions/tx-123") == "monitoring"


# =============================================================================
# MonitoringService tests
# =============================================================================


def _make_os_hit(
    event_id: str = "evt-1",
    method: str = "GET",
    path: str = "/v1/apis",
    status_code: int = 200,
    latency_ms: float = 42.5,
    tenant_id: str = "tenant-1",
    correlation_id: str = "corr-1",
    timestamp: str = "2026-03-02T10:00:00Z",
    gateway_timings: dict[str, float] | None = None,
) -> dict:
    """Build a realistic OpenSearch audit hit."""
    response: dict = {"status_code": status_code, "latency_ms": latency_ms}
    if gateway_timings is not None:
        response["gateway_timings"] = gateway_timings
    return {
        "_id": f"os-{event_id}",
        "_source": {
            "@timestamp": timestamp,
            "event_id": event_id,
            "correlation_id": correlation_id,
            "tenant_id": tenant_id,
            "request": {"method": method, "path": path},
            "response": response,
            "actor": {"id": "user-1", "ip_address": "10.0.0.1"},
            "details": {},
        },
    }


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.search = AsyncMock()
    return client


@pytest.fixture
def service(mock_client):
    return MonitoringService(mock_client)


class TestListTransactions:
    @pytest.mark.asyncio
    async def test_maps_audit_events(self, service, mock_client):
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    _make_os_hit(event_id="e1", path="/v1/apis", status_code=200, latency_ms=35),
                    _make_os_hit(event_id="e2", path="/v1/tenants/t1", status_code=404, latency_ms=12),
                ],
            },
        }

        result = await service.list_transactions(tenant_id="tenant-1", limit=10)

        assert result is not None
        assert len(result) == 2
        assert result[0].id == "e1"
        assert result[0].api_name == "apis"
        assert result[0].status == "success"
        assert result[0].total_duration_ms == 35
        assert result[1].id == "e2"
        assert result[1].status == "error"

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self, service, mock_client):
        mock_client.search.side_effect = Exception("connection refused")

        result = await service.list_transactions(tenant_id="t1")
        assert result is None

    @pytest.mark.asyncio
    async def test_filters_by_status_success(self, service, mock_client):
        mock_client.search.return_value = {"hits": {"hits": []}}

        await service.list_transactions(tenant_id="t1", status="success")

        call_body = mock_client.search.call_args[1]["body"]
        filters = call_body["query"]["bool"]["filter"]
        # Should have tenant_id, time_range, and status_code range filter
        assert len(filters) == 3
        assert {"range": {"response.status_code": {"lt": 400}}} in filters

    @pytest.mark.asyncio
    async def test_filters_by_status_timeout(self, service, mock_client):
        mock_client.search.return_value = {"hits": {"hits": []}}

        await service.list_transactions(tenant_id="t1", status="timeout")

        call_body = mock_client.search.call_args[1]["body"]
        filters = call_body["query"]["bool"]["filter"]
        assert {"term": {"response.status_code": 504}} in filters

    @pytest.mark.asyncio
    async def test_empty_results(self, service, mock_client):
        mock_client.search.return_value = {"hits": {"hits": []}}

        result = await service.list_transactions(tenant_id="t1")
        assert result is not None
        assert result == []


class TestGetTransactionStats:
    @pytest.mark.asyncio
    async def test_aggregations_mapped(self, service, mock_client):
        mock_client.search.return_value = {
            "hits": {"total": {"value": 1000}},
            "aggregations": {
                "success_count": {"doc_count": 900},
                "error_count": {"doc_count": 90},
                "timeout_count": {"doc_count": 10},
                "latency_stats": {"avg": 85.5, "count": 1000, "min": 5, "max": 3000, "sum": 85500},
                "latency_percentiles": {"values": {"95.0": 250.0, "99.0": 800.0}},
                "by_api": {
                    "buckets": [
                        {
                            "key": "/v1/apis",
                            "doc_count": 500,
                            "avg_latency": {"value": 60.0},
                            "errors": {"doc_count": 20},
                        },
                        {
                            "key": "/v1/tenants/t1",
                            "doc_count": 300,
                            "avg_latency": {"value": 120.0},
                            "errors": {"doc_count": 50},
                        },
                    ]
                },
                "by_status_code": {
                    "buckets": [
                        {"key": 200, "doc_count": 800},
                        {"key": 404, "doc_count": 90},
                        {"key": 504, "doc_count": 10},
                    ]
                },
            },
        }

        result = await service.get_transaction_stats(tenant_id="t1", time_range_minutes=60)

        assert result is not None
        assert result.total_requests == 1000
        assert result.success_count == 900
        assert result.error_count == 90
        assert result.timeout_count == 10
        assert result.avg_latency_ms == 85.5
        assert result.p95_latency_ms == 250.0
        assert result.p99_latency_ms == 800.0
        assert result.requests_per_minute == pytest.approx(1000 / 60, rel=0.01)
        assert "apis" in result.by_api
        assert result.by_api["apis"]["total"] == 500
        assert result.by_api["apis"]["errors"] == 20
        assert result.by_status_code[200] == 800

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self, service, mock_client):
        mock_client.search.side_effect = Exception("timeout")

        result = await service.get_transaction_stats(tenant_id="t1")
        assert result is None


class TestGetTransaction:
    @pytest.mark.asyncio
    async def test_maps_single_event(self, service, mock_client):
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    _make_os_hit(
                        event_id="evt-42",
                        method="POST",
                        path="/v1/apis",
                        status_code=201,
                        latency_ms=150,
                    )
                ],
            },
        }

        result = await service.get_transaction(event_id="evt-42", tenant_id="tenant-1")

        assert result is not None
        assert result.id == "evt-42"
        assert result.method == "POST"
        assert result.status == "success"
        assert result.total_duration_ms == 150
        assert len(result.spans) == 1
        assert result.spans[0].name == "api_request"
        assert result.spans[0].duration_ms == 150

    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_client):
        mock_client.search.return_value = {"hits": {"hits": []}}

        result = await service.get_transaction(event_id="nope", tenant_id="t1")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self, service, mock_client):
        mock_client.search.side_effect = Exception("connection error")

        result = await service.get_transaction(event_id="e1", tenant_id="t1")
        assert result is None

    @pytest.mark.asyncio
    async def test_error_message_populated_on_failure(self, service, mock_client):
        hit = _make_os_hit(event_id="err-1", status_code=500)
        hit["_source"]["details"] = {"error": "Internal failure"}
        mock_client.search.return_value = {"hits": {"hits": [hit]}}

        result = await service.get_transaction(event_id="err-1", tenant_id="tenant-1")

        assert result is not None
        assert result.status == "error"
        assert result.error_message == "Internal Server Error: Internal failure"

    @pytest.mark.asyncio
    async def test_multi_span_from_gateway_timings(self, service, mock_client):
        """CAB-1790: gateway_timings in audit event → multi-span transaction detail."""
        timings = {"identity": 1.5, "auth": 3.0, "backend_call": 40.0}
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    _make_os_hit(
                        event_id="evt-gw",
                        method="GET",
                        path="/v1/apis",
                        status_code=200,
                        latency_ms=50,
                        gateway_timings=timings,
                    )
                ],
            },
        }

        result = await service.get_transaction(event_id="evt-gw", tenant_id="tenant-1")

        assert result is not None
        assert len(result.spans) == 3
        assert result.spans[0].name == "identity"
        assert result.spans[0].service == "gateway-identity"
        assert result.spans[0].start_offset_ms == 0
        assert result.spans[1].name == "auth"
        assert result.spans[1].start_offset_ms == 2  # round(1.5) = 2
        assert result.spans[2].name == "backend_call"
        assert result.spans[2].duration_ms == 40

    @pytest.mark.asyncio
    async def test_no_gateway_timings_falls_back_to_single_span(self, service, mock_client):
        """Without gateway_timings, get_transaction still returns a single fallback span."""
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    _make_os_hit(
                        event_id="evt-plain",
                        status_code=200,
                        latency_ms=80,
                    )
                ],
            },
        }

        result = await service.get_transaction(event_id="evt-plain", tenant_id="tenant-1")

        assert result is not None
        assert len(result.spans) == 1
        assert result.spans[0].name == "api_request"
        assert result.spans[0].duration_ms == 80


class TestListTransactionsSpansCount:
    """CAB-1790: list_transactions populates spans_count from gateway_timings."""

    @pytest.mark.asyncio
    async def test_spans_count_with_gateway_timings(self, service, mock_client):
        timings = {"identity": 1.0, "auth": 2.0, "backend_call": 30.0}
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    _make_os_hit(event_id="e1", gateway_timings=timings),
                ],
            },
        }

        result = await service.list_transactions(tenant_id="tenant-1")

        assert result is not None
        assert len(result) == 1
        assert result[0].spans_count == 3

    @pytest.mark.asyncio
    async def test_spans_count_without_gateway_timings(self, service, mock_client):
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    _make_os_hit(event_id="e1"),
                ],
            },
        }

        result = await service.list_transactions(tenant_id="tenant-1")

        assert result is not None
        assert result[0].spans_count == 1
