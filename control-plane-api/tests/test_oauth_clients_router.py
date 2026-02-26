"""Tests for OAuth Clients Router — CAB-1527

Covers: /v1/oauth-clients/ (register, list, get, revoke).

CRITICAL: This router uses current_user.get("tenant_id") — the user must be a dict,
          NOT a Pydantic User model. Custom app fixture required.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

IGS_PATH = "src.routers.oauth_clients.IdentityGovernanceService"
REPO_PATH = "src.routers.oauth_clients.OAuthClientRepository"


def _mock_client(**overrides):
    """Build a MagicMock mimicking an OAuthClient ORM object."""
    mock = MagicMock()
    defaults = {
        "id": str(uuid4()),
        "tenant_id": "acme",
        "keycloak_client_id": "kc-client-abc",
        "client_name": "acme-billing-service",
        "description": "Billing service",
        "product_roles": ["api:read", "billing:admin"],
        "oauth_metadata": {"grant_types": ["client_credentials"]},
        "status": "active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _build_app(app, mock_db_session, user_dict=None):
    """Build app with dict-based current_user override (oauth_clients router expects a dict)."""
    from src.auth import get_current_user
    from src.database import get_db

    if user_dict is None:
        user_dict = {
            "sub": "tenant-admin-user-id",
            "email": "admin@acme.com",
            "tenant_id": "acme",
            "realm_access": {"roles": ["tenant-admin"]},
        }

    async def override_user():
        return user_dict

    async def override_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return app


def _build_no_tenant_app(app, mock_db_session):
    """Build app for user with no tenant_id."""
    return _build_app(
        app,
        mock_db_session,
        user_dict={
            "sub": "orphan-user-id",
            "email": "orphan@example.com",
            "tenant_id": None,
            "realm_access": {"roles": []},
        },
    )


# ============== Register OAuth Client (POST /) ==============


class TestRegisterOAuthClient:
    """POST /v1/oauth-clients/"""

    def test_register_success(self, app, mock_db_session):
        client_obj = _mock_client()
        test_app = _build_app(app, mock_db_session)

        mock_svc = MagicMock()
        mock_svc.register_client = AsyncMock(return_value=client_obj)

        with patch(IGS_PATH, return_value=mock_svc), TestClient(test_app) as client:
            resp = client.post(
                "/v1/oauth-clients/",
                json={
                    "client_name": "acme-billing-service",
                    "description": "Billing service",
                    "product_roles": ["api:read"],
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["client_name"] == "acme-billing-service"
        assert data["tenant_id"] == "acme"
        mock_svc.register_client.assert_awaited_once()
        test_app.dependency_overrides.clear()

    def test_register_no_tenant_returns_403(self, app, mock_db_session):
        test_app = _build_no_tenant_app(app, mock_db_session)

        with TestClient(test_app) as client:
            resp = client.post(
                "/v1/oauth-clients/",
                json={"client_name": "some-client", "product_roles": []},
            )

        assert resp.status_code == 403
        assert "No tenant_id" in resp.json()["detail"]
        test_app.dependency_overrides.clear()

    def test_register_value_error_returns_400(self, app, mock_db_session):
        test_app = _build_app(app, mock_db_session)

        mock_svc = MagicMock()
        mock_svc.register_client = AsyncMock(side_effect=ValueError("invalid role"))

        with patch(IGS_PATH, return_value=mock_svc), TestClient(test_app) as client:
            resp = client.post(
                "/v1/oauth-clients/",
                json={"client_name": "bad-client", "product_roles": ["bad:role"]},
            )

        assert resp.status_code == 400
        assert "invalid role" in resp.json()["detail"]
        test_app.dependency_overrides.clear()

    def test_register_runtime_error_returns_503(self, app, mock_db_session):
        test_app = _build_app(app, mock_db_session)

        mock_svc = MagicMock()
        mock_svc.register_client = AsyncMock(side_effect=RuntimeError("Keycloak down"))

        with patch(IGS_PATH, return_value=mock_svc), TestClient(test_app) as client:
            resp = client.post(
                "/v1/oauth-clients/",
                json={"client_name": "down-client", "product_roles": []},
            )

        assert resp.status_code == 503
        test_app.dependency_overrides.clear()

    def test_register_unexpected_error_returns_503(self, app, mock_db_session):
        test_app = _build_app(app, mock_db_session)

        mock_svc = MagicMock()
        mock_svc.register_client = AsyncMock(side_effect=Exception("unexpected"))

        with patch(IGS_PATH, return_value=mock_svc), TestClient(test_app) as client:
            resp = client.post(
                "/v1/oauth-clients/",
                json={"client_name": "boom-client", "product_roles": []},
            )

        assert resp.status_code == 503
        test_app.dependency_overrides.clear()


# ============== List OAuth Clients (GET /) ==============


class TestListOAuthClients:
    """GET /v1/oauth-clients/"""

    def test_list_success(self, app, mock_db_session):
        clients = [_mock_client(), _mock_client(id=str(uuid4()), client_name="other-svc")]
        test_app = _build_app(app, mock_db_session)

        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=(clients, 2))

        with patch(REPO_PATH, return_value=mock_repo), TestClient(test_app) as client:
            resp = client.get("/v1/oauth-clients/")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        test_app.dependency_overrides.clear()

    def test_list_with_status_filter(self, app, mock_db_session):
        test_app = _build_app(app, mock_db_session)

        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([], 0))

        with patch(REPO_PATH, return_value=mock_repo), TestClient(test_app) as client:
            resp = client.get("/v1/oauth-clients/?status=active&page=2&page_size=5")

        assert resp.status_code == 200
        mock_repo.list_by_tenant.assert_awaited_once_with(
            "acme", page=2, page_size=5, status="active"
        )
        test_app.dependency_overrides.clear()

    def test_list_no_tenant_returns_403(self, app, mock_db_session):
        test_app = _build_no_tenant_app(app, mock_db_session)

        with TestClient(test_app) as client:
            resp = client.get("/v1/oauth-clients/")

        assert resp.status_code == 403
        test_app.dependency_overrides.clear()

    def test_list_empty_returns_200(self, app, mock_db_session):
        test_app = _build_app(app, mock_db_session)

        mock_repo = MagicMock()
        mock_repo.list_by_tenant = AsyncMock(return_value=([], 0))

        with patch(REPO_PATH, return_value=mock_repo), TestClient(test_app) as client:
            resp = client.get("/v1/oauth-clients/")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []
        test_app.dependency_overrides.clear()


# ============== Get OAuth Client (GET /{client_id}) ==============


class TestGetOAuthClient:
    """GET /v1/oauth-clients/{client_id}"""

    def test_get_success(self, app, mock_db_session):
        client_obj = _mock_client()
        test_app = _build_app(app, mock_db_session)

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=client_obj)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(test_app) as client:
            resp = client.get(f"/v1/oauth-clients/{client_obj.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["client_name"] == "acme-billing-service"
        test_app.dependency_overrides.clear()

    def test_get_not_found_returns_404(self, app, mock_db_session):
        test_app = _build_app(app, mock_db_session)

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(test_app) as client:
            resp = client.get("/v1/oauth-clients/nonexistent-id")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]
        test_app.dependency_overrides.clear()

    def test_get_wrong_tenant_returns_404(self, app, mock_db_session):
        """Client exists but belongs to a different tenant."""
        client_obj = _mock_client(tenant_id="other-tenant")
        test_app = _build_app(app, mock_db_session)

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=client_obj)

        with patch(REPO_PATH, return_value=mock_repo), TestClient(test_app) as client:
            resp = client.get(f"/v1/oauth-clients/{client_obj.id}")

        assert resp.status_code == 404
        test_app.dependency_overrides.clear()

    def test_get_no_tenant_returns_403(self, app, mock_db_session):
        test_app = _build_no_tenant_app(app, mock_db_session)

        with TestClient(test_app) as client:
            resp = client.get("/v1/oauth-clients/some-id")

        assert resp.status_code == 403
        test_app.dependency_overrides.clear()


# ============== Revoke OAuth Client (DELETE /{client_id}) ==============


class TestRevokeOAuthClient:
    """DELETE /v1/oauth-clients/{client_id}"""

    def test_revoke_success(self, app, mock_db_session):
        test_app = _build_app(app, mock_db_session)

        mock_svc = MagicMock()
        mock_svc.revoke_client = AsyncMock(return_value=True)

        with patch(IGS_PATH, return_value=mock_svc), TestClient(test_app) as client:
            resp = client.delete("/v1/oauth-clients/client-to-delete")

        assert resp.status_code == 204
        mock_svc.revoke_client.assert_awaited_once()
        test_app.dependency_overrides.clear()

    def test_revoke_not_found_returns_404(self, app, mock_db_session):
        test_app = _build_app(app, mock_db_session)

        mock_svc = MagicMock()
        mock_svc.revoke_client = AsyncMock(return_value=False)

        with patch(IGS_PATH, return_value=mock_svc), TestClient(test_app) as client:
            resp = client.delete("/v1/oauth-clients/nonexistent-client")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]
        test_app.dependency_overrides.clear()

    def test_revoke_no_tenant_returns_403(self, app, mock_db_session):
        test_app = _build_no_tenant_app(app, mock_db_session)

        with TestClient(test_app) as client:
            resp = client.delete("/v1/oauth-clients/some-id")

        assert resp.status_code == 403
        test_app.dependency_overrides.clear()


# ============== Helper: has_tenant_access ==============


class TestHasTenantAccess:
    """Unit tests for the _has_tenant_access helper."""

    def test_cpi_admin_has_access_to_any_tenant(self):
        from src.routers.oauth_clients import _has_tenant_access

        user = {"realm_access": {"roles": ["stoa:admin"]}, "tenant_id": None}
        assert _has_tenant_access(user, "any-tenant") is True

    def test_tenant_user_matches_own_tenant(self):
        from src.routers.oauth_clients import _has_tenant_access

        user = {"realm_access": {"roles": ["tenant-admin"]}, "tenant_id": "acme"}
        assert _has_tenant_access(user, "acme") is True

    def test_tenant_user_denied_other_tenant(self):
        from src.routers.oauth_clients import _has_tenant_access

        user = {"realm_access": {"roles": ["tenant-admin"]}, "tenant_id": "acme"}
        assert _has_tenant_access(user, "other-tenant") is False

    def test_no_realm_access_defaults_false(self):
        from src.routers.oauth_clients import _has_tenant_access

        user = {"tenant_id": "acme"}
        assert _has_tenant_access(user, "other-tenant") is False
