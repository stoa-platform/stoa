"""Tests for APIs router — /v1/tenants/{tenant_id}/apis"""

from unittest.mock import AsyncMock, patch

GIT_PATH = "src.routers.apis.git_service"
KAFKA_PATH = "src.routers.apis.kafka_service"


def _mock_api_yaml(**overrides):
    """Build a mock API YAML dict as returned by git_service."""
    data = {
        "id": "api-1",
        "name": "weather-api",
        "display_name": "Weather API",
        "version": "1.0.0",
        "description": "Weather data",
        "backend_url": "https://api.weather.com",
        "status": "draft",
        "deployments": {"dev": False, "staging": False},
        "tags": [],
    }
    data.update(overrides)
    return data


class TestListAPIs:
    def test_list_returns_paginated(self, client_as_tenant_admin):
        apis = [_mock_api_yaml(), _mock_api_yaml(id="api-2", name="maps-api")]
        with patch(GIT_PATH) as mock_git:
            mock_git.list_apis = AsyncMock(return_value=apis)
            resp = client_as_tenant_admin.get("/v1/tenants/acme/apis")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    def test_list_filter_by_env(self, client_as_tenant_admin):
        apis = [
            _mock_api_yaml(deployments={"dev": True, "staging": False}),
            _mock_api_yaml(id="api-2", deployments={"dev": False, "staging": True}),
        ]
        with patch(GIT_PATH) as mock_git:
            mock_git.list_apis = AsyncMock(return_value=apis)
            resp = client_as_tenant_admin.get("/v1/tenants/acme/apis?environment=dev")

        body = resp.json()
        assert body["total"] == 1

    def test_list_error_returns_empty(self, client_as_tenant_admin):
        with patch(GIT_PATH) as mock_git:
            mock_git.list_apis = AsyncMock(side_effect=RuntimeError("Git down"))
            resp = client_as_tenant_admin.get("/v1/tenants/acme/apis")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_other_tenant_forbidden(self, client_as_other_tenant):
        with patch(GIT_PATH) as mock_git:
            mock_git.list_apis = AsyncMock(return_value=[])
            resp = client_as_other_tenant.get("/v1/tenants/acme/apis")

        assert resp.status_code == 403

    def test_cpi_admin_cross_tenant(self, client_as_cpi_admin):
        with patch(GIT_PATH) as mock_git:
            mock_git.list_apis = AsyncMock(return_value=[])
            resp = client_as_cpi_admin.get("/v1/tenants/acme/apis")

        assert resp.status_code == 200


class TestGetAPI:
    def test_get_success(self, client_as_tenant_admin):
        with patch(GIT_PATH) as mock_git:
            mock_git.get_api = AsyncMock(return_value=_mock_api_yaml())
            resp = client_as_tenant_admin.get("/v1/tenants/acme/apis/api-1")

        assert resp.status_code == 200
        assert resp.json()["name"] == "weather-api"

    def test_get_not_found(self, client_as_tenant_admin):
        with patch(GIT_PATH) as mock_git:
            mock_git.get_api = AsyncMock(return_value=None)
            resp = client_as_tenant_admin.get("/v1/tenants/acme/apis/missing")

        assert resp.status_code == 404


class TestCreateAPI:
    def test_create_success(self, client_as_tenant_admin):
        with patch(GIT_PATH) as mock_git, patch(KAFKA_PATH) as mock_kafka:
            mock_git.create_api = AsyncMock(return_value=None)
            mock_kafka.emit_api_created = AsyncMock(return_value="evt-1")
            mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")

            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "new-api",
                    "display_name": "New API",
                    "backend_url": "https://api.example.com",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "new-api"
        assert body["status"] == "draft"

    def test_create_duplicate_returns_409(self, client_as_tenant_admin):
        with patch(GIT_PATH) as mock_git, patch(KAFKA_PATH):
            mock_git.create_api = AsyncMock(side_effect=ValueError("already exists"))
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "dup-api",
                    "display_name": "Dup",
                    "backend_url": "https://api.example.com",
                },
            )

        assert resp.status_code == 409

    def test_portal_promoted_tag(self, client_as_tenant_admin):
        with patch(GIT_PATH) as mock_git, patch(KAFKA_PATH) as mock_kafka:
            mock_git.create_api = AsyncMock(return_value=None)
            mock_kafka.emit_api_created = AsyncMock(return_value="evt-1")
            mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")

            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "portal-api",
                    "display_name": "Portal API",
                    "backend_url": "https://api.example.com",
                    "tags": ["portal:published", "v1"],
                },
            )

        body = resp.json()
        assert body["portal_promoted"] is True


class TestUpdateAPI:
    def test_update_success(self, client_as_tenant_admin):
        current = _mock_api_yaml()
        updated = _mock_api_yaml(description="Updated desc")
        with patch(GIT_PATH) as mock_git, patch(KAFKA_PATH) as mock_kafka:
            mock_git.get_api = AsyncMock(side_effect=[current, updated])
            mock_git.update_api = AsyncMock(return_value=None)
            mock_kafka.emit_api_updated = AsyncMock(return_value="evt-1")
            mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")

            resp = client_as_tenant_admin.put(
                "/v1/tenants/acme/apis/api-1",
                json={"description": "Updated desc"},
            )

        assert resp.status_code == 200

    def test_update_not_found(self, client_as_tenant_admin):
        with patch(GIT_PATH) as mock_git, patch(KAFKA_PATH):
            mock_git.get_api = AsyncMock(return_value=None)
            resp = client_as_tenant_admin.put(
                "/v1/tenants/acme/apis/missing",
                json={"description": "test"},
            )

        assert resp.status_code == 404


class TestDeleteAPI:
    def test_delete_success(self, client_as_tenant_admin):
        with patch(GIT_PATH) as mock_git, patch(KAFKA_PATH) as mock_kafka:
            mock_git.get_api = AsyncMock(return_value=_mock_api_yaml())
            mock_git.delete_api = AsyncMock(return_value=None)
            mock_kafka.emit_api_deleted = AsyncMock(return_value="evt-1")
            mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")

            resp = client_as_tenant_admin.delete("/v1/tenants/acme/apis/api-1")

        assert resp.status_code == 200

    def test_delete_not_found(self, client_as_tenant_admin):
        with patch(GIT_PATH) as mock_git, patch(KAFKA_PATH):
            mock_git.get_api = AsyncMock(return_value=None)
            resp = client_as_tenant_admin.delete("/v1/tenants/acme/apis/missing")

        assert resp.status_code == 404


class TestApiFromYaml:
    def test_portal_promoted_detection(self):
        from src.routers.apis import _api_from_yaml

        result = _api_from_yaml("acme", _mock_api_yaml(tags=["portal:published", "v1"]))
        assert result.portal_promoted is True

    def test_no_portal_tag(self):
        from src.routers.apis import _api_from_yaml

        result = _api_from_yaml("acme", _mock_api_yaml(tags=["v1"]))
        assert result.portal_promoted is False
