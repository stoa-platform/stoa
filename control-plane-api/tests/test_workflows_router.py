"""Smoke tests for workflow router endpoints (CAB-593 PR 4)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

SVC_PATH = "src.routers.workflows.WorkflowService"


def _mock_template(**overrides):
    """Create a mock WorkflowTemplate object."""
    t = MagicMock()
    t.id = overrides.get("id", uuid4())
    t.tenant_id = overrides.get("tenant_id", "acme")
    t.workflow_type = overrides.get("workflow_type", "user_registration")
    t.name = overrides.get("name", "Default Template")
    t.description = overrides.get("description", "Test template")
    t.mode = overrides.get("mode", "auto")
    t.approval_steps = overrides.get("approval_steps", [])
    t.auto_provision = overrides.get("auto_provision", "true")
    t.notification_config = overrides.get("notification_config", {})
    t.sector = overrides.get("sector")
    t.is_active = overrides.get("is_active", "true")
    t.created_at = overrides.get("created_at", datetime.utcnow())
    t.updated_at = overrides.get("updated_at", datetime.utcnow())
    t.created_by = overrides.get("created_by", "admin-user-id")
    return t


def _mock_instance(**overrides):
    """Create a mock WorkflowInstance object."""
    inst = MagicMock()
    inst.id = overrides.get("id", uuid4())
    inst.template_id = overrides.get("template_id", uuid4())
    inst.tenant_id = overrides.get("tenant_id", "acme")
    inst.workflow_type = overrides.get("workflow_type", "user_registration")
    inst.subject_id = overrides.get("subject_id", "user-123")
    inst.subject_email = overrides.get("subject_email", "user@example.com")
    inst.status = overrides.get("status", "pending")
    inst.current_step_index = overrides.get("current_step_index", 0)
    inst.context = overrides.get("context", {})
    inst.initiated_by = overrides.get("initiated_by", "admin-user-id")
    inst.completed_at = overrides.get("completed_at")
    inst.created_at = overrides.get("created_at", datetime.utcnow())
    inst.updated_at = overrides.get("updated_at", datetime.utcnow())
    return inst


def _mock_audit(**overrides):
    """Create a mock WorkflowAuditLog object."""
    a = MagicMock()
    a.id = overrides.get("id", uuid4())
    a.instance_id = overrides.get("instance_id", uuid4())
    a.event_type = overrides.get("event_type", "workflow.created")
    a.actor_id = overrides.get("actor_id", "admin-user-id")
    a.details = overrides.get("details", {})
    a.created_at = overrides.get("created_at", datetime.utcnow())
    return a


class TestListTemplates:
    """GET /v1/tenants/{tenant_id}/workflows/templates"""

    def test_list_templates_as_tenant_admin(self, client_as_tenant_admin, mock_db_session):
        tmpl = _mock_template()
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.list_templates = AsyncMock(return_value=([tmpl], 1))
            resp = client_as_tenant_admin.get("/v1/tenants/acme/workflows/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_templates_as_cpi_admin(self, client_as_cpi_admin, mock_db_session):
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.list_templates = AsyncMock(return_value=([], 0))
            resp = client_as_cpi_admin.get("/v1/tenants/acme/workflows/templates")
        assert resp.status_code == 200

    def test_list_templates_other_tenant_forbidden(self, client_as_other_tenant, mock_db_session):
        resp = client_as_other_tenant.get("/v1/tenants/acme/workflows/templates")
        assert resp.status_code == 403


class TestCreateTemplate:
    """POST /v1/tenants/{tenant_id}/workflows/templates"""

    def test_create_template_as_tenant_admin(self, client_as_tenant_admin, mock_db_session):
        tmpl = _mock_template()
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.create_template = AsyncMock(return_value=tmpl)
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/workflows/templates",
                json={
                    "workflow_type": "user_registration",
                    "name": "New Template",
                    "mode": "auto",
                },
            )
        assert resp.status_code == 201

    def test_create_template_forbidden_for_viewer(self, app, mock_user_viewer, mock_db_session):
        """Viewer has workflows:read but NOT workflows:manage."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db

        async def override_user():
            return mock_user_viewer

        async def override_db():
            yield mock_db_session

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db

        with TestClient(app) as client:
            resp = client.post(
                "/v1/tenants/acme/workflows/templates",
                json={
                    "workflow_type": "user_registration",
                    "name": "Should Fail",
                    "mode": "auto",
                },
            )
        assert resp.status_code == 403
        app.dependency_overrides.clear()


class TestGetTemplate:
    """GET /v1/tenants/{tenant_id}/workflows/templates/{template_id}"""

    def test_get_template_found(self, client_as_tenant_admin, mock_db_session):
        tmpl = _mock_template()
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.get_template = AsyncMock(return_value=tmpl)
            resp = client_as_tenant_admin.get(f"/v1/tenants/acme/workflows/templates/{tmpl.id}")
        assert resp.status_code == 200

    def test_get_template_not_found(self, client_as_tenant_admin, mock_db_session):
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.get_template = AsyncMock(return_value=None)
            resp = client_as_tenant_admin.get(f"/v1/tenants/acme/workflows/templates/{uuid4()}")
        assert resp.status_code == 404


class TestApproveReject:
    """POST /v1/tenants/{tenant_id}/workflows/instances/{id}/approve|reject"""

    def test_approve_step(self, client_as_tenant_admin, mock_db_session):
        inst = _mock_instance(status="approved")
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.approve_step = AsyncMock(return_value=inst)
            resp = client_as_tenant_admin.post(
                f"/v1/tenants/acme/workflows/instances/{inst.id}/approve",
                json={"comment": "Looks good"},
            )
        assert resp.status_code == 200

    def test_reject_step(self, client_as_tenant_admin, mock_db_session):
        inst = _mock_instance(status="rejected")
        with patch(SVC_PATH) as MockSvc:
            MockSvc.return_value.reject_step = AsyncMock(return_value=inst)
            resp = client_as_tenant_admin.post(
                f"/v1/tenants/acme/workflows/instances/{inst.id}/reject",
                json={"comment": "Needs revision"},
            )
        assert resp.status_code == 200
