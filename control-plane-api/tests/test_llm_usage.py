"""Tests for LLM Usage & Cost monitoring router (CAB-1487, CAB-1822).

DB-backed endpoints — mocks UsageMeteringRepository instead of Prometheus.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth import User, get_current_user
from src.database import get_db
from src.routers.llm_usage import router


def _make_user(roles: list[str] | None = None, tenant_id: str = "acme") -> User:
    return User(
        id="user-1",
        username="testuser",
        email="test@example.com",
        roles=roles or ["tenant-admin"],
        tenant_id=tenant_id,
    )


def _mock_db():
    """Create a mock async session."""
    return MagicMock()


@pytest.fixture()
def app():
    """Create a minimal FastAPI app with the LLM usage router."""
    _app = FastAPI()
    _app.include_router(router)
    return _app


@pytest.fixture()
def client(app):
    """Test client with tenant-admin auth."""
    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _mock_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_client(app):
    """Test client with cpi-admin auth."""
    user = _make_user(roles=["cpi-admin"])
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _mock_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def wrong_tenant_client(app):
    """Test client with a different tenant."""
    user = _make_user(tenant_id="other-corp")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _mock_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


_SAMPLE_TOTALS = {
    "total_requests": 100,
    "input_tokens": 50000,
    "output_tokens": 20000,
    "total_tokens": 70000,
    "total_latency_ms": 150000,
    "cache_creation_input_tokens": 1000,
    "cache_read_input_tokens": 5000,
}

_EMPTY_TOTALS = {
    "total_requests": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "total_latency_ms": 0,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
}


class TestGetLlmUsage:
    """GET /v1/tenants/{tenant_id}/llm/usage"""

    @patch("src.routers.llm_usage.UsageMeteringRepository")
    def test_returns_usage_summary(self, mock_repo_cls, client):
        mock_repo = MagicMock()
        mock_repo.get_llm_usage_totals = AsyncMock(return_value=_SAMPLE_TOTALS)
        mock_repo_cls.return_value = mock_repo

        resp = client.get("/v1/tenants/acme/llm/usage?period=month")
        assert resp.status_code == 200
        data = resp.json()
        assert data["input_tokens"] == 50000
        assert data["output_tokens"] == 20000
        assert data["total_cost_usd"] > 0
        assert data["period"] == "month"

    def test_403_wrong_tenant(self, wrong_tenant_client):
        resp = wrong_tenant_client.get("/v1/tenants/acme/llm/usage")
        assert resp.status_code == 403

    @patch("src.routers.llm_usage.UsageMeteringRepository")
    def test_cpi_admin_can_access_any_tenant(self, mock_repo_cls, admin_client):
        mock_repo = MagicMock()
        mock_repo.get_llm_usage_totals = AsyncMock(return_value=_EMPTY_TOTALS)
        mock_repo_cls.return_value = mock_repo

        resp = admin_client.get("/v1/tenants/any-tenant/llm/usage")
        assert resp.status_code == 200

    @patch("src.routers.llm_usage.UsageMeteringRepository")
    def test_returns_zero_when_no_data(self, mock_repo_cls, client):
        mock_repo = MagicMock()
        mock_repo.get_llm_usage_totals = AsyncMock(return_value=_EMPTY_TOTALS)
        mock_repo_cls.return_value = mock_repo

        resp = client.get("/v1/tenants/acme/llm/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost_usd"] == 0.0
        assert data["avg_cost_per_request"] == 0.0

    def test_invalid_period_rejected(self, client):
        resp = client.get("/v1/tenants/acme/llm/usage?period=year")
        assert resp.status_code == 422


class TestGetLlmTimeseries:
    """GET /v1/tenants/{tenant_id}/llm/usage/timeseries"""

    @patch("src.routers.llm_usage.UsageMeteringRepository")
    def test_returns_timeseries(self, mock_repo_cls, client):
        mock_repo = MagicMock()
        mock_repo.get_llm_usage_timeseries = AsyncMock(
            return_value=[
                {
                    "period_start": datetime(2026, 3, 14),
                    "input_tokens": 10000,
                    "output_tokens": 5000,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
                {
                    "period_start": datetime(2026, 3, 15),
                    "input_tokens": 20000,
                    "output_tokens": 8000,
                    "cache_creation_input_tokens": 500,
                    "cache_read_input_tokens": 1000,
                },
            ]
        )
        mock_repo_cls.return_value = mock_repo

        resp = client.get("/v1/tenants/acme/llm/usage/timeseries?period=day")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["points"]) == 2
        assert data["period"] == "day"
        assert data["step"] == "1h"
        # Each point should have a computed cost value
        assert data["points"][0]["value"] > 0


class TestGetLlmProviderBreakdown:
    """GET /v1/tenants/{tenant_id}/llm/usage/providers"""

    @patch("src.routers.llm_usage.UsageMeteringRepository")
    def test_returns_breakdown(self, mock_repo_cls, client):
        mock_repo = MagicMock()
        mock_repo.get_llm_usage_totals = AsyncMock(return_value=_SAMPLE_TOTALS)
        mock_repo_cls.return_value = mock_repo

        resp = client.get("/v1/tenants/acme/llm/usage/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["providers"]) == 1
        assert data["providers"][0]["provider"] == "anthropic"
        assert data["providers"][0]["cost_usd"] > 0

    @patch("src.routers.llm_usage.UsageMeteringRepository")
    def test_empty_when_no_data(self, mock_repo_cls, client):
        mock_repo = MagicMock()
        mock_repo.get_llm_usage_totals = AsyncMock(return_value=_EMPTY_TOTALS)
        mock_repo_cls.return_value = mock_repo

        resp = client.get("/v1/tenants/acme/llm/usage/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["providers"]) == 0


class TestGetLlmAnomalies:
    """GET /v1/tenants/{tenant_id}/llm/usage/anomalies"""

    @patch("src.routers.llm_usage.UsageMeteringRepository")
    def test_returns_anomalies(self, mock_repo_cls, client):
        mock_repo = MagicMock()
        mock_repo.get_llm_usage_totals = AsyncMock(return_value=_SAMPLE_TOTALS)
        mock_repo_cls.return_value = mock_repo

        resp = client.get("/v1/tenants/acme/llm/usage/anomalies")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["provider"] == "anthropic"
        # avg latency = 150000ms / 100 requests / 1000 = 1.5s
        assert data["entries"][0]["avg_latency_seconds"] == 1.5

    @patch("src.routers.llm_usage.UsageMeteringRepository")
    def test_empty_when_no_requests(self, mock_repo_cls, client):
        mock_repo = MagicMock()
        mock_repo.get_llm_usage_totals = AsyncMock(return_value=_EMPTY_TOTALS)
        mock_repo_cls.return_value = mock_repo

        resp = client.get("/v1/tenants/acme/llm/usage/anomalies")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 0


class TestPrometheusClientLlmMethods:
    """Unit tests for PrometheusClient LLM-specific methods (mocked HTTP)."""

    @pytest.mark.asyncio
    async def test_get_llm_cost_total(self):
        from src.services.prometheus_client import PrometheusClient

        client = PrometheusClient()
        client._enabled = True

        with patch.object(client, "query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = {
                "resultType": "vector",
                "result": [{"value": [1709164800, "42.5"]}],
            }
            result = await client.get_llm_cost_total(tenant_id="acme", time_range="7d")
            assert result == 42.5

    @pytest.mark.asyncio
    async def test_get_llm_cost_total_returns_zero_when_no_data(self):
        from src.services.prometheus_client import PrometheusClient

        client = PrometheusClient()
        client._enabled = True

        with patch.object(client, "query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = None
            result = await client.get_llm_cost_total()
            assert result == 0.0

    @pytest.mark.asyncio
    async def test_get_llm_provider_breakdown(self):
        from src.services.prometheus_client import PrometheusClient

        client = PrometheusClient()
        client._enabled = True

        with patch.object(client, "query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"provider": "anthropic", "model": "claude-3-5-sonnet"},
                        "value": [1709164800, "8.5"],
                    },
                    {
                        "metric": {"provider": "openai", "model": "gpt-4o"},
                        "value": [1709164800, "3.2"],
                    },
                ],
            }
            result = await client.get_llm_provider_breakdown(tenant_id="acme")
            assert len(result) == 2
            # Should be sorted descending by cost
            assert result[0]["provider"] == "anthropic"
            assert result[0]["cost_usd"] == 8.5

    @pytest.mark.asyncio
    async def test_get_llm_cache_savings(self):
        from src.services.prometheus_client import PrometheusClient

        client = PrometheusClient()
        client._enabled = True

        with patch.object(client, "query", new_callable=AsyncMock) as mock_query:
            mock_query.side_effect = [
                {"resultType": "vector", "result": [{"value": [1709164800, "0.5"]}]},
                {"resultType": "vector", "result": [{"value": [1709164800, "0.1"]}]},
            ]
            result = await client.get_llm_cache_savings(tenant_id="acme")
            assert result["cache_read_cost_usd"] == 0.5
            assert result["cache_write_cost_usd"] == 0.1

    @pytest.mark.asyncio
    async def test_get_llm_timeseries(self):
        from src.services.prometheus_client import PrometheusClient

        client = PrometheusClient()
        client._enabled = True

        with patch.object(client, "query_range", new_callable=AsyncMock) as mock_qr:
            mock_qr.return_value = {
                "resultType": "matrix",
                "result": [
                    {
                        "values": [
                            [1709164800, "1.5"],
                            [1709168400, "2.3"],
                        ]
                    }
                ],
            }
            result = await client.get_llm_cost_timeseries(tenant_id="acme", days=1, step="1h")
            assert len(result) == 2
            assert result[0]["value"] == 1.5

    @pytest.mark.asyncio
    async def test_get_llm_avg_cost_per_request_handles_nan(self):
        from src.services.prometheus_client import PrometheusClient

        client = PrometheusClient()
        client._enabled = True

        with patch.object(client, "query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = {
                "resultType": "vector",
                "result": [{"value": [1709164800, "NaN"]}],
            }
            result = await client.get_llm_avg_cost_per_request()
            assert result == 0.0
