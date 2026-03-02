"""Tests for MCP Connector Catalog Router — App Store pattern.

Endpoints:
- GET    /v1/admin/mcp-connectors              — List catalog with connection status
- GET    /v1/admin/mcp-connectors/{slug}        — Template detail
- POST   /v1/admin/mcp-connectors/{slug}/authorize  — Initiate OAuth flow
- POST   /v1/admin/mcp-connectors/callback      — OAuth callback (code+state exchange)
- DELETE /v1/admin/mcp-connectors/{slug}/disconnect  — Disconnect connector

Auth: get_current_user + _require_admin (cpi-admin or tenant-admin).
Exception: /callback has NO auth (CSRF state token provides security).
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

# Patch paths (where objects are looked up at runtime in the router)
TEMPLATE_REPO_PATH = "src.routers.mcp_connectors.ConnectorTemplateRepository"
SESSION_REPO_PATH = "src.routers.mcp_connectors.OAuthSessionRepository"
CONNECTOR_SERVER_REPO_PATH = "src.routers.mcp_connectors.ConnectorServerRepository"
EXT_SERVER_REPO_PATH = "src.routers.mcp_connectors.ExternalMCPServerRepository"
OAUTH_SERVICE_PATH = "src.routers.mcp_connectors.ConnectorOAuthService"
SETTINGS_PATH = "src.routers.mcp_connectors.settings"

BASE = "/v1/admin/mcp-connectors"


def _mock_template(**overrides):
    """Create a mock MCPConnectorTemplate."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "slug": "linear",
        "display_name": "Linear",
        "description": "Linear issue tracking MCP server",
        "icon_url": "https://linear.app/icon.png",
        "category": "project-management",
        "mcp_base_url": "https://mcp.linear.app/sse",
        "transport": "sse",
        "oauth_authorize_url": "https://linear.app/oauth/authorize",
        "oauth_token_url": "https://api.linear.app/oauth/token",
        "oauth_scopes": "read write",
        "oauth_pkce_required": True,
        "documentation_url": "https://developers.linear.app",
        "is_featured": True,
        "enabled": True,
        "sort_order": 10,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    for k, v in {**defaults, **overrides}.items():
        setattr(mock, k, v)
    return mock


def _mock_server(**overrides):
    """Create a mock ExternalMCPServer for connector tests."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "name": "linear-abcd1234",
        "display_name": "Linear",
        "description": "Linear issue tracking MCP server",
        "icon": "https://linear.app/icon.png",
        "base_url": "https://mcp.linear.app/sse",
        "transport": "sse",
        "auth_type": "oauth2",
        "tool_prefix": "linear",
        "tenant_id": "acme",
        "created_by": "admin-user-id",
        "connector_template_id": uuid4(),
        "credential_vault_path": "external-mcp-servers/some-uuid",
    }
    for k, v in {**defaults, **overrides}.items():
        setattr(mock, k, v)
    return mock


# ============== List Connectors ==============


class TestListConnectors:
    """GET /v1/admin/mcp-connectors"""

    def test_list_connectors_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        """CPI admin sees full catalog with connection status."""
        templates = [_mock_template(), _mock_template(slug="github", display_name="GitHub")]

        with (
            patch(TEMPLATE_REPO_PATH) as MockTemplateRepo,
            patch(CONNECTOR_SERVER_REPO_PATH) as MockConnServerRepo,
        ):
            MockTemplateRepo.return_value.list_all = AsyncMock(return_value=templates)
            MockConnServerRepo.return_value.list_connected_template_ids = AsyncMock(return_value={})

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(BASE)

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 2
        assert len(data["connectors"]) == 2
        assert data["connectors"][0]["slug"] == "linear"
        assert data["connectors"][0]["is_connected"] is False

    def test_list_connectors_with_connected(self, app_with_cpi_admin, mock_db_session):
        """Connected templates show is_connected=True and server_id."""
        template = _mock_template()
        server_id = uuid4()
        connected_map = {template.id: (server_id, "healthy")}

        with (
            patch(TEMPLATE_REPO_PATH) as MockTemplateRepo,
            patch(CONNECTOR_SERVER_REPO_PATH) as MockConnServerRepo,
        ):
            MockTemplateRepo.return_value.list_all = AsyncMock(return_value=[template])
            MockConnServerRepo.return_value.list_connected_template_ids = AsyncMock(return_value=connected_map)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(BASE)

        assert response.status_code == 200
        data = response.json()
        assert data["connectors"][0]["is_connected"] is True
        assert data["connectors"][0]["connected_server_id"] == str(server_id)
        assert data["connectors"][0]["connection_health"] == "healthy"

    def test_list_connectors_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin can list connectors (uses own tenant_id)."""
        with (
            patch(TEMPLATE_REPO_PATH) as MockTemplateRepo,
            patch(CONNECTOR_SERVER_REPO_PATH) as MockConnServerRepo,
        ):
            MockTemplateRepo.return_value.list_all = AsyncMock(return_value=[])
            MockConnServerRepo.return_value.list_connected_template_ids = AsyncMock(return_value={})

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(BASE)

        assert response.status_code == 200

    def test_list_connectors_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        """Viewer (no admin role) gets 403."""
        with TestClient(app_with_no_tenant_user) as client:
            response = client.get(BASE)

        assert response.status_code == 403

    def test_list_connectors_cpi_admin_with_tenant_filter(self, app_with_cpi_admin, mock_db_session):
        """CPI admin can filter by explicit tenant_id."""
        with (
            patch(TEMPLATE_REPO_PATH) as MockTemplateRepo,
            patch(CONNECTOR_SERVER_REPO_PATH) as MockConnServerRepo,
        ):
            MockTemplateRepo.return_value.list_all = AsyncMock(return_value=[])
            MockConnServerRepo.return_value.list_connected_template_ids = AsyncMock(return_value={})

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"{BASE}?tenant_id=other-tenant")

        assert response.status_code == 200


