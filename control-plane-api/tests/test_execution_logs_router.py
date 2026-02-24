"""Tests for Execution Logs Router — CAB-1318

Covers:
  - GET /v1/tenants/{tenant_id}/executions        (list_executions)
  - GET /v1/tenants/{tenant_id}/executions/taxonomy
  - GET /v1/tenants/{tenant_id}/executions/{id}   (get_execution_detail)
  - GET /v1/usage/me/executions                   (list_my_executions)
  - GET /v1/usage/me/executions/taxonomy          (get_my_execution_taxonomy)

RBAC: cpi-admin can access any tenant; other users only their own tenant.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

EXEC_REPO_PATH = "src.routers.execution_logs.ExecutionLogRepository"


def _mock_exec_log(**overrides):
    """Build a MagicMock resembling an ExecutionLog ORM row.

    Fields match ExecutionLogSummary (from_attributes=True) — all typed correctly
    so that Pydantic's model_validate succeeds.
    """
    mock = MagicMock()
    lid = str(uuid4())
    now = datetime.utcnow()
    defaults = {
        "id": lid,
        "tenant_id": "acme",
        "consumer_id": "consumer-1",
        "api_id": "api-1",
        "api_name": "Test API",
        "tool_name": "search",
        "request_id": str(uuid4()),
        "method": "POST",
        "path": "/tools/search",
        "status_code": 200,
        "status": "success",
        "error_category": None,
        "error_message": None,
        "started_at": now,
        "completed_at": now,
        "duration_ms": 42,
        # ExecutionLogResponse-specific optional fields (must be dict or None, not MagicMock)
        "request_headers": None,
        "response_summary": None,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


# ============== RBAC: tenant access guard ==============


class TestExecutionLogsRBAC:
    """_has_tenant_access: cpi-admin passes; wrong tenant gets 403."""

    def test_list_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.get("/v1/tenants/acme/executions")

        assert resp.status_code == 403
        assert "denied" in resp.json()["detail"].lower()

    def test_taxonomy_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.get("/v1/tenants/acme/executions/taxonomy")

        assert resp.status_code == 403

    def test_detail_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.get(f"/v1/tenants/acme/executions/{uuid4()}")

        assert resp.status_code == 403

    def test_list_200_as_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([], 0))

        with (
            patch(EXEC_REPO_PATH, return_value=mock_repo),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/tenants/any-tenant/executions")

        assert resp.status_code == 200

    def test_list_200_own_tenant(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([], 0))

        with (
            patch(EXEC_REPO_PATH, return_value=mock_repo),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/executions")

        assert resp.status_code == 200


# ============== list_executions ==============


class TestListExecutions:
    """GET /v1/tenants/{tenant_id}/executions"""

    def test_list_success_with_results(self, app_with_tenant_admin, mock_db_session):
        # Use a real ORM-like object with all required fields so Pydantic validates correctly
        log = _mock_exec_log()
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([log], 1))

        with (
            patch(EXEC_REPO_PATH, return_value=mock_repo),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/executions")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["page"] == 1
        assert data["page_size"] == 20

    def test_list_empty(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([], 0))

        with (
            patch(EXEC_REPO_PATH, return_value=mock_repo),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/executions")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []

    def test_list_passes_filters_to_repo(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([], 0))

        with (
            patch(EXEC_REPO_PATH, return_value=mock_repo),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(
                "/v1/tenants/acme/executions" "?status=success&consumer_id=consumer-1&api_id=api-1&page=2&page_size=10"
            )

        assert resp.status_code == 200
        call_kwargs = mock_repo.list_by_tenant.call_args.kwargs
        assert call_kwargs["consumer_id"] == "consumer-1"
        assert call_kwargs["api_id"] == "api-1"
        assert call_kwargs["page"] == 2
        assert call_kwargs["page_size"] == 10

    def test_list_pagination_defaults(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([], 0))

        with (
            patch(EXEC_REPO_PATH, return_value=mock_repo),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/executions")

        assert resp.status_code == 200
        call_kwargs = mock_repo.list_by_tenant.call_args.kwargs
        assert call_kwargs["page"] == 1
        assert call_kwargs["page_size"] == 20


# ============== get_execution_taxonomy ==============


class TestGetExecutionTaxonomy:
    """GET /v1/tenants/{tenant_id}/executions/taxonomy"""

    def test_taxonomy_success(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_taxonomy = AsyncMock(
            return_value=(
                [{"category": "timeout", "count": 3, "percentage": 60.0, "avg_duration_ms": None}],
                3,
                5,
            )
        )

        with (
            patch(EXEC_REPO_PATH, return_value=mock_repo),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/executions/taxonomy")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_errors"] == 3
        assert data["total_executions"] == 5
        assert data["error_rate"] == 60.0

    def test_taxonomy_zero_executions(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_taxonomy = AsyncMock(return_value=([], 0, 0))

        with (
            patch(EXEC_REPO_PATH, return_value=mock_repo),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/executions/taxonomy")

        assert resp.status_code == 200
        data = resp.json()
        # No division by zero: error_rate defaults to 0
        assert data["error_rate"] == 0
        assert data["items"] == []


# ============== get_execution_detail ==============


class TestGetExecutionDetail:
    """GET /v1/tenants/{tenant_id}/executions/{execution_id}"""

    def test_detail_success(self, app_with_tenant_admin, mock_db_session):
        # ExecutionLogResponse has additional fields (request_id, started_at) — provide all
        log = _mock_exec_log(tenant_id="acme")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=log)

        with (
            patch(EXEC_REPO_PATH, return_value=mock_repo),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(f"/v1/tenants/acme/executions/{log.id}")

        assert resp.status_code == 200

    def test_detail_404_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with (
            patch(EXEC_REPO_PATH, return_value=mock_repo),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(f"/v1/tenants/acme/executions/{uuid4()}")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_detail_404_wrong_tenant(self, app_with_tenant_admin, mock_db_session):
        # Log exists but belongs to a different tenant
        log = _mock_exec_log(tenant_id="other-tenant")
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=log)

        with (
            patch(EXEC_REPO_PATH, return_value=mock_repo),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(f"/v1/tenants/acme/executions/{log.id}")

        assert resp.status_code == 404


# ============== list_my_executions ==============


def _override_app_with_consumer(app, mock_db_session, consumer_id="consumer-1"):
    """Override get_current_user to return a MagicMock user with a consumer_id."""
    from src.auth.dependencies import get_current_user
    from src.database import get_db

    mock_user = MagicMock()
    mock_user.id = "portal-user"
    mock_user.email = "user@acme.com"
    mock_user.username = "portal-user"
    mock_user.roles = ["viewer"]
    mock_user.tenant_id = "acme"
    mock_user.consumer_id = consumer_id

    async def _override_user():
        return mock_user

    async def _override_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db
    return app


def _override_app_no_consumer(app, mock_db_session):
    """Override get_current_user to return a user with consumer_id=None."""
    from src.auth.dependencies import get_current_user
    from src.database import get_db

    mock_user = MagicMock()
    mock_user.id = "portal-user"
    mock_user.email = "user@acme.com"
    mock_user.username = "portal-user"
    mock_user.roles = ["viewer"]
    mock_user.tenant_id = "acme"
    mock_user.consumer_id = None

    async def _override_user():
        return mock_user

    async def _override_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db
    return app


class TestListMyExecutions:
    """GET /v1/usage/me/executions (portal, consumer-scoped)"""

    def test_my_executions_no_consumer_id_returns_empty(self, app, mock_db_session):
        """When user has no consumer_id, return empty list without hitting repo."""
        _override_app_no_consumer(app, mock_db_session)

        with TestClient(app) as client:
            resp = client.get("/v1/usage/me/executions")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_my_executions_success(self, app, mock_db_session):
        log = _mock_exec_log(consumer_id="consumer-1")
        mock_repo = MagicMock()
        mock_repo.list_by_consumer = AsyncMock(return_value=([log], 1))

        _override_app_with_consumer(app, mock_db_session)

        with (
            patch(EXEC_REPO_PATH, return_value=mock_repo),
            TestClient(app) as client,
        ):
            resp = client.get("/v1/usage/me/executions")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_my_executions_passes_pagination(self, app, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.list_by_consumer = AsyncMock(return_value=([], 0))

        _override_app_with_consumer(app, mock_db_session)

        with (
            patch(EXEC_REPO_PATH, return_value=mock_repo),
            TestClient(app) as client,
        ):
            resp = client.get("/v1/usage/me/executions?page=3&page_size=5")

        assert resp.status_code == 200
        call_kwargs = mock_repo.list_by_consumer.call_args.kwargs
        assert call_kwargs["page"] == 3
        assert call_kwargs["page_size"] == 5


# ============== get_my_execution_taxonomy ==============


class TestGetMyExecutionTaxonomy:
    """GET /v1/usage/me/executions/taxonomy (portal, consumer-scoped)"""

    def test_my_taxonomy_no_consumer_returns_empty(self, app, mock_db_session):
        """When user has no consumer_id, return zero-filled response."""
        _override_app_no_consumer(app, mock_db_session)

        with TestClient(app) as client:
            resp = client.get("/v1/usage/me/executions/taxonomy")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_errors"] == 0
        assert data["total_executions"] == 0
        assert data["items"] == []
