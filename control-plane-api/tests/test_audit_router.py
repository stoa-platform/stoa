"""Tests for Audit Router — CAB-1452

Covers: /v1/audit (list, export CSV/JSON, security events, isolation test, global summary).

Strategy:
  - Mock OpenSearchService so client=None => demo data fallback
  - Demo data tenants: oasis, high-five, ioi
  - cpi-admin bypasses @require_tenant_access
  - Viewer with no tenant_id always gets 403
"""

import json as _json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

import pytest

import src.routers.audit as audit_router
from src.auth.dependencies import User, get_current_user
from src.database import get_db

OS_SVC_PATH = "src.routers.audit.OpenSearchService"
AUDIT_SERVICE_PATH = "src.routers.audit.AuditService"
DEMO_TENANT = "oasis"


@pytest.fixture
def app_with_viewer(app, mock_db_session):
    """App with viewer role user who has a valid tenant (oasis)."""

    async def override():
        return User(
            id="viewer-user-id",
            email="viewer@oasis.com",
            username="viewer",
            roles=["viewer"],
            tenant_id=DEMO_TENANT,
        )

    async def override_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = override
    app.dependency_overrides[get_db] = override_db
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def app_with_devops(app, mock_db_session):
    """App with devops role user who has a valid tenant (oasis)."""

    async def override():
        return User(
            id="devops-user-id",
            email="devops@oasis.com",
            username="devops",
            roles=["devops"],
            tenant_id=DEMO_TENANT,
        )

    async def override_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = override
    app.dependency_overrides[get_db] = override_db
    yield app
    app.dependency_overrides.clear()


def _make_os_mock() -> MagicMock:
    """OpenSearchService mock where client=None forces demo-data fallback."""
    mock_svc = MagicMock()
    mock_svc.client = None
    mock_os_cls = MagicMock()
    mock_os_cls.get_instance.return_value = mock_svc
    return mock_os_cls


class TestListAuditEntries:
    """Tests for GET /v1/audit/{tenant_id}."""

    def test_list_audit_entries_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}")

        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert data["page"] == 1

    def test_list_audit_entries_paginated(self, app_with_cpi_admin, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}?page=1&page_size=5")

        assert resp.status_code == 200
        data = resp.json()
        assert data["page_size"] == 5
        assert "has_more" in data

    def test_list_audit_entries_filter_by_action(self, app_with_cpi_admin, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}?action=api_call")

        assert resp.status_code == 200
        for entry in resp.json()["entries"]:
            assert entry["action"] == "api_call"

    def test_list_audit_entries_unknown_tenant_empty(self, app_with_cpi_admin, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/audit/nonexistent-tenant-xyz")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_audit_entries_403_no_tenant_user(self, app_with_no_tenant_user, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_no_tenant_user) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}")

        assert resp.status_code == 403


class TestAuditStatsEndpoint:
    """Tests for GET /v1/audit/{tenant_id}/stats."""

    def test_stats_endpoint_returns_aggregates(self, app_with_cpi_admin):
        window_end = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
        service = MagicMock()
        service.get_stats = AsyncMock(
            return_value={
                "total_events": 4,
                "success_count": 3,
                "failed_count": 1,
                "unique_actors": 2,
                "by_action": {"export": 2, "deploy": 1, "update": 1},
                "by_status": {"success": 3, "failure": 1},
                "window_start": window_end - timedelta(days=30),
                "window_end": window_end,
            }
        )

        with patch(AUDIT_SERVICE_PATH, return_value=service), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 4
        assert data["success_count"] == 3
        assert data["failed_count"] == 1
        assert data["unique_actors"] == 2
        assert data["by_action"] == {"export": 2, "deploy": 1, "update": 1}
        assert data["by_status"] == {"success": 3, "failure": 1}

    def test_stats_endpoint_filters_by_window(self, app_with_cpi_admin):
        service = MagicMock()
        service.get_stats = AsyncMock(
            return_value={
                "total_events": 1,
                "success_count": 1,
                "failed_count": 0,
                "unique_actors": 1,
                "by_action": {"export": 1},
                "by_status": {"success": 1},
                "window_start": datetime(2026, 5, 1, tzinfo=UTC),
                "window_end": datetime(2026, 5, 8, tzinfo=UTC),
            }
        )

        with patch(AUDIT_SERVICE_PATH, return_value=service), TestClient(app_with_cpi_admin) as client:
            resp = client.get(
                f"/v1/audit/{DEMO_TENANT}/stats"
                "?start_date=2026-05-01T00:00:00Z&end_date=2026-05-08T00:00:00Z"
            )

        assert resp.status_code == 200
        kwargs = service.get_stats.await_args.kwargs
        assert kwargs["start_date"] == datetime(2026, 5, 1, tzinfo=UTC)
        assert kwargs["end_date"] == datetime(2026, 5, 8, tzinfo=UTC)

    def test_stats_endpoint_filters_by_action(self, app_with_cpi_admin):
        service = MagicMock()
        service.get_stats = AsyncMock(
            return_value={
                "total_events": 2,
                "success_count": 2,
                "failed_count": 0,
                "unique_actors": 1,
                "by_action": {"export": 2},
                "by_status": {"success": 2},
                "window_start": datetime(2026, 5, 1, tzinfo=UTC),
                "window_end": datetime(2026, 5, 8, tzinfo=UTC),
            }
        )

        with patch(AUDIT_SERVICE_PATH, return_value=service), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/stats?action=export")

        assert resp.status_code == 200
        assert service.get_stats.await_args.kwargs["action"] == "export"
        assert resp.json()["by_action"] == {"export": 2}


