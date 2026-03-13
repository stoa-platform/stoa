"""Regression test for CAB-1790: non-DCR connector client_secret lost between authorize and callback.

PR: #1726
Root cause: client_secret was resolved via Vault in handle_callback(), but if Vault was unavailable
the secret was lost. For non-DCR providers (GitHub, Slack, Notion) that require a client_secret,
the token exchange would fail silently.

Fix: Store client_secret in the ephemeral OAuthPendingSession during authorize, and use it as
fallback in handle_callback() when Vault is unavailable.

Invariant: client_secret provided during authorize MUST be available during callback,
regardless of Vault availability.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.mcp_connector_template import MCPConnectorTemplate, OAuthPendingSession
from src.services.connector_oauth import ConnectorOAuthService


@pytest.fixture
def mock_repos():
    """Create mock repositories for the OAuth service."""
    template_repo = MagicMock()
    session_repo = MagicMock()
    connector_server_repo = MagicMock()
    server_repo = MagicMock()
    return template_repo, session_repo, connector_server_repo, server_repo


@pytest.fixture
def non_dcr_template():
    """A connector template without DCR (e.g., GitHub, Slack, Notion)."""
    t = MagicMock(spec=MCPConnectorTemplate)
    t.id = uuid.uuid4()
    t.slug = "github"
    t.display_name = "GitHub"
    t.description = "GitHub MCP connector"
    t.icon_url = None
    t.mcp_base_url = "https://mcp.github.com"
    t.transport = "sse"
    t.oauth_authorize_url = "https://github.com/login/oauth/authorize"
    t.oauth_token_url = "https://github.com/login/oauth/access_token"
    t.oauth_scopes = "repo"
    t.oauth_pkce_required = False
    t.oauth_client_id = "test-client-id"
    t.oauth_registration_url = None  # No DCR
    return t


@pytest.mark.asyncio
async def test_regression_client_secret_stored_in_pending_session(mock_repos, non_dcr_template):
    """client_secret MUST be stored in the pending session during authorize."""
    template_repo, session_repo, connector_server_repo, server_repo = mock_repos

    # No existing connection
    connector_server_repo.get_by_template_and_tenant = AsyncMock(return_value=None)
    session_repo.create = AsyncMock()
    session_repo.cleanup_expired = AsyncMock()

    service = ConnectorOAuthService(
        template_repo=template_repo,
        session_repo=session_repo,
        connector_server_repo=connector_server_repo,
        server_repo=server_repo,
    )

    with patch.object(ConnectorOAuthService, "_resolve_client_id", return_value="test-client-id"):
        await service.initiate_authorize(
            template=non_dcr_template,
            user_id="user-1",
            tenant_id="tenant-1",
            redirect_after="/connectors",
            redirect_uri="https://console.example.com/mcp-connectors/callback",
            client_secret="my-secret-123",
        )

    # Verify the pending session was created WITH client_secret
    session_repo.create.assert_called_once()
    pending = session_repo.create.call_args[0][0]
    assert pending.client_secret == "my-secret-123", (
        "client_secret must be stored in pending session for non-DCR providers"
    )


@pytest.mark.asyncio
async def test_regression_client_secret_used_from_pending_when_vault_unavailable(
    mock_repos, non_dcr_template
):
    """When Vault is unavailable, client_secret from pending session MUST be used as fallback."""
    template_repo, session_repo, connector_server_repo, server_repo = mock_repos

    template_id = non_dcr_template.id
    pending = MagicMock(spec=OAuthPendingSession)
    pending.state = "test-state-token"
    pending.connector_template_id = template_id
    pending.user_id = "user-1"
    pending.tenant_id = "tenant-1"
    pending.code_verifier = None
    pending.redirect_after = "/connectors"
    pending.client_secret = "my-secret-123"  # Stored during authorize
    pending.expires_at = datetime.utcnow() + timedelta(minutes=5)

    session_repo.get_by_state = AsyncMock(return_value=pending)
    session_repo.delete = AsyncMock()
    template_repo.get_by_id = AsyncMock(return_value=non_dcr_template)

    service = ConnectorOAuthService(
        template_repo=template_repo,
        session_repo=session_repo,
        connector_server_repo=connector_server_repo,
        server_repo=server_repo,
    )

    # Vault unavailable: _resolve_client_secret returns empty
    with (
        patch.object(ConnectorOAuthService, "_resolve_client_id", return_value="test-client-id"),
        patch.object(ConnectorOAuthService, "_resolve_client_secret", return_value=""),
        patch.object(service, "_exchange_code_for_tokens", new_callable=AsyncMock) as mock_exchange,
    ):
        mock_exchange.return_value = {"access_token": "tok-123"}

        with (
            patch("src.services.connector_oauth.get_vault_client") as mock_vault,
        ):
            mock_vc = MagicMock()
            mock_vc.store_credential = AsyncMock(return_value=None)
            mock_vc.enabled = False
            mock_vault.return_value = mock_vc

            server_repo.create = AsyncMock(side_effect=lambda s: s)

            await service.handle_callback(
                code="auth-code-123",
                state="test-state-token",
                redirect_uri="https://console.example.com/mcp-connectors/callback",
            )

        # The exchange MUST have received the client_secret from the pending session
        mock_exchange.assert_called_once()
        call_kwargs = mock_exchange.call_args[1]
        assert call_kwargs["client_secret"] == "my-secret-123", (
            "client_secret from pending session must be used when Vault is unavailable"
        )
