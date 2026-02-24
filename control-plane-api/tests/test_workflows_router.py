"""Tests for Workflows Router — CAB-593

Covers: /v1/tenants/{tenant_id}/workflows templates CRUD,
        instances lifecycle (start, list, get, approve, reject),
        and audit trail.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

WF_SVC_PATH = "src.routers.workflows.WorkflowService"

TENANT_ID = "acme"
BASE_URL = f"/v1/tenants/{TENANT_ID}/workflows"


# ============== Mock Factories ==============


def _make_template(**overrides):
    """Build a MagicMock that mimics a WorkflowTemplate ORM object."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "tenant_id": TENANT_ID,
        "workflow_type": "user_registration",
        "name": "Test Workflow",
        "description": "Test template description",
        "mode": "manual",
        "approval_steps": [],
        "auto_provision": "true",
        "notification_config": {},
        "sector": None,
        "is_active": "true",
        "created_by": "tenant-admin-user-id",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_instance(**overrides):
    """Build a MagicMock that mimics a WorkflowInstance ORM object."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "template_id": uuid4(),
        "tenant_id": TENANT_ID,
        "workflow_type": "user_registration",
        "subject_id": "user-subject-001",
        "subject_email": "subject@example.com",
        "status": "pending",
        "current_step_index": 0,
        "context": {},
        "initiated_by": "tenant-admin-user-id",
        "completed_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_audit_entry(**overrides):
    """Build a MagicMock that mimics a WorkflowAuditLog ORM object."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "instance_id": uuid4(),
        "event_type": "step_approved",
        "actor_id": "tenant-admin-user-id",
        "details": {"comment": "Looks good"},
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_template_response(template):
    """Build a mock TemplateResponse that FastAPI can serialize."""
    resp = MagicMock()
    resp.id = template.id
    resp.tenant_id = template.tenant_id
    resp.workflow_type = template.workflow_type
    resp.name = template.name
    resp.description = template.description
    resp.mode = template.mode
    resp.approval_steps = template.approval_steps
    resp.auto_provision = template.auto_provision
    resp.notification_config = template.notification_config
    resp.sector = template.sector
    resp.is_active = template.is_active
    resp.created_at = template.created_at
    resp.updated_at = template.updated_at
    resp.created_by = template.created_by
    return resp


def _make_instance_response(instance):
    """Build a mock InstanceResponse that FastAPI can serialize."""
    resp = MagicMock()
    resp.id = instance.id
    resp.template_id = instance.template_id
    resp.tenant_id = instance.tenant_id
    resp.workflow_type = instance.workflow_type
    resp.subject_id = instance.subject_id
    resp.subject_email = instance.subject_email
    resp.status = instance.status
    resp.current_step_index = instance.current_step_index
    resp.context = instance.context
    resp.initiated_by = instance.initiated_by
    resp.completed_at = instance.completed_at
    resp.created_at = instance.created_at
    resp.updated_at = instance.updated_at
    return resp


def _make_audit_response(entry):
    """Build a mock AuditResponse that FastAPI can serialize."""
    resp = MagicMock()
    resp.id = entry.id
    resp.instance_id = entry.instance_id
    resp.event_type = entry.event_type
    resp.actor_id = entry.actor_id
    resp.details = entry.details
    resp.created_at = entry.created_at
    return resp


# ============== Template CRUD ==============


