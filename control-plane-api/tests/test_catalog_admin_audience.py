"""Tests for PATCH /v1/admin/catalog/{tenant_id}/{api_id}/audience (CAB-1323 Phase 3)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.auth.dependencies import User
from src.models.catalog import APICatalog
from src.routers.catalog_admin import router

# ---------- Fixtures ----------


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


def _make_user(role: str, tenant_id: str | None = None) -> User:
    return User(
        id=f"user-{role}",
        email=f"{role}@test.com",
        username=role,
        roles=[role],
        tenant_id=tenant_id,
    )


def _make_api_catalog(tenant_id: str = "oasis", api_id: str = "payment-api", audience: str = "public"):
    api = MagicMock(spec=APICatalog)
    api.id = uuid.uuid4()
    api.tenant_id = tenant_id
    api.api_id = api_id
    api.audience = audience
    return api


def _patch_deps(app: FastAPI, user: User, api_obj=None):
    """Patch auth + DB dependencies for the test app."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    async def override_user():
        return user

    async def override_db():
        return mock_db

    from src.auth.dependencies import get_current_user
    from src.database import get_db

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db

    return mock_db


# ---------- Tests ----------


@pytest.mark.asyncio
async def test_cpi_admin_can_update_audience(app):
    user = _make_user("cpi-admin")
    api_obj = _make_api_catalog()
    _patch_deps(app, user)

    with patch("src.routers.catalog_admin.CatalogRepository") as MockRepo:
        MockRepo.return_value.get_api_by_id = AsyncMock(return_value=api_obj)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.patch(
                "/v1/admin/catalog/oasis/payment-api/audience",
                json={"audience": "internal"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["audience"] == "internal"
    assert data["api_id"] == "payment-api"
    assert data["tenant_id"] == "oasis"
    assert data["updated_by"] == "cpi-admin"


@pytest.mark.asyncio
async def test_tenant_admin_can_update_own_tenant(app):
    user = _make_user("tenant-admin", tenant_id="oasis")
    api_obj = _make_api_catalog()
    _patch_deps(app, user)

    with patch("src.routers.catalog_admin.CatalogRepository") as MockRepo:
        MockRepo.return_value.get_api_by_id = AsyncMock(return_value=api_obj)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.patch(
                "/v1/admin/catalog/oasis/payment-api/audience",
                json={"audience": "partner"},
            )

    assert resp.status_code == 200
    assert resp.json()["audience"] == "partner"


@pytest.mark.asyncio
async def test_tenant_admin_cannot_update_other_tenant(app):
    user = _make_user("tenant-admin", tenant_id="other-tenant")
    _patch_deps(app, user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            "/v1/admin/catalog/oasis/payment-api/audience",
            json={"audience": "internal"},
        )

    assert resp.status_code == 403
    assert "Access denied" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_devops_cannot_update_audience(app):
    user = _make_user("devops", tenant_id="oasis")
    _patch_deps(app, user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            "/v1/admin/catalog/oasis/payment-api/audience",
            json={"audience": "internal"},
        )

    assert resp.status_code == 403
    assert "Admin access required" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_viewer_cannot_update_audience(app):
    user = _make_user("viewer", tenant_id="oasis")
    _patch_deps(app, user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            "/v1/admin/catalog/oasis/payment-api/audience",
            json={"audience": "internal"},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_invalid_audience_value(app):
    user = _make_user("cpi-admin")
    _patch_deps(app, user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            "/v1/admin/catalog/oasis/payment-api/audience",
            json={"audience": "secret"},
        )

    assert resp.status_code == 400
    assert "Invalid audience" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_not_found(app):
    user = _make_user("cpi-admin")
    _patch_deps(app, user)

    with patch("src.routers.catalog_admin.CatalogRepository") as MockRepo:
        MockRepo.return_value.get_api_by_id = AsyncMock(return_value=None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.patch(
                "/v1/admin/catalog/oasis/nonexistent-api/audience",
                json={"audience": "internal"},
            )

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_same_value_update_is_idempotent(app):
    user = _make_user("cpi-admin")
    api_obj = _make_api_catalog(audience="internal")
    _patch_deps(app, user)

    with patch("src.routers.catalog_admin.CatalogRepository") as MockRepo:
        MockRepo.return_value.get_api_by_id = AsyncMock(return_value=api_obj)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.patch(
                "/v1/admin/catalog/oasis/payment-api/audience",
                json={"audience": "internal"},
            )

    assert resp.status_code == 200
    assert resp.json()["audience"] == "internal"


@pytest.mark.asyncio
async def test_response_includes_all_fields(app):
    user = _make_user("cpi-admin")
    api_obj = _make_api_catalog()
    _patch_deps(app, user)

    with patch("src.routers.catalog_admin.CatalogRepository") as MockRepo:
        MockRepo.return_value.get_api_by_id = AsyncMock(return_value=api_obj)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.patch(
                "/v1/admin/catalog/oasis/payment-api/audience",
                json={"audience": "partner"},
            )

    data = resp.json()
    assert set(data.keys()) == {"api_id", "tenant_id", "audience", "updated_by"}
