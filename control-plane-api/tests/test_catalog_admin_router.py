"""Tests for Catalog Admin Router — CAB-1452

Covers: /v1/admin/catalog (sync, sync/mcp-servers, sync/tenant, sync/status,
sync/history, stats, cache, seed, audience).

Admin check: _require_admin() requires cpi-admin or tenant-admin.
Viewers always get 403.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

SYNC_SVC_PATH = "src.routers.catalog_admin.CatalogSyncService"
CATALOG_REPO_PATH = "src.routers.catalog_admin.CatalogRepository"
GET_ASYNC_DB_PATH = "src.routers.catalog_admin.get_async_db"


async def _fake_get_db():
    """Mock async generator for get_db used by background tasks."""
    yield AsyncMock()


def _mock_sync_status(status: str = "success") -> MagicMock:
    s = MagicMock()
    s.id = uuid4()
    s.sync_type = "full"
    s.status = status
    s.started_at = datetime.now(UTC)
    s.completed_at = datetime.now(UTC)
    s.items_synced = 42
    s.errors = []
    s.git_commit_sha = "abc123"
    s.duration_seconds = 3.5
    return s


def _mock_catalog_api(tenant_id: str = "acme", api_id: str = "weather-api") -> MagicMock:
    api = MagicMock()
    api.id = uuid4()
    api.tenant_id = tenant_id
    api.api_id = api_id
    api.api_name = "Weather API"
    api.version = "1.0.0"
    api.status = "active"
    api.category = "data"
    api.tags = ["weather"]
    api.portal_published = True
    api.api_metadata = {"display_name": "Weather API", "description": "Get weather data"}
    api.openapi_spec = None
    api.git_path = None
    api.git_commit_sha = None
    api.synced_at = datetime.now(UTC)
    api.audience = "public"
    return api


class TestTriggerCatalogSync:
    """Tests for POST /v1/admin/catalog/sync."""

    def test_trigger_sync_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_last_sync_status = AsyncMock(return_value=None)
        mock_svc.sync_all = AsyncMock()

        with (
            patch(SYNC_SVC_PATH, return_value=mock_svc),
            patch(GET_ASYNC_DB_PATH, _fake_get_db),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post("/v1/admin/catalog/sync")

        assert resp.status_code == 200
        assert resp.json()["status"] == "sync_started"

    def test_trigger_sync_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_last_sync_status = AsyncMock(return_value=None)
        mock_svc.sync_all = AsyncMock()

        with (
            patch(SYNC_SVC_PATH, return_value=mock_svc),
            patch(GET_ASYNC_DB_PATH, _fake_get_db),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.post("/v1/admin/catalog/sync")

        assert resp.status_code == 200

    def test_trigger_sync_already_running(self, app_with_cpi_admin, mock_db_session):
        running_sync = _mock_sync_status(status="running")
        mock_svc = MagicMock()
        mock_svc.get_last_sync_status = AsyncMock(return_value=running_sync)

        with patch(SYNC_SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.post("/v1/admin/catalog/sync")

        assert resp.status_code == 200
        assert resp.json()["status"] == "sync_already_running"

    def test_trigger_sync_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.post("/v1/admin/catalog/sync")

        assert resp.status_code == 403

    def test_trigger_sync_500_service_error(self, app_with_cpi_admin, mock_db_session):
        with (
            patch(SYNC_SVC_PATH, side_effect=RuntimeError("DB connection lost")),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post("/v1/admin/catalog/sync")

        assert resp.status_code == 500
        assert "Failed to trigger sync" in resp.json()["detail"]


class TestTriggerMcpServersSync:
    """Tests for POST /v1/admin/catalog/sync/mcp-servers."""

    def test_trigger_mcp_sync_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.sync_mcp_servers = AsyncMock()

        with (
            patch(SYNC_SVC_PATH, return_value=mock_svc),
            patch(GET_ASYNC_DB_PATH, _fake_get_db),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post("/v1/admin/catalog/sync/mcp-servers")

        assert resp.status_code == 200
        assert resp.json()["status"] == "sync_started"

    def test_trigger_mcp_sync_with_tenant_filter(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.sync_mcp_servers = AsyncMock()

        with (
            patch(SYNC_SVC_PATH, return_value=mock_svc),
            patch(GET_ASYNC_DB_PATH, _fake_get_db),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post("/v1/admin/catalog/sync/mcp-servers?tenant_id=acme")

        assert resp.status_code == 200
        assert "acme" in resp.json()["message"]

    def test_trigger_mcp_sync_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.post("/v1/admin/catalog/sync/mcp-servers")

        assert resp.status_code == 403



class TestTriggerTenantSync:
    """Tests for POST /v1/admin/catalog/sync/tenant/{tenant_id}."""

    def test_trigger_tenant_sync_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.sync_tenant = AsyncMock()

        with (
            patch(SYNC_SVC_PATH, return_value=mock_svc),
            patch(GET_ASYNC_DB_PATH, _fake_get_db),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post("/v1/admin/catalog/sync/tenant/acme")

        assert resp.status_code == 200
        assert "acme" in resp.json()["message"]

    def test_trigger_tenant_sync_own_tenant(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.sync_tenant = AsyncMock()

        with (
            patch(SYNC_SVC_PATH, return_value=mock_svc),
            patch(GET_ASYNC_DB_PATH, _fake_get_db),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.post("/v1/admin/catalog/sync/tenant/acme")

        assert resp.status_code == 200

    def test_trigger_tenant_sync_403_cross_tenant(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.post("/v1/admin/catalog/sync/tenant/other-tenant")

        assert resp.status_code == 403

    def test_trigger_tenant_sync_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.post("/v1/admin/catalog/sync/tenant/acme")

        assert resp.status_code == 403



class TestGetSyncStatus:
    """Tests for GET /v1/admin/catalog/sync/status."""

    def test_get_sync_status_success(self, app_with_cpi_admin, mock_db_session):
        sync = _mock_sync_status()
        mock_svc = MagicMock()
        mock_svc.get_last_sync_status = AsyncMock(return_value=sync)

        with patch(SYNC_SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/admin/catalog/sync/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["items_synced"] == 42

    def test_get_sync_status_404_no_syncs(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_last_sync_status = AsyncMock(return_value=None)

        with patch(SYNC_SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/admin/catalog/sync/status")

        assert resp.status_code == 404

    def test_get_sync_status_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get("/v1/admin/catalog/sync/status")

        assert resp.status_code == 403

    def test_get_sync_status_500_service_error(self, app_with_cpi_admin, mock_db_session):
        with (
            patch(SYNC_SVC_PATH, side_effect=RuntimeError("DB read failure")),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/admin/catalog/sync/status")

        assert resp.status_code == 500
        assert "Failed to get sync status" in resp.json()["detail"]


class TestGetSyncHistory:
    """Tests for GET /v1/admin/catalog/sync/history."""

    def test_get_sync_history_success(self, app_with_cpi_admin, mock_db_session):
        syncs = [_mock_sync_status(), _mock_sync_status(status="failed")]
        mock_svc = MagicMock()
        mock_svc.get_sync_history = AsyncMock(return_value=syncs)

        with patch(SYNC_SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/admin/catalog/sync/history")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["syncs"]) == 2

    def test_get_sync_history_empty(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_sync_history = AsyncMock(return_value=[])

        with patch(SYNC_SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/admin/catalog/sync/history")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_get_sync_history_custom_limit(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_sync_history = AsyncMock(return_value=[])

        with patch(SYNC_SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/admin/catalog/sync/history?limit=5")

        assert resp.status_code == 200
        mock_svc.get_sync_history.assert_awaited_once_with(limit=5)

    def test_get_sync_history_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get("/v1/admin/catalog/sync/history")

        assert resp.status_code == 403

    def test_get_sync_history_500_service_error(self, app_with_cpi_admin, mock_db_session):
        with (
            patch(SYNC_SVC_PATH, side_effect=RuntimeError("DB read failure")),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/admin/catalog/sync/history")

        assert resp.status_code == 500
        assert "Failed to get sync history" in resp.json()["detail"]

    def test_get_sync_history_422_limit_too_low(self, app_with_cpi_admin, mock_db_session):
        with TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/admin/catalog/sync/history?limit=0")

        assert resp.status_code == 422

    def test_get_sync_history_422_limit_too_high(self, app_with_cpi_admin, mock_db_session):
        with TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/admin/catalog/sync/history?limit=101")

        assert resp.status_code == 422


class TestGetCatalogStats:
    """Tests for GET /v1/admin/catalog/stats."""

    def test_get_stats_success(self, app_with_cpi_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_stats = AsyncMock(
            return_value={
                "total_apis": 10,
                "published_apis": 7,
                "unpublished_apis": 3,
                "by_tenant": {"acme": 5},
                "by_category": {"data": 10},
            }
        )
        mock_svc = MagicMock()
        mock_svc.get_last_sync_status = AsyncMock(return_value=None)

        with (
            patch(CATALOG_REPO_PATH, return_value=mock_repo),
            patch(SYNC_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/admin/catalog/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_apis"] == 10
        assert data["last_sync"] is None

    def test_get_stats_includes_last_sync(self, app_with_cpi_admin, mock_db_session):
        sync = _mock_sync_status()
        mock_repo = MagicMock()
        mock_repo.get_stats = AsyncMock(
            return_value={
                "total_apis": 5,
                "published_apis": 3,
                "unpublished_apis": 2,
                "by_tenant": {},
                "by_category": {},
            }
        )
        mock_svc = MagicMock()
        mock_svc.get_last_sync_status = AsyncMock(return_value=sync)

        with (
            patch(CATALOG_REPO_PATH, return_value=mock_repo),
            patch(SYNC_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/admin/catalog/stats")

        assert resp.status_code == 200
        assert resp.json()["last_sync"] is not None

    def test_get_stats_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.get("/v1/admin/catalog/stats")

        assert resp.status_code == 403

    def test_get_stats_500_repo_error(self, app_with_cpi_admin, mock_db_session):
        with (
            patch(CATALOG_REPO_PATH, side_effect=RuntimeError("DB failure")),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/admin/catalog/stats")

        assert resp.status_code == 500
        assert "Failed to get catalog stats" in resp.json()["detail"]


class TestInvalidateCache:
    """Tests for DELETE /v1/admin/catalog/cache."""

    def test_invalidate_cache_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        with TestClient(app_with_cpi_admin) as client:
            resp = client.delete("/v1/admin/catalog/cache")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_invalidate_cache_403_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.delete("/v1/admin/catalog/cache")

        assert resp.status_code == 403

    def test_invalidate_cache_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.delete("/v1/admin/catalog/cache")

        assert resp.status_code == 403


class TestSeedCatalog:
    """Tests for POST /v1/admin/catalog/seed."""

    def test_seed_catalog_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock())
        mock_db_session.commit = AsyncMock()

        payload = {
            "tenant_id": "acme",
            "apis": [
                {
                    "name": "weather-api",
                    "display_name": "Weather API",
                    "version": "1.0.0",
                    "description": "Weather data",
                    "backend_url": "https://api.weather.com",
                    "tags": ["weather"],
                }
            ],
        }

        with TestClient(app_with_cpi_admin) as client:
            resp = client.post("/v1/admin/catalog/seed", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["seeded"] == 1
        assert data["failed"] == 0

    def test_seed_catalog_403_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.post("/v1/admin/catalog/seed", json={"tenant_id": "acme", "apis": []})

        assert resp.status_code == 403

    def test_seed_catalog_empty_apis(self, app_with_cpi_admin, mock_db_session):
        mock_db_session.commit = AsyncMock()

        with TestClient(app_with_cpi_admin) as client:
            resp = client.post("/v1/admin/catalog/seed", json={"tenant_id": "acme", "apis": []})

        assert resp.status_code == 200
        assert resp.json()["seeded"] == 0

    def test_seed_catalog_with_valid_openapi_spec(self, app_with_cpi_admin, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock())
        mock_db_session.commit = AsyncMock()

        payload = {
            "tenant_id": "acme",
            "apis": [
                {
                    "name": "petstore-api",
                    "display_name": "Petstore",
                    "version": "3.0.0",
                    "description": "Pet store",
                    "backend_url": "https://petstore.example.com",
                    "tags": [],
                    "openapi_spec": '{"openapi": "3.0.0", "info": {"title": "Petstore"}}',
                }
            ],
        }

        with TestClient(app_with_cpi_admin) as client:
            resp = client.post("/v1/admin/catalog/seed", json=payload)

        assert resp.status_code == 200
        assert resp.json()["seeded"] == 1

    def test_seed_catalog_invalid_openapi_spec_graceful(self, app_with_cpi_admin, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock())
        mock_db_session.commit = AsyncMock()

        payload = {
            "tenant_id": "acme",
            "apis": [
                {
                    "name": "broken-api",
                    "display_name": "Broken Spec",
                    "version": "1.0.0",
                    "description": "Has invalid JSON spec",
                    "backend_url": "https://example.com",
                    "tags": [],
                    "openapi_spec": "NOT VALID JSON {{{",
                }
            ],
        }

        with TestClient(app_with_cpi_admin) as client:
            resp = client.post("/v1/admin/catalog/seed", json=payload)

        assert resp.status_code == 200
        assert resp.json()["seeded"] == 1
        assert resp.json()["failed"] == 0

    def test_seed_catalog_per_api_db_failure(self, app_with_cpi_admin, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=RuntimeError("constraint violation"))
        mock_db_session.commit = AsyncMock()

        payload = {
            "tenant_id": "acme",
            "apis": [
                {
                    "name": "fail-api",
                    "display_name": "Will Fail",
                    "version": "1.0.0",
                    "description": "DB error",
                    "backend_url": "https://example.com",
                    "tags": [],
                }
            ],
        }

        with TestClient(app_with_cpi_admin) as client:
            resp = client.post("/v1/admin/catalog/seed", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["seeded"] == 0
        assert data["failed"] == 1
        assert "failed:" in data["results"]["fail-api"]

    def test_seed_catalog_mixed_success_and_failure(self, app_with_cpi_admin, mock_db_session):
        call_count = 0

        async def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("duplicate key")
            return MagicMock()

        mock_db_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db_session.commit = AsyncMock()

        payload = {
            "tenant_id": "acme",
            "apis": [
                {"name": "api-ok", "display_name": "OK", "version": "1.0.0"},
                {"name": "api-fail", "display_name": "Fail", "version": "1.0.0"},
                {"name": "api-ok-2", "display_name": "OK 2", "version": "1.0.0"},
            ],
        }

        with TestClient(app_with_cpi_admin) as client:
            resp = client.post("/v1/admin/catalog/seed", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["seeded"] == 2
        assert data["failed"] == 1

    def test_seed_catalog_portal_published_tags(self, app_with_cpi_admin, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock())
        mock_db_session.commit = AsyncMock()

        payload = {
            "tenant_id": "acme",
            "apis": [
                {
                    "name": "promoted-api",
                    "display_name": "Promoted",
                    "version": "1.0.0",
                    "tags": ["portal:published", "v2"],
                }
            ],
        }

        with TestClient(app_with_cpi_admin) as client:
            resp = client.post("/v1/admin/catalog/seed", json=payload)

        assert resp.status_code == 200
        assert resp.json()["seeded"] == 1

    def test_seed_catalog_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.post("/v1/admin/catalog/seed", json={"tenant_id": "acme", "apis": []})

        assert resp.status_code == 403


class TestUpdateApiAudience:
    """Tests for PATCH /v1/admin/catalog/{tenant_id}/{api_id}/audience."""

    def test_update_audience_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        api = _mock_catalog_api()
        mock_repo = MagicMock()
        mock_repo.get_api_by_id = AsyncMock(return_value=api)
        mock_db_session.commit = AsyncMock()

        with patch(CATALOG_REPO_PATH, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.patch(
                f"/v1/admin/catalog/acme/{api.api_id}/audience",
                json={"audience": "internal"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["audience"] == "internal"
        assert data["tenant_id"] == "acme"

    def test_update_audience_tenant_admin_own_tenant(self, app_with_tenant_admin, mock_db_session):
        api = _mock_catalog_api(tenant_id="acme")
        mock_repo = MagicMock()
        mock_repo.get_api_by_id = AsyncMock(return_value=api)
        mock_db_session.commit = AsyncMock()

        with patch(CATALOG_REPO_PATH, return_value=mock_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.patch(
                f"/v1/admin/catalog/acme/{api.api_id}/audience",
                json={"audience": "partner"},
            )

        assert resp.status_code == 200

    def test_update_audience_403_tenant_admin_cross_tenant(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.patch(
                "/v1/admin/catalog/other-tenant/some-api/audience",
                json={"audience": "public"},
            )

        assert resp.status_code == 403

    def test_update_audience_404_api_not_found(self, app_with_cpi_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_api_by_id = AsyncMock(return_value=None)

        with patch(CATALOG_REPO_PATH, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.patch(
                "/v1/admin/catalog/acme/nonexistent-api/audience",
                json={"audience": "public"},
            )

        assert resp.status_code == 404

    def test_update_audience_400_invalid_audience(self, app_with_cpi_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_api_by_id = AsyncMock(return_value=_mock_catalog_api())

        with patch(CATALOG_REPO_PATH, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.patch(
                "/v1/admin/catalog/acme/weather-api/audience",
                json={"audience": "classified"},
            )

        assert resp.status_code == 400
        assert "classified" in resp.json()["detail"]

    def test_update_audience_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.patch(
                "/v1/admin/catalog/acme/weather-api/audience",
                json={"audience": "public"},
            )

        assert resp.status_code == 403

    def test_update_audience_all_valid_values(self, app_with_cpi_admin, mock_db_session):
        for audience_val in ("public", "internal", "partner"):
            api = _mock_catalog_api()
            mock_repo = MagicMock()
            mock_repo.get_api_by_id = AsyncMock(return_value=api)
            mock_db_session.commit = AsyncMock()

            with (
                patch(CATALOG_REPO_PATH, return_value=mock_repo),
                TestClient(app_with_cpi_admin) as client,
            ):
                resp = client.patch(
                    f"/v1/admin/catalog/acme/{api.api_id}/audience",
                    json={"audience": audience_val},
                )

            assert resp.status_code == 200
            assert resp.json()["audience"] == audience_val