class TestListTemplates:
    """GET /v1/tenants/{tenant_id}/workflows/templates"""

    def test_list_templates_empty(self, client_as_tenant_admin, mock_db_session):
        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.list_templates = AsyncMock(return_value=([], 0))
            resp = client_as_tenant_admin.get(f"{BASE_URL}/templates")

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    def test_list_templates_with_items(self, client_as_tenant_admin, mock_db_session):
        t1 = _make_template()
        t2 = _make_template(name="Second Workflow")

        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.list_templates = AsyncMock(return_value=([t1, t2], 2))

            with patch("src.routers.workflows.TemplateResponse") as MockResp:
                MockResp.model_validate.side_effect = [
                    _make_template_response(t1),
                    _make_template_response(t2),
                ]
                resp = client_as_tenant_admin.get(f"{BASE_URL}/templates")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_list_templates_pagination_params(self, client_as_tenant_admin, mock_db_session):
        with patch(WF_SVC_PATH) as MockSvc:
            mock_svc = MockSvc.return_value
            mock_svc.list_templates = AsyncMock(return_value=([], 0))

            resp = client_as_tenant_admin.get(f"{BASE_URL}/templates?page=2&page_size=10")

        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2
        assert data["page_size"] == 10
        mock_svc.list_templates.assert_called_once_with(TENANT_ID, workflow_type=None, page=2, page_size=10)

    def test_list_templates_workflow_type_filter(self, client_as_tenant_admin, mock_db_session):
        with patch(WF_SVC_PATH) as MockSvc:
            mock_svc = MockSvc.return_value
            mock_svc.list_templates = AsyncMock(return_value=([], 0))

            resp = client_as_tenant_admin.get(f"{BASE_URL}/templates?workflow_type=user_registration")

        assert resp.status_code == 200
        mock_svc.list_templates.assert_called_once_with(
            TENANT_ID, workflow_type="user_registration", page=1, page_size=50
        )

    def test_list_templates_as_cpi_admin(self, client_as_cpi_admin, mock_db_session):
        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.list_templates = AsyncMock(return_value=([], 0))
            resp = client_as_cpi_admin.get(f"{BASE_URL}/templates")

        assert resp.status_code == 200

    def test_list_templates_other_tenant_forbidden(self, client_as_other_tenant, mock_db_session):
        resp = client_as_other_tenant.get(f"{BASE_URL}/templates")
        assert resp.status_code == 403


class TestCreateTemplate:
    """POST /v1/tenants/{tenant_id}/workflows/templates"""

    def test_create_template_success(self, client_as_tenant_admin, mock_db_session):
        template = _make_template()

        with patch(WF_SVC_PATH) as MockSvc:
            mock_svc = MockSvc.return_value
            mock_svc.create_template = AsyncMock(return_value=template)

            with patch("src.routers.workflows.TemplateResponse") as MockResp:
                MockResp.model_validate.return_value = _make_template_response(template)
                resp = client_as_tenant_admin.post(
                    f"{BASE_URL}/templates",
                    json={
                        "workflow_type": "user_registration",
                        "name": "Test Workflow",
                        "mode": "manual",
                    },
                )

        assert resp.status_code == 201
        mock_svc.create_template.assert_called_once()
        call_kwargs = mock_svc.create_template.call_args.kwargs
        assert call_kwargs["tenant_id"] == TENANT_ID
        assert call_kwargs["workflow_type"] == "user_registration"
        assert call_kwargs["name"] == "Test Workflow"

    def test_create_template_with_approval_chain(self, client_as_tenant_admin, mock_db_session):
        template = _make_template(mode="approval_chain")

        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.create_template = AsyncMock(return_value=template)

            with patch("src.routers.workflows.TemplateResponse") as MockResp:
                MockResp.model_validate.return_value = _make_template_response(template)
                resp = client_as_tenant_admin.post(
                    f"{BASE_URL}/templates",
                    json={
                        "workflow_type": "consumer_registration",
                        "name": "Chain Workflow",
                        "mode": "approval_chain",
                        "approval_steps": [
                            {
                                "step_index": 0,
                                "role": "tenant-admin",
                                "label": "Manager Approval",
                            }
                        ],
                    },
                )

        assert resp.status_code == 201

    def test_create_template_invalid_type_422(self, client_as_tenant_admin, mock_db_session):
        resp = client_as_tenant_admin.post(
            f"{BASE_URL}/templates",
            json={
                "workflow_type": "invalid_type",
                "name": "Bad Workflow",
                "mode": "manual",
            },
        )
        assert resp.status_code == 422

    def test_create_template_forbidden_for_viewer(self, app, mock_user_viewer, mock_db_session):
        """Viewer has WORKFLOWS_READ but NOT WORKFLOWS_MANAGE."""
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
                f"{BASE_URL}/templates",
                json={
                    "workflow_type": "user_registration",
                    "name": "Should Fail",
                    "mode": "auto",
                },
            )

        assert resp.status_code == 403

    def test_create_template_other_tenant_forbidden(self, client_as_other_tenant, mock_db_session):
        resp = client_as_other_tenant.post(
            f"{BASE_URL}/templates",
            json={"workflow_type": "user_registration", "name": "T", "mode": "manual"},
        )
        assert resp.status_code == 403


