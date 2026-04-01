"""Tests for APIs router — /v1/tenants/{tenant_id}/apis"""

from unittest.mock import AsyncMock, MagicMock, patch

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


def _make_mock_git(**methods):
    """Create a mock GitProvider with the given async methods configured."""
    from src.services.git_provider import GitProvider

    mock = MagicMock(spec=GitProvider)
    mock._project = object()  # non-None so _require_git_service passes
    for name, value in methods.items():
        setattr(mock, name, value)
    return mock


class TestListAPIs:
    def test_list_returns_paginated(self, app_with_tenant_admin, client_as_tenant_admin):
        from src.services.git_provider import get_git_provider

        apis = [_mock_api_yaml(), _mock_api_yaml(id="api-2", name="maps-api")]
        mock_git = _make_mock_git(list_apis=AsyncMock(return_value=apis))
        app_with_tenant_admin.dependency_overrides[get_git_provider] = lambda: mock_git
        resp = client_as_tenant_admin.get("/v1/tenants/acme/apis")
        app_with_tenant_admin.dependency_overrides.pop(get_git_provider, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    def test_list_filter_by_env(self, app_with_tenant_admin, client_as_tenant_admin):
        from src.services.git_provider import get_git_provider

        apis = [
            _mock_api_yaml(deployments={"dev": True, "staging": False}),
            _mock_api_yaml(id="api-2", deployments={"dev": False, "staging": True}),
        ]
        mock_git = _make_mock_git(list_apis=AsyncMock(return_value=apis))
        app_with_tenant_admin.dependency_overrides[get_git_provider] = lambda: mock_git
        resp = client_as_tenant_admin.get("/v1/tenants/acme/apis?environment=dev")
        app_with_tenant_admin.dependency_overrides.pop(get_git_provider, None)

        body = resp.json()
        assert body["total"] == 1

    def test_list_error_returns_empty(self, app_with_tenant_admin, client_as_tenant_admin):
        from src.services.git_provider import get_git_provider

        mock_git = _make_mock_git(list_apis=AsyncMock(side_effect=RuntimeError("Git down")))
        app_with_tenant_admin.dependency_overrides[get_git_provider] = lambda: mock_git
        resp = client_as_tenant_admin.get("/v1/tenants/acme/apis")
        app_with_tenant_admin.dependency_overrides.pop(get_git_provider, None)

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_other_tenant_forbidden(self, app_with_other_tenant, client_as_other_tenant):
        from src.services.git_provider import get_git_provider

        mock_git = _make_mock_git(list_apis=AsyncMock(return_value=[]))
        app_with_other_tenant.dependency_overrides[get_git_provider] = lambda: mock_git
        resp = client_as_other_tenant.get("/v1/tenants/acme/apis")
        app_with_other_tenant.dependency_overrides.pop(get_git_provider, None)

        assert resp.status_code == 403

    def test_cpi_admin_cross_tenant(self, app_with_cpi_admin, client_as_cpi_admin):
        from src.services.git_provider import get_git_provider

        mock_git = _make_mock_git(list_apis=AsyncMock(return_value=[]))
        app_with_cpi_admin.dependency_overrides[get_git_provider] = lambda: mock_git
        resp = client_as_cpi_admin.get("/v1/tenants/acme/apis")
        app_with_cpi_admin.dependency_overrides.pop(get_git_provider, None)

        assert resp.status_code == 200


class TestGetAPI:
    def test_get_success(self, app_with_tenant_admin, client_as_tenant_admin):
        from src.services.git_provider import get_git_provider

        mock_git = _make_mock_git(get_api=AsyncMock(return_value=_mock_api_yaml()))
        app_with_tenant_admin.dependency_overrides[get_git_provider] = lambda: mock_git
        resp = client_as_tenant_admin.get("/v1/tenants/acme/apis/api-1")
        app_with_tenant_admin.dependency_overrides.pop(get_git_provider, None)

        assert resp.status_code == 200
        assert resp.json()["name"] == "weather-api"

    def test_get_not_found(self, app_with_tenant_admin, client_as_tenant_admin):
        from src.services.git_provider import get_git_provider

        mock_git = _make_mock_git(get_api=AsyncMock(return_value=None))
        app_with_tenant_admin.dependency_overrides[get_git_provider] = lambda: mock_git
        resp = client_as_tenant_admin.get("/v1/tenants/acme/apis/missing")
        app_with_tenant_admin.dependency_overrides.pop(get_git_provider, None)

        assert resp.status_code == 404


class TestCreateAPI:
    def test_create_success(self, app_with_tenant_admin, client_as_tenant_admin):
        from src.services.git_provider import get_git_provider

        mock_git = _make_mock_git(create_api=AsyncMock(return_value=None))
        app_with_tenant_admin.dependency_overrides[get_git_provider] = lambda: mock_git
        with patch(KAFKA_PATH) as mock_kafka:
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
        app_with_tenant_admin.dependency_overrides.pop(get_git_provider, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "new-api"
        assert body["status"] == "draft"

    def test_create_duplicate_returns_409(self, app_with_tenant_admin, client_as_tenant_admin):
        from src.services.git_provider import get_git_provider

        mock_git = _make_mock_git(create_api=AsyncMock(side_effect=ValueError("already exists")))
        app_with_tenant_admin.dependency_overrides[get_git_provider] = lambda: mock_git
        with patch(KAFKA_PATH):
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "dup-api",
                    "display_name": "Dup",
                    "backend_url": "https://api.example.com",
                },
            )
        app_with_tenant_admin.dependency_overrides.pop(get_git_provider, None)

        assert resp.status_code == 409

    def test_portal_promoted_tag(self, app_with_tenant_admin, client_as_tenant_admin):
        from src.services.git_provider import get_git_provider

        mock_git = _make_mock_git(create_api=AsyncMock(return_value=None))
        app_with_tenant_admin.dependency_overrides[get_git_provider] = lambda: mock_git
        with patch(KAFKA_PATH) as mock_kafka:
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
        app_with_tenant_admin.dependency_overrides.pop(get_git_provider, None)

        body = resp.json()
        assert body["portal_promoted"] is True


