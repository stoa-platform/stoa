"""Execution logs endpoint tests (CAB-1318).

Covers: list, filter, detail, taxonomy, portal endpoints, RBAC, pagination, empty states.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth import get_current_user
from src.database import get_db
from src.models.execution_log import ErrorCategory, ExecutionLog, ExecutionStatus
from src.routers.execution_logs import router

app = FastAPI()
app.include_router(router)


def _make_user(
    tenant_id: str = "tenant-1",
    roles: list[str] | None = None,
    consumer_id: str | None = None,
):
    """Create a mock user."""
    user = MagicMock()
    user.tenant_id = tenant_id
    user.roles = roles or ["tenant-admin"]
    user.consumer_id = consumer_id
    return user


def _make_execution(
    tenant_id: str = "tenant-1",
    status: ExecutionStatus = ExecutionStatus.SUCCESS,
    error_category: ErrorCategory | None = None,
    **kwargs,
) -> ExecutionLog:
    """Create a mock execution log."""
    log = ExecutionLog()
    log.id = kwargs.get("id", str(uuid.uuid4()))
    log.tenant_id = tenant_id
    log.consumer_id = kwargs.get("consumer_id")
    log.api_id = kwargs.get("api_id")
    log.api_name = kwargs.get("api_name", "Test API")
    log.tool_name = kwargs.get("tool_name")
    log.request_id = kwargs.get("request_id", f"req-{uuid.uuid4().hex[:8]}")
    log.method = kwargs.get("method", "GET")
    log.path = kwargs.get("path", "/v1/test")
    log.status_code = kwargs.get("status_code", 200 if status == ExecutionStatus.SUCCESS else 500)
    log.status = status
    log.error_category = error_category
    log.error_message = kwargs.get("error_message")
    log.started_at = kwargs.get("started_at", datetime.now(UTC))
    log.completed_at = kwargs.get("completed_at", datetime.now(UTC))
    log.duration_ms = kwargs.get("duration_ms", 42)
    log.request_headers = None
    log.response_summary = None
    return log


def _override_auth(user):
    """Create a dependency override for get_current_user."""

    async def _get_user():
        return user

    return _get_user


async def _override_db():
    yield AsyncMock()


@pytest.fixture(autouse=True)
def _reset_overrides():
    """Reset dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_executions():
    """List executions returns paginated results."""
    logs = [_make_execution(), _make_execution()]
    user = _make_user()
    app.dependency_overrides[get_current_user] = _override_auth(user)
    app.dependency_overrides[get_db] = _override_db

    with patch("src.routers.execution_logs.ExecutionLogRepository") as MockRepo:
        MockRepo.return_value.list_by_tenant = AsyncMock(return_value=(logs, 2))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/tenants/tenant-1/executions")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 20


@pytest.mark.asyncio
async def test_list_executions_with_status_filter():
    """List executions respects status filter."""
    user = _make_user()
    app.dependency_overrides[get_current_user] = _override_auth(user)
    app.dependency_overrides[get_db] = _override_db

    with patch("src.routers.execution_logs.ExecutionLogRepository") as MockRepo:
        MockRepo.return_value.list_by_tenant = AsyncMock(return_value=([], 0))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/tenants/tenant-1/executions?status=error")

    assert resp.status_code == 200
    MockRepo.return_value.list_by_tenant.assert_called_once()
    call_kwargs = MockRepo.return_value.list_by_tenant.call_args.kwargs
    assert call_kwargs["status"] == ExecutionStatus.ERROR


@pytest.mark.asyncio
async def test_list_executions_with_error_category_filter():
    """List executions respects error_category filter."""
    user = _make_user()
    app.dependency_overrides[get_current_user] = _override_auth(user)
    app.dependency_overrides[get_db] = _override_db

    with patch("src.routers.execution_logs.ExecutionLogRepository") as MockRepo:
        MockRepo.return_value.list_by_tenant = AsyncMock(return_value=([], 0))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/tenants/tenant-1/executions?error_category=auth")

    assert resp.status_code == 200
    call_kwargs = MockRepo.return_value.list_by_tenant.call_args.kwargs
    assert call_kwargs["error_category"] == ErrorCategory.AUTH


@pytest.mark.asyncio
async def test_list_executions_empty():
    """List executions returns empty state."""
    user = _make_user()
    app.dependency_overrides[get_current_user] = _override_auth(user)
    app.dependency_overrides[get_db] = _override_db

    with patch("src.routers.execution_logs.ExecutionLogRepository") as MockRepo:
        MockRepo.return_value.list_by_tenant = AsyncMock(return_value=([], 0))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/tenants/tenant-1/executions")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_get_execution_detail():
    """Get execution detail returns full data."""
    log = _make_execution(id="exec-123")
    user = _make_user()
    app.dependency_overrides[get_current_user] = _override_auth(user)
    app.dependency_overrides[get_db] = _override_db

    with patch("src.routers.execution_logs.ExecutionLogRepository") as MockRepo:
        MockRepo.return_value.get_by_id = AsyncMock(return_value=log)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/tenants/tenant-1/executions/exec-123")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "exec-123"
    assert data["api_name"] == "Test API"