class TestAuditActionsEndpoint:
    """Tests for GET /v1/audit/{tenant_id}/actions."""

    def test_actions_endpoint_returns_distinct_top_100(self, app_with_cpi_admin):
        window_end = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
        actions = [{"action": f"action_{idx}", "count": 100 - idx} for idx in range(100)]
        service = MagicMock()
        service.get_actions = AsyncMock(
            return_value={
                "actions": actions,
                "window_start": window_end - timedelta(days=30),
                "window_end": window_end,
            }
        )

        with patch(AUDIT_SERVICE_PATH, return_value=service), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/actions")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["actions"]) == 100
        assert data["actions"][0] == {"action": "action_0", "count": 100}

    def test_actions_endpoint_orders_by_count_desc(self, app_with_cpi_admin):
        window_end = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
        service = MagicMock()
        service.get_actions = AsyncMock(
            return_value={
                "actions": [
                    {"action": "export", "count": 5},
                    {"action": "deploy", "count": 3},
                    {"action": "update", "count": 1},
                ],
                "window_start": window_end - timedelta(days=30),
                "window_end": window_end,
            }
        )

        with patch(AUDIT_SERVICE_PATH, return_value=service), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/actions")

        assert resp.status_code == 200
        counts = [item["count"] for item in resp.json()["actions"]]
        assert counts == [5, 3, 1]


class TestAuditDemoFallbackGate:
    """Tests for STOA_AUDIT_DEMO_FALLBACK gating."""

    def test_demo_fallback_disabled_when_env_false(self, app_with_cpi_admin, monkeypatch):
        service = MagicMock()
        service.list_events = AsyncMock(side_effect=RuntimeError("pg down"))
        monkeypatch.setattr("src.routers.audit.settings.STOA_AUDIT_DEMO_FALLBACK", False)

        mock_os = _make_os_mock()
        with patch(AUDIT_SERVICE_PATH, return_value=service), patch(OS_SVC_PATH, mock_os), TestClient(
            app_with_cpi_admin
        ) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"] == []
        assert data["total"] == 0
        assert data.get("source") is None
        assert data.get("warning") is None

    def test_demo_fallback_enabled_when_env_true_emits_source_demo(self, app_with_cpi_admin, monkeypatch):
        service = MagicMock()
        service.list_events = AsyncMock(side_effect=RuntimeError("pg down"))
        monkeypatch.setattr("src.routers.audit.settings.STOA_AUDIT_DEMO_FALLBACK", True)

        mock_os = _make_os_mock()
        with patch(AUDIT_SERVICE_PATH, return_value=service), patch(OS_SVC_PATH, mock_os), TestClient(
            app_with_cpi_admin
        ) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "demo"
        assert data["warning"] == "Audit backend unavailable"
        assert data["total"] >= 1

    def test_stats_demo_fallback_enabled_emits_source_demo(self, app_with_cpi_admin, monkeypatch):
        service = MagicMock()
        service.get_stats = AsyncMock(side_effect=RuntimeError("pg down"))
        monkeypatch.setattr("src.routers.audit.settings.STOA_AUDIT_DEMO_FALLBACK", True)

        mock_os = _make_os_mock()
        with patch(AUDIT_SERVICE_PATH, return_value=service), patch(OS_SVC_PATH, mock_os), TestClient(
            app_with_cpi_admin
        ) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/stats?action=api_call")

        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "demo"
        assert data["warning"] == "Audit backend unavailable"
        assert data["by_action"] == {"api_call": data["total_events"]}

    def test_actions_demo_fallback_disabled_returns_empty(self, app_with_cpi_admin, monkeypatch):
        service = MagicMock()
        service.get_actions = AsyncMock(side_effect=RuntimeError("pg down"))
        monkeypatch.setattr("src.routers.audit.settings.STOA_AUDIT_DEMO_FALLBACK", False)

        mock_os = _make_os_mock()
        with patch(AUDIT_SERVICE_PATH, return_value=service), patch(OS_SVC_PATH, mock_os), TestClient(
            app_with_cpi_admin
        ) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/actions")

        assert resp.status_code == 200
        data = resp.json()
        assert data["actions"] == []
        assert data.get("source") is None
        assert data.get("warning") is None