class TestUpdateAPI:
    def test_update_success(self, app_with_tenant_admin, client_as_tenant_admin):
        from src.services.git_provider import get_git_provider

        current = _mock_api_yaml()
        updated = _mock_api_yaml(description="Updated desc")
        mock_git = _make_mock_git(
            get_api=AsyncMock(side_effect=[current, updated]),
            update_api=AsyncMock(return_value=None),
        )
        app_with_tenant_admin.dependency_overrides[get_git_provider] = lambda: mock_git
        with patch(KAFKA_PATH) as mock_kafka:
            mock_kafka.emit_api_updated = AsyncMock(return_value="evt-1")
            mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")
            resp = client_as_tenant_admin.put(
                "/v1/tenants/acme/apis/api-1",
                json={"description": "Updated desc"},
            )
        app_with_tenant_admin.dependency_overrides.pop(get_git_provider, None)

        assert resp.status_code == 200

    def test_update_not_found(self, app_with_tenant_admin, client_as_tenant_admin):
        from src.services.git_provider import get_git_provider

        mock_git = _make_mock_git(get_api=AsyncMock(return_value=None))
        app_with_tenant_admin.dependency_overrides[get_git_provider] = lambda: mock_git
        with patch(KAFKA_PATH):
            resp = client_as_tenant_admin.put(
                "/v1/tenants/acme/apis/missing",
                json={"description": "test"},
            )
        app_with_tenant_admin.dependency_overrides.pop(get_git_provider, None)

        assert resp.status_code == 404


class TestDeleteAPI:
    def test_delete_success(self, app_with_tenant_admin, client_as_tenant_admin):
        from src.services.git_provider import get_git_provider

        mock_git = _make_mock_git(
            get_api=AsyncMock(return_value=_mock_api_yaml()),
            delete_api=AsyncMock(return_value=None),
        )
        app_with_tenant_admin.dependency_overrides[get_git_provider] = lambda: mock_git
        with patch(KAFKA_PATH) as mock_kafka:
            mock_kafka.emit_api_deleted = AsyncMock(return_value="evt-1")
            mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")
            resp = client_as_tenant_admin.delete("/v1/tenants/acme/apis/api-1")
        app_with_tenant_admin.dependency_overrides.pop(get_git_provider, None)

        assert resp.status_code == 200

    def test_delete_not_found(self, app_with_tenant_admin, client_as_tenant_admin):
        from src.services.git_provider import get_git_provider

        mock_git = _make_mock_git(get_api=AsyncMock(return_value=None))
        app_with_tenant_admin.dependency_overrides[get_git_provider] = lambda: mock_git
        with patch(KAFKA_PATH):
            resp = client_as_tenant_admin.delete("/v1/tenants/acme/apis/missing")
        app_with_tenant_admin.dependency_overrides.pop(get_git_provider, None)

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
