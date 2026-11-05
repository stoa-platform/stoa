"""Tests for gateway router — /v1/gateway (webMethods proxy)"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.services.gateway_service import GatewayAdminService

GW_PATH = "src.routers.gateway.gateway_service"


class TestListGatewayAPIs:
    def test_list_returns_paginated(self, client_as_cpi_admin):
        apis = [
            {
                "api": {
                    "id": "gw-1",
                    "apiName": "Weather",
                    "apiVersion": "1.0",
                    "type": "openapi",
                    "isActive": True,
                    "systemVersion": 1,
                }
            },
            {
                "api": {
                    "id": "gw-2",
                    "apiName": "Maps",
                    "apiVersion": "2.0",
                    "type": "openapi",
                    "isActive": False,
                    "systemVersion": 2,
                }
            },
        ]
        with patch(GW_PATH) as mock_gw:
            mock_gw.list_apis = AsyncMock(return_value=apis)
            resp = client_as_cpi_admin.get(
                "/v1/gateway/apis",
                headers={"Authorization": "Bearer mock-token"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2

    def test_list_error_returns_empty(self, client_as_cpi_admin):
        with patch(GW_PATH) as mock_gw:
            mock_gw.list_apis = AsyncMock(side_effect=RuntimeError("GW down"))
            resp = client_as_cpi_admin.get(
                "/v1/gateway/apis",
                headers={"Authorization": "Bearer mock-token"},
            )

        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestGetGatewayAPI:
    def test_get_success(self, client_as_cpi_admin):
        api_data = {"id": "gw-1", "apiName": "Weather"}
        with patch(GW_PATH) as mock_gw:
            mock_gw.get_api = AsyncMock(return_value=api_data)
            resp = client_as_cpi_admin.get(
                "/v1/gateway/apis/gw-1",
                headers={"Authorization": "Bearer mock-token"},
            )

        assert resp.status_code == 200

    def test_get_not_found(self, client_as_cpi_admin):
        with patch(GW_PATH) as mock_gw:
            mock_gw.get_api = AsyncMock(return_value=None)
            resp = client_as_cpi_admin.get(
                "/v1/gateway/apis/missing",
                headers={"Authorization": "Bearer mock-token"},
            )

        assert resp.status_code == 404


class TestImportAPI:
    def test_import_with_url(self, client_as_cpi_admin):
        result = {"apiResponse": {"api": {"id": "gw-new"}}}
        with patch(GW_PATH) as mock_gw:
            mock_gw.import_api = AsyncMock(return_value=result)
            resp = client_as_cpi_admin.post(
                "/v1/gateway/apis",
                json={
                    "apiName": "New API",
                    "apiVersion": "1.0",
                    "url": "https://petstore.swagger.io/v2/swagger.json",
                },
                headers={"Authorization": "Bearer mock-token"},
            )

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_import_missing_url_and_definition(self, client_as_cpi_admin):
        with patch(GW_PATH):
            resp = client_as_cpi_admin.post(
                "/v1/gateway/apis",
                json={"apiName": "No Source", "apiVersion": "1.0"},
                headers={"Authorization": "Bearer mock-token"},
            )

        assert resp.status_code == 400


class TestActivateDeactivate:
    def test_activate(self, client_as_cpi_admin):
        with patch(GW_PATH) as mock_gw:
            mock_gw.activate_api = AsyncMock(return_value={"success": True})
            resp = client_as_cpi_admin.put(
                "/v1/gateway/apis/gw-1/activate",
                headers={"Authorization": "Bearer mock-token"},
            )

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_deactivate(self, client_as_cpi_admin):
        with patch(GW_PATH) as mock_gw:
            mock_gw.deactivate_api = AsyncMock(return_value={"success": True})
            resp = client_as_cpi_admin.put(
                "/v1/gateway/apis/gw-1/deactivate",
                headers={"Authorization": "Bearer mock-token"},
            )

        assert resp.status_code == 200


class TestDeleteGatewayAPI:
    def test_delete_success(self, client_as_cpi_admin):
        with patch(GW_PATH) as mock_gw:
            mock_gw.delete_api = AsyncMock(return_value=None)
            resp = client_as_cpi_admin.delete(
                "/v1/gateway/apis/gw-1",
                headers={"Authorization": "Bearer mock-token"},
            )

        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestListApplications:
    def test_list_returns_paginated(self, client_as_cpi_admin):
        apps = [{"id": "app-1", "name": "TestApp", "description": "Test", "contactEmails": []}]
        with patch(GW_PATH) as mock_gw:
            mock_gw.list_applications = AsyncMock(return_value=apps)
            resp = client_as_cpi_admin.get(
                "/v1/gateway/applications",
                headers={"Authorization": "Bearer mock-token"},
            )

        assert resp.status_code == 200
        assert resp.json()["total"] == 1


class TestListScopes:
    def test_list_scopes(self, client_as_cpi_admin):
        scopes = [{"scopeName": "openid", "scopeDescription": "OpenID"}]
        with patch(GW_PATH) as mock_gw:
            mock_gw.list_scopes = AsyncMock(return_value=scopes)
            resp = client_as_cpi_admin.get(
                "/v1/gateway/scopes",
                headers={"Authorization": "Bearer mock-token"},
            )

        assert resp.status_code == 200
        assert resp.json()[0]["scopeName"] == "openid"


class TestGatewayHealth:
    def test_healthy(self, client_as_cpi_admin):
        with patch(GW_PATH) as mock_gw, patch("src.routers.gateway.settings") as mock_settings:
            mock_gw.health_check = AsyncMock(return_value={"status": "ok"})
            mock_settings.GATEWAY_USE_OIDC_PROXY = True
            mock_settings.GATEWAY_ADMIN_PROXY_URL = "http://proxy:8080"
            resp = client_as_cpi_admin.get(
                "/v1/gateway/health",
                headers={"Authorization": "Bearer mock-token"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_unhealthy(self, client_as_cpi_admin):
        with patch(GW_PATH) as mock_gw, patch("src.routers.gateway.settings") as mock_settings:
            mock_gw.health_check = AsyncMock(side_effect=RuntimeError("GW down"))
            mock_settings.GATEWAY_USE_OIDC_PROXY = False
            resp = client_as_cpi_admin.get(
                "/v1/gateway/health",
                headers={"Authorization": "Bearer mock-token"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "unhealthy"


class TestUnauthenticated:
    def test_no_auth_returns_401(self, client):
        resp = client.get("/v1/gateway/apis")
        # HTTPBearer with auto_error=True returns 403 when no credentials
        assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_regression_oidc_error_response_and_log(client_as_cpi_admin, caplog):
    """Transport failures keep internal details in the server log."""
    error = RuntimeError("internal gateway connection diagnostic")

    def fail_request(request: httpx.Request) -> httpx.Response:
        raise error

    service = GatewayAdminService(auth_config={"type": "basic"})
    async with httpx.AsyncClient(
        base_url="https://gateway.example.test", transport=httpx.MockTransport(fail_request)
    ) as upstream:
        service._client = upstream
        with patch(GW_PATH, service):
            response = client_as_cpi_admin.post(
                "/v1/gateway/configure-oidc",
                json={
                    "tenant_id": "acme",
                    "api_name": "weather",
                    "api_version": "1.0",
                    "api_id": "weather-api",
                    "client_id": "weather-client",
                },
                headers={"Authorization": "Bearer mock-token"},
            )

    assert response.status_code == 500
    assert response.json() == {"detail": "Gateway OIDC configuration error"}
    assert str(error) not in response.text
    records = [record for record in caplog.records if record.name == "src.routers.gateway"]
    assert any(record.exc_info and record.exc_info[1] is error for record in records)
    assert str(error) in caplog.text