class TestGetTemplate:
    """GET /v1/tenants/{tenant_id}/workflows/templates/{template_id}"""

    def test_get_template_success(self, client_as_tenant_admin, mock_db_session):
        template = _make_template()

        with patch(WF_SVC_PATH) as MockSvc:
            mock_svc = MockSvc.return_value
            mock_svc.get_template = AsyncMock(return_value=template)

            with patch("src.routers.workflows.TemplateResponse") as MockResp:
                MockResp.model_validate.return_value = _make_template_response(template)
                resp = client_as_tenant_admin.get(f"{BASE_URL}/templates/{template.id}")

        assert resp.status_code == 200
        mock_svc.get_template.assert_called_once_with(TENANT_ID, template.id)

    def test_get_template_not_found(self, client_as_tenant_admin, mock_db_session):
        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.get_template = AsyncMock(return_value=None)
            resp = client_as_tenant_admin.get(f"{BASE_URL}/templates/{uuid4()}")

        assert resp.status_code == 404
        assert "Template not found" in resp.json()["detail"]

    def test_get_template_other_tenant_forbidden(self, client_as_other_tenant, mock_db_session):
        resp = client_as_other_tenant.get(f"{BASE_URL}/templates/{uuid4()}")
        assert resp.status_code == 403


class TestUpdateTemplate:
    """PUT /v1/tenants/{tenant_id}/workflows/templates/{template_id}"""

    def test_update_template_success(self, client_as_tenant_admin, mock_db_session):
        template = _make_template(name="Updated Name")

        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.update_template = AsyncMock(return_value=template)

            with patch("src.routers.workflows.TemplateResponse") as MockResp:
                MockResp.model_validate.return_value = _make_template_response(template)
                resp = client_as_tenant_admin.put(
                    f"{BASE_URL}/templates/{template.id}",
                    json={"name": "Updated Name"},
                )

        assert resp.status_code == 200
        MockSvc.return_value.update_template.assert_called_once()

    def test_update_template_not_found(self, client_as_tenant_admin, mock_db_session):
        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.update_template = AsyncMock(side_effect=ValueError("Template not found"))
            resp = client_as_tenant_admin.put(
                f"{BASE_URL}/templates/{uuid4()}",
                json={"name": "New Name"},
            )

        assert resp.status_code == 404
        assert "Template not found" in resp.json()["detail"]

    def test_update_template_partial_fields(self, client_as_tenant_admin, mock_db_session):
        template = _make_template(description="Updated desc")

        with patch(WF_SVC_PATH) as MockSvc:
            mock_svc = MockSvc.return_value
            mock_svc.update_template = AsyncMock(return_value=template)

            with patch("src.routers.workflows.TemplateResponse") as MockResp:
                MockResp.model_validate.return_value = _make_template_response(template)
                resp = client_as_tenant_admin.put(
                    f"{BASE_URL}/templates/{template.id}",
                    json={"description": "Updated desc"},
                )

        assert resp.status_code == 200
        call_kwargs = mock_svc.update_template.call_args.kwargs
        assert "description" in call_kwargs

    def test_update_template_other_tenant_forbidden(self, client_as_other_tenant, mock_db_session):
        resp = client_as_other_tenant.put(
            f"{BASE_URL}/templates/{uuid4()}",
            json={"name": "X"},
        )
        assert resp.status_code == 403


class TestDeleteTemplate:
    """DELETE /v1/tenants/{tenant_id}/workflows/templates/{template_id}"""

    def test_delete_template_success(self, client_as_tenant_admin, mock_db_session):
        template_id = uuid4()

        with patch(WF_SVC_PATH) as MockSvc:
            mock_svc = MockSvc.return_value
            mock_svc.delete_template = AsyncMock(return_value=None)

            resp = client_as_tenant_admin.delete(f"{BASE_URL}/templates/{template_id}")

        assert resp.status_code == 204
        mock_svc.delete_template.assert_called_once_with(TENANT_ID, template_id)

    def test_delete_template_not_found(self, client_as_tenant_admin, mock_db_session):
        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.delete_template = AsyncMock(side_effect=ValueError("Template not found"))
            resp = client_as_tenant_admin.delete(f"{BASE_URL}/templates/{uuid4()}")

        assert resp.status_code == 404
        assert "Template not found" in resp.json()["detail"]

    def test_delete_template_other_tenant_forbidden(self, client_as_other_tenant, mock_db_session):
        resp = client_as_other_tenant.delete(f"{BASE_URL}/templates/{uuid4()}")
        assert resp.status_code == 403


