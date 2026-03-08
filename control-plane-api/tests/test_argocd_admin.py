"""Tests for ArgoCD Admin router (CAB-1706 W3)"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.routers.argocd_admin import router

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _mock_user(roles: list[str]):
    """Create a mock user dependency override."""
    from src.auth.dependencies import User, get_current_user

    user = User(
        id="uid-1",
        username="admin@acme.com",
        email="admin@acme.com",
        roles=roles,
        tenant_id="acme",
    )

    async def override():
        return user

    return get_current_user, override


# ---------------------------------------------------------------------------
# Sync Endpoint
# ---------------------------------------------------------------------------


class TestSyncEndpoint:
    @pytest.mark.asyncio
    @patch("src.routers.argocd_admin.argocd_service")
    async def test_sync_success(self, mock_argocd):
        mock_argocd.sync_application = AsyncMock(return_value={"status": "ok"})
        app = _make_app()
        dep, override = _mock_user(["cpi-admin"])
        app.dependency_overrides[dep] = override

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/admin/argocd/sync/control-plane-api",
                json={"revision": "HEAD", "prune": False},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["application"] == "control-plane-api"
        assert data["status"] == "syncing"
        mock_argocd.sync_application.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sync_forbidden_for_viewer(self):
        app = _make_app()
        dep, override = _mock_user(["viewer"])
        app.dependency_overrides[dep] = override

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/admin/argocd/sync/control-plane-api")

        assert resp.status_code == 403
        assert "cpi-admin" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_sync_forbidden_for_devops(self):
        app = _make_app()
        dep, override = _mock_user(["devops"])
        app.dependency_overrides[dep] = override

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/admin/argocd/sync/control-plane-api")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch("src.routers.argocd_admin.argocd_service")
    async def test_sync_argocd_failure(self, mock_argocd):
        mock_argocd.sync_application = AsyncMock(side_effect=Exception("Connection refused"))
        app = _make_app()
        dep, override = _mock_user(["cpi-admin"])
        app.dependency_overrides[dep] = override

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/admin/argocd/sync/control-plane-api")

        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Diff Endpoint
# ---------------------------------------------------------------------------


class TestDiffEndpoint:
    @pytest.mark.asyncio
    @patch("src.routers.argocd_admin.argocd_service")
    async def test_diff_success(self, mock_argocd):
        mock_argocd.get_application_diff = AsyncMock(
            return_value={
                "application": "control-plane-api",
                "total_resources": 5,
                "diff_count": 1,
                "resources": [
                    {
                        "name": "deployment",
                        "namespace": "stoa-system",
                        "kind": "Deployment",
                        "group": "apps",
                        "status": "OutOfSync",
                        "health": "Healthy",
                        "diff": {"image": "v1.2.3 → v1.2.4"},
                    }
                ],
            }
        )
        app = _make_app()
        dep, override = _mock_user(["cpi-admin"])
        app.dependency_overrides[dep] = override

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/admin/argocd/diff/control-plane-api")

        assert resp.status_code == 200
        data = resp.json()
        assert data["diff_count"] == 1
        assert data["resources"][0]["status"] == "OutOfSync"

    @pytest.mark.asyncio
    async def test_diff_forbidden_for_tenant_admin(self):
        app = _make_app()
        dep, override = _mock_user(["tenant-admin"])
        app.dependency_overrides[dep] = override

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/admin/argocd/diff/control-plane-api")

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Status Endpoint
# ---------------------------------------------------------------------------


class TestStatusEndpoint:
    @pytest.mark.asyncio
    @patch("src.routers.argocd_admin.argocd_service")
    async def test_status_success(self, mock_argocd):
        mock_argocd.get_platform_status = AsyncMock(
            return_value={
                "status": "healthy",
                "components": [
                    {
                        "name": "control-plane-api",
                        "sync_status": "Synced",
                        "health_status": "Healthy",
                    }
                ],
                "checked_at": "2026-03-08T12:00:00Z",
            }
        )
        app = _make_app()
        dep, override = _mock_user(["cpi-admin"])
        app.dependency_overrides[dep] = override

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/admin/argocd/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert len(data["components"]) == 1

    @pytest.mark.asyncio
    async def test_status_forbidden_for_viewer(self):
        app = _make_app()
        dep, override = _mock_user(["viewer"])
        app.dependency_overrides[dep] = override

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/admin/argocd/status")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch("src.routers.argocd_admin.argocd_service")
    async def test_status_argocd_failure(self, mock_argocd):
        mock_argocd.get_platform_status = AsyncMock(side_effect=Exception("timeout"))
        app = _make_app()
        dep, override = _mock_user(["cpi-admin"])
        app.dependency_overrides[dep] = override

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/admin/argocd/status")

        assert resp.status_code == 502