class TestAuditDemoHelpers:
    """Direct coverage for explicit demo fallback helpers."""

    def test_demo_stats_helper_filters_and_emits_warning(self):
        result = audit_router._demo_audit_stats_response(
            DEMO_TENANT,
            action="api_call",
            resource_type="tool",
            search="oasis",
        )

        assert result.source == "demo"
        assert result.warning == "Audit backend unavailable"
        assert result.total_events >= 1
        assert set(result.by_action) == {"api_call"}
        assert result.by_status["success"] >= 1

    def test_demo_actions_helper_orders_actions(self):
        result = audit_router._demo_audit_actions_response(DEMO_TENANT)

        assert result.source == "demo"
        assert result.warning == "Audit backend unavailable"
        assert result.actions
        assert result.actions[0].count >= result.actions[-1].count


class TestAuditOpenSearchHelpers:
    """Direct coverage for OpenSearch audit fallback helpers."""

    @pytest.mark.asyncio
    async def test_query_opensearch_audit_maps_entries_and_actor_resolution(self):
        client = MagicMock()
        client.search = AsyncMock(
            return_value={
                "hits": {
                    "total": {"value": 1},
                    "hits": [
                        {
                            "_id": "os-1",
                            "_source": {
                                "@timestamp": "2026-05-08T12:00:00+00:00",
                                "event_id": "event-1",
                                "tenant_id": DEMO_TENANT,
                                "actor": {
                                    "id": "user-123",
                                    "email": None,
                                    "ip_address": "192.0.2.10",
                                    "user_agent": "pytest",
                                },
                                "action": "export",
                                "resource": {"type": "report", "id": "rpt-1"},
                                "outcome": "success",
                                "details": {"source": "opensearch"},
                                "correlation_id": "req-1",
                            },
                        }
                    ],
                }
            }
        )
        actor = SimpleNamespace(user_email="alice@example.com", user_display_name="Alice Nguyen", resolved=True)

        with patch("src.routers.audit.resolve_actor", AsyncMock(return_value=actor)):
            result = await audit_router._query_opensearch_audit(
                client,
                DEMO_TENANT,
                1,
                50,
                action="export",
                status="success",
                resource_type="report",
                start_date=datetime(2026, 5, 1, tzinfo=UTC),
                end_date=datetime(2026, 5, 8, tzinfo=UTC),
                search="report",
            )

        assert result is not None
        assert result.total == 1
        assert result.entries[0].user_email == "alice@example.com"
        assert result.entries[0].user_display_name == "Alice Nguyen"
        assert result.entries[0].user_resolved is True
        body = client.search.await_args.kwargs["body"]
        must = body["query"]["bool"]["must"]
        assert {"term": {"action.keyword": "export"}} in must
        assert {"term": {"outcome.keyword": "success"}} in must
        assert {"term": {"resource.type.keyword": "report"}} in must
        assert any("multi_match" in item for item in must)

    @pytest.mark.asyncio
    async def test_query_opensearch_audit_stats_returns_aggregates(self):
        client = MagicMock()
        client.search = AsyncMock(
            return_value={
                "hits": {"total": {"value": 3}},
                "aggregations": {
                    "by_action": {"buckets": [{"key": "export", "doc_count": 2}, {"key": "deploy", "doc_count": 1}]},
                    "by_status": {"buckets": [{"key": "success", "doc_count": 2}, {"key": "failure", "doc_count": 1}]},
                    "unique_actors": {"value": 2},
                    "success_count": {"doc_count": 2},
                },
            }
        )

        result = await audit_router._query_opensearch_audit_stats(
            client,
            DEMO_TENANT,
            action="export",
            status="success",
            resource_type="report",
            search="report",
        )

        assert result is not None
        assert result.total_events == 3
        assert result.success_count == 2
        assert result.failed_count == 1
        assert result.unique_actors == 2
        assert result.by_action == {"export": 2, "deploy": 1}
        assert result.by_status == {"success": 2, "failure": 1}

    @pytest.mark.asyncio
    async def test_query_opensearch_audit_actions_returns_top_actions(self):
        client = MagicMock()
        client.search = AsyncMock(
            return_value={
                "aggregations": {
                    "actions": {
                        "buckets": [
                            {"key": "export", "doc_count": 5},
                            {"key": "deploy", "doc_count": 2},
                        ]
                    }
                }
            }
        )

        result = await audit_router._query_opensearch_audit_actions(client, DEMO_TENANT)

        assert result is not None
        assert [item.action for item in result.actions] == ["export", "deploy"]
        assert [item.count for item in result.actions] == [5, 2]