# ============== Get Connector Detail ==============


class TestGetConnector:
    """GET /v1/admin/mcp-connectors/{slug}"""

    def test_get_connector_found(self, app_with_cpi_admin, mock_db_session):
        """Returns connector template detail."""
        template = _mock_template()

        with (
            patch(TEMPLATE_REPO_PATH) as MockTemplateRepo,
            patch(CONNECTOR_SERVER_REPO_PATH) as MockConnServerRepo,
        ):
            MockTemplateRepo.return_value.get_by_slug = AsyncMock(return_value=template)
            MockConnServerRepo.return_value.list_connected_template_ids = AsyncMock(return_value={})

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"{BASE}/linear")

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == "linear"
        assert data["display_name"] == "Linear"
        assert data["category"] == "project-management"

    def test_get_connector_not_found(self, app_with_cpi_admin, mock_db_session):
        """Returns 404 for unknown slug."""
        with patch(TEMPLATE_REPO_PATH) as MockTemplateRepo:
            MockTemplateRepo.return_value.get_by_slug = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"{BASE}/nonexistent")

        assert response.status_code == 404

    def test_get_connector_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        """Viewer gets 403."""
        with TestClient(app_with_no_tenant_user) as client:
            response = client.get(f"{BASE}/linear")

        assert response.status_code == 403


# ============== Authorize ==============