# ============== Instances ==============


class TestStartWorkflow:
    """POST /v1/tenants/{tenant_id}/workflows/instances"""

    def test_start_workflow_success(self, client_as_tenant_admin, mock_db_session):
        template_id = uuid4()
        instance = _make_instance(template_id=template_id)

        with patch(WF_SVC_PATH) as MockSvc:
            mock_svc = MockSvc.return_value
            mock_svc.start_workflow = AsyncMock(return_value=instance)

            with patch("src.routers.workflows.InstanceResponse") as MockResp:
                MockResp.model_validate.return_value = _make_instance_response(instance)
                resp = client_as_tenant_admin.post(
                    f"{BASE_URL}/instances",
                    json={
                        "template_id": str(template_id),
                        "subject_id": "user-subject-001",
                        "subject_email": "subject@example.com",
                        "context": {"key": "value"},
                    },
                )

        assert resp.status_code == 201
        call_kwargs = mock_svc.start_workflow.call_args.kwargs
        assert call_kwargs["tenant_id"] == TENANT_ID
        assert call_kwargs["subject_id"] == "user-subject-001"

    def test_start_workflow_invalid(self, client_as_tenant_admin, mock_db_session):
        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.start_workflow = AsyncMock(side_effect=ValueError("Template not found or inactive"))
            resp = client_as_tenant_admin.post(
                f"{BASE_URL}/instances",
                json={
                    "template_id": str(uuid4()),
                    "subject_id": "user-001",
                },
            )

        assert resp.status_code == 400
        assert "Template not found or inactive" in resp.json()["detail"]

    def test_start_workflow_missing_subject_id_422(self, client_as_tenant_admin, mock_db_session):
        resp = client_as_tenant_admin.post(
            f"{BASE_URL}/instances",
            json={"template_id": str(uuid4())},
        )
        assert resp.status_code == 422

    def test_start_workflow_other_tenant_forbidden(self, client_as_other_tenant, mock_db_session):
        resp = client_as_other_tenant.post(
            f"{BASE_URL}/instances",
            json={"template_id": str(uuid4()), "subject_id": "x"},
        )
        assert resp.status_code == 403


class TestListInstances:
    """GET /v1/tenants/{tenant_id}/workflows/instances"""

    def test_list_instances_empty(self, client_as_tenant_admin, mock_db_session):
        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.list_instances = AsyncMock(return_value=([], 0))
            resp = client_as_tenant_admin.get(f"{BASE_URL}/instances")

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_instances_with_items(self, client_as_tenant_admin, mock_db_session):
        i1 = _make_instance()
        i2 = _make_instance(status="in_progress")

        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.list_instances = AsyncMock(return_value=([i1, i2], 2))

            with patch("src.routers.workflows.InstanceResponse") as MockResp:
                MockResp.model_validate.side_effect = [
                    _make_instance_response(i1),
                    _make_instance_response(i2),
                ]
                resp = client_as_tenant_admin.get(f"{BASE_URL}/instances")

        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_list_instances_status_filter(self, client_as_tenant_admin, mock_db_session):
        with patch(WF_SVC_PATH) as MockSvc:
            mock_svc = MockSvc.return_value
            mock_svc.list_instances = AsyncMock(return_value=([], 0))

            resp = client_as_tenant_admin.get(f"{BASE_URL}/instances?status=pending")

        assert resp.status_code == 200
        mock_svc.list_instances.assert_called_once_with(
            TENANT_ID, workflow_type=None, status="pending", page=1, page_size=50
        )

    def test_list_instances_other_tenant_forbidden(self, client_as_other_tenant, mock_db_session):
        resp = client_as_other_tenant.get(f"{BASE_URL}/instances")
        assert resp.status_code == 403


