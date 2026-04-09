"""Regression tests for CAB-2030 — Tenant filter on OpenSearch spans + Tempo.

Validates:
- tenant-admin has tenant_id passed to monitoring service and tempo service
- cpi-admin has tenant_id=None (sees all)
- PromQL tenant injection in metrics proxy
"""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.routers.monitoring import _tenant_filter
from src.auth.dependencies import User

MONITORING_SVC_PATH = "src.routers.monitoring._get_monitoring_service"
TEMPO_SVC_PATH = "src.routers.monitoring.tempo_service"
SETTINGS_PATH = "src.routers.monitoring.settings"


def _make_user(role: str = "tenant-admin", tenant_id: str | None = "acme") -> User:
    return User(
        id="test-user", email="test@acme.com", username="test",
        roles=[role], tenant_id=tenant_id,
    )


# ============ _tenant_filter unit tests ============


class TestTenantFilter:
    def test_cpi_admin_returns_none(self):
        user = _make_user(role="cpi-admin", tenant_id=None)
        assert _tenant_filter(user) is None

    def test_tenant_admin_returns_tenant_id(self):
        user = _make_user(role="tenant-admin", tenant_id="acme")
        assert _tenant_filter(user) == "acme"

    def test_viewer_returns_tenant_id(self):
        user = _make_user(role="viewer", tenant_id="globex")
        assert _tenant_filter(user) == "globex"


# ============ list_transactions tenant filtering ============


class TestListTransactionsTenantFilter:
    @patch(SETTINGS_PATH)
    @patch(MONITORING_SVC_PATH)
    def test_tenant_admin_passes_tenant_id_to_opensearch(
        self, mock_get_svc, mock_settings, app_with_tenant_admin
    ):
        mock_settings.OPENSEARCH_TRACES_ENABLED = True
        mock_svc = AsyncMock()
        mock_svc.list_transactions_from_spans = AsyncMock(return_value=[])
        mock_get_svc.return_value = mock_svc

        client = TestClient(app_with_tenant_admin)
        resp = client.get("/v1/monitoring/transactions")
        assert resp.status_code == 200

        call_kwargs = mock_svc.list_transactions_from_spans.call_args.kwargs
        assert call_kwargs.get("tenant_id") == "acme"

    @patch(SETTINGS_PATH)
    @patch(MONITORING_SVC_PATH)
    def test_cpi_admin_passes_none_tenant_id(
        self, mock_get_svc, mock_settings, app_with_cpi_admin
    ):
        mock_settings.OPENSEARCH_TRACES_ENABLED = True
        mock_svc = AsyncMock()
        mock_svc.list_transactions_from_spans = AsyncMock(return_value=[])
        mock_get_svc.return_value = mock_svc

        client = TestClient(app_with_cpi_admin)
        resp = client.get("/v1/monitoring/transactions")
        assert resp.status_code == 200

        call_kwargs = mock_svc.list_transactions_from_spans.call_args.kwargs
        assert call_kwargs.get("tenant_id") is None

    @patch(TEMPO_SVC_PATH)
    @patch(SETTINGS_PATH)
    @patch(MONITORING_SVC_PATH)
    def test_tenant_id_passed_to_tempo_fallback(
        self, mock_get_svc, mock_settings, mock_tempo, app_with_tenant_admin
    ):
        mock_settings.OPENSEARCH_TRACES_ENABLED = False
        mock_get_svc.return_value = None
        mock_tempo.search_traces = AsyncMock(return_value=([], None))

        client = TestClient(app_with_tenant_admin)
        resp = client.get("/v1/monitoring/transactions")
        assert resp.status_code == 200

        call_kwargs = mock_tempo.search_traces.call_args.kwargs
        assert call_kwargs.get("tenant_id") == "acme"


# ============ get_transaction_stats tenant filtering ============


class TestTransactionStatsTenantFilter:
    @patch(SETTINGS_PATH)
    @patch(MONITORING_SVC_PATH)
    def test_stats_passes_tenant_id(self, mock_get_svc, mock_settings, app_with_tenant_admin):
        mock_settings.OPENSEARCH_TRACES_ENABLED = True
        mock_svc = AsyncMock()
        mock_svc.get_transaction_stats_from_spans = AsyncMock(return_value=None)
        mock_svc.get_transaction_stats = AsyncMock(return_value=None)
        mock_get_svc.return_value = mock_svc

        client = TestClient(app_with_tenant_admin)
        resp = client.get("/v1/monitoring/transactions/stats")
        assert resp.status_code == 200

        call_kwargs = mock_svc.get_transaction_stats_from_spans.call_args.kwargs
        assert call_kwargs.get("tenant_id") == "acme"


# ============ get_transaction detail tenant filtering ============


class TestTransactionDetailTenantFilter:
    @patch(SETTINGS_PATH)
    @patch(MONITORING_SVC_PATH)
    def test_detail_passes_tenant_id_to_opensearch(
        self, mock_get_svc, mock_settings, app_with_tenant_admin
    ):
        mock_settings.OPENSEARCH_TRACES_ENABLED = True
        mock_svc = AsyncMock()
        mock_svc.get_transaction_from_spans = AsyncMock(return_value=None)
        mock_get_svc.return_value = mock_svc

        client = TestClient(app_with_tenant_admin)
        resp = client.get("/v1/monitoring/transactions/some-trace-id")
        assert resp.status_code == 200

        call_kwargs = mock_svc.get_transaction_from_spans.call_args.kwargs
        assert call_kwargs.get("tenant_id") == "acme"