@pytest.mark.asyncio
async def test_get_execution_detail_not_found():
    """Get execution detail returns 404 for missing log."""
    user = _make_user()
    app.dependency_overrides[get_current_user] = _override_auth(user)
    app.dependency_overrides[get_db] = _override_db

    with patch("src.routers.execution_logs.ExecutionLogRepository") as MockRepo:
        MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/tenants/tenant-1/executions/nonexistent")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_taxonomy():
    """Get error taxonomy returns aggregated data."""
    taxonomy_items = [
        {
            "category": "auth",
            "count": 10,
            "avg_duration_ms": 15.0,
            "percentage": 50.0,
        },
        {
            "category": "rate_limit",
            "count": 10,
            "avg_duration_ms": 8.0,
            "percentage": 50.0,
        },
    ]
    user = _make_user()
    app.dependency_overrides[get_current_user] = _override_auth(user)
    app.dependency_overrides[get_db] = _override_db

    with patch("src.routers.execution_logs.ExecutionLogRepository") as MockRepo:
        MockRepo.return_value.get_taxonomy = AsyncMock(return_value=(taxonomy_items, 20, 100))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/tenants/tenant-1/executions/taxonomy")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_errors"] == 20
    assert data["total_executions"] == 100
    assert data["error_rate"] == 20.0
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_get_taxonomy_empty():
    """Get taxonomy returns empty state."""
    user = _make_user()
    app.dependency_overrides[get_current_user] = _override_auth(user)
    app.dependency_overrides[get_db] = _override_db

    with patch("src.routers.execution_logs.ExecutionLogRepository") as MockRepo:
        MockRepo.return_value.get_taxonomy = AsyncMock(return_value=([], 0, 0))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/tenants/tenant-1/executions/taxonomy")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_errors"] == 0
    assert data["error_rate"] == 0


@pytest.mark.asyncio
async def test_list_executions_access_denied():
    """Non-tenant user cannot list executions."""
    user = _make_user(tenant_id="other-tenant", roles=["viewer"])
    app.dependency_overrides[get_current_user] = _override_auth(user)
    app.dependency_overrides[get_db] = _override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/v1/tenants/tenant-1/executions")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_executions_cpi_admin_access():
    """CPI admin can access any tenant's executions."""
    user = _make_user(tenant_id="other-tenant", roles=["cpi-admin"])
    app.dependency_overrides[get_current_user] = _override_auth(user)
    app.dependency_overrides[get_db] = _override_db

    with patch("src.routers.execution_logs.ExecutionLogRepository") as MockRepo:
        MockRepo.return_value.list_by_tenant = AsyncMock(return_value=([], 0))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/tenants/tenant-1/executions")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_my_executions():
    """Portal user can list their own executions."""
    logs = [_make_execution(consumer_id="consumer-1")]
    user = _make_user(consumer_id="consumer-1")
    app.dependency_overrides[get_current_user] = _override_auth(user)
    app.dependency_overrides[get_db] = _override_db

    with patch("src.routers.execution_logs.ExecutionLogRepository") as MockRepo:
        MockRepo.return_value.list_by_consumer = AsyncMock(return_value=(logs, 1))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/usage/me/executions")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_list_my_executions_no_consumer():
    """Portal user without consumer_id gets empty response."""
    user = _make_user(consumer_id=None)
    app.dependency_overrides[get_current_user] = _override_auth(user)
    app.dependency_overrides[get_db] = _override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/v1/usage/me/executions")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_my_taxonomy():
    """Portal user can get their error taxonomy."""
    taxonomy_items = [
        {
            "category": "auth",
            "count": 5,
            "avg_duration_ms": 10.0,
            "percentage": 100.0,
        },
    ]
    user = _make_user(consumer_id="consumer-1")
    app.dependency_overrides[get_current_user] = _override_auth(user)
    app.dependency_overrides[get_db] = _override_db

    with patch("src.routers.execution_logs.ExecutionLogRepository") as MockRepo:
        MockRepo.return_value.get_taxonomy = AsyncMock(return_value=(taxonomy_items, 5, 50))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/usage/me/executions/taxonomy")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_errors"] == 5
    assert data["error_rate"] == 10.0


@pytest.mark.asyncio
async def test_my_taxonomy_no_consumer():
    """Portal user without consumer_id gets empty taxonomy."""
    user = _make_user(consumer_id=None)
    app.dependency_overrides[get_current_user] = _override_auth(user)
    app.dependency_overrides[get_db] = _override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/v1/usage/me/executions/taxonomy")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_errors"] == 0