class TestGetInstance:
    """GET /v1/tenants/{tenant_id}/workflows/instances/{instance_id}"""

    def test_get_instance_success(self, client_as_tenant_admin, mock_db_session):
        instance = _make_instance()

        with patch(WF_SVC_PATH) as MockSvc:
            mock_svc = MockSvc.return_value
            mock_svc.get_instance = AsyncMock(return_value=instance)

            with patch("src.routers.workflows.InstanceResponse") as MockResp:
                MockResp.model_validate.return_value = _make_instance_response(instance)
                resp = client_as_tenant_admin.get(f"{BASE_URL}/instances/{instance.id}")

        assert resp.status_code == 200
        mock_svc.get_instance.assert_called_once_with(TENANT_ID, instance.id)

    def test_get_instance_not_found(self, client_as_tenant_admin, mock_db_session):
        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.get_instance = AsyncMock(return_value=None)
            resp = client_as_tenant_admin.get(f"{BASE_URL}/instances/{uuid4()}")

        assert resp.status_code == 404
        assert "Workflow instance not found" in resp.json()["detail"]

    def test_get_instance_other_tenant_forbidden(self, client_as_other_tenant, mock_db_session):
        resp = client_as_other_tenant.get(f"{BASE_URL}/instances/{uuid4()}")
        assert resp.status_code == 403


# ============== Step Actions ==============


class TestApproveStep:
    """POST /v1/tenants/{tenant_id}/workflows/instances/{instance_id}/approve"""

    def test_approve_step_success(self, client_as_tenant_admin, mock_db_session):
        instance = _make_instance(status="in_progress", current_step_index=1)

        with patch(WF_SVC_PATH) as MockSvc:
            mock_svc = MockSvc.return_value
            mock_svc.approve_step = AsyncMock(return_value=instance)

            with patch("src.routers.workflows.InstanceResponse") as MockResp:
                MockResp.model_validate.return_value = _make_instance_response(instance)
                resp = client_as_tenant_admin.post(
                    f"{BASE_URL}/instances/{instance.id}/approve",
                    json={"comment": "Approved!"},
                )

        assert resp.status_code == 200
        mock_svc.approve_step.assert_called_once_with(TENANT_ID, instance.id, "tenant-admin-user-id", "Approved!")

    def test_approve_step_no_body(self, client_as_tenant_admin, mock_db_session):
        instance = _make_instance()

        with patch(WF_SVC_PATH) as MockSvc:
            mock_svc = MockSvc.return_value
            mock_svc.approve_step = AsyncMock(return_value=instance)

            with patch("src.routers.workflows.InstanceResponse") as MockResp:
                MockResp.model_validate.return_value = _make_instance_response(instance)
                # POST with no body -- comment should be None
                resp = client_as_tenant_admin.post(
                    f"{BASE_URL}/instances/{instance.id}/approve",
                )

        assert resp.status_code == 200
        mock_svc.approve_step.assert_called_once_with(TENANT_ID, instance.id, "tenant-admin-user-id", None)

    def test_approve_step_invalid(self, client_as_tenant_admin, mock_db_session):
        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.approve_step = AsyncMock(side_effect=ValueError("No pending step to approve"))
            resp = client_as_tenant_admin.post(
                f"{BASE_URL}/instances/{uuid4()}/approve",
                json={"comment": "approve"},
            )

        assert resp.status_code == 400
        assert "No pending step to approve" in resp.json()["detail"]

    def test_approve_step_other_tenant_forbidden(self, client_as_other_tenant, mock_db_session):
        resp = client_as_other_tenant.post(
            f"{BASE_URL}/instances/{uuid4()}/approve",
            json={},
        )
        assert resp.status_code == 403


