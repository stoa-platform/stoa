"""Tests for applications router — Keycloak-backed CRUD."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Shared mock user fixtures
_ADMIN_USER = MagicMock()
_ADMIN_USER.id = "admin-1"
_ADMIN_USER.email = "admin@gostoa.dev"
_ADMIN_USER.tenant_id = "acme"
_ADMIN_USER.roles = ["cpi-admin"]

_VIEWER_USER = MagicMock()
_VIEWER_USER.id = "viewer-1"
_VIEWER_USER.email = "viewer@gostoa.dev"
_VIEWER_USER.tenant_id = "acme"
_VIEWER_USER.roles = ["viewer"]

_OTHER_TENANT_USER = MagicMock()
_OTHER_TENANT_USER.id = "other-1"
_OTHER_TENANT_USER.email = "other@corp.dev"
_OTHER_TENANT_USER.tenant_id = "other-corp"
_OTHER_TENANT_USER.roles = ["tenant-admin"]


def _make_kc_client(
    uuid: str = "kc-uuid-1",
    client_id: str = "acme-myapp",
    name: str = "My App",
    tenant_id: str = "acme",
    enabled: bool = True,
    api_subscriptions: list | None = None,
):
    """Build a Keycloak client dict."""
    return {
        "id": uuid,
        "clientId": client_id,
        "name": name,
        "description": "A test app",
        "enabled": enabled,
        "attributes": {
            "tenant_id": [tenant_id],
            "api_subscriptions": [json.dumps(api_subscriptions or [])],
            "created_at": ["2026-01-01T00:00:00+00:00"],
            "updated_at": ["2026-01-01T00:00:00+00:00"],
        },
    }


def _build_test_app(user=None):
    """Create a FastAPI test app with mocked auth."""
    from src.routers.applications import router

    app = FastAPI()
    app.include_router(router)

    if user is None:
        user = _ADMIN_USER

    async def override_get_current_user():
        return user

    from src.auth.dependencies import get_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    return app


TENANT = "acme"
BASE = f"/v1/tenants/{TENANT}/applications"


# ---- List ----


@patch("src.routers.applications.keycloak_service")
def test_list_empty(mock_kc):
    mock_kc.get_clients = AsyncMock(return_value=[])
    client = TestClient(_build_test_app())
    resp = client.get(BASE)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@patch("src.routers.applications.keycloak_service")
def test_list_with_data(mock_kc):
    mock_kc.get_clients = AsyncMock(return_value=[_make_kc_client()])
    client = TestClient(_build_test_app())
    resp = client.get(BASE)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "myapp"
    assert data["items"][0]["client_id"] == "acme-myapp"


@patch("src.routers.applications.keycloak_service")
def test_list_pagination(mock_kc):
    clients = [_make_kc_client(uuid=f"uuid-{i}", client_id=f"acme-app{i}") for i in range(5)]
    mock_kc.get_clients = AsyncMock(return_value=clients)
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}?page=2&page_size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2


# ---- Get ----


@patch("src.routers.applications.keycloak_service")
def test_get_success(mock_kc):
    mock_kc.get_client_by_id = AsyncMock(return_value=_make_kc_client())
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/kc-uuid-1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "kc-uuid-1"


@patch("src.routers.applications.keycloak_service")
def test_get_not_found(mock_kc):
    mock_kc.get_client_by_id = AsyncMock(return_value=None)
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/nonexistent")
    assert resp.status_code == 404


@patch("src.routers.applications.keycloak_service")
def test_get_wrong_tenant(mock_kc):
    mock_kc.get_client_by_id = AsyncMock(return_value=_make_kc_client(tenant_id="other", client_id="other-x"))
    client = TestClient(_build_test_app())
    resp = client.get(f"{BASE}/kc-uuid-1")
    assert resp.status_code == 404


# ---- Create ----


@patch("src.routers.applications.keycloak_service")
def test_create(mock_kc):
    mock_kc.create_client = AsyncMock(
        return_value={"id": "new-uuid", "client_id": "acme-newapp", "client_secret": "s3cret"}
    )
    mock_kc.update_client = AsyncMock(return_value=True)
    mock_kc.get_client_by_id = AsyncMock(
        return_value=_make_kc_client(uuid="new-uuid", client_id="acme-newapp", name="New App")
    )
    client = TestClient(_build_test_app())
    resp = client.post(
        BASE,
        json={
            "name": "newapp",
            "display_name": "New App",
            "description": "desc",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == "new-uuid"


@patch("src.routers.applications.keycloak_service")
def test_create_viewer_forbidden(mock_kc):
    client = TestClient(_build_test_app(user=_VIEWER_USER))
    resp = client.post(BASE, json={"name": "x", "display_name": "X"})
    assert resp.status_code == 403


# ---- Update ----


@patch("src.routers.applications.keycloak_service")
def test_update(mock_kc):
    mock_kc.get_client_by_id = AsyncMock(return_value=_make_kc_client())
    mock_kc.update_client = AsyncMock(return_value=True)
    updated = _make_kc_client(name="Updated Name")
    mock_kc.get_client_by_id = AsyncMock(side_effect=[_make_kc_client(), updated])
    client = TestClient(_build_test_app())
    resp = client.put(
        f"{BASE}/kc-uuid-1",
        json={
            "name": "myapp",
            "display_name": "Updated Name",
        },
    )
    assert resp.status_code == 200


# ---- Delete ----


@patch("src.routers.applications.keycloak_service")
def test_delete(mock_kc):
    mock_kc.get_client_by_id = AsyncMock(return_value=_make_kc_client())
    mock_kc.delete_client = AsyncMock(return_value=True)
    client = TestClient(_build_test_app())
    resp = client.delete(f"{BASE}/kc-uuid-1")
    assert resp.status_code == 204


@patch("src.routers.applications.keycloak_service")
def test_delete_viewer_forbidden(mock_kc):
    client = TestClient(_build_test_app(user=_VIEWER_USER))
    resp = client.delete(f"{BASE}/kc-uuid-1")
    assert resp.status_code == 403


# ---- Regenerate Secret ----


@patch("src.routers.applications.keycloak_service")
def test_regenerate_secret(mock_kc):
    mock_kc.get_client_by_id = AsyncMock(return_value=_make_kc_client())
    mock_kc.regenerate_client_secret = AsyncMock(return_value="new-secret-value")
    client = TestClient(_build_test_app())
    resp = client.post(f"{BASE}/kc-uuid-1/regenerate-secret")
    assert resp.status_code == 200
    assert resp.json()["client_secret"] == "new-secret-value"


# ---- Subscribe / Unsubscribe ----


@patch("src.routers.applications.keycloak_service")
def test_subscribe(mock_kc):
    mock_kc.get_client_by_id = AsyncMock(return_value=_make_kc_client())
    mock_kc.update_client = AsyncMock(return_value=True)
    client = TestClient(_build_test_app())
    resp = client.post(f"{BASE}/kc-uuid-1/subscribe/api-123")
    assert resp.status_code == 200
    assert "subscribed" in resp.json()["message"]


@patch("src.routers.applications.keycloak_service")
def test_subscribe_duplicate(mock_kc):
    mock_kc.get_client_by_id = AsyncMock(return_value=_make_kc_client(api_subscriptions=["api-123"]))
    client = TestClient(_build_test_app())
    resp = client.post(f"{BASE}/kc-uuid-1/subscribe/api-123")
    assert resp.status_code == 409


@patch("src.routers.applications.keycloak_service")
def test_unsubscribe(mock_kc):
    mock_kc.get_client_by_id = AsyncMock(return_value=_make_kc_client(api_subscriptions=["api-123"]))
    mock_kc.update_client = AsyncMock(return_value=True)
    client = TestClient(_build_test_app())
    resp = client.delete(f"{BASE}/kc-uuid-1/subscribe/api-123")
    assert resp.status_code == 200
    assert "unsubscribed" in resp.json()["message"]


@patch("src.routers.applications.keycloak_service")
def test_unsubscribe_not_subscribed(mock_kc):
    mock_kc.get_client_by_id = AsyncMock(return_value=_make_kc_client())
    client = TestClient(_build_test_app())
    resp = client.delete(f"{BASE}/kc-uuid-1/subscribe/api-999")
    assert resp.status_code == 404


# ---- Tenant isolation ----


@patch("src.routers.applications.keycloak_service")
def test_tenant_isolation(mock_kc):
    """Other tenant user cannot access acme's applications."""
    client = TestClient(_build_test_app(user=_OTHER_TENANT_USER))
    mock_kc.get_clients = AsyncMock(return_value=[])
    resp = client.get(BASE)
    assert resp.status_code == 403


# ---- Viewer can read ----


@patch("src.routers.applications.keycloak_service")
def test_viewer_can_list(mock_kc):
    mock_kc.get_clients = AsyncMock(return_value=[])
    client = TestClient(_build_test_app(user=_VIEWER_USER))
    resp = client.get(BASE)
    assert resp.status_code == 200
