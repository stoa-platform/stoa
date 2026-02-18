"""Tests for Monitoring Router — CAB-1378

Endpoints (demo data generators, no DB):
- GET /v1/monitoring/transactions
- GET /v1/monitoring/transactions/stats
- GET /v1/monitoring/transactions/{transaction_id}

Auth: get_current_user (any authenticated user)
"""

from fastapi.testclient import TestClient


class TestMonitoringRouter:
    """Test suite for Monitoring Router endpoints."""

    # ============== GET /transactions ==============

    def test_list_transactions_success(self, app_with_tenant_admin):
        """GET /transactions returns demo transaction list."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/monitoring/transactions")

        assert response.status_code == 200
        data = response.json()
        assert "transactions" in data
        assert "total" in data
        assert isinstance(data["transactions"], list)
        # Default limit is 50
        assert len(data["transactions"]) <= 50

    def test_list_transactions_with_limit(self, app_with_tenant_admin):
        """GET /transactions?limit=5 respects limit parameter."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/monitoring/transactions?limit=10")

        assert response.status_code == 200
        data = response.json()
        # Filtering may reduce count, but original generation respects limit
        assert data["total"] <= 10

    def test_list_transactions_filter_by_api_name(self, app_with_tenant_admin):
        """GET /transactions?api_name=X filters results."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get(
                "/v1/monitoring/transactions?limit=200&api_name=customer-api"
            )

        assert response.status_code == 200
        data = response.json()
        for tx in data["transactions"]:
            assert tx["api_name"] == "customer-api"

    def test_list_transactions_filter_by_status(self, app_with_tenant_admin):
        """GET /transactions?status=error filters by status."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get(
                "/v1/monitoring/transactions?limit=200&status=error"
            )

        assert response.status_code == 200
        data = response.json()
        for tx in data["transactions"]:
            assert tx["status"] == "error"

    def test_list_transactions_response_shape(self, app_with_tenant_admin):
        """Each transaction has required fields."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/monitoring/transactions?limit=5")

        assert response.status_code == 200
        data = response.json()
        if data["transactions"]:
            tx = data["transactions"][0]
            required_fields = [
                "id", "trace_id", "api_name", "method", "path",
                "status_code", "status", "started_at",
                "total_duration_ms", "spans_count",
            ]
            for field in required_fields:
                assert field in tx, f"Missing field: {field}"

    # ============== GET /transactions/stats ==============

    def test_get_transaction_stats_success(self, app_with_tenant_admin):
        """GET /transactions/stats returns aggregated statistics."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/monitoring/transactions/stats")

        assert response.status_code == 200
        data = response.json()
        assert "total_requests" in data
        assert "success_count" in data
        assert "error_count" in data
        assert "avg_latency_ms" in data
        assert "p95_latency_ms" in data
        assert "by_api" in data
        assert "by_status_code" in data
        assert isinstance(data["by_api"], dict)

    # ============== GET /transactions/{transaction_id} ==============

    def test_get_transaction_detail_success(self, app_with_tenant_admin):
        """GET /transactions/{id} returns detailed transaction with spans."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/monitoring/transactions/tx-000001-1234")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "tx-000001-1234"
        assert "spans" in data
        assert isinstance(data["spans"], list)
        assert len(data["spans"]) > 0
        # Each span has required fields
        span = data["spans"][0]
        assert "name" in span
        assert "service" in span
        assert "duration_ms" in span

    def test_get_transaction_detail_uses_user_tenant(self, app_with_tenant_admin):
        """Transaction detail uses the authenticated user's tenant_id."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/monitoring/transactions/tx-test-001")

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == "acme"

    def test_list_transactions_unauthenticated_401(self, app):
        """Unauthenticated requests to monitoring endpoints return 401."""
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/v1/monitoring/transactions")

        # Without auth override, get_current_user raises 401
        assert response.status_code in (401, 403)