class TestAuthorize:
    """POST /v1/admin/mcp-connectors/{slug}/authorize"""

    def test_authorize_success(self, app_with_cpi_admin, mock_db_session):
        """Initiates OAuth flow and returns authorize URL + state."""
        template = _mock_template()
        authorize_url = "https://linear.app/oauth/authorize?client_id=xxx&state=abc"
        state = "csrf-state-token"

        with (
            patch(TEMPLATE_REPO_PATH) as MockTemplateRepo,
            patch(CONNECTOR_SERVER_REPO_PATH),
            patch(SESSION_REPO_PATH),
            patch(EXT_SERVER_REPO_PATH),
            patch(OAUTH_SERVICE_PATH) as MockOAuthService,
        ):
            MockTemplateRepo.return_value.get_by_slug = AsyncMock(return_value=template)
            mock_service = MockOAuthService.return_value
            mock_service.initiate_authorize = AsyncMock(return_value=(authorize_url, state))

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    f"{BASE}/linear/authorize",
                    json={"tenant_id": "acme"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["authorize_url"] == authorize_url
        assert data["state"] == state

    def test_authorize_template_not_found(self, app_with_cpi_admin, mock_db_session):
        """Returns 404 when slug not found."""
        with patch(TEMPLATE_REPO_PATH) as MockTemplateRepo:
            MockTemplateRepo.return_value.get_by_slug = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    f"{BASE}/nonexistent/authorize",
                    json={},
                )

        assert response.status_code == 404

    def test_authorize_template_disabled(self, app_with_cpi_admin, mock_db_session):
        """Returns 400 when template is disabled."""
        template = _mock_template(enabled=False)

        with patch(TEMPLATE_REPO_PATH) as MockTemplateRepo:
            MockTemplateRepo.return_value.get_by_slug = AsyncMock(return_value=template)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    f"{BASE}/linear/authorize",
                    json={},
                )

        assert response.status_code == 400

    def test_authorize_already_connected_409(self, app_with_cpi_admin, mock_db_session):
        """Returns 409 when connector already connected for tenant."""
        from src.services.connector_oauth import ConnectorOAuthError

        template = _mock_template()

        with (
            patch(TEMPLATE_REPO_PATH) as MockTemplateRepo,
            patch(CONNECTOR_SERVER_REPO_PATH),
            patch(SESSION_REPO_PATH),
            patch(EXT_SERVER_REPO_PATH),
            patch(OAUTH_SERVICE_PATH) as MockOAuthService,
        ):
            MockTemplateRepo.return_value.get_by_slug = AsyncMock(return_value=template)
            mock_service = MockOAuthService.return_value
            mock_service.initiate_authorize = AsyncMock(
                side_effect=ConnectorOAuthError(
                    "Connector 'linear' is already connected for this tenant",
                    status_code=409,
                )
            )

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    f"{BASE}/linear/authorize",
                    json={"tenant_id": "acme"},
                )

        assert response.status_code == 409

    def test_authorize_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        """Viewer gets 403."""
        with TestClient(app_with_no_tenant_user) as client:
            response = client.post(
                f"{BASE}/linear/authorize",
                json={},
            )

        assert response.status_code == 403

    def test_authorize_tenant_admin_uses_own_tenant(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin ignores explicit tenant_id and uses own."""
        template = _mock_template()
        authorize_url = "https://linear.app/oauth/authorize?state=xyz"
        state = "xyz"

        with (
            patch(TEMPLATE_REPO_PATH) as MockTemplateRepo,
            patch(CONNECTOR_SERVER_REPO_PATH),
            patch(SESSION_REPO_PATH),
            patch(EXT_SERVER_REPO_PATH),
            patch(OAUTH_SERVICE_PATH) as MockOAuthService,
        ):
            MockTemplateRepo.return_value.get_by_slug = AsyncMock(return_value=template)
            mock_service = MockOAuthService.return_value
            mock_service.initiate_authorize = AsyncMock(return_value=(authorize_url, state))

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"{BASE}/linear/authorize",
                    json={"tenant_id": "other-tenant"},
                )

        assert response.status_code == 200
        # Verify initiate_authorize was called with tenant_admin's tenant, not the override
        call_kwargs = mock_service.initiate_authorize.call_args
        assert call_kwargs.kwargs.get("tenant_id") == "acme" or (
            len(call_kwargs.args) >= 3 and call_kwargs.args[2] == "acme"
        )


# ============== Callback ==============


class TestCallback:
    """POST /v1/admin/mcp-connectors/callback"""

    def test_callback_success(self, app, mock_db_session):
        """Exchanges code+state for tokens and creates server."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            server = _mock_server()
            redirect_after = "/mcp-connectors"

            with (
                patch(TEMPLATE_REPO_PATH),
                patch(SESSION_REPO_PATH),
                patch(CONNECTOR_SERVER_REPO_PATH),
                patch(EXT_SERVER_REPO_PATH),
                patch(OAUTH_SERVICE_PATH) as MockOAuthService,
            ):
                mock_service = MockOAuthService.return_value
                mock_service.handle_callback = AsyncMock(return_value=(server, redirect_after))

                with TestClient(app) as client:
                    response = client.post(
                        f"{BASE}/callback",
                        json={"code": "auth-code-123", "state": "csrf-state"},
                    )

            assert response.status_code == 200
            data = response.json()
            assert data["server_id"] == str(server.id)
            assert data["server_name"] == server.name
            assert data["redirect_url"] == redirect_after
        finally:
            app.dependency_overrides.clear()

    def test_callback_invalid_state(self, app, mock_db_session):
        """Returns 400 for invalid/expired state token."""
        from src.database import get_db
        from src.services.connector_oauth import ConnectorOAuthError

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            with (
                patch(TEMPLATE_REPO_PATH),
                patch(SESSION_REPO_PATH),
                patch(CONNECTOR_SERVER_REPO_PATH),
                patch(EXT_SERVER_REPO_PATH),
                patch(OAUTH_SERVICE_PATH) as MockOAuthService,
            ):
                mock_service = MockOAuthService.return_value
                mock_service.handle_callback = AsyncMock(
                    side_effect=ConnectorOAuthError("Invalid or expired state token")
                )

                with TestClient(app) as client:
                    response = client.post(
                        f"{BASE}/callback",
                        json={"code": "auth-code", "state": "bad-state"},
                    )

            assert response.status_code == 400
            assert "Invalid or expired state token" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_callback_expired_state(self, app, mock_db_session):
        """Returns 400 for expired state token."""
        from src.database import get_db
        from src.services.connector_oauth import ConnectorOAuthError

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            with (
                patch(TEMPLATE_REPO_PATH),
                patch(SESSION_REPO_PATH),
                patch(CONNECTOR_SERVER_REPO_PATH),
                patch(EXT_SERVER_REPO_PATH),
                patch(OAUTH_SERVICE_PATH) as MockOAuthService,
            ):
                mock_service = MockOAuthService.return_value
                mock_service.handle_callback = AsyncMock(
                    side_effect=ConnectorOAuthError("OAuth state has expired, please try again")
                )

                with TestClient(app) as client:
                    response = client.post(
                        f"{BASE}/callback",
                        json={"code": "auth-code", "state": "expired-state"},
                    )

            assert response.status_code == 400
            assert "expired" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_callback_token_exchange_failure(self, app, mock_db_session):
        """Returns 502 when token exchange with provider fails."""
        from src.database import get_db
        from src.services.connector_oauth import ConnectorOAuthError

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            with (
                patch(TEMPLATE_REPO_PATH),
                patch(SESSION_REPO_PATH),
                patch(CONNECTOR_SERVER_REPO_PATH),
                patch(EXT_SERVER_REPO_PATH),
                patch(OAUTH_SERVICE_PATH) as MockOAuthService,
            ):
                mock_service = MockOAuthService.return_value
                mock_service.handle_callback = AsyncMock(
                    side_effect=ConnectorOAuthError(
                        "Failed to exchange authorization code (HTTP 401)",
                        status_code=502,
                    )
                )

                with TestClient(app) as client:
                    response = client.post(
                        f"{BASE}/callback",
                        json={"code": "bad-code", "state": "valid-state"},
                    )

            assert response.status_code == 502
        finally:
            app.dependency_overrides.clear()

    def test_callback_no_auth_required(self, app, mock_db_session):
        """Callback endpoint works WITHOUT authentication (browser redirect)."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        # Explicitly do NOT override get_current_user — callback has no auth dep
        app.dependency_overrides[get_db] = override_get_db

        try:
            server = _mock_server()

            with (
                patch(TEMPLATE_REPO_PATH),
                patch(SESSION_REPO_PATH),
                patch(CONNECTOR_SERVER_REPO_PATH),
                patch(EXT_SERVER_REPO_PATH),
                patch(OAUTH_SERVICE_PATH) as MockOAuthService,
            ):
                mock_service = MockOAuthService.return_value
                mock_service.handle_callback = AsyncMock(return_value=(server, None))

                with TestClient(app) as client:
                    response = client.post(
                        f"{BASE}/callback",
                        json={"code": "code", "state": "state"},
                    )

            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_callback_missing_fields(self, app, mock_db_session):
        """Returns 422 when required fields are missing."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        try:
            with TestClient(app) as client:
                response = client.post(
                    f"{BASE}/callback",
                    json={"code": "auth-code"},  # Missing 'state'
                )

            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()


# ============== Disconnect ==============


class TestDisconnect:
    """DELETE /v1/admin/mcp-connectors/{slug}/disconnect"""

    def test_disconnect_success(self, app_with_cpi_admin, mock_db_session):
        """Disconnects connector and returns server_id."""
        template = _mock_template()
        server_id = uuid4()

        with (
            patch(TEMPLATE_REPO_PATH) as MockTemplateRepo,
            patch(CONNECTOR_SERVER_REPO_PATH),
            patch(SESSION_REPO_PATH),
            patch(EXT_SERVER_REPO_PATH),
            patch(OAUTH_SERVICE_PATH) as MockOAuthService,
        ):
            MockTemplateRepo.return_value.get_by_slug = AsyncMock(return_value=template)
            mock_service = MockOAuthService.return_value
            mock_service.disconnect = AsyncMock(return_value=server_id)

            with TestClient(app_with_cpi_admin) as client:
                response = client.delete(f"{BASE}/linear/disconnect")

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == "linear"
        assert data["disconnected"] is True
        assert data["server_id"] == str(server_id)

    def test_disconnect_not_connected(self, app_with_cpi_admin, mock_db_session):
        """Returns 404 when connector is not connected for this tenant."""
        template = _mock_template()

        with (
            patch(TEMPLATE_REPO_PATH) as MockTemplateRepo,
            patch(CONNECTOR_SERVER_REPO_PATH),
            patch(SESSION_REPO_PATH),
            patch(EXT_SERVER_REPO_PATH),
            patch(OAUTH_SERVICE_PATH) as MockOAuthService,
        ):
            MockTemplateRepo.return_value.get_by_slug = AsyncMock(return_value=template)
            mock_service = MockOAuthService.return_value
            mock_service.disconnect = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.delete(f"{BASE}/linear/disconnect")

        assert response.status_code == 404
        assert "not connected" in response.json()["detail"]

    def test_disconnect_template_not_found(self, app_with_cpi_admin, mock_db_session):
        """Returns 404 when slug not found."""
        with patch(TEMPLATE_REPO_PATH) as MockTemplateRepo:
            MockTemplateRepo.return_value.get_by_slug = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.delete(f"{BASE}/nonexistent/disconnect")

        assert response.status_code == 404

    def test_disconnect_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        """Viewer gets 403."""
        with TestClient(app_with_no_tenant_user) as client:
            response = client.delete(f"{BASE}/linear/disconnect")

        assert response.status_code == 403

    def test_disconnect_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """Tenant admin can disconnect their own connectors."""
        template = _mock_template()
        server_id = uuid4()

        with (
            patch(TEMPLATE_REPO_PATH) as MockTemplateRepo,
            patch(CONNECTOR_SERVER_REPO_PATH),
            patch(SESSION_REPO_PATH),
            patch(EXT_SERVER_REPO_PATH),
            patch(OAUTH_SERVICE_PATH) as MockOAuthService,
        ):
            MockTemplateRepo.return_value.get_by_slug = AsyncMock(return_value=template)
            mock_service = MockOAuthService.return_value
            mock_service.disconnect = AsyncMock(return_value=server_id)

            with TestClient(app_with_tenant_admin) as client:
                response = client.delete(f"{BASE}/linear/disconnect")

        assert response.status_code == 200


# ============== Service Unit Tests ==============


class TestConnectorOAuthService:
    """Unit tests for ConnectorOAuthService business logic."""

    def test_initiate_authorize_builds_url(self):
        """initiate_authorize returns a valid authorize URL with state."""
        import asyncio

        from src.services.connector_oauth import ConnectorOAuthService

        template = _mock_template()
        template_repo = MagicMock()
        session_repo = MagicMock()
        session_repo.create = AsyncMock()
        session_repo.cleanup_expired = AsyncMock()
        connector_server_repo = MagicMock()
        connector_server_repo.get_by_template_and_tenant = AsyncMock(return_value=None)
        server_repo = MagicMock()

        service = ConnectorOAuthService(
            template_repo=template_repo,
            session_repo=session_repo,
            connector_server_repo=connector_server_repo,
            server_repo=server_repo,
        )

        with patch.object(
            service,
            "_get_provider_credentials",
            new=AsyncMock(return_value={"client_id": "test-client-id", "client_secret": "secret"}),
        ):
            url, state = asyncio.get_event_loop().run_until_complete(
                service.initiate_authorize(
                    template=template,
                    user_id="user-1",
                    tenant_id="acme",
                    redirect_after="/connectors",
                    redirect_uri="https://console.gostoa.dev/mcp-connectors/callback",
                )
            )

        assert "linear.app/oauth/authorize" in url
        assert "client_id=test-client-id" in url
        assert "state=" in url
        assert "code_challenge=" in url  # PKCE enabled for Linear
        assert "code_challenge_method=S256" in url
        assert len(state) > 20

    def test_initiate_authorize_already_connected(self):
        """initiate_authorize raises 409 when already connected."""
        import asyncio

        from src.services.connector_oauth import ConnectorOAuthError, ConnectorOAuthService

        template = _mock_template()
        connector_server_repo = MagicMock()
        connector_server_repo.get_by_template_and_tenant = AsyncMock(return_value=_mock_server())

        service = ConnectorOAuthService(
            template_repo=MagicMock(),
            session_repo=MagicMock(),
            connector_server_repo=connector_server_repo,
            server_repo=MagicMock(),
        )

        with pytest.raises(ConnectorOAuthError) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                service.initiate_authorize(template=template, user_id="u", tenant_id="acme")
            )
        assert exc_info.value.status_code == 409

    def test_initiate_authorize_no_pkce_when_not_required(self):
        """No PKCE params when oauth_pkce_required=False."""
        import asyncio

        from src.services.connector_oauth import ConnectorOAuthService

        template = _mock_template(oauth_pkce_required=False, slug="github")
        session_repo = MagicMock()
        session_repo.create = AsyncMock()
        session_repo.cleanup_expired = AsyncMock()
        connector_server_repo = MagicMock()
        connector_server_repo.get_by_template_and_tenant = AsyncMock(return_value=None)

        service = ConnectorOAuthService(
            template_repo=MagicMock(),
            session_repo=session_repo,
            connector_server_repo=connector_server_repo,
            server_repo=MagicMock(),
        )

        with patch.object(
            service,
            "_get_provider_credentials",
            new=AsyncMock(return_value={"client_id": "gh-id"}),
        ):
            url, _state = asyncio.get_event_loop().run_until_complete(
                service.initiate_authorize(
                    template=template,
                    user_id="u",
                    tenant_id="t",
                    redirect_uri="https://example.com/callback",
                )
            )

        assert "code_challenge" not in url
        assert "code_challenge_method" not in url

    def test_disconnect_returns_none_when_not_connected(self):
        """disconnect returns None when no server found."""
        import asyncio

        from src.services.connector_oauth import ConnectorOAuthService

        template = _mock_template()
        connector_server_repo = MagicMock()
        connector_server_repo.get_by_template_and_tenant = AsyncMock(return_value=None)

        service = ConnectorOAuthService(
            template_repo=MagicMock(),
            session_repo=MagicMock(),
            connector_server_repo=connector_server_repo,
            server_repo=MagicMock(),
        )

        result = asyncio.get_event_loop().run_until_complete(service.disconnect(template, "acme"))

        assert result is None

    def test_generate_code_challenge_s256(self):
        """PKCE S256 code challenge is correctly generated."""
        import base64
        import hashlib

        from src.services.connector_oauth import ConnectorOAuthService

        verifier = "test-code-verifier-string"
        challenge = ConnectorOAuthService._generate_code_challenge(verifier)

        # Manually verify S256
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

        assert challenge == expected
