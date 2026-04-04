"""Tests for Monitoring Router — CAB-1984

Endpoints (OpenSearch → Tempo → empty, no mocks):
- GET /v1/monitoring/transactions
- GET /v1/monitoring/transactions/stats
- GET /v1/monitoring/transactions/{transaction_id}

Auth: get_current_user (any authenticated user)
"""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


# Sample Tempo search response for testing
_TEMPO_SEARCH_RESPONSE = {
    "traces": [
        {
            "traceID": "abc123def456",
            "rootServiceName": "stoa-gateway",
            "rootTraceName": "GET /v1/apis",
            "startTimeUnixNano": 1712000000000000000,
            "durationMs": 150,
            "spanCount": 4,
            "spanSets": [],
        },
        {
            "traceID": "def789abc012",
            "rootServiceName": "stoa-gateway",
            "rootTraceName": "POST /v1/subscriptions",
            "startTimeUnixNano": 1711999000000000000,
            "durationMs": 320,
            "spanCount": 6,
            "spanSets": [],
        },
    ]
}

# Sample Tempo trace detail response
_TEMPO_TRACE_RESPONSE = {
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
                            "name": "gateway_ingress",
                            "spanId": "span1",
                            "parentSpanId": "",
                            "startTimeUnixNano": "1712000000000000000",
                            "endTimeUnixNano": "1712000000050000000",
                            "status": {"code": 1},
                            "attributes": [
                                {"key": "http.method", "value": {"stringValue": "GET"}},
                                {"key": "http.target", "value": {"stringValue": "/v1/apis"}},
                                {"key": "http.status_code", "value": {"intValue": 200}},
                            ],
                        },
                        {
                            "name": "auth_validation",
                            "spanId": "span2",
                            "parentSpanId": "span1",
                            "startTimeUnixNano": "1712000000050000000",
                            "endTimeUnixNano": "1712000000080000000",
                            "status": {"code": 1},
                            "attributes": [],
                        },
                        {
                            "name": "backend_call",
                            "spanId": "span3",
                            "parentSpanId": "span1",
                            "startTimeUnixNano": "1712000000080000000",
                            "endTimeUnixNano": "1712000000150000000",
                            "status": {"code": 1},
                            "attributes": [],
                        },
                    ]
                }
            ],
        }
    ]
}


def _mock_httpx_response(json_data: dict, status_code: int = 200):
    """Create a mock httpx response."""
    import httpx

    return httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("GET", "http://tempo:3200/test"),
    )


