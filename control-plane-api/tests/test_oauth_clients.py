"""Tests for OAuth Clients Router — CAB-1526

Tests the /v1/oauth-clients/ endpoints with RBAC persona coverage.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

REPO_PATH = "src.routers.oauth_clients.OAuthClientRepository"
SVC_PATH = "src.routers.oauth_clients.IdentityGovernanceService"


def _mock_oauth_client(**overrides):
    """Build a MagicMock mimicking an OAuthClient ORM object."""
    mock = MagicMock()
    defaults = {
        "id": "client-001",
        "tenant_id": "acme",
        "keycloak_client_id": "kc-client-001",
        "client_name": "acme-billing-service",
        "description": "Billing service",
        "product_roles": ["api:read", "billing:admin"],
        "oauth_metadata": {"grant_types": ["client_credentials"]},
        "status": "active",
        "created_at": datetime(2026, 1, 15, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 15, tzinfo=UTC),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestRegisterOAuthClient:
    """POST /v1/oauth-clients/"""

    def test_register_success(self, client_as_tenant_admin):
        client_obj = _mock_oauth_client()
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.register_client = AsyncMock(return_value=client_obj)

            resp = client_as_tenant_admin.post(
                "/v1/oauth-clients/",
                json={
                    "client_name": "acme-billing-service",
                    "description": "Billing service",
                    "product_roles": ["api:read"],
                },
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["client_name"] == "acme-billing-service"
        assert body["tenant_id"] == "acme"
        assert body["keycloak_client_id"] == "kc-client-001"

    def test_register_no_tenant_returns_403(self, client_as_no_tenant_user):
        resp = client_as_no_tenant_user.post(
            "/v1/oauth-clients/",
            json={"client_name": "test"},
        )
        assert resp.status_code == 403
        assert "tenant_id" in resp.json()["detail"].lower()

    def test_register_value_error_returns_400(self, client_as_tenant_admin):
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.register_client = AsyncMock(side_effect=ValueError("Invalid client name"))

            resp = client_as_tenant_admin.post(
                "/v1/oauth-clients/",
                json={"client_name": "bad-name"},
            )

        assert resp.status_code == 400
        assert "Invalid client name" in resp.json()["detail"]

    def test_register_runtime_error_returns_503(self, client_as_tenant_admin):
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.register_client = AsyncMock(side_effect=RuntimeError("Keycloak down"))

            resp = client_as_tenant_admin.post(
                "/v1/oauth-clients/",
                json={"client_name": "test"},
            )

        assert resp.status_code == 503
        assert "Keycloak down" in resp.json()["detail"]

    def test_register_unexpected_error_returns_503(self, client_as_tenant_admin):
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.register_client = AsyncMock(side_effect=ConnectionError("boom"))

            resp = client_as_tenant_admin.post(
                "/v1/oauth-clients/",
                json={"client_name": "test"},
            )

        assert resp.status_code == 503
        assert "Internal error" in resp.json()["detail"]

    def test_register_cpi_admin_no_tenant_returns_403(self, client_as_cpi_admin):
        """CPI admin without tenant_id cannot register clients."""
        resp = client_as_cpi_admin.post(
            "/v1/oauth-clients/",
            json={"client_name": "test"},
        )
        assert resp.status_code == 403


class TestListOAuthClients:
    """GET /v1/oauth-clients/"""

    def test_list_success(self, client_as_tenant_admin):
        clients = [_mock_oauth_client(), _mock_oauth_client(id="client-002", client_name="acme-payments")]
        with patch(REPO_PATH) as MockRepo:
            instance = MockRepo.return_value
            instance.list_by_tenant = AsyncMock(return_value=(clients, 2))

            resp = client_as_tenant_admin.get("/v1/oauth-clients/")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2
        assert body["page"] == 1
        assert body["page_size"] == 20

    def test_list_with_pagination(self, client_as_tenant_admin):
        with patch(REPO_PATH) as MockRepo:
            instance = MockRepo.return_value
            instance.list_by_tenant = AsyncMock(return_value=([], 0))

            resp = client_as_tenant_admin.get("/v1/oauth-clients/?page=2&page_size=5")

        assert resp.status_code == 200
        body = resp.json()
        assert body["page"] == 2
        assert body["page_size"] == 5

    def test_list_with_status_filter(self, client_as_tenant_admin):
        with patch(REPO_PATH) as MockRepo:
            instance = MockRepo.return_value
            instance.list_by_tenant = AsyncMock(return_value=([], 0))

            resp = client_as_tenant_admin.get("/v1/oauth-clients/?status=active")

        assert resp.status_code == 200
        instance.list_by_tenant.assert_awaited_once_with("acme", page=1, page_size=20, status="active")

    def test_list_no_tenant_returns_403(self, client_as_no_tenant_user):
        resp = client_as_no_tenant_user.get("/v1/oauth-clients/")
        assert resp.status_code == 403


class TestGetOAuthClient:
    """GET /v1/oauth-clients/{client_id}"""

    def test_get_success(self, client_as_tenant_admin):
        client_obj = _mock_oauth_client()
        with patch(REPO_PATH) as MockRepo:
            instance = MockRepo.return_value
            instance.get_by_id = AsyncMock(return_value=client_obj)

            resp = client_as_tenant_admin.get("/v1/oauth-clients/client-001")

        assert resp.status_code == 200
        assert resp.json()["id"] == "client-001"

    def test_get_not_found(self, client_as_tenant_admin):
        with patch(REPO_PATH) as MockRepo:
            instance = MockRepo.return_value
            instance.get_by_id = AsyncMock(return_value=None)

            resp = client_as_tenant_admin.get("/v1/oauth-clients/nonexistent")

        assert resp.status_code == 404

    def test_get_other_tenant_returns_404(self, client_as_tenant_admin):
        """Client from another tenant returns 404 (not 403 — no info leak)."""
        client_obj = _mock_oauth_client(tenant_id="other-tenant")
        with patch(REPO_PATH) as MockRepo:
            instance = MockRepo.return_value
            instance.get_by_id = AsyncMock(return_value=client_obj)

            resp = client_as_tenant_admin.get("/v1/oauth-clients/client-001")

        assert resp.status_code == 404

    def test_get_no_tenant_returns_403(self, client_as_no_tenant_user):
        resp = client_as_no_tenant_user.get("/v1/oauth-clients/client-001")
        assert resp.status_code == 403


class TestRevokeOAuthClient:
    """DELETE /v1/oauth-clients/{client_id}"""

    def test_revoke_success(self, client_as_tenant_admin):
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.revoke_client = AsyncMock(return_value=True)

            resp = client_as_tenant_admin.delete("/v1/oauth-clients/client-001")

        assert resp.status_code == 204

    def test_revoke_not_found(self, client_as_tenant_admin):
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.revoke_client = AsyncMock(return_value=False)

            resp = client_as_tenant_admin.delete("/v1/oauth-clients/nonexistent")

        assert resp.status_code == 404

    def test_revoke_no_tenant_returns_403(self, client_as_no_tenant_user):
        resp = client_as_no_tenant_user.delete("/v1/oauth-clients/client-001")
        assert resp.status_code == 403

    def test_revoke_passes_actor_info(self, client_as_tenant_admin):
        """Verify actor_id and actor_email are forwarded to service."""
        with patch(SVC_PATH) as MockSvc:
            instance = MockSvc.return_value
            instance.revoke_client = AsyncMock(return_value=True)

            client_as_tenant_admin.delete("/v1/oauth-clients/client-001")

            instance.revoke_client.assert_awaited_once()
            call_kwargs = instance.revoke_client.call_args.kwargs
            assert call_kwargs["client_id"] == "client-001"
            assert call_kwargs["tenant_id"] == "acme"
            assert call_kwargs["actor_id"] is not None
            assert call_kwargs["actor_email"] is not None
