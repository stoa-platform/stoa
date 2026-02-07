"""
Tests for Audit Router - CAB-1116 Phase 2B

Target: Coverage of src/routers/audit.py
Tests: 15 test cases covering list, export, security events, isolation, and global summary.

Note: The audit router is not registered in the main app (it's a standalone module).
We create a standalone test app that includes it.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.routers.audit as audit_mod
from src.routers.audit import router as audit_router


def _clear_audit_data():
    """Reset in-memory audit data between tests."""
    audit_mod._demo_audit_entries.clear()
    audit_mod._demo_security_events.clear()


def _make_app(user_roles=None, user_tenant_id=None):
    """Create a minimal FastAPI app with the audit router and auth override."""
    from tests.conftest import User

    test_app = FastAPI()
    test_app.include_router(audit_router)

    from src.auth.dependencies import get_current_user

    user = User(
        id="test-user",
        email="test@example.com",
        username="test-user",
        roles=user_roles or ["cpi-admin"],
        tenant_id=user_tenant_id,
    )

    async def override_user():
        return user

    test_app.dependency_overrides[get_current_user] = override_user
    return test_app


class TestAuditRouter:
    """Test suite for Audit Router endpoints."""

    # ============== List Audit Entries ==============

    def test_list_audit_entries_success(self):
        """CPI admin can list audit entries for any tenant."""
        _clear_audit_data()
        app = _make_app()
        with TestClient(app) as client:
            response = client.get("/v1/audit/oasis")

        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "has_more" in data

    def test_list_audit_entries_pagination(self):
        """Pagination works correctly."""
        _clear_audit_data()
        app = _make_app()
        with TestClient(app) as client:
            response = client.get("/v1/audit/oasis?page=1&page_size=2")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_list_audit_entries_filter_action(self):
        """Filter by action type works."""
        _clear_audit_data()
        app = _make_app()
        with TestClient(app) as client:
            response = client.get("/v1/audit/oasis?action=api_call")

        assert response.status_code == 200
        data = response.json()
        for entry in data["entries"]:
            assert entry["action"] == "api_call"

    def test_list_audit_entries_filter_status(self):
        """Filter by status works."""
        _clear_audit_data()
        app = _make_app()
        with TestClient(app) as client:
            response = client.get("/v1/audit/oasis?status=success")

        assert response.status_code == 200
        data = response.json()
        for entry in data["entries"]:
            assert entry["status"] == "success"

    def test_list_audit_entries_tenant_isolation(self):
        """Tenant admin cannot access another tenant's audit log."""
        _clear_audit_data()
        app = _make_app(user_roles=["tenant-admin"], user_tenant_id="other-tenant")
        with TestClient(app) as client:
            response = client.get("/v1/audit/acme")

        assert response.status_code == 403

    def test_list_audit_entries_own_tenant(self):
        """Tenant admin can access their own tenant's audit log."""
        _clear_audit_data()
        app = _make_app(user_roles=["tenant-admin"], user_tenant_id="oasis")
        with TestClient(app) as client:
            response = client.get("/v1/audit/oasis")

        assert response.status_code == 200

    # ============== Export CSV ==============

    def test_export_csv_success(self):
        """CSV export returns valid CSV content."""
        _clear_audit_data()
        app = _make_app()
        with TestClient(app) as client:
            response = client.get("/v1/audit/oasis/export/csv")

        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        assert "Content-Disposition" in response.headers
        content = response.text
        lines = content.strip().split("\n")
        assert len(lines) >= 1  # At least header row
        assert "ID" in lines[0]

    def test_export_csv_tenant_isolation(self):
        """CSV export blocked for wrong tenant."""
        _clear_audit_data()
        app = _make_app(user_roles=["tenant-admin"], user_tenant_id="other-tenant")
        with TestClient(app) as client:
            response = client.get("/v1/audit/acme/export/csv")

        assert response.status_code == 403

    # ============== Export JSON ==============

    def test_export_json_success(self):
        """JSON export returns valid JSON content."""
        _clear_audit_data()
        app = _make_app()
        with TestClient(app) as client:
            response = client.get("/v1/audit/oasis/export/json")

        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")
        data = response.json()
        assert "tenant_id" in data
        assert data["tenant_id"] == "oasis"
        assert "entries" in data

    # ============== Security Events ==============

    def test_security_events_success(self):
        """CPI admin can retrieve security events."""
        _clear_audit_data()
        app = _make_app()
        with TestClient(app) as client:
            response = client.get("/v1/audit/oasis/security")

        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "total" in data
        assert "summary" in data

    def test_security_events_filter_severity(self):
        """Filter security events by severity."""
        _clear_audit_data()
        app = _make_app()
        with TestClient(app) as client:
            response = client.get("/v1/audit/oasis/security?severity=warning")

        assert response.status_code == 200
        data = response.json()
        for event in data["events"]:
            assert event["severity"] == "warning"

    def test_security_events_tenant_isolation(self):
        """Security events blocked for wrong tenant."""
        _clear_audit_data()
        app = _make_app(user_roles=["tenant-admin"], user_tenant_id="other-tenant")
        with TestClient(app) as client:
            response = client.get("/v1/audit/acme/security")

        assert response.status_code == 403

    # ============== Isolation Test ==============

    def test_isolation_test_same_tenant(self):
        """Same-tenant access is allowed."""
        _clear_audit_data()
        app = _make_app()
        with TestClient(app) as client:
            response = client.get("/v1/audit/oasis/isolation-test?target_tenant=oasis")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "allowed"

    def test_isolation_test_cross_tenant(self):
        """Cross-tenant access is blocked and logged."""
        _clear_audit_data()
        app = _make_app()
        with TestClient(app) as client:
            response = client.get("/v1/audit/oasis/isolation-test?target_tenant=ioi")

        assert response.status_code == 403
        data = response.json()
        assert data["detail"]["error"] == "tenant_isolation_violation"

    # ============== Global Summary ==============

    def test_global_summary_cpi_admin(self):
        """CPI admin can access global audit summary."""
        _clear_audit_data()
        app = _make_app()
        with TestClient(app) as client:
            response = client.get("/v1/audit/global/summary")

        assert response.status_code == 200
        data = response.json()
        assert "total_audit_entries" in data
        assert "total_security_events" in data
        assert "entries_by_tenant" in data

    def test_global_summary_tenant_admin_forbidden(self):
        """Tenant admin cannot access global audit summary."""
        _clear_audit_data()
        app = _make_app(user_roles=["tenant-admin"], user_tenant_id="acme")
        with TestClient(app) as client:
            response = client.get("/v1/audit/global/summary")

        assert response.status_code == 403