class TestMonitoringRouterWithTempo:
    """Test suite for monitoring endpoints with Tempo as data source."""

    def _patch_tempo_search(self, response_data: dict | None = None, raise_error: bool = False):
        """Patch tempo_service.search_traces."""
        if raise_error:
            return patch(
                "src.routers.monitoring.tempo_service.search_traces",
                new_callable=AsyncMock,
                return_value=None,
            )
        data = response_data or _TEMPO_SEARCH_RESPONSE
        traces = []
        from src.services.tempo_service import _map_trace_to_summary

        for t in data.get("traces", []):
            traces.append(_map_trace_to_summary(t))
        return patch(
            "src.routers.monitoring.tempo_service.search_traces",
            new_callable=AsyncMock,
            return_value=(traces, None),
        )

    def _patch_tempo_trace(self, response_data: dict | None = None, return_none: bool = False):
        """Patch tempo_service.get_trace."""
        if return_none:
            return patch(
                "src.routers.monitoring.tempo_service.get_trace",
                new_callable=AsyncMock,
                return_value=None,
            )
        from src.services.tempo_service import _map_spans, _status_from_code

        data = response_data or _TEMPO_TRACE_RESPONSE
        spans, root_info = _map_spans(data)
        from src.schemas.monitoring import APITransaction

        tx = APITransaction(
            id="abc123def456",
            trace_id="abc123def456",
            api_name=root_info.get("service", "unknown"),
            method=root_info.get("method", "GET"),
            path=root_info.get("path", ""),
            status_code=root_info.get("status_code", 200),
            status=_status_from_code(root_info.get("status_code", 200)),
            started_at="",
            total_duration_ms=spans[-1].start_offset_ms + spans[-1].duration_ms if spans else 0,
            spans=spans,
        )
        return patch(
            "src.routers.monitoring.tempo_service.get_trace",
            new_callable=AsyncMock,
            return_value=tx,
        )

    # ============== GET /transactions ==============

    def test_list_transactions_from_tempo(self, app_with_tenant_admin):
        """GET /transactions returns Tempo traces when OpenSearch unavailable."""
        with self._patch_tempo_search():
            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/monitoring/transactions")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "tempo"
        assert data["demo_mode"] is False
        assert len(data["transactions"]) == 2
        assert data["total"] == 2

    def test_list_transactions_empty_when_no_source(self, app_with_tenant_admin):
        """GET /transactions returns empty when both OpenSearch and Tempo unavailable."""
        with self._patch_tempo_search(raise_error=True):
            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/monitoring/transactions")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "none"
        assert data["demo_mode"] is False
        assert data["transactions"] == []
        assert data["total"] == 0

    def test_list_transactions_response_shape(self, app_with_tenant_admin):
        """Each transaction from Tempo has required fields."""
        with self._patch_tempo_search():
            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/monitoring/transactions")

        assert response.status_code == 200
        data = response.json()
        tx = data["transactions"][0]
        required_fields = [
            "id", "trace_id", "api_name", "method", "path",
            "status_code", "status", "started_at", "total_duration_ms", "spans_count",
        ]
        for field in required_fields:
            assert field in tx, f"Missing field: {field}"

    def test_list_transactions_with_limit(self, app_with_tenant_admin):
        """GET /transactions?limit=5 passes limit to Tempo."""
        with patch(
            "src.routers.monitoring.tempo_service.search_traces",
            new_callable=AsyncMock,
            return_value=([], None),
        ) as mock_search:
            with TestClient(app_with_tenant_admin) as client:
                client.get("/v1/monitoring/transactions?limit=5")

        mock_search.assert_called_once()
        assert mock_search.call_args.kwargs.get("limit") == 5

    def test_list_transactions_with_cursor(self, app_with_tenant_admin):
        """GET /transactions?cursor=X passes cursor for pagination."""
        with patch(
            "src.routers.monitoring.tempo_service.search_traces",
            new_callable=AsyncMock,
            return_value=([], "next_page_cursor"),
        ) as mock_search:
            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/monitoring/transactions?cursor=12345")

        mock_search.assert_called_once()
        assert mock_search.call_args.kwargs.get("cursor") == "12345"
        data = response.json()
        assert data["next_cursor"] == "next_page_cursor"

    # ============== GET /transactions/stats ==============

    def test_get_transaction_stats_empty_when_no_opensearch(self, app_with_tenant_admin):
        """GET /transactions/stats returns zeroed stats when OpenSearch unavailable."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/monitoring/transactions/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "none"
        assert data["demo_mode"] is False
        assert data["total_requests"] == 0
        assert data["success_count"] == 0

    # ============== GET /transactions/{transaction_id} ==============

    def test_get_transaction_detail_from_tempo(self, app_with_tenant_admin):
        """GET /transactions/{id} returns trace detail from Tempo."""
        with self._patch_tempo_trace():
            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/monitoring/transactions/abc123def456")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "tempo"
        assert data["demo_mode"] is False
        assert data["id"] == "abc123def456"
        assert "spans" in data
        assert len(data["spans"]) == 3

    def test_get_transaction_detail_spans_have_fields(self, app_with_tenant_admin):
        """Transaction detail spans from Tempo have all required fields."""
        with self._patch_tempo_trace():
            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/monitoring/transactions/abc123def456")

        data = response.json()
        for span in data["spans"]:
            assert "name" in span
            assert "service" in span
            assert "start_offset_ms" in span
            assert "duration_ms" in span
            assert "status" in span
            assert isinstance(span["duration_ms"], int)
            assert span["duration_ms"] >= 0

    def test_get_transaction_detail_not_found(self, app_with_tenant_admin):
        """GET /transactions/{id} returns empty response when trace not in any source."""
        with self._patch_tempo_trace(return_none=True):
            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/monitoring/transactions/nonexistent")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "none"
        assert data["id"] == "nonexistent"
        assert data["spans"] == []

    # ============== Auth ==============

    def test_list_transactions_unauthenticated_401(self, app):
        """Unauthenticated requests to monitoring endpoints return 401."""
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/v1/monitoring/transactions")
        assert response.status_code in (401, 403)

    def test_get_transaction_stats_unauthenticated_401(self, app):
        """Unauthenticated requests to stats endpoint return 401."""
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/v1/monitoring/transactions/stats")
        assert response.status_code in (401, 403)

    def test_get_transaction_detail_unauthenticated_401(self, app):
        """Unauthenticated requests to detail endpoint return 401."""
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/v1/monitoring/transactions/abc123")
        assert response.status_code in (401, 403)

    # ============== CPI Admin access ==============

    def test_list_transactions_cpi_admin_access(self, app_with_cpi_admin):
        """CPI admin can access monitoring transactions."""
        with self._patch_tempo_search():
            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/monitoring/transactions")

        assert response.status_code == 200
        data = response.json()
        assert "transactions" in data

    # ============== No demo_mode: true ever ==============

    def test_demo_mode_never_true_in_list(self, app_with_tenant_admin):
        """demo_mode is always False — mock data has been removed."""
        with self._patch_tempo_search(raise_error=True):
            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/monitoring/transactions")
        assert response.json()["demo_mode"] is False

    def test_demo_mode_never_true_in_stats(self, app_with_tenant_admin):
        """demo_mode is always False in stats — mock data removed."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/monitoring/transactions/stats")
        assert response.json()["demo_mode"] is False

    def test_demo_mode_never_true_in_detail(self, app_with_tenant_admin):
        """demo_mode is always False in detail — mock data removed."""
        with self._patch_tempo_trace(return_none=True):
            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/monitoring/transactions/any-id")
        assert response.json()["demo_mode"] is False