class TestRejectStep:
    """POST /v1/tenants/{tenant_id}/workflows/instances/{instance_id}/reject"""

    def test_reject_step_success(self, client_as_tenant_admin, mock_db_session):
        instance = _make_instance(status="rejected")

        with patch(WF_SVC_PATH) as MockSvc:
            mock_svc = MockSvc.return_value
            mock_svc.reject_step = AsyncMock(return_value=instance)

            with patch("src.routers.workflows.InstanceResponse") as MockResp:
                MockResp.model_validate.return_value = _make_instance_response(instance)
                resp = client_as_tenant_admin.post(
                    f"{BASE_URL}/instances/{instance.id}/reject",
                    json={"comment": "Rejected due to policy"},
                )

        assert resp.status_code == 200
        mock_svc.reject_step.assert_called_once_with(
            TENANT_ID, instance.id, "tenant-admin-user-id", "Rejected due to policy"
        )

    def test_reject_step_no_body(self, client_as_tenant_admin, mock_db_session):
        instance = _make_instance(status="rejected")

        with patch(WF_SVC_PATH) as MockSvc:
            mock_svc = MockSvc.return_value
            mock_svc.reject_step = AsyncMock(return_value=instance)

            with patch("src.routers.workflows.InstanceResponse") as MockResp:
                MockResp.model_validate.return_value = _make_instance_response(instance)
                # POST with no body -- comment should be None
                resp = client_as_tenant_admin.post(
                    f"{BASE_URL}/instances/{instance.id}/reject",
                )

        assert resp.status_code == 200
        mock_svc.reject_step.assert_called_once_with(TENANT_ID, instance.id, "tenant-admin-user-id", None)

    def test_reject_step_invalid(self, client_as_tenant_admin, mock_db_session):
        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.reject_step = AsyncMock(
                side_effect=ValueError("Instance is not in a rejectable state")
            )
            resp = client_as_tenant_admin.post(
                f"{BASE_URL}/instances/{uuid4()}/reject",
                json={"comment": "nope"},
            )

        assert resp.status_code == 400
        assert "Instance is not in a rejectable state" in resp.json()["detail"]

    def test_reject_step_other_tenant_forbidden(self, client_as_other_tenant, mock_db_session):
        resp = client_as_other_tenant.post(
            f"{BASE_URL}/instances/{uuid4()}/reject",
            json={},
        )
        assert resp.status_code == 403


# ============== Audit Trail ==============


class TestGetAuditTrail:
    """GET /v1/tenants/{tenant_id}/workflows/audit/{instance_id}"""

    def test_audit_trail_empty(self, client_as_tenant_admin, mock_db_session):
        instance_id = uuid4()

        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.get_audit_log = AsyncMock(return_value=([], 0))
            resp = client_as_tenant_admin.get(f"{BASE_URL}/audit/{instance_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_audit_trail_with_entries(self, client_as_tenant_admin, mock_db_session):
        instance_id = uuid4()
        a1 = _make_audit_entry(instance_id=instance_id, event_type="step_approved")
        a2 = _make_audit_entry(instance_id=instance_id, event_type="step_rejected")

        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.get_audit_log = AsyncMock(return_value=([a1, a2], 2))

            with patch("src.routers.workflows.AuditResponse") as MockResp:
                MockResp.model_validate.side_effect = [
                    _make_audit_response(a1),
                    _make_audit_response(a2),
                ]
                resp = client_as_tenant_admin.get(f"{BASE_URL}/audit/{instance_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_audit_trail_pagination(self, client_as_tenant_admin, mock_db_session):
        instance_id = uuid4()

        with patch(WF_SVC_PATH) as MockSvc:
            mock_svc = MockSvc.return_value
            mock_svc.get_audit_log = AsyncMock(return_value=([], 0))

            resp = client_as_tenant_admin.get(f"{BASE_URL}/audit/{instance_id}?page=2&page_size=5")

        assert resp.status_code == 200
        mock_svc.get_audit_log.assert_called_once_with(instance_id, page=2, page_size=5)

    def test_audit_trail_other_tenant_forbidden(self, client_as_other_tenant, mock_db_session):
        resp = client_as_other_tenant.get(f"{BASE_URL}/audit/{uuid4()}")
        assert resp.status_code == 403

    def test_audit_trail_cpi_admin_access(self, client_as_cpi_admin, mock_db_session):
        instance_id = uuid4()

        with patch(WF_SVC_PATH) as MockSvc:
            MockSvc.return_value.get_audit_log = AsyncMock(return_value=([], 0))
            resp = client_as_cpi_admin.get(f"{BASE_URL}/audit/{instance_id}")

        assert resp.status_code == 200
