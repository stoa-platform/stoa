"""Tests for service accounts router — /v1/service-accounts"""

from unittest.mock import AsyncMock, patch

KC_PATH = "src.routers.service_accounts.keycloak_service"


class TestListServiceAccounts:
    def test_list_returns_accounts(self, client_as_tenant_admin):
        accounts = [
            {"id": "sa-1", "client_id": "sa-acme-user-1", "name": "claude", "description": None, "enabled": True},
            {"id": "sa-2", "client_id": "sa-acme-user-2", "name": "cursor", "description": "IDE", "enabled": True},
        ]
        with patch(KC_PATH) as mock_kc:
            mock_kc.list_user_service_accounts = AsyncMock(return_value=accounts)
            resp = client_as_tenant_admin.get("/v1/service-accounts")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["client_id"] == "sa-acme-user-1"

    def test_list_empty(self, client_as_tenant_admin):
        with patch(KC_PATH) as mock_kc:
            mock_kc.list_user_service_accounts = AsyncMock(return_value=[])
            resp = client_as_tenant_admin.get("/v1/service-accounts")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/v1/service-accounts")
        assert resp.status_code == 401


class TestCreateServiceAccount:
    def test_create_success(self, client_as_tenant_admin):
        result = {
            "id": "sa-new",
            "client_id": "sa-acme-admin-claude",
            "client_secret": "super-secret-value",
            "name": "claude-desktop",
        }
        with patch(KC_PATH) as mock_kc:
            mock_kc.create_service_account = AsyncMock(return_value=result)
            resp = client_as_tenant_admin.post(
                "/v1/service-accounts",
                json={"name": "claude-desktop", "description": "For Claude Desktop"},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["client_secret"] == "super-secret-value"
        assert body["name"] == "claude-desktop"

    def test_create_returns_500_on_error(self, client_as_tenant_admin):
        with patch(KC_PATH) as mock_kc:
            mock_kc.create_service_account = AsyncMock(side_effect=RuntimeError("KC down"))
            resp = client_as_tenant_admin.post(
                "/v1/service-accounts",
                json={"name": "fail"},
            )

        assert resp.status_code == 500


class TestDeleteServiceAccount:
    def test_delete_success(self, client_as_tenant_admin):
        with patch(KC_PATH) as mock_kc:
            mock_kc.delete_service_account = AsyncMock(return_value=None)
            resp = client_as_tenant_admin.delete("/v1/service-accounts/sa-1")

        assert resp.status_code == 204

    def test_delete_not_found(self, client_as_tenant_admin):
        with patch(KC_PATH) as mock_kc:
            mock_kc.delete_service_account = AsyncMock(side_effect=ValueError("Not found"))
            resp = client_as_tenant_admin.delete("/v1/service-accounts/sa-missing")

        assert resp.status_code == 404

    def test_delete_not_owner(self, client_as_tenant_admin):
        with patch(KC_PATH) as mock_kc:
            mock_kc.delete_service_account = AsyncMock(side_effect=PermissionError("Not owner"))
            resp = client_as_tenant_admin.delete("/v1/service-accounts/sa-other")

        assert resp.status_code == 403


class TestRegenerateSecret:
    def test_regenerate_success(self, client_as_tenant_admin):
        accounts = [
            {"id": "sa-1", "client_id": "sa-acme-admin-claude", "name": "claude", "description": None, "enabled": True},
        ]
        with patch(KC_PATH) as mock_kc:
            mock_kc.list_user_service_accounts = AsyncMock(return_value=accounts)
            mock_kc.regenerate_client_secret = AsyncMock(return_value="new-secret-123")
            resp = client_as_tenant_admin.post("/v1/service-accounts/sa-1/regenerate-secret")

        assert resp.status_code == 200
        body = resp.json()
        assert body["client_secret"] == "new-secret-123"
        assert body["id"] == "sa-1"

    def test_regenerate_not_found(self, client_as_tenant_admin):
        with patch(KC_PATH) as mock_kc:
            mock_kc.list_user_service_accounts = AsyncMock(return_value=[])
            resp = client_as_tenant_admin.post("/v1/service-accounts/sa-missing/regenerate-secret")

        assert resp.status_code == 404
