"""Tests for Audit Router — CAB-1452

Covers: /v1/audit (list, export CSV/JSON, security events, isolation test, global summary).

Strategy:
  - Mock OpenSearchService so client=None => demo data fallback
  - Demo data tenants: oasis, high-five, ioi
  - cpi-admin bypasses @require_tenant_access
  - Viewer with no tenant_id always gets 403
"""

import json as _json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

OS_SVC_PATH = "src.routers.audit.OpenSearchService"
DEMO_TENANT = "oasis"


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
