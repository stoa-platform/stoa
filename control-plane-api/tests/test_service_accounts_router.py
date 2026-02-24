"""Tests for Service Accounts Router — CAB-1448

Covers: /v1/service-accounts (list, create, delete, regenerate-secret).
Uses keycloak_service directly (mocked globally in conftest).
"""

from unittest.mock import AsyncMock, patch

KC_SVC_PATH = "src.routers.service_accounts.keycloak_service"


class TestListServiceAccounts:
    """Tests for GET /v1/service-accounts."""

    def test_list_success(self, client_as_tenant_admin):
        with patch(KC_SVC_PATH) as mock_kc:
            mock_kc.list_user_service_accounts = AsyncMock(
                return_value=[
                    {
                        "id": "sa-1",
                        "client_id": "sa-acme-admin-claude",
                        "name": "claude",
                        "description": None,
                        "enabled": True,
                    },
                ]
            )
            resp = client_as_tenant_admin.get("/v1/service-accounts")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["client_id"] == "sa-acme-admin-claude"

    def test_list_empty(self, client_as_tenant_admin):
        with patch(KC_SVC_PATH) as mock_kc:
            mock_kc.list_user_service_accounts = AsyncMock(return_value=[])
            resp = client_as_tenant_admin.get("/v1/service-accounts")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_error_500(self, client_as_tenant_admin):
        with patch(KC_SVC_PATH) as mock_kc:
            mock_kc.list_user_service_accounts = AsyncMock(side_effect=RuntimeError("KC down"))
            resp = client_as_tenant_admin.get("/v1/service-accounts")

        assert resp.status_code == 500


class TestCreateServiceAccount:
    """Tests for POST /v1/service-accounts."""

    def test_create_success(self, client_as_tenant_admin):
        with patch(KC_SVC_PATH) as mock_kc:
            mock_kc.create_service_account = AsyncMock(
                return_value={
                    "id": "sa-1",
                    "client_id": "sa-acme-admin-claude",
                    "client_secret": "super-secret",
                    "name": "claude-desktop",
                }
            )
            resp = client_as_tenant_admin.post(
                "/v1/service-accounts",
                json={"name": "claude-desktop", "description": "For Claude Desktop"},
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["client_secret"] == "super-secret"
        assert "message" in data

    def test_create_error_500(self, client_as_tenant_admin):
        with patch(KC_SVC_PATH) as mock_kc:
            mock_kc.create_service_account = AsyncMock(side_effect=RuntimeError("KC error"))
            resp = client_as_tenant_admin.post(
                "/v1/service-accounts",
                json={"name": "test-sa"},
            )

        assert resp.status_code == 500


class TestDeleteServiceAccount:
    """Tests for DELETE /v1/service-accounts/{account_id}."""

    def test_delete_success(self, client_as_tenant_admin):
        with patch(KC_SVC_PATH) as mock_kc:
            mock_kc.delete_service_account = AsyncMock(return_value=None)
            resp = client_as_tenant_admin.delete("/v1/service-accounts/sa-1")

        assert resp.status_code == 204

    def test_delete_not_found(self, client_as_tenant_admin):
        with patch(KC_SVC_PATH) as mock_kc:
            mock_kc.delete_service_account = AsyncMock(side_effect=ValueError("Not found"))
            resp = client_as_tenant_admin.delete("/v1/service-accounts/nonexistent")

        assert resp.status_code == 404

    def test_delete_forbidden(self, client_as_tenant_admin):
        with patch(KC_SVC_PATH) as mock_kc:
            mock_kc.delete_service_account = AsyncMock(side_effect=PermissionError("Not yours"))
            resp = client_as_tenant_admin.delete("/v1/service-accounts/sa-other")

        assert resp.status_code == 403


class TestRegenerateSecret:
    """Tests for POST /v1/service-accounts/{account_id}/regenerate-secret."""

    def test_regenerate_success(self, client_as_tenant_admin):
        with patch(KC_SVC_PATH) as mock_kc:
            mock_kc.list_user_service_accounts = AsyncMock(
                return_value=[{"id": "sa-1", "client_id": "sa-acme-admin-claude"}]
            )
            mock_kc.regenerate_client_secret = AsyncMock(return_value="new-secret-value")
            resp = client_as_tenant_admin.post("/v1/service-accounts/sa-1/regenerate-secret")

        assert resp.status_code == 200
        data = resp.json()
        assert data["client_secret"] == "new-secret-value"

    def test_regenerate_not_found(self, client_as_tenant_admin):
        with patch(KC_SVC_PATH) as mock_kc:
            mock_kc.list_user_service_accounts = AsyncMock(return_value=[])
            resp = client_as_tenant_admin.post("/v1/service-accounts/nonexistent/regenerate-secret")

        assert resp.status_code == 404