class TestExportAuditCsv:
    """Tests for GET /v1/audit/{tenant_id}/export/csv."""

    def test_export_csv_success(self, app_with_cpi_admin, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/export/csv")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["Content-Disposition"]

    def test_export_csv_has_header_row(self, app_with_cpi_admin, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/export/csv")

        assert "Timestamp" in resp.text
        assert "Action" in resp.text

    def test_export_csv_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_no_tenant_user) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/export/csv")

        assert resp.status_code == 403


class TestExportAuditJson:
    """Tests for GET /v1/audit/{tenant_id}/export/json."""

    def test_export_json_success(self, app_with_cpi_admin, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/export/json")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        assert "attachment" in resp.headers["Content-Disposition"]

    def test_export_json_expected_keys(self, app_with_cpi_admin, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/export/json")

        data = _json.loads(resp.text)
        assert "tenant_id" in data
        assert "entries" in data
        assert "total_entries" in data
        assert data["tenant_id"] == DEMO_TENANT

    def test_export_json_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_no_tenant_user) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/export/json")

        assert resp.status_code == 403


class TestGetSecurityEvents:
    """Tests for GET /v1/audit/{tenant_id}/security."""

    def test_security_events_success(self, app_with_cpi_admin, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/security")

        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "summary" in data

    def test_security_events_filter_severity(self, app_with_cpi_admin, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/security?severity=warning")

        assert resp.status_code == 200
        for event in resp.json()["events"]:
            assert event["severity"] == "warning"

    def test_security_events_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_no_tenant_user) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/security")

        assert resp.status_code == 403


class TestTenantIsolationTest:
    """Tests for GET /v1/audit/{tenant_id}/isolation-test."""

    def test_isolation_same_tenant_allowed(self, app_with_cpi_admin, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/isolation-test?target_tenant={DEMO_TENANT}")

        assert resp.status_code == 200
        assert resp.json()["status"] == "allowed"

    def test_isolation_cross_tenant_blocked(self, app_with_cpi_admin, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/isolation-test?target_tenant=high-five")

        assert resp.status_code == 403
        assert "tenant_isolation_violation" in str(resp.json()["detail"])

    def test_isolation_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_no_tenant_user) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/isolation-test?target_tenant={DEMO_TENANT}")

        assert resp.status_code == 403


class TestGetGlobalAuditSummary:
    """Tests for GET /v1/audit/global/summary."""

    def test_global_summary_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        with TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/audit/global/summary")

        assert resp.status_code == 200
        data = resp.json()
        assert "total_audit_entries" in data
        assert "total_security_events" in data
        assert "entries_by_tenant" in data

    def test_global_summary_403_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/audit/global/summary")

        assert resp.status_code == 403

    def test_global_summary_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get("/v1/audit/global/summary")

        assert resp.status_code == 403


class TestRbacTightening:
    """RBAC enforcement: viewer/devops with valid tenant get 403 on exports and security events."""

    def test_viewer_can_list_audit_entries(self, app_with_viewer, mock_db_session):
        """Viewer can still read paginated audit entries (low-risk)."""
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_viewer) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}")
        assert resp.status_code == 200

    def test_viewer_403_export_csv(self, app_with_viewer, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_viewer) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/export/csv")
        assert resp.status_code == 403

    def test_viewer_403_export_json(self, app_with_viewer, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_viewer) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/export/json")
        assert resp.status_code == 403

    def test_viewer_403_security_events(self, app_with_viewer, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_viewer) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/security")
        assert resp.status_code == 403

    def test_devops_403_export_csv(self, app_with_devops, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_devops) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/export/csv")
        assert resp.status_code == 403

    def test_devops_403_security_events(self, app_with_devops, mock_db_session):
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_devops) as client:
            resp = client.get(f"/v1/audit/{DEMO_TENANT}/security")
        assert resp.status_code == 403

    def test_tenant_admin_200_export_csv(self, app_with_tenant_admin, mock_db_session):
        """tenant-admin should still have export access (tenant acme)."""
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/audit/acme/export/csv")
        assert resp.status_code == 200

    def test_tenant_admin_200_security_events(self, app_with_tenant_admin, mock_db_session):
        """tenant-admin should still have security events access (tenant acme)."""
        mock_os = _make_os_mock()
        with patch(OS_SVC_PATH, mock_os), TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/audit/acme/security")
        assert resp.status_code == 200
