"""
Tests for Catalog Admin Router - CAB-1116 Phase 2B

Target: Coverage of src/routers/catalog_admin.py
Tests: 18 test cases covering sync triggers, status, history, stats, cache, and seed.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

SYNC_UUID = uuid4()


def _mock_sync_status(status="success", sync_id=None):
    """Create a mock sync status object."""
    mock = MagicMock()
    mock.id = sync_id or SYNC_UUID
    mock.status = status
    mock.sync_type = "full"
    mock.tenant_id = None
    mock.started_at = "2026-01-01T00:00:00Z"
    mock.completed_at = "2026-01-01T00:01:00Z"
    mock.items_synced = 10
    mock.items_failed = 0
    mock.errors = []
    mock.duration_ms = 60000
    return mock


def _mock_sync_status_response():
    """Create a mock SyncStatusResponse for from_db_model."""
    from src.schemas.catalog import SyncStatusResponse

    return SyncStatusResponse(
        id=SYNC_UUID,
        status="success",
        sync_type="full",
        tenant_id=None,
        started_at="2026-01-01T00:00:00Z",
        completed_at="2026-01-01T00:01:00Z",
        items_synced=10,
        items_failed=0,
        errors=[],
        duration_ms=60000,
    )


class TestCatalogAdminSync:
    """Test sync trigger endpoints."""

    def test_trigger_sync_success(self, app_with_cpi_admin, mock_db_session):
        """CPI admin can trigger full catalog sync."""
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("src.routers.catalog_admin.CatalogSyncService") as MockService, \
             patch("src.routers.catalog_admin.get_async_db", return_value=mock_ctx):
            svc = MockService.return_value
            svc.get_last_sync_status = AsyncMock(return_value=None)
            svc.sync_all = AsyncMock()

            with TestClient(app_with_cpi_admin) as client:
                response = client.post("/v1/admin/catalog/sync")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sync_started"

    def test_trigger_sync_already_running(self, app_with_cpi_admin, mock_db_session):
        """Returns sync_already_running when sync is in progress."""
        running_sync = _mock_sync_status(status="running")

        with patch("src.routers.catalog_admin.CatalogSyncService") as MockService:
            svc = MockService.return_value
            svc.get_last_sync_status = AsyncMock(return_value=running_sync)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post("/v1/admin/catalog/sync")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sync_already_running"

    def test_trigger_sync_viewer_forbidden(self, app, mock_db_session):
        """Viewer role cannot trigger sync."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db
        from tests.conftest import User

        async def override_user():
            return User(
                id="viewer-id",
                email="viewer@acme.com",
                username="viewer",
                roles=["viewer"],
                tenant_id="acme",
            )

        async def override_db():
            yield mock_db_session

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db

        with TestClient(app) as client:
            response = client.post("/v1/admin/catalog/sync")

        app.dependency_overrides.clear()
        assert response.status_code == 403

    def test_trigger_mcp_servers_sync(self, app_with_cpi_admin, mock_db_session):
        """CPI admin can trigger MCP servers sync."""
        # Patch get_db generator used inside background task
        async def mock_get_db():
            yield mock_db_session

        with patch("src.routers.catalog_admin.CatalogSyncService") as MockService, \
             patch("src.routers.catalog_admin.get_async_db", mock_get_db):
            svc = MockService.return_value
            svc.sync_mcp_servers = AsyncMock()

            with TestClient(app_with_cpi_admin) as client:
                response = client.post("/v1/admin/catalog/sync/mcp-servers")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sync_started"

    def test_trigger_tenant_sync_own_tenant(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin can sync their own tenant."""
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("src.routers.catalog_admin.CatalogSyncService") as MockService, \
             patch("src.routers.catalog_admin.get_async_db", return_value=mock_ctx):
            svc = MockService.return_value
            svc.sync_tenant = AsyncMock()

            with TestClient(app_with_tenant_admin) as client:
                response = client.post("/v1/admin/catalog/sync/tenant/acme")

        assert response.status_code == 200

    def test_trigger_tenant_sync_cross_tenant_forbidden(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin cannot sync another tenant."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.post("/v1/admin/catalog/sync/tenant/other-tenant")

        assert response.status_code == 403

    def test_trigger_tenant_sync_cpi_admin_any_tenant(self, app_with_cpi_admin, mock_db_session):
        """CPI admin can sync any tenant."""
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("src.routers.catalog_admin.CatalogSyncService") as MockService, \
             patch("src.routers.catalog_admin.get_async_db", return_value=mock_ctx):
            svc = MockService.return_value
            svc.sync_tenant = AsyncMock()

            with TestClient(app_with_cpi_admin) as client:
                response = client.post("/v1/admin/catalog/sync/tenant/any-tenant")

        assert response.status_code == 200


class TestCatalogAdminStatus:
    """Test sync status and history endpoints."""

    def test_get_sync_status_success(self, app_with_cpi_admin, mock_db_session):
        """Get last sync status."""
        mock_status = _mock_sync_status()
        mock_response = _mock_sync_status_response()

        with patch("src.routers.catalog_admin.CatalogSyncService") as MockService:
            svc = MockService.return_value
            svc.get_last_sync_status = AsyncMock(return_value=mock_status)
            with patch("src.schemas.catalog.SyncStatusResponse.from_db_model", return_value=mock_response), \
                 TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/catalog/sync/status")

        assert response.status_code == 200

    def test_get_sync_status_no_syncs(self, app_with_cpi_admin, mock_db_session):
        """Returns 404 when no syncs exist."""
        with patch("src.routers.catalog_admin.CatalogSyncService") as MockService:
            svc = MockService.return_value
            svc.get_last_sync_status = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/catalog/sync/status")

        assert response.status_code == 404

    def test_get_sync_history(self, app_with_cpi_admin, mock_db_session):
        """Get sync history returns list."""
        mock_syncs = [_mock_sync_status(), _mock_sync_status(sync_id=uuid4())]
        mock_response = _mock_sync_status_response()

        with patch("src.routers.catalog_admin.CatalogSyncService") as MockService:
            svc = MockService.return_value
            svc.get_sync_history = AsyncMock(return_value=mock_syncs)
            with patch("src.schemas.catalog.SyncStatusResponse.from_db_model", return_value=mock_response), \
                 TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/catalog/sync/history")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2


class TestCatalogAdminStats:
    """Test catalog stats endpoint."""

    def test_get_stats_success(self, app_with_cpi_admin, mock_db_session):
        """Get catalog stats."""
        mock_stats = {
            "total_apis": 25,
            "published_apis": 20,
            "unpublished_apis": 5,
            "by_tenant": {"acme": 15, "beta": 10},
            "by_category": {"finance": 10, "weather": 15},
        }

        with patch("src.routers.catalog_admin.CatalogRepository") as MockRepo, \
             patch("src.routers.catalog_admin.CatalogSyncService") as MockService:
            repo = MockRepo.return_value
            repo.get_stats = AsyncMock(return_value=mock_stats)
            svc = MockService.return_value
            svc.get_last_sync_status = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/catalog/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_apis"] == 25
        assert data["published_apis"] == 20

    def test_get_stats_viewer_forbidden(self, app, mock_db_session):
        """Viewer cannot access stats."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db
        from tests.conftest import User

        async def override_user():
            return User(
                id="viewer-id",
                email="viewer@acme.com",
                username="viewer",
                roles=["viewer"],
                tenant_id="acme",
            )

        async def override_db():
            yield mock_db_session

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db

        with TestClient(app) as client:
            response = client.get("/v1/admin/catalog/stats")

        app.dependency_overrides.clear()
        assert response.status_code == 403


class TestCatalogAdminCache:
    """Test cache invalidation endpoint."""

    def test_invalidate_cache_cpi_admin(self, app_with_cpi_admin):
        """CPI admin can invalidate cache."""
        with TestClient(app_with_cpi_admin) as client:
            response = client.delete("/v1/admin/catalog/cache")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_invalidate_cache_tenant_admin_forbidden(self, app_with_tenant_admin):
        """Tenant admin cannot invalidate cache."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.delete("/v1/admin/catalog/cache")

        assert response.status_code == 403


class TestCatalogAdminSeed:
    """Test catalog seed endpoint."""

    def test_seed_catalog_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        """CPI admin can seed catalog."""
        mock_db_session.execute = AsyncMock()
        mock_db_session.commit = AsyncMock()

        with TestClient(app_with_cpi_admin) as client:
            response = client.post(
                "/v1/admin/catalog/seed",
                json={
                    "tenant_id": "acme",
                    "apis": [
                        {
                            "name": "weather-api",
                            "display_name": "Weather API",
                            "version": "1.0.0",
                            "description": "Get weather data",
                            "tags": ["portal:published"],
                        }
                    ],
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["seeded"] == 1
        assert data["failed"] == 0

    def test_seed_catalog_tenant_admin_forbidden(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin cannot seed catalog."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                "/v1/admin/catalog/seed",
                json={
                    "tenant_id": "acme",
                    "apis": [
                        {"name": "test", "display_name": "Test"},
                    ],
                },
            )

        assert response.status_code == 403
