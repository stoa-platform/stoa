"""Tests for Applications Router — CAB-1437

Covers: GET/POST/PUT/DELETE /v1/tenants/{tenant_id}/applications
        POST /{app_id}/regenerate-secret
        POST/DELETE /{app_id}/subscribe/{api_id}

RBAC: @require_tenant_access (cpi-admin or own tenant).
Permissions: APPS_CREATE, APPS_UPDATE, APPS_DELETE via @require_permission.
"""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

KC_SVC_PATH = "src.routers.applications.keycloak_service"


def _mock_kc_client(app_id="app-uuid-1", tenant_id="acme", **overrides):
    """Build a dict that mimics a Keycloak client object."""
    now = "2026-01-01T00:00:00"
    data = {
        "id": app_id,
        "clientId": f"{tenant_id}-my-app",
        "name": "My App",
        "description": "Test application",
        "enabled": True,
        "redirectUris": [],
        "attributes": {
            "tenant_id": tenant_id,
            "api_subscriptions": ["[]"],
            "created_at": now,
            "updated_at": now,
        },
    }
    data.update(overrides)
    return data


# ============== RBAC: @require_tenant_access ==============


class TestApplicationsRBAC:
    """@require_tenant_access blocks cross-tenant access."""

    def test_list_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.get("/v1/tenants/acme/applications")

        assert resp.status_code == 403

    def test_list_200_own_tenant(self, app_with_tenant_admin, mock_db_session):
        with (
            patch(f"{KC_SVC_PATH}.get_clients", new=AsyncMock(return_value=[])),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/applications")

        assert resp.status_code == 200

    def test_list_200_as_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        with (
            patch(f"{KC_SVC_PATH}.get_clients", new=AsyncMock(return_value=[])),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/applications")

        assert resp.status_code == 200


# ============== List Applications ==============


class TestListApplications:
    """GET /v1/tenants/{tenant_id}/applications"""

    def test_list_empty(self, app_with_tenant_admin, mock_db_session):
        with (
            patch(f"{KC_SVC_PATH}.get_clients", new=AsyncMock(return_value=[])),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/applications")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_with_clients(self, app_with_tenant_admin, mock_db_session):
        clients = [_mock_kc_client("id-1"), _mock_kc_client("id-2")]

        with (
            patch(f"{KC_SVC_PATH}.get_clients", new=AsyncMock(return_value=clients)),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/applications")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_list_pagination(self, app_with_tenant_admin, mock_db_session):
        clients = [_mock_kc_client(f"id-{i}") for i in range(5)]

        with (
            patch(f"{KC_SVC_PATH}.get_clients", new=AsyncMock(return_value=clients)),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/applications?page=2&page_size=2")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2  # page 2 of page_size=2 → items[2:4]


# ============== Get Application ==============


class TestGetApplication:
    """GET /v1/tenants/{tenant_id}/applications/{app_id}"""

    def test_get_success(self, app_with_tenant_admin, mock_db_session):
        client_data = _mock_kc_client("app-1", "acme")

        with (
            patch(f"{KC_SVC_PATH}.get_client_by_id", new=AsyncMock(return_value=client_data)),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/applications/app-1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "app-1"
        assert data["tenant_id"] == "acme"

    def test_get_404_not_found(self, app_with_tenant_admin, mock_db_session):
        with (
            patch(f"{KC_SVC_PATH}.get_client_by_id", new=AsyncMock(return_value=None)),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/applications/nonexistent")

        assert resp.status_code == 404

    def test_get_404_wrong_tenant(self, app_with_tenant_admin, mock_db_session):
        # Client belongs to "other-tenant", not "acme"
        client_data = _mock_kc_client("app-1", "other-tenant")

        with (
            patch(f"{KC_SVC_PATH}.get_client_by_id", new=AsyncMock(return_value=client_data)),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/applications/app-1")

        assert resp.status_code == 404


# ============== Create Application ==============


class TestCreateApplication:
    """POST /v1/tenants/{tenant_id}/applications"""

    def test_create_success(self, app_with_tenant_admin, mock_db_session):
        created_client = _mock_kc_client("new-app-id", "acme")

        with (
            patch(f"{KC_SVC_PATH}.create_client", new=AsyncMock(return_value={"id": "new-app-id"})),
            patch(f"{KC_SVC_PATH}.update_client", new=AsyncMock(return_value=None)),
            patch(f"{KC_SVC_PATH}.get_client_by_id", new=AsyncMock(return_value=created_client)),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.post(
                "/v1/tenants/acme/applications",
                json={
                    "name": "my-app",
                    "display_name": "My App",
                    "description": "Test app",
                    "redirect_uris": ["https://example.com/callback"],
                    "api_subscriptions": [],
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "new-app-id"

    def test_create_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.post(
                "/v1/tenants/acme/applications",
                json={"name": "app", "display_name": "App", "redirect_uris": []},
            )

        assert resp.status_code == 403


# ============== Update Application ==============


class TestUpdateApplication:
    """PUT /v1/tenants/{tenant_id}/applications/{app_id}"""

    def test_update_success(self, app_with_tenant_admin, mock_db_session):
        original = _mock_kc_client("app-1", "acme")
        updated = _mock_kc_client("app-1", "acme", name="Updated App")

        with (
            patch(f"{KC_SVC_PATH}.get_client_by_id", new=AsyncMock(side_effect=[original, updated])),
            patch(f"{KC_SVC_PATH}.update_client", new=AsyncMock(return_value=None)),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.put(
                "/v1/tenants/acme/applications/app-1",
                json={"name": "my-app", "display_name": "Updated App", "redirect_uris": []},
            )

        assert resp.status_code == 200

    def test_update_404_not_found(self, app_with_tenant_admin, mock_db_session):
        with (
            patch(f"{KC_SVC_PATH}.get_client_by_id", new=AsyncMock(return_value=None)),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.put(
                "/v1/tenants/acme/applications/nonexistent",
                json={"name": "app", "display_name": "App", "redirect_uris": []},
            )

        assert resp.status_code == 404


# ============== Delete Application ==============


class TestDeleteApplication:
    """DELETE /v1/tenants/{tenant_id}/applications/{app_id}"""

    def test_delete_success(self, app_with_tenant_admin, mock_db_session):
        client_data = _mock_kc_client("app-1", "acme")

        with (
            patch(f"{KC_SVC_PATH}.get_client_by_id", new=AsyncMock(return_value=client_data)),
            patch(f"{KC_SVC_PATH}.delete_client", new=AsyncMock(return_value=None)),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.delete("/v1/tenants/acme/applications/app-1")

        assert resp.status_code == 204

    def test_delete_404_not_found(self, app_with_tenant_admin, mock_db_session):
        with (
            patch(f"{KC_SVC_PATH}.get_client_by_id", new=AsyncMock(return_value=None)),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.delete("/v1/tenants/acme/applications/nonexistent")

        assert resp.status_code == 404


# ============== Regenerate Secret ==============


class TestRegenerateSecret:
    """POST /v1/tenants/{tenant_id}/applications/{app_id}/regenerate-secret"""

    def test_regenerate_success(self, app_with_tenant_admin, mock_db_session):
        client_data = _mock_kc_client("app-1", "acme")

        with (
            patch(f"{KC_SVC_PATH}.get_client_by_id", new=AsyncMock(return_value=client_data)),
            patch(f"{KC_SVC_PATH}.regenerate_client_secret", new=AsyncMock(return_value="new-secret-xyz")),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.post("/v1/tenants/acme/applications/app-1/regenerate-secret")

        assert resp.status_code == 200
        data = resp.json()
        assert data["client_secret"] == "new-secret-xyz"
        assert "client_id" in data


# ============== Subscribe / Unsubscribe ==============


class TestSubscriptions:
    """POST/DELETE /v1/tenants/{tenant_id}/applications/{app_id}/subscribe/{api_id}"""

    def test_subscribe_success(self, app_with_tenant_admin, mock_db_session):
        client_data = _mock_kc_client("app-1", "acme")

        with (
            patch(f"{KC_SVC_PATH}.get_client_by_id", new=AsyncMock(return_value=client_data)),
            patch(f"{KC_SVC_PATH}.update_client", new=AsyncMock(return_value=None)),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.post("/v1/tenants/acme/applications/app-1/subscribe/api-123")

        assert resp.status_code == 200
        assert "api-123" in resp.json()["message"]

    def test_subscribe_409_already_subscribed(self, app_with_tenant_admin, mock_db_session):
        client_data = _mock_kc_client(
            "app-1",
            "acme",
            attributes={
                "tenant_id": "acme",
                "api_subscriptions": ['["api-123"]'],
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            },
        )

        with (
            patch(f"{KC_SVC_PATH}.get_client_by_id", new=AsyncMock(return_value=client_data)),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.post("/v1/tenants/acme/applications/app-1/subscribe/api-123")

        assert resp.status_code == 409

    def test_unsubscribe_success(self, app_with_tenant_admin, mock_db_session):
        client_data = _mock_kc_client(
            "app-1",
            "acme",
            attributes={
                "tenant_id": "acme",
                "api_subscriptions": ['["api-123"]'],
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            },
        )

        with (
            patch(f"{KC_SVC_PATH}.get_client_by_id", new=AsyncMock(return_value=client_data)),
            patch(f"{KC_SVC_PATH}.update_client", new=AsyncMock(return_value=None)),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.delete("/v1/tenants/acme/applications/app-1/subscribe/api-123")

        assert resp.status_code == 200
        assert "api-123" in resp.json()["message"]

    def test_unsubscribe_404_not_subscribed(self, app_with_tenant_admin, mock_db_session):
        client_data = _mock_kc_client("app-1", "acme")  # empty subscriptions

        with (
            patch(f"{KC_SVC_PATH}.get_client_by_id", new=AsyncMock(return_value=client_data)),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.delete("/v1/tenants/acme/applications/app-1/subscribe/nonexistent-api")

        assert resp.status_code == 404
